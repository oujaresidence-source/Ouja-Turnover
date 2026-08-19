# -*- coding: utf-8 -*-
"""
monthly.collect — gathers live inputs and hands them to the pure layers.

The seam: data.py reads Hostaway, db.py reads our own tables, diagnose.py and
engine.py do arithmetic on plain dicts. Only this file knows about all three, so
only this file needs credentials to run.
"""

import datetime

from . import data, db, engine
from . import diagnose as _diag
from .host import HOST


def _meta_for(listing):
    return {"district": (listing or {}).get("district"),
            "bedrooms": (listing or {}).get("bedrooms"),
            "name": (listing or {}).get("name")}


def diagnose(month, today=None):
    """The full S8 report for one target month. Read-only end to end."""
    today = today or (HOST.now().date() if HOST.now else datetime.date.today())
    today_key = data.month_key(today)

    reservations = data.fetch_history(month, today=today)
    listings = HOST.require("get_listings_map")() or {}

    unit_meta = {}
    for lid, val in listings.items():
        try:
            lid = int(lid)
        except (TypeError, ValueError):
            continue
        unit_meta[lid] = _meta_for(val if isinstance(val, dict) else {"name": val})

    all_rows = data.unit_month_rows(reservations, int(month[5:7]), today_key)
    unit_rows, dropped_partial = {}, 0
    for lid, rows in all_rows.items():
        keep = [r for r in rows if not r.get("partial")]
        dropped_partial += len(rows) - len(keep)
        unit_rows[lid] = keep
    dpool, bpool = data.pool_rows(unit_rows, unit_meta,
                                  lambda m: m.get("district"),
                                  lambda m: m.get("bedrooms"))

    tc, tc_source = data.turnover_cost_sar(engine.DEFAULT_COSTS["turnover_cost_sar"])
    cost_set = engine.costs(turnover_cost_sar=tc)

    units = []
    for lid, meta in unit_meta.items():
        d, b = meta.get("district"), meta.get("bedrooms")
        dp = dpool.get((d, b)) or []
        bp = bpool.get(b) or []
        pool_f = engine.forecast(dp) or engine.forecast(bp)
        units.append({
            "lid": lid, "name": meta.get("name"), "month": month,
            "own": unit_rows.get(lid) or [],
            "district_pool": dp, "bedroom_pool": bp,
            "attr_values": db.unit_attrs(lid),
            "ejar_row": db.ejar_latest(d, bedrooms=b) if d else None,
            "adr_pool": (pool_f or {}).get("adr"),
            "occ_pool": (pool_f or {}).get("occ"),
        })

    rep = _diag.run(units, cost_set=cost_set, today=today.isoformat())
    rep["turnover_cost_source"] = tc_source
    rep["month"] = month
    rep["n_reservations_read"] = len(reservations)
    rep["partial_months_dropped"] = dropped_partial
    return rep


def diagnose_months(months, today=None):
    """Several target months side by side. One month is not the answer: the
    question is whether occupancy leaves room for a monthly band, and that moves
    far more by season than by unit."""
    out = []
    for m in [x.strip() for x in str(months or "").split(",") if x.strip()]:
        try:
            out.append(diagnose(m, today=today))
        except Exception as e:
            out.append({"month": m, "error": "%s: %s" % (type(e).__name__, e)})
    return {"months": out, "compare": [
        {"month": r.get("month"),
         "pct_above_85": (r.get("headline") or {}).get("pct_above_85"),
         "pct_own_history": (r.get("headline") or {}).get("pct_own_history"),
         "ceiling_share": ((r.get("segmented") or {}).get("overall") or {}).get("ceiling_share"),
         "floor_ratio_median": (r.get("floor_ratio") or {}).get("median"),
         "no_price": len(r.get("no_price") or []),
         "trustworthy": (r.get("headline") or {}).get("trustworthy"),
         "error": r.get("error")}
        for r in out]}
