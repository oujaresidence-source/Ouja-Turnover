# -*- coding: utf-8 -*-
"""
oncall.notify — the minute tick and every Discord-facing decision of «المناوبة».

tick(now) runs once a minute from bot.py (off the event loop). Each step is idempotent by a
database fact, so a double tick or a restart mid-tick can never ping twice:
    publish  12:00  tomorrow's night            (oncall_nights PK)
    lock     15:00  tonight                     (status flip published -> locked)
    remind   slot - 15 min                      (oncall_slots.reminded_at)
    checks   slot start, then every 15 min      (UNIQUE(slot_id, due_at))
    judge    10 min after each check            (status flip pending -> …)
    issues   claim overdue / stale              (claim_alerted_at / stale_alerted_night)
    handover at each slot end                   (oncall_slots.handover_at)
    summary  after midnight                     (oncall_nights.summary_at)

THE PRINCIPLE (shared with ops/): the system accuses, humans only forgive. The ONLY call to
ops.db.issue_warning in this package is in _warn(), reached only from the judge step.
"""

import datetime
import os

from . import db, engine, roster, texts
from .host import HOST

OC_KIND = "oc"                     # ops_obligations.kind for an on-call night


def channel_name():
    return os.environ.get("ONCALL_CHANNEL", "المناوبة")


def enabled():
    """Stored switch. Default ON (owner ruling: live from day one; he never edits Railway)."""
    return (db.config_get("enabled", "1") or "1") == "1"


def set_enabled(on, by, at):
    db.config_set("enabled", "1" if on else "0", by, db.iso(at))
    db.log("switch", at, by, {"on": bool(on)})


def _now():
    return HOST.require("now")()


def _send(payload):
    try:
        if HOST.send:
            HOST.send(payload)
            return True
    except Exception as e:
        print("[oncall] send failed:", e)
    return False


def _pct(mult):
    from ops import notify as _onotify
    return _onotify.ar_num(round(float(mult) * 100)) + "٪"


def _date(s):
    return datetime.date.fromisoformat(s)


# ------------------------------------------------------------------ THE TICK

def heartbeat(now):
    """A gap longer than DOWNTIME_GAP_SEC since the last tick is recorded as bot downtime;
    checks whose window it spans are voided (the employee never pays for a restart)."""
    last = db.parse(db.config_get("last_tick", ""))
    if last is not None and (now - last).total_seconds() > engine.DOWNTIME_GAP_SEC:
        db.log("downtime", now, "", {"from": db.iso(last), "to": db.iso(now)})
    db.config_set("last_tick", db.iso(now))


def tick(now=None):
    now = now or _now()
    if not enabled():
        db.config_set("last_tick", db.iso(now))
        return {"skipped": "off"}
    heartbeat(now)
    rep = {}
    for name, step in (("published", publish_due), ("locked", lock_due),
                       ("reminded", remind_due), ("checks", checks_due),
                       ("judged", judge_due), ("issues", issues_due),
                       ("handover", handover_due), ("summary", summary_due)):
        try:
            rep[name] = step(now)
        except Exception as e:                    # one broken step must not stop the others
            print("[oncall] %s step failed: %s" % (name, e))
            rep[name] = "error: %s" % e
    return rep


# ------------------------------------------------------------------ publish / lock

def _schedule_payload(date_iso, edit=False):
    n = db.night(date_iso)
    d = _date(date_iso)
    slots = db.slots_for(date_iso)
    roster_rows = []
    try:
        import json
        roster_rows = json.loads((n or {}).get("roster_json") or "[]")
    except Exception:
        pass
    unavailable = [r for r in roster_rows if not r.get("ok")]
    locked = (n or {}).get("status") != "published"
    return {"kind": "schedule_edit" if edit else "schedule",
            "channel_text": texts.schedule_text(d, slots, unavailable, locked),
            "view": "schedule",
            "slots": [{"id": s["id"], "label": texts.slot_label(s) + " · " + s["employee"],
                       "locked": locked} for s in slots],
            "edit_message_id": ((n or {}).get("message_id") or "") if edit else "",
            "report": {"what": "schedule", "id": date_iso} if not edit else None}


