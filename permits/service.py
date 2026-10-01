# -*- coding: utf-8 -*-
"""
permits.service — orchestration: the database + a DiscordPort (permits/port.py).

THE TICK (bot.py's permits_loop, every PERMITS_TICK_MIN minutes)
    1. reconcile   stale claims → retried; stale `opening` tickets → adopted by topic or
                   retried; open tickets whose channel is gone → `lost` (a replacement opens
                   in step 2). "Couldn't check" is never "deleted".
    2. plan        engine.plan over the DB: which permits need a ticket now.
    3. enqueue     ticket rows + outbox rows, in ONE transaction each; reminders; the digest.
    4. drain       every Discord side effect, claimed atomically, retried with backoff.

Each step is wrapped on its own: one failure never blocks the others.

DRY vs LIVE (permits_settings.mode, default DRY). In dry mode nothing reaches Discord and
no ticket row is created; would-open rows are written with state='dry' so the dashboard
can say exactly what going live would do. PERMITS_FORCE_DRY=1 overrides everything.

Closing a ticket has exactly three doors — renew(), cancel(), update() (a date
correction that moves the permit out of its window). There is no fourth.
"""

import datetime
import json
import sqlite3

from . import dates, db, engine
from .host import HOST

try:                                    # reuse the ops switch's typed word (ops/switch.py)
    from ops.switch import CONFIRM_WORD
except Exception:                       # pragma: no cover - ops package absent
    CONFIRM_WORD = "تشغيل"

RIYADH = datetime.timezone(datetime.timedelta(hours=3))
STALE_MIN = 15
_BACKOFF = (1, 5, 15, 60)


# ---------------- time helpers ----------------

