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
# Owner, 2026-10-04: عهود is the only operations employee who works from the office, so on
# her working days the 17:00 slot is always hers. Editable in the tab; "" switches it off.
DEFAULT_FIRST_SLOT = "عهود"

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
    """{calendar name: discord id}. RAISES on a read failure: an unreadable calendar must not
    look like «nobody is linked» — that once would have published an empty night for good.
    The tick step fails instead and the next minute retries."""
    from ops import notify as _onotify
    rows, err = _onotify.roster_or_error()
    if err is not None:
        raise RuntimeError("ops roster unreadable: %s" % err)
    return {e["name"]: e.get("did") or "" for e in rows}


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
            continue
        name = emp["name"]          # the calendar's spelling — warnings and pay key on it
        if emp.get("off_day") is not None and int(emp["off_day"]) == sw:
            out.append({"name": name, "did": did, "ok": False, "why": WHY_OFF_DAY})
        elif emp.get("id") in away:
            out.append({"name": name, "did": did, "ok": False, "why": WHY_LEAVE})
        elif not did:
            out.append({"name": name, "did": "", "ok": False, "why": WHY_NO_DISCORD})
        else:
            out.append({"name": name, "did": did, "ok": True, "why": ""})
    return out


def on_leave(name, d):
    """Recorded leave for this person on the evening of date d — re-read at every check, so
    leave approved AFTER the night was published still protects them."""
    emp = next((e for e in _calendar() if engine.norm(e["name"]) == engine.norm(name)), None)
    return bool(emp) and emp.get("id") in _leave_ids(d.isoformat())


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


def first_slot():
    """The name pinned to the 17:00 slot on their working days, or "" for none."""
    v = db.config_get("first_slot", None)
    return DEFAULT_FIRST_SLOT if v is None else (v or "").strip()


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
