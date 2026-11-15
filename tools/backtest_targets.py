# -*- coding: utf-8 -*-
"""
Backtest of the payout rules on a Hostaway reservations export (CSV).

    python3 tools/backtest_targets.py /path/to/reservations.csv

Scenario "lazy team": every month the team logs a contact with EVERY callable guest on day 1
and does nothing else. The calls change nothing, so every booking that follows is one that
would have come anyway. A safe plan must pay (close to) nothing here. The script prints the
raw commission those natural bookings would claim, and what the uplift cap lets through.
"""
import collections
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from targets import engine as E   # noqa: E402

FEE = 0.198     # portfolio average; the live system reads each unit's contract


def load(path):
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for x in csv.DictReader(f):
            if x["Status"] not in E.CONFIRMED or "CLOSED" in x["Guest name"].upper():
                continue
            if x["Channel"] == "customIcal" or not E.phone_key(x["Phone"]):
                continue
            try:
                out.append({"id": x["Hostaway reservation ID"], "phone": x["Phone"],
                            "arrival": dt.date.fromisoformat(x["Check-in date"]),
                            "departure": dt.date.fromisoformat(x["Check-out date"]),
                            "created": dt.date.fromisoformat(x["Reservation date"][:10]),
                            "total": float(x["Total price"] or 0), "status": x["Status"]})
            except ValueError:
                continue
    return out


def main(path):
    rows = load(path)
    by_phone = collections.defaultdict(list)
    for r in rows:
        by_phone[E.phone_key(r["phone"])].append(r)
    months = ["%d-%02d" % (y, m) for y in (2025, 2026) for m in range(1, 13)]
    months = [m for m in months if "2025-09" <= m <= "2026-09"]
    print("month     callable contacted holdout | natural bookings: contacted holdout | raw claim | pool | paid")
    tot_raw = tot_paid = 0.0
    hist_c = hist_n = 0
    for mk in months:
        day1, _ = E.month_bounds(mk)
        quarter = "%s-Q%d" % (mk[:4], (int(mk[5:]) - 1) // 3 + 1)
        contacted, holdout, contacts = [], [], []
        for key, stays in by_phone.items():
            past = [s["departure"] for s in stays if s["departure"] < day1 and s["created"] < day1]
            if not past:
                continue
            guest = {"phone": key, "last_checkout": max(past), "consent": True,
                     "has_future_booking": any(s["created"] < day1 <= s["arrival"] for s in stays)}
            if not E.callable_guest(guest, day1)[0]:
                continue
            if E.in_holdout(key, quarter):
                holdout.append(key)
            else:
                contacted.append(key)
                contacts.append({"id": key, "employee": "team", "phone": key, "at": day1})
        window = [r for r in rows if 0 <= (r["created"] - day1).days <= E.ATTRIBUTION_DAYS]
        got = E.attribute(contacts, window)
        raw = sum(E.booking_commission(r, E.SHARE_BASE, FEE) for r in window if r["id"] in got)
        hold_set = set(holdout)
        hold_hits = len({E.phone_key(r["phone"]) for r in window if E.phone_key(r["phone"]) in hold_set})
        cont_hits = len({E.phone_key(r["phone"]) for r in window if r["id"] in got})
        fees = [r["total"] * FEE for r in window if r["id"] in got]
        avg_fee = sum(fees) / len(fees) if fees else 0.0
        fallback = (hist_n / hist_c) if hist_c else None      # history BEFORE this month only
        pool = E.uplift_pool(len(contacted), cont_hits, len(holdout), hold_hits, avg_fee, fallback)
        paid = E.settle({"team": raw}, pool["pool"])["total_paid"]
        hist_c += len(contacted) + len(holdout)
        hist_n += cont_hits + hold_hits
        tot_raw += raw
        tot_paid += paid
        print("%s   %6d %8d %7d |                 %8d %7d | %9.0f | %4.0f | %4.0f"
              % (mk, len(contacted) + len(holdout), len(contacted), len(holdout), cont_hits,
                 hold_hits, raw, pool["pool"], paid))
    n = len(months)
    print("\n%d months. Natural bookings would CLAIM %.0f SAR. The cap lets through %.0f SAR (%.1f%%)."
          % (n, tot_raw, tot_paid, 100 * tot_paid / tot_raw if tot_raw else 0))


if __name__ == "__main__":
    main(sys.argv[1])
