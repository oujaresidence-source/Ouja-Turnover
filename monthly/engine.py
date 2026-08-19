# -*- coding: utf-8 -*-
"""
monthly.engine — PURE math for «التسعير الشهري».

No network. No database. No clock. No import of bot.py. Every number produced
here is reachable from a unit test with hand-written inputs, which is the only
reason anyone should believe it. Same discipline as pricecheck/engine.py and
match/engine.py, and the reason those two are trusted.

THE SHAPE OF THE ANSWER (§3)
  1. Forecast what a night actually earns us in THIS unit in THIS calendar month.
  2. Work out what 30 nights of nightly letting nets us after turnovers and
     commission.
  3. FLOOR — the monthly rent that leaves us no worse off than that, plus what
     the monthly path itself costs, plus a margin.
  4. MODEL  — what the unit's own quality says it is worth.        (S5)
  5. GATE   — what the owner must clear to beat their annual lease. (S7)
  6. FINAL  = max of the three, and WHICH ONE won is the explanation.

WHY PER CALENDAR MONTH AND NEVER A YEARLY AVERAGE
Ramadan and the summer trough are real and large in Riyadh. A flat twelve-month
average overprices July and underprices Riyadh Season, and both mistakes reach
an owner as a number they will remember.
"""

# An observation is one unit-month of realized performance: {adr, occ,
# months_old, nights}. `nights` is how many booked nights it rests on — the
# thing that decides whether we know enough to speak.
MIN_OWN_OBS = 8               # booked nights of our own before we trust our own
HALF_LIFE_MONTHS = 6.0        # a six-month-old month counts half as much

# Costs. Every default is deliberately non-zero: a cost that silently defaults to
# zero understates the FLOOR, and understating the floor is the one direction
# this feature must never fail in. These are starting values, overridable from
# monthly_settings; turnover_cost_sar has a real derived source in
# coverage_study (inhouse_per_clean), which data.py feeds in.
DEFAULT_COSTS = {
    "turnover_cost_sar": 140.0,     # one clean, all-in
    "utilities_month": 350.0,       # electricity + water
    "consumables_month": 120.0,     # guest amenities on a monthly stay
    "wifi_month": 150.0,
    "min_margin_sar": 650.0,        # what we require to bother
    "blended_channel_pct": 0.15,    # Airbnb/Booking/Gathern blended host fee
    "alos": 2.9,                    # average length of stay, nights
}


def costs(**overrides):
    """Settings with defaults filled in. Nothing here may be zero or negative:
    alos divides, and the rest would silently lower the floor."""
    c = dict(DEFAULT_COSTS)
    for k, v in (overrides or {}).items():
        if k not in c or v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            c[k] = f
    if c["alos"] <= 0:
        c["alos"] = DEFAULT_COSTS["alos"]
    return c


def freshness_weight(months_old):
    """Half-life decay. Six months ago counts half, a year ago a quarter. Old
    months still speak; they just do not shout."""
    try:
        k = max(0.0, float(months_old))
    except (TypeError, ValueError):
        k = 0.0
    return 0.5 ** (k / HALF_LIFE_MONTHS)


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def forecast(observations):
    """Freshness-weighted ADR and occupancy. None when there is nothing to
    average — never a zero, which would read as a real forecast of nothing."""
    rows = []
    for o in (observations or []):
        adr = _num((o or {}).get("adr"))
        occ = _num((o or {}).get("occ"))
        if adr is None or occ is None or adr <= 0:
            continue
        w = freshness_weight((o or {}).get("months_old", 0))
        if w <= 0:
            continue
        rows.append((adr, min(max(occ, 0.0), 1.0), w))
    if not rows:
        return None
    tot = sum(w for (_a, _o, w) in rows)
    if tot <= 0:
        return None
    return {
        "adr": sum(a * w for (a, _o, w) in rows) / tot,
        "occ": sum(o * w for (_a, o, w) in rows) / tot,
        "n": len(rows),
    }


def _nights(observations):
    return int(sum(_num((o or {}).get("nights")) or 0 for o in (observations or [])))


