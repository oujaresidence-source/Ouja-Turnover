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


def _imported_rows(unit_meta):
    """The uploaded export, joined to listing ids by name. None when nothing has
    been uploaded, which keeps the live path exactly as it was."""
    from . import importer
    try:
        blob = HOST.load_json("monthly_reservations.json", None) if HOST.load_json else None
    except Exception:
        blob = None
    if not blob or not blob.get("rows"):
        return None
    rows, unmatched = importer.attach_listing_ids(blob["rows"], unit_meta)
    if unmatched:
        print("[monthly] import: %d listing names had no match: %s"
              % (len(unmatched), list(unmatched)[:6]))
    return rows or None


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

    Reuses month_state rather than rebuilding the pipeline beside it: two copies
    of the same assembly is how a report and a screen end up disagreeing about
    the same unit, and the backtest that chooses the fallback ladder lives in
    month_state.
    """
    today = today or (HOST.now().date() if HOST.now else datetime.date.today())
    st = month_state(month, force=True, today=today)

    units = []
    for lid, meta in st["unit_meta"].items():
        d, b = meta.get("district"), meta.get("bedrooms")
        dp = st["dpool"].get((d, b)) or []
        bp = st["bpool"].get(b) or []
        pool_f = engine.forecast(dp) or engine.forecast(bp)
        units.append({
            "lid": lid, "name": meta.get("name"),
            "public_name": meta.get("public_name"), "month": month,
            "own": st["unit_rows"].get(lid) or [],
            "district_pool": dp, "bedroom_pool": bp,
            "attr_values": db.unit_attrs(lid),
            "ejar_row": db.ejar_latest(d, bedrooms=b) if d and b else None,
            "adr_pool": (pool_f or {}).get("adr"),
            "occ_pool": (pool_f or {}).get("occ"),
            "own_all": (st.get("all_obs") or {}).get(lid) or [],
            "rung2": st.get("rung2"), "factors": st.get("factors"),
            "portfolio": st.get("portfolio") or [],
        })

    rep = _diag.run(units, cost_set=st["cost_set"], today=st["today"])
    rep["turnover_cost_source"] = st["turnover_cost_source"]
    rep["month"] = month
    rep["n_reservations_read"] = st.get("n_reservations_read", 0)
    rep["partial_months_dropped"] = st.get("dropped_partial", 0)
    rep["funnel"] = st.get("funnel") or {}
    rep["backtest"] = st.get("backtest")
    rep["rung2"] = st.get("rung2")
    rep["join"] = {
        "listings_active": len(st["unit_meta"]),
        "with_district": sum(1 for m in st["unit_meta"].values() if m.get("district")),
        "with_bedrooms": sum(1 for m in st["unit_meta"].values() if m.get("bedrooms")),
        "district_from_kb": sum(1 for m in st["unit_meta"].values()
                                if m.get("district_source") == "kb"),
        "units_matching_a_reservation": sum(1 for lid in st["unit_meta"]
                                            if st["unit_rows"].get(lid)),
        "units_with_any_recent_history": sum(1 for lid in st["unit_meta"]
                                             if (st.get("all_obs") or {}).get(lid)),
        "reservation_lids_not_in_listings": sorted(
            set(st["unit_rows"]) - set(st["unit_meta"]))[:20],
        "district_pools": len(st["dpool"]), "bedroom_pools": len(st["bpool"]),
    }
    return rep


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

    unit_meta = data.listing_meta(HOST.require("api_get"), _kb_district_lookup())

    # AN UPLOADED EXPORT WINS OVER THE API. It is complete, it has no arrival
    # window, and it cannot time out — which is the entire reason this feature
    # kept taking pages down. The live pull stays as the fallback for when no
    # file has been uploaded yet.
    imported = _imported_rows(unit_meta)
    if imported is not None:
        reservations = imported
        recent_res = imported
    else:
        reservations = data.fetch_history(month, today=today)
        recent_res = data.fetch_recent(today=today)

    # The recent corpus: every month of the last year, for every unit. This is
    # what lets a unit with no Augusts still be described by its own record.
    seen = {r.get("id") for r in reservations}
    merged = list(reservations) + [r for r in recent_res if r.get("id") not in seen]
    all_obs = data.unit_month_rows_all(merged, today_key)

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

    # WHICH RUNG WINS IS DECIDED BY THE CORPUS, not by preference. Every real
    # unit-month is held out in turn and each method scored against it; the
    # cheapest median error that is not rung 1 becomes rung 2.
    def _pool_of(lid):
        m = unit_meta.get(lid) or {}
        d, b = m.get("district"), m.get("bedrooms")
        pool = []
        for other, rows in all_obs.items():
            if other == lid:
                continue
            om = unit_meta.get(other) or {}
            if om.get("bedrooms") == b and (d is None or om.get("district") == d):
                pool.extend(rows)
        return pool

    bt = engine.backtest_methods(all_obs, all_obs, _pool_of)
    factors = engine.seasonal_factors(all_obs)

    # The last-resort pool: every unit that has data for this month, whatever its
    # size or district. A unit whose bedroom count Hostaway never recorded had no
    # pool at all and therefore no price — this is the difference between "we
    # cannot compare it" and "we will not answer".
    portfolio = [o for rows in unit_rows.values() for o in rows]

    st = {"at": _now_ts(), "month": month, "today": today.isoformat(),
          "unit_meta": unit_meta, "unit_rows": unit_rows, "all_obs": all_obs,
          "dpool": dpool, "bpool": bpool, "portfolio": portfolio,
          "backtest": bt, "rung2": bt.get("rung2"), "factors": factors,
          "funnel": funnel, "dropped_partial": dropped_partial,
          "n_reservations_read": len(merged),
          "cost_set": engine.costs(turnover_cost_sar=tc),
          "turnover_cost_source": tc_source}
    _CACHE[month] = st
    return st


# ─────────────────────────── never block a request ───────────────────────────
#
# month_state() reads years of Hostaway history and paginates the listings API.
# Every screen needed it, so every screen could hang, and Railway's proxy gave up
# before the app did — an "Application failed to respond" page on a service that
# was merely busy. Three separate outages came from this one shape.
#
# So NO request computes any more. A request either finds the month warm and
# answers instantly, or it starts the work in a background thread and answers
# "computing" — and the page waits visibly instead of the browser dying quietly.

_JOBS = {}
_JOBS_LOCK = __import__("threading").Lock()
_JOB_STALE = 600          # a job older than this is presumed dead and may restart


def ensure_month(month):
    """Warm the month WITHOUT blocking. Returns 'ready', 'running' or 'error'."""
    import threading
    if cached_month(month):
        return "ready"
    with _JOBS_LOCK:
        j = _JOBS.get(month)
        if j and j.get("state") == "running" and (_now_ts() - j["started"]) < _JOB_STALE:
            return "running"
        _JOBS[month] = {"state": "running", "started": _now_ts(), "error": None}

    def _work():
        try:
            month_state(month, force=True)
            with _JOBS_LOCK:
                _JOBS[month] = {"state": "ready", "started": _now_ts(), "error": None}
        except Exception as e:
            with _JOBS_LOCK:
                _JOBS[month] = {"state": "error", "started": _now_ts(),
                                "error": "%s: %s" % (type(e).__name__, e)}
            print("[monthly] month_state failed for %s: %s" % (month, e))

    threading.Thread(target=_work, name="monthly-%s" % month, daemon=True).start()
    return "running"


def month_status(month):
    if cached_month(month):
        return {"state": "ready", "error": None}
    with _JOBS_LOCK:
        j = _JOBS.get(month)
    if not j:
        return {"state": "cold", "error": None}
    return {"state": j.get("state"), "error": j.get("error")}


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
        paired_obs=db.paired_obs_count(), today=st["today"],
        own_all=(st.get("all_obs") or {}).get(lid) or [],
        rung2=st.get("rung2"), factors=st.get("factors"),
        portfolio=st.get("portfolio") or [])
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
    stated reason rather than a blank. Returns None when the month is not warm:
    the caller answers "computing" rather than making a browser wait."""
    if force:
        month_state(month, force=True, today=today)
    st = cached_month(month)
    if not st:
        return None
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
            "shortfall": p.get("shortfall"),
            "is_estimate": p.get("is_estimate"),
            "has_saved_quote": bool(p.get("saved_quote")),
            "pooled_range": p.get("pooled_range"),
            # A model gate computed with every quality_mult at 1.0 is not a
            # model: it is the pool average wearing a different label. The page
            # must not draw it as an independent estimate.
            "model_is_measured": abs(((p.get("quality") or {}).get("mult") or 1.0) - 1.0) > 1e-9,
        })
    priced = [r for r in rows if r["price"] is not None]
    own = [r for r in rows if r["basis"] in ("own_history", "own_recent",
                                             "own_seasonal")]
    return {
        "month": month, "rows": rows,
        "n": len(rows), "n_priced": len(priced),
        "n_own_history": len(own),
        "pct_own_history": (len(own) / float(len(rows))) if rows else 0.0,
        "trustworthy": (len(own) / float(len(rows)) if rows else 0) >= 0.60,
        "turnover_cost_source": st["turnover_cost_source"],
        "backtest": st.get("backtest"), "rung2": st.get("rung2"),
        "computed_at": st["at"],
    }
