# -*- coding: utf-8 -*-
"""
checkout.flow — the orchestration of «متابعة الخروج»: the tick, the four answers, WhatsApp,
the Airbnb message, the board, the 17:00 summary, the risk analysis, the report and the demo.

It talks to the outside world ONLY through HOST (checkout.host). Hostaway hooks are blocking
and run on this package's OWN small thread pool (run_blocking); Discord hooks are coroutines. Everything here is
therefore testable with a fake HOST, a temp brain.db and an injected `now`.

THE OWNER'S RULES, and where each one is enforced
  * No escalation to أصيل or the owner — there is no code path here that messages anyone but
    the turnover's own channel and the one board channel.
  * Warning only, never block — cleaners are warned through the oujact state and the card;
    nothing here refuses a cleaning submit.
  * The presser is accountable — every answer stores who pressed it (state_by / cw_events).
  * The demo is isolated — every write to Hostaway, oujact_checkout.json, the board, the
    report and the stats is behind `if not row["demo"]`, and readers filter demo=0.
"""

import asyncio
import datetime
import functools
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor

from . import db, engine, texts
from .host import HOST

CARD_BUTTONS = ("yes", "noanswer", "no", "contact", "surprise")
PROMPT_BUTTONS = ("yes", "noanswer", "no", "contact")

# Blocking work runs on its OWN pool. asyncio.to_thread shares one default pool with every
# background job in bot.py, and right after a deploy Hostaway work can hold all of it for
# minutes — a button press queued behind that shows «thinking…» forever (seen live on the
# first /checkout-demo, 2026-09-26). Six workers: one tick read + a few humans at once.
_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="checkout")

_locks = {}                      # (name, loop) -> asyncio.Lock, created on the running loop
_tcache = {"at": None, "day": None, "rows": {}}
_TURNOVER_TTL = 300              # seconds — Hostaway is read at most once per 5 minutes


def _lock(name):
    """One tick / sweep at a time (two sweeps must not post two cards), one board publish at a
    time. Built lazily on the running loop: a Lock made at import time would bind to a
    different loop than the one discord.py runs."""
    loop = asyncio.get_running_loop()
    key = (name, id(loop))
    lk = _locks.get(key)
    if lk is None:
        lk = _locks[key] = asyncio.Lock()
    return lk


# ------------------------------------------------------------------ config (all defaults correct)

def _env(name, default):
    return (os.environ.get(name, default) or default).strip()


def remind_min():
    try:
        return max(5, int(_env("CHECKOUT_REMIND_MIN", "30")))
    except ValueError:
        return 30


def deadline_str():
    v = _env("CHECKOUT_DEADLINE", "17:00")
    return v if engine.parse_hhmm(v) else "17:00"


def quiet_from():
    v = _env("CHECKOUT_QUIET_FROM", "23:00")
    return v if engine.parse_hhmm(v) else "23:00"


def quiet_to():
    v = _env("CHECKOUT_QUIET_TO", "08:00")
    return v if engine.parse_hhmm(v) else "08:00"


def airbnb_enabled():
    return _env("CHECKOUT_WATCH_AIRBNB", "1") == "1"


def board_channel_name():
    return _env("CHECKOUT_BOARD_CHANNEL", "متابعة-الخروج")


def demo_category_name():
    return _env("CHECKOUT_DEMO_CATEGORY", "🎬 تجربة الخروج")


def live():
    if HOST.is_live is not None:
        try:
            return bool(HOST.is_live())
        except Exception:
            return False
    return db.live()


def now():
    return HOST.now() if HOST.now else datetime.datetime.now(engine.tz())


def deadline(day):
    return engine.deadline_at(day, deadline_str())


def _iso(d):
    return engine.iso(d)


def _plus(now_, minutes):
    return _iso(now_ + datetime.timedelta(minutes=minutes))


# ------------------------------------------------------------------ Hostaway (5-minute cache)

def reset_cache():
    _tcache.update({"at": None, "day": None, "rows": {}})


async def turnovers(now_, fresh=False):
    """{lid: turnover} for every departure today. One Hostaway read per 5 minutes."""
    day = now_.date().isoformat()
    at = _tcache["at"]
    if (not fresh and at is not None and _tcache["day"] == day
            and (now_ - at).total_seconds() < _TURNOVER_TTL):
        return _tcache["rows"]
    try:
        rows = await run_blocking(HOST.require("today_turnovers")) or []
    except Exception as e:
        print("[checkout] turnovers unavailable:", e)
        return _tcache["rows"] if _tcache["day"] == day else {}
    out = {}
    for t in rows:
        try:
            lid = int(t.get("lid"))
        except (TypeError, ValueError):
            continue
        if str(t.get("day") or "")[:10] != day:
            continue
        prev = out.get(lid)
        if prev is None or str(t.get("checkout_at")) < str(prev.get("checkout_at")):
            out[lid] = t
    _tcache.update({"at": now_, "day": day, "rows": out})
    return out