def publish_due(now):
    if now.hour < engine.PUBLISH_HOUR:
        return None
    d = now.date() + datetime.timedelta(days=1)
    di = d.isoformat()
    if db.night(di):
        return None
    av = roster.availability(d)
    names = [a["name"] for a in av if a["ok"]]
    dids = {a["name"]: a["did"] for a in av}
    slots = engine.build_night(d, names, db.history(di, 7))
    for s in slots:
        s["employee_did"] = dids.get(s["employee"], "")
    if not db.publish_night(di, slots, av, now):
        return None
    db.log("publish", now, "", {"date": di, "slots": len(slots)})
    _send(_schedule_payload(di))
    unavailable = [a for a in av if not a["ok"]]
    if unavailable or not slots:
        sup = roster.supervisor()
        _send({"kind": "supervisor", "dm": [{"did": sup["did"],
                                             "text": texts.supervisor_roster_alert(d, unavailable, not slots)}]})
    return di


def lock_due(now):
    if now.hour < engine.LOCK_HOUR:
        return None
    di = now.date().isoformat()
    n = db.night(di)
    if not n or n["status"] != "published" or not db.lock_night(di, now):
        return None
    for sw in db.pending_swaps_on(di):
        if db.decide_swap(sw["id"], "expired", now):
            s = db.slot(sw["slot_id"])
            _send({"kind": "swap_expired",
                   "dm": [{"did": sw["requester_did"], "text": texts.swap_expired(s)},
                          {"did": sw["target_did"], "text": texts.swap_expired(s)}]})
    _send(_schedule_payload(di, edit=True))
    db.log("lock", now, "", {"date": di})
    return di


# ------------------------------------------------------------------ reminders + checks

def _live_night(d):
    n = db.night(d.isoformat())
    return n if n and n["status"] in ("published", "locked") else None


def remind_due(now):
    d = now.date()
    if not _live_night(d):
        return 0
    sent = 0
    for s in db.slots_for(d.isoformat()):
        start = engine.at_minute(d, s["start_min"], now.tzinfo)
        if start - datetime.timedelta(minutes=engine.REMIND_BEFORE_MIN) <= now < start \
                and s["employee_did"] and db.mark_slot(s["id"], "reminded_at", now):
            _send({"kind": "reminder", "dm": [{"did": s["employee_did"], "text": texts.reminder(s)}]})
            sent += 1
    return sent


def checks_due(now):
    nd, _m = engine.night_minute(now)
    if nd is None or not _live_night(nd):
        return 0               # safety net 3: a night never published can never produce a miss
    sent = 0
    for s in db.slots_for(nd.isoformat()):
        for cm in engine.check_minutes(s["start_min"], s["end_min"]):
            due = engine.at_minute(nd, cm, now.tzinfo)
            if due > now:
                break
            if now - due > datetime.timedelta(minutes=engine.SEND_GRACE_MIN):
                db.claim_check(s, due, status="voided", void_reason="bot_down")
                continue
            row = db.claim_check(s, due)
            if row is None:
                continue
            if not s["employee_did"]:
                db.decide_check(row["id"], "voided", now, "unreachable")
                continue
            _send({"kind": "check",
                   "dm": [{"did": s["employee_did"], "text": texts.check_text(engine.hm(cm))}],
                   "channel_text": "<@%s> %s" % (s["employee_did"], texts.check_text(engine.hm(cm))),
                   "mentions": [s["employee_did"]],
                   "view": "here",
                   "report": {"what": "check", "id": row["id"]}})
            sent += 1
    return sent


def delivered(report, dm_ok, dm_mid, ch_ok, ch_mid):
    """bot.py calls this after the Discord work (from a worker thread)."""
    if not report:
        return
    now = _now()
    what, rid = report.get("what"), report.get("id")
    if what == "check":
        db.set_check_delivery(rid, dm_ok, ch_ok, dm_mid, ch_mid, now)
    elif what == "swap":
        db.set_swap_message(rid, dm_mid)
    elif what == "schedule":
        db.set_night_message(rid, ch_mid)
    elif what == "issue_note":
        db.set_issue_note(rid, ch_mid)


def _judge_one(c, now, downs):
    """Decide one pending check. Returns the new status or 'pending'."""
    due = db.parse(c["due_at"])
    if c["sent_at"] is None and now < due + datetime.timedelta(minutes=engine.ANSWER_WINDOW_MIN):
        return "pending"
    verdict, reason = engine.check_verdict(due, now, bool(c["dm_ok"] or c["channel_ok"]),
                                           db.parse(c["answered_at"]), downs)
    if verdict == "pending":
        return "pending"
    if verdict == "voided":
        db.decide_check(c["id"], "voided", now, reason)
        return "voided"
    if verdict == "answered":
        db.decide_check(c["id"], "answered", now)
        return "answered"
    if db.decide_check(c["id"], "missed", now):
        _on_miss(c, now)
    return "missed"


