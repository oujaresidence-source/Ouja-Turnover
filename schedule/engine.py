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

Ouja extension 2 (leave planner): a recurring override is a rule about a WEEKDAY, forever. The
planner needs the other kind — "on this one date, نورة takes حطين 6b" — so `date_overrides`
pins an apartment for ONE concrete date and outranks both the recurring rule and the balancer.
It is the primitive the whole «مخطط الإجازات» screen is built on.

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


def compute_day(weekday, employees, apartments, overrides=None, absent_ids=None,
                date_overrides=None):
    """Pure coverage computation. See module docstring + build spec §5.

    Args:
      weekday: int 0..6 (0=الأحد .. 6=السبت)
      employees:  [{id, name, off_day, color, sort_order}]
      apartments: [{id, name, owner_id, sort_order}]
      overrides:  [{day_of_week, apartment_id, covering_employee_id}]  (recurring, per weekday)
      absent_ids: iterable of employee ids on ad-hoc leave for this date (treated as off)
      date_overrides: [{apartment_id, covering_employee_id}] pinned for THIS EXACT DATE

    Precedence: date_overrides  ->  overrides (recurring)  ->  auto-balance.

    A date override applies to the WHOLE apartment list, not only to the pool belonging to off
    employees — moving one apartment on one day must work with nobody absent at all. One aimed
    at an employee who is off/absent that day is SKIPPED (same rule as a stale recurring
    override) and reported in `skipped_date_overrides` so the UI can flag it instead of
    silently doing nothing.

    Returns:
      {weekday, total, has_coverage, balanced, max_load, min_load, skipped_date_overrides,
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

    # 0) date pins win over everything. Resolved FIRST and against the whole apartment list, so
    #    one apartment can be moved on one day even when nobody is off. A pin at someone who is
    #    off/absent (or at a deleted employee/apartment) is refused and reported, never silently
    #    dropped — the planner UI shows it as a stale row.
    apt_by_id = {a["id"]: a for a in apts}
    date_ov, skipped = {}, []
    for d in (date_overrides or []):
        aid, cov = d.get("apartment_id"), d.get("covering_employee_id")
        if aid not in apt_by_id:
            reason = "unknown_apartment"
        elif cov not in emp_by_id:
            reason = "unknown_employee"
        elif cov not in working_ids:
            reason = "target_off"
        else:
            date_ov[aid] = cov
            continue
        skipped.append({"apartment_id": aid, "covering_employee_id": cov, "reason": reason})

    # base load = own apartments for working employees; their own list kept for display
    board = {e["id"]: {"own": [], "coverage": [], "load": 0} for e in working}
    covered = {}                                # apartment_id -> {covering_id, overridden}
    pool = []                                   # apartments owned by an off employee
    for a in apts:
        owner = a.get("owner_id")
        pin = date_ov.get(a["id"])
        if pin is not None:
            if pin == owner:                    # pinned at its own working owner = a no-op, and
                board[pin]["own"].append(a)     # never a card that says "covering yourself"
                board[pin]["load"] += 1
            else:
                board[pin]["coverage"].append({"apartment": a, "owner_id": owner,
                                               "owner_name": _nm(emp_by_id, owner),
                                               "overridden": True})
                board[pin]["load"] += 1
                covered[a["id"]] = {"covering_id": pin, "overridden": True}
            continue                            # a pinned apartment never reaches the pool
        if owner in working_ids:
            board[owner]["own"].append(a)
            board[owner]["load"] += 1
        else:
            pool.append(a)                      # owner is off (or unknown/None) -> needs coverage

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
                            "emoji": e.get("emoji"), "sort_order": e.get("sort_order", 0),
                            "own": b["own"], "coverage": b["coverage"], "load": b["load"]})

    off_out = []
    for e in emps:
        if e["id"] not in off_ids:
            continue
        mine = [a for a in apts if a.get("owner_id") == e["id"]]
        off_out.append({
            "id": e["id"], "name": e["name"], "color": e.get("color"), "emoji": e.get("emoji"),
            "reason": "leave" if e["id"] in leave else "off",
            "apartments": [{"apartment": a,
                            "covering_id": covered.get(a["id"], {}).get("covering_id"),
                            "covering_name": _nm(emp_by_id, covered.get(a["id"], {}).get("covering_id"))}
                           for a in mine],
        })

    loads = [w["load"] for w in working_out]
    # a day with date pins HAS coverage even when nobody is off — and `balanced` then reports
    # honestly that the owner's manual plan broke the even split, which is the point of a pin.
    has_cov = bool(off_ids) or bool(date_ov)
    mx, mn = (max(loads), min(loads)) if loads else (0, 0)
    total = len(apts)
    balanced = (not has_cov) or (mx - mn <= 1 and sum(loads) == total)
    return {"weekday": weekday, "total": total, "has_coverage": has_cov,
            "balanced": balanced, "max_load": mx, "min_load": mn,
            "skipped_date_overrides": skipped,
            "working": working_out, "off": off_out}


def _nm(emp_by_id, eid):
    e = emp_by_id.get(eid)
    return e["name"] if e else None


def rank_candidates(apartment, candidates, context=None):
    """Who should take this apartment on this day — ranked, with the REASON shown.

    Pure and deterministic, and deliberately in the engine rather than in JavaScript: the
    suggestion is part of the model, so it can be tested and can never drift from the board.

    context = {
      apartment_district: the apartment's compound/district,
      districts: {employee_id: [districts they already work that day]},
      history:   {employee_id: how many times they have covered THIS apartment before},
      minutes:   {employee_id: their estimated minutes that day},
    }

    Order: same district (less driving between Malqa and Qurtubah is the biggest real win)
        -> has covered it before -> lightest day -> sort_order -> id.

    The `reason` reported is the factor that actually SEPARATED this candidate from the others.
    A factor every candidate shares explains nothing, so it is skipped — otherwise every
    suggestion on a single-district day would claim "same compound" and mean nothing.
    """
    ctx = context or {}
    apt_district = ctx.get("apartment_district")
    districts = ctx.get("districts") or {}
    history = ctx.get("history") or {}
    minutes = ctx.get("minutes") or {}
    cands = list(candidates or [])
    if not cands:
        return []

    def _same(c):
        return bool(apt_district and apt_district in (districts.get(c["id"]) or []))

    def _hist(c):
        return int(history.get(c["id"]) or 0)

    def _mins(c):
        return int(minutes.get(c["id"]) or 0)

    same_all = [_same(c) for c in cands]
    hist_all = [_hist(c) for c in cands]
    mins_all = [_mins(c) for c in cands]
    sep_district = len(set(same_all)) > 1
    sep_hist = len(set(hist_all)) > 1
    sep_mins = len(set(mins_all)) > 1
    best_hist, best_mins = max(hist_all), min(mins_all)

    out = []
    for c in cands:
        same, hist, mins = _same(c), _hist(c), _mins(c)
        if sep_district and same:
            reason, ar, en = "same_district", "نفس المجمع", "Same compound"
        elif sep_hist and hist and hist == best_hist:
            reason, ar, en = "covers_it_usually", "يغطّيها عادة", "Usually covers it"
        elif sep_mins and mins == best_mins:
            reason, ar, en = "lightest_day", "أقل حمل اليوم", "Lightest day"
        else:
            reason, ar, en = "available", "متاح", "Available"
        out.append(dict(c, reason=reason, reason_ar=ar, reason_en=en,
                        same_district=same, covered_before=hist, est_minutes=mins))
    out.sort(key=lambda c: (0 if c["same_district"] else 1, -c["covered_before"],
                            c["est_minutes"], c.get("sort_order", 0), c["id"]))
    return out
