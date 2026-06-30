"""
schedule.engine — the SINGLE SOURCE OF TRUTH for "which apartments is each employee
responsible for on a given weekday". Pure, deterministic, dependency-free (no DB, no clock).

The dashboard tab, the standalone /team-calendar page, and every notification all render from
`compute_day(...)`, so the numbers can never disagree.

Model (build spec §1 + §5):
  * each employee permanently OWNS a set of apartments (their base, every working day).
  * each employee has exactly one weekly day off (off_day, 0=الأحد … 6=السبت).
  * on an employee's day off, their apartments are covered by the others working that day,
    auto-distributed as evenly as possible (balanced daily load). An editor may pin any single
    apartment to a chosen employee for a weekday via a recurring OVERRIDE.
  * days where nobody is off (Thu/Fri) have no coverage — everyone on their own base.

Ouja extension (kept from roster v1, per owner choice): ad-hoc, date-specific LEAVE. The route
passes the set of employee ids who are on approved leave for the chosen date as `absent_ids`;
the engine treats them exactly like an extra day-off, so their apartments join the pool and
rebalance. Pass an empty set (default) for the pure weekly model.
"""

# Python date.weekday(): Mon=0 .. Sun=6. The spec numbers days 0=الأحد(Sun) .. 6=السبت(Sat).
def to_weekday(d):
    """date/datetime/ISO-string -> spec weekday int (0=Sun .. 6=Sat)."""
    if isinstance(d, str):
        import datetime as _dt
        d = _dt.date.fromisoformat(d[:10])
    return (d.weekday() + 1) % 7


def compute_day(weekday, employees, apartments, overrides=None, absent_ids=None):
    """Pure coverage computation. See module docstring + build spec §5.

    Args:
      weekday: int 0..6 (0=الأحد .. 6=السبت)
      employees:  [{id, name, off_day, color, sort_order}]
      apartments: [{id, name, owner_id, sort_order}]
      overrides:  [{day_of_week, apartment_id, covering_employee_id}]  (recurring)
      absent_ids: iterable of employee ids on ad-hoc leave for this date (treated as off)

    Returns:
      {weekday, total, has_coverage, balanced, max_load, min_load,
       working:[{id,name,color,sort_order, own:[apt], coverage:[{apartment,owner_id,owner_name,overridden}], load}],
       off:[{id,name,color, reason:'off'|'leave', apartments:[{apartment, covering_id, covering_name}]}]}
    """
    overrides = overrides or []
    leave = set(absent_ids or [])

    emps = sorted(employees, key=lambda e: (e.get("sort_order", 0), e["id"]))
    emp_by_id = {e["id"]: e for e in employees}

    off_by_day = {e["id"] for e in emps if e.get("off_day") == weekday}
    off_ids = off_by_day | leave
    working = [e for e in emps if e["id"] not in off_ids]
    working_ids = {e["id"] for e in working}

    apts = sorted(apartments, key=lambda a: (
        emp_by_id.get(a.get("owner_id"), {}).get("sort_order", 9999), a.get("sort_order", 0), a["id"]))

    # base load = own apartments for working employees; their own list kept for display
    board = {e["id"]: {"own": [], "coverage": [], "load": 0} for e in working}
    pool = []                                   # apartments owned by an off employee
    for a in apts:
        owner = a.get("owner_id")
        if owner in working_ids:
            board[owner]["own"].append(a)
            board[owner]["load"] += 1
        else:
            pool.append(a)                      # owner is off (or unknown/None) -> needs coverage

    covered = {}                                # apartment_id -> {covering_id, overridden}

    # 1) recurring overrides for this weekday: pin apt -> covering (if covering is working)
    ov_for_day = {o["apartment_id"]: o["covering_employee_id"]
                  for o in overrides if o.get("day_of_week") == weekday}
    remaining = []
    for a in pool:
        cov = ov_for_day.get(a["id"])
        if cov is not None and cov in working_ids:
            board[cov]["coverage"].append({"apartment": a, "owner_id": a.get("owner_id"),
                                           "owner_name": _nm(emp_by_id, a.get("owner_id")),
                                           "overridden": True})
            board[cov]["load"] += 1
            covered[a["id"]] = {"covering_id": cov, "overridden": True}
        else:
            remaining.append(a)                 # stale/absent-target override is skipped

    # 2) greedy balance the rest: least-loaded working employee, tiebreak sort_order
    for a in remaining:
        if not working:
            covered[a["id"]] = {"covering_id": None, "overridden": False}   # nobody to cover
            continue
        target = min(working, key=lambda e: (board[e["id"]]["load"], e.get("sort_order", 0), e["id"]))
        tid = target["id"]
        board[tid]["coverage"].append({"apartment": a, "owner_id": a.get("owner_id"),
                                       "owner_name": _nm(emp_by_id, a.get("owner_id")),
                                       "overridden": False})
        board[tid]["load"] += 1
        covered[a["id"]] = {"covering_id": tid, "overridden": False}

    # assemble output
    working_out = []
    for e in working:
        b = board[e["id"]]
        working_out.append({"id": e["id"], "name": e["name"], "color": e.get("color"),
                            "sort_order": e.get("sort_order", 0),
                            "own": b["own"], "coverage": b["coverage"], "load": b["load"]})

    off_out = []
    for e in emps:
        if e["id"] not in off_ids:
            continue
        mine = [a for a in apts if a.get("owner_id") == e["id"]]
        off_out.append({
            "id": e["id"], "name": e["name"], "color": e.get("color"),
            "reason": "leave" if e["id"] in leave else "off",
            "apartments": [{"apartment": a,
                            "covering_id": covered.get(a["id"], {}).get("covering_id"),
                            "covering_name": _nm(emp_by_id, covered.get(a["id"], {}).get("covering_id"))}
                           for a in mine],
        })

    loads = [w["load"] for w in working_out]
    has_cov = bool(off_ids)
    mx, mn = (max(loads), min(loads)) if loads else (0, 0)
    total = len(apts)
    balanced = (not has_cov) or (mx - mn <= 1 and sum(loads) == total)
    return {"weekday": weekday, "total": total, "has_coverage": has_cov,
            "balanced": balanced, "max_load": mx, "min_load": mn,
            "working": working_out, "off": off_out}


def _nm(emp_by_id, eid):
    e = emp_by_id.get(eid)
    return e["name"] if e else None