def judge_due(now):
    downs = db.downtimes(now - datetime.timedelta(days=1))
    n = 0
    for c in db.pending_checks():
        if _judge_one(c, now, downs) != "pending":
            n += 1
    return n


def _on_miss(c, now):
    nth = db.misses_on(c["employee"], c["date"])
    decision = engine.miss_decision(nth)
    s = db.slot(c["slot_id"]) or {"start_min": 0, "end_min": 0}
    sup = roster.supervisor()
    sup_text = texts.supervisor_miss(c["employee"], nth, s)
    _send({"kind": "miss",
           "dm": [{"did": c["employee_did"], "text": texts.miss_dm(nth)},
                  {"did": sup["did"], "text": sup_text}],
           "channel_text": (("<@%s> " % sup["did"]) if sup["did"] else "") + sup_text,
           "mentions": [sup["did"]] if sup["did"] else []})
    db.log("miss", now, c["employee"], {"check": c["id"], "nth": nth, "decision": decision})
    if decision == engine.MISS_WARN:
        _warn(c["employee"], c["employee_did"], c["date"], now)


def _warn(employee, did, date_iso, now):
    """THE ONLY ops.db.issue_warning CALL IN THIS PACKAGE. One per employee per night,
    by ops' own UNIQUE(kind, employee, period_key) + UNIQUE(obligation_id)."""
    from ops import db as odb, engine as oeng, notify as onotify
    label = texts.day_label(_date(date_iso))
    ob = odb.ensure_obligation(OC_KIND, employee, did, "OC-" + date_iso, now)
    odb.set_status(ob["id"], "missed")
    w = odb.issue_warning(ob, texts.warning_reason(label))
    led = odb.recompute_commission(employee, oeng.month_key(now.date()))
    link = onotify._appeal_link(w["appeal_token"])
    _send({"kind": "warning",
           "dm": [{"did": did, "text": texts.warning_dm(label, _pct(led["multiplier"]), link)}],
           "hr_channel": onotify.hr_channel(),
           "hr_text": texts.hr_line(employee, label, _pct(led["multiplier"]))})
    db.log("warning", now, employee, {"date": date_iso, "warning_id": w["id"]})
    return w


def answer_check(message_id, presser_did, now=None):
    """The «✋ موجود» button. Returns (code, text_ar)."""
    now = now or _now()
    c = db.check_by_message(message_id)
    if not c:
        return "unknown", texts.NOT_FOUND
    if str(presser_did or "") != str(c["employee_did"] or ""):
        return "not_yours", texts.NOT_YOURS
    if c["status"] == "pending":
        due = db.parse(c["due_at"])
        if now <= due + datetime.timedelta(minutes=engine.ANSWER_WINDOW_MIN):
            if db.decide_check(c["id"], "answered", now, answered_at=now):
                return "answered", texts.THANKS
        else:
            _judge_one(c, now, db.downtimes(now - datetime.timedelta(days=1)))
        c = db.check(c["id"])
    if c["status"] == "answered":
        return "already", texts.ALREADY
    if c["status"] in ("missed", "late"):
        db.mark_late(c["id"], now)
        return "late", texts.LATE
    return "void", texts.THANKS


# ------------------------------------------------------------------ swaps

def request_swap(slot_id, presser_did, now=None):
    now = now or _now()
    s = db.slot(slot_id)
    requester = roster.name_for_did(presser_did)
    if not requester:
        return False, texts.NOT_ROSTER
    if not s:
        return False, "ما لقيت السلوت."
    n = db.night(s["date"]) or {}
    mine = next((x for x in db.slots_for(s["date"])
                 if engine.same_person(x["employee"], requester)), None)
    av = {a["name"]: a for a in roster.availability(_date(s["date"]))}
    ok, kind, why = engine.swap_decision(
        n.get("status"), requester, s, mine, bool((av.get(requester) or {}).get("ok")),
        bool(s["employee_did"]), bool(db.pending_swap_for_slot(s["id"])))
    if not ok:
        return False, why
    sw = db.create_swap(s["date"], s["id"], requester, str(presser_did), s["employee"],
                        s["employee_did"], kind, now)
    _send({"kind": "swap_ask", "view": "swap_ask",
           "dm": [{"did": s["employee_did"], "text": texts.swap_ask(requester, s, mine, kind)}],
           "report": {"what": "swap", "id": sw["id"]}})
    db.log("swap_request", now, requester, {"swap": sw["id"], "slot": s["id"], "kind": kind})
    return True, texts.SWAP_SENT.format(who=s["employee"])


