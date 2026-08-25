# -*- coding: utf-8 -*-
"""
pricecheck.engine — PURE comparison rules for «فحص الأسعار». No network, no database,
no import of bot.py. Every number here is reachable from a unit test.

WHAT IT IS FOR
An employee creates a manual direct booking in the Hostaway mobile app and edits the
price. Afterwards the Calendar shows one number and Financial Reporting → Rental
Activity → «Rental Revenue» shows another for the same stay. The owner's rule
(2026-08-05): THE CALENDAR IS THE TRUTH.

TWO RULES THAT MUST NOT BE SOFTENED

1. A night counts only when the calendar says it belongs to THIS reservation. If any
   night of the stay is missing or is owned by a different reservation, the row is
   «uncertain» and NO difference is produced. A confident-looking wrong difference is
   worse than a blank: it sends a human to correct a price that was already right.

2. Nothing here hardcodes which Hostaway field is «Rental Revenue». `harvest_money`
   collects every money-shaped field the payload actually carries, `compare_row`
   records which of them equal the calendar, and `field_agreement` ranks them across
   the whole portfolio. The field that tracks the calendar on hundreds of healthy
   bookings identifies itself — we read it off real data instead of guessing, which is
   the same discipline the payout/paid-basis probes in bot.py already follow.
"""

from datetime import date, timedelta

# Riyal tolerance. Hostaway rounds; half a riyal is rounding, not a wrong price.
TOL = 0.5

# A field is money if its name says money...
_MONEY_WORDS = ("price", "total", "amount", "rate", "revenue", "payout", "paid", "fee",
                "balance", "charge", "net", "gross", "tax", "discount", "commission",
                "refund", "earning", "cost", "payment", "deposit")

# ...and is not one of these, which are money-shaped words attached to non-money values.
_NOT_MONEY = ("count", "number", "guests", "adults", "children", "infants", "pets",
              "nights", "percent", "version", "phone", "zip", "status", "currency",
              "type", "date", "time")

# Keys used to read a name and an amount out of one entry of a breakdown array
# (Hostaway's `financeField`). Read defensively — the exact key set is confirmed
# against live data by the scan's `deep` mode, never assumed.
_NAME_KEYS = ("name", "type", "title", "label", "key")
_AMOUNT_KEYS = ("amount", "value", "total", "price", "sum")


