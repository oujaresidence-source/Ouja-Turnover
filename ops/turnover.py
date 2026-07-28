# -*- coding: utf-8 -*-
"""
ops.turnover — PHASE 2 «القفل»: private, escalating turnover nudges.

WHAT THIS REPLACES
    reminder_loop used to @mention a person in the SHARED turnover room every 15-30 minutes,
    so the whole team watched one person get nagged. And it had already been switched off for
    every in-house (OujaCT) unit, which meant most apartments got NO reminder at all — a
    cleaner could forget a unit and nobody found out until the guest was at the door.
    This module fixes both: private first, and covering every apartment.

THE TWO RULES THAT SHAPE EVERYTHING HERE
  1. ANCHORED TO CHECK-IN, never the wall clock. A guest arriving at 20:00 must not be
     nudged on a 15:00 schedule.
  2. ONE MESSAGE, EDITED IN PLACE. Escalation is by CONTENT — colour, countdown, buttons.
     Only L3 and L5 are allowed to be a NEW message (a phone buzz). 40 pings is how people
     learn to mute the bot, and a muted bot kills the whole accountability suite silently.

AND THE ONE THAT PROTECTS PEOPLE
    Between 00:00 and 06:00, two unanswered nudges mean the person is ASLEEP. The unit goes
    to the on-call backup and NOBODY IS WARNED. Nothing in this file can create a warning —
    it never reaches Phase 1's verdict function and never touches the warnings table. The
    guard is a test (tests/test_ops_turnover.py), not a promise in a comment.
"""

import datetime
import os

from . import db, engine
from .host import HOST


# ------------------------------------------------------------------ env

def _env(name, default=""):
    return (os.environ.get(name, default) or default).strip()


def _int(name, default):
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


def enabled():
    return _env("NUDGE_ENABLED", "1") == "1"


def dryrun():
    """DEFAULT ON, like every other phase. Computes and logs everything, sends nothing."""
    return _env("NUDGE_DRYRUN", "1") == "1"


def quiet_start():
    return _int("NUDGE_QUIET_START", engine.QUIET_START_DEFAULT)


def quiet_end():
    return _int("NUDGE_QUIET_END", engine.QUIET_END_DEFAULT)


def ops_channel():
    """Where L5 goes — the only level anyone but the person and the lead ever sees."""
    return _env("NUDGE_OPS_CHANNEL", "غرفة-المراقبة")


def upload_link(work_item_id):
    try:
        base = (HOST.public_base() if HOST.public_base else "") or ""
    except Exception:
        base = ""
    return (base + "/oujact-route") if base else ""


# ------------------------------------------------------------------ Arabic wording

def _clock(dt_):
    return dt_.strftime("%H:%M")