def _utc(now):
    """Aware datetime → naive-UTC ISO seconds (what the DB stores and compares)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=RIYADH)
    return now.astimezone(datetime.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _riyadh_day(now):
    if now.tzinfo is None:
        now = now.replace(tzinfo=RIYADH)
    return now.astimezone(RIYADH).date().isoformat()


def _now():
    try:
        return HOST.now()
    except Exception:
        return datetime.datetime.now(RIYADH)


def backoff_minutes(attempts):
    return _BACKOFF[min(max(int(attempts), 1), len(_BACKOFF)) - 1]


async def _direct(fn, *a, **kw):
    return fn(*a, **kw)


# ---------------- mode ----------------

def effective_mode(c=None):
    c = c or engine.cfg()
    if c["force_dry"]:
        return "dry"
    return "live" if db.get_setting("mode", "dry") == "live" else "dry"


def mode_info(c=None):
    c = c or engine.cfg()
    return {"mode": effective_mode(c), "stored": db.get_setting("mode", "dry"),
            "forced": bool(c["force_dry"]),
            "changed_by": db.get_setting("mode_changed_by", ""),
            "changed_at": db.get_setting("mode_changed_at", ""),
            "confirm_word": CONFIRM_WORD}


def set_mode(mode, confirm, actor):
    mode = str(mode or "").strip()
    if mode not in ("dry", "live"):
        return {"ok": False, "error_ar": "وضع غير معروف", "error_en": "unknown mode"}
    if mode == "live" and str(confirm or "").strip() != CONFIRM_WORD:
        return {"ok": False, "need_confirm": True,
                "error_ar": "اكتب كلمة «%s» عشان تشغّل التنبيهات فعلياً" % CONFIRM_WORD,
                "error_en": "Type «%s» to go live" % CONFIRM_WORD}
    with db.transaction() as cx:
        db.set_setting("mode", mode, cx=cx)
        db.set_setting("mode_changed_by", actor or "", cx=cx)
        db.set_setting("mode_changed_at", db.now_iso(), cx=cx)
        if mode == "live":
            db.set_setting("golive_sweep", "1", cx=cx)
        db.log_event("mode_changed", payload={"mode": mode}, actor=actor, cx=cx)
    return {"ok": True, "mode": mode, "forced": engine.cfg()["force_dry"]}


def consume_golive_sweep():
    db.set_setting("golive_sweep", "0")


# ---------------- reading helpers ----------------

def listing_map():
    try:
        rows = HOST.listings() if HOST.listings else []
    except Exception as e:
        print("[permits] listings unavailable:", e)
        rows = []
    if isinstance(rows, dict):
        return {int(k): (dict(v, id=int(k)) if isinstance(v, dict) else {"id": int(k), "internal_name": str(v)})
                for k, v in rows.items()}
    return {int(r["id"]): r for r in rows if r.get("id") is not None}


def unit_name(permit, lmap=None):
    lmap = listing_map() if lmap is None else lmap
    rec = lmap.get(permit.get("listing_id")) if permit.get("listing_id") else None
    if rec:
        return rec.get("internal_name") or rec.get("public_name") or ""
    return ""


def responsible(permit):
    """(name, discord_id): the permit's own field → the unit's maintenance owner → default."""
    name = str(permit.get("responsible_name") or "").strip()
    did = str(permit.get("responsible_discord_id") or "").strip()
    if did or name:
        return name, did
    try:
        if HOST.maint_assignee_for:
            n, d = HOST.maint_assignee_for(permit.get("listing_id") or 0)
            return str(n or ""), str(d or "")
    except Exception as e:
        print("[permits] maint_assignee_for failed:", e)
    return "", ""


def mention(name, did):
    if did:
        return "<@%s>" % did + ((" (%s)" % name) if name else "")
    if name:
        return "**%s**" % name
    return "⚠️ ما فيه مسؤول معيّن — حدّده من الداشبورد"


def _dash_url():
    try:
        return HOST.dashboard_url() if HOST.dashboard_url else ""
    except Exception:
        return ""


def described(now, c=None, status="active"):
    c = c or engine.cfg()
    today = _riyadh_day(now)
    return [engine.describe(p, today, c) for p in db.permits(status)]


def summary(now, c=None):
    c = c or engine.cfg()
    rows = described(now, c)
    return {"ok": True, "counts": engine.counts(rows), "mode": mode_info(c),
            "last_tick_at": db.get_setting("last_tick_at", ""), "lead_days": c["lead_days"],
            "headsup_days": c["headsup_days"]}


# ---------------- plan ----------------

def plan(now, c=None):
    c = c or engine.cfg()
    live = {t["permit_id"] for t in db.live_tickets()}
    sweep = db.get_setting("golive_sweep", "0") == "1"
    return engine.plan(db.permits("active"), live, now, c, golive_sweep=sweep)


def would_open(now, c=None):
    """What going live would open (window ignored): the dry-mode banner list."""
    c = c or engine.cfg()
    today = _riyadh_day(now)
    live = {t["permit_id"] for t in db.live_tickets()}
    lmap = listing_map()
    out = []
    for p in db.permits("active"):
        if p["id"] in live or not engine.should_open(p, today, c):
            continue
        d = engine.describe(p, today, c)
        out.append({"id": p["id"], "unit": engine.unit_label(p, unit_name(p, lmap)),
                    "permit_type": p["permit_type"], "permit_no": p.get("permit_no") or "",
                    "days_left": d["days_left"], "band": d["band"], "end_date": p.get("end_date")})
    out.sort(key=lambda r: (r["days_left"], r["unit"]))
    return out


# ---------------- enqueue ----------------

def open_ticket_row(pid, now):
    """THE duplicate-proof open: ticket row + outbox row in one transaction. The partial
    unique index refuses a second live ticket — then this returns None and does nothing."""
    today = _riyadh_day(now)
    with db.transaction() as cx:
        prev = cx.execute("SELECT id, state FROM permits_tickets WHERE permit_id=? ORDER BY id DESC LIMIT 1",
                          (int(pid),)).fetchone()
        try:
            # last_reminder_date = today: the card itself is today's nudge (never two pings in a day)
            cur = cx.execute("INSERT INTO permits_tickets(permit_id, state, opened_at, last_reminder_date) "
                             "VALUES(?, 'opening', ?, ?)", (int(pid), _utc(now), today))
        except sqlite3.IntegrityError:
            return None
        tid = cur.lastrowid
        replaced = prev["id"] if prev is not None and prev["state"] == "lost" else None
        db.enqueue("open_ticket", "open:t%d" % tid,
                   {"ticket_id": tid, "permit_id": int(pid), "replaced_tid": replaced}, cx=cx)
        db.log_event("ticket_queued", int(pid), tid, {"replaced_tid": replaced}, cx=cx)
    return tid


def enqueue_due(now, c=None):
    c = c or engine.cfg()
    p = plan(now, c)
    opened = [t for t in (open_ticket_row(pid, now) for pid in p["open"]) if t]
    if db.get_setting("golive_sweep", "0") == "1":
        consume_golive_sweep()
    return opened


def enqueue_reminders(now, c=None):
    c = c or engine.cfg()
    today = _riyadh_day(now)
    n = 0
    for t in db.live_tickets():
        if not engine.reminder_due(t, now, c):
            continue
        with db.transaction() as cx:
            db.enqueue("reminder", "reminder:t%d:%s" % (t["id"], today), {"ticket_id": t["id"]}, cx=cx)
            db.update_ticket(t["id"], cx=cx, last_reminder_date=today)
        n += 1
    return n


def enqueue_digest(now, c=None):
    c = c or engine.cfg()
    if engine.summary_due(now, db.get_setting("digest_date"), c["daily_hour"]):
        return db.enqueue("digest", "digest:%s" % _riyadh_day(now), {"date": _riyadh_day(now)})
    return None


def record_dry(now, c=None):
    """Dry mode: remember (once per permit + end date) what WOULD open; send nothing."""
    c = c or engine.cfg()
    for w in would_open(now, c):
        p = db.permit(w["id"])
        db.enqueue("open_ticket", "dry-open:p%d:%s" % (w["id"], p.get("end_date")),
                   {"permit_id": w["id"], "permit_no": w["permit_no"], "unit": w["unit"]}, state="dry")
    if engine.summary_due(now, db.get_setting("dry_digest_date"), c["daily_hour"]):
        db.enqueue("digest", "dry-digest:%s" % _riyadh_day(now), {"date": _riyadh_day(now)}, state="dry")
        db.set_setting("dry_digest_date", _riyadh_day(now))


def daily_link(now):
    """Re-try the unit auto-linker for still-unlinked rows, once per Riyadh day."""
    day = _riyadh_day(now)
    if db.get_setting("link_date") == day:
        return None
    from .seed import seed as _seed
    res = _seed.link_units(lambda: list(listing_map().values()))
    db.set_setting("link_date", day)
    return res


# ---------------- reconcile ----------------

def _stale(iso, now, minutes=STALE_MIN):
    if not iso:
        return True
    try:
        t = datetime.datetime.fromisoformat(str(iso))
    except ValueError:
        return True
    cur = datetime.datetime.fromisoformat(_utc(now))
    return (cur - t) >= datetime.timedelta(minutes=minutes)


def _reset_stale_claims(now):
    n = 0
    for o in db.outbox_rows("claimed"):
        if _stale(o.get("claimed_at"), now):
            db.execute("UPDATE permits_outbox SET state='pending', next_at=NULL WHERE id=? AND state='claimed'",
                       (o["id"],))
            n += 1
    return n


def _mark_lost(t):
    with db.transaction() as cx:
        db.update_ticket(t["id"], cx=cx, state="lost", closed_at=db.now_iso())
        db.log_event("ticket_lost", t["permit_id"], t["id"], {"channel_id": t.get("channel_id")}, cx=cx)


async def reconcile(port, now, run=_direct, c=None):
    await run(_reset_stale_claims, now)
    # stale `opening`: adopt a channel a crashed run already made, else let the outbox retry
    for t in await run(db.live_tickets):
        if t["state"] != "opening" or t.get("channel_id") or not _stale(t.get("opened_at"), now):
            continue
        cid = await port.find_channel_by_tid(t["id"])
        if cid:
            await _adopt(port, t["id"], cid, now, c or engine.cfg(), run, "reconcile")
        else:
            await run(db.execute, "UPDATE permits_outbox SET state='pending', next_at=NULL "
                                  "WHERE ref=? AND state='claimed'", ("open:t%d" % t["id"],))
    # lost channels — and "couldn't check" is NEVER "deleted"
    for t in await run(db.live_tickets):
        if t["state"] != "open" or not t.get("channel_id"):
            continue
        try:
            exists = await port.channel_exists(t["channel_id"])
        except Exception as e:
            print("[permits] channel check failed — no change this tick:", e)
            return
        if exists is False:
            await run(_mark_lost, t)


# ---------------- drain ----------------

def _due_outbox(now):
    cur = _utc(now)
    return db.q("SELECT * FROM permits_outbox WHERE (state='pending' OR (state='failed' AND "
                "(next_at IS NULL OR next_at<=?))) ORDER BY id", (cur,))


def _mark_done(oid, now):
    db.execute("UPDATE permits_outbox SET state='done', done_at=?, last_error='' WHERE id=?", (_utc(now), oid))


def _mark_failed(row, err, now):
    attempts = int(row.get("attempts") or 0) + 1
    nxt = datetime.datetime.fromisoformat(_utc(now)) + datetime.timedelta(minutes=backoff_minutes(attempts))
    msg = ("%s: %s" % (type(err).__name__, err))[:500]
    db.execute("UPDATE permits_outbox SET state='failed', attempts=?, last_error=?, next_at=? WHERE id=?",
               (attempts, msg, nxt.isoformat(timespec="seconds"), row["id"]))
    if row["kind"] == "open_ticket":
        payload = json.loads(row["payload_json"] or "{}")
        if payload.get("ticket_id"):
            db.update_ticket(payload["ticket_id"], attempts=attempts, last_error=msg)
    print("[permits] outbox %s failed (attempt %d): %s" % (row["ref"], attempts, msg))


def _open_payload(tid, now, c):
    """Everything create_ticket_channel needs, or None when the ticket no longer wants a channel."""
    t = db.ticket(tid)
    if not t or t["state"] != "opening":
        return None
    p = db.permit(t["permit_id"])
    if not p:
        return None
    payload = json.loads((db.outbox("open:t%d" % tid) or {}).get("payload_json") or "{}")
    uname = unit_name(p)
    rname, rid = responsible(p)
    card = engine.ticket_card(p, tid, _riyadh_day(now), c, unit_name=uname, responsible=mention(rname, rid),
                              dashboard_url=_dash_url(), replaced_tid=payload.get("replaced_tid"))
    return {"name": engine.channel_name(tid, uname or p.get("unit_text") or p.get("building") or p["permit_type"]),
            "topic": engine.topic(p["id"], tid, p.get("end_date")), "card": card, "responsible_id": rid}


def _mark_open(tid, res, how="created", now=None):
    with db.transaction() as cx:
        db.update_ticket(tid, cx=cx, state="open", channel_id=str(res["channel_id"]),
                         card_msg_id=str(res.get("card_msg_id") or ""), last_error="")
        if how != "created":                      # adopted outside the drain's own claim
            cx.execute("UPDATE permits_outbox SET state='done', done_at=? WHERE ref=?",
                       (_utc(now or _now()), "open:t%d" % tid))
        t = cx.execute("SELECT permit_id FROM permits_tickets WHERE id=?", (tid,)).fetchone()
        db.log_event("ticket_opened" if how == "created" else "ticket_adopted", t["permit_id"], tid,
                     {"channel_id": str(res["channel_id"]), "how": how}, cx=cx)


async def _adopt(port, tid, cid, now, c, run, how):
    """A channel for this ticket already exists (a crashed run made it): take it over and
    make sure its card is there. Never a second channel for the same tid."""
    spec = await run(_open_payload, tid, now, c)
    if spec is None:
        return
    mid = await port.ensure_card(cid, spec["card"])
    await run(_mark_open, tid, {"channel_id": cid, "card_msg_id": mid}, how, now)


def _reminder_payload(tid, now, c):
    t = db.ticket(tid)
    if not t or t["state"] != "open" or not t.get("channel_id"):
        return None
    p = db.permit(t["permit_id"])
    if not p:
        return None
    d = engine.describe(p, _riyadh_day(now), c)
    rname, rid = responsible(p)
    users, roles = engine.reminder_mentions(d["band"], rid, c)
    pings = " ".join(["<@%s>" % u for u in users] + ["<@&%s>" % r for r in roles])
    text = engine.reminder_text(p, t, _riyadh_day(now), c, unit_name(p), pings)
    return {"channel_id": t["channel_id"], "text": text, "users": users, "roles": roles}


def build_digest(now, c=None):
    c = c or engine.cfg()
    today = _riyadh_day(now)
    lmap = listing_map()
    live = {t["permit_id"]: t for t in db.live_tickets()}
    rows = []
    for p in db.permits("active"):
        r = engine.describe(p, today, c)
        r["unit_name"] = unit_name(p, lmap)
        r["ticket"] = live.get(p["id"])
        r["resp_name"], r["resp_id"] = responsible(p)
        rows.append(r)
    problems = []
    for o in db.outbox_rows("failed"):
        if o["kind"] == "open_ticket":
            problems.append({"tid": json.loads(o["payload_json"]).get("ticket_id"), "error": o["last_error"]})
    yday = (datetime.date.fromisoformat(today) - datetime.timedelta(days=1)).isoformat()
    renewed = []
    for e in db.q("SELECT * FROM permits_events WHERE kind='renewed' ORDER BY id DESC LIMIT 200"):
        pl = json.loads(e.get("payload_json") or "{}")
        if pl.get("day") != yday:
            continue
        p = db.permit(e["permit_id"]) or {}
        renewed.append({"permit_type": p.get("permit_type"), "unit_name": engine.unit_label(p, unit_name(p, lmap)),
                        "by": e.get("actor")})
    return engine.digest_messages(rows, today, c, problems=problems, renewed=renewed, mode=effective_mode(c))


def _set_digest_latch(date):
    db.set_setting("digest_date", date)


async def _execute(row, port, now, c, run):
    payload = json.loads(row["payload_json"] or "{}")
    kind = row["kind"]
    if kind == "open_ticket":
        tid = payload["ticket_id"]
        spec = await run(_open_payload, tid, now, c)
        if spec is None:
            return
        cid = await port.find_channel_by_tid(tid)          # a crashed run may already have made it
        if cid:
            await _adopt(port, tid, cid, now, c, run, "drain")
            return
        res = await port.create_ticket_channel(spec["name"], spec["topic"], spec["card"], spec["responsible_id"])
        await run(_mark_open, tid, res)
    elif kind == "reminder":
        spec = await run(_reminder_payload, payload["ticket_id"], now, c)
        if spec is None:
            return
        await port.post(spec["channel_id"], spec["text"], spec["users"], spec["roles"])
    elif kind == "close_ticket":
        t = await run(db.ticket, payload["ticket_id"])
        if not t or not t.get("channel_id"):
            return                                          # closed before a channel ever existed
        await port.close_channel(t["channel_id"], t.get("card_msg_id"), payload.get("note") or "")
    elif kind == "post_note":
        await port.post(payload["channel_id"], payload.get("text") or "")
    elif kind == "digest":
        chunks, mentions = await run(build_digest, now, c)
        await port.post_digest(chunks, mentions)
        await run(_set_digest_latch, payload.get("date") or _riyadh_day(now))   # ONLY after success
    else:
        print("[permits] unknown outbox kind:", kind)


async def drain_outbox(port, now, c=None, run=_direct):
    c = c or engine.cfg()
    done = failed = 0
    for row in await run(_due_outbox, now):
        if not await run(db.claim_outbox, row["id"], _utc(now)):
            continue                                        # another copy owns it
        try:
            await _execute(row, port, now, c, run)
            await run(_mark_done, row["id"], now)
            done += 1
        except Exception as e:
            await run(_mark_failed, row, e, now)
            failed += 1
    return {"done": done, "failed": failed}


# ---------------- the tick ----------------

async def tick(port, now=None, c=None, run=None):
    """One pass. `run` executes DB work (bot.py passes asyncio.to_thread — a loop, not a
    request handler); tests pass nothing and everything runs inline."""
    run = run or _direct
    now = now or _now()
    c = c or engine.cfg()
    out = {"mode": None}
    try:
        await run(db.set_setting, "last_tick_at", _utc(now))
    except Exception as e:
        print("[permits] heartbeat write failed:", e)
    try:
        await run(daily_link, now)
    except Exception as e:
        print("[permits] daily unit link failed:", e)
    mode = await run(effective_mode, c)
    out["mode"] = mode
    if mode == "dry":
        try:
            await run(record_dry, now, c)
        except Exception as e:
            print("[permits] dry pass failed:", e)
        return out
    if not port.ready():
        out["skipped"] = "discord_not_ready"
        return out
    for name, step in (("reconcile", lambda: reconcile(port, now, run, c)),):
        try:
            await step()
        except Exception as e:
            print("[permits] %s failed:" % name, e)
    for name, fn in (("enqueue_due", enqueue_due), ("enqueue_reminders", enqueue_reminders),
                     ("enqueue_digest", enqueue_digest)):
        try:
            out[name] = await run(fn, now, c)
        except Exception as e:
            print("[permits] %s failed:" % name, e)
    try:
        out["drain"] = await drain_outbox(port, now, c, run)
    except Exception as e:
        print("[permits] drain failed:", e)
    return out


# ---------------- the three closing doors (+ claim) ----------------

def _err(ar, en):
    return {"ok": False, "error_ar": ar, "error_en": en}


def _close_live_ticket(cx, pid, kind, note, actor):
    t = cx.execute("SELECT * FROM permits_tickets WHERE permit_id=? AND state IN ('opening','open')",
                   (int(pid),)).fetchone()
    if t is None:
        return None
    db.update_ticket(t["id"], cx=cx, state="closed", closed_at=db.now_iso(), closed_by=actor or "",
                     close_kind=kind)
    db.enqueue("close_ticket", "close:t%d" % t["id"], {"ticket_id": t["id"], "note": note}, cx=cx)
    db.log_event("ticket_closed", int(pid), t["id"], {"kind": kind}, actor, cx=cx)
    return t["id"]


_COPY_ON_RENEW = ("permit_type", "title", "scope", "listing_id", "unit_text", "building", "issuer",
                  "holder", "district", "street", "building_no", "unit_no", "ownership_kind",
                  "holder_id_last4", "listing_link_kind", "serial", "lead_days", "cost_sar",
                  "responsible_name", "responsible_discord_id", "renew_notes", "extra_json")


def renew(pid, new_end, actor, today, new_no="", notes="", proof=False, override_reason="",
          via="dashboard", doc_path="", is_admin=False, start_date=None):
    """The renewal transaction (§5). `proof`: Discord already saw a file in the room.
    Dashboard: a document upload, or an ADMIN override with a written reason."""
    p = db.permit(pid)
    if not p or p["status"] != "active":
        return _err("التصريح مو فعّال (مجدَّد أو ملغي من قبل)", "permit is not active")
    parsed = dates.parse_date(new_end)
    iso = parsed["iso"]
    if not iso:
        return _err("ما قدرنا نقرأ تاريخ الانتهاء الجديد — اكتبه مثل 2027-10-11 أو 11/10/2027 أو 01/05/1449",
                    "could not read the new end date")
    if p.get("end_date") and iso <= p["end_date"]:
        return _err("تاريخ الانتهاء الجديد لازم يكون بعد القديم (%s)" % p["end_date"],
                    "the new end date must be after the old one")
    if iso < str(today)[:10]:
        return _err("تاريخ الانتهاء الجديد في الماضي — تأكد منه", "the new end date is in the past")
    if via == "discord":
        if not proof:
            return _err("ارفع صورة أو PDF للتصريح المجدَّد في التذكرة أول، بعدين اضغط «تم التجديد»",
                        "upload the renewed permit in the ticket first")
    else:
        if not doc_path and not (is_admin and str(override_reason or "").strip()):
            return _err("ارفع مستند التصريح المجدَّد (أو تجاوز بصلاحية مدير مع كتابة السبب)",
                        "upload the renewed document (or an admin override with a reason)")
    raw = dates.clean_text(new_end) if not hasattr(new_end, "isoformat") else iso
    s_parsed = dates.parse_date(start_date) if start_date else {"iso": None}
    with db.transaction() as cx:
        new = {k: p.get(k) for k in _COPY_ON_RENEW}
        new.update({"permit_no": str(new_no or "").strip() or p.get("permit_no") or "",
                    "end_date": iso, "end_date_raw": raw, "start_date": s_parsed["iso"],
                    "start_date_raw": dates.clean_text(start_date) if start_date else "",
                    "notes": notes if str(notes or "").strip() else (p.get("notes") or ""),
                    "doc_path": doc_path or "", "status": "active", "needs_data": 0,
                    "date_issue": parsed["issue"], "replaces_id": p["id"], "source": "renewal",
                    "source_ref": "renewal of #%d" % p["id"],
                    "review_issues": json.dumps(engine.open_issues(p), ensure_ascii=False)})
        new_id = db.insert_permit(new, actor, cx=cx)
        db.update_permit(p["id"], {"status": "renewed", "replaced_by_id": new_id}, actor, cx=cx)
        tid = _close_live_ticket(cx, p["id"], "renewed", engine.renewed_note(iso, today), actor)
        day = str(today)[:10]
        db.log_event("renewed", p["id"], tid, {"new_id": new_id, "new_end": iso, "via": via, "day": day,
                                               "override_reason": override_reason or ""}, actor, cx=cx)
        db.log_event("renewal_created", new_id, None, {"replaces_id": p["id"], "day": day}, actor, cx=cx)
    return {"ok": True, "new_id": new_id, "ticket_closed": tid, "end_date": iso,
            "words": dates.words_ar(iso), "days_left": engine.days_left(iso, today)}


def cancel(pid, reason, actor, allowed):
    if not allowed:
        return _err("«لن يُجدَّد» لأصحاب صلاحية إقفال الصيانة أو مدير النظام بس", "not allowed")
    reason = str(reason or "").strip()
    if not 5 <= len(reason) <= 400:
        return _err("اكتب السبب (من ٥ إلى ٤٠٠ حرف)", "reason must be 5–400 characters")
    p = db.permit(pid)
    if not p or p["status"] != "active":
        return _err("التصريح مو فعّال", "permit is not active")
    with db.transaction() as cx:
        db.update_permit(p["id"], {"status": "cancelled", "cancel_reason": reason}, actor, cx=cx)
        tid = _close_live_ticket(cx, p["id"], "cancelled", engine.cancelled_note(reason, actor), actor)
        db.log_event("cancelled", p["id"], tid, {"reason": reason}, actor, cx=cx)
    return {"ok": True, "ticket_closed": tid}


EDITABLE = ("permit_type", "permit_no", "title", "scope", "unit_text", "building", "issuer", "holder",
            "start_date", "end_date", "district", "street", "building_no", "unit_no", "ownership_kind",
            "doc_url", "lead_days", "cost_sar", "responsible_name", "responsible_discord_id",
            "renew_notes", "notes")


def update(pid, patch, actor, today, reason=""):
    """Edit fields. Changing end_date needs a reason; a correction that moves a permit out
    of its window closes the live ticket as 'corrected' (the third closing door)."""
    p = db.permit(pid)
    if not p:
        return _err("التصريح غير موجود", "not found")
    c = engine.cfg()
    fields = {}
    for k, v in (patch or {}).items():
        if k not in EDITABLE:
            continue
        fields[k] = v.strip() if isinstance(v, str) else v
    for k in ("start_date", "end_date"):
        if k in fields:
            raw = fields[k]
            pd = dates.parse_date(raw) if str(raw or "").strip() else {"iso": None, "issue": ""}
            if str(raw or "").strip() and not pd["iso"]:
                return _err("ما قدرنا نقرأ التاريخ «%s»" % raw, "could not read the date")
            fields[k] = pd["iso"]
            fields[k + "_raw"] = dates.clean_text(raw)
            if k == "end_date":
                fields["date_issue"] = pd["issue"]
                fields["needs_data"] = 0 if pd["iso"] else 1
    if "lead_days" in fields:
        v = str(fields["lead_days"] if fields["lead_days"] is not None else "").strip()
        if v and not v.isdigit():
            return _err("أيام التنبيه لازم رقم", "lead days must be a number")
        fields["lead_days"] = int(v) if v else None
    if "cost_sar" in fields:
        v = str(fields["cost_sar"] if fields["cost_sar"] is not None else "").replace(",", "").strip()
        try:
            fields["cost_sar"] = float(v) if v else None
        except ValueError:
            return _err("التكلفة لازم رقم", "cost must be a number")
    if "permit_type" in fields and not fields["permit_type"]:
        return _err("نوع التصريح مطلوب", "type is required")
    end_changed = "end_date" in fields and fields["end_date"] != p.get("end_date")
    reason = str(reason or "").strip()
    if end_changed and len(reason) < 3:
        return _err("تغيير تاريخ الانتهاء يحتاج سبب", "changing the end date needs a reason")
    if end_changed and p["status"] != "active":
        return _err("ما يتعدّل تاريخ تصريح منتهي الدورة (مجدَّد/ملغي)", "history rows cannot change dates")
    allowed_db = set(db.PERMIT_FIELDS)
    fields = {k: v for k, v in fields.items() if k in allowed_db}
    with db.transaction() as cx:
        db.update_permit(p["id"], fields, actor, cx=cx)
        closed = None
        if end_changed:
            newp = dict(p, **fields)
            db.log_event("corrected", p["id"], None, {"old_end": p.get("end_date"), "new_end": fields.get("end_date"),
                                                      "reason": reason}, actor, cx=cx)
            if not engine.should_open(newp, today, c):
                closed = _close_live_ticket(cx, p["id"], "corrected",
                                            engine.corrected_note(fields.get("end_date"), today, reason, actor), actor)
        else:
            db.log_event("edited", p["id"], None, {"fields": sorted(fields)}, actor, cx=cx)
    return {"ok": True, "ticket_closed": closed}


def claim(tid, name, did, actor):
    t = db.ticket(tid)
    if not t or t["state"] not in ("opening", "open"):
        return _err("التذكرة مقفلة", "ticket is closed")
    with db.transaction() as cx:
        db.update_ticket(tid, cx=cx, claimed_by=name or "", claimed_by_id=str(did or ""), claimed_at=db.now_iso())
        db.log_event("claimed", t["permit_id"], tid, {"by": name}, actor, cx=cx)
    return {"ok": True}


def link(pid, listing_id, actor):
    p = db.permit(pid)
    if not p:
        return _err("التصريح غير موجود", "not found")
    lid = int(listing_id) if str(listing_id or "").strip().isdigit() else None
    db.update_permit(pid, {"listing_id": lid, "listing_link_kind": "manual"}, actor)
    db.log_event("linked", pid, None, {"listing_id": lid, "how": "manual"}, actor)
    return {"ok": True, "listing_id": lid}


def review_clear(pid, code, note, actor):
    note = str(note or "").strip()
    if len(note) < 3:
        return _err("اكتب ملاحظة المراجعة", "a note is required")
    p = db.permit(pid)
    if not p:
        return _err("التصريح غير موجود", "not found")
    items = json.loads(p.get("review_issues") or "[]")
    hit = False
    for it in items:
        if it.get("code") == code and not it.get("cleared_at"):
            it.update({"cleared_by": actor, "cleared_at": db.now_iso(), "note": note})
            hit = True
    if not hit:
        return _err("ما فيه ملاحظة مفتوحة بهذا الرمز", "no open issue with that code")
    db.update_permit(pid, {"review_issues": items}, actor)
    db.log_event("review_cleared", pid, None, {"code": code, "note": note}, actor)
    return {"ok": True}


# ---------------- what the Discord buttons read ----------------

def ticket_for_channel(channel_id, topic=""):
    """The permit ticket living in this room — by channel id, else by the topic tag
    (so the buttons keep working even if the row lost its channel id)."""
    t = db.q1("SELECT * FROM permits_tickets WHERE channel_id=? ORDER BY id DESC LIMIT 1", (str(channel_id),))
    if t:
        return t
    parsed = engine.parse_topic(topic)
    return db.ticket(parsed[1]) if parsed else None


def ticket_details(tid, now=None):
    """(card dict, [event lines]) for the ephemeral «📋 التفاصيل» answer."""
    now = now or _now()
    t = db.ticket(tid)
    p = db.permit(t["permit_id"]) if t else None
    if not p:
        return None, []
    rname, rid = responsible(p)
    card = engine.ticket_card(p, tid, _riyadh_day(now), engine.cfg(), unit_name=unit_name(p),
                              responsible=mention(rname, rid), dashboard_url=_dash_url())
    lines = []
    for e in db.events_for([x["id"] for x in db.chain(p["id"])], 10):
        pl = json.loads(e.get("payload_json") or "{}")
        extra = pl.get("reason") or pl.get("new_end") or pl.get("by") or ""
        lines.append("• %s — %s%s" % (str(e.get("at") or "")[:16].replace("T", " "), e.get("kind"),
                                      (" · " + str(extra)) if extra else ""))
    return card, lines