async def run_blocking(fn, *args, **kwargs):
    """Like asyncio.to_thread, but on this package's own pool (see _pool)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_pool, functools.partial(fn, *args, **kwargs))


async def _thread(fn, *args):
    if fn is None:
        return None
    return await run_blocking(fn, *args)


# ------------------------------------------------------------------ Discord helpers

def _hint(row):
    if row.get("demo") or not HOST.early_hint:
        return False
    try:
        return bool(HOST.early_hint(row.get("lid")))
    except Exception:
        return False


def contact_button(row):
    """('link', label, url) — ONE tap opens the guest's WhatsApp chat with the message typed.
    Discord fixes a link button's URL when the message is posted and caps it at 512 chars,
    so it points at our short /cw/<token> link, which rebuilds the message and redirects.
    No phone → the Airbnb conversation instead; neither → no button."""
    lk = db.link_for(row["work_key"])
    base = ""
    if HOST.link_base:
        try:
            base = (HOST.link_base() or "").rstrip("/")
        except Exception:
            base = ""
    if lk and base and (row.get("phone") or row.get("demo")):
        return ("link", texts.BUTTON_LABELS["contact"], "%s/cw/%s" % (base, lk["token"]))
    if lk and lk.get("airbnb_url"):
        return ("link", texts.BUTTON_LABELS["airbnb"], lk["airbnb_url"])
    return None


def _with_contact(row, keys):
    out = []
    for k in keys:
        if k == "contact":
            b = contact_button(row)
            if b:
                out.append(b)
        else:
            out.append(k)
    return out


def card_buttons(row):
    if row.get("state") == engine.APPROVED:
        return []
    return _with_contact(row, CARD_BUTTONS)


def prompt_buttons(row):
    return _with_contact(row, PROMPT_BUTTONS)


async def ensure_contact(row):
    """Create the short link once per turnover; look the Airbnb link up only when there is
    no phone (it is a Hostaway call)."""
    if db.link_for(row["work_key"]):
        return
    airbnb = ""
    if not row.get("phone") and not row.get("demo") and HOST.guest_links and row.get("res_id"):
        try:
            links = await _thread(HOST.guest_links, row["res_id"]) or []
            airbnb = next((u for u, _l in links if "wa.me" not in u and len(u) <= 512), "")
        except Exception as e:
            print("[checkout] guest links failed:", e)
    db.ensure_link(row["work_key"], airbnb)


def wa_redirect(token):
    """The target of /cw/<token>: the full wa.me link, rebuilt fresh. BLOCKING-safe (sqlite)."""
    row = db.item_by_token(token)
    if not row:
        return None
    text = texts.wa_text(row.get("guest"), row.get("responsible") or "")
    number = ""
    if not row.get("demo") and row.get("phone") and HOST.wa_number:
        number = HOST.wa_number(row["phone"]) or ""
    if not number and not row.get("demo"):
        return None
    db.log_event(row["work_key"], "wa_link", "رابط", "", detail="opened")
    return texts.wa_link(number, text)


async def refresh_card(row):
    if not (row and row.get("card_message_id") and row.get("channel_id")):
        return False
    try:
        return await HOST.edit(row["channel_id"], row["card_message_id"],
                               embed=texts.card(row, deadline(row["day"]), _hint(row)),
                               buttons=card_buttons(row), demo=bool(row.get("demo")))
    except Exception as e:
        print("[checkout] card edit failed:", row.get("work_key"), e)
        return False


async def _disable_prompts(row):
    """The previous reminder's buttons are disabled by editing it — only the newest prompt
    (and the card) stays pressable, so the channel never shows five live copies."""
    for m in db.active_messages(row["work_key"]):
        try:
            await HOST.edit(m.get("channel_id") or row.get("channel_id"), m["message_id"],
                            buttons=prompt_buttons(row), disabled=True,
                            demo=bool(row.get("demo")))
        except Exception as e:
            print("[checkout] could not disable a prompt:", e)
        db.deactivate_message(m["message_id"])


async def _post(row, text, buttons=None):
    try:
        return await HOST.post(row["channel_id"], text=text, buttons=buttons,
                               demo=bool(row.get("demo")))
    except Exception as e:
        print("[checkout] post failed:", row.get("work_key"), e)
        return None


async def _prompt(row, kind, text):
    await _disable_prompts(row)
    mid = await _post(row, text, prompt_buttons(row))
    if mid:
        db.add_message(mid, row["work_key"], row.get("channel_id"), kind)
    return mid


async def _oujact(row, answer, by, reason_code=None):
    """The cleaners' warning: the dispatch/route page reads this state."""
    if row.get("demo"):
        return
    state = engine.oujact_state_for(answer, reason_code)
    try:
        if state and HOST.set_oujact_state:
            await _thread(HOST.set_oujact_state, row.get("lid"), row.get("day"), state, by)
        if answer == "yes" and HOST.log_oujact:
            await _thread(HOST.log_oujact, row.get("lid"), row.get("day"), "guest_out",
                          "متابعة الخروج ✅", by)
    except Exception as e:
        print("[checkout] oujact write failed:", row.get("work_key"), e)


# ------------------------------------------------------------------ Airbnb (§6)

def _is_block(res):
    return isinstance(res, str) or res is None