def answer_swap(message_id, presser_did, accept, now=None):
    now = now or _now()
    sw = db.swap_by_message(message_id)
    if not sw:
        return False, texts.NOT_FOUND
    if str(presser_did or "") != str(sw["target_did"] or ""):
        return False, texts.NOT_YOURS
    n = db.night(sw["date"]) or {}
    s = db.slot(sw["slot_id"])
    if n.get("status") != "published":
        db.decide_swap(sw["id"], "expired", now)
        return False, texts.SWAP_GONE
    if not s or not engine.same_person(s["employee"], sw["target"]):
        db.decide_swap(sw["id"], "expired", now)
        return False, texts.SWAP_CHANGED
    if not db.decide_swap(sw["id"], "accepted" if accept else "declined", now):
        return False, texts.ALREADY
    if not accept:
        _send({"kind": "swap_declined",
               "dm": [{"did": sw["requester_did"], "text": texts.swap_result(False, sw["target"], s)}]})
        return True, "تم — رفضت الطلب."
    mine = next((x for x in db.slots_for(sw["date"])
                 if engine.same_person(x["employee"], sw["requester"])), None)
    db.set_slot_employee(s["id"], sw["requester"], sw["requester_did"], "swap", sw["target"])
    if sw["kind"] == "exchange" and mine:
        db.set_slot_employee(mine["id"], sw["target"], sw["target_did"], "swap", sw["target"])
    sup = roster.supervisor()
    _send({"kind": "swap_accepted",
           "dm": [{"did": sw["requester_did"], "text": texts.swap_result(True, sw["target"], s)},
                  {"did": sup["did"], "text": texts.swap_fyi(sw["requester"], sw["target"], s, sw["kind"])}]})
    _send(_schedule_payload(sw["date"], edit=True))
    db.log("swap_accepted", now, sw["target"], {"swap": sw["id"]})
    return True, "تم — الجدول تعدّل ✅"


def edit_slot(slot_id, employee, by, reason, now=None):
    """Dashboard reassignment by an editor (اسيل / admin). Works on a locked night too."""
    now = now or _now()
    s = db.slot(slot_id)
    if not s:
        return False, "ما لقيت السلوت."
    if not (reason or "").strip():
        return False, "اكتب سبب التغيير."
    if employee not in roster.roster_names():
        return False, "الاسم مو من فريق المناوبة."
    did = roster.did_for(employee)
    if not did:
        return False, "حساب %s مو مربوط بديسكورد — ما نقدر نسأله «موجود؟»." % employee
    old = dict(s)
    s = db.set_slot_employee(slot_id, employee, did, "edit", by, reason)
    _send({"kind": "slot_edit",
           "dm": [{"did": did, "text": texts.slot_edited_new(s, by)},
                  {"did": old["employee_did"], "text": texts.slot_edited_old(old, by)}]})
    _send(_schedule_payload(s["date"], edit=True))
    db.log("slot_edit", now, by, {"slot": s["id"], "from": old["employee"], "to": employee,
                                  "reason": reason})
    return True, ""


# ------------------------------------------------------------------ issue ownership (hooks)

def owner_now(now):
    nd, m = engine.night_minute(now)
    if nd is None or not _live_night(nd):
        return None
    return engine.owner_at(db.slots_for(nd.isoformat()), m)


def on_issue_opened(kind, ref, title, now=None):
    """Escalation card posted / maintenance ticket opened. Returns the note payload text for
    bot.py to post under it, or None when nobody is on duty (outside 17-24 or no night)."""
    now = now or _now()
    if not enabled():
        return None
    s = owner_now(now)
    if not s:
        return None
    row = db.open_issue(kind, ref, title, s["employee"], s["employee_did"], s["id"], s["date"], now)
    if not row:
        return None
    db.log("issue_open", now, s["employee"], {"kind": kind, "ref": str(ref)})
    return {"owner": s["employee"], "owner_did": s["employee_did"],
            "text": texts.issue_note(kind, s["employee_did"], s["employee"])}


