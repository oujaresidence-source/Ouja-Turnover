# -*- coding: utf-8 -*-
"""
reviewask.flow — the orchestration of «رفع التقييم»: opening rooms, the clock, the presses,
review detection, cancellations, the board, the 30-min monitor report, the 22:00 summary, the
private report and the 7-day room sweep.

It talks to the outside world ONLY through HOST (reviewask.host). Blocking work runs on this
package's OWN pool (run_blocking) — never asyncio.to_thread, whose shared pool jams after a
deploy (CLAUDE.md trap 6). Everything is testable with a fake HOST, a temp brain.db and an
injected `now`.

OWNER RULES, and where each one is enforced
  * R1 rooms, one per reservation — db UNIQUE + HOST.once_claim + HOST.known_rooms (topics).
  * R7 only closed review rooms are deleted, ≥7 days after closing, topic re-checked, the
    transcript saved first — sweep_closed is the ONLY caller of HOST.delete_room.
  * R9 ships OFF — tick() returns at once until /reviews-start; buttons still record.
  * Nothing guest-facing 22:00–13:00 — engine.next_action holds pings and reminders.
"""

import asyncio
import datetime
import functools
import hashlib
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from . import config, db, engine, texts
from .host import HOST

NL = chr(10)

_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="reviewask")
_locks = {}
_dcache = {}
_DEP_TTL = 600                  # seconds — the departure window is read at most every 10 min
_OPEN_EVERY = 1800              # seconds between catch-up opening passes for one day
_SWEEP_EVERY = 3600             # the hourly deletion sweep
_CANCEL_EVERY = 600
_MISSING_REREAD = 5             # rows re-read by id per tick when missing from the window

CALL_OUTCOMES = ("rated", "promise", "noanswer", "later", "complaint", "decline", "wrong",
                 "satisfied")
WA_OUTCOMES = ("sent", "no_phone", "replied_will", "replied_no", "replied_quiet")


def _lock(name):
    loop = asyncio.get_running_loop()
    key = (name, id(loop))
    lk = _locks.get(key)
    if lk is None:
        lk = _locks[key] = asyncio.Lock()
    return lk