def _left(mins):
    """A countdown a tired person can read at a glance."""
    if mins >= 120:
        return "باقي %d ساعات" % (mins // 60)
    if mins >= 60:
        return "باقي ساعة و%d دقيقة" % (mins - 60) if mins > 60 else "باقي ساعة"
    if mins > 0:
        return "باقي %d دقيقة" % mins
    if mins == 0:
        return "الضيف وصل وقته"
    return "تأخرنا %d دقيقة" % abs(mins)


HEAD = {"L1": "🧹", "L2": "⏳", "L3": "🔴", "L4": "🔴", "L5": "🚨"}


def message_text(item, level, now):
    """The ONE message, re-rendered for the level it is at. Same message id, new content —
    that is the whole escalation mechanism."""
    ci = _parse(item.get("checkin_at"))
    mins = engine.minutes_to(ci, now) if ci else 0
    unit = item.get("unit") or item.get("work_item_id")
    nl = "\n"
    lines = ["%s %s" % (HEAD.get(level, "🧹"), unit)]

    if level == "L1":
        lines += ["الضيف داخل الساعة %s — %s." % (_clock(ci), _left(mins)),
                  "خلّص الشقة وارفع الصور، وبعدها اضغط «جاهزة»."]
    elif level == "L2":
        lines += ["الضيف داخل الساعة %s — %s." % (_clock(ci), _left(mins)),
                  "إذا خلصت اضغط «جاهزة». وإذا فيه شي واقف، اضغط «فيه مشكلة» وبنلحق عليك."]
    elif level == "L3":
        lines += ["⚠️ وقت دخول الضيف: %s — %s." % (_clock(ci), _left(mins)),
                  "محتاجين نعرف وضع الشقة الحين."]
    elif level == "L4":
        lines += ["⚠️ %s والشقة ما انقفلت بعد." % _left(mins),
                  "بلّغنا المسؤول عشان يلحق."]
    else:
        lines += ["🚨 الضيف على الباب و%s." % _left(mins).replace("تأخرنا", "تأخرنا"),
                  "محتاجين أحد يلحق على هذي الشقة الحين."]

    if not item.get("photos"):
        link = upload_link(item.get("work_item_id"))
        lines.append("📷 الصور ما وصلت بعد" + ((" — " + link) if link else ""))
    return nl.join(lines)


def lead_text(item, level, now):
    ci = _parse(item.get("checkin_at"))
    mins = engine.minutes_to(ci, now) if ci else 0
    nl = "\n"
    return nl.join(["🔴 %s — %s" % (item.get("unit"), _left(mins)),
                    "المسؤول: %s" % (item.get("employee") or "غير محدد"),
                    "الضيف داخل الساعة %s وما وصلنا رد." % _clock(ci) if ci else "",
                    "كلّمه قبل ما يوصل الضيف."])


def ops_text(item, now):
    """L5 — the only public line, and only because a guest is standing at the door."""
    ci = _parse(item.get("checkin_at"))
    mins = engine.minutes_to(ci, now) if ci else 0
    nl = "\n"
    return nl.join(["🚨 شقة ما انقفلت والضيف واصل — %s" % item.get("unit"),
                    "دخول الضيف: %s · %s" % (_clock(ci) if ci else "؟", _left(mins)),
                    "المسؤول: %s" % (item.get("employee") or "غير محدد"),
                    "محتاجين أحد يلحق عليها الحين."])


def asleep_text(item, backup_name):
    nl = "\n"
    return nl.join(["😴 %s ما رد على تذكيرين بالليل — يبدو نايم، وهذا شي طبيعي." % (item.get("employee") or "؟"),
                    "حوّلنا %s إلى %s." % (item.get("unit"), backup_name or "المناوب"),
                    "ما انسجل عليه أي إنذار."])


def backup_text(item, from_name):
    ci = _parse(item.get("checkin_at"))
    nl = "\n"
    return nl.join(["🌙 محوّلة لك: %s" % item.get("unit"),
                    "كانت على %s وما رد (الوقت متأخر)." % (from_name or "زميلك"),
                    ("دخول الضيف: %s" % _clock(ci)) if ci else "",
                    "إذا ما تقدر، بلّغ المسؤول على طول."])


def ack_reply(ok, has_photos):
    if ok:
        return "✅ تمام، سجّلناها جاهزة. تسلم."
    if not has_photos:
        return ("📷 لسه ما وصلتنا صور لهذي الشقة. ارفع الصور أول وبعدها اضغط «جاهزة» — "
                "الزر يشتغل لحاله أول ما توصل الصور.")
    return "ما قدرنا نسجلها الحين — جرّب مرة ثانية."


# ------------------------------------------------------------------ helpers

def _parse(v):
    if not v:
        return None
    if isinstance(v, datetime.datetime):
        return v
    try:
        d = datetime.datetime.fromisoformat(str(v))
        return d if d.tzinfo else d.replace(tzinfo=engine.tz())
    except Exception:
        return None


def _send(payload):
    """Hand one message to bot.py. In dry-run nothing leaves the process."""
    if dryrun():
        db.dry_log("nudge", employee=payload.get("employee"),
                   period_key=payload.get("work_item_id"),
                   detail=(payload.get("text") or payload.get("lead_text")
                           or payload.get("ops_text") or "")[:400],
                   payload=payload)
        return "dryrun"
    try:
        if HOST.notify:
            HOST.notify(payload)
            return "queued"
    except Exception as e:
        print("[ops.turnover] notify failed:", e)
    return "failed"


# ------------------------------------------------------------------ THE TICK

def tick(now=None):
    """One pass over today's turnovers. Safe every minute, safe to run twice.

    HOST.turnover_items() gives the live picture from bot.py: every open turnover, its unit,
    its guest check-in time, who is responsible, and whether cleaning photos exist yet."""
    if not enabled():
        return {"skipped": "disabled"}
    now = now or db.now_dt()
    dry = dryrun()
    try:
        items = HOST.turnover_items() or []
    except Exception as e:
        print("[ops.turnover] items unavailable:", e)
        return {"skipped": "no items", "error": str(e)}

    out = {"now": now.isoformat(timespec="minutes"), "dryrun": dry,
           "nudged": [], "edited": [], "closed": [], "asleep": [], "skipped": []}

    for it in items:
        wid = it.get("work_item_id")
        ci = _parse(it.get("checkin_at"))
        if not wid:
            continue
        if not ci:
            # No guest arriving = nothing is urgent. The whole ladder is anchored to a real
            # check-in, so without one we deliberately say nothing at all.
            out["skipped"].append({"item": wid, "why": "no check-in today"})
            continue

        row = db.ensure_nudge_item(wid, it.get("unit"), it.get("date"), it.get("employee"),
                                   it.get("employee_did"), ci)
        state = dict(row or {})
        state["photos"] = bool(it.get("photos"))
        state["work_item_id"] = wid
        state["unit"] = it.get("unit")

        if it.get("done") or state.get("acked_at"):
            if not state.get("closed_at"):
                db.close_nudge(wid)
                out["closed"].append(wid)
            continue
        if state.get("problem_at"):
            continue                       # a human is already on it; the bot stops nudging
        if state.get("reassigned_to"):
            # handed over (asleep, or by a lead). The person who was asleep is DONE being
            # nudged — waking someone repeatedly after we already moved their unit is exactly
            # the behaviour this phase exists to remove.
            continue

        # ---- sleep protection, before anything else is sent
        quiet = engine.in_quiet_window(now, quiet_start(), quiet_end())
        if quiet and not state.get("reassigned_to"):
            since = (now - datetime.timedelta(hours=6)).isoformat(timespec="seconds")
            strikes = db.unacked_nudges_in_window(wid, since)
            if engine.sleep_reassign(strikes, quiet):
                _reassign_asleep(state, it, now, dry)
                out["asleep"].append({"item": wid, "employee": state.get("employee")})
                continue

        sent = db.nudge_levels_sent(wid)
        step = engine.nudge_due_step(ci, now, sent)

        if step is None:
            # still at L3? keep the countdown honest with a silent EDIT, no new notification
            if "L3" in sent and "L4" not in sent and state.get("message_id"):
                if engine.l3_refresh_due(_parse(state.get("last_edit_at")), now):
                    _emit(state, "L3", now, dry, edit_only=True)
                    out["edited"].append(wid)
            continue

        _emit(state, step["level"], now, dry)
        out["nudged"].append({"item": wid, "level": step["level"],
                              "employee": state.get("employee")})
    return out


def _emit(item, level, now, dry, edit_only=False):
    """Send or edit the ONE message for this turnover at this level."""
    wid = item["work_item_id"]
    has_msg = bool(item.get("message_id"))
    # A new message (phone buzz) only at L3/L5, or when we have nothing to edit yet.
    as_new = (not has_msg) or (engine.nudge_is_push(level) and not edit_only)

    if level == "L5":
        _send({"kind": "nudge_ops", "work_item_id": wid, "employee": item.get("employee"),
               "ops_channel": ops_channel(), "ops_text": ops_text(item, now)})
        db.record_nudge(wid, item.get("employee"), item.get("employee_did"), level,
                        "dryrun" if dry else "ops", at=now)
        return

    if level == "L4":
        _send({"kind": "nudge_lead", "work_item_id": wid, "employee": item.get("employee"),
               "lead_id": _lead_id(), "lead_text": lead_text(item, level, now)})
        db.record_nudge(wid, item.get("employee"), item.get("employee_did"), level,
                        "dryrun" if dry else "lead", at=now)
        # and refresh the person's own message so it reflects the new severity
        _send({"kind": "nudge", "op": "edit", "work_item_id": wid,
               "employee": item.get("employee"), "employee_did": item.get("employee_did"),
               "message_id": item.get("message_id"), "channel_id": item.get("channel_id"),
               "text": message_text(item, level, now), "buttons": True,
               "can_ack": engine.can_ack(item.get("photos")),
               "channel": _person_channel(item.get("employee"))})
        db.touch_nudge_edit(wid, now)
        return

    _send({"kind": "nudge", "op": "send" if as_new else "edit", "work_item_id": wid,
           "employee": item.get("employee"), "employee_did": item.get("employee_did"),
           "message_id": item.get("message_id"), "channel_id": item.get("channel_id"),
           "text": message_text(item, level, now),
           "buttons": level != "L1", "can_ack": engine.can_ack(item.get("photos")),
           "upload_url": upload_link(wid),
           "channel": _person_channel(item.get("employee"))})
    if not edit_only:
        db.record_nudge(wid, item.get("employee"), item.get("employee_did"), level,
                        "dryrun" if dry else "queued", at=now)
    db.touch_nudge_edit(wid, now)


def _reassign_asleep(item, raw, now, dry):
    """Hand the unit to the on-call backup. THIS MUST NOT GENERATE A WARNING."""
    backup = raw.get("backup") or {}
    name = backup.get("name") or ""
    db.reassign_nudge(item["work_item_id"], name, "reassigned_asleep")
    if dry:
        db.dry_log("nudge_asleep", item.get("employee"), item["work_item_id"],
                   "كان بيتحوّل %s إلى %s (نايم) — بدون أي إنذار"
                   % (item.get("unit"), name or "المناوب"))
        return
    _send({"kind": "nudge_asleep", "work_item_id": item["work_item_id"],
           "employee": backup.get("name"), "employee_did": backup.get("did"),
           "text": backup_text(item, item.get("employee")),
           "lead_id": _lead_id(), "lead_text": asleep_text(item, name),
           "channel": _person_channel(backup.get("name"))})


def _lead_id():
    from . import notify as _n
    return _n.lead_id()


def _person_channel(name):
    from . import notify as _n
    return _n.channel_name(name) if name else ""


# ------------------------------------------------------------------ the two buttons

def press_ready(work_item_id_or_message, by, has_photos=None):
    """«✅ جاهزة». Refused without photos — an ack from a half-asleep person with no photos
    closes the loop on a lie, which is worse than silence."""
    item = (db.nudge_item(work_item_id_or_message)
            or db.nudge_item_by_message(work_item_id_or_message))
    if not item:
        return {"ok": False, "error": "ما لقينا هذي المهمة"}
    if has_photos is None:
        try:
            has_photos = bool(HOST.has_photos(item["work_item_id"])) if HOST.has_photos else False
        except Exception:
            has_photos = False
    if not engine.can_ack(has_photos):
        return {"ok": False, "error": ack_reply(False, False), "need_photos": True,
                "work_item_id": item["work_item_id"]}
    db.ack_nudge(item["work_item_id"], by)
    db.close_nudge(item["work_item_id"])
    return {"ok": True, "message": ack_reply(True, True), "work_item_id": item["work_item_id"]}


def press_problem(work_item_id_or_message, by, note=""):
    """«⚠️ فيه مشكلة» — stops the nudging and pulls the lead in. Never a black mark."""
    item = (db.nudge_item(work_item_id_or_message)
            or db.nudge_item_by_message(work_item_id_or_message))
    if not item:
        return {"ok": False, "error": "ما لقينا هذي المهمة"}
    db.flag_nudge_problem(item["work_item_id"], by)
    _send({"kind": "nudge_problem", "work_item_id": item["work_item_id"],
           "employee": item.get("employee"), "lead_id": _lead_id(),
           "lead_text": "⚠️ %s بلّغ عن مشكلة في %s%s"
                        % (by or item.get("employee") or "؟", item.get("unit"),
                           (" — " + note) if note else "")})
    return {"ok": True, "message": "بلّغنا المسؤول ✅ وقفنا التذكيرات لين يتواصل معك.",
            "work_item_id": item["work_item_id"]}


# ------------------------------------------------------------------ owner screen

def state(date_iso=None):
    now = db.now_dt()
    day = date_iso or now.date().isoformat()
    rows = []
    for r in db.nudge_items_for_date(day):
        ci = _parse(r.get("checkin_at"))
        rows.append({
            "work_item_id": r["work_item_id"], "unit": r.get("unit"),
            "employee": r.get("employee"), "checkin_at": _clock(ci) if ci else "—",
            "levels": db.nudge_levels_sent(r["work_item_id"]),
            "acked_at": r.get("acked_at"), "problem_at": r.get("problem_at"),
            "reassigned_to": r.get("reassigned_to"),
            "asleep": r.get("reassigned_reason") == "reassigned_asleep",
            "closed": bool(r.get("closed_at")),
        })
    since = (now - datetime.timedelta(days=30)).isoformat(timespec="seconds")
    return {"date": day, "dryrun": dryrun(), "enabled": enabled(), "rows": rows,
            "staffing_signal": db.sleep_reassignments(since)}
