"""Stay Match scoring engine. PURE — no I/O, no network, no clock reads.

The contract that makes this feature work: search FILTERS and can return zero;
this engine SCORES and returns the best available fit. Only physically-true
constraints eliminate a unit. Everything else lowers a score and produces an
honest tradeoff string the UI shows to the guest.
"""

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

TOP_N = 3


def required_bedrooms(party_size, sleep_pref):
    """How many bedrooms the guest's own answers imply."""
    if party_size <= 2:
        return 1
    if sleep_pref == "together":
        return 1
    if sleep_pref == "each":
        return party_size
    # "pairs" and the None default: two per room, rounded up.
    return max(1, -(-party_size // 2))


def _passes_hard_gates(u, answers, dated):
    """Only physically-true constraints. Unknown data never eliminates a unit."""
    cap = u.get("capacity")
    if cap:
        try:
            if int(cap) < int(answers.get("party_size") or 1):
                return False
        except (TypeError, ValueError):
            pass
    if dated and u.get("available") is False:
        return False
    return True


def score(answers, units, geo=None, top=TOP_N):
    """Rank units by fit. See the plan's data contract for shapes."""
    answers = answers or {}
    units = list(units or [])
    dated = bool(answers.get("check_in") and answers.get("check_out"))

    eligible = [u for u in units if _passes_hard_gates(u, answers, dated)]

    if not eligible:
        caps = []
        for u in units:
            try:
                caps.append(int(u.get("capacity") or 0))
            except (TypeError, ValueError):
                continue
        return {"top": [], "near": [], "confident": False,
                "impossible": bool(units), "max_capacity": (max(caps) if caps else 0)}

    scored = []
    for u in eligible:
        total, reasons, tradeoffs = _score_one(u, answers, geo or {})
        item = dict(u)
        item["match_score"] = int(round(total))
        item["reasons"] = reasons[:3]
        item["tradeoff"] = (tradeoffs[0] if tradeoffs else None)
        scored.append(item)

    # Stable, deterministic: best score first, ties broken by id ascending.
    scored.sort(key=lambda x: (-x["match_score"], x.get("id") or 0))

    best = scored[0]["match_score"] if scored else 0
    return {"top": scored[:top], "near": scored[top:],
            "confident": best >= CONFIDENCE_FLOOR,
            "impossible": False,
            "max_capacity": 0}


def _score_one(u, answers, geo):
    """Returns (total_0_to_100, reasons, tradeoffs). Filled in across Tasks 3-6."""
    total = 0.0
    reasons, tradeoffs = [], []
    return total, reasons, tradeoffs
