# -*- coding: utf-8 -*-
"""
monthly.diagnose — the S8 report. Numbers only; no proposals live in this file.

PURE: everything arrives as arguments, so the report can be checked on
hand-written portfolios exactly like the engine can. data.collect() does the
live pull and hands it in.

THE HEADLINE COMES FIRST AND ALONE: what fraction of the units forecast above
85% occupancy in the target month. That single number decides the feature's
scope, because the price band at 95% occupancy is a few hundred riyals wide —
too thin to run a product on. "Monthly does not apply to those units" is a real
answer, not a failure, and it should not have to be dug out of a table.
"""

from . import attrs, engine

# ─────────────────── PREDICTIONS, RECORDED BEFORE THE DATA ───────────────────
# Written 2026-08-19, before the endpoint had ever run against Hostaway. If the
# numbers arrive and we rationalise whatever they say, the diagnosis is worth
# nothing; a prediction on record makes a surprise visible AS a surprise.
#
# The sharpest one is CEILING_TRACKS_HIGH_OCC. With nothing scored every
# quality_mult is 1.0, so the ceiling binds when occ_pool x (adr_pool/adr_unit)
# exceeds (1 - d) = 0.85. For a unit priced near its pool that is simply
# "occupancy above 85%". So the ceiling-bound share should land close to the
# >85% share. If it does not, ADR dispersion inside the pools is doing more work
# than expected, and that is a finding in itself.

PREDICTIONS = {
    "stated_on": "2026-08-19",
    "stated_before_any_live_run": True,
    "pct_above_85": {
        "2026-08": [0.10, 0.25],   # summer trough: Riyadh empties
        "2026-10": [0.30, 0.50],   # a strong ordinary month
        "2027-01": [0.55, 0.75],   # Riyadh Season
        "why": "CLAUDE.md targets ~95% ex-Ramadan, but a target is not a realized "
               "figure, and the seasonal swing should dominate the unit spread",
    },
    "ceiling_bound_share_tracks_pct_above_85": {
        "within": 0.15,
        "why": "with nothing scored, qmult is 1.0 everywhere, so the ceiling "
               "binds at occ > 0.85 for any unit priced near its pool",
    },
    "floor_ratio": {
        "median": [0.82, 0.92],
        "spread_within_a_band": [0.0, 0.05],
        "falls_with_occupancy": True,
    },
    "units_with_own_history": {
        "share": [0.70, 0.90],
        "why": "3 same-months back, and one 10-night booking clears MIN_OWN_OBS=8; "
               "the shortfall should be new units and units that sat empty",
    },
    "loss_making_nightly": {"count": [0, 0],
                            "why": "real ADRs are far above the synthetic 120 that "
                                   "produced the clamped case"},
    "no_price_band_closed": {"count": [0, 3],
                             "why": "only reachable near 100% occupancy"},
}



def _pct(n, d):
    return (n / float(d)) if d else 0.0


def _segmented_or_suppressed(results, no_price, fallback, own, n):
    """Suppress whenever the TRUST CHECK fails — not only when units are missing.

    The first version only suppressed above 40% no-price, so a run that was 68%
    priced from district pools printed "*** NOT TRUSTWORTHY ***" at the top and
    then a confident "model_is_a_low_occupancy_tool" underneath it. Those two
    lines cannot both be true, and the second is the one people quote.
    """
    seg = engine.segmented_report(results)
    reason = None
    if n and _pct(no_price, n) > 0.40:
        reason = ("%d of %d units returned no price" % (no_price, n))
    elif n and _pct(own, n) < 0.60:
        reason = ("only %d of %d units priced from their own history — %d came "
                  "from district pools" % (own, n, fallback))
    if reason:
        seg["verdict_suppressed"] = True
        seg["verdict_would_have_been"] = seg.get("verdict")
        seg["verdict"] = ("SUPPRESSED — %s, so any verdict here would describe "
                          "the sample, not the portfolio" % reason)
    else:
        seg["verdict_suppressed"] = False
    return seg


def _trust_warnings(own, fallback, no_price, n):
    out = []
    if not n:
        return out
    if _pct(fallback, n) > 0.40:
        out.append({
            "kind": "on_fallback",
            "text": "MOST UNITS ARE PRICED FROM DISTRICT POOLS — the distribution "
                    "describes the pools, not these units",
            "count": fallback})
    if _pct(no_price, n) > 0.40:
        out.append({
            "kind": "no_price",
            "text": "MOST UNITS RETURNED NO PRICE AT ALL — they are absent from "
                    "the distribution, so the percentages below are shares of the "
                    "few that priced, not of the portfolio",
            "count": no_price})
    if _pct(own, n) < 0.60 and not out:
        out.append({
            "kind": "thin_own_history",
            "text": "fewer than 60% of units priced from their own history",
            "count": own})
    return out