def on_escalation_claimed(ref, by_name, now=None):
    now = now or _now()
    i = db.issue_by_ref(ref)
    if not i:
        return
    helper = None if engine.same_person(by_name, i["owner"]) else by_name
    db.claim_issue(ref, by_name, helper, now)


def on_issue_resolved(ref, by, now=None):
    now = now or _now()
    if db.resolve_issue(ref, by, now):
        db.log("issue_resolved", now, by, {"ref": str(ref)})


def on_ticket_message(ref, author_did, now=None):
    i = db.issue_by_ref(ref)
    if i and not i["resolved_at"] and str(author_did) == str(i["owner_did"] or ""):
        db.touch_issue(ref, now or _now())


def resolve_press(note_message_id, presser_did, is_admin, now=None):
    now = now or _now()
    i = db.issue_by_note(note_message_id)
    if not i:
        return False, texts.NOT_FOUND
    if i["resolved_at"]:
        return False, texts.ALREADY
    who = roster.name_for_did(presser_did) or ""
    allowed = (str(presser_did) == str(i["owner_did"] or "") or is_admin
               or (i["helper"] and engine.same_person(who, i["helper"])))
    if not allowed:
        return False, texts.RESOLVE_NOT_ALLOWED
    on_issue_resolved(i["ref"], who or str(presser_did), now)
    return True, texts.RESOLVED


def issues_due(now):
    if engine.night_minute(now)[0] is None:
        return 0
    sup = roster.supervisor()
    tonight = now.date().isoformat()
    n = 0
    for i in db.open_issues():
        opened = db.parse(i["opened_at"])
        if i["kind"] == "escalation" and engine.claim_overdue(
                opened, db.parse(i["claimed_at"]), now, bool(i["claim_alerted_at"])):
            db.mark_issue(i["ref"], "claim_alerted_at", db.iso(now))
            _send({"kind": "claim_overdue", "dm": [{"did": sup["did"], "text": texts.claim_overdue(i)}]})
            n += 1
        s = db.slot(i["slot_id"]) if i["slot_id"] else None
        if not s:
            continue
        slot_end = engine.at_minute(_date(s["date"]), s["end_min"], now.tzinfo)
        last = max(t for t in (opened, db.parse(i["claimed_at"]), db.parse(i["last_update_at"]))
                   if t is not None)
        if engine.stale_due(slot_end, last, now, i["stale_alerted_night"] == tonight):
            db.mark_issue(i["ref"], "stale_alerted_night", tonight)
            _send({"kind": "stale", "dm": [{"did": sup["did"], "text": texts.stale(i)}]})
            n += 1
    return n


# ------------------------------------------------------------------ handover + summary

def handover_due(now):
    d = now.date()
    if not _live_night(d):
        return 0
    slots = db.slots_for(d.isoformat())
    n = 0
    for s in slots:
        if s["end_min"] >= engine.WINDOW_MINUTES:
            continue
        end = engine.at_minute(d, s["end_min"], now.tzinfo)
        if not (end <= now < end + datetime.timedelta(minutes=engine.HANDOVER_GRACE_MIN)):
            continue
        if not db.mark_slot(s["id"], "handover_at", now):
            continue
        nxt = next((x for x in slots if x["start_min"] == s["end_min"]), None)
        if not nxt:
            continue
        _send({"kind": "handover",
               "channel_text": texts.handover(s, nxt, db.open_issues()),
               "mentions": [nxt["employee_did"]] if nxt["employee_did"] else []})
        n += 1
    return n


def summary_due(now):
    if now.hour >= engine.PUBLISH_HOUR:
        return None
    d = now.date() - datetime.timedelta(days=1)
    di = d.isoformat()
    if not db.night(di) or not db.mark_summary(di, now):
        return None
    checks = db.checks_on(di)
    per = []
    for s in db.slots_for(di):
        mine = [c for c in checks if c["slot_id"] == s["id"]]
        per.append({"name": s["employee"],
                    "answered": sum(1 for c in mine if c["status"] == "answered"),
                    "total": sum(1 for c in mine if c["status"] != "voided"),
                    "missed": sum(1 for c in mine if c["status"] in ("missed", "late"))})
    warned = [e["employee"] for e in db.events("warning", 50)
              if '"date": "%s"' % di in (e["detail"] or "")]
    text = texts.night_summary(d, per, warned, db.open_issues())
    sup = roster.supervisor()
    _send({"kind": "summary", "dm": [{"did": sup["did"], "text": text}], "channel_text": text})
    return di
