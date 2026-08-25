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

# An inquiry is a QUESTION, not a sale. The first live run swept 3,818 of them into the
# comparison and then wondered why the calendar had no nights for them — of course it
# didn't, nobody ever booked. They are counted in `meta` and excluded from the maths.
NOT_A_SALE = ("inquiry", "inquirynotpossible", "inquirypreapproved",
              "inquirytimeout", "awaitingguestverification", "unavailable")

# Days per calendar request. One 6-month request is far likelier to be refused or
# truncated than six 1-month ones.
CAL_CHUNK_DAYS = 31

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


def _read_calendar(lid, start, end):
    """Calendar days for one listing, in chunks, WITHOUT swallowing failures.

    bot.py's fetch_calendar_days catches its own exceptions and returns [] — perfect
    for a dashboard tile, fatal here: the first live run turned 55 failed calendar
    reads into "every booking matches". This calls the API directly so a failure
    raises and is reported, and splits long spans because one 6-month request is far
    likelier to be refused than six 1-month ones."""
    api_get = HOST.require("api_get")
    out, cur = [], start
    while cur <= end:
        stop = min(cur + timedelta(days=CAL_CHUNK_DAYS - 1), end)
        data = api_get("/listings/%s/calendar" % lid,
                       params={"startDate": cur.isoformat(), "endDate": stop.isoformat()})
        rows = (data or {}).get("result") or []
        if isinstance(rows, dict):          # some payloads nest the days one level down
            rows = rows.get("days") or rows.get("calendar") or []
        out.extend(rows)
        cur = stop + timedelta(days=1)
    return out


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
    api_get = HOST.require("api_get")
    listings = {}
    try:
        listings = HOST.get_listings_map() or {}
    except Exception:
        listings = {}

    raw = fetch_res(start, end) or []
    keep, odd_statuses, not_a_sale = [], {}, {}
    for r in raw:
        st = (r.get("status") or "").lower()
        if st in CANCELLED and not include_cancelled:
            continue
        if st in NOT_A_SALE:
            not_a_sale[st] = not_a_sale.get(st, 0) + 1
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
    # Per-listing evidence about what the calendar ACTUALLY returned. Without this the
    # first live run reported "everything matches" while every calendar had come back
    # empty — a silent empty read is indistinguishable from agreement, so it must be
    # counted and shown. days_seen=0 means the read failed; days_seen>0 with
    # days_with_res=0 means Hostaway does not put reservationId on these days.
    cal_stats = {}

    def _one(item):
        li, (lo, hi) = item
        try:
            days = _read_calendar(li, lo, hi - timedelta(days=1))
            return li, days, None
        except Exception as e:
            return li, [], "%s: %s" % (type(e).__name__, e)

    if spans:
        with ThreadPoolExecutor(max_workers=CAL_WORKERS) as ex:
            for li, days, err in ex.map(_one, list(spans.items())):
                cal_by_lid[li] = days or []
                cal_stats[li] = {
                    "days_seen": len(days or []),
                    "days_with_res": sum(1 for d in (days or []) if d.get("reservationId")),
                    "day_keys": sorted((days or [{}])[0].keys()) if days else [],
                }
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
            "unrecognised_statuses": odd_statuses, "not_a_sale": not_a_sale,
            "calendar_days_seen": sum(v["days_seen"] for v in cal_stats.values()),
            "calendar_days_with_reservation": sum(v["days_with_res"] for v in cal_stats.values()),
            "calendar_blind_listings": sorted(li for li, v in cal_stats.items()
                                              if v["days_seen"] == 0),
            "calendar_day_keys": sorted({k for v in cal_stats.values() for k in v["day_keys"]}),
            "deep_fetched": deep_done, "deep_errors": deep_errors[:10],
            "deep_capped": bool(deep and len(keep) > DEEP_MAX),
            "read_only": True,
        },
    }


def probe(reservation_id):
    """Everything Hostaway will tell us about ONE booking, raw and uninterpreted.

    Exists because the portfolio scan can only say "these two numbers differ" — it
    cannot say WHERE a third number lives. The owner can see SAR 644 in Financial
    Reporting for a booking whose own record says SAR 530; this dumps every field on
    the reservation and every field on each of its calendar days so that 644 can be
    found by looking instead of by guessing. Read-only, one booking, no filtering."""
    api_get = HOST.require("api_get")
    out = {"id": reservation_id, "read_only": True}
    try:
        res = (api_get("/reservations/%s" % reservation_id) or {}).get("result")
    except Exception as e:
        return {**out, "error": "%s: %s" % (type(e).__name__, e)}
    if not isinstance(res, dict) or not res:
        return {**out, "error": "not_found",
                "message": "ما لقينا حجز بهذا الرقم"}

    money = engine.harvest_money(res)
    lid = res.get("listingMapId")
    ci, co = res.get("arrivalDate"), res.get("departureDate")
    out.update({
        "guest": (res.get("guestName") or "").strip(),
        "listing": res.get("listingName") or "", "lid": lid,
        "channel": res.get("channelName") or res.get("channel") or "",
        "status": res.get("status"), "checkin": ci, "checkout": co,
        "money": money,
        # Every key the payload carries, so a money field we do not yet recognise is
        # still visible rather than quietly filtered out by the money-word rule.
        "all_keys": sorted(res.keys()),
        "non_money_numbers": {k: v for k, v in res.items()
                              if isinstance(v, (int, float)) and not isinstance(v, bool)
                              and k not in money},
    })
    try:
        a, b = _d(ci), _d(co)
        days = _read_calendar(lid, a, b - timedelta(days=1)) if (lid and b > a) else []
        out["calendar_days"] = days
        out["calendar_matched"] = engine.calendar_slice(days, reservation_id, ci, co)
    except Exception as e:
        out["calendar_error"] = "%s: %s" % (type(e).__name__, e)
        out["calendar_days"] = []
    return out
