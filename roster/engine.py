"""
roster.engine — the SINGLE SOURCE OF TRUTH for "who is responsible for which unit today".

Pure, dependency-free, deterministic. No DB, no I/O, no clock. Both front-ends (the
dashboard tab and the standalone /roster page) and every notification render from the
SAME `compute_roster(...)` output, so the numbers can never disagree for a given date.

The model (see build spec §4):
  * every active employee may have ONE weekly day off (weekly_off: 'sun'..'sat' | '').
  * every active property has a primary custodian (primary_owner_id).
  * on any date some custodians are OUT (weekly day off OR an approved absence). Their
    units become "orphans" that must be covered by an available colleague.
  * coverage is COUNT-BALANCED: each orphan goes to whoever currently carries the fewest
    units; ties broken by employee id so the result is 100% reproducible.

`pick_target` is a pluggable strategy (default = count-balance) so LATER we can swap in
zone/proximity or skills matching without touching this function's contract.
"""

# Python's date.weekday(): Mon=0 .. Sun=6. We store days off as short names.
_DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def weekday_name(d):
    """Accept a datetime.date/datetime OR an ISO 'YYYY-MM-DD' string -> 'sun'..'sat'."""
    if isinstance(d, str):
        import datetime as _dt
        d = _dt.date.fromisoformat(d[:10])
    return _DAY_NAMES[d.weekday()]


def _count_balance(prop, available, board, load):
    """Default strategy: give the orphan to the least-loaded available employee.
    Deterministic tiebreak = employee id (so the board is reproducible). `available`
    is a list of employee dicts; returns an employee id."""
    return min(available, key=lambda e: (load[e["id"]], e["id"]))["id"]


def compute_roster(date, employees, properties, absences_for_date, locks=None,
                   pick_target=None, cap=None):
    """Compute today's responsibility board. See module docstring + build spec §4.

    Args:
      date: date | 'YYYY-MM-DD'.
      employees: [{id, name_ar, initial_ar, weekly_off, role, is_active}]
      properties: [{id, display_name_ar, primary_owner_id, zone, turnover_weight, status}]
      absences_for_date: [{employee_id, status, type}]  (only status=='approved' counts)
      locks: [{property_id, responsible_id, original_owner_id}]  (engine won't move these)
      pick_target: optional callable(prop, available, board, load) -> employee_id
      cap: optional int per-person soft cap; defaults to balanced ceil + 1.

    Returns a dict:
      {date, weekday, board:{id:{primary:[prop],covered:[{property,original_owner_id}]}},
       absent:[id], available:[id], total, assigned, gaps, gap_properties:[prop],
       overloads:[id], escalate:bool}
    """
    locks = locks or []
    pick = pick_target or _count_balance
    wd = weekday_name(date)

    emps_by_id = {e["id"]: e for e in employees}
    active_emps = [e for e in employees if e.get("is_active")]

    # --- who is OUT today: weekly day off + approved absences ---
    off_today = {e["id"] for e in active_emps if (e.get("weekly_off") or "") == wd}
    on_leave = {a["employee_id"] for a in (absences_for_date or [])
                if a.get("status") == "approved"}
    absent = off_today | on_leave

    available = [e for e in active_emps if e["id"] not in absent]
    avail_ids = {e["id"] for e in available}
    board = {e["id"]: {"primary": [], "covered": []} for e in available}
    load = {e["id"]: 0 for e in available}

    active_props = [p for p in properties if (p.get("status") or "active") == "active"]
    props_by_id = {p["id"]: p for p in active_props}

    gap_properties = []          # properties we could not place onto anyone available
    locked_ids = set()

    # --- 1) locked assignments first (manual overrides) — engine never moves these ---
    for lk in locks:
        pid = lk.get("property_id")
        p = props_by_id.get(pid)
        if not p:
            continue
        locked_ids.add(pid)
        resp = lk.get("responsible_id")
        orig = lk.get("original_owner_id")
        if resp not in avail_ids:
            # pinned to someone who is out → cannot honor it today → a gap (escalate).
            gap_properties.append(p)
            continue
        if resp == p.get("primary_owner_id") and (orig in (None, resp)):
            board[resp]["primary"].append(p)
        else:
            board[resp]["covered"].append({"property": p, "original_owner_id": orig
                                           if orig is not None else p.get("primary_owner_id")})
        load[resp] += 1

    # --- 2) available custodians keep their own (unlocked) units ---
    for p in active_props:
        if p["id"] in locked_ids:
            continue
        owner = p.get("primary_owner_id")
        if owner in avail_ids:
            board[owner]["primary"].append(p)
            load[owner] += 1

    # --- 3) orphans = unlocked active units whose owner is absent / missing / inactive ---
    orphans = [p for p in active_props
               if p["id"] not in locked_ids and p.get("primary_owner_id") not in avail_ids]
    orphans.sort(key=lambda p: p["id"])

    for p in orphans:
        if not available:
            gap_properties.append(p)          # whole team out → cannot cover (escalate)
            continue
        target = pick(p, available, board, load)
        board[target]["covered"].append({"property": p,
                                          "original_owner_id": p.get("primary_owner_id")})
        load[target] += 1

    total = len(active_props)
    assigned = sum(load.values())
    gaps = total - assigned
    if cap is None and available:
        # a balanced board carries ceil(total/available); allow +1 slack before "overloaded".
        cap = -(-total // len(available)) + 1
    overloads = sorted([eid for eid, n in load.items() if cap is not None and n > cap])

    return {
        "date": date if isinstance(date, str) else date.isoformat(),
        "weekday": wd,
        "board": board,
        "load": load,
        "absent": sorted(absent),
        "available": sorted(avail_ids),
        "total": total,
        "assigned": assigned,
        "gaps": gaps,
        "gap_properties": gap_properties,
        "overloads": overloads,
        "escalate": bool(gaps or gap_properties),
        "_emps_by_id": emps_by_id,   # convenience for the route layer to enrich names
    }
