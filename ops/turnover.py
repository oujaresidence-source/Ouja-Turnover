# -*- coding: utf-8 -*-
"""
ops.turnover — «القفل»: ONE private question per turnover, asked once, after the moment the
apartment should already have been finished.

    🧹 {UNIT} — عدّى وقت دخول الضيف (15:00)
    هل تم تنظيف الشقة؟
    [ ✅ نعم ]   [ ❌ لا ]

WHAT THIS REPLACED, AND WHY
    The first build was a five-level ladder: T-3h, T-1h, T-0 refreshing every ten minutes,
    T+20 to the lead, T+40 to the ops room. The owner's read was that anything sent BEFORE
    the deadline is nagging rather than help — the team closes turnovers in one to three
    hours as a matter of course, and the only moment worth a message is when that did not
    happen. Everything else was noise, and noise is how a bot gets muted.

WHEN THE QUESTION IS ASKED
    check-in today  ->  the moment check-in passes
    no check-in     ->  DAILY_CHECK_HOUR (16:00 Riyadh)
    The second case is not a nicety. Turnovers with no arriving guest were receiving NO
    reminder at all: the old shared-room loop is superseded, and a check-in-anchored trigger
    has nothing to anchor to on a gap night. Same question, different clock.

THE ANSWER IS THE FEATURE
    «نعم» needs photos — a yes with no evidence closes the loop on a lie.
    «لا» needs a REASON, and the reason is stored. The owner has no data today on why
    apartments go unclean; «الفريق ما وصل» logged twelve times is a staffing fact, and that
    is the thing this feature exists to produce.

WHAT THIS FILE CANNOT DO
    Produce a warning. It never reaches Phase 1's verdict function and never touches the
    warnings table — asleep at 3 AM is not misconduct, and neither is an honest «لا».
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
    return _env("CLEAN_CHECK_ENABLED", "1") == "1"


def dryrun():
    """DEFAULT ON. Flipped from the remote control on /compliance or CLEAN_CHECK_DRYRUN."""
    from . import switch
    return switch.is_dry("clean_check_dryrun")


def daily_check_hour():
    return _int("DAILY_CHECK_HOUR", engine.DAILY_CHECK_HOUR_DEFAULT)


def quiet_start():
    return _int("NUDGE_QUIET_START", engine.QUIET_START_DEFAULT)


def quiet_end():
    return _int("NUDGE_QUIET_END", engine.QUIET_END_DEFAULT)


def upload_link():
    try:
        base = (HOST.public_base() if HOST.public_base else "") or ""
    except Exception:
        base = ""
    return (base + "/oujact-route") if base else ""


# ------------------------------------------------------------------ Arabic wording

def _clock(dt_):
    return dt_.strftime("%H:%M") if dt_ else "—"


def question_text(unit, due_at, had_checkin, has_photos):
    nl = "\n"
    head = ("عدّى وقت دخول الضيف (%s)" % _clock(due_at)) if had_checkin \
        else ("عدّى وقت المراجعة اليومية (%s)" % _clock(due_at))
    lines = ["🧹 %s — %s" % (unit, head), "هل تم تنظيف الشقة؟"]
    if not has_photos:
        link = upload_link()
        lines.append("📷 الصور ما وصلت بعد" + ((" — " + link) if link else ""))
    return nl.join(lines)


def answered_text(unit, answer, reason_ar=""):
    """What the ONE message becomes after an answer — edited, never re-sent."""
    nl = "\n"
    if answer == "yes":
        return "🧹 %s — ✅ تم التنظيف. تسلم." % unit
    lines = ["🧹 %s — ❌ ما تم التنظيف" % unit]
    if reason_ar:
        lines.append("السبب: %s" % reason_ar)
    lines.append("بلّغنا المسؤول.")
    return nl.join(lines)


def lead_text(unit, responsible, reason_ar, reason_text=""):
    nl = "\n"
    lines = ["⚠️ شقة ما انظفت — %s" % unit,
             "المسؤول: %s" % (responsible or "غير محدد"),
             "السبب: %s" % (reason_ar or "—")]
    if reason_text:
        lines.append("ملاحظة: %s" % reason_text)
    return nl.join(lines)


def yes_refused_text():
    return ("📷 لسه ما وصلتنا صور لهذي الشقة. ارفع الصور أول وبعدها اضغط «نعم» — "
            "الزر يشتغل لحاله أول ما توصل الصور.")


def asleep_text(unit, who, backup_name):
    nl = "\n"
    return nl.join(["😴 %s ما رد على سؤالين بالليل — يبدو نايم، وهذا شي طبيعي." % (who or "؟"),
                    "حوّلنا %s إلى %s." % (unit, backup_name or "المناوب"),
                    "ما انسجل عليه أي إنذار."])


def backup_text(unit, from_name):
    nl = "\n"
    return nl.join(["🌙 محوّلة لك: %s" % unit,
                    "كانت على %s وما رد (الوقت متأخر)." % (from_name or "زميلك"),
                    "إذا ما تقدر، بلّغ المسؤول على طول."])


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
    if dryrun():
        db.dry_log("clean_check", employee=payload.get("employee"),
                   period_key=payload.get("work_item_id"),
                   detail=(payload.get("text") or payload.get("lead_text") or "")[:400],
                   payload=payload)
        return "dryrun"
    try:
        if HOST.notify:
            HOST.notify(payload)
            return "queued"
    except Exception as e:
        print("[ops.turnover] notify failed:", e)
    return "failed"


def _lead_id():
    from . import notify as _n
    return _n.lead_id()


def _person_channel(name):
    from . import notify as _n
    return _n.channel_name(name) if name else ""


# ------------------------------------------------------------------ THE TICK

def tick(now=None):
    """One pass. Asks at most ONE question per turnover, ever — UNIQUE(work_item_id) makes
    that a fact about the database rather than a promise about this loop."""
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
           "asked": [], "waiting": [], "closed": [], "asleep": []}

    for it in items:
        wid = it.get("work_item_id")
        if not wid:
            continue
        try:
            ci = _parse(it.get("checkin_at"))
            day = it.get("date") or now.date().isoformat()
            due = engine.check_due_at(ci, day, daily_check_hour(), now.tzinfo)
            row = db.clean_check(wid)

            if it.get("done"):
                out["closed"].append(wid)
                continue
            if row and row.get("answered_at"):
                continue                       # answered — there is nothing left to ask
            if row and row.get("reassigned_to"):
                continue                       # handed over; the backup owns it now

            # ---- sleep protection, before anything is sent
            if row and engine.in_quiet_window(now, quiet_start(), quiet_end()):
                since = (now - datetime.timedelta(hours=6)).isoformat(timespec="seconds")
                strikes = db.unanswered_checks_since(row.get("responsible"), since)
                if engine.sleep_reassign(strikes, True):
                    _reassign_asleep(row, it, dry)
                    out["asleep"].append({"item": wid, "employee": row.get("responsible")})
                    continue

            if not engine.should_ask(ci, day, now, daily_check_hour(), already_asked=bool(row)):
                out["waiting"].append(wid)
                continue

            db.open_clean_check({
                "work_item_id": wid, "unit": it.get("unit"),
                "responsible": it.get("employee"), "responsible_did": it.get("employee_did"),
                "asked_at": now.isoformat(timespec="seconds"),
                "day_key": day, "month_key": engine.month_key(day)})
            _send({"kind": "clean_check", "op": "send", "work_item_id": wid,
                   "employee": it.get("employee"), "employee_did": it.get("employee_did"),
                   "unit": it.get("unit"),
                   "text": question_text(it.get("unit"), due, ci is not None,
                                         bool(it.get("photos"))),
                   "can_ack": engine.can_ack(it.get("photos")),
                   "upload_url": upload_link(),
                   "channel": _person_channel(it.get("employee"))})
            out["asked"].append({"item": wid, "employee": it.get("employee")})
        except Exception as e:
            print("[ops.turnover] item skipped:", wid, e)
    return out


def _reassign_asleep(row, it, dry):
    """Hand the unit to the on-call backup. THIS MUST NOT GENERATE A WARNING."""
    backup = (it or {}).get("backup") or {}
    name = backup.get("name") or ""
    db.reassign_clean_check(row["work_item_id"], name, "reassigned_asleep")
    if dry:
        db.dry_log("clean_asleep", row.get("responsible"), row["work_item_id"],
                   "كان بيتحوّل %s إلى %s (نايم) — بدون أي إنذار"
                   % (row.get("unit"), name or "المناوب"))
        return
    _send({"kind": "clean_asleep", "work_item_id": row["work_item_id"],
           "employee": backup.get("name"), "employee_did": backup.get("did"),
           "text": backup_text(row.get("unit"), row.get("responsible")),
           "lead_id": _lead_id(),
           "lead_text": asleep_text(row.get("unit"), row.get("responsible"), name),
           "channel": _person_channel(backup.get("name"))})


# ------------------------------------------------------------------ the two answers

def _find(ref):
    return db.clean_check(ref) or db.clean_check_by_message(ref)


def answer_yes(ref, by, has_photos=None):
    """«✅ نعم» — refused without photos. A yes with no evidence is worse than silence: it
    tells everyone the apartment is ready when nobody can show that it is."""
    row = _find(ref)
    if not row:
        return {"ok": False, "error": "ما لقينا هذي المهمة"}
    if row.get("answered_at"):
        return {"ok": False, "error": "انسجل الرد من قبل"}
    if has_photos is None:
        try:
            has_photos = bool(HOST.has_photos(row["work_item_id"])) if HOST.has_photos else False
        except Exception:
            has_photos = False
    if not engine.can_ack(has_photos):
        return {"ok": False, "error": yes_refused_text(), "need_photos": True,
                "work_item_id": row["work_item_id"]}
    db.answer_clean_check(row["work_item_id"], "yes")
    return {"ok": True, "answer": "yes", "work_item_id": row["work_item_id"],
            "unit": row.get("unit"),
            "edit": answered_text(row.get("unit"), "yes"),
            "message": "✅ تمام، سجّلناها. تسلم."}


def answer_no(ref, by, reason_code, reason_text=""):
    """«❌ لا» — a reason is REQUIRED. The reason is the whole point: a bare «no» would leave
    the owner exactly as blind as before."""
    row = _find(ref)
    if not row:
        return {"ok": False, "error": "ما لقينا هذي المهمة"}
    if row.get("answered_at"):
        return {"ok": False, "error": "انسجل الرد من قبل"}
    if not engine.valid_reason(reason_code, reason_text):
        return {"ok": False, "error": "لازم تختار سبب — وإذا «سبب ثاني» اكتبه",
                "need_reason": True, "work_item_id": row["work_item_id"]}
    db.answer_clean_check(row["work_item_id"], "no", reason_code, reason_text)
    reason_ar = engine.REASON_AR.get(reason_code, reason_code)
    _send({"kind": "clean_problem", "work_item_id": row["work_item_id"],
           "employee": row.get("responsible"), "unit": row.get("unit"),
           "lead_id": _lead_id(),
           "lead_text": lead_text(row.get("unit"), row.get("responsible"), reason_ar,
                                  reason_text)})
    return {"ok": True, "answer": "no", "work_item_id": row["work_item_id"],
            "unit": row.get("unit"),
            "edit": answered_text(row.get("unit"), "no", reason_ar),
            "message": "تم ✅ بلّغنا المسؤول بالسبب."}


# ------------------------------------------------------------------ owner screen

def state(date_iso=None):
    now = db.now_dt()
    day = date_iso or now.date().isoformat()
    month = engine.month_key(day)
    rows = []
    for r in db.clean_checks_for_day(day):
        rows.append({
            "work_item_id": r["work_item_id"], "unit": r.get("unit"),
            "employee": r.get("responsible"),
            "asked_at": (r.get("asked_at") or "")[11:16],
            "answer": r.get("answer"),
            "reason": engine.REASON_AR.get(r.get("reason_code") or "", ""),
            "reason_text": r.get("reason_text") or "",
            "reassigned_to": r.get("reassigned_to"),
            "asleep": r.get("reassigned_reason") == "reassigned_asleep",
        })
    reasons = [{"code": x["reason_code"],
                "label": engine.REASON_AR.get(x["reason_code"], x["reason_code"]),
                "n": x["n"]}
               for x in db.clean_reason_counts(month)]
    return {"date": day, "month": month, "dryrun": dryrun(), "enabled": enabled(),
            "daily_hour": daily_check_hour(), "rows": rows,
            "reasons": reasons, "totals": db.clean_check_totals(month)}
