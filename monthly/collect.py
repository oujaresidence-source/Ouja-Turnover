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


def _kb_district_lookup():
    """listing id -> canonical Arabic district from the knowledge base, which is
    the only place that spelling is curated. Hostaway's `city` is 'Riyadh' for
    every unit, which pools everything together and can never match an Ejar row
    keyed on الملقا. Returns None if the KB is unreachable — a missing district
    is a wider pool, not a crash."""
    try:
        from kb import db as kbdb
        rows = kbdb.all_units(active_only=True) or []
    except Exception:
        return None
    by_code = {}
    for r in rows:
        code = str((r or {}).get("listing_code") or "").strip()
        d = (r or {}).get("district")
        if code and d:
            try:
                by_code[int(code)] = d
            except (TypeError, ValueError):
                continue
    if not by_code:
        return None
    return lambda lid: by_code.get(int(lid))


def diagnose(month, today=None):
    """The full S8 report for one target month. Read-only end to end."""
    today = today or (HOST.now().date() if HOST.now else datetime.date.today())
    today_key = data.month_key(today)

    reservations = data.fetch_history(month, today=today)
    unit_meta = data.listing_meta(HOST.require("api_get"), _kb_district_lookup())

    all_rows = data.unit_month_rows(reservations, int(month[5:7]), today_key)
    unit_rows, dropped_partial = {}, 0
    for lid, rows in all_rows.items():
        keep = [r for r in rows if not r.get("partial")]
        dropped_partial += len(rows) - len(keep)
        unit_rows[lid] = keep

    dpool, bpool = data.pool_rows(unit_rows, unit_meta,
                                  lambda m: m.get("district"),
                                  lambda m: m.get("bedrooms"))

    tc, tc_source = data.turnover_cost_sar(
        engine.DEFAULT_COSTS["turnover_cost_sar"], HOST.load_json)
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
            "ejar_row": db.ejar_latest(d, bedrooms=b) if d and b else None,
            "adr_pool": (pool_f or {}).get("adr"),
            "occ_pool": (pool_f or {}).get("occ"),
        })

    rep = _diag.run(units, cost_set=cost_set, today=today.isoformat())
    rep["turnover_cost_source"] = tc_source
    rep["month"] = month
    rep["n_reservations_read"] = len(reservations)
    rep["partial_months_dropped"] = dropped_partial
    # The join, made auditable: how many listings, how many carried the metadata
    # the pools are keyed on, and how many actually matched a reservation.
    rep["join"] = {
        "listings_active": len(unit_meta),
        "with_district": sum(1 for m in unit_meta.values() if m.get("district")),
        "with_bedrooms": sum(1 for m in unit_meta.values() if m.get("bedrooms")),
        "district_from_kb": sum(1 for m in unit_meta.values()
                                if m.get("district_source") == "kb"),
        "units_matching_a_reservation": sum(1 for lid in unit_meta if unit_rows.get(lid)),
        "reservation_lids_not_in_listings": sorted(
            set(unit_rows) - set(unit_meta))[:20],
        "district_pools": len(dpool), "bedroom_pools": len(bpool),
    }
    return rep


def trace(lid, month, today=None):
    """Every step for ONE unit, so a join failure can be seen rather than
    inferred. Read-only."""
    today = today or (HOST.now().date() if HOST.now else datetime.date.today())
    lid = int(lid)
    reservations = data.fetch_history(month, today=today)
    mine = [r for r in reservations if str(r.get("listingMapId")) == str(lid)]
    unit_meta = data.listing_meta(HOST.require("api_get"), _kb_district_lookup())
    rows = data.unit_month_rows(reservations, int(month[5:7]), data.month_key(today))
    steps = []
    for r in mine[:25]:
        steps.append({
            "id": r.get("id"), "status": r.get("status"),
            "confirmed": data.is_confirmed(r),
            "arrival": r.get("arrivalDate"), "departure": r.get("departureDate"),
            "totalPrice": r.get("totalPrice"),
            "listingMapId": r.get("listingMapId"),
            "listingMapId_type": type(r.get("listingMapId")).__name__,
        })
    return {
        "lid": lid, "month": month,
        "in_listing_map": lid in unit_meta,
        "listing_meta": unit_meta.get(lid),
        "reservations_in_window_total": len(reservations),
        "reservations_matching_this_lid": len(mine),
        "sample": steps,
        "observations_built": rows.get(lid) or [],
        "observations_after_partial_drop": [o for o in (rows.get(lid) or [])
                                            if not o.get("partial")],
        "min_own_obs_required": None,
    }


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
