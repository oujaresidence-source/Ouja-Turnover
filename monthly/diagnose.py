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


def _pct(n, d):
    return (n / float(d)) if d else 0.0


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

    return {
        # ── the headline, on its own ──
        "headline": {
            "n_units": n,
            "n_above_85": len(high),
            "pct_above_85": _pct(len(high), n),
            "band_at_95_note": "the price band at 95% occupancy is a few hundred SAR",
        },
        "bands": {b: sum(1 for r in per_unit if r["band"] == b)
                  for b in engine.OCC_BANDS + ("unknown",)},
        "segmented": engine.segmented_report(results),
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
