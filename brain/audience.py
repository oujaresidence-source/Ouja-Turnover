"""
brain.audience — turn the chosen campaign + signals into the exact governed member list.

Pipeline (build spec section 8): eligibility (target tiers, not excluded) -> match score
(heuristic, pluggable) -> Governor -> demand-matched cap (Appendix B). The cap is what
keeps it un-naggy: volume is derived from OPEN INVENTORY, never from the size of the list.

    needed_bookings = ceil(nights_to_fill / avg_nights_per_booking)
    N_messages      = ceil(needed_bookings / conv_per_msg * buffer)
    N_final         = min(N_messages, eligible_after_governor, remaining_today_cap)
"""

import math
from . import settings, members, governor, campaigns
from .host import HOST
from .util import parse_date, now_dt

_TIER_W = {"Turaif": 3, "Gold": 2, "Silver": 1, "Quarantine": 0}


def _recency_days(m):
    d = parse_date(m.get("last_stay_date"))
    if not d:
        return None
    return (now_dt().date() - d).days


def _match_score(m, trigger_type):
    """Higher = better fit. Tier + frequency + recency, with a win-back inversion."""
    score = _TIER_W.get(m.get("tier"), 1) * 2.0
    score += min(int(m.get("stays_count") or 0), 10) * 0.5
    rd = _recency_days(m)
    if trigger_type == "winback_dormant":
        # dormant guests are the POINT of win-back: older last stay scores higher
        if rd is None:
            score += 1
        elif rd > 365:
            score += 4
        elif rd > 180:
            score += 2.5
        elif rd > 90:
            score += 1
    else:
        if rd is None:
            score += 0
        elif rd <= 90:
            score += 3
        elif rd <= 180:
            score += 2
        elif rd <= 365:
            score += 1
    # spend nudge (engaged, higher-value members first), small weight
    score += min(float(m.get("total_spend") or 0) / 5000.0, 2.0)
    return round(score, 3)


def _estimate_adr():
    """Rough average nightly rate from the cached forward calendar; safe fallback."""
    try:
        cal = HOST.get_forward_calendar(14, 1200) if HOST.get_forward_calendar else []
        prices = [d.get("avg_price") for d in (cal or []) if d.get("avg_price")]
        if prices:
            return round(sum(prices) / len(prices))
    except Exception:
        pass
    return 450


def demand_cap(nights_to_fill, eligible_after_gov):
    conv = max(settings.get_float("expected_bookings_per_message"), 0.001)
    avg_nights = max(settings.get_float("avg_nights_per_booking"), 1.0)
    buffer = max(settings.get_float("audience_buffer"), 1.0)
    needed_bookings = math.ceil(max(nights_to_fill, 0) / avg_nights) if nights_to_fill > 0 else 0
    n_messages = math.ceil(needed_bookings / conv * buffer) if needed_bookings > 0 else 0
    remaining = governor.remaining_today()
    n_final = min(n_messages, eligible_after_gov, remaining)
    return {"needed_bookings": needed_bookings, "n_messages": n_messages,
            "remaining_today": remaining, "n_final": max(0, n_final),
            "conv": conv, "avg_nights": avg_nights, "buffer": buffer}


def build_audience(decision):
    """decision = campaigns.select_campaign(signals). Returns the full audience package."""
    code = decision.get("code")
    camp = campaigns.get_campaign(code) if code else None
    if not camp:
        return {"code": code, "audience": [], "audience_ids": [], "audience_size": 0,
                "excluded": [], "pool_size": 0, "eligible_after_governor": 0,
                "demand": demand_cap(0, 0), "projected": {"replies": 0, "bookings": 0, "revenue": 0}}

    tier_targets = camp.get("tier_targets", [])
    trigger_type = camp.get("trigger_type", "")
    pool = members.eligible_pool(tier_targets)
    screened = governor.screen(pool, code)
    eligible = screened["included"]

    for m in eligible:
        m["_score"] = _match_score(m, trigger_type)
    eligible.sort(key=lambda m: m["_score"], reverse=True)

    cap = demand_cap(decision.get("nights_to_fill", 0), len(eligible))
    n_final = cap["n_final"]
    chosen = eligible[:n_final]

    conv = cap["conv"]
    adr = _estimate_adr()
    projected_bookings = round(n_final * conv, 1)
    projected_replies = round(n_final * max(conv * 3.0, 0.10), 1)   # estimate; auto-learned in Phase 2
    projected_revenue = round(projected_bookings * cap["avg_nights"] * adr)

    return {
        "code": code,
        "campaign": camp,
        "tier_targets": tier_targets,
        "pool_size": len(pool),
        "eligible_after_governor": len(eligible),
        "excluded": screened["excluded"],
        "audience": [{"id": m["id"], "first_name": m.get("first_name"), "phone": m.get("phone"),
                      "tier": m.get("tier"), "stays": m.get("stays_count"),
                      "score": m.get("_score")} for m in chosen],
        "audience_ids": [m["id"] for m in chosen],
        "audience_size": n_final,
        "demand": cap,
        "adr": adr,
        "projected": {"replies": projected_replies, "bookings": projected_bookings,
                      "revenue": projected_revenue},
    }