async def _airbnb(row, now_, second=False):
    """At most two messages; a block or an error is logged ONCE and never retried."""
    if not airbnb_enabled():
        return
    wk = row["work_key"]
    body = texts.airbnb_body(row.get("guest"), second=second)
    sent = int(row.get("airbnb_sent") or 0)
    if row.get("demo"):
        await _post(row, texts.demo_airbnb_preview(body))
        db.update_item(wk, {"airbnb_sent": sent + 1})
        return
    cid = str(row.get("conversation_id") or "").strip()
    if not cid:
        res = "no_conversation"
    else:
        try:
            res = await _thread(HOST.require("send_guest"), cid, body)
        except Exception as e:
            res = "error: %s" % str(e)[:80]
    if _is_block(res):
        db.log_event(wk, "airbnb_failed", detail=str(res or "empty"), at=_iso(now_))
        db.update_item(wk, {"airbnb_sent": engine.AIRBNB_MAX,
                            "airbnb_note": texts.airbnb_failed(res or "empty")})
        return
    db.log_event(wk, "airbnb_sent", detail="second" if second else "first", at=_iso(now_))
    db.update_item(wk, {"airbnb_sent": sent + 1,
                        "airbnb_note": texts.airbnb_sent_line(sent + 1)})


# ------------------------------------------------------------------ card attach (§5.1)

async def attach(ch, t, now_, kind="card_posted", present=None):
    """'posted' | 'exists' | 'cleaned' | 'failed'. Idempotent: the row is claimed by
    INSERT OR IGNORE before anything is posted, and a row that already has a card is left.
    The card only moves to another room when its own room is GONE — two rooms sharing one key
    must never make the card hop between them every tick."""
    lid, day = int(t["lid"]), str(t["day"])[:10]
    wk = "%s:%s" % (lid, day)
    chan = str(ch["channel_id"])
    row = db.item(wk)
    if row and row.get("card_message_id") and (
            str(row.get("channel_id")) == chan
            or (present is not None and str(row.get("channel_id")) in present)):
        return "exists"
    if row and row.get("state") in (engine.CLEANED, engine.APPROVED):
        return "cleaned"
    if not row:
        status = await _thread(HOST.cleaning_status, lid, day, chan) if HOST.cleaning_status else "none"
        if ch.get("review") or status in ("submitted", "approved"):
            return "cleaned"
        cov = {}
        if HOST.cover:
            try:
                cov = await _thread(HOST.cover, lid, day, chan) or {}
            except Exception as e:
                print("[checkout] cover lookup failed:", wk, e)
        did = str(cov.get("did") or "")
        if not did and cov.get("role_id"):
            did = "role:%s" % cov["role_id"]
        db.insert_item(wk, {
            "lid": lid, "day": day, "res_id": str(t.get("res_id") or ""),
            "unit": t.get("unit") or "", "guest": t.get("guest") or "",
            "phone": t.get("phone") or "", "conversation_id": str(t.get("conversation_id") or ""),
            "channel_name": t.get("channel_name") or "",
            "checkout_at": _iso(engine.parse_dt(t.get("checkout_at"))),
            "checkin_at": _iso(engine.parse_dt(t.get("checkin_at"))),
            "clean_minutes": int(t.get("clean_minutes") or HOST.clean_minutes_default or 40),
            "responsible": cov.get("name") or "", "responsible_did": did,
            "responsible_emoji": cov.get("emoji") or "",
            "channel_id": chan,
            "state": engine.initial_state(t.get("checkout_at"), now_),
        }, at=_iso(now_))
    elif str(row.get("channel_id")) != chan:
        db.update_item(wk, {"channel_id": chan, "card_message_id": None})   # room was re-opened
    row = db.item(wk)
    if row.get("card_message_id"):
        return "exists"
    await ensure_contact(row)
    mid = await HOST.post(chan, embed=texts.card(row, deadline(day), _hint(row)),
                          buttons=card_buttons(row), demo=False)
    if not mid:
        return "failed"
    db.update_item(wk, {"card_message_id": str(mid)})
    db.log_event(wk, kind, at=_iso(now_))
    return "posted"


# ------------------------------------------------------------------ one item's clock (§5.2, §5.7)

