# -*- coding: utf-8 -*-
"""
targets.score — the scoreboard: per-unit occupancy, quarterly baselines, tiers, the gate.

NOTHING IN THIS FILE PAYS CASH. Occupancy cannot tell work from luck (the backtest in the
design spec), so all it does is move an employee's share between 30% and 40% and tell the
team where the empty nights are. The rules themselves are engine.py's; this file only feeds
them the stored history.
"""

import datetime as dt
import math

from . import db, engine, history
from .host import HOST

_cache = {"v": None, "by_unit": {}, "blocked": {}}


def data():
    """(confirmed reservations by unit, blocked dates by unit) — reloaded after any write."""
    v = db.version()
    if _cache["v"] != v:
        by_unit = {}
        for r in db.q("SELECT unit, arrival, departure, total, status FROM tg_res "
                      "WHERE status IN ('new','modified')"):
            by_unit.setdefault(r["unit"], []).append(r)
        _cache.update(v=v, by_unit=by_unit, blocked=db.all_blocked())
    return _cache["by_unit"], _cache["blocked"]


# ------------------------------------------------------------------ calendar helpers

def month_of(d):
    return "%04d-%02d" % (d.year, d.month)


def quarter_of(d):
    if isinstance(d, str):
        return "%s-Q%d" % (d[:4], (int(d[5:7]) - 1) // 3 + 1)
    return "%04d-Q%d" % (d.year, (d.month - 1) // 3 + 1)


def quarter_months(quarter):
    y, qn = int(quarter[:4]), int(quarter[-1])
    return ["%04d-%02d" % (y, m) for m in range(3 * qn - 2, 3 * qn + 1)]


def prev_quarter(quarter):
    y, qn = int(quarter[:4]), int(quarter[-1])
    return "%04d-Q%d" % ((y - 1, 4) if qn == 1 else (y, qn - 1))


def next_quarter(quarter):
    y, qn = int(quarter[:4]), int(quarter[-1])
    return "%04d-Q%d" % ((y + 1, 1) if qn == 4 else (y, qn + 1))


# ------------------------------------------------------------------ one unit, one month

def blocked_count(unit, month_key):
    s, e = engine.month_bounds(month_key)
    si, ei = s.isoformat(), e.isoformat()
    return sum(1 for d in data()[1].get(unit, ()) if si <= d < ei)


def unit_month(unit, month_key, floor=0, typical=0):
    return engine.unit_month(data()[0].get(unit, []), blocked_count(unit, month_key),
                             month_key, floor, typical)


def unit_revenue(unit, month_key):
    """What the unit's confirmed stays bring in that month (a stay across two months is split
    by night)."""
    return engine.revenue_in_month(data()[0].get(unit, []), month_key)


def revenue_base(unit, months):
    """The unit's average month over `months` — only months AFTER the one it first took a
    booking in (a half first month would make the target too easy). None = no full month."""
    stays = data()[0].get(unit, [])
    born = min((r["arrival"] for r in stays), default="9999")[:7]
    full = [mk for mk in months if mk > born]
    if not full:
        return None
    return sum(unit_revenue(unit, mk) for mk in full) / len(full)


def price_stats(unit, asof):
    """(typical, p75, p10) nightly price over the year before `asof`, weighted by nights.
    typical = the unit's average night; p75 = the suggested price ceiling; p10 = the suggested
    price floor (nine nights in ten sold above it)."""
    lo, hi = (asof - dt.timedelta(days=365)).isoformat(), asof.isoformat()
    prices = []
    for r in data()[0].get(unit, []):
        if not (lo <= r["arrival"] < hi):
            continue
        n = (dt.date.fromisoformat(r["departure"]) - dt.date.fromisoformat(r["arrival"])).days
        if n > 0 and (r["total"] or 0) > 0:
            prices.extend([float(r["total"]) / n] * n)
    if not prices:
        return 0, 0, 0
    prices.sort()
    p75 = prices[min(len(prices) - 1, int(math.ceil(0.75 * len(prices))) - 1)]
    p10 = prices[max(0, int(math.ceil(0.10 * len(prices))) - 1)]
    return int(round(sum(prices) / len(prices))), int(round(p75)), int(round(p10))


def empty_nights(unit, start, end):
    """Dates in [start, end) with no confirmed stay and no block."""
    by_unit, blocked = data()
    taken = set(blocked.get(unit, ()))
    si, ei = start.isoformat(), end.isoformat()
    for r in by_unit.get(unit, []):
        if r["departure"] <= si or r["arrival"] >= ei:
            continue
        a = max(dt.date.fromisoformat(r["arrival"]), start)
        b = min(dt.date.fromisoformat(r["departure"]), end)
        for i in range((b - a).days):
            taken.add((a + dt.timedelta(days=i)).isoformat())
    out = []
    for i in range(max(0, (end - start).days)):
        d = (start + dt.timedelta(days=i)).isoformat()
        if d not in taken:
            out.append(d)
    return out


# ------------------------------------------------------------------ quarterly proposal

def owned_units():
    """[{unit, listing_id, name, employee}] from the Employee Calendar (the one ownership list)."""
    out = []
    for o in HOST.call("ownership", []) or []:
        lid = o.get("listing_id")
        if lid in (None, ""):
            continue
        out.append({"unit": str(lid), "listing_id": lid, "name": o.get("name") or str(lid),
                    "employee": o.get("employee") or ""})
    return out


def propose(quarter, today):
    """Compute (and store as 'proposed') this quarter's baseline, tiers and price bounds for
    every owned unit. Approved rows are left untouched."""
    months = quarter_months(quarter)
    last_year = ["%04d-%s" % (int(m[:4]) - 1, m[5:]) for m in months]
    ref = min(months[0], month_of(today))
    trailing = [history.shift_month(ref, -i) for i in (3, 2, 1)]
    asof = engine.month_bounds(ref)[0]
    prev = {r["unit"]: r for r in db.targets(prev_quarter(quarter)) if r["status"] == "approved"}
    old = {r["unit"]: r for r in db.targets(quarter)}
    kept = {u: float(r["floor"] or 0) for u, r in old.items()}
    rows = []
    for u in owned_units():
        typical, p75, p10 = price_stats(u["unit"], asof)
        # The floor, in order: what the owner already typed for this quarter; the floor set in
        # the pricing engine; else a SUGGESTION from the unit's own history (it is only a
        # proposal — the owner edits it before approving).
        floor = (kept.get(u["unit"]) or float(HOST.call("floor", 0, u["listing_id"]) or 0)
                 or float(p10))

        stays = data()[0].get(u["unit"], [])
        born = min((r["arrival"] for r in stays), default="9999")[:7]

        def occ(mk, _u=u["unit"], _f=floor, _t=typical, _born=born):
            if mk < _born:          # before the unit's first booking: not a zero, just no data
                return None
            m = unit_month(_u, mk, _f, _t)
            return None if m is None else m["occupancy"]

        a = [occ(mk) for mk in last_year]
        b = [occ(mk) for mk in trailing]
        has_history = bool(data()[0].get(u["unit"]))
        base = engine.baseline(a, b) if has_history else None
        basis = ("peers" if base is None else
                 "last_year+recent" if any(x is not None for x in a) and any(x is not None for x in b)
                 else "recent" if any(x is not None for x in b) else "last_year")
        compound = (HOST.call("unit_meta", {}, u["listing_id"]) or {}).get("compound") or ""
        rows.append(dict(u, floor=floor, typical=typical, ceiling_suggested=p75,
                         floor_suggested=p10, base=base, basis=basis, compound=compound,
                         rev_base=revenue_base(u["unit"], trailing)))
    known = [r for r in rows if r["base"] is not None]
    rev_known = [r["rev_base"] for r in rows if r["rev_base"]]
    for r in rows:
        # The revenue target: the unit's own average month + the step. A unit with no full
        # month yet takes the average of the others. A target the owner already typed stays.
        if not r["rev_base"]:
            r["rev_base"] = (sum(rev_known) / len(rev_known)) if rev_known else 0.0
        r["rev_base"] = round(r["rev_base"], 2)
        r["rev_target"] = float(round(r["rev_base"] * (1 + engine.TARGET_STEP)))
        o = old.get(r["unit"])
        if o and o.get("rev_target") and o.get("rev_base") is not None \
                and float(o["rev_target"]) != float(round(float(o["rev_base"]) * (1 + engine.TARGET_STEP))):
            r["rev_target"] = float(o["rev_target"])
    for r in rows:
        if r["base"] is None:
            peers = [k["base"] for k in known if r["compound"] and k["compound"] == r["compound"]]
            peers = peers or [k["base"] for k in known]
            r["base"] = (sum(peers) / len(peers)) if peers else engine.BRONZE_FLOOR - 0.05
        p = prev.get(r["unit"])
        if p and p.get("baseline") is not None:
            r["base"] = min(r["base"], float(p["baseline"]) + 0.02)   # never more than +2 points
        t = engine.tiers(r["base"])
        ceiling = r["ceiling_suggested"] if r["ceiling_suggested"] > r["floor"] else 0
        r.update(baseline=round(r["base"], 4), bronze=round(t["bronze"], 4),
                 silver=round(t["silver"], 4), gold=round(t["gold"], 4), ceiling=ceiling)
    db.save_proposals(quarter, rows)
    return db.targets(quarter)


def quarter_state(quarter):
    rows = db.targets(quarter)
    if not rows:
        return "none"
    return "approved" if all(r["status"] == "approved" for r in rows) else "proposed"


# ------------------------------------------------------------------ the board

def _unit_line(unit, name, month_key, today, target):
    """One unit's scoreboard line. `target` is its tg_targets row (or None)."""
    lid = unit if not unit.startswith("n:") else None
    floor = float((target or {}).get("floor") or 0) or float(HOST.call("floor", 0, lid) or 0)
    typical = float((target or {}).get("typical") or 0)
    if not typical:
        typical = price_stats(unit, engine.month_bounds(month_key)[0])[0]   # (typical, p75, p10)
    m = unit_month(unit, month_key, floor, typical)
    line = {"unit": unit, "name": name, "floor": int(floor), "has_target": bool(target),
            "ceiling": int((target or {}).get("ceiling") or 0)}
    s0, e0 = engine.month_bounds(month_key)
    line.update(revenue=round(unit_revenue(unit, month_key)),
                rev_target=round(engine.month_target(float((target or {}).get("rev_target") or 0),
                                                     (e0 - s0).days, blocked_count(unit, month_key))))
    if m is None:
        line.update(excluded=True)
        return line
    s, e = engine.month_bounds(month_key)
    empties = empty_nights(unit, max(s, today), e) if today < e else []
    half = int(round(2 * (m["nights"] - m["below_floor"] - m["weighted"])))
    line.update(excluded=False, occupancy=round(m["occupancy"], 4), available=m["available"],
                nights=int(m["nights"]), below_floor=int(m["below_floor"]), half_nights=max(0, half),
                empty=len(empties), empty_dates=empties[:31])
    if target:
        tg = {k: float(target[k]) for k in ("bronze", "silver", "gold")}
        line.update(tg, tier=engine.tier_reached(m["occupancy"], tg),
                    to_bronze=max(0, int(math.ceil(tg["bronze"] * m["available"] - m["weighted"] - 1e-9))))
    return line


def board(employee, month_key, today):
    """An employee's scoreboard for one month.
    With approved targets the unit list is the one frozen at approval; before that it is the
    live ownership, shown without tiers."""
    quarter = quarter_of(month_key)
    rows = [r for r in db.targets(quarter) if r["status"] == "approved" and r["employee"] == employee]
    approved = bool(rows)
    if approved:
        units = [_unit_line(r["unit"], r["name"], month_key, today, r) for r in rows]
    else:
        units = [_unit_line(u["unit"], u["name"], month_key, today, None)
                 for u in owned_units() if u["employee"] == employee]
    scored = [u for u in units if not u.get("excluded") and u.get("has_target")]
    hit = sum(1 for u in scored if u.get("tier"))
    share = engine.employee_share(hit, len(scored))
    need_full = max(0, int(math.ceil(engine.GATE_FULL * len(scored) - 1e-9)) - hit)
    return {"employee": employee, "month": month_key, "quarter": quarter, "approved": approved,
            "units": units, "hit": hit, "scored": len(scored), "share": round(share, 4),
            "units_to_full_share": need_full}


def gate(employee, month_key, today):
    b = board(employee, month_key, today)
    return b["hit"], b["scored"]


def employees(quarter=None):
    names = {u["employee"] for u in owned_units() if u["employee"]}
    if quarter:
        names |= {r["employee"] for r in db.targets(quarter) if r["employee"]}
    return sorted(names)


def rescue(month_key, today):
    """Units behind bronze this month — the operations manager's list (day 10 and day 20)."""
    out = []
    for r in db.targets(quarter_of(month_key)):
        if r["status"] != "approved":
            continue
        line = _unit_line(r["unit"], r["name"], month_key, today, r)
        if line.get("excluded") or line.get("tier"):
            continue
        out.append({"unit": r["unit"], "name": r["name"], "employee": r["employee"] or "",
                    "occupancy": line["occupancy"], "bronze": line["bronze"],
                    "to_bronze": line["to_bronze"], "empty": line["empty"],
                    "price_stuck": line["below_floor"] > 0, "below_floor": line["below_floor"]})
    out.sort(key=lambda x: (-x["to_bronze"], x["name"] or ""))
    return out


def snapshot_rescue(today):
    """Called by the nightly job: freezes the list on day 10 and day 20."""
    if today.day not in (10, 20):
        return False
    mk = month_of(today)
    db.save_rescue(mk, today.day, rescue(mk, today), HOST.require("now")().isoformat(timespec="seconds"))
    return True