def _num(v):
    """A finite number, or None. Booleans are not money (bool is an int in Python)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        try:
            v = float(v.replace(",", "").strip())
        except (ValueError, AttributeError):
            return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    return None


def _is_money_key(k):
    if not isinstance(k, str) or not k:
        return False
    # A trailing capital 'Id' (or a bare/underscored id) is an identifier. Checked on the
    # ORIGINAL case on purpose: lowercasing first would throw away 'totalPaid' and
    # 'alreadyPaid', which merely end in the letters i-d.
    if k == "id" or k.endswith("Id") or k.endswith("_id") or k.endswith("ID"):
        return False
    low = k.lower()
    if any(bad in low for bad in _NOT_MONEY):
        return False
    return any(w in low for w in _MONEY_WORDS)


def harvest_money(res):
    """Every money-shaped number on one raw Hostaway reservation, flat.

    Includes entries of any list-of-dicts breakdown (`financeField` and friends) as
    'financeField.baseRate'. Pure harvesting — nothing is inferred, converted or
    combined, so what the page shows is what Hostaway actually sent."""
    out = {}
    for k, v in (res or {}).items():
        if isinstance(v, list):
            for item in v:
                if not isinstance(item, dict):
                    continue
                name = None
                for nk in _NAME_KEYS:
                    if isinstance(item.get(nk), str) and item[nk].strip():
                        name = item[nk].strip()
                        break
                if not name:
                    continue
                amt = None
                for ak in _AMOUNT_KEYS:
                    amt = _num(item.get(ak))
                    if amt is not None:
                        break
                if amt is not None:
                    out["%s.%s" % (k, name)] = amt
            continue
        if not _is_money_key(k):
            continue
        n = _num(v)
        if n is not None:
            out[k] = n
    return out


def _d(s):
    try:
        y, m, dd = str(s)[:10].split("-")
        return date(int(y), int(m), int(dd))
    except (ValueError, AttributeError, TypeError):
        return None


def calendar_slice(cal_days, res_id, checkin, checkout):
    """The calendar's own account of one stay.

    Returns total / nights_expected / nights_matched / complete / nights[]. `total` is
    the sum of the nightly prices the calendar has recorded AGAINST THIS RESERVATION —
    the checkout night is excluded, because nobody is charged for it."""
    a, b = _d(checkin), _d(checkout)
    expected = (b - a).days if (a and b and b > a) else 0
    want = str(res_id)
    by_date = {}
    for row in (cal_days or []):
        dt = _d(row.get("date"))
        if dt is None or not (a and b) or not (a <= dt < b):
            continue
        if str(row.get("reservationId")) != want:
            continue
        # A duplicated date in the payload must not be counted twice.
        by_date[dt] = _num(row.get("price"))
    nights, total, priced = [], 0.0, 0
    for i in range(max(expected, 0)):
        dt = a + timedelta(days=i)
        p = by_date.get(dt)
        nights.append({"date": dt.isoformat(), "price": p, "matched": dt in by_date})
        if dt in by_date:
            priced += 1
            total += (p or 0.0)          # a 0-riyal night is a real night, not a gap
    complete = expected > 0 and priced == expected
    return {"total": (round(total, 2) if complete else None),
            "raw_total": round(total, 2), "nights_expected": expected,
            "nights_matched": priced, "complete": complete, "nights": nights}


def compare_row(res, cal_days, tol=TOL):
    """One reservation against the calendar's account of it.

    status:
      'ok'        — at least one money field equals the calendar total
      'differs'   — the calendar is complete and NO money field equals it
      'uncertain' — the calendar does not fully cover the stay; no difference claimed
    """
    rid = res.get("id") or res.get("reservationId")
    sl = calendar_slice(cal_days, rid, res.get("arrivalDate"), res.get("departureDate"))
    money = harvest_money(res)
    agree = []
    if sl["complete"]:
        agree = sorted(k for k, v in money.items() if abs(v - sl["total"]) <= tol)
    if not sl["complete"]:
        status = "uncertain"
    elif agree:
        status = "ok"
    else:
        status = "differs"
    return {
        "id": rid,
        "lid": res.get("listingMapId"),
        "listing": res.get("listingName") or "",
        "guest": (res.get("guestName") or "").strip(),
        "channel": (res.get("channelName") or res.get("channel") or "").strip(),
        "res_status": (res.get("status") or "").lower(),
        "checkin": res.get("arrivalDate"), "checkout": res.get("departureDate"),
        "created": (str(res.get("reservationDate") or "")[:10] or None),
        "nights_expected": sl["nights_expected"], "nights_matched": sl["nights_matched"],
        "calendar_total": sl["total"], "calendar_partial": sl["raw_total"],
        "nights": sl["nights"], "money": money, "agree": agree, "status": status,
    }


def field_agreement(rows, tol=TOL):
    """Which money field tracks the calendar, measured — not assumed.

    For every field name seen anywhere, count the comparable rows (calendar complete AND
    the field present) and how many of those it matched. Sorted by agreement rate, then
    volume. On healthy data the field Hostaway calls «Rental Revenue» rises to the top;
    the bookings where it does NOT agree are the ones an employee edited."""
    seen, agrees, compared = set(), {}, {}
    for r in rows or []:
        seen.update(r.get("money") or {})
    for f in seen:
        agrees[f] = 0
        compared[f] = 0
    for r in rows or []:
        if r.get("status") == "uncertain" or r.get("calendar_total") is None:
            continue
        money = r.get("money") or {}
        for f in seen:
            if f not in money:
                continue
            compared[f] += 1
            if abs(money[f] - r["calendar_total"]) <= tol:
                agrees[f] += 1
    out = [{"field": f, "agrees": agrees[f], "compared": compared[f],
            "rate": (round(agrees[f] * 100.0 / compared[f], 1) if compared[f] else 0.0)}
           for f in seen]
    out.sort(key=lambda x: (-x["rate"], -x["compared"], x["field"]))
    return out


def verdict(rows, field, tol=TOL):
    """The answer, against ONE chosen field: which bookings disagree with the calendar.

    ok      — field equals the calendar
    wrong   — field present, calendar complete, and they disagree. `gap` is
              field − calendar, so a negative gap means Hostaway is UNDER the calendar.
    unknown — the field is not on that booking at all. Listed, never scored as zero:
              a missing field is a thing to look at, not a difference of nothing.
    skipped — the calendar could not fully account for the stay."""
    ok, wrong, unknown, skipped, gap_sum = 0, [], [], [], 0.0
    for r in rows or []:
        if r.get("status") == "uncertain" or r.get("calendar_total") is None:
            skipped.append(r)
            continue
        v = (r.get("money") or {}).get(field)
        if v is None:
            unknown.append(r)
            continue
        gap = round(v - r["calendar_total"], 2)
        if abs(gap) <= tol:
            ok += 1
        else:
            wrong.append({**r, "field_value": v, "gap": gap})
            gap_sum += gap
    wrong.sort(key=lambda x: -abs(x["gap"]))
    return {"field": field, "ok": ok, "wrong": wrong, "unknown": unknown,
            "skipped": skipped, "total_gap": round(gap_sum, 2),
            "counts": {"ok": ok, "wrong": len(wrong), "unknown": len(unknown),
                       "skipped": len(skipped), "rows": len(rows or [])}}