async def process(row, now_, present=None):
    """Cleaning link-up first, then whatever the clock owes. Returns the action taken."""
    wk, demo = row["work_key"], bool(row.get("demo"))
    if not demo:
        status = "none"
        if HOST.cleaning_status:
            status = await _thread(HOST.cleaning_status, row.get("lid"), row.get("day"),
                                   row.get("channel_id")) or "none"
        gone = present is not None and str(row.get("channel_id")) not in present
        if status == "approved" or (gone and row.get("state") == engine.CLEANED):
            if row.get("state") != engine.APPROVED:
                db.update_item(wk, {"state": engine.APPROVED, "state_at": _iso(now_),
                                    "next_action_at": None}, at=_iso(now_))
                if not db.has_event(wk, "approved"):
                    db.log_event(wk, "approved", at=_iso(now_))
                row = db.item(wk)
                if not gone:
                    await _disable_prompts(row)
                    await refresh_card(row)
                return "approved"
            return None
        if status == "submitted" and row.get("state") not in (engine.CLEANED, engine.APPROVED):
            db.update_item(wk, {"state": engine.CLEANED, "state_at": _iso(now_),
                                "next_action_at": None}, at=_iso(now_))
            if not db.has_event(wk, "submitted"):
                db.log_event(wk, "submitted", at=_iso(now_))
            row = db.item(wk)
            await _disable_prompts(row)
            await refresh_card(row)
            return "submitted"
        if gone:
            return None                         # the room is closed; nothing to post into

    act = engine.due_action(row, now_, quiet_from(), quiet_to(), demo=demo)
    if act is None:
        return None
    rm = remind_min()
    if act == "ping":
        db.update_item(wk, {"state": engine.ASKING, "pinged_at": _iso(now_),
                            "next_action_at": _plus(now_, rm)}, at=_iso(now_))
        row = db.item(wk)
        mid = await _prompt(row, "ping", texts.ping(row))
        db.log_event(wk, "ping", detail=str(mid or ""), at=_iso(now_))
    elif act == "remind":
        n = int(row.get("remind_count") or 0) + 1
        db.update_item(wk, {"remind_count": n, "next_action_at": _plus(now_, rm)}, at=_iso(now_))
        row = db.item(wk)
        mid = await _prompt(row, "remind", texts.remind(row, n, n * rm))
        db.log_event(wk, "remind", detail="%d|%s" % (n, mid or ""), at=_iso(now_))
        if row.get("state") == engine.NO_ANSWER and engine.airbnb_due(row, next_remind_count=n):
            await _airbnb(row, now_, second=True)
    elif act == "reask":
        db.update_item(wk, {"state": engine.ASKING, "pinged_at": _iso(now_), "remind_count": 0,
                            "next_action_at": _plus(now_, rm)}, at=_iso(now_))
        row = db.item(wk)
        mid = await _prompt(row, "reask", texts.reask(row))
        db.log_event(wk, "reask", detail=str(mid or ""), at=_iso(now_))
    await refresh_card(db.item(wk))
    return act


# ------------------------------------------------------------------ the tick (§11)

def _channel_day(ch):
    key = str(ch.get("key") or "")
    return key.split(":", 1)[1] if ":" in key else ""


async def tick(now_=None, force=False, kind="card_posted"):
    """One pass. `force` = the /checkout-start sweep: runs even while stopped and before 08:00."""
    async with _lock("tick"):
        now_ = now_ or now()
        if not force and not live():
            return {"skipped": "off"}
        day = now_.date().isoformat()
        rep = {"posted": [], "pinged": [], "cleaned": [], "actions": [], "no_channel": []}
        tmap = await turnovers(now_)
        try:
            chans = list(HOST.channels() or []) if HOST.channels else []
        except Exception as e:
            print("[checkout] channel scan failed:", e)
            chans = []
        present = {str(c["channel_id"]) for c in chans}
        keyed = {str(c.get("key")) for c in chans}
        rep["no_channel"] = sorted(t.get("unit") or str(lid) for lid, t in tmap.items()
                                   if "%s:%s" % (lid, day) not in keyed)
        if force or now_ >= engine.at_clock(day, "08:00"):
            for ch in chans:
                if _channel_day(ch) != day:
                    continue
                try:
                    lid = int(str(ch["key"]).split(":", 1)[0])
                except (TypeError, ValueError):
                    continue
                t = tmap.get(lid)
                if not t:
                    continue
                try:
                    res = await attach(ch, t, now_, kind=kind, present=present)
                except Exception as e:
                    print("[checkout] attach failed:", ch.get("key"), e)
                    continue
                if res == "posted":
                    rep["posted"].append(str(ch["key"]))
                elif res == "cleaned":
                    rep["cleaned"].append(str(ch["key"]))
        for row in db.items_for_day(day):
            try:
                act = await process(row, now_, present)
            except Exception as e:
                print("[checkout] item skipped:", row.get("work_key"), e)
                continue
            if act:
                rep["actions"].append((row["work_key"], act))
                if act == "ping" and row["work_key"] in rep["posted"]:
                    rep["pinged"].append(row["work_key"])
        if live():
            try:
                await publish_board(now_)
            except Exception as e:
                print("[checkout] board failed:", e)
            try:
                await maybe_summary(now_)
            except Exception as e:
                print("[checkout] summary failed:", e)
        return rep


async def start(by, now_=None):
    """/checkout-start: switch on, then sweep every turnover room of today."""
    db.set_setting("live", "1", by)
    return await tick(now_, force=True, kind="converted")


def stop(by):
    db.set_setting("live", "0", by)


# ------------------------------------------------------------------ the answers (§5.3–5.5)

async def _after_answer(row, now_):
    if not row.get("demo") and live():
        try:
            await publish_board(now_)
        except Exception as e:
            print("[checkout] board after answer failed:", e)


