"""Stay Match scoring engine. PURE — no I/O, no network, no clock reads.

The contract that makes this feature work: search FILTERS and can return zero;
this engine SCORES and returns the best available fit. Only physically-true
constraints eliminate a unit. Everything else lowers a score and produces an
honest tradeoff string the UI shows to the guest.
"""

import copy
import math

from . import poi

# Weights sum to 100. Tunable here without touching the UI or the tests that
# lock behaviour (the tests assert orderings, never absolute scores).
WEIGHTS = {
    "bedrooms": 30,
    "proximity": 25,
    "budget": 20,
    "amenities": 15,
    "quality": 10,
}

# Below this, we tell the guest the truth instead of dressing up a weak match.
# NOTE: this assumes ALL FIVE weights (bedrooms, proximity, budget, amenities,
# quality) are wired into `_score_one`. That is now true (Tasks 3-6 all land
# in `_score_one`) — see
# TestConfidenceReachable.test_a_strong_match_clears_the_confidence_floor in
# tests/test_match_engine.py, which is a regression guard: if a future change
# ever unwires one of the five blocks, that test fails loudly instead of the
# honest low-confidence fallback copy silently firing for every guest.
CONFIDENCE_FLOOR = 55

# Bayesian prior for ratings. A raw average lets 5.0 from 3 reviews outrank 4.8
# from 90, which would put barely-reviewed units at the top of every result.
# PRIOR_RATING=4.6 encodes "an Ouja unit is expected to perform around 4.6" —
# so a unit with almost no reviews is pulled toward that expectation rather
# than trusted at face value, and a unit PROVEN below the prior over many
# reviews correctly loses to a barely-reviewed unit whose one data point sits
# near the prior. (4.5*/200 losing to 5.0*/1 is intentional, not a bug — see
# TestQualitySmoothing.test_barely_reviewed_near_perfect_unit_can_beat_a_proven_strong_unit.)
# 4.6 is an ASSUMED portfolio mean; re-derive it from live review data once
# enough units have real review histories.
PRIOR_RATING = 4.6
PRIOR_WEIGHT = 12

TOP_N = 3