def run(units, cost_set=None, today=None):
    """`units` = [{lid, name, own, district_pool, bedroom_pool, attr_values,
    ejar_row, adr_pool, occ_pool}] — everything already gathered."""
    c = cost_set or engine.costs()
    results, rows_for_sweep, per_unit = [], [], []

    for u in (units or []):
        p = engine.price_unit(
            u.get("lid"), u.get("month"), own=u.get("own"),
            district=u.get("district_pool"), bedroom=u.get("bedroom_pool"),
            attr_values=u.get("attr_values") or {}, cost_set=c,
            ejar_row=u.get("ejar_row"), today=today)
        results.append(p)
        d = p.get("data") or {}
        nightly = (p.get("floor_detail") or {}).get("nightly") or {}
        per_unit.append({
            "lid": u.get("lid"), "name": u.get("name"),
            "occ": d.get("occ"), "adr": d.get("adr"),
            "band": engine.occupancy_band(d.get("occ")),
            "bound_by": p.get("bound_by"), "price": p.get("price"),
            "floor": (p.get("gates") or {}).get("floor"),
            "model": (p.get("gates") or {}).get("model"),
            "ceiling": (p.get("gates") or {}).get("ceiling"),
            "nightly_net": nightly.get("nightly_net"),
            "nightly_gross": nightly.get("nightly_gross"),
            "basis": p.get("basis"), "confidence": p.get("confidence"),
            "warnings": p.get("warnings") or [],
            # THE CORRECTION FROM THE PREVIOUS STAGE, carried into the output so
            # a bound_by count can never be read as evidence about the model when
            # it is evidence about the unit: with quality_mult at 1.0 the model
            # gate is simply the POOL AVERAGE, so a unit comes out model-bound
            # purely by under-earning its pool, with no quality involved at all.
            "model_bound_means": (
                "under_earns_its_pool"
                if p.get("bound_by") == "model"
                and abs(((p.get("quality") or {}).get("mult") or 1.0) - 1.0) < 1e-9
                else None),
        })
        if d.get("adr") is not None and u.get("adr_pool") and u.get("occ_pool"):
            rows_for_sweep.append({"adr_unit": d.get("adr"),
                                   "adr_pool": u.get("adr_pool"),
                                   "occ_pool": u.get("occ_pool")})

    n = len(per_unit)
    high = [r for r in per_unit if r["band"] == ">85"]
    priced = [r for r in per_unit if r["price"] is not None]
    unscored = sum(1 for u in (units or []) if not (u.get("attr_values") or {}))

    # THE FAILURE THAT WOULD LOOK LIKE A FINDING. If most units have too little
    # same-month history and fall back to the district pool, the distribution
    # describes the POOL, not the portfolio — and it reads like a clean answer
    # because every unit still gets a number. So the split sits next to the
    # headline, not buried in the per-unit table.
    own_hist = [r for r in per_unit if r["basis"] == "own_history"]
    fallback = [r for r in per_unit if r["basis"] in ("district_pool", "bedroom_pool")]
    none_at_all = [r for r in per_unit if r["basis"] == "insufficient"]

    return {
        # ── the headline, on its own ──
        "predictions": PREDICTIONS,
        "headline": {
            "n_units": n,
            "n_above_85": len(high),
            "pct_above_85": _pct(len(high), n),
            "band_at_95_note": "the price band at 95% occupancy is a few hundred SAR",
            # read these two before reading anything else
            "units_with_own_history": len(own_hist),
            "units_on_fallback": len(fallback),
            "units_with_no_price": len(none_at_all),
            "pct_own_history": _pct(len(own_hist), n),
            "pct_on_fallback": _pct(len(fallback), n),
            "pct_no_price": _pct(len(none_at_all), n),
            "trustworthy": _pct(len(own_hist), n) >= 0.60,
            # TWO DIFFERENT FAILURES THAT MEAN OPPOSITE THINGS, and the first
            # version of this printed the same sentence for both. On fallback:
            # every unit got a number, but the numbers describe district pools.
            # No price: the unit got nothing, so it is absent from the
            # distribution entirely and the denominator is the lie. The warning
            # now names whichever actually happened.
            "warnings": _trust_warnings(len(own_hist), len(fallback),
                                        len(none_at_all), n),
        },
        "bands": {b: sum(1 for r in per_unit if r["band"] == b)
                  for b in engine.OCC_BANDS + ("unknown",)},
        # THE VERDICT IS SUPPRESSED WHILE THE TRUST CHECK IS FAILING. It was
        # reading data completeness as seasonality: January said "inconclusive"
        # only because 41 units matched where August matched 20. A conclusion
        # drawn from a sample we already know is broken is worse than no
        # conclusion, because it looks like a finding.
        "segmented": _segmented_or_suppressed(results, len(none_at_all),
                                              len(fallback), len(own_hist), n),
        "floor_ratio": engine.floor_ratio_report(results),
        "floor_ratio_by_band": {
            b: engine.floor_ratio_report(
                [p for p, r in zip(results, per_unit) if r["band"] == b])
            for b in engine.OCC_BANDS},
        "sensitivity": engine.sensitivity_sweep(rows_for_sweep, cost_set=c),
        "clamp": engine.clamp_report(results),
        "anchor": attrs.median_report([u.get("attr_values") or {} for u in (units or [])]),
        "anchor_is_empty": unscored == n,
        "n_unscored": unscored,
        # ── the sweep the owner asked for two stages ago ──
        "loss_making_nightly": [r for r in per_unit
                                if r["nightly_net"] is not None and r["nightly_net"] <= 0],
        "no_price": [r for r in per_unit if r["price"] is None],
        "band_widths": [
            {"lid": r["lid"], "width": (r["ceiling"] - r["floor"])}
            for r in per_unit
            if r["ceiling"] is not None and r["floor"] is not None],
        "per_unit": per_unit,
        "n_priced": len(priced),
        "turnover_cost_used": c["turnover_cost_sar"],
    }


