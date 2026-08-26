# -*- coding: utf-8 -*-
"""
cp.stats — every figure on /cp, and where it came from.

Three things are true at once on this page, and the design has to hold all three:

  1. Hardcoded numbers rot. A reviewer who cross-checks a stale figure stops
     trusting the rest of the page, so the numbers must refresh.
  2. A failed refresh must never show zeros, a blank, or a stack trace. The
     /business page already learned this the expensive way: a failed live fetch
     computes all-zeros, and persisting that quietly replaced good figures with
     nothing. So the seeds values are a FALLBACK, permanently, for every field.
  3. Four of the figures have no data source in this system at all — median
     response time, message volume, maintenance closed in SLA, headcount. The
     honest thing is not to wire them to a pipe that only looks live. They
     travel as `manual`, and seeds §8 sets the gate: a value, a date and a
     source, or it is not reported.

So every field carries its provenance, and `load()` returns cells, not scalars:

    {"reservations_total": {"value": 8114, "source": "seeds", "as_of": "2026-08-26"}}

The page renders the value AND the stamp. That source-stamping is the strongest
credibility device /business has, and it is the reason to extend it rather than
flatten everything into one "refreshed nightly" claim that is only half true.
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "data")

# The date the canonical export was compiled (seeds header). Fallback figures are
# true as of this date, and say so rather than borrowing the job's timestamp.
SEEDS_AS_OF = "2026-08-26"


def _load(name, default):
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    if isinstance(data, dict):   # strip the _note / _why_these commentary keys
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return data


FALLBACK = _load("cp_stats_fallback.json", {})
MARKET = _load("cp_market.json", {})
_MANUAL_RAW = _load("cp_manual.json", {})


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #
# hostaway — the nightly job recomputes it from the PMS
# manual   — hand-sourced, gated on value + as_of + source (seeds §8)
# seeds    — a company constant, not a measurement (capacity, time-to-live)
PROVENANCE = {
    "reservations_total": "hostaway", "nights_total": "hostaway",
    "occupancy_pct": "hostaway", "occupancy_active_pct": "hostaway",
    "occupancy_by_type": "hostaway",
    "adr_sar": "hostaway", "adr_90d_sar": "hostaway",
    "revpar_sar": "hostaway", "revpar_active_sar": "hostaway",
    "rating_avg": "hostaway", "reviews_total": "hostaway",
    "perfect_ten_pct": "hostaway", "category_scores": "hostaway",
    "repeat_booking_pct": "hostaway", "repeat_guests": "hostaway",
    "repeat_guest_share_pct": "hostaway", "top_guest_stays": "hostaway",
    "saudi_guest_pct": "hostaway", "gcc_guest_pct": "hostaway",
    "solo_guest_pct": "hostaway", "couple_guest_pct": "hostaway",
    "same_day_booking_pct": "hostaway", "within_24h_pct": "hostaway",
    "median_lead_time_days": "hostaway", "avg_stay_nights": "hostaway",
    "one_night_booking_pct": "hostaway", "long_stay_booking_pct": "hostaway",
    "long_stay_revenue_pct": "hostaway", "thu_fri_arrival_pct": "hostaway",
    "weekend_adr_premium_pct": "hostaway", "direct_stay_nights": "hostaway",
    "residences_total": "hostaway",

    "median_response_minutes": "manual", "messages_total": "manual",
    "messages_monthly_start": "manual", "messages_monthly_now": "manual",
    "maintenance_closed_in_sla": "manual", "team_headcount": "manual",
    "residences_per_person_per_day": "manual", "residences_per_custodian": "manual",

    "designed_capacity_residences": "seeds", "platform_lines_of_code": "seeds",
    "days_to_live_furnished": "seeds", "days_to_live_unfurnished": "seeds",
}

REQUIRED_MANUAL_FIELDS = ("value", "as_of", "source")


def valid_manual(raw=None):
    """Drop any hand-entered figure missing a value, a date or a source (seeds §8).

    Silent by design: a half-filled entry disappears from the page rather than
    rendering a number nobody can stand behind. The stats tests assert that every
    shipped entry is complete, so an incomplete one fails the build, not the page.
    """
    out = {}
    for key, entry in (_MANUAL_RAW if raw is None else raw).items():
        if not isinstance(entry, dict):
            continue
        if all(str(entry.get(f) if entry.get(f) is not None else "").strip()
               for f in REQUIRED_MANUAL_FIELDS):
            out[key] = entry
    return out


MANUAL = valid_manual()


# --------------------------------------------------------------------------- #
# rounding — the source documents are the spec (seeds §2, superprompt §6)
# --------------------------------------------------------------------------- #
# Explicit, not derived from the fallback's own precision: a reviewer checks
# these against the PDF, so the rule they are rounded by should be readable.
DECIMALS = {
    "occupancy_pct": 1, "occupancy_active_pct": 1, "perfect_ten_pct": 1,
    "gcc_guest_pct": 1, "median_response_minutes": 1,
    "residences_per_person_per_day": 1,
    "rating_avg": 2, "avg_stay_nights": 2, "direct_stay_nights": 2,
}
DEFAULT_DECIMALS = 0


def fmt(field, value, lang="en"):
    """Render one figure exactly as the source documents do.

    Seeds §10: Western numerals in BOTH editions — standard in Saudi business
    documents, and it keeps the comparison tables legible. `lang` is accepted so
    callers never have to decide, and so the rule lives in one place.
    """
    places = DECIMALS.get(field, DEFAULT_DECIMALS)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return ("{:,.%df}" % places).format(number)


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def _cell(value, source, as_of):
    return {"value": value, "source": source, "as_of": as_of}


def _is_empty(value):
    """A failed fetch computes zeros. Zero reservations is not a fact about this
    business, it is a fact about the network — so it never displaces a fallback."""
    if value is None:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 0
    if isinstance(value, (str, dict, list)):
        return len(value) == 0
    return False


def load(snapshot=None, manual=None):
    """Every figure, with its provenance. `snapshot` is cp_stats.json (or None).

    Overlay rules:
      * only `hostaway` fields can be overlaid by the nightly job,
      * only when the computed value is non-empty,
      * `manual` and `seeds` fields are never touched by the job, so a stray key
        in a snapshot cannot quietly restate a hand-sourced figure.
    """
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    manual = MANUAL if manual is None else valid_manual(manual)
    computed_at = snapshot.get("computed_at") or SEEDS_AS_OF

    out = {}
    for field, fallback in FALLBACK.items():
        kind = PROVENANCE.get(field, "seeds")

        if kind == "manual":
            entry = manual.get(field)
            if entry:
                out[field] = _cell(entry["value"], "manual", entry["as_of"])
            else:
                out[field] = _cell(fallback, "seeds", SEEDS_AS_OF)
            continue

        if kind == "hostaway":
            live = snapshot.get(field)
            if not _is_empty(live):
                out[field] = _cell(live, "hostaway", computed_at)
                continue

        out[field] = _cell(fallback, "seeds", SEEDS_AS_OF)

    return out


def sync_stamp(snapshot=None):
    """What the page's «refreshed» line is allowed to say.

    `live` is False when nothing came from the job — and then the page must not
    claim a nightly refresh. Defect §8.5 on /business was exactly this: the claim
    outlived the job.
    """
    cells = load(snapshot=snapshot)
    live = [c for c in cells.values() if c["source"] == "hostaway"]
    return {
        "live": bool(live),
        "as_of": (live[0]["as_of"] if live else SEEDS_AS_OF),
        "live_fields": len(live),
        "total_fields": len(cells),
    }
