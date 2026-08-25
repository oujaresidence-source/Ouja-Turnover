# -*- coding: utf-8 -*-
"""
schedule.owners — the SHARED permanent-owner resolver.

The Employee Calendar (schedule_* tables) is the single source of truth for which
employee PERMANENTLY owns which apartment: `schedule_apartments.owner_id` →
`schedule_employees.id`. Every feature that needs "who is responsible for this
apartment" (weekly-report auto-fill, assignee defaults, future consumers) must go
through this module instead of keeping its own copy — one resolver, one answer.

Resolution order for a foreign apartment reference:
  1. Hostaway listing id (`listing_id`) — the stable key,
  2. exact apartment name — fallback for rows that predate Hostaway linking.
An apartment whose owner_id is NULL resolves to owner_name None (graceful blank).
"""

from . import db


def permanent_map():
    """One snapshot of the calendar's permanent assignments.

    Returns {
      employees:  [{id, name, emoji, color, off_day, sort_order}],
      apartments: [{id, name, listing_id, owner_id, owner_name, owner_emoji}],
    } — always fresh from the DB, so deletions/reassignments are reflected
    immediately everywhere.
    """
    emps = db.employees()
    ebyid = {e["id"]: e for e in emps}
    apartments = []
    for a in db.apartments():
        o = ebyid.get(a.get("owner_id"))
        apartments.append({
            "id": a["id"], "name": a.get("name"), "listing_id": a.get("listing_id"),
            "owner_id": (o or {}).get("id"),
            "owner_name": (o or {}).get("name"),
            "owner_emoji": (o or {}).get("emoji"),
        })
    employees = [{"id": e["id"], "name": e["name"], "emoji": e.get("emoji"),
                  "color": e.get("color"), "off_day": e.get("off_day"),
                  "sort_order": e.get("sort_order", 0)} for e in emps]
    return {"employees": employees, "apartments": apartments}


def owner_for(listing_id=None, name=None, pm=None):
    """Permanent owner name for one apartment reference (listing id first, then
    exact name). Pass a `permanent_map()` result as pm when resolving in a loop.
    Returns None when the apartment is unknown or unassigned."""
    pm = pm or permanent_map()
    rec = None
    if listing_id is not None:
        want = str(listing_id)
        for a in pm["apartments"]:
            if a.get("listing_id") is not None and str(a["listing_id"]) == want:
                rec = a
                break
    if rec is None and name:
        for a in pm["apartments"]:
            if a.get("name") == name:
                rec = a
                break
    return (rec or {}).get("owner_name")