async def answer_yes(wk, by, by_did="", now_=None):
    now_ = now_ or now()
    if not db.item(wk):
        return {"ok": False, "message": texts.REPLY_NOT_FOUND}
    moved, row = db.transition(wk, engine.ALLOWED_FROM["yes"], {
        "state": engine.OUT, "state_by": by, "state_by_did": str(by_did or ""),
        "state_at": _iso(now_), "next_action_at": None}, at=_iso(now_))
    if not moved:
        return {"ok": False, "message": texts.reply_taken(row)}
    db.log_event(wk, "yes", by, by_did, at=_iso(now_))
    await _oujact(row, "yes", by)
    await _disable_prompts(row)
    await refresh_card(row)
    await _post(row, texts.YES_POST)
    await _after_answer(row, now_)
    return {"ok": True, "message": texts.reply_saved("yes", row)}


async def answer_noanswer(wk, by, by_did="", now_=None):
    now_ = now_ or now()
    row = db.item(wk)
    if not row:
        return {"ok": False, "message": texts.REPLY_NOT_FOUND}
    if row.get("state") == engine.NO_ANSWER:
        return {"ok": False, "message": texts.REPLY_NOANSWER_AGAIN}
    moved, row = db.transition(wk, engine.ALLOWED_FROM["noanswer"], {
        "state": engine.NO_ANSWER, "state_by": by, "state_by_did": str(by_did or ""),
        "state_at": _iso(now_), "remind_count": 0,
        "next_action_at": _plus(now_, remind_min())}, at=_iso(now_))
    if not moved:
        return {"ok": False, "message": texts.reply_taken(row)}
    db.log_event(wk, "noanswer", by, by_did, at=_iso(now_))
    await _oujact(row, "noanswer", by)
    if engine.airbnb_due(row, on_noanswer=True):
        await _airbnb(row, now_)
    row = db.item(wk)
    await refresh_card(row)
    await _after_answer(row, now_)
    return {"ok": True, "message": texts.reply_saved("noanswer", row)}


def can_answer(wk, kind):
    """Checked BEFORE the ⛔ form opens, so nobody fills a form that is already answered."""
    row = db.item(wk)
    if not row:
        return False, texts.REPLY_NOT_FOUND
    if row.get("state") not in engine.ALLOWED_FROM[kind]:
        return False, texts.reply_taken(row)
    return True, ""


async def answer_no(wk, by, by_did, reason_code, reason_text, choice, typed=None, now_=None):
    now_ = now_ or now()
    if not db.item(wk):
        return {"ok": False, "message": texts.REPLY_NOT_FOUND}
    if reason_code not in engine.REASON_CODES:
        return {"ok": False, "error": "reason", "message": "اختر السبب."}
    reason_text = (reason_text or "").strip()[:300]
    if reason_code == "other" and not reason_text:
        return {"ok": False, "error": "reason_text", "message": "اكتب السبب."}
    exp, err = engine.expected_from_choice(choice, now_, typed)
    if err:
        return {"ok": False, "error": err, "message": texts.EXPECT_ERRORS[err]}
    moved, row = db.transition(wk, engine.ALLOWED_FROM["no"], {
        "state": engine.INSIDE, "state_by": by, "state_by_did": str(by_did or ""),
        "state_at": _iso(now_), "reason_code": reason_code, "reason_text": reason_text,
        "expected_out_at": _iso(exp), "next_action_at": None, "remind_count": 0},
        at=_iso(now_))
    if not moved:
        return {"ok": False, "message": texts.reply_taken(row)}
    db.log_event(wk, "no", by, by_did, detail="%s|%s" % (reason_code, texts.hm(exp)),
                 at=_iso(now_))
    await _oujact(row, "no", by, reason_code)
    await _disable_prompts(row)
    await refresh_card(row)
    await _after_answer(row, now_)
    return {"ok": True, "message": texts.reply_saved("no", row)}


async def surprise(wk, by, by_did="", now_=None):
    """🚨 the team is at the door and the guest is inside. Logged against whoever pressed ✅."""
    now_ = now_ or now()
    before = db.item(wk)
    if not before:
        return {"ok": False, "message": texts.REPLY_NOT_FOUND}
    confirmer = before.get("state_by") if before.get("state") == engine.OUT else ""
    if not confirmer:
        yeses = db.events(wk, ["yes"])
        confirmer = yeses[-1]["actor"] if yeses else ""
    moved, row = db.transition(wk, engine.ALLOWED_FROM["surprise"], {
        "state": engine.INSIDE, "state_by": by, "state_by_did": str(by_did or ""),
        "state_at": _iso(now_), "reason_code": "surprise", "reason_text": "",
        "expected_out_at": None, "remind_count": 0,
        "next_action_at": _plus(now_, remind_min())}, at=_iso(now_))
    if not moved:
        return {"ok": False, "message": texts.reply_taken(row)}
    db.log_event(wk, "surprise", by, by_did, detail=confirmer or "", at=_iso(now_))
    await _oujact(row, "surprise", by)
    await refresh_card(row)
    await _post(row, texts.surprise_post(row))
    mid = await _prompt(row, "reask", texts.reask_now(row))
    db.log_event(wk, "reask", detail=str(mid or ""), at=_iso(now_))
    await _after_answer(row, now_)
    return {"ok": True, "message": texts.reply_saved("surprise", row)}