def forecast_unit(own=None, district=None, bedroom=None, quality_index=1.0):
    """The fallback ladder (§3.1).

        1. our own history for this unit and month
        2. the same (district, bedrooms) pool, scaled by THIS unit's quality
        3. the same bedrooms across all districts, scaled the same way
        4. nothing — and then we say nothing

    A pool average describes the pool. Multiplying by the unit's quality index is
    what makes it a statement about this flat rather than about its neighbours.
    `basis` travels with the number all the way to the screen, because an owner
    is entitled to know whether we are quoting his flat's record or its street's.
    """
    qi = _num(quality_index) or 1.0
    own_nights = _nights(own)

    f = forecast(own)
    if f and own_nights >= MIN_OWN_OBS:
        return {"adr": f["adr"], "occ": f["occ"], "basis": "own_history",
                "own_obs": own_nights, "pool_obs": f["n"], "quality_index": qi}

    for rows, basis in ((district, "district_pool"), (bedroom, "bedroom_pool")):
        pf = forecast(rows)
        if pf:
            return {"adr": pf["adr"] * qi, "occ": pf["occ"], "basis": basis,
                    "own_obs": own_nights, "pool_obs": pf["n"], "quality_index": qi}

    return {"adr": None, "occ": None, "basis": "insufficient",
            "own_obs": own_nights, "pool_obs": 0, "quality_index": qi}


def nightly_economics(adr, occ, cost_set=None):
    """What 30 nights of nightly letting actually nets us (§3.2)."""
    c = cost_set or costs()
    a, o = _num(adr), _num(occ)
    if a is None or o is None:
        return None
    o = min(max(o, 0.0), 1.0)
    booked_nights = 30.0 * o
    gross = 30.0 * a * o
    stays = booked_nights / c["alos"]
    turnover = stays * c["turnover_cost_sar"]
    channel = gross * c["blended_channel_pct"]
    return {
        "nightly_gross": gross,
        "booked_nights": booked_nights,
        "stays": stays,
        "turnover_cost_tot": turnover,
        "channel_fee_tot": channel,
        "nightly_net": max(0.0, gross - turnover - channel),
    }


def floor_price(adr, occ, cost_set=None):
    """FLOOR (§3.3) — the monthly rent below which we are simply worse off
    letting the unit by the night.

    A monthly let costs us far less to serve: ONE clean instead of `stays`, and
    no channel commission when it is sold direct. So the monthly price only has
    to cover the net the nightly path produced, plus what the monthly path itself
    costs, plus our margin.

    THE WATERFALL SUMS EXACTLY TO THE FLOOR. The brief's sample did not add up to
    its own total, and a column of numbers shown to an owner that does not reach
    the number at the top of it is worse than no column at all. A test asserts
    the sum. The two negative rows are labelled as what they are — costs the
    NIGHTLY path pays and the monthly path avoids — rather than as "savings",
    because a negative number labelled as a saving reads as an error.
    """
    c = cost_set or costs()
    e = nightly_economics(adr, occ, c)
    if e is None:
        return None

    monthly_direct = (c["turnover_cost_sar"] + c["utilities_month"]
                      + c["consumables_month"] + c["wifi_month"])
    floor = e["nightly_net"] + monthly_direct + c["min_margin_sar"]

    # When the nightly path costs more to run than it earns, nightly_net clamps
    # to zero — we would simply not let it that way. The WATERFALL HAS TO CLAMP
    # WITH IT. Showing the three raw rows here would print a negative column
    # under a positive headline (a 3,072 SAR discrepancy in the case that found
    # this), so the three collapse into one honest row instead.
    if e["nightly_net"] <= 0:
        components = [
            {"key": "nightly_net_zero", "sar": 0,
             "label_ar": "التأجير اليومي ما يغطي تكاليفه لهذي الوحدة",
             "label_en": "Nightly letting does not cover its own costs here"},
            {"key": "monthly_cost", "sar": monthly_direct,
             "label_ar": "تكاليف التأجير الشهري (كهرباء، ماء، نت، مستهلكات، تنظيفة)",
             "label_en": "Monthly-let running costs (utilities, wifi, consumables, one clean)"},
            {"key": "margin", "sar": c["min_margin_sar"],
             "label_ar": "الحد الأدنى لهامشنا",
             "label_en": "Our minimum margin"},
        ]
        check_reconciles(components, floor, "floor waterfall (nightly loss)")
        return {"floor": floor, "monthly_direct_cost": monthly_direct,
                "nightly": e, "components": components}

    components = [
        {"key": "nightly_gross", "sar": e["nightly_gross"],
         "label_ar": "دخل التأجير اليومي لـ30 ليلة",
         "label_en": "30 nights let nightly, gross"},
        {"key": "turnover_cost", "sar": -e["turnover_cost_tot"],
         "label_ar": "تكلفة التنظيف بين الحجوزات (تنظيفة وحدة بالشهري)",
         "label_en": "Turnover cleans between stays (one on a monthly let)"},
        {"key": "channel_fee", "sar": -e["channel_fee_tot"],
         "label_ar": "عمولة المنصات (صفر بالتأجير المباشر)",
         "label_en": "Channel commission (zero when let direct)"},
        {"key": "monthly_cost", "sar": monthly_direct,
         "label_ar": "تكاليف التأجير الشهري (كهرباء، ماء، نت، مستهلكات، تنظيفة)",
         "label_en": "Monthly-let running costs (utilities, wifi, consumables, one clean)"},
        {"key": "margin", "sar": c["min_margin_sar"],
         "label_ar": "الحد الأدنى لهامشنا",
         "label_en": "Our minimum margin"},
    ]

    check_reconciles(components, floor, "floor waterfall")
    return {
        "floor": floor,
        "monthly_direct_cost": monthly_direct,
        "nightly": e,
        "components": components,
    }


