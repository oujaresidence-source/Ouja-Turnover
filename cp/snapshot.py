# -*- coding: utf-8 -*-
"""
cp.snapshot — the nightly refresher for cp_stats.json.

    Hostaway ─► fetch (business.metrics.fetch_snapshot) ─► compute ─► sanity ─► cp_stats.json

Scope, and why it is narrow on purpose: v1 refreshes only the figures whose
methodology is unambiguous from reservation and review rows — counts, nights,
repeat rates, weekday shares, review scores. Occupancy, ADR and RevPAR are NOT
refreshed: the published 76.9 / 582 / 451 follow the owner's export
methodology, and a page that invites a reviewer to check its numbers must not
print a value computed a different way. Those fields keep their seeds value and
their honest «as of» stamp until that computation exists and reconciles.

Between compute and write sits `apply_sanity`: totals must not shrink (the
dataset only grows — a smaller number means a partial fetch), shares must sit
inside wide-but-real bands, and a field this job does not own never passes.
Nothing surviving means nothing written; a good snapshot is never overwritten
by a bad night. cp.stats then overlays only non-empty values, and cp.guard
scans the rendered page — three fences, each independent of the other two.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from . import stats

CONFIRMED = ("new", "modified")

# Fields this job owns. Anything else is dropped by apply_sanity, so a future
# edit to compute() cannot quietly start publishing a figure nobody reviewed.
OWNED = ("reservations_total", "nights_total", "avg_stay_nights",
         "one_night_booking_pct", "repeat_guests", "repeat_booking_pct",
         "thu_fri_arrival_pct", "reviews_total", "rating_avg",
         "perfect_ten_pct", "category_scores")

# floor = the seeds value: totals are monotonic over a growing dataset.
_SEED = stats.FALLBACK


def _bands(seeds=None):
    s = seeds if seeds is not None else _SEED
    return {
        "reservations_total": (s.get("reservations_total", 0), None),
        "nights_total": (s.get("nights_total", 0), None),
        "reviews_total": (s.get("reviews_total", 0), None),
        "repeat_guests": (s.get("repeat_guests", 0), None),
        "avg_stay_nights": (1.0, 5.0),
        "one_night_booking_pct": (40, 90),
        "repeat_booking_pct": (20, 60),
        "thu_fri_arrival_pct": (15, 60),
        "rating_avg": (4.5, 5.0),
        "perfect_ten_pct": (70, 100),
    }


def _round(x, places=0):
    """Half-up, the way the published figures round — Python's round() is
    banker's (4.625 -> 4.62) and would print a rating no reviewer reproduces."""
    q = Decimal(1).scaleb(-places)
    v = float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))
    return int(v) if places == 0 else v


def _days(a, b):
    try:
        d = (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days
        return d if d > 0 else 0
    except (TypeError, ValueError):
        return 0


def compute(raw):
    """Figures from normalized reservation/review rows (the business.metrics
    `raw` contract). Rounding matches the seeds file exactly — cp.stats.fmt is
    the display authority, but stored values are already at source precision."""
    out = {}
    res = [r for r in (raw.get("reservations") or [])
           if r.get("status") in CONFIRMED]
    n = len(res)
    if n:
        nights = [_days(r.get("arrival"), r.get("departure")) for r in res]
        total_nights = sum(nights)
        out["reservations_total"] = n
        out["nights_total"] = total_nights
        out["avg_stay_nights"] = _round(total_nights / n, 2)
        out["one_night_booking_pct"] = _round(
            100.0 * sum(1 for x in nights if x == 1) / n)

        by_guest = {}
        for r in res:
            by_guest.setdefault(r.get("guest_key"), []).append(r)
        repeat_guests = [g for g, rows in by_guest.items() if len(rows) >= 2]
        out["repeat_guests"] = len(repeat_guests)
        repeat_bookings = sum(len(by_guest[g]) for g in repeat_guests)
        out["repeat_booking_pct"] = _round(100.0 * repeat_bookings / n)

        thu_fri = 0
        for r in res:
            try:
                if datetime.strptime(r["arrival"], "%Y-%m-%d").weekday() in (3, 4):
                    thu_fri += 1
            except (KeyError, TypeError, ValueError):
                pass
        out["thu_fri_arrival_pct"] = _round(100.0 * thu_fri / n)

    reviews = [v for v in (raw.get("reviews") or []) if v.get("public", True)]
    rated = [v["rating10"] for v in reviews if v.get("rating10") is not None]
    if reviews:
        out["reviews_total"] = len(reviews)
    if rated:
        out["rating_avg"] = _round(sum(rated) / len(rated) / 2, 2)
        out["perfect_ten_pct"] = _round(
            100.0 * sum(1 for x in rated if x == 10) / len(rated), 1)
        cats = {}
        for v in reviews:
            for name, score in (v.get("categories") or {}).items():
                cats.setdefault(name, []).append(score)
        if cats:
            out["category_scores"] = {
                name: _round(sum(xs) / len(xs), 2) for name, xs in cats.items()}

    out["computed_at"] = (raw.get("as_of") or datetime.utcnow().date().isoformat()) \
        + "T03:00:00+03:00"
    return out


def apply_sanity(computed, seeds=None):
    """Keep only owned, in-band fields. Silent about what it drops by design —
    the build result reports counts, and the seeds value simply keeps rendering."""
    bands = _bands(seeds)
    out = {}
    for field, value in (computed or {}).items():
        if field == "computed_at":
            continue
        if field not in OWNED:
            continue
        if field == "category_scores":
            if isinstance(value, dict) and value and all(
                    isinstance(v, (int, float)) and 8.0 <= v <= 10.0
                    for v in value.values()):
                out[field] = value
            continue
        lo, hi = bands.get(field, (None, None))
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if lo is not None and v < lo:
            continue
        if hi is not None and v > hi:
            continue
        out[field] = value
    return out


def build_and_write(fetch=None, save_json=None, seeds=None):
    """Fetch -> compute -> sanity -> write cp_stats.json. Never raises; never
    writes when nothing survives. Returns a small report dict."""
    result = {"ok": False, "kept": 0, "dropped": 0, "error": None}
    try:
        if fetch is None:
            from business import metrics as _bm
            raw = _bm.fetch_snapshot()
        else:
            raw = fetch()
        computed = compute(raw)
        gated = apply_sanity(computed, seeds=seeds)
        result["dropped"] = max(0, len([k for k in computed if k != "computed_at"])
                                - len(gated))
        if not gated:
            result["error"] = "nothing_survived_sanity"
            return result
        gated["computed_at"] = computed.get("computed_at")
        if save_json is None:
            import bot
            save_json = bot._save_json
        save_json("cp_stats.json", gated)
        result["kept"] = len(gated) - 1
        result["ok"] = True
    except Exception as exc:                      # the nightly loop must survive
        result["error"] = repr(exc)
    return result