async def whatsapp(wk, presser_name, by_did="", now_=None):
    """{ok, url, links, message}. The link carries the PRESSER's name, not the bot's."""
    now_ = now_ or now()
    row = db.item(wk)
    if not row:
        return {"ok": False, "message": texts.REPLY_NOT_FOUND}
    text = texts.wa_text(row.get("guest"), presser_name)
    out = {"ok": True, "url": "", "links": [], "message": texts.WA_REPLY}
    if row.get("demo"):
        out.update(url=texts.wa_link("", text), message=texts.WA_DEMO)
    else:
        number = ""
        if row.get("phone") and HOST.wa_number:
            number = HOST.wa_number(row["phone"]) or ""
        if number:
            out["url"] = texts.wa_link(number, text)
        else:
            links = []
            if HOST.guest_links and row.get("res_id"):
                try:
                    links = await _thread(HOST.guest_links, row["res_id"]) or []
                except Exception as e:
                    print("[checkout] guest links failed:", e)
            out.update(links=[(u, lab) for u, lab in links if "wa.me" not in u],
                       message=texts.WA_NO_PHONE)
    db.log_event(wk, "wa_link", presser_name, by_did,
                 detail="phone" if out["url"] and not row.get("demo") else
                 ("demo" if row.get("demo") else "no_phone"), at=_iso(now_))
    return out


def submitted_before_out(wk, by=""):
    """The extra warning after a cleaning submit (§5.8). True when the line must be posted."""
    row = db.item(wk)
    if not row or row.get("demo") or row.get("state") in (engine.OUT, engine.APPROVED):
        return False
    if row.get("state") == engine.CLEANED and db.has_event(wk, "submitted"):
        return False
    db.log_event(wk, "submitted", by, detail="before_out")
    return True


# ------------------------------------------------------------------ board (§10)

def _risk_ctx(rows, now_):
    """{work_key: (level, code)} with the surprise + early check-in facts filled in."""
    surprised = {e["work_key"] for e in db.events_for_keys([r["work_key"] for r in rows])
                 if e["kind"] == "surprise"}
    out = {}
    for r in rows:
        early = False
        if HOST.early_checkin and not r.get("demo"):
            try:
                early = bool(HOST.early_checkin(r.get("lid"), r.get("day")))
            except Exception:
                early = False
        out[r["work_key"]] = engine.risk(r, now_, deadline(r["day"]),
                                         r["work_key"] in surprised, early)
    return out


def board_chunks(rows, now_):
    risk = _risk_ctx(rows, now_)
    buckets = {k: [] for k, _ in texts.BOARD_SECTIONS}
    for r in rows:
        st = r.get("state")
        if st in (engine.INSIDE, engine.NO_ANSWER) or (
                st in engine.OPEN and risk[r["work_key"]][0] == engine.RED):
            buckets["act"].append(r)
        elif st in (engine.WAITING, engine.ASKING):
            buckets["wait"].append(r)
        elif st == engine.OUT:
            buckets["out"].append(r)
        elif st == engine.CLEANED:
            buckets["review"].append(r)
        else:
            buckets["done"].append(r)
    body = []
    for key, title in texts.BOARD_SECTIONS:
        if not buckets[key]:
            continue
        body.append("")
        body.append("**%s** (%d)" % (title, len(buckets[key])))
        body.extend("• " + texts.board_line(r) for r in buckets[key])
    if not rows:
        body = ["", texts.BOARD_EMPTY]
    chunks, cur = [], ""
    for line in body:
        piece = line + texts.NL
        if len(cur) + len(piece) > 1850:
            chunks.append(cur)
            cur = ""
        cur += piece
    if cur.strip():
        chunks.append(cur)
    if len(chunks) > 2:                         # the board keeps 1–2 messages, never a stream
        chunks = chunks[:2]
        chunks[1] = chunks[1][:1800] + texts.NL + "…"
    return chunks


async def publish_board(now_):
    """Edits 1–2 messages in place, and ONLY when the content changed (content hash)."""
    async with _lock("board"):
        return await _publish_board(now_)


async def _publish_board(now_):
    rows = db.items_for_day(now_.date().isoformat())
    chunks = board_chunks(rows, now_)
    h = hashlib.sha1(texts.NL.join(chunks).encode("utf-8")).hexdigest()
    if db.setting("board_hash") == h and db.board_message_ids():
        return False
    ch = await HOST.require("board_channel")()
    if not ch:
        return False
    if db.setting("board_channel_id") != str(ch):
        db.set_board_message_ids([])
        db.set_setting("board_channel_id", str(ch))
    ids = db.board_message_ids()
    out_ids = []
    for i, chunk in enumerate(chunks):
        text = (texts.board_header(now_) + texts.NL + chunk) if i == 0 else chunk
        ok = False
        if i < len(ids):
            ok = await HOST.edit(ch, ids[i], text=text)
            if ok:
                out_ids.append(ids[i])
        if not ok:
            mid = await HOST.post(ch, text=text, mentions=False)
            if mid:
                out_ids.append(str(mid))
    for extra in ids[len(chunks):]:
        await HOST.edit(ch, extra, text="‏—")
        out_ids.append(extra)
    db.set_board_message_ids(out_ids)
    db.set_setting("board_hash", h)
    return True


