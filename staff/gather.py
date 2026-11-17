# -*- coding: utf-8 -*-
"""
staff.gather — collect every input staff.engine needs for ONE day, from the bridges bot.py
hands over (staff.host). Caches and local tables ONLY: a phone poll must never reach Hostaway
(the 2026-11-06 pool jam, when dashboard polls starved Discord). Each source fails on its own,
so one broken store blanks one part of the screen, never the whole app.
"""

import datetime
import time

from .host import HOST

OPEN_TICKET = ("open", "in_progress")


def _lid(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _get(name, default):
    """A missing bridge gives `default`; a FAILING one raises, so _safe drops that part instead
    of showing an empty list that looks like «nothing to do»."""
    fn = getattr(HOST, name, None)
    if fn is None:
        return default
    v = fn()
    return default if v is None else v


def _safe(name, fn, g):
    try:
        fn(g)
    except Exception as e:
        print("[staff] gather %s failed: %s" % (name, e))


def _schedule(g, today_iso):
    day = HOST.schedule_day
    if day is None:
        return
    g["day"] = day(today_iso)
    base = datetime.date.fromisoformat(today_iso)
    g["week_days"] = [day((base + datetime.timedelta(days=i)).isoformat()) for i in range(7)]


def _snapshot(g, today_iso, clock):
    snap = _get("today_snapshot", None)
    if snap and str((snap[0] or {}).get("date") or "") == today_iso:
        g["snap"] = snap[0]
        g["snap_age_min"] = int(max(0, clock() - snap[1]) // 60)
    names = {}
    for lid, nm in (_get("listing_names", {}) or {}).items():
        names.setdefault(nm, _lid(lid))
    for u in _get("catalog_units", []) or []:
        if u.get("id") and u.get("name"):
            names.setdefault(u["name"], _lid(u["id"]))
    g["name_to_lid"] = names


def _tickets(g):
    g["tickets"] = [{"id": t.get("id"), "lid": _lid(t.get("lid")), "status": t.get("status"),
                     "priority": t.get("priority"), "title": t.get("title"),
                     "due_date": t.get("due_date")}
                    for t in _get("tickets", []) or [] if t.get("status") in OPEN_TICKET]


def _cleaning(g, today_iso):
    cl, reviews = {}, []
    for r in _get("cleaning_reports", []) or []:
        if str(r.get("date") or "")[:10] != today_iso or r.get("listing_id") is None:
            continue
        lid = _lid(r.get("listing_id"))
        cl.setdefault(lid, {})["report"] = r.get("status") or ""
        reviews.append({"lid": lid, "name": r.get("apartment_name") or "",
                        "status": r.get("status") or ""})
    suffix = "|" + today_iso
    for k, e in (_get("route_status", {}) or {}).items():
        if str(k).endswith(suffix) and isinstance(e, dict):
            cl.setdefault(_lid(e.get("lid")), {})["action"] = e.get("action") or ""
    g["cleaning"], g["reviews"] = cl, reviews


def _oncall(g):
    if HOST.oncall_state is None:
        return
    st = HOST.oncall_state() or {}
    g["oncall"] = {"now": st.get("now"),
                   "tonight": [{"employee": x.get("employee"), "from": x.get("from"),
                                "to": x.get("to")}
                               for x in ((st.get("tonight") or {}).get("slots") or [])]}


def gather(today_iso, clock=time.time):
    g = {}
    _safe("schedule", lambda x: _schedule(x, today_iso), g)
    _safe("snapshot", lambda x: _snapshot(x, today_iso, clock), g)
    _safe("tickets", _tickets, g)
    _safe("promises", lambda x: x.update(promises=list(_get("promises", []) or [])), g)
    _safe("cleaning", lambda x: _cleaning(x, today_iso), g)
    _safe("oncall", _oncall, g)
    g["replies"] = HOST.call("pending_replies", 0)
    g["escalations"] = HOST.call("open_escalations", 0)
    return g