async def run_blocking(fn, *args, **kwargs):
    """Like asyncio.to_thread, but on this package's own pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_pool, functools.partial(fn, *args, **kwargs))


def now():
    return HOST.now() if HOST.now else datetime.datetime.now(engine.tz())


def cfg():
    return config.snapshot()


def _iso(d):
    return engine.iso(d)


def live():
    if HOST.is_live is not None:
        try:
            return bool(HOST.is_live())
        except Exception:
            return False
    return db.live(config.live_env())


def start(by):
    db.set_setting("live", "1", by)


def stop(by):
    db.set_setting("live", "0", by)


def reset_caches():
    _dcache.clear()


# ------------------------------------------------------------------ reads (BLOCKING)

def _reviews(strict=False):
    """The review list (bot.py's in-memory _reviews). Read up to 3 times — another thread may be
    merging a fresh pull. strict=True raises instead of answering [] (see plan_day)."""
    err = None
    for _ in range(3):
        try:
            return list(HOST.reviews() or []) if HOST.reviews else []
        except Exception as e:
            err = e
    print("[reviewask] reviews unavailable:", err)
    if strict:
        raise RuntimeError("reviews unavailable: %s" % err)
    return []


def program(reviews=None):
    """{lid: status} — the weak-apartment list (spec §3)."""
    counts = {}
    if HOST.open_ticket_counts:
        try:
            counts = HOST.open_ticket_counts() or {}
        except Exception as e:
            print("[reviewask] open ticket count failed:", e)
    return engine.apartment_status(_reviews() if reviews is None else reviews, db.overrides(),
                                   counts, config.threshold(), config.min_reviews())


def reviews_by_reservation():
    out = {}
    for r in engine.counted_reviews(_reviews()):
        res = str(r.get("reservation_id") or "").strip()
        if res:
            out[res] = r
    return out


def departures(start_iso, end_iso, fresh=False):
    """Targeted departure window, cached 10 min. None = the read failed (never 'no stays')."""
    key = (start_iso, end_iso)
    hit = _dcache.get(key)
    if hit and not fresh and time.time() - hit[0] < _DEP_TTL:
        return hit[1]
    try:
        rows = list(HOST.require("departures")(start_iso, end_iso) or [])
    except Exception as e:
        print("[reviewask] departures unavailable:", e)
        return hit[1] if hit else None
    _dcache[key] = (time.time(), rows)
    return rows


def plan_day(day, known=()):
    """BLOCKING. -> {day, eligible: [...], skipped: [...], error}. Every skip has a reason."""
    day = engine.parse_day(day).isoformat()
    rows = departures(day, day)
    out = {"day": day, "eligible": [], "skipped": [], "error": ""}
    if rows is None:
        out["error"] = "ما قدرت أقرأ الحجوزات من Hostaway — جرب بعد شوي."
        return out
    # No reviews at all would make EVERY apartment look new (< 3 reviews → in the program) and
    # open rooms for strong ones. An empty or unreadable list is an error, never "all weak".
    try:
        revs = _reviews(strict=True)
    except RuntimeError:
        revs = []
    if not revs:
        out["error"] = "ما قدرت أقرأ التقييمات — ما فتحت شي، جرب بعد شوي."
        return out
    audit = engine.type_audit(revs)
    if audit["unknown_types"]:
        # the guest/host filter does not understand this data — never guess which reviews count
        out["error"] = ("فيه نوع تقييم ما نعرفه (%s) — ما فتحت شي لين نراجع الفلتر."
                        % "، ".join(audit["unknown_types"][:5]))
        return out
    # 2026-10-03 lesson: the live bot held only the May CSV seed, so 50 of 82 apartments looked
    # weak and 60 rooms opened. No fresh review from Hostaway itself = no decision at all.
    today = engine.parse_day(now().date())
    newest = engine.newest_live_review(revs, today)
    if newest is None or (today - newest).days > config.fresh_days():
        out["error"] = ("ما وصلتني تقييمات جديدة من Hostaway (آخر تقييم: %s) — ما فتحت شي، "
                        "لأن الحسبة على بيانات قديمة تفتح غرف لشقق ما تحتاج." % (newest or "ولا واحد"))
        return out
    prog = program(revs)
    reviewed = {str(r.get("reservation_id")): r for r in engine.counted_reviews(revs)
                if str(r.get("reservation_id") or "").strip()}
    known = {str(k) for k in (known or ())}
    seen = set()
    for r in sorted(rows, key=lambda x: str(x.get("unit") or "")):
        res_id = str(r.get("res_id") or "")
        if not res_id or res_id in seen or str(r.get("departure") or "")[:10] != day:
            continue
        seen.add(res_id)
        lid = r.get("lid")
        try:
            lid = int(lid)
        except (TypeError, ValueError):
            lid = None
        st = prog.get(lid) if lid is not None else None
        in_prog = st["in_program"] if st else engine.in_program(0, 0, config.threshold(),
                                                                config.min_reviews())
        exists = res_id in known or db.by_reservation(res_id) is not None
        care = ""       # owner ruling 2026-10-03: weak apartments ONLY — no care-mode rooms
        mode, skip = engine.eligibility(dict(r, lid=lid), in_prog, bool(care), exists=exists)
        if mode and res_id in reviewed:
            mode, skip = None, "already_reviewed"
        item = {"res_id": res_id, "lid": lid, "unit": r.get("unit") or "", "guest": r.get("guest") or "",
                "phone": r.get("phone") or "", "conversation_id": str(r.get("conversation_id") or ""),
                "arrival": str(r.get("arrival") or "")[:10], "day": day}
        if mode:
            st = st or {}
            item.update({"mode": mode, "care_reason": care, "avg": st.get("avg"),
                         "n": st.get("n") or 0,
                         "needed": st.get("needed") if st else config.min_reviews()})
            out["eligible"].append(item)
        else:
            item["reason"] = skip
            out["skipped"].append(item)
    return out


# ------------------------------------------------------------------ opening rooms (§5)

async def open_rooms(day, by="", dry=None, now_=None):
    """/reviews-tomorrow, /reviews-today and the 00:05 catch-up. Idempotent: the DB row is
    claimed first (UNIQUE), then _once_claim, then the room; Discord topics count as rooms."""
    async with _lock("open"):
        now_ = now_ or now()
        known = {}
        if HOST.known_rooms:
            try:
                known = HOST.known_rooms() or {}
            except Exception as e:
                print("[reviewask] room scan failed:", e)
        plan = await run_blocking(plan_day, day, set(known))
        dry = (not live()) if dry is None else bool(dry)
        rep = {"day": plan["day"], "opened": [], "existing": [], "failed": [],
               "skipped": plan["skipped"], "would_open": [], "error": plan["error"]}
        if dry:
            rep["would_open"] = plan["eligible"]
            return rep
        for it in plan["eligible"]:
            res = await _open_one(it, by, now_)
            rep[res].append(it)
        return rep


async def _open_one(it, by, now_):
    """'opened' | 'existing' | 'failed'."""
    created, row = db.insert_ticket({
        "reservation_id": it["res_id"], "lid": it["lid"], "day": it["day"],
        "arrival": it.get("arrival"), "unit": it["unit"], "guest": it["guest"],
        "phone": it.get("phone") or "", "conversation_id": it.get("conversation_id") or "",
        "mode": it["mode"], "care_reason": it.get("care_reason") or "",
        "state": engine.WAITING, "avg_at_open": it.get("avg"), "n_at_open": it.get("n") or 0,
        "needed_at_open": it.get("needed"), "created_by": by or "النظام",
    }, at=_iso(now_))
    if row is None:
        return "failed"
    if row.get("channel_id"):
        return "existing"
    key = "reviewask:open:%s" % it["res_id"]
    if HOST.once_claim and not HOST.once_claim(key):
        return "existing"
    try:
        cov = await _cover(row, now_.date())
        if cov:
            db.update_ticket(row["id"], cov)
        name = engine.room_name(row["unit"], row["guest"])
        topic = engine.topic(row["reservation_id"], row["lid"], row["id"])
        row = db.ticket(row["id"])
        # PRIVATE: only the responsible manager (+ admins + the bot) sees the room (owner 2026-10-03)
        ch = await HOST.require("open_room")(name, topic, _person(row.get("responsible_did")))
        if not ch:
            raise RuntimeError("no channel")
        db.update_ticket(row["id"], {"channel_id": str(ch)})
        row = db.ticket(row["id"])
        await ensure_link(row)
        mid = await HOST.post(str(ch), embed=texts.card(row), buttons=None, mentions=False)
        if mid:
            db.update_ticket(row["id"], {"card_message_id": str(mid)})
        db.log_event(row["id"], "opened", by or "النظام", "",
                     detail="%s|%s" % (row["mode"], name), at=_iso(now_))
        return "opened"
    except Exception as e:
        if HOST.once_release:
            try:
                HOST.once_release(key)
            except Exception:
                pass
        print("[reviewask] room open failed (will retry):", it.get("res_id"), e)
        return "failed"


def _person(did):
    """A Discord user id, or '' for a role / nobody (a role would expose the room to a team)."""
    did = str(did or "")
    return did if did.isdigit() else ""


async def _grant(row, did):
    """Let a newly responsible manager see an existing room (the call on day+1 can be someone else)."""
    if not (HOST.grant and row.get("channel_id") and _person(did)):
        return
    try:
        await HOST.grant(row["channel_id"], _person(did))
    except Exception as e:
        print("[reviewask] could not add the responsible person to the room:", row.get("id"), e)


async def _cover(row, day):
    """{responsible, responsible_did} for the day of the ACTION (Employee Calendar first)."""
    if not HOST.cover:
        return {}
    try:
        cov = await run_blocking(HOST.cover, row.get("lid"), day.isoformat()) or {}
    except Exception as e:
        print("[reviewask] cover lookup failed:", e)
        return {}
    did = str(cov.get("did") or "")
    if not did and cov.get("role_id"):
        did = "role:%s" % cov["role_id"]
    return {"responsible": cov.get("name") or "", "responsible_did": did}


# ------------------------------------------------------------------ WhatsApp (R4)

async def ensure_link(row):
    if row and not db.link_for(row["id"]):
        db.ensure_link(row["id"])


def _base():
    if not HOST.link_base:
        return ""
    try:
        return (HOST.link_base() or "").rstrip("/")
    except Exception:
        return ""


def _number(row):
    if row.get("phone") and HOST.wa_number:
        try:
            return HOST.wa_number(row["phone"]) or ""
        except Exception:
            return ""
    return ""


def values_for(row):
    return {"الاسم": engine.guest_first(row.get("guest")) or "",
            "الموظف": row.get("responsible") or "فريق عوجا",
            "الشقة": engine.unit_short(row.get("unit")) or "",
            "رابط_التقييم": config.review_url()}


def guest_message(row, number=None):
    number = _number(row) if number is None else number
    lang = engine.language(number)
    text, _unknown = engine.render_template(engine.pick_template(db.templates(), lang),
                                            values_for(row))
    return text, lang


def wa_url(number, text):
    enc = urllib.parse.quote(text, safe="")
    if number:
        return "https://%s?text=%s" % (number, enc)
    return "https://wa.me/?text=%s" % enc


def wa_redirect(token):
    """BLOCKING. The target of /rv/<token>: wa.me with the owner's message typed, signed with
    the RESPONSIBLE person's name (a link button cannot know who pressed it)."""
    row = db.by_token(token)
    if not row:
        return None
    number = _number(row)
    if not number:
        return None
    text, lang = guest_message(row, number)
    db.log_event(row["id"], "wa_opened", "رابط", "", detail=lang)
    return wa_url(number, text)


def call_script(row):
    text, _u = engine.render_template(db.templates().get("call_script") or "", values_for(row))
    return text


def buttons_for(row):
    out = []
    for k in engine.stage_buttons(row):
        if k == "wa":
            lk = db.link_for(row["id"])
            base = _base()
            if lk and base and row.get("phone"):
                out.append(("link", texts.BUTTON_LABELS["wa"], "%s/rv/%s" % (base, lk["token"])))
            continue
        out.append(k)
    return out


# ------------------------------------------------------------------ Discord helpers

async def refresh_card(row):
    if not (row and row.get("card_message_id") and row.get("channel_id")):
        return False
    try:
        return await HOST.edit(row["channel_id"], row["card_message_id"], embed=texts.card(row),
                               buttons=None)
    except Exception as e:
        print("[reviewask] card edit failed:", row.get("id"), e)
        return False


async def _disable_prompts(row):
    for m in db.active_messages(row["id"]):
        try:
            await HOST.edit(m.get("channel_id") or row.get("channel_id"), m["message_id"],
                            buttons=buttons_for(row), disabled=True)
        except Exception as e:
            print("[reviewask] could not disable a prompt:", e)
        db.deactivate_message(m["message_id"])


async def _post(row, text, buttons=None, mentions=False):
    if not row.get("channel_id"):
        return None
    try:
        return await HOST.post(row["channel_id"], text=text, buttons=buttons, mentions=mentions)
    except Exception as e:
        print("[reviewask] post failed:", row.get("id"), e)
        return None


async def _prompt(row, kind, text):
    await _disable_prompts(row)
    mid = await _post(row, text, buttons_for(row) or None, mentions=True)
    if mid:
        db.add_message(mid, row["id"], row.get("channel_id"), kind)
    return mid


def _ping_text(row, c):
    text = texts.stage_ping(row)
    if row.get("state") in (engine.CALL_DUE, engine.CARE_DUE):
        script = call_script(row)
        if script.strip():
            text += NL + NL + "**نص المكالمة:**" + NL + script
    return text[:1990]


# ------------------------------------------------------------------ closing

async def close(row, state, by="النظام", note="", now_=None, extra=None):
    now_ = now_ or now()
    fields = {"state": state, "state_by": by, "state_at": _iso(now_), "closed_at": _iso(now_),
              "close_note": note[:300] if note else None}
    fields.update(extra or {})
    moved, row2 = db.transition(row["id"], engine.OPEN, fields, at=_iso(now_))
    if not moved:
        return False, row2
    db.log_event(row["id"], state, by, "", detail=note, at=_iso(now_))
    await _disable_prompts(row2)
    await refresh_card(row2)
    return True, row2


async def close_reviewed(row, review, now_=None):
    now_ = now_ or now()
    score = engine.review_score(review)
    stars_ = float(score) / 2 if score is not None else None
    ok, row2 = await close(row, engine.REVIEWED, "Airbnb", "", now_,
                           {"review_id": str(review.get("id") or ""), "review_stars": stars_})
    if ok:
        db.log_event(row["id"], "stars", "Airbnb", "", detail=str(stars_), at=_iso(now_))
        await _post(row2, texts.reviewed_post(stars_))
    return ok


# ------------------------------------------------------------------ one ticket's clock

async def process(row, now_, c):
    act = engine.next_action(row, now_, c)
    if act is None:
        return None
    tid = row["id"]
    a = act["act"]
    if a == "expire":
        ok, row2 = await close(row, act["state"], "النظام", "", now_)
        if ok:
            await _post(row2, texts.close_post(act["state"]))
        return a if ok else None
    fields = dict(act.get("fields") or {})
    if a in ("stage", "ping"):
        fields.update(await _cover(row, now_.date()))
        if fields.get("responsible_did") and fields["responsible_did"] != row.get("responsible_did"):
            await _grant(row, fields["responsible_did"])
    if a == "stage":
        moved, row2 = db.transition(tid, (row["state"],), fields, at=_iso(now_))
        if not moved:
            return None
        await refresh_card(row2)
        mid = await _prompt(row2, "stage", _ping_text(row2, c))
        db.log_event(tid, "stage", row2.get("responsible") or "", row2.get("responsible_did") or "",
                     detail="%s|%s" % (row2["state"], mid or ""), at=_iso(now_))
        return a
    moved, row2 = db.transition(tid, (row["state"],), fields, at=_iso(now_))
    if not moved:
        return None
    if a == "ping":
        await refresh_card(row2)
        mid = await _prompt(row2, "ping", _ping_text(row2, c))
        db.log_event(tid, "stage", row2.get("responsible") or "", row2.get("responsible_did") or "",
                     detail="%s|%s" % (row2["state"], mid or ""), at=_iso(now_))
    elif a == "remind":
        mid = await _prompt(row2, "remind", texts.remind(row2, int(row2.get("remind_count") or 0)))
        db.log_event(tid, "remind", row2.get("responsible") or "", "",
                     detail="%s|%s" % (row2.get("remind_count"), mid or ""), at=_iso(now_))
    elif a == "miss":
        db.log_event(tid, "staff_miss", row2.get("responsible") or "", row2.get("responsible_did") or "",
                     detail=row2["state"], at=_iso(now_))
        await _post(row2, texts.miss_line(row2))
    return a


# ------------------------------------------------------------------ presses (§7)

def can_press(tid, kind):
    row = db.ticket(tid) if tid is not None else None
    if not row:
        return False, texts.NOT_FOUND
    allowed = engine.ALLOWED_FROM.get(kind, ())
    if row.get("state") not in allowed:
        return False, texts.taken(row)
    return True, ""


async def answer(tid, kind, by, by_did="", note="", now_=None):
    """One button. -> {ok, message, links}. The presser is what gets recorded."""
    now_ = now_ or now()
    row = db.ticket(tid)
    if not row:
        return {"ok": False, "message": texts.NOT_FOUND}
    try:
        p = engine.press(row, kind, now_, cfg())
    except ValueError:
        return {"ok": False, "message": texts.NOT_FOUND}
    f = dict(p["fields"])
    f.update({"state_by": by, "state_by_did": str(by_did or ""), "state_at": _iso(now_)})
    if f["state"] in engine.TERMINAL:
        f["closed_at"] = _iso(now_)
        if note:
            f["close_note"] = note[:300]
    moved, row2 = db.transition(tid, p["allowed_from"], f, at=_iso(now_))
    if not moved:
        return {"ok": False, "message": texts.taken(row2 or row)}
    db.log_event(tid, p["kind"], by, by_did, detail=note, at=_iso(now_))
    out = {"ok": True, "message": texts.press_saved(p["kind"], row2), "links": []}
    if row2["state"] in engine.DUE_STATES:            # «راضي» → the WhatsApp step opens now
        await refresh_card(row2)
        mid = await _prompt(row2, "stage", _ping_text(row2, cfg()))
        db.log_event(tid, "stage", row2.get("responsible") or "", row2.get("responsible_did") or "",
                     detail="%s|%s" % (row2["state"], mid or ""), at=_iso(now_))
    else:
        await _disable_prompts(row2)
        await refresh_card(row2)
        if row2["state"] in (engine.WA_SENT, engine.CALL_RETRY):
            # keep the stage buttons reachable on a fresh prompt (e.g. «الضيف رد» later)
            mid = await _post(row2, texts.press_line(p["kind"], by), buttons_for(row2) or None)
            if mid and buttons_for(row2):
                db.add_message(mid, tid, row2.get("channel_id"), "after")
        else:
            await _post(row2, texts.press_line(p["kind"], by))
    if p["kind"] == "no_phone" and HOST.guest_links:
        try:
            links = await run_blocking(HOST.guest_links, row2["reservation_id"]) or []
            out["links"] = [(u, texts.BUTTON_LABELS["airbnb"]) for u, _l in links
                            if "wa.me" not in u and len(u) <= 512][:1]
        except Exception as e:
            print("[reviewask] airbnb link failed:", e)
    await _after(now_)
    return out


async def complaint_opened(tid, maint_channel_id, by, by_did="", now_=None):
    """After bot.py opened the maintenance room: the review room links it, the row → complaint."""
    res = await answer(tid, "complaint", by, by_did, note="maint:%s" % maint_channel_id, now_=now_)
    row = db.ticket(tid)
    if row and maint_channel_id:
        await _post(row, texts.complaint_room_reply(maint_channel_id))
    return res


async def _after(now_):
    if live():
        try:
            await publish_board(now_)
        except Exception as e:
            print("[reviewask] board after press failed:", e)


# ------------------------------------------------------------------ the tick

async def tick(now_=None, force=False):
    async with _lock("tick"):
        now_ = now_ or now()
        if not force and not live():
            return {"skipped": "off"}
        rep = {"opened": [], "actions": [], "reviewed": [], "cancelled": []}
        db.set_setting("last_tick_at", _iso(now_))
        c = cfg()
        today = now_.date()
        # 1) rooms open the EVENING BEFORE (20:00) for tomorrow's checkouts; today's are only a
        #    catch-up for a room missed while the bot was down. Never yesterday (2026-10-03).
        days = [today]
        if now_ >= engine.at_clock(today, config.open_at()):
            days.append(today + datetime.timedelta(days=1))
        for d in days:
            key = "open_check:%s" % d.isoformat()
            last = engine.parse_dt(db.setting(key))
            if last and (now_ - last).total_seconds() < _OPEN_EVERY:
                continue
            db.set_setting(key, _iso(now_))
            try:
                r = await open_rooms(d, "النظام", dry=False, now_=now_)
                rep["opened"] += [it["res_id"] for it in r.get("opened") or []]
            except Exception as e:
                print("[reviewask] catch-up open failed:", d, e)
        # 2) reviews that landed close their rooms
        try:
            got = await run_blocking(reviews_by_reservation)
        except Exception as e:
            print("[reviewask] review match failed:", e)
            got = {}
        for row in db.open_tickets():
            rv = got.get(str(row["reservation_id"]))
            if rv:
                try:
                    if await close_reviewed(row, rv, now_):
                        rep["reviewed"].append(row["id"])
                except Exception as e:
                    print("[reviewask] close reviewed failed:", row["id"], e)
        # 3) cancellations / moved departures
        try:
            rep["cancelled"] = await check_cancellations(now_)
        except Exception as e:
            print("[reviewask] cancellation check failed:", e)
        # 4) the clock
        for row in db.open_tickets():
            try:
                act = await process(row, now_, c)
            except Exception as e:
                print("[reviewask] ticket skipped:", row.get("id"), e)
                continue
            if act:
                rep["actions"].append((row["id"], act))
        # 5) board, monitor report, summary, sweep
        for fn in (publish_board, maybe_monitor_report, maybe_summary, maybe_sweep):
            try:
                await fn(now_)
            except Exception as e:
                print("[reviewask] %s failed:" % fn.__name__, e)
        return rep


async def check_cancellations(now_):
    last = engine.parse_dt(db.setting("cancel_check_at"))
    if last and (now_ - last).total_seconds() < _CANCEL_EVERY:
        return []
    rows = db.open_tickets()
    if not rows:
        return []
    db.set_setting("cancel_check_at", _iso(now_))
    start = (now_.date() - datetime.timedelta(days=config.window_days() + 1)).isoformat()
    end = (now_.date() + datetime.timedelta(days=2)).isoformat()
    window = await run_blocking(departures, start, end)
    if window is None:
        return []                                       # a failed read never cancels anything
    by_id = {str(r.get("res_id")): r for r in window}
    out, reread = [], 0
    for row in rows:
        r = by_id.get(str(row["reservation_id"]))
        if r is None and HOST.reservation and reread < _MISSING_REREAD:
            reread += 1
            try:
                r = await run_blocking(HOST.reservation, row["reservation_id"])
            except Exception as e:
                print("[reviewask] reservation re-read failed:", e)
                r = None
        if r is None:
            continue
        note = ""
        if str(r.get("status") or "").lower() not in ("new", "modified"):
            note = "الحجز انلغى في Hostaway"
        elif str(r.get("departure") or "")[:10] and str(r.get("departure"))[:10] != row["day"]:
            note = "تغيّر تاريخ الخروج إلى %s" % str(r.get("departure"))[:10]
        if note:
            ok, row2 = await close(row, engine.CANCELLED, "النظام", note, now_)
            if ok:
                await _post(row2, texts.close_post(engine.CANCELLED) + " — " + note)
                out.append(row["id"])
    return out


# ------------------------------------------------------------------ board (§11)

def _today_rows(now_):
    day = now_.date().isoformat()
    opened = db.open_tickets()
    closed = db.closed_between(_iso(engine.at_clock(day, "00:00")),
                               _iso(engine.at_clock(day, "00:00") + datetime.timedelta(days=1)))
    return opened, closed


def board_chunks(now_, prog=None, names=None):
    opened, closed = _today_rows(now_)
    day = now_.date()
    buckets = {k: [] for k, _t in texts.BOARD_SECTIONS}
    for r in opened:
        st = r.get("state")
        nd = engine.parse_dt(r.get("next_due_at"))
        if st == engine.WA_DUE:
            buckets["wa"].append(texts.board_line(r))
        elif st in (engine.CALL_DUE, engine.CARE_DUE) or (
                st in (engine.CALL_RETRY, engine.WA_SENT) and nd and nd.date() == day):
            buckets["call"].append(texts.board_line(r))
        elif st in (engine.PROMISED, engine.WA_SENT, engine.CALL_RETRY):
            buckets["wait"].append(texts.board_line(r))
    for r in closed:
        buckets["closed"].append(texts.board_line(r))
    since = _iso(engine.at_clock(day - datetime.timedelta(days=14), "00:00"))
    for r in db.q("SELECT * FROM rv_tickets WHERE state=? AND closed_at>=? AND review_stars<5 "
                  "ORDER BY closed_at DESC", (engine.REVIEWED, since)):
        buckets["low"].append(texts.board_line(r))
    prog = prog or {}
    names = names or {}
    weak = sorted((s for s in prog.values() if s.get("in_program")),
                  key=lambda s: (s.get("avg") is not None, s.get("avg") or 0))
    buckets["weak"] = [texts.weak_line(s, names.get(s["lid"]) or ("#%s" % s["lid"])) for s in weak]
    body = []
    waiting = sum(1 for r in opened if r.get("state") == engine.WAITING)
    if waiting:
        body.append("غرف تنتظر يوم الخروج: %d" % waiting)
    for key, title in texts.BOARD_SECTIONS:
        if not buckets[key]:
            continue
        body.append("")
        body.append("**%s** (%d)" % (title, len(buckets[key])))
        body.extend("• " + line for line in buckets[key])
    if not body:
        body = ["", texts.BOARD_EMPTY]
    chunks = split(body, 1850)
    return chunks[:3]


def _names():
    if not HOST.listings:
        return {}
    try:
        return {int(k): v for k, v in (HOST.listings() or {}).items()}
    except Exception:
        return {}


async def publish_board(now_):
    async with _lock("board"):
        prog = await run_blocking(program)
        names = await run_blocking(_names)
        chunks = board_chunks(now_, prog, names)
        h = hashlib.sha1(NL.join(chunks).encode("utf-8")).hexdigest()
        ids = db.setting("board_message_ids") or ""
        ids = [x for x in ids.split(",") if x]
        if db.setting("board_hash") == h and ids:
            return False
        ch = await HOST.require("board_channel")()
        if not ch:
            return False
        if db.setting("board_channel_id") != str(ch):
            ids = []
            db.set_setting("board_channel_id", str(ch))
        out_ids = []
        for i, chunk in enumerate(chunks):
            text = (texts.board_header(now_) + NL + chunk) if i == 0 else chunk
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
        db.set_setting("board_message_ids", ",".join(out_ids))
        db.set_setting("board_hash", h)
        return True


def split(lines, limit=1900):
    chunks, cur = [], ""
    for line in lines:
        piece = line + NL
        if len(piece) > limit:
            piece = piece[:limit - 2] + "…" + NL
        if len(cur) + len(piece) > limit:
            chunks.append(cur)
            cur = ""
        cur += piece
    if cur.strip():
        chunks.append(cur)
    return chunks


# ------------------------------------------------------------------ 30-min report → «غرفة-المراقبة»

def _slot(now_, every):
    mins = (now_.hour * 60 + now_.minute) // every * every
    return now_.replace(hour=mins // 60, minute=mins % 60, second=0, microsecond=0)


def overdue_lines(now_):
    lines = []
    what = {engine.WA_DUE: "واتساب ما انرسل", engine.CALL_DUE: "مكالمة ما صارت",
            engine.CARE_DUE: "مكالمة اطمئنان ما صارت"}
    for r in db.open_tickets():
        if r.get("state") not in engine.DUE_STATES:
            continue
        sd = engine.parse_dt(r.get("stage_due_at"))
        if not sd or sd > now_ or sd.date() != now_.date():
            continue
        lines.append(texts.monitor_line(r, int((now_ - sd).total_seconds() // 60), what[r["state"]]))
    return lines


async def maybe_monitor_report(now_):
    """One NEW message per half-hour slot, 17:00–22:00, naming the responsible person. Silent
    when nothing is overdue. The slot is claimed before posting (no double post on redeploy)."""
    if not HOST.monitor_channel:
        return False
    if (now_ < engine.at_clock(now_.date(), config.report_from())
            or now_ >= engine.at_clock(now_.date(), config.quiet_from())):
        return False
    slot = _slot(now_, config.report_every())
    if not db.claim("report_slot:%s" % _iso(slot)):
        return False
    lines = overdue_lines(now_)
    if not lines:
        return False
    ch = await HOST.monitor_channel()
    if not ch:
        return False
    for chunk in split([texts.monitor_header(now_)] + lines):
        await HOST.post(ch, text=chunk, mentions=False)
    return True


# ------------------------------------------------------------------ 22:00 summary

def day_stats(day):
    start = _iso(engine.at_clock(day, "00:00"))
    end = _iso(engine.at_clock(day, "00:00") + datetime.timedelta(days=1))
    evs = db.events_between(start, end)
    stages = {}
    for e in evs:
        if e["kind"] == "stage":
            stages.setdefault(e["ticket_id"], set()).add((e.get("detail") or "").split("|")[0])
    wa_t = {t for t, s in stages.items() if engine.WA_DUE in s}
    call_t = {t for t, s in stages.items() if s & {engine.CALL_DUE, engine.CARE_DUE}}
    wa_done = {e["ticket_id"] for e in evs if e["kind"] in WA_OUTCOMES} & wa_t
    call_done = {e["ticket_id"] for e in evs if e["kind"] in CALL_OUTCOMES} & call_t
    st = [float(e["detail"]) for e in evs if e["kind"] == "stars" and _num(e.get("detail"))]
    return {"reviews": sum(1 for e in evs if e["kind"] == engine.REVIEWED), "stars": st,
            "wa_due": len(wa_t), "wa_done": len(wa_done),
            "calls_due": len(call_t), "calls_done": len(call_done),
            "misses": sum(1 for e in evs if e["kind"] == "staff_miss"),
            "complaints": sum(1 for e in evs if e["kind"] == "complaint")}


def _num(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


async def maybe_summary(now_):
    day = now_.date()
    if now_ < engine.at_clock(day, config.summary_at()):
        return False
    if not db.claim("summary:%s" % day.isoformat()):
        return False
    s = await run_blocking(day_stats, day)
    if not (s["reviews"] or s["wa_due"] or s["calls_due"] or s["misses"] or s["complaints"]):
        return False
    ch = await HOST.require("board_channel")()
    if ch:
        await HOST.post(ch, text=texts.summary(day.isoformat(), s), mentions=False)
    return True


# ------------------------------------------------------------------ private report (§11)

def report_data(now_, days=7):
    """-> (people, apartments). One computation for /reviews-report and the dashboard."""
    end = now_.date()
    start = end - datetime.timedelta(days=max(1, int(days)) - 1)
    s_iso = _iso(engine.at_clock(start, "00:00"))
    e_iso = _iso(engine.at_clock(end, "00:00") + datetime.timedelta(days=1))
    evs = db.events_between(s_iso, e_iso)
    people = {}

    def p(name):
        name = name or "بدون اسم"
        return people.setdefault(name, {"name": name, "wa_due": 0, "wa_done": 0, "calls_due": 0,
                                        "calls_done": 0, "reviews": 0, "stars": [], "misses": 0})
    for e in evs:
        k, actor = e["kind"], e.get("actor") or ""
        state = (e.get("detail") or "").split("|")[0]
        if k == "stage" and state == engine.WA_DUE:
            p(actor)["wa_due"] += 1
        elif k == "stage" and state in (engine.CALL_DUE, engine.CARE_DUE):
            p(actor)["calls_due"] += 1
        elif k in WA_OUTCOMES:
            p(actor)["wa_done"] += 1
        elif k in CALL_OUTCOMES:
            p(actor)["calls_done"] += 1
        elif k == "staff_miss":
            p(actor)["misses"] += 1
    rows = db.closed_between(s_iso, e_iso)
    for r in rows:
        if r.get("state") == engine.REVIEWED:
            x = p(r.get("responsible"))
            x["reviews"] += 1
            if r.get("review_stars"):
                x["stars"].append(float(r["review_stars"]))
    out_people = []
    for x in sorted(people.values(), key=lambda v: v["name"]):
        x["avg_stars"] = (sum(x["stars"]) / len(x["stars"])) if x["stars"] else None
        out_people.append(x)
    prog = program()
    names = _names()
    apts = {}
    for r in db.tickets_between(start.isoformat(), end.isoformat()):
        lid = r.get("lid")
        if lid is None:
            continue
        a = apts.setdefault(lid, {"unit": engine.unit_short(r.get("unit") or names.get(lid)) or "#%s" % lid,
                                  "then": r.get("avg_at_open"), "now": None, "needed": 0})
        st = prog.get(lid) or {}
        a["now"], a["needed"] = st.get("avg"), st.get("needed") or 0
    for x in out_people:
        x.pop("stars", None)
    return out_people, sorted(apts.values(), key=lambda a: str(a["unit"]))


def report_text(now_, days=7):
    people, apts = report_data(now_, days)
    title = "تقرير رفع التقييم — آخر %d يوم" % days if days > 1 else "تقرير رفع التقييم — اليوم"
    return split(texts.report(people, apts, title).split(NL))


# ------------------------------------------------------------------ the 7-day room sweep (R7)

async def maybe_sweep(now_):
    last = engine.parse_dt(db.setting("sweep_at"))
    if last and (now_ - last).total_seconds() < _SWEEP_EVERY:
        return []
    db.set_setting("sweep_at", _iso(now_))
    return await sweep_closed(now_)


async def sweep_closed(now_=None, pause=1.0, limit=10, rows=None, ignore_age=False):
    """Deletes closed review rooms ≥ DELETE_AFTER_DAYS after closing — and nothing else.
    Order is the safety: fetch by the stored id → the topic must carry THIS reservation → the
    transcript is saved and read back → only then delete. 'Could not check' is never 'deleted'."""
    async with _lock("sweep"):
        now_ = now_ or now()
        cutoff = now_ - datetime.timedelta(days=config.delete_after_days())
        done = []
        rows = db.due_for_sweep(_iso(cutoff), limit) if rows is None else list(rows)[:limit]
        for i, row in enumerate(rows):
            if row.get("state") not in engine.TERMINAL or row.get("deleted_at"):
                continue
            closed = engine.parse_dt(row.get("closed_at"))
            if closed is None or (closed > cutoff and not ignore_age):
                continue
            tid, cid = row["id"], str(row.get("channel_id") or "")
            try:
                info = await HOST.require("room_info")(cid)
            except Exception as e:
                print("[reviewask] room check failed (kept):", tid, e)
                continue
            if info is None:
                continue                                  # could not check → keep, try later
            if not info.get("exists"):
                db.update_ticket(tid, {"deleted_at": _iso(now_), "delete_note": "كانت محذوفة"})
                db.log_event(tid, "room_missing", "النظام", "", at=_iso(now_))
                continue
            if engine.topic_reservation(info.get("topic")) != str(row["reservation_id"]):
                db.update_ticket(tid, {"delete_note": "refused: topic %s"
                                       % str(info.get("topic") or "")[:80]})
                db.log_event(tid, "delete_refused", "النظام", "",
                             detail=str(info.get("topic") or "")[:200], at=_iso(now_))
                continue
            try:
                msgs = await HOST.require("fetch_transcript")(cid, 500)
            except Exception as e:
                print("[reviewask] transcript failed (kept):", tid, e)
                continue
            if msgs is None:
                continue
            db.save_transcript(tid, list(msgs)[:500])
            if db.transcript(tid) is None:
                continue
            db.log_event(tid, "transcript_saved", "النظام", "", detail=str(len(msgs)), at=_iso(now_))
            try:
                ok = await HOST.require("delete_room")(cid)
            except Exception as e:
                print("[reviewask] delete failed (kept):", tid, e)
                ok = False
            if ok:
                db.update_ticket(tid, {"deleted_at": _iso(now_), "delete_note": "deleted"})
                db.log_event(tid, "room_deleted", "النظام", "", at=_iso(now_))
                done.append(tid)
            if pause and i < len(rows) - 1:
                await asyncio.sleep(pause)
        return done


# ------------------------------------------------------------------ the 2026-10-03 mistake (one-off)

# The default-ON push opened 60 rooms at 01:48 on 2026-10-03 from stale review data. The owner
# approved deleting exactly those (2026-10-03 ~02:05). Window = the bad run only.
MISTAKE_FROM = "2026-10-03T01:00:00+03:00"
MISTAKE_TO = "2026-10-03T02:30:00+03:00"
MISTAKE_NOTE = "انفتحت بالغلط (بيانات تقييم قديمة) — حذف بموافقة المالك 2026-10-03"


async def maybe_purge_mistake(now_=None, pause=1.0):
    """Void every ticket created in the bad run, then delete its room through sweep_closed (the
    same fence: stored id, matching topic, transcript first). Runs while switched OFF, a
    batch per tick, until none is left; then latched."""
    if db.setting("purge_2026_10_03_done") == "1":
        return []
    now_ = now_ or now()
    rows = db.q("SELECT * FROM rv_tickets WHERE created_at>=? AND created_at<=? ORDER BY id",
                (MISTAKE_FROM, MISTAKE_TO))
    for r in rows:
        if r.get("state") in engine.OPEN:
            await close(r, engine.VOID, "النظام", MISTAKE_NOTE, now_)
    todo = [r for r in db.q("SELECT * FROM rv_tickets WHERE created_at>=? AND created_at<=? "
                            "AND deleted_at IS NULL AND channel_id IS NOT NULL AND channel_id<>'' "
                            "AND (delete_note IS NULL OR delete_note NOT LIKE 'refused%%') ORDER BY id",
                            (MISTAKE_FROM, MISTAKE_TO))]
    done = await sweep_closed(now_, pause=pause, limit=20, rows=todo, ignore_age=True) if todo else []
    left = db.q1("SELECT COUNT(*) AS n FROM rv_tickets WHERE created_at>=? AND created_at<=? "
                 "AND deleted_at IS NULL AND channel_id IS NOT NULL AND channel_id<>'' "
                 "AND (delete_note IS NULL OR delete_note NOT LIKE 'refused%%')",
                 (MISTAKE_FROM, MISTAKE_TO))["n"]
    if not left:
        db.set_setting("purge_2026_10_03_done", "1", "النظام")
    return done


# ------------------------------------------------------------------ public health (counts only)

def health():
    """BLOCKING. The no-login health view: switch, review-type counts, how many reviews count,
    weak apartments, open tickets, last tick. NUMBERS ONLY — no guest, phone or apartment name."""
    revs = _reviews()
    audit = engine.type_audit(revs)
    prog = program(revs) if revs else {}
    return {"ok": True, "enabled": config.enabled(), "live": live(),
            "reviews_total": audit["total"], "types": audit["types"], "channels": audit["channels"],
            "unknown_types": audit["unknown_types"],
            "counted": len(engine.counted_reviews(revs)),
            "weak_apartments": sum(1 for s in prog.values() if s.get("in_program")),
            "apartments": len(prog), "open_tickets": len(db.open_tickets()),
            "last_tick_at": db.setting("last_tick_at") or "",
            "newest_live_review": str(engine.newest_live_review(revs, now().date()) or ""),
            "with_reservation": audit["with_reservation"],
            "fresh_days": config.fresh_days(),
            "review_pull": _pull_status(),
            "purge_done": db.setting("purge_2026_10_03_done") == "1",
            "deleted_rooms": db.q1("SELECT COUNT(*) AS n FROM rv_tickets WHERE deleted_at IS NOT NULL")["n"]}


def _pull_status():
    """bot.py's last Hostaway review pull: {at, n, error} — counts and an error class only."""
    if not HOST.reviews_status:
        return {}
    try:
        return dict(HOST.reviews_status() or {})
    except Exception:
        return {}


# ------------------------------------------------------------------ the editor preview (R4)

SAMPLE = {"guest": "سارة العتيبي", "responsible": "أصيل", "unit": "Ouja | Narjis 101",
          "phone_ar": "wa.me/966500000000", "phone_en": "wa.me/447700900000"}


def preview(tpl):
    """BLOCKING-safe. The editor's live preview: rendered text, unknown placeholders, and the
    length of the encoded wa.me URL (the /rv/ redirect means Discord's 512 cap never applies)."""
    row = {"guest": SAMPLE["guest"], "responsible": SAMPLE["responsible"], "unit": SAMPLE["unit"]}
    vals = values_for(row)
    out = {}
    for key, number in (("ar", SAMPLE["phone_ar"]), ("en", SAMPLE["phone_en"])):
        src = engine.pick_template(tpl, key)
        text, unknown = engine.render_template(src, vals)
        out[key] = {"text": text, "unknown": unknown, "url_len": len(wa_url(number, text))}
    text, unknown = engine.render_template(tpl.get("call_script") or "", vals)
    out["call_script"] = {"text": text, "unknown": unknown}
    return out