def required_bedrooms(party_size, sleep_pref):
    """How many bedrooms the guest's own answers imply.

    Requires an already-clean int `party_size` (see `_clean_party_size`,
    applied up front in `score`) — this function does not validate its input.
    """
    if party_size <= 2:
        return 1
    if sleep_pref == "together":
        return 1
    if sleep_pref == "each":
        return party_size
    # "pairs" and the None default: two per room, rounded up.
    return max(1, -(-party_size // 2))


def _clean_party_size(party_size):
    """Coerce to a positive int. Malformed/missing input defaults to 1
    rather than silently disabling the capacity gate (a bad string used to
    make `int(cap) < int(party_size)` raise, get swallowed, and admit the
    unit regardless of its capacity — fail-open on exactly the input it
    should distrust)."""
    try:
        v = int(party_size)
    except (TypeError, ValueError):
        return 1
    return v if v >= 1 else 1


def _passes_capacity_gate(u, party_size):
    """Only a KNOWN capacity that is too small excludes a unit. `party_size`
    must already be a clean positive int (see `_clean_party_size`)."""
    cap = u.get("capacity")
    if not cap:
        return True
    try:
        return int(cap) >= party_size
    except (TypeError, ValueError):
        return True


def _passes_availability_gate(u, dated):
    """Dates only matter when the guest actually gave dates."""
    if not dated:
        return True
    return u.get("available") is not False


def _id_sort_key(uid):
    """Type-stable sort key so mixed id types (int/str/None) never raise
    TypeError in sort — numeric ids sort together numerically, everything
    else sorts together as text, and the two groups never get compared to
    each other."""
    try:
        return (0, int(uid))
    except (TypeError, ValueError):
        return (1, str(uid))


def score(answers, units, geo=None, top=TOP_N):
    """Rank units by fit. See the plan's data contract for shapes.

    Two independent hard gates, deliberately evaluated in this order so the
    caller can tell "your party is too big for anything we have" apart from
    "those dates are booked" — conflating them tells a couple with a fully
    booked weekend that no apartment is big enough for two people, which is
    a lie:

    1. CAPACITY — physically true regardless of dates. If nothing in the
       whole inventory can hold the party, that is the one legitimate zero
       (`impossible: True`).
    2. AVAILABILITY — only applies when the guest gave check-in/check-out.
       If capacity was fine but everything that fits is booked, that is a
       normal empty result, not "impossible".
    """
    answers = answers or {}
    units = list(units or [])
    dated = bool(answers.get("check_in") and answers.get("check_out"))
    party_size = _clean_party_size(answers.get("party_size"))

    capacity_ok = [u for u in units if _passes_capacity_gate(u, party_size)]

    if not capacity_ok and units:
        caps = []
        for u in units:
            try:
                caps.append(int(u.get("capacity") or 0))
            except (TypeError, ValueError):
                continue
        return {"top": [], "near": [], "confident": False,
                "impossible": True, "max_capacity": (max(caps) if caps else 0)}

    eligible = [u for u in capacity_ok if _passes_availability_gate(u, dated)]

    if not eligible:
        # Capacity was fine — the dates are just booked. Never report this
        # as "impossible" (that phrase is reserved for capacity).
        return {"top": [], "near": [], "confident": False,
                "impossible": False, "max_capacity": 0}

    scored = []
    raw_totals = []
    for u in eligible:
        total, reasons, tradeoffs = _score_one(u, answers, geo or {}, party_size, dated)
        # Deep copy: nested fields (amenities, images, ...) must not be
        # shared with the caller's dict — a later mutation of a returned
        # item (e.g. Task 6 amenity scoring) must never corrupt bot.py's
        # cached listing snapshots.
        item = copy.deepcopy(u)
        item["match_score"] = int(round(total))
        item["reasons"] = reasons[:3]
        item["tradeoff"] = (tradeoffs[0] if tradeoffs else None)
        scored.append(item)
        raw_totals.append(total)

    # Stable, deterministic: best score first, ties broken by id ascending.
    # Sort on the RAW float total, not the rounded `match_score` shown to the
    # guest. With only bedrooms+quality wired (Tasks 1-4) the two never
    # diverged, but now that all five weights are summed, two units a fraction
    # of a point apart can round to the same displayed integer — sorting on
    # the rounded value would silently coin-flip that pair on id instead of on
    # which one actually scored higher. `match_score` in the returned dict is
    # still the rounded integer; only the sort key uses the pre-rounding sum.
    order = sorted(range(len(scored)),
                   key=lambda i: (-raw_totals[i], _id_sort_key(scored[i].get("id"))))
    scored = [scored[i] for i in order]

    best = scored[0]["match_score"] if scored else 0
    return {"top": scored[:top], "near": scored[top:],
            "confident": best >= CONFIDENCE_FLOOR,
            "impossible": False,
            "max_capacity": 0}


def _ar_count(n, one, two, few, many):
    """Arabic number agreement: 1 singular, 2 dual, 3-10 plural, 11+ singular.
    Guest-facing copy that gets this wrong reads as machine translation."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return f"{n} {many}"
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n % 100 <= 10:
        return f"{n} {few}"
    return f"{n} {many}"


_BEDROOM_FORMS = ("غرفة نوم وحدة", "غرفتين نوم", "غرف نوم", "غرفة نوم")


def _ar_bedrooms(n):
    return _ar_count(n, *_BEDROOM_FORMS)


def _score_bedrooms(u, party_size, sleep_pref):
    """0.0-1.0 fit, plus a reason or a tradeoff. Exact match wins; over-provisioned
    is slightly worse (the guest pays for space they said they don't need);
    under-provisioned is heavily penalised but NEVER eliminated. The 0.6 floor
    on over-provisioning is deliberate: no amount of excess space should ever
    score worse than a one-room shortfall — a too-big apartment is merely an
    inconvenience, a too-small one can ruin the stay.

    `party_size` must already be a clean positive int (the same value the
    capacity gate used) — this function does not validate it.

    `beds` is handled carefully: missing/non-numeric is genuinely UNKNOWN data
    (neutral 0.5, no claim made either way). `0` is a real studio — Hostaway
    sends `bedroomsNumber: 0` for these — and must NOT be laundered into the
    same "unknown" bucket, because 0.5 beats a real one-bedroom that is one
    room short (0.37), which is backwards and hides studios from guests who
    should be told honestly.
    """
    need = required_bedrooms(party_size, sleep_pref)
    raw = u.get("beds")
    try:
        have = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        have = None
    if have is None:
        return 0.5, None, None                      # unknown data scores neutral
    if have == 0:
        # Real studio: no separate bedroom, so it is scored on the same
        # under-provisioned curve as a real apartment that is `need` rooms
        # short (this also guarantees it never outscores a real 1-bedroom at
        # the same need) — but named honestly rather than as a bare number.
        short = need
        return max(0.1, 0.55 - 0.18 * short), None, "استوديو — بدون غرفة نوم منفصلة"
    if have == need:
        return 1.0, f"{_ar_bedrooms(have)} — بالضبط اللي طلبته", None
    if have > need:
        over = have - need
        return max(0.6, 1.0 - 0.12 * over), f"{_ar_bedrooms(have)} — فيها زيادة راحة", None
    short = need - have
    return (max(0.1, 0.55 - 0.18 * short), None,
            f"{_ar_bedrooms(have)} بس — طلبت {_ar_bedrooms(need)}")


def _score_quality(u):
    """0.0-1.0 from rating, shrunk toward the portfolio prior by review count.
    A CONFIDENT low rating (>=10 reviews, so it is not noise) earns an honest
    tradeoff. A thinly-reviewed or unrated unit gets neither the reason nor
    the tradeoff — absence of reviews is not proof of a flaw, and it would be
    unfair to tell a guest new inventory is "worse" than the rest."""
    try:
        rating = float(u.get("rating") or 0)
        n = int(u.get("reviews_count") or 0)
    except (TypeError, ValueError):
        return 0.5, None, None
    if rating <= 0 or n <= 0:
        return 0.5, None, None                      # unrated scores neutral, never punished
    smoothed = ((rating * n) + (PRIOR_RATING * PRIOR_WEIGHT)) / (n + PRIOR_WEIGHT)
    fit = max(0.0, min(1.0, (smoothed - 3.5) / 1.5))
    reason, tradeoff = None, None
    if rating >= 4.7 and n >= 10:
        reason = f"{rating} ★ من {n} تقييم"
    elif n >= 10 and rating < 4.3:
        tradeoff = f"تقييمها {rating} ★ — أقل من بقية وحداتنا"
    return fit, reason, tradeoff


# Minutes at which proximity stops helping. Beyond this a unit is "across town".
_NEAR_MIN, _FAR_MIN = 10, 35


def _score_proximity(u, answers, geo):
    """0.0-1.0 by drive time to the POI implied by the guest's purpose.
    Neutral (never punishing) when the purpose has no POI or the unit cannot be
    located — invariant 7 means this never returns None.

    NOTE (reviewed, intentional): across Ouja's actual north-Riyadh footprint,
    almost every unit computes to 3-20 minutes from every POI, so the
    "بعيدة عن ..." far-tradeoff below will rarely fire in production. That is
    correct, not a bug — the copy exists for a genuinely distant or
    mislabeled unit, not to manufacture a downside where none exists. Do not
    "fix" this by lowering `_NEAR_MIN`/`_FAR_MIN` to make it fire more often.
    """
    poi_key = poi.PURPOSE_POI.get(answers.get("purpose") or "")
    if not poi_key:
        return 0.5, None, None
    target = poi.POIS.get(poi_key)
    if not target:
        return 0.5, None, None
    point = poi.resolve_point(u, geo)
    if not point:
        return 0.5, None, None

    label = target[0]
    mins = poi.minutes_to(poi.haversine_km(point, (target[2], target[3])))
    if mins <= _NEAR_MIN:
        return 1.0, f"{mins} دقيقة عن {label}", None
    if mins >= _FAR_MIN:
        return 0.1, None, f"بعيدة عن {label} — حوالي {mins} دقيقة"
    span = _FAR_MIN - _NEAR_MIN
    fit = 1.0 - ((mins - _NEAR_MIN) / span) * 0.9
    reason = f"{mins} دقيقة عن {label}" if mins <= 20 else None
    return fit, reason, None


# Beyond the 25%-over tier, decay continuously instead of a flat 0.15 — a unit
# 26% over budget and one 1000% over used to score identically, which threw
# away ranking resolution among over-budget units (the tradeoff TEXT already
# stated the real SAR gap correctly either way; this only affects the score).
# Chosen so the curve is continuous with the 0.5 "near budget" tier exactly at
# ratio==0.25, decays smoothly, and lands close to the old flat 0.15 around
# ratio==1.0 (100% over) — i.e. it doesn't reshuffle the common case, it only
# adds resolution further out. Floors above zero: an absurdly over-budget unit
# never fully vanishes from scoring (soft signals never eliminate a unit).
_BUDGET_OVER_FLOOR = 0.05
_BUDGET_DECAY = 2.0


def _score_budget(u, answers):
    """0.0-1.0 by nightly price against the guest's band. Unpriced/no-budget
    scores neutral, never punished — invariant: only physically-true facts
    eliminate a unit, and price is a soft signal here, not a gate."""
    budget = answers.get("budget_max")
    if not budget:
        return 0.5, None, None
    price = u.get("est_avg") or u.get("price_base")
    try:
        price = int(price)
    except (TypeError, ValueError):
        return 0.5, None, None
    if price <= 0:
        return 0.5, None, None
    try:
        budget = int(budget)
    except (TypeError, ValueError):
        # Malformed budget_max (e.g. a non-numeric string) must score neutral
        # rather than raise — mirrors `_clean_party_size`'s fail-closed-to-
        # neutral handling of garbage guest input.
        return 0.5, None, None
    if price <= budget:
        return 1.0, f"{price} ريال بالليلة — داخل ميزانيتك", None
    gap = price - budget
    tradeoff = f"أغلى {gap} ريال بالليلة من ميزانيتك"
    if gap <= budget * 0.25:
        return 0.5, None, tradeoff
    ratio = gap / budget
    fit = _BUDGET_OVER_FLOOR + (0.5 - _BUDGET_OVER_FLOOR) * math.exp(-_BUDGET_DECAY * (ratio - 0.25))
    return fit, None, tradeoff


# Amenity keywords that genuinely matter per purpose. (keyword, exclusions,
# arabic_label). A keyword only counts when it appears in an amenity name
# that contains NONE of its exclusions — this is what stops real Hostaway/
# Airbnb amenity strings from producing false positives that would tell a
# guest they have something they don't: "washer" must not be satisfied by
# "Dishwasher", "pool" must not be satisfied by "Pool table"/"Pool cue", and
# "parking" must not be satisfied by paid/off-site/street parking, which is
# not the convenience a guest means when they ask for parking.
PURPOSE_AMENITIES = {
    "work":      [("workspace", (), "مكتب للشغل"),
                  ("wifi", (), "واي فاي"),
                  ("desk", (), "مكتب")],
    "family":    [("kitchen", (), "مطبخ كامل"),
                  ("washer", ("dishwasher",), "غسالة"),
                  ("crib", (), "سرير أطفال")],
    "rest":      [("pool", ("pool table", "pool cue"), "مسبح"),
                  ("balcony", (), "بلكونة"),
                  ("jacuzzi", (), "جاكوزي")],
    "medical":   [("kitchen", (), "مطبخ كامل"),
                  ("elevator", (), "مصعد"),
                  ("parking", ("paid parking", "off premises", "street parking"), "موقف")],
    "boulevard": [("parking", ("paid parking", "off premises", "street parking"), "موقف سيارة"),
                  ("wifi", (), "واي فاي")],
    "shopping":  [("parking", ("paid parking", "off premises", "street parking"), "موقف سيارة"),
                  ("elevator", (), "مصعد")],
}


def _missing_amenities_tradeoff(wanted):
    """Natural Najdi tradeoff naming what THIS purpose cares about that the
    unit does not have — built from PURPOSE_AMENITIES' own labels (its top
    one or two entries) rather than six hand-written sentences, so a future
    purpose added to that table gets an honest tradeoff for free."""
    labels = [ar for (_, _, ar) in wanted]
    if len(labels) == 1:
        return f"ما فيها {labels[0]}"
    return f"ما فيها {labels[0]} ولا {labels[1]}"


def _score_amenities(u, answers):
    """0.0-1.0 by how many purpose-relevant amenities the unit actually has.
    Neutral when the purpose has no amenity list; a missing/malformed
    amenities field is treated as "has none" rather than raising.

    Matched per RAW amenity string, one at a time — never against one joined
    blob. Joining first would let an exclusion meant for one amenity string
    accidentally cancel a genuine match sitting in a different string (or vice
    versa); matching string-by-string keeps each exclusion scoped to only the
    string it actually appears in.

    When NOTHING relevant matched, returns an honest tradeoff naming what is
    missing instead of just going quietly neutral-looking (Fix 2) — a unit
    with no purpose-relevant amenity is a real, guest-visible downside.
    """
    wanted = PURPOSE_AMENITIES.get(answers.get("purpose") or "")
    if not wanted:
        return 0.5, None, None
    strings = [str(a).lower() for a in (u.get("amenities") or [])]
    hits = []
    for kw, exclusions, ar in wanted:
        for s in strings:
            if kw in s and not any(ex in s for ex in exclusions):
                hits.append(ar)
                break
    if not hits:
        return 0.2, None, _missing_amenities_tradeoff(wanted)
    fit = min(1.0, len(hits) / len(wanted))
    return fit, " · ".join(hits[:2]), None


def _score_one(u, answers, geo, party_size, dated):
    """Returns (total_0_to_100, reasons, tradeoffs). Filled in across Tasks 3-6.

    `party_size` is the already-cleaned value from `score()` (see
    `_clean_party_size`) — never re-derive it from raw `answers` here, that
    reintroduces the fail-open-on-garbage-input bug the gate exists to avoid.

    `dated` is whether the guest gave check-in/check-out (same flag `score()`
    used for the availability gate) — the reason-guarantee fallback below
    needs it to avoid claiming availability that was never actually checked.
    """
    bfit, breason, btradeoff = _score_bedrooms(u, party_size, answers.get("sleep_pref"))
    pfit, preason, ptradeoff = _score_proximity(u, answers, geo)
    gfit, greason, gtradeoff = _score_budget(u, answers)          # g: budget (b is bedrooms)
    afit, areason, atradeoff = _score_amenities(u, answers)
    qfit, qreason, qtradeoff = _score_quality(u)

    # (weight, fit, reason, tradeoff) in the FIXED weight-descending order —
    # this order is also the tie-break below, since `sorted` is stable.
    parts = [
        (WEIGHTS["bedrooms"], bfit, breason, btradeoff),
        (WEIGHTS["proximity"], pfit, preason, ptradeoff),
        (WEIGHTS["budget"], gfit, greason, gtradeoff),
        (WEIGHTS["amenities"], afit, areason, atradeoff),
        (WEIGHTS["quality"], qfit, qreason, qtradeoff),
    ]
    total = sum(weight * fit for weight, fit, _, _ in parts)

    # Reasons: sorted by actual points EARNED (fit * weight), not by which
    # block happened to run first — a perfect proximity match (25 pts) must
    # outrank a merely-adequate over-provisioned bedroom fit (18 pts) even
    # though bedrooms is scored first. Equal-point ties fall back to the
    # fixed weight-descending order above (stable sort + `parts` already in
    # that order), so the existing determinism tests keep holding.
    reason_candidates = [(weight * fit, text) for weight, fit, text, _ in parts if text]
    reason_candidates.sort(key=lambda r: -r[0])
    reasons = [text for _, text in reason_candidates]

    # Tradeoff: sorted by actual points LOST ((1 - fit) * weight) so the guest
    # sees the single biggest real shortfall — e.g. being 129 minutes from the
    # one place they asked to be near (22.5 pts lost) must beat being a single
    # bedroom short (18.9 pts lost), never whichever block ran first.
    tradeoff_candidates = [(weight * (1 - fit), text) for weight, fit, _, text in parts if text]
    tradeoff_candidates.sort(key=lambda t: -t[0])
    tradeoffs = [text for _, text in tradeoff_candidates]

    # Reason guarantee (invariant 4): a unit with nothing notable still says
    # something true rather than showing a bare card. MUST STAY LAST — every
    # scoring block above appends its own candidate reason first; any future
    # scoring block must insert BEFORE this one, never after.
    if not reasons:
        cap = u.get("capacity")
        if cap:
            reasons.append(f"تستوعب {_ar_count(cap, 'ضيف واحد', 'ضيفين', 'ضيوف', 'ضيف')}")
        else:
            # Never claim availability we have not checked. Hostaway
            # availability is only verified when the guest gave real dates
            # (mirrors bot.py's `_gw_search` browse mode, which reports
            # `available: None` and tells the guest to check inside Airbnb).
            reasons.append("متاحة بتواريخك" if dated else "من وحدات عوجا المختارة")

    return total, reasons, tradeoffs
