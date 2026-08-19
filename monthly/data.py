# -*- coding: utf-8 -*-
"""
monthly.data — the ONLY file in this package that talks to Hostaway, and only
with GET. host.py wires no api_post and no api_put, so that is structural rather
than a promise.

CLAUDE.md TRAP #4 IS THE WHOLE REASON THIS FILE EXISTS SEPARATELY.
get_reservations_cached() truncates at ~6,000 rows and silently drops the NEWEST
months — it produced an owner statement of 18,842 where the truth was 48,114.
Every read here goes through fetch_reservations_window. A monthly price built on
a truncated history is a wrong price sent to an owner, and it would look
completely normal.

Everything this module produces is a plain dict handed to engine.py, which stays
pure. The split is what lets the arithmetic be argued with in a unit test while
the I/O is argued with here.
"""

import calendar
import datetime

from .host import HOST

# Mirrors bot.py's CONFIRMED_STATUSES / _REPORT_CANCELLED. Duplicated
# DELIBERATELY and temporarily: wiring them through host.py needs a bot.py edit,
# and every bot.py change is batched into one announced edit at S14 rather than
# dripped into a 3.9 MB file three sessions are editing at once. Fold these into
# the wiring block then.
CONFIRMED_STATUSES = {"new", "modified"}
CANCELLED_STATUSES = {"cancelled", "canceled", "declined", "expired", "denied"}

YEARS_BACK = 3


def _d(s):
    try:
        y, m, d = str(s)[:10].split("-")
        return datetime.date(int(y), int(m), int(d))
    except (ValueError, AttributeError, TypeError):
        return None


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def month_key(d):
    return "%04d-%02d" % (d.year, d.month)


def months_between(a_key, b_key):
    ay, am = int(a_key[:4]), int(a_key[5:7])
    by, bm = int(b_key[:4]), int(b_key[5:7])
    return (by - bm // 13) * 12 + bm - (ay * 12 + am)


def month_bounds(key):
    y, m = int(key[:4]), int(key[5:7])
    return datetime.date(y, m, 1), datetime.date(y, m, calendar.monthrange(y, m)[1])


def is_confirmed(res):
    st = str((res or {}).get("status") or "").strip().lower()
    if st in CANCELLED_STATUSES:
        return False
    return st in CONFIRMED_STATUSES


def nights_in_month(res, first, last):
    """Booked nights of THIS reservation that fall inside [first, last].

    A night belongs to the date it starts on, so the departure date is excluded —
    the guest does not sleep that night. Counting it would inflate occupancy on
    every stay that straddles a month end.
    """
    ci, co = _d(res.get("arrivalDate")), _d(res.get("departureDate"))
    if not ci or not co or co <= ci:
        return 0
    lo = max(ci, first)
    hi = min(co - datetime.timedelta(days=1), last)
    return max(0, (hi - lo).days + 1)


def unit_month_rows(reservations, target_month_num, today_key):
    """Realized (ADR, occupancy) per unit per matching CALENDAR MONTH.

    Only months whose NUMBER matches the target — October is compared with
    Octobers. Ramadan and the summer trough are large enough in Riyadh that a
    flat twelve-month average overprices July and underprices Riyadh Season.
    """
    buckets = {}
    for r in (reservations or []):
        if not is_confirmed(r):
            continue
        lid = r.get("listingMapId")
        ci, co = _d(r.get("arrivalDate")), _d(r.get("departureDate"))
        if lid is None or not ci or not co:
            continue
        total = _num(r.get("totalPrice"))
        stay_nights = (co - ci).days
        if not total or stay_nights <= 0:
            continue
        adr_of_stay = total / float(stay_nights)

        d = datetime.date(ci.year, ci.month, 1)
        while d <= co:
            key = month_key(d)
            if int(key[5:7]) == int(target_month_num):
                first, last = month_bounds(key)
                n = nights_in_month(r, first, last)
                if n > 0:
                    b = buckets.setdefault((int(lid), key), {"nights": 0, "revenue": 0.0})
                    b["nights"] += n
                    b["revenue"] += adr_of_stay * n
            d = (datetime.date(d.year + (d.month // 12), (d.month % 12) + 1, 1))

    out = {}
    for (lid, key), b in buckets.items():
        first, last = month_bounds(key)
        days = (last - first).days + 1
        age = months_between(key, today_key)
        out.setdefault(lid, []).append({
            "month": key,
            "adr": b["revenue"] / b["nights"],
            "occ": min(1.0, b["nights"] / float(days)),
            "nights": b["nights"],
            "months_old": max(0, age),
            # A month still running has unsold nights that may yet sell, so its
            # occupancy reads LOW. Mixing it into a weighted average biases the
            # forecast downward, which widens the price band and makes monthly
            # look more viable than it is — the wrong direction to be wrong in.
            # Flagged here; collect.py drops it and reports how many it dropped.
            "partial": age <= 0,
        })
    for lid in out:
        out[lid].sort(key=lambda o: o["month"], reverse=True)
    return out


def pool_rows(unit_rows, unit_meta, district_of, bedrooms_of):
    """(district, bedrooms) and bedrooms-only pools, built from the same rows."""
    district, bedroom = {}, {}
    for lid, rows in (unit_rows or {}).items():
        meta = (unit_meta or {}).get(lid) or {}
        d = district_of(meta)
        b = bedrooms_of(meta)
        for r in rows:
            if d is not None and b is not None:
                district.setdefault((d, b), []).append(r)
            if b is not None:
                bedroom.setdefault(b, []).append(r)
    return district, bedroom


# ───────────────────────────── the live pulls ─────────────────────────────

def fetch_history(target_month, years_back=YEARS_BACK, today=None):
    """Every confirmed reservation that can touch the matching calendar months of
    the last `years_back` years. fetch_reservations_window ONLY."""
    today = today or datetime.date.today()
    m = int(str(target_month)[5:7])
    rows, seen = [], set()
    for back in range(0, years_back + 1):
        y = today.year - back
        try:
            first = datetime.date(y, m, 1)
        except ValueError:
            continue
        last = datetime.date(y, m, calendar.monthrange(y, m)[1])
        if first > today:
            continue
        got = HOST.require("fetch_reservations_window")(first, last) or []
        for r in got:
            rid = r.get("id")
            if rid in seen:
                continue
            seen.add(rid)
            rows.append(r)
    return rows


def turnover_cost_sar(fallback):
    """The real derived cost of one clean, from the cleaning coverage study —
    fully-loaded payroll divided by our own checkouts, NOT a settings default.

    A floor built on a too-cheap clean is a floor that is too low, and the floor
    is the one number in this engine we tell owners is safe. Returns
    (value, source) so the report can say which it used rather than implying the
    real one when it fell back.
    """
    try:
        from coverage_study import engine as cs
        study = cs.build_study() if hasattr(cs, "build_study") else None
        per = ((study or {}).get("cost") or {}).get("inhouse_per_clean")
        if per and float(per) > 0:
            return float(per), "coverage_study.inhouse_per_clean"
    except Exception:
        pass
    return float(fallback), "default (coverage_study unavailable)"