def render_text(multi):
    """A compact, pasteable summary. The full JSON is 53 units x N months and is
    unreadable in a terminal; this is the part a human actually reads, with the
    two trust numbers first because everything else is conditional on them."""
    L = []
    A = L.append
    A("=" * 68)
    A("  MONTHLY PRICING DIAGNOSIS")
    A("=" * 68)

    p = PREDICTIONS
    A("")
    A("  PREDICTIONS ON RECORD (stated %s, before any live run)" % p["stated_on"])
    for m in ("2026-08", "2026-10", "2027-01"):
        if m in p["pct_above_85"]:
            lo, hi = p["pct_above_85"][m]
            A("    %s  pct_above_85 predicted %.0f-%.0f%%" % (m, lo * 100, hi * 100))
    A("    ceiling-bound share should track pct_above_85 within %.0f pts"
      % (p["ceiling_bound_share_tracks_pct_above_85"]["within"] * 100))
    A("    units_with_own_history predicted %.0f-%.0f%%"
      % (p["units_with_own_history"]["share"][0] * 100,
         p["units_with_own_history"]["share"][1] * 100))

    A("")
    A("  TRUST CHECK FIRST — everything below is conditional on this")
    A("  " + "-" * 64)
    for r in multi.get("months") or []:
        if r.get("error"):
            A("    %s  ERROR: %s" % (r.get("month"), r["error"]))
            continue
        h = r.get("headline") or {}
        A("    %s   %s" % (r.get("month"),
                             "OK" if h.get("trustworthy") else "*** NOT TRUSTWORTHY ***"))
        A("        own history  %3d / %-3d (%.0f%%)   priced from this unit's own record"
          % (h.get("units_with_own_history", 0), h.get("n_units", 0),
             (h.get("pct_own_history") or 0) * 100))
        A("        on fallback  %3d / %-3d (%.0f%%)   priced from a district/bedroom pool"
          % (h.get("units_on_fallback", 0), h.get("n_units", 0),
             (h.get("pct_on_fallback") or 0) * 100))
        A("        NO PRICE     %3d / %-3d (%.0f%%)   absent from the distribution entirely"
          % (h.get("units_with_no_price", 0), h.get("n_units", 0),
             (h.get("pct_no_price") or 0) * 100))
        for w in (h.get("warnings") or []):
            A("        !! %s" % w["text"])
        j = r.get("join") or {}
        if j:
            A("        join: %s active listings, %s with a district (%s from KB), "
              "%s with bedrooms, %s matched a reservation"
              % (j.get("listings_active"), j.get("with_district"),
                 j.get("district_from_kb"), j.get("with_bedrooms"),
                 j.get("units_matching_a_reservation")))
            A("        pools built: %s district, %s bedroom"
              % (j.get("district_pools"), j.get("bedroom_pools")))

    A("")
    A("  HEADLINE — share of units forecasting above 85% occupancy")
    A("  " + "-" * 64)
    A("    month      units   >85%     ceiling-bound   floor/gross   no-price")
    for c in multi.get("compare") or []:
        if c.get("error"):
            continue
        mrow = next((x for x in (multi.get("months") or [])
                     if x.get("month") == c.get("month")), {})
        n = (mrow.get("headline") or {}).get("n_units", 0)
        A("    %-9s  %5d  %5.0f%%   %11.0f%%   %11s   %8d"
          % (c.get("month"), n, (c.get("pct_above_85") or 0) * 100,
             (c.get("ceiling_share") or 0) * 100,
             ("%.3f" % c["floor_ratio_median"]) if c.get("floor_ratio_median") else "—",
             c.get("no_price") or 0))

    for r in multi.get("months") or []:
        if r.get("error"):
            continue
        A("")
        A("  %s" % r.get("month"))
        A("  " + "-" * 64)
        seg = r.get("segmented") or {}
        A("    band     n   floor  model  ceiling  no-price   floor/gross")
        for b in engine.OCC_BANDS:
            br = (seg.get("bands") or {}).get(b) or {}
            if not br.get("n"):
                continue
            k = br["counts"]
            fr = ((r.get("floor_ratio_by_band") or {}).get(b) or {}).get("median")
            A("    %-7s %3d  %5d  %5d  %7d  %8d   %11s"
              % (b, br["n"], k["floor"], k["model"], k["ceiling"], k["no_price"],
                 ("%.3f" % fr) if fr else "—"))
        A("    verdict: %s" % seg.get("verdict"))
        fn = r.get("funnel") or {}
        if fn:
            A("    reservation funnel: read %s -> kept %s   (drops below are"
              " EXPECTED, not losses)" % (fn.get("read"), fn.get("kept")))
            _why = {
                "dropped_not_confirmed": "inquiries, cancellations, declines — not bookings",
                "dropped_no_listing_id": "*** UNEXPECTED — investigate ***",
                "dropped_bad_dates": "*** UNEXPECTED — investigate ***",
                "dropped_no_price": "zero-price rows (owner blocks etc.)",
                "dropped_no_nights_in_month": "arrived in the 45-day pad, left before the month began",
            }
            for k in ("dropped_not_confirmed", "dropped_no_listing_id",
                      "dropped_bad_dates", "dropped_no_price",
                      "dropped_no_nights_in_month"):
                if fn.get(k):
                    A("        %-30s %-6s %s" % (k, fn[k], _why.get(k, "")))
            ss = fn.get("status_seen") or {}
            if ss:
                A("        statuses seen: %s"
                  % ", ".join("%s=%d" % (k, v) for k, v in
                              sorted(ss.items(), key=lambda x: -x[1])[:8]))
            lt = fn.get("listing_id_types") or {}
            if lt:
                A("        listingMapId types: %s"
                  % ", ".join("%s=%d" % (k, v) for k, v in lt.items()))
        lm = r.get("loss_making_nightly") or []
        A("    loss-making nightly: %d    band-closed/no-price: %d"
          % (len(lm), len(r.get("no_price") or [])))
        A("    turnover cost used: %s SAR  (%s)"
          % (r.get("turnover_cost_used"), r.get("turnover_cost_source")))
        A("    reservations read: %s   partial months dropped: %s"
          % (r.get("n_reservations_read"), r.get("partial_months_dropped")))
        if r.get("anchor_is_empty"):
            A("    anchor: EMPTY — %d units unscored, so every quality_mult is 1.0"
              % r.get("n_unscored", 0))
        cl = r.get("clamp") or {}
        A("    quality clamp: %d/%d at 1.60 (%.0f%%)%s"
          % (cl.get("clamped", 0), cl.get("n", 0), (cl.get("rate") or 0) * 100,
             "  ANCHOR SUSPECT" if cl.get("anchor_suspect") else ""))
        for row in (r.get("no_price") or [])[:8]:
            A("      no price: %s (%s) occ %s floor %s ceiling %s  %s"
              % (row.get("name"), row.get("lid"),
                 # None is NOT 0.00. Printing it as 0.00 made "no forecast" read
                 # as "zero reservations found", which sent a diagnosis chasing a
                 # data-matching bug that was really a missing-metadata bug.
                 ("%.2f" % row["occ"]) if row.get("occ") is not None else "  —",
                 int(row["floor"]) if row.get("floor") else "—",
                 int(row["ceiling"]) if row.get("ceiling") else "—",
                 ",".join(row.get("warnings") or [])))

    A("")
    A("=" * 68)
    return "\n".join(L)
