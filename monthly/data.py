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


def turnover_cost_sar(fallback, load_json=None):
    """The cost of one clean, and WHERE IT CAME FROM.

    An earlier version of this called coverage_study.build_study() — a function
    that does not exist. hasattr() returned False, the call silently fell through
    to the default, and the report said "default (coverage_study unavailable)"
    which read like a transient outage rather than an invented API. The real
    entry point is coverage_study.engine.study(), which needs live teams, status
    logs, reports and photos rebuilt per request and is not cached anywhere, so
    this module cannot reach it without becoming a second copy of that pipeline.

    So the number is an OWNER SETTING, read from monthly_settings.json, and the
    source string always says which of the two it used. This is load-bearing for
    every floor on the page: at occ 0.85 each riyal on the true cost of a clean
    moves the floor by -7.79 riyals, so a wrong default is not a rounding error.
    """
    if load_json:
        try:
            cfg = load_json("monthly_settings.json", None) or {}
            v = cfg.get("turnover_cost_sar")
            if v is not None and float(v) > 0:
                return float(v), "monthly_settings.json (owner-set)"
        except (TypeError, ValueError, AttributeError):
            pass
    return float(fallback), ("DEFAULT %s — nobody has entered the real per-clean "
                             "cost; read it off the cleaning coverage page and set "
                             "turnover_cost_sar in monthly_settings.json" % fallback)


def listing_meta(api_get, kb_district=None):
    """Real per-listing metadata, read straight from Hostaway.

    get_listings_map() returns {id: name} — a STRING, not a record. collect.py
    wrapped it as {"name": ...}, so district and bedrooms came out None for every
    unit, both pools were built empty, and the fallback ladder had no rungs. That
    is why zero units were 'on fallback': the path could not execute, not that it
    was not needed.

    Inactive listings are dropped here. A unit that has not operated since 2024
    should not sit in the denominator making the percentages mean less than they
    appear to.
    """
    out, limit, offset = {}, 100, 0
    while True:
        data = api_get("/listings", params={"limit": limit, "offset": offset}) or {}
        batch = data.get("result", []) or []
        for L in batch:
            lid = L.get("id")
            if lid is None:
                continue
            if not _is_active(L):
                continue
            try:
                lid = int(lid)
            except (TypeError, ValueError):
                continue
            district = None
            if kb_district:
                try:
                    district = kb_district(lid)
                except Exception:
                    district = None
            out[lid] = {
                "name": (L.get("internalListingName") or L.get("name") or "").strip(),
                "bedrooms": L.get("bedroomsNumber"),
                "district": district or (L.get("city") or L.get("address") or "").strip() or None,
                "district_source": "kb" if district else "hostaway_city",
                "status": L.get("status"),
            }
        if len(batch) < limit:
            break
        offset += limit
    return out


# Mirrors bot.py's _listing_active: the red no-entry sign in Hostaway.
_INACTIVE_WORDS = ("inactive", "disabled", "unlisted", "delisted", "deleted",
                   "draft", "paused", "off")


def _is_active(L):
    v = (L or {}).get("status")
    if isinstance(v, str) and v.lower() in _INACTIVE_WORDS:
        return False
    if v in (0, "0", False):
        return False
    for key in ("isActive", "listed", "active", "isListed"):
        if key in (L or {}) and L.get(key) in (0, "0", False):
            return False
    return True
