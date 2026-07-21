"""Stay Match scoring engine. PURE — no I/O, no network, no clock reads.

The contract that makes this feature work: search FILTERS and can return zero;
this engine SCORES and returns the best available fit. Only physically-true
constraints eliminate a unit. Everything else lowers a score and produces an
honest tradeoff string the UI shows to the guest.
"""

import copy

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
CONFIDENCE_FLOOR = 55

# Bayesian prior for ratings. A raw average lets 5.0 from 3 reviews outrank 4.8
# from 90, which would put barely-reviewed units at the top of every result.
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
    for u in eligible:
        total, reasons, tradeoffs = _score_one(u, answers, geo or {}, party_size)
        # Deep copy: nested fields (amenities, images, ...) must not be
        # shared with the caller's dict — a later mutation of a returned
        # item (e.g. Task 6 amenity scoring) must never corrupt bot.py's
        # cached listing snapshots.
        item = copy.deepcopy(u)
        item["match_score"] = int(round(total))
        item["reasons"] = reasons[:3]
        item["tradeoff"] = (tradeoffs[0] if tradeoffs else None)
        scored.append(item)

    # Stable, deterministic: best score first, ties broken by id ascending.
    scored.sort(key=lambda x: (-x["match_score"], _id_sort_key(x.get("id"))))

    best = scored[0]["match_score"] if scored else 0
    return {"top": scored[:top], "near": scored[top:],
            "confident": best >= CONFIDENCE_FLOOR,
            "impossible": False,
            "max_capacity": 0}


def _score_bedrooms(u, party_size, sleep_pref):
    """0.0-1.0 fit, plus a reason or a tradeoff. Exact match wins; over-provisioned
    is slightly worse (the guest pays for space they said they don't need);
    under-provisioned is heavily penalised but NEVER eliminated.

    `party_size` must already be a clean positive int (the same value the
    capacity gate used) — this function does not validate it.
    """
    need = required_bedrooms(party_size, sleep_pref)
    try:
        have = int(u.get("beds") or 0)
    except (TypeError, ValueError):
        have = 0
    if not have:
        return 0.5, None, None                      # unknown data scores neutral
    if have == need:
        return 1.0, f"{have} غرف نوم — بالضبط اللي طلبته", None
    if have > need:
        over = have - need
        return max(0.6, 1.0 - 0.12 * over), f"{have} غرف نوم — فيها زيادة راحة", None
    short = need - have
    return max(0.1, 0.55 - 0.18 * short), None, f"{have} غرف نوم بس — طلبت {need}"


def _score_quality(u):
    """0.0-1.0 from rating, shrunk toward the portfolio prior by review count."""
    try:
        rating = float(u.get("rating") or 0)
        n = int(u.get("reviews_count") or 0)
    except (TypeError, ValueError):
        return 0.5, None
    if rating <= 0 or n <= 0:
        return 0.5, None                            # unrated scores neutral, never punished
    smoothed = ((rating * n) + (PRIOR_RATING * PRIOR_WEIGHT)) / (n + PRIOR_WEIGHT)
    fit = max(0.0, min(1.0, (smoothed - 3.5) / 1.5))
    reason = None
    if rating >= 4.7 and n >= 10:
        reason = f"{rating} ★ من {n} تقييم"
    return fit, reason


def _score_one(u, answers, geo, party_size):
    """Returns (total_0_to_100, reasons, tradeoffs). Filled in across Tasks 3-6.

    `party_size` is the already-cleaned value from `score()` (see
    `_clean_party_size`) — never re-derive it from raw `answers` here, that
    reintroduces the fail-open-on-garbage-input bug the gate exists to avoid.
    """
    total = 0.0
    reasons, tradeoffs = [], []

    fit, reason, tradeoff = _score_bedrooms(u, party_size, answers.get("sleep_pref"))
    total += fit * WEIGHTS["bedrooms"]
    if reason:
        reasons.append(reason)
    if tradeoff:
        tradeoffs.append(tradeoff)

    # Proximity (Task 5) and budget/amenities (Task 6) insert their blocks here.

    qfit, qreason = _score_quality(u)
    total += qfit * WEIGHTS["quality"]
    if qreason:
        reasons.append(qreason)

    # Reason guarantee (invariant 4): a unit with nothing notable still says
    # something true rather than showing a bare card. MUST STAY LAST — every
    # scoring block above (and any Task 5/6 blocks) appends its own reason
    # first; later tasks must insert their blocks BEFORE this one, never after.
    if not reasons:
        cap = u.get("capacity")
        reasons.append(f"تستوعب {cap} ضيوف" if cap else "متاحة للحجز")

    return total, reasons, tradeoffs
