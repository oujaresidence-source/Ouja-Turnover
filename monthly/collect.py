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


def diagnose(month, today=None, unit_meta=None, years=None):
    """The full S8 report for one target month. Read-only end to end.

    unit_meta is passed in when several months are run together: it paginates
    the whole Hostaway listings API and does not change between months, so
    rebuilding it per month tripled the request for nothing. That, plus a third
    year of history worth a 0.028 freshness weight, is what pushed this past
    Railway's proxy timeout and produced an "Application failed to respond" page
    on a service the dashboard showed as Online.
    """
    today = today or (HOST.now().date() if HOST.now else datetime.date.today())
    today_key = data.month_key(today)

    reservations = data.fetch_history(month, today=today, years_back=years)
    if unit_meta is None:
        unit_meta = data.listing_meta(HOST.require("api_get"), _kb_district_lookup())

    funnel = {}
    all_rows = data.unit_month_rows(reservations, int(month[5:7]), today_key,
                                    funnel=funnel)
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
    rep["funnel"] = funnel
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


def trace(lid, month, today=None, windows=1):
    """Every step for ONE unit, so a join failure can be seen rather than
    inferred. Read-only.

    ONE window by default. The first version pulled four years of history plus
    the full listings pagination before answering, and Railway's proxy gave up
    before the app did — an "Application failed to respond" page that looks like
    a crash and is really a slow query. A trace is a question about one unit; it
    does not need the whole corpus to answer.
    """
    today = today or (HOST.now().date() if HOST.now else datetime.date.today())
    lid = int(lid)
    reservations = data.fetch_history(month, today=today, max_windows=windows)
    mine = [r for r in reservations if str(r.get("listingMapId")) == str(lid)]
    unit_meta = data.listing_meta(HOST.require("api_get"), _kb_district_lookup())
    unit_funnel = {}
    data.unit_month_rows(mine, int(month[5:7]), data.month_key(today),
                         funnel=unit_funnel)
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
        "windows_pulled": windows,
        "note": ("one history window only, for speed — add &windows=4 for the "
                 "full picture if this returns quickly"),
        "in_listing_map": lid in unit_meta,
        "listing_meta": unit_meta.get(lid),
        "reservations_in_window_total": len(reservations),
        "reservations_matching_this_lid": len(mine),
        "sample": steps,
        "funnel_for_this_unit": unit_funnel,
        "observations_built": rows.get(lid) or [],
        "observations_after_partial_drop": [o for o in (rows.get(lid) or [])
                                            if not o.get("partial")],
        "min_own_obs_required": engine.MIN_OWN_OBS,
        "own_nights_total": sum(o.get("nights") or 0
                                for o in (rows.get(lid) or [])
                                if not o.get("partial")),
    }


def diagnose_months(months, today=None, years=None):
    """Several target months side by side. One month is not the answer: the
    question is whether occupancy leaves room for a monthly band, and that moves
    far more by season than by unit.

    The listings pull is hoisted OUT of the loop — it is identical for every
    month and paginating it three times was pure waste on the slowest call in
    the request."""
    out = []
    try:
        shared_meta = data.listing_meta(HOST.require("api_get"), _kb_district_lookup())
    except Exception:
        shared_meta = None
    for m in [x.strip() for x in str(months or "").split(",") if x.strip()]:
        try:
            out.append(diagnose(m, today=today, unit_meta=shared_meta, years=years))
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


# ─────────────────────────── the page's data layer ───────────────────────────
#
# Pricing ONE unit still needs its district pool, which needs every unit's
# history for that month — so the cheap-looking question costs the same as the
# expensive one. The month is computed once and held briefly, which is what makes
# the page feel like a page instead of a report generator.

_CACHE = {}
_CACHE_TTL = 900          # seconds


def _now_ts():
    import time
    return time.time()


def month_state(month, force=False, today=None):
    hit = _CACHE.get(month)
    if hit and not force and (_now_ts() - hit["at"]) < _CACHE_TTL:
        return hit
    today = today or (HOST.now().date() if HOST.now else datetime.date.today())
    today_key = data.month_key(today)

    reservations = data.fetch_history(month, today=today)
    unit_meta = data.listing_meta(HOST.require("api_get"), _kb_district_lookup())

    all_rows = data.unit_month_rows(reservations, int(month[5:7]), today_key)
    unit_rows = {lid: [r for r in rows if not r.get("partial")]
                 for lid, rows in all_rows.items()}

    dpool, bpool = data.pool_rows(unit_rows, unit_meta,
                                  lambda m: m.get("district"),
                                  lambda m: m.get("bedrooms"))
    tc, tc_source = data.turnover_cost_sar(
        engine.DEFAULT_COSTS["turnover_cost_sar"], HOST.load_json)

    st = {"at": _now_ts(), "month": month, "today": today.isoformat(),
          "unit_meta": unit_meta, "unit_rows": unit_rows,
          "dpool": dpool, "bpool": bpool,
          "cost_set": engine.costs(turnover_cost_sar=tc),
          "turnover_cost_source": tc_source}
    _CACHE[month] = st
    return st


def cached_month(month):
    """The month state ONLY if it is already warm. Never computes.

    month_state() pulls years of Hostaway history and paginates the listings API.
    That is fine on an admin screen where someone chose to wait; it is a hazard
    on a guest page, where it would put a 30-60 second Hostaway round trip in
    front of a customer looking at apartments. The guest path uses this and
    nothing else."""
    hit = _CACHE.get(month)
    if hit and (_now_ts() - hit["at"]) < _CACHE_TTL:
        return hit
    return None


