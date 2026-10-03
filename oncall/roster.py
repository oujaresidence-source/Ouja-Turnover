# -*- coding: utf-8 -*-
"""
oncall.roster — WHO can be on duty on a date, and who the supervisor is.

Nothing here keeps its own copy of the team:
  * people, weekly day off  -> the Employee Calendar (schedule.owners.permanent_map)
  * recorded leave          -> schedule.db.absences_recorded_on
  * Discord ids             -> ops.notify.employees()  (typed > env > assignments.json)
Only the LIST of on-call names (default the five) and the supervisor live in oncall_config.
"""

import json

from . import db, engine

DEFAULT_ROSTER = ["نورة", "ناصر", "محمد اليامي", "عهود", "مآثر"]
DEFAULT_SUPERVISOR = "اسيل"

WHY_OFF_DAY = "يوم الإجازة الأسبوعية"
WHY_LEAVE = "إجازة مسجّلة في تقويم الموظفين"
WHY_NO_DISCORD = "حساب الديسكورد مو مربوط"
WHY_NOT_IN_CALENDAR = "مو موجود في تقويم الموظفين"


def roster_names():
    raw = db.config_get("roster", "")
    try:
        names = json.loads(raw) if raw else None
    except Exception:
        names = None
    return [n for n in (names or DEFAULT_ROSTER) if (n or "").strip()]


def _calendar():
    from schedule import owners as _sowners
    return (_sowners.permanent_map() or {}).get("employees", [])


def _ids():
    from ops import notify as _onotify
    return {e["name"]: e.get("did") or "" for e in _onotify.employees()}


def _leave_ids(date_iso):
    """Employee ids NOT available in the EVENING of date_iso.

    Inverse of the cleaning board's rule on purpose: a MORNING half-day is back by 17:00
    (available tonight), an EVENING half-day is not. Every other approved absence = away."""
    from schedule import db as _sdb
    away = set()
    for a in _sdb.absences_recorded_on(date_iso):
        if (a.get("type") or "") == "half_day" and (a.get("shift") or "") == "morning":
            continue
        away.add(a.get("employee_id"))
    return away


def availability(d):
    """[{name, did, ok, why}] in roster order for the evening of date d."""
    cal = _calendar()
    ids = _ids()
    away = _leave_ids(d.isoformat())
    sw = engine.sun_weekday(d)
    out = []
    for name in roster_names():
        emp = next((e for e in cal if engine.norm(e["name"]) == engine.norm(name)), None)
        did = next((v for k, v in ids.items() if engine.norm(k) == engine.norm(name)), "")
        if emp is None:
            out.append({"name": name, "did": did, "ok": False, "why": WHY_NOT_IN_CALENDAR})
        elif emp.get("off_day") is not None and int(emp["off_day"]) == sw:
            out.append({"name": name, "did": did, "ok": False, "why": WHY_OFF_DAY})
        elif emp.get("id") in away:
            out.append({"name": name, "did": did, "ok": False, "why": WHY_LEAVE})
        elif not did:
            out.append({"name": name, "did": "", "ok": False, "why": WHY_NO_DISCORD})
        else:
            out.append({"name": name, "did": did, "ok": True, "why": ""})
    return out


def name_for_did(did):
    did = str(did or "")
    if not did:
        return None
    ids = _ids()
    for name in roster_names():
        for k, v in ids.items():
            if engine.norm(k) == engine.norm(name) and str(v) == did:
                return name
    return None


def did_for(name):
    ids = _ids()
    return next((v for k, v in ids.items() if engine.norm(k) == engine.norm(name)), "")


def supervisor():
    """{name, did}. Typed in the tab > ops lead (the first appeal approver) > nothing."""
    did = (db.config_get("supervisor_did", "") or "").strip()
    if not did:
        try:
            from ops import notify as _onotify
            did = _onotify.lead_id() or ""
        except Exception:
            did = ""
    return {"name": db.config_get("supervisor_name", "") or DEFAULT_SUPERVISOR, "did": did}
