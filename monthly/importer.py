# -*- coding: utf-8 -*-
"""
monthly.importer — read a Hostaway reservations CSV export.

WHY THIS EXISTS. Every crash in this feature came from the same place: an admin
screen asking Hostaway for years of history inside a request, and Railway giving
up before the app did. An export removes the cause rather than working around it.
There is no API call, no pagination, no 45-day arrival window and no timeout —
just a file that was already complete when it was downloaded.

It also removes a real blind spot. fetch_reservations_window filters on arrival
date, so a stay that began before the window and covered the whole month was
never fetched. A file has no window at all.

THE PARSER IS DELIBERATELY LOUD. Every row that cannot be used is counted with a
reason and reported. A silent drop in an import is how a price ends up built on
half a portfolio, and this feature has already been bitten twice by numbers that
looked fine because what was missing never announced itself.
"""

import csv
import datetime
import io
import os

# Hostaway's export header, with the alternatives its other exports use. Matched
# case- and space-insensitively so a renamed column does not silently blank a
# whole field.
_FIELDS = {
    "listing": ("listing", "listingname", "internallistingname", "property", "unit"),
    "checkin": ("checkindate", "arrivaldate", "arrival", "checkin", "startdate"),
    "checkout": ("checkoutdate", "departuredate", "departure", "checkout", "enddate"),
    "total": ("totalprice", "total", "amount", "totalamount", "price"),
    "status": ("status", "reservationstatus"),
    "nights": ("numberofnights", "nights"),
    "resid": ("hostawayreservationid", "reservationid", "id"),
    "channel_res": ("channelreservationid",),
    "currency": ("currency",),
}

CONFIRMED = {"new", "modified"}


def _norm(h):
    return "".join(ch for ch in str(h or "").lower() if ch.isalnum())


def _map_headers(fieldnames):
    got = {}
    for want, alts in _FIELDS.items():
        for h in (fieldnames or []):
            if _norm(h) in alts:
                got[want] = h
                break
    return got


def _date(s):
    s = str(s or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


def parse(text_or_path):
    """CSV -> (rows, report). Rows carry the same field names the live Hostaway
    path produces, so nothing downstream can tell the difference."""
    if os.path.exists(str(text_or_path)):
        with io.open(text_or_path, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    else:
        text = text_or_path

    rdr = csv.DictReader(io.StringIO(text))
    cols = _map_headers(rdr.fieldnames)
    missing = [k for k in ("listing", "checkin", "checkout", "total", "status")
               if k not in cols]
    if missing:
        return [], {"ok": False, "error": "missing_columns", "missing": missing,
                    "saw": list(rdr.fieldnames or [])[:40]}

    rows, seen = [], set()
    rep = {"ok": True, "read": 0, "kept": 0, "listings": set(),
           "dropped_bad_dates": 0, "dropped_no_price": 0, "dropped_no_listing": 0,
           "duplicates": 0, "statuses": {}, "first": None, "last": None}

    for r in rdr:
        rep["read"] += 1
        st = str(r.get(cols["status"]) or "").strip()
        rep["statuses"][st] = rep["statuses"].get(st, 0) + 1

        name = str(r.get(cols["listing"]) or "").strip()
        ci, co = _date(r.get(cols["checkin"])), _date(r.get(cols["checkout"]))
        total = _num(r.get(cols["total"]))
        rid = (r.get(cols.get("resid")) or "").strip() if cols.get("resid") else ""

        if not name:
            rep["dropped_no_listing"] += 1
            continue
        if not ci or not co or (co - ci).days <= 0:
            rep["dropped_bad_dates"] += 1
            continue
        if total is None or total <= 0:
            rep["dropped_no_price"] += 1
            continue
        if rid:
            if rid in seen:
                rep["duplicates"] += 1
                continue
            seen.add(rid)

        rep["listings"].add(name)
        rep["first"] = ci.isoformat() if not rep["first"] else min(rep["first"], ci.isoformat())
        rep["last"] = ci.isoformat() if not rep["last"] else max(rep["last"], ci.isoformat())
        rep["kept"] += 1
        rows.append({
            "id": rid or ("%s-%s" % (name, ci.isoformat())),
            "listingName": name,
            "arrivalDate": ci.isoformat(),
            "departureDate": co.isoformat(),
            "totalPrice": total,
            "status": st,
        })

    rep["listings"] = sorted(rep["listings"])
    rep["n_listings"] = len(rep["listings"])
    rep["confirmed"] = sum(v for k, v in rep["statuses"].items()
                           if k.strip().lower() in CONFIRMED)
    return rows, rep


def attach_listing_ids(rows, unit_meta):
    """Join the export's listing NAME to the listing id.

    The export names the unit the way the team does («2D - صاد»), which is
    exactly Hostaway's internalListingName — so the join is on a field both sides
    already agree on. Unmatched names are RETURNED, never dropped quietly: a name
    that does not match is either a renamed unit or a delisted one, and both are
    worth seeing.
    """
    by_name = {}
    for lid, m in (unit_meta or {}).items():
        for key in (m.get("name"), m.get("public_name")):
            if key:
                by_name[str(key).strip()] = lid

    out, unmatched = [], {}
    for r in rows:
        lid = by_name.get(r["listingName"])
        if lid is None:
            unmatched[r["listingName"]] = unmatched.get(r["listingName"], 0) + 1
            continue
        rr = dict(r)
        rr["listingMapId"] = lid
        out.append(rr)
    return out, unmatched