async def maybe_summary(now_):
    """17:00: one new message per day in the board channel. Names no person."""
    day = now_.date().isoformat()
    dl = deadline(day)
    if now_ < dl or db.daily_claimed(day):
        return False
    rows = db.items_for_day(day)
    if not db.claim_daily(day, _iso(now_)):
        return False
    approved_at = {e["work_key"]: e["at"] for e in db.events_for_keys([r["work_key"] for r in rows])
                   if e["kind"] == "approved"}
    on_time, late = 0, []
    for r in rows:
        at = engine.parse_dt(approved_at.get(r["work_key"]))
        if at and at < dl:
            on_time += 1
        else:
            late.append(r.get("unit") or r["work_key"])
            db.log_event(r["work_key"], "deadline_miss", at=_iso(now_))
    ch = await HOST.require("board_channel")()
    if ch:
        await HOST.post(ch, text=texts.summary(len(rows), on_time, late), mentions=False)
    return True


# ------------------------------------------------------------------ risk analysis (§8.3)

async def risk_rows(now_, demo_only=False):
    """Every departure today, with the watch state when there is one. Computed live even
    while the watch is stopped."""
    day = now_.date().isoformat()
    if demo_only:
        return db.demo_items()
    tmap = await turnovers(now_)
    stored = {r["work_key"]: r for r in db.items_for_day(day)}
    rows = []
    for lid, t in sorted(tmap.items(), key=lambda kv: str(kv[1].get("unit") or "")):
        wk = "%s:%s" % (lid, day)
        if wk in stored:
            rows.append(stored[wk])
            continue
        cov = {}
        if HOST.cover:
            try:
                cov = await _thread(HOST.cover, lid, day, None) or {}
            except Exception:
                cov = {}
        status = await _thread(HOST.cleaning_status, lid, day, None) if HOST.cleaning_status else "none"
        st = engine.initial_state(t.get("checkout_at"), now_)
        if status == "approved":
            st = engine.APPROVED
        elif status == "submitted":
            st = engine.CLEANED
        rows.append({"work_key": wk, "lid": lid, "day": day, "unit": t.get("unit"),
                     "guest": t.get("guest"), "responsible": cov.get("name") or "",
                     "responsible_emoji": cov.get("emoji") or "",
                     "checkout_at": _iso(engine.parse_dt(t.get("checkout_at"))),
                     "checkin_at": _iso(engine.parse_dt(t.get("checkin_at"))),
                     "clean_minutes": int(t.get("clean_minutes") or HOST.clean_minutes_default or 40),
                     "state": st, "demo": 0})
    return rows


def risk_chunks(rows, now_):
    risk = _risk_ctx(rows, now_)
    counts = {}
    for r in rows:
        counts[risk[r["work_key"]][0]] = counts.get(risk[r["work_key"]][0], 0) + 1
    with_ci = sum(1 for r in rows if r.get("checkin_at"))
    lines = [texts.risk_header(len(rows), with_ci, counts)]
    ordered = sorted(rows, key=lambda r: (engine.RISK_ORDER[risk[r["work_key"]][0]],
                                          str(r.get("checkin_at") or "~"), str(r.get("unit"))))
    for r in ordered:
        lvl, code = risk[r["work_key"]]
        if lvl in (engine.RED, engine.ORANGE):
            lines.append(texts.risk_line(r, lvl, code, deadline(r["day"])))
    for lvl in (engine.GREEN, engine.DONE):
        units = [str(r.get("unit")) for r in ordered if risk[r["work_key"]][0] == lvl]
        if units:
            lines.append(texts.risk_rest(lvl, units))
    return _split(lines)


def _split(lines, limit=1900):
    chunks, cur = [], ""
    for line in lines:
        piece = line + texts.NL
        if len(piece) > limit:
            piece = piece[:limit - 2] + "…" + texts.NL
        if len(cur) + len(piece) > limit:
            chunks.append(cur)
            cur = ""
        cur += piece
    if cur.strip():
        chunks.append(cur)
    return chunks


# ------------------------------------------------------------------ report (§8.6)

def report_text(now_, days=1):
    end = now_.date()
    start = end - datetime.timedelta(days=max(1, int(days)) - 1)
    rows = db.items_between(start.isoformat(), end.isoformat())
    evs = db.events_for_keys([r["work_key"] for r in rows])
    people = engine.person_report(rows, evs, deadline)
    title = "تقرير الخروج — اليوم" if days <= 1 else "تقرير الخروج — آخر %d أيام" % days
    return _split(texts.report(people, title).split(texts.NL))


# ------------------------------------------------------------------ demo (§9)

def _demo_times(now_, scenario):
    base = (now_ + datetime.timedelta(minutes=30)).replace(second=0, microsecond=0)
    checkin = None
    if scenario == "no":
        four = engine.at_clock(now_.date(), "16:00")
        later = (now_ + datetime.timedelta(hours=2)).replace(second=0, microsecond=0)
        checkin = four if now_ < four - datetime.timedelta(hours=2) else later
        if checkin.date() != now_.date():
            checkin = None
    return base, checkin


