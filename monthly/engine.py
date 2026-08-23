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
  4. MODEL  — what the unit's own quality says it is worth.
  5. FINAL  = max(FLOOR, MODEL), and WHICH ONE won is the explanation.

There is no third gate. The owner-versus-annual-lease comparison left this path
on 2026-08-19 — Ouja's owners are on revenue guarantees, so it answered a
question nobody asks. Ejar survives as market context AFTER the price, never
before it.

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
    # A guest who commits to 30 nights up front must pay LESS than booking those
    # 30 nights one at a time, or the monthly product has no reason to exist.
    # This discount IS the product. Owner-editable.
    "monthly_commitment_discount": 0.15,
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


def forecast_unit(own=None, district=None, bedroom=None, quality_index=1.0,
                  own_all=None, pool_all=None, month_num=None, rung2=None,
                  factors=None, portfolio=None):
    """The fallback ladder (§3.1).

        1. our own history for this unit and month
        2. the unit's own recent record (rung chosen by the corpus)
        3. the same (district, bedrooms) pool, scaled by THIS unit's quality
        4. the same bedrooms across all districts, scaled the same way
        5. EVERY unit we have data for — the last resort, and the reason a unit
           with no recorded bedroom count still gets an answer instead of a
           blank. It is a weak number and says so.
        6. nothing — and then we say nothing

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

    # RUNG 2, chosen by the corpus rather than by preference. A unit with no
    # Augusts but eight months of its own record is described far better by that
    # record than by its neighbours — and the backtest says by how much.
    if rung2 in ("recent", "seasonal") and own_all:
        cand = (recent_forecast(own_all) if rung2 == "recent"
                else seasonal_forecast(own_all, month_num, factors))
        if cand:
            return {"adr": cand["adr"], "occ": cand["occ"],
                    "basis": "own_recent" if rung2 == "recent" else "own_seasonal",
                    "own_obs": own_nights, "pool_obs": cand.get("n", 0),
                    "quality_index": qi}

    for rows, basis in ((district, "district_pool"), (bedroom, "bedroom_pool"),
                        (portfolio, "portfolio_pool")):
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
        # The occupancy is IN the label. Without it this reads as a full-rack
        # figure and invites comparison with the ceiling, which is a full-rack
        # figure — two different quantities that both said "30 nights".
        {"key": "nightly_gross", "sar": e["nightly_gross"],
         "label_ar": "دخل 30 ليلة بإشغال %d%%" % round(min(max(_num(occ) or 0, 0.0), 1.0) * 100),
         "label_en": "30 nights at %d%% occupancy, gross"
                     % round(min(max(_num(occ) or 0, 0.0), 1.0) * 100)},
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


# ═════════════════════ the two gates, and the answer (§3.6, §3.7) ═════════════════════
#
# FINAL = max(FLOOR, MODEL). There is no third gate.
#
# The owner-versus-annual-lease comparison was removed from this path on
# 2026-08-19: Ouja's owners are on revenue guarantees, so it answered a question
# nobody asks. Its math survives in ejar.owner_annual_net for acquisition
# material. THIS MODULE DOES NOT IMPORT IT, and a test asserts so — a retired
# gate that can still be reached is not retired.
#
# `base` for the model price comes from OUR OWN realised history and never from
# the annual-lease index. An index feeding a variable named base_rate would be
# Ejar binding the price under a different name, and nobody reading that call
# site would see it happen. Ejar appears only AFTER the price, as a multiple.

PRICE_STEP = 50


def base_rate(district=None, bedroom=None):
    """What a unit like this actually earns us in a month, from our own history:
    30 nights at the comparable pool's own ADR and occupancy.

    Deliberately NOT scaled by this unit's quality — model_price applies
    quality_mult exactly once, and scaling here as well would count a good unit
    twice.
    """
    for rows, basis in ((district, "district_pool"), (bedroom, "bedroom_pool")):
        f = forecast(rows)
        if f:
            return {"base": 30.0 * f["adr"] * f["occ"], "basis": basis,
                    "pool_obs": f["n"]}
    return {"base": None, "basis": "insufficient", "pool_obs": 0}


BOUND_BY_VALUES = ("floor", "model", "ceiling")


def ceiling_price(adr, cost_set=None):
    """CEILING — 30 nights at our own nightly rate, less the commitment discount.

    THE CONSTRAINT THAT WAS MISSING. max(FLOOR, MODEL) runs upward forever: the
    floor is a floor and nothing held the model down. A guest can always book 30
    consecutive nights one at a time, so a monthly price above that rack total is
    a price nobody takes. The engine proposed 23,506 for a unit whose 30 nights
    cost 18,840 — arithmetically consistent, commercially absurd.
    """
    c = cost_set or costs()
    a = _num(adr)
    if a is None or a <= 0:
        return None
    return 30.0 * a * (1.0 - c["monthly_commitment_discount"])


def round_to_50(value, floor=None, ceiling=None):
    """Round to the nearest 50 WITHOUT leaving the band.

    The original rule — round up when rounding down would breach — was written
    for a floor. Against a ceiling it is exactly backwards: rounding up breaches
    the cap. So the band is respected in both directions, and if no multiple of
    50 fits inside it at all, there is no sane rounded price and we say so rather
    than quietly stepping outside.
    """
    v = _num(value)
    if v is None:
        return None
    import math
    nearest = round(v / PRICE_STEP) * PRICE_STEP
    lo, hi = _num(floor), _num(ceiling)
    if lo is not None and nearest < lo:
        nearest = math.ceil(lo / PRICE_STEP) * PRICE_STEP
    if hi is not None and nearest > hi:
        nearest = math.floor(hi / PRICE_STEP) * PRICE_STEP
    if lo is not None and nearest < lo:
        return None                     # the band holds no 50-step price
    return nearest


def clamp_report(results):
    """How often the quality clamp binds across a set of priced units.

    The clamp is a DIAGNOSTIC, not a save. One unit pinned at 1.60 is an
    exceptional apartment; a tenth of the portfolio pinned there is a
    mis-anchored scale, and the second is far more likely than the first.
    """
    rows = [r for r in (results or []) if r]
    n = len(rows)
    hits = sum(1 for r in rows if (r.get("quality") or {}).get("clamped"))
    rate = (hits / float(n)) if n else 0.0
    return {"n": n, "clamped": hits, "rate": rate,
            "anchor_suspect": n >= 10 and rate > CLAMP_RATE_ALARM,
            "threshold": CLAMP_RATE_ALARM}


CLAMP_RATE_ALARM = 0.10


def months_let_breakeven(price, monthly_direct_cost, nightly_year_net):
    """How many months of the year this unit must be let MONTHLY to match what it
    would have earned let NIGHTLY over the same year.

    The question the monthly product actually raises. Above 12 it cannot match
    nightly even fully let, which is a real and useful answer rather than a
    failure.
    """
    p, cost, ny = _num(price), _num(monthly_direct_cost), _num(nightly_year_net)
    if p is None or cost is None or ny is None:
        return {"months_let": None, "kept_per_month": None,
                "nightly_year_net": ny, "exceeds_year": None}
    kept = p - cost
    if kept <= 0:
        return {"months_let": None, "kept_per_month": kept,
                "nightly_year_net": ny, "exceeds_year": None}
    months = ny / kept
    return {"months_let": months, "kept_per_month": kept,
            "nightly_year_net": ny, "exceeds_year": months > 12.0}


_CONF_LADDER = ("high", "medium", "low")


def _confidence(basis, own_obs, unanswered_count):
    from . import attrs
    if basis == "insufficient":
        return "insufficient"
    i = 0
    if basis in ("own_recent", "own_seasonal"):
        i += 0                      # the unit's own record, just not its own August
    elif basis != "own_history":
        i += 1
    if (own_obs or 0) < 20:
        i += 1
    if (unanswered_count or 0) > attrs.MAX_UNANSWERED_BEFORE_LOW:
        i += 1
    return _CONF_LADDER[min(i, len(_CONF_LADDER) - 1)]


def _no_price(unit_id, month, fc, q, fl, gates, attrs, _ejar, ejar_row,
              today, paired_obs, reason, own_all_rows=None):
    """No price, and the reason why. A blank with a stated cause beats a number
    nobody should act on."""
    return {
        "unit_id": unit_id, "month": month, "price": None, "price_unrounded": None,
        "bound_by": None, "confidence": "insufficient", "basis": fc["basis"],
        "gates": gates, "components": [], "multipliers": [], "quality": q,
        "floor_detail": fl, "breakeven": None,
        "market_context": _ejar.market_context(None, ejar_row, today=today),
        "data": {"own_obs": fc["own_obs"], "unanswered": q["unanswered"],
                 "adr": fc["adr"], "occ": fc["occ"],
                 "beta_version": attrs.BETA_VERSION, "paired_obs": paired_obs},
        "is_estimate": True, "label_ar": "تقدير", "label_en": "Estimate",
        "warnings": [reason],
        # WHY there is no price, in numbers. «ما عندنا حجوزات كافية» is true and
        # useless; a brand-new unit with three bookings in one month deserves to
        # be told that, and told what would change it.
        "shortfall": {
            "own_month_nights": fc.get("own_obs") or 0,
            "months_of_record": len([o for o in (own_all_rows or [])
                                     if not o.get("partial")]),
            "months_needed": MIN_RECENT_OBS,
            "min_month_nights": MIN_OWN_OBS,
        },
    }


def price_unit(unit_id, month, own=None, district=None, bedroom=None,
               attr_values=None, cost_set=None, ejar_row=None, paired_obs=0,
               today=None, own_all=None, pool_all=None, rung2=None, factors=None,
               portfolio=None):
    """THE ANSWER, and the reason for it.

    One producer, two surfaces: page.py renders the waterfall from `components`
    and quote.py renders the PDF from the same object, so the screen and the
    document cannot drift apart.
    """
    from . import attrs, ejar as _ejar

    c = cost_set or costs()
    attr_values = attr_values or {}

    q = quality_multiplier(attr_values)
    fc = forecast_unit(own=own, district=district, bedroom=bedroom,
                       quality_index=q["mult"], own_all=own_all, pool_all=pool_all,
                       month_num=int(str(month)[5:7]) if month else None,
                       rung2=rung2, factors=factors, portfolio=portfolio)

    base = base_rate(district=district, bedroom=bedroom)
    if fc["basis"] in ("own_recent", "own_seasonal") and fc["adr"]:
        # The model gate compares against what units LIKE this one earn. When the
        # unit's own recent record is the better evidence, that record is the
        # comparison — otherwise a strong unit is measured against a pool it has
        # already outgrown, which is the whole complaint.
        base = {"base": 30.0 * fc["adr"] * fc["occ"], "basis": fc["basis"],
                "pool_obs": fc["pool_obs"]}
    fl = floor_price(fc["adr"], fc["occ"], c)
    mp = model_price(base["base"], attr_values)

    ceil_p = ceiling_price(fc["adr"], c)
    gates = {"floor": (fl or {}).get("floor"), "model": (mp or {}).get("model"),
             "ceiling": ceil_p}
    live = {k: v for k, v in gates.items()
            if v is not None and k in ("floor", "model")}

    # Market context is computed AFTER the price and never feeds it. Passing the
    # price in one direction only is what keeps that true.
    if not live:
        return _no_price(unit_id, month, fc, q, fl, gates, attrs, _ejar,
                         ejar_row, today, paired_obs, "insufficient_history",
                         own_all)

    # FINAL = clamp(max(FLOOR, MODEL), FLOOR, CEILING).
    bound_by = max(live, key=lambda k: live[k])
    final_raw = live[bound_by]

    floor_v = gates["floor"]
    if ceil_p is not None and floor_v is not None and floor_v > ceil_p:
        # Not lettable monthly at a price that makes sense. Do NOT split the
        # difference — a number halfway between "we lose money" and "no guest
        # would pay it" is simply a number nobody should act on.
        return _no_price(unit_id, month, fc, q, fl, gates, attrs, _ejar,
                         ejar_row, today, paired_obs, "floor_above_ceiling",
                         own_all)

    capped = False
    if ceil_p is not None and final_raw > ceil_p:
        final_raw = ceil_p
        bound_by = "ceiling"
        capped = True

    price = round_to_50(final_raw, floor=floor_v, ceiling=ceil_p)
    if price is None:
        return _no_price(unit_id, month, fc, q, fl, gates, attrs, _ejar,
                         ejar_row, today, paired_obs, "band_too_narrow",
                         own_all)

    # The waterfall starts at the FLOOR's own components and is carried up to the
    # number printed at the top of the page — one step for what the unit's
    # quality is worth, one for the rounding. It must land exactly on `price`.
    components = list((fl or {}).get("components") or [])
    if not components:
        components = [{"key": "model_base", "sar": (mp or {}).get("model") or 0.0,
                       "label_ar": "سعر الوحدة حسب مواصفاتها وأداء الحي",
                       "label_en": "The unit's own worth, from its features and its district"}]
    if bound_by == "model":
        # The step is only about QUALITY when quality was actually measured. With
        # every attribute unscored the model gate is the comparable-units average,
        # so this gap is the distance between that average and our cost floor —
        # and calling it «مواصفات» would print a claim the rest of the document
        # contradicts three pages later.
        measured = abs(q["mult"] - 1.0) > 1e-9
        components.append({
            "key": "quality_uplift" if measured else "pool_above_floor",
            "sar": final_raw - (fl or {}).get("floor", 0.0),
            "label_ar": ("رفعناه لأن مواصفات الوحدة تستاهل أكثر من الأرضية"
                         if measured else
                         "الفرق بين أداء الوحدات المماثلة وأرضية التكلفة"),
            "label_en": ("Raised: the unit's own features are worth more than the floor"
                         if measured else
                         "The gap between what comparable units achieve and our cost floor")})
    elif bound_by == "ceiling":
        components.append({
            "key": "ceiling_cap", "sar": final_raw - (fl or {}).get("floor", 0.0),
            "label_ar": "وقفناه عند سقف: أقل مما يدفعه الضيف لو حجز 30 ليلة وحدة وحدة",
            "label_en": "Capped: below what a guest would pay booking 30 nights one by one"})
    if abs(price - final_raw) > 1e-9:
        components.append({
            "key": "rounding", "sar": price - final_raw,
            "label_ar": "تقريب لأقرب 50 ريال",
            "label_en": "Rounded to the nearest 50 SAR"})

    check_reconciles(components, price, "price waterfall")

    nightly_year_net = 12.0 * (fl or {}).get("nightly", {}).get("nightly_net", 0.0)
    be = months_let_breakeven(price, (fl or {}).get("monthly_direct_cost"),
                              nightly_year_net)

    conf = _confidence(fc["basis"], fc["own_obs"], q["unanswered"])
    is_estimate = (paired_obs or 0) < attrs.CALIBRATED_AT

    warnings = []
    if capped:
        # A WARNING, not a normal outcome: the model wanted more than a guest
        # would pay night-by-night. That is a signal about the model, not about
        # the unit.
        warnings.append("model_above_ceiling")
    if fc["basis"] in ("district_pool", "bedroom_pool", "portfolio_pool"):
        warnings.append("priced_from_pool")
    elif fc["basis"] in ("own_recent", "own_seasonal"):
        warnings.append("priced_from_own_recent")
    if q["clamped"]:
        warnings.append("quality_clamped")
    if q["unanswered"] > attrs.MAX_UNANSWERED_BEFORE_LOW:
        warnings.append("thin_attributes")

    return {
        "unit_id": unit_id, "month": month,
        "price": price, "price_unrounded": final_raw,
        "bound_by": bound_by,
        "confidence": conf, "basis": fc["basis"],
        "gates": gates,
        "components": components,
        "multipliers": (mp or {}).get("quality", {}).get("multipliers", []),
        "quality": q,
        "floor_detail": fl,
        "breakeven": be,
        "market_context": _ejar.market_context(price, ejar_row, today=today),
        "data": {"own_obs": fc["own_obs"], "pool_obs": fc["pool_obs"],
                 "unanswered": q["unanswered"], "adr": fc["adr"], "occ": fc["occ"],
                 "base": base["base"], "base_basis": base["basis"],
                 "beta_version": attrs.BETA_VERSION, "paired_obs": paired_obs},
        "is_estimate": is_estimate,
        "label_ar": "تقدير" if is_estimate else "سعر",
        "label_en": "Estimate" if is_estimate else "Price",
        "warnings": warnings,
    }


# ═════════════════ diagnosis: how often does the ceiling actually bind? ═════════════════
#
# A COINCIDENCE TO NOT MISTAKE FOR A RELATIONSHIP. In the first worked example
# the ceiling and the nightly gross were both 16,014. Occupancy was 0.85 and the
# commitment discount 0.15, so (1 - discount) happened to equal occ. They share
# no term:
#     ceiling       = 30 x adr x (1 - discount)     — no occupancy in it
#     nightly_gross = 30 x adr x occ                — no discount in it
# Tests pin them apart at other occupancies so this never becomes folklore.
#
# THE THRESHOLD. The ceiling binds when MODEL > CEILING, i.e. when
#     base x qmult > 30 x adr_unit x (1 - d)
#     30 x adr_pool x occ_pool x qmult > 30 x adr_unit x (1 - d)
# so the ceiling binds above
#     qmult > (adr_unit x (1 - d)) / (adr_pool x occ_pool)
#
# For a unit priced near its pool (adr_unit ~ adr_pool) that collapses to
# (1 - d) / occ_pool — which carries an uncomfortable implication: THE BETTER OUR
# OCCUPANCY, THE MORE CERTAINLY THE CEILING BINDS. Above occ = (1 - d) the
# threshold drops below 1.0 and the ceiling binds even for units the model rates
# BELOW average. Ouja targets ~95% occupancy.
#
# This function exists to measure that, not to fix it.


def ceiling_binds_above(adr_unit, adr_pool, occ_pool, cost_set=None):
    """The quality multiplier at which the ceiling starts to bind. None when
    there is no pool to compare against."""
    c = cost_set or costs()
    au, ap, op = _num(adr_unit), _num(adr_pool), _num(occ_pool)
    if au is None or ap is None or op is None or ap <= 0 or op <= 0:
        return None
    return (au * (1.0 - c["monthly_commitment_discount"])) / (ap * op)


def bound_by_report(results):
    """The distribution of what actually set the price, across a set of units.

    Read it as:
        ceiling-bound > 50%   the model contributes nothing — say so plainly
        ceiling-bound 20-40%  healthy: the ceiling is a guardrail, not the rule
        floor-bound common    the units are marginal, which is its own finding
    """
    import statistics
    rows = [r for r in (results or []) if r]
    counts = {"floor": 0, "model": 0, "ceiling": 0, "no_price": 0}
    mults, overshoot = [], []
    for r in rows:
        b = r.get("bound_by")
        counts[b if b in counts else "no_price"] += 1
        m = (r.get("quality") or {}).get("mult")
        if m is not None:
            mults.append(float(m))
        if b == "ceiling":
            g = r.get("gates") or {}
            if g.get("model") and g.get("ceiling"):
                overshoot.append(g["model"] / g["ceiling"] - 1.0)

    priced = counts["floor"] + counts["model"] + counts["ceiling"]
    ceil_share = counts["ceiling"] / float(priced) if priced else 0.0
    floor_share = counts["floor"] / float(priced) if priced else 0.0

    if ceil_share > 0.50:
        verdict = "model_contributes_nothing"
    elif floor_share > 0.50:
        verdict = "units_marginal"
    elif 0.20 <= ceil_share <= 0.40:
        verdict = "healthy"
    else:
        verdict = "inconclusive"

    clamped = sum(1 for m in mults if m >= QUALITY_CLAMP[1] - 1e-9)
    return {
        "n": len(rows), "counts": counts,
        "ceiling_share": ceil_share, "floor_share": floor_share,
        "quality_mult": {
            "min": min(mults) if mults else None,
            "median": statistics.median(mults) if mults else None,
            "max": max(mults) if mults else None,
            "pct_at_clamp": (clamped / float(len(mults))) if mults else 0.0,
        },
        "overshoot": {
            "n": len(overshoot),
            "median_pct": statistics.median(overshoot) if overshoot else None,
            "max_pct": max(overshoot) if overshoot else None,
        },
        "verdict": verdict,
    }


# ══════════ is the floor the whole answer at high occupancy? (S8 diagnosis) ══════════
#
# The owner's derivation, carried one step further. Both sides of the binding
# comparison are 30 x ADR x something:
#     ceiling = 30 x ADR_unit x (1 - d)
#     model   = 30 x ADR_pool x occ x qmult
# so for a unit priced near its pool it reduces to (1 - d) vs occ x qmult. That
# is arithmetic, not economics. QUALITY IS ALREADY INSIDE ADR — a better unit
# charges more per night, so its ceiling rises with it and the model chases a
# target that moves with it. Quality cannot win at high occupancy.
#
# Which raises the real question these functions exist to answer with numbers:
# at 95% we are not filling empty nights, because there are none. A monthly
# booking displaces nightly revenue we would have earned anyway, so monthly stops
# being a yield play and becomes a cost-and-hassle play — one clean instead of
# ten, no channel fee, no gaps. THE FLOOR ALREADY COMPUTES EXACTLY THAT. The
# quality model may simply belong to the low-occupancy case: soft months, new
# units, and later developer inventory with no history at all.
#
# Diagnosis only. Nothing here changes the ceiling, the discount or any beta.

OCC_BANDS = ("<60", "60-75", "75-85", ">85")
FLOOR_RATIO_STABLE_SPREAD = 0.10     # inter-quartile-ish spread that still reads as "one number"


def occupancy_band(occ):
    o = _num(occ)
    if o is None:
        return "unknown"
    if o < 0.60:
        return "<60"
    if o < 0.75:
        return "60-75"
    if o < 0.85:
        return "75-85"
    return ">85"


def segmented_report(results):
    """The bound_by distribution split by forecast occupancy band.

    One band can otherwise hide another: a portfolio that is 50% ceiling-bound
    overall might be 100% ceiling-bound above 85% and 0% below 60%, which is a
    completely different fact about the model.
    """
    rows = [r for r in (results or []) if r]
    bands = {}
    for b in OCC_BANDS + ("unknown",):
        bands[b] = bound_by_report(
            [r for r in rows if occupancy_band((r.get("data") or {}).get("occ")) == b])

    high = bands[">85"]["ceiling_share"] if bands[">85"]["n"] else None
    low_model = 0.0
    low_n = bands["<60"]["n"] + bands["60-75"]["n"]
    if low_n:
        low_model = (bands["<60"]["counts"]["model"]
                     + bands["60-75"]["counts"]["model"]) / float(low_n)

    verdict = "inconclusive"
    if high is not None and high >= 0.80 and low_model >= 0.40:
        # Not a defect — a domain. The model bites where there are empty nights
        # to fill, and stands aside where there are not.
        verdict = "model_is_a_low_occupancy_tool"
    elif high is not None and high >= 0.80 and low_n and low_model < 0.20:
        verdict = "model_contributes_nothing_anywhere"

    return {"bands": bands, "overall": bound_by_report(rows), "verdict": verdict,
            "high_occ_ceiling_share": high, "low_occ_model_share": low_model}


def floor_ratio_report(results):
    """FLOOR as a share of nightly gross, per unit.

    If this is stable across the portfolio the floor is doing something simple
    and legible — "about 86% of what the unit grosses nightly" — and it should be
    shown that way rather than dressed up as a model.
    """
    import statistics
    ratios = []
    for r in (results or []):
        if not r:
            continue
        fl = (r.get("gates") or {}).get("floor")
        gross = ((r.get("floor_detail") or {}).get("nightly") or {}).get("nightly_gross")
        f, g = _num(fl), _num(gross)
        if f is None or g is None or g <= 0:
            continue
        ratios.append(f / g)
    if not ratios:
        return {"n": 0, "ratios": [], "median": None, "min": None, "max": None,
                "spread": None, "stable": False}
    return {
        "n": len(ratios), "ratios": ratios,
        "median": statistics.median(ratios),
        "min": min(ratios), "max": max(ratios),
        "spread": max(ratios) - min(ratios),
        "stable": (max(ratios) - min(ratios)) <= FLOOR_RATIO_STABLE_SPREAD,
    }


def sensitivity_sweep(units, steps=None, cost_set=None):
    """What the FIRST scoring pass will do to the engine, before anyone scores.

    Every quality_mult is 1.0 today because no unit has been scored. Sweeping
    qmult from 1.0 to 1.6 says at which value ceiling-bound crosses half, per
    occupancy band. If a band crosses at 1.05, scoring changes nothing except
    which gate gets named — and that is worth knowing before two days of work,
    not after.

    `units` are dicts of {adr_unit, adr_pool, occ_pool}: no attributes needed,
    which is exactly the point.
    """
    c = cost_set or costs()
    steps = steps or [round(1.0 + 0.1 * i, 1) for i in range(7)]
    rows = [u for u in (units or []) if u]

    bands = {}
    for b in OCC_BANDS:
        members = [u for u in rows if occupancy_band(u.get("occ_pool")) == b]
        curve, crossover = [], None
        for q in steps:
            if not members:
                curve.append(None)
                continue
            hits = 0
            for u in members:
                t = ceiling_binds_above(u.get("adr_unit"), u.get("adr_pool"),
                                        u.get("occ_pool"), c)
                if t is not None and q > t:
                    hits += 1
            share = hits / float(len(members))
            curve.append(share)
            if crossover is None and share > 0.50:
                crossover = q
        bands[b] = {"n": len(members), "curve": curve, "crossover": crossover,
                    "already_crossed": crossover == steps[0] if crossover else False}
    return {"steps": steps, "bands": bands}


# ═════════════ the fallback ladder, decided by evidence rather than by me ═════════════
#
# THE DESIGN FLAW THIS FIXES. Same-month-only history means a unit onboarded
# eight months ago has NO evidence for August and drops straight to a district
# average — which is why a 4BR with a private cinema priced identically to
# fifteen other units. Eight months of that unit's own earnings were sitting
# unused because none of them happened to be an August.
#
# Four candidates for rung 2, and the corpus picks the winner:
#   1 same_month   the unit's own Augusts                      (rung 1, unchanged)
#   2 recent       the unit's own recent months, any month
#   3 pool         the district/size average                   (today's rung 2)
#   4 seasonal     the unit's recent level x the pool's August-vs-average shape
#
# (4) is the interesting one: it keeps the UNIT's earning level and borrows only
# the SEASONAL SHAPE from the pool, which is the part a pool actually knows.

MIN_RECENT_OBS = 3          # months of recent history before "recent" may speak
MIN_SEASONAL_UNITS = 3      # units with multi-year history before a factor is trusted
MIN_BACKTEST_CASES = 12     # cases before the corpus is allowed to pick a rung


def recent_forecast(all_obs, exclude_month=None):
    """Freshness-weighted ADR and occupancy over the unit's recent months,
    whatever month number they are."""
    rows = [o for o in (all_obs or [])
            if not o.get("partial") and o.get("month") != exclude_month]
    if len(rows) < MIN_RECENT_OBS:
        return None
    return forecast(rows)


def seasonal_factors(pool_all_obs, min_units=MIN_SEASONAL_UNITS):
    """month_num -> (adr_factor, occ_factor) against the pool's own average.

    Built ONLY from units with more than one calendar year of history: a unit
    that has existed for four months cannot tell you what August does, and
    including it would let recent growth masquerade as seasonality.
    """
    import collections
    by_unit = collections.defaultdict(list)
    for lid, rows in (pool_all_obs or {}).items():
        by_unit[lid] = [o for o in rows if not o.get("partial")]

    qualified = {lid: rows for lid, rows in by_unit.items()
                 if len({o["month"][:4] for o in rows}) >= 2 and len(rows) >= 12}
    if len(qualified) < min_units:
        return {}

    adr_by_month, occ_by_month = collections.defaultdict(list), collections.defaultdict(list)
    for lid, rows in qualified.items():
        adrs = [o["adr"] for o in rows if o.get("adr")]
        occs = [o["occ"] for o in rows if o.get("occ") is not None]
        if not adrs or not occs:
            continue
        base_adr = sum(adrs) / len(adrs)
        base_occ = sum(occs) / len(occs)
        if base_adr <= 0 or base_occ <= 0:
            continue
        for o in rows:
            if o.get("adr"):
                adr_by_month[o["month_num"]].append(o["adr"] / base_adr)
            if o.get("occ") is not None:
                occ_by_month[o["month_num"]].append(o["occ"] / base_occ)

    out = {}
    for m in range(1, 13):
        a, oc = adr_by_month.get(m), occ_by_month.get(m)
        if a and oc:
            out[m] = (sum(a) / len(a), sum(oc) / len(oc))
    return out


def seasonal_forecast(all_obs, month_num, factors, exclude_month=None):
    """The unit's own recent level, shaped by the pool's seasonality."""
    r = recent_forecast(all_obs, exclude_month=exclude_month)
    f = (factors or {}).get(int(month_num))
    if not r or not f:
        return None
    adr_f, occ_f = f
    return {"adr": r["adr"] * adr_f,
            "occ": min(1.0, max(0.0, r["occ"] * occ_f)),
            "n": r["n"]}


def _ape(pred, actual):
    if pred is None or actual is None or actual <= 0:
        return None
    return abs(pred - actual) / actual


def backtest_methods(units_all_obs, pools_all_obs, pool_of, min_cases=MIN_BACKTEST_CASES):
    """Hold out one real unit-month at a time and score every rung against it.

    The held-out month is excluded from its own prediction, so a method cannot
    score well by remembering the answer.
    """
    import statistics
    factors = seasonal_factors(pools_all_obs)
    errs = {"same_month": [], "recent": [], "pool": [], "seasonal": []}

    for lid, rows in (units_all_obs or {}).items():
        rows = [o for o in rows if not o.get("partial")]
        if len(rows) < MIN_RECENT_OBS + 1:
            continue
        pool_rows = (pool_of(lid) or []) if pool_of else []
        for held in rows:
            actual = held.get("adr")
            if not actual or actual <= 0:
                continue
            others = [o for o in rows if o["month"] != held["month"]]

            same = forecast([o for o in others if o["month_num"] == held["month_num"]])
            if same:
                errs["same_month"].append(_ape(same["adr"], actual))

            rec = recent_forecast(others)
            if rec:
                errs["recent"].append(_ape(rec["adr"], actual))

            pf = forecast([o for o in pool_rows
                           if o.get("month_num") == held["month_num"]
                           and o.get("month") != held["month"]])
            if pf:
                errs["pool"].append(_ape(pf["adr"], actual))

            se = seasonal_forecast(others, held["month_num"], factors)
            if se:
                errs["seasonal"].append(_ape(se["adr"], actual))

    out = {}
    for k, v in errs.items():
        vals = [x for x in v if x is not None]
        out[k] = {"mape": statistics.median(vals) if vals else None, "n": len(vals)}

    ranked = [(v["mape"], k) for k, v in out.items()
              if v["mape"] is not None and v["n"] >= min_cases]
    ranked.sort()
    # rung 1 is always the unit's own same-month history; this picks rung 2.
    rung2 = None
    for _m, k in ranked:
        if k != "same_month":
            rung2 = k
            break
    return {"methods": out, "winner": ranked[0][1] if ranked else None,
            "rung2": rung2, "n_seasonal_factors": len(factors),
            "min_cases": min_cases}