# ─────────────────────────── the quality model (§3.4) ───────────────────────────
#
# An INDEX model, not a regression. Two reasons, and both matter more than the
# extra accuracy a regression might buy:
#   1. We do not have the rows. A regression fitted on 53 units with sqm missing
#      on all of them would be a confident-looking fiction.
#   2. We could not explain one to an owner. "Your majlis is worth 340 riyals a
#      month" is a sentence. A coefficient vector is not.
#
# QUALITY_CLAMP is load-bearing, not cosmetic: it is what stops one mistyped
# input — a 400 sqm studio, a 6-bathroom flat — from running away with the price
# of a real apartment that a real owner will read.

QUALITY_CLAMP = (0.65, 1.60)


def quality_multiplier(values):
    """Π(1 + beta_i x (score_i - 5)/5) over the answered attributes, clamped.

    Unanswered attributes contribute exactly 1.0 (attrs.multiplier enforces it),
    and so does any attribute scored at the neutral 5 — so neither appears in
    `multipliers`, which lists only the factors that actually moved the number.
    An explanation that includes rows worth zero riyals is not an explanation.
    """
    from . import attrs

    values = values or {}
    raw = 1.0
    movers = []
    for k in attrs.keys():
        m = attrs.multiplier(k, values.get(k))
        raw *= m
        if abs(m - 1.0) > 1e-9:
            movers.append({"key": k, "beta": attrs.beta(k),
                           "score": attrs.to_score(k, values.get(k)),
                           "mult": m,
                           "label_ar": attrs.label_ar(k),
                           "label_en": attrs.label_en(k)})

    lo, hi = QUALITY_CLAMP
    mult = min(max(raw, lo), hi)
    movers.sort(key=lambda r: -abs(r["mult"] - 1.0))
    return {
        "mult": mult,
        "raw_mult": raw,
        "clamped": mult != raw,
        "unanswered": attrs.unanswered(values),
        "multipliers": movers,
    }


def model_price(base, values):
    """MODEL_PRICE — what this unit's own quality says it is worth, given the
    district base rate for its size.

    `delta_sar` on each factor answers the question an owner actually asks:
    what would the price be WITHOUT this? — so it is the price less the price
    divided by that factor's multiplier. When the product has been clamped these
    per-factor riyals no longer reconcile to the total, and `clamped` says so
    rather than letting the screen imply an arithmetic that is not there.
    """
    b = _num(base)
    if b is None or b <= 0:
        return None
    q = quality_multiplier(values)
    price = b * q["mult"]
    for row in q["multipliers"]:
        row["delta_sar"] = price - (price / row["mult"]) if row["mult"] else 0.0
    return {"model": price, "base": b, "quality": q}


# ───────────────────── the reconciliation invariant (§ hard rule) ─────────────────────
#
# THIS CLASS OF BUG HAS NOW OCCURRED TWICE, from two different authors:
#   * the brief's own sample payload summed to 12,900 under a stated 11,800;
#   * this engine's first waterfall printed -1,402 under a headline of 1,670.
#
# Twice from independent directions means it is not a bug to fix, it is a bug to
# make impossible. There are at least four more places it can reappear — rounding
# to the nearest 50, the override percentage, the owner-gate uplift and the
# months-let break-even — and each is a fresh chance at the same failure.
#
# So reconciliation is checked HERE, on every payload, at construction, rather
# than by whichever test someone remembered to write. A number shown to an owner
# under a column that does not add up to it is the single most expensive kind of
# wrong this feature can be: it is not a miscalculation, it is a visible one.

RECONCILE_TOL = 0.01          # riyals; floating point, not judgement


class ReconciliationError(AssertionError):
    """A payload whose parts do not add up to its whole. Raised at construction
    so it can never reach a screen, a PDF or an owner."""


def check_reconciles(components, total, label="waterfall"):
    """sum(components) must equal the number the components explain."""
    s = sum(_num(c.get("sar")) or 0.0 for c in (components or []))
    t = _num(total)
    if t is None:
        raise ReconciliationError("%s: no total to reconcile against" % label)
    if abs(s - t) > RECONCILE_TOL:
        raise ReconciliationError(
            "%s does not reconcile: components sum to %.2f but the total shown "
            "is %.2f (a %.2f SAR discrepancy on screen)" % (label, s, t, s - t))
    return True
