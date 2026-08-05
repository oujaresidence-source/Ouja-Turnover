# -*- coding: utf-8 -*-
"""
pricecheck.scan — the only part that touches Hostaway. READ-ONLY: every call in this
file is a GET. Nothing here writes a price, a calendar day, or a reservation.

It pulls the bookings in a window with fetch_reservations_window (CLAUDE.md trap #4 —
the cached full-history pull silently drops the newest months and must never be used
for a money question), pulls each listing's calendar ONCE for the whole window, and
hands both to the pure engine.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import engine
from .host import HOST

CONFIRMED = ("new", "modified", "ownerstay", "awaitingpayment")
CANCELLED = ("cancelled", "canceled", "declined", "expired", "denied")

# How many listing calendars to fetch at once. Small on purpose: Hostaway answers 429
# under load and api_get's backoff would turn a burst into a slow scan, not a fast one.
CAL_WORKERS = 6

# Cap on the per-reservation detail fetches in deep mode. Deep mode exists to reveal the
# `financeField` breakdown that the list endpoint omits; it costs one API call per row.
DEEP_MAX = 120


def _d(s):
    y, m, dd = str(s)[:10].split("-")
    return date(int(y), int(m), int(dd))


def _channel_of(r):
    """direct / airbnb / other — same reading as bot.py's _finance_channel, kept local
    so this package has no dependency on bot.py's internals."""
    ch = (r.get("channelName") or r.get("channel") or "").strip().lower()
    if "airbnb" in ch:
        return "airbnb"
    if (not ch) or any(w in ch for w in ("direct", "manual", "website", "owner", "walk")):
        return "direct"
    return "other"


def _overlaps(r, start, end):
    try:
        a, b = _d(r.get("arrivalDate")), _d(r.get("departureDate"))
    except (ValueError, AttributeError, TypeError):
        return False
    return a < end and b > start          # any shared night


def scan(start, end, channel="direct", lid=None, include_cancelled=False, deep=False):
    """Compare every booking whose stay touches [start, end) against the calendar.

    Returns {rows, ranking, listings, meta}. `ranking` is the measured answer to "which
    Hostaway field is «Rental Revenue»" — see engine.field_agreement."""
    fetch_res = HOST.require("fetch_reservations_window")
    fetch_cal = HOST.require("fetch_calendar_days")
    api_get = HOST.require("api_get")
    listings = {}
    try:
        listings = HOST.get_listings_map() or {}
    except Exception:
        listings = {}

    raw = fetch_res(start, end) or []
    keep, odd_statuses = [], {}
    for r in raw:
        st = (r.get("status") or "").lower()
        if st in CANCELLED and not include_cancelled:
            continue
        if st not in CONFIRMED and st not in CANCELLED:
            # An unrecognised status is KEPT, not dropped — silently discarding money is
            # the exact class of bug this tool exists to find. It is counted in `meta`
            # so an unexpected status shows up as a number instead of as nothing.
            odd_statuses[st] = odd_statuses.get(st, 0) + 1
        if channel != "all" and _channel_of(r) != channel:
            continue
        if lid is not None and str(r.get("listingMapId")) != str(lid):
            continue
        if not _overlaps(r, start, end):
            continue
        keep.append(r)

    # ---- calendars: ONE call per listing, covering that listing's whole span ----
    spans = {}
    for r in keep:
        li = r.get("listingMapId")
        if li is None:
            continue
        a, b = _d(r["arrivalDate"]), _d(r["departureDate"])
        lo, hi = spans.get(li, (a, b))
        spans[li] = (min(lo, a), max(hi, b))

    cal_by_lid, cal_errors = {}, []

    def _one(item):
        li, (lo, hi) = item
        try:
            return li, fetch_cal(li, lo, hi - timedelta(days=1)), None
        except Exception as e:
            return li, [], "%s: %s" % (type(e).__name__, e)

    if spans:
        with ThreadPoolExecutor(max_workers=CAL_WORKERS) as ex:
            for li, days, err in ex.map(_one, list(spans.items())):
                cal_by_lid[li] = days or []
                if err:
                    cal_errors.append({"lid": li, "error": err[:200]})

    # ---- optional: the per-reservation detail, for the finance breakdown ----
    deep_done, deep_errors = 0, []
    if deep:
        for r in keep[:DEEP_MAX]:
            try:
                full = (api_get("/reservations/%s" % r.get("id")) or {}).get("result")
                if isinstance(full, dict):
                    r.update(full)
                    deep_done += 1
            except Exception as e:
                deep_errors.append({"id": r.get("id"), "error": str(e)[:160]})

    rows = []
    for r in keep:
        row = engine.compare_row(r, cal_by_lid.get(r.get("listingMapId"), []))
        if not row["listing"]:
            row["listing"] = listings.get(row["lid"]) or ("unit-%s" % row["lid"])
        rows.append(row)

    ranking = engine.field_agreement(rows)
    rows.sort(key=lambda x: (x["status"] != "differs", x["checkin"] or ""))
    return {
        "rows": rows,
        "ranking": ranking,
        "listings": sorted({(x["lid"], x["listing"]) for x in rows if x["lid"] is not None}),
        "meta": {
            "start": start.isoformat(), "end": end.isoformat(),
            "channel": channel, "lid": lid, "deep": bool(deep),
            "fetched": len(raw), "compared": len(keep),
            "listings_scanned": len(spans), "calendar_errors": cal_errors,
            "unrecognised_statuses": odd_statuses,
            "deep_fetched": deep_done, "deep_errors": deep_errors[:10],
            "deep_capped": bool(deep and len(keep) > DEEP_MAX),
            "read_only": True,
        },
    }