async def demo_setup(channels, by, by_did, now_=None, emoji=""):
    """channels = {scenario: channel_id}. Resets every demo row, then each apartment room gets
    what a REAL turnover room shows: the Turnover card first (built by bot.py's own
    _oujact_card_embed through HOST.turnover_card, so it is not a look-alike), then the
    Checkout Watch card under it — the add-on, same layout. No script, no badge; the owner
    narrates. The risk room starts empty; /checkout-risk typed there reads the demo rows."""
    now_ = now_ or now()
    db.delete_demo()
    day = now_.date().isoformat()
    n = 0
    for _name, scen, unit in texts.DEMO_CHANNELS:
        ch = channels.get(scen)
        if not ch:
            continue
        if scen == "risk":
            db.set_setting("demo_risk_channel", str(ch))
            continue
        n += 1
        co, ci = _demo_times(now_, scen)
        if HOST.turnover_card:
            try:
                tcard = HOST.turnover_card(unit, co, ci, by, emoji)
                await HOST.post(ch, embed=tcard, buttons=["demo_submit"], demo=True,
                                mentions=False)
            except Exception as e:
                print("[checkout] demo turnover card failed:", e)
        wk = "demo:%d" % n
        db.insert_item(wk, {"lid": 0, "day": day, "unit": unit, "guest": texts.DEMO_GUEST,
                            "phone": "", "conversation_id": "", "channel_name": "Airbnb",
                            "checkout_at": _iso(co), "checkin_at": _iso(ci),
                            "clean_minutes": int(HOST.clean_minutes_default or 40),
                            "responsible": by, "responsible_did": str(by_did or ""),
                            "responsible_emoji": emoji or "",
                            "channel_id": str(ch), "state": engine.WAITING, "demo": 1},
                       at=_iso(now_))
        row = db.item(wk)
        await ensure_contact(row)
        mid = await HOST.post(ch, embed=texts.card(row, deadline(day)),
                              buttons=card_buttons(row), demo=True, mentions=False)
        if mid:
            db.update_item(wk, {"card_message_id": str(mid)})
            db.log_event(wk, "card_posted")
    return len(db.demo_items())


async def demo_submit(channel_id, by, by_did="", now_=None):
    """📷 Submit for Review pressed in a DEMO room: act out what the real button does to the
    watch — the confirmation line, the card moves to «بانتظار الاعتماد», and the before-out
    warning when nobody pressed ✅ first. It never touches the cleaning-report store."""
    now_ = now_ or now()
    row = db.demo_item_by_channel(channel_id)
    if not row:
        return {"ok": False, "message": texts.REPLY_NOT_FOUND}
    if row.get("state") in (engine.CLEANED, engine.APPROVED):
        return {"ok": False, "message": texts.DEMO_ALREADY_SUBMITTED}
    wk = row["work_key"]
    before_out = row.get("state") != engine.OUT
    await _post(row, texts.demo_submitted(texts.mention(by_did) or by))
    if before_out:
        await _post(row, texts.BEFORE_OUT)
    db.update_item(wk, {"state": engine.CLEANED, "state_at": _iso(now_), "next_action_at": None},
                   at=_iso(now_))
    db.log_event(wk, "submitted", by, by_did, detail="before_out" if before_out else "",
                 at=_iso(now_))
    row = db.item(wk)
    await _disable_prompts(row)
    await refresh_card(row)
    return {"ok": True, "message": "✅ (تجربة) انرسل للمراجعة."}


async def demo_next(channel_id, now_=None):
    """/checkout-demo-next typed inside a demo apartment room: the next timed step happens
    now. The reply is private to whoever typed it; the team only sees the real message."""
    row = db.demo_item_by_channel(channel_id)
    if not row:
        return {"ok": False, "message": "اكتب الأمر داخل غرفة شقة من شقق التجربة."}
    return await demo_ff(row["work_key"], now_)


async def demo_ff(wk, now_=None):
    """⏩ — makes the next timed step (ping, reminder, re-ask) happen NOW by moving the demo
    row's clock back by exactly the wait. Demo rows only."""
    now_ = now_ or now()
    row = db.item(wk)
    if not row or not row.get("demo"):
        return {"ok": False, "message": "هذا الزر للتجربة بس."}
    due = engine.next_due_at(row)
    if due is None:
        return {"ok": False, "message": "ما فيه خطوة جاية بالوقت — اضغط زر من أزرار الكرت."}
    delta = max(datetime.timedelta(0), due - now_)
    shifted = {}
    for f in ("checkout_at", "checkin_at", "expected_out_at", "next_action_at", "pinged_at",
              "state_at"):
        d = engine.parse_dt(row.get(f))
        if d:
            shifted[f] = _iso(d - delta)
    db.update_item(wk, shifted)
    act = await process(db.item(wk), now_)
    mins = int(delta.total_seconds() // 60)
    return {"ok": True, "action": act,
            "message": "⏩ قدمنا الوقت %d دقيقة." % mins if mins else "⏩ تم."}


def demo_end():
    n = db.delete_demo()
    db.set_setting("demo_risk_channel", "")
    return n