def price_one_cached(lid, month):
    """A price for the guest site, or None. O(1) against a warm cache, and
    silent otherwise — never a computation, never a network call."""
    st = cached_month(month)
    if not st:
        return None
    lid = int(lid)
    if lid not in st["unit_meta"]:
        return None
    return price_one(lid, month)


def price_one(lid, month, force=False, today=None):
    """The full explainability payload for ONE unit — the same object the page
    renders and the PDF renders, so the screen and the document cannot drift."""
    st = month_state(month, force=force, today=today)
    lid = int(lid)
    meta = st["unit_meta"].get(lid) or {}
    d, b = meta.get("district"), meta.get("bedrooms")
    dp = st["dpool"].get((d, b)) or []
    bp = st["bpool"].get(b) or []
    p = engine.price_unit(
        lid, month, own=st["unit_rows"].get(lid) or [],
        district=dp, bedroom=bp, attr_values=db.unit_attrs(lid),
        cost_set=st["cost_set"],
        ejar_row=db.ejar_latest(d, bedrooms=b) if d and b else None,
        paired_obs=db.paired_obs_count(), today=st["today"])
    p["name"] = meta.get("name")
    p["public_name"] = meta.get("public_name")
    p["district"] = d
    p["district_source"] = meta.get("district_source")
    p["bedrooms"] = b
    p["turnover_cost_source"] = st["turnover_cost_source"]
    p["saved_quote"] = db.latest_quote(lid, month)
    p["pooled_range"] = pooled_range(p, st, meta)
    return p


def _pctile(vals, q):
    """Nearest-rank percentile. No numpy, no interpolation games."""
    if not vals:
        return None
    xs = sorted(vals)
    i = int(round(q * (len(xs) - 1)))
    return xs[max(0, min(i, len(xs) - 1))]


def pooled_range(p, st, meta):
    """A RANGE for a unit priced from a pool, not a point.

    A pool average repeated as an identical point price on fifteen rows implies a
    precision the pool does not have — and the repetition makes that obvious to
    anyone reading the page, which is worse than admitting it up front. So a
    pooled unit is priced at the pool's 25th and 75th percentile ADR and shown as
    the band between them.

    Computed by re-running the real engine at both ends rather than scaling the
    midpoint: the floor is not linear in ADR (the monthly running costs are
    fixed), so a scaled band would be wrong at exactly the edges it exists to
    describe.
    """
    if p.get("basis") not in ("district_pool", "bedroom_pool"):
        return None
    d, b = meta.get("district"), meta.get("bedrooms")
    rows = (st["dpool"].get((d, b)) if p["basis"] == "district_pool"
            else st["bpool"].get(b)) or []
    adrs = [r.get("adr") for r in rows if r.get("adr")]
    if len(adrs) < 4:
        return None
    occ = (p.get("data") or {}).get("occ")
    lo_adr, hi_adr = _pctile(adrs, 0.25), _pctile(adrs, 0.75)
    if not lo_adr or not hi_adr or hi_adr <= lo_adr:
        return None
    out = []
    for adr in (lo_adr, hi_adr):
        synthetic = [{"adr": adr, "occ": occ, "months_old": 0, "nights": 30}]
        q = engine.price_unit(p.get("unit_id"), p.get("month"), own=[],
                              district=synthetic, bedroom=[],
                              attr_values={}, cost_set=st["cost_set"])
        out.append(q.get("price"))
    if out[0] is None or out[1] is None:
        return None
    lo, hi = min(out), max(out)
    return {"low": lo, "high": hi, "n_pool": len(adrs)} if hi > lo else None


def units_report(month, force=False, today=None):
    """Every unit, its price, what bound it, and — when there is no price — the
    stated reason rather than a blank."""
    st = month_state(month, force=force, today=today)
    rows = []
    for lid in sorted(st["unit_meta"]):
        p = price_one(lid, month, today=today)
        rows.append({
            "lid": lid, "name": p.get("name"),
            "public_name": p.get("public_name"), "district": p.get("district"),
            "bedrooms": p.get("bedrooms"),
            "price": p.get("price"), "bound_by": p.get("bound_by"),
            "confidence": p.get("confidence"), "basis": p.get("basis"),
            "own_obs": (p.get("data") or {}).get("own_obs"),
            "occ": (p.get("data") or {}).get("occ"),
            "gates": p.get("gates"),
            "unanswered": (p.get("quality") or {}).get("unanswered"),
            "warnings": p.get("warnings") or [],
            "no_price_reason": (p.get("warnings") or ["unknown"])[0]
                               if p.get("price") is None else None,
            "is_estimate": p.get("is_estimate"),
            "has_saved_quote": bool(p.get("saved_quote")),
            "pooled_range": p.get("pooled_range"),
            # A model gate computed with every quality_mult at 1.0 is not a
            # model: it is the pool average wearing a different label. The page
            # must not draw it as an independent estimate.
            "model_is_measured": abs(((p.get("quality") or {}).get("mult") or 1.0) - 1.0) > 1e-9,
        })
    priced = [r for r in rows if r["price"] is not None]
    own = [r for r in rows if r["basis"] == "own_history"]
    return {
        "month": month, "rows": rows,
        "n": len(rows), "n_priced": len(priced),
        "n_own_history": len(own),
        "pct_own_history": (len(own) / float(len(rows))) if rows else 0.0,
        "trustworthy": (len(own) / float(len(rows)) if rows else 0) >= 0.60,
        "turnover_cost_source": st["turnover_cost_source"],
        "computed_at": st["at"],
    }
