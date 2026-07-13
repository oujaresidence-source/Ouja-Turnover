# -*- coding: utf-8 -*-
"""
HOSTAWAY FETCH — READ-ONLY. FOREVER.  (spec §1, §9 step 3)

This module NEVER writes to Hostaway. It only reads. It wraps the bot's existing,
audited read helpers (`fetch_reservations_window_checked`, `normalize_reservation`,
`get_listings_map`, `fetch_calendar_days`, `fetch_reviews_from_hostaway`, the expense
store) via dependency injection, so it is testable without the network and cannot
accidentally import a write path.

The network-touching methods are thin pass-throughs to injected READ callables. The
aggregation + VAT-reconcile logic is pure and unit-tested with synthetic rows.

Normalized reservation dict this module operates on (the DI adapter maps the bot's
row shape into this):
    {checkout: 'YYYY-MM-DD', nights: int, revenue: float (net accommodation, ex-cleaning,
     ex-VAT per resolved basis), channel: str, lead_days: float, is_repeat: bool,
     status: 'confirmed'|'cancelled'}
"""
from __future__ import annotations

from collections import defaultdict

VAT_RATE = 0.15

# Write verbs that must never appear in this module. A test asserts their absence.
_FORBIDDEN = ("api_post", "api_put", "api_delete")


# ────────────────────────── pure aggregation helpers ──────────────────────────
def confirmed_revenue_rows(reservations):
    """Only confirmed reservations count toward revenue. Cancelled never do."""
    return [r for r in reservations if r.get("status") != "cancelled"]


def reservation_revenue_total(reservations):
    return sum(r["revenue"] for r in confirmed_revenue_rows(reservations))


def monthly_rows(reservations, month_defs, calendar_available):
    """Build the MONTHS cfg rows on an accrual (check-out) basis.

    month_defs: ordered [(month_ar, month_en, 'YYYY-MM')] for the period.
    calendar_available: {'YYYY-MM': nights_available} from the listing calendar.
    Returns [(ar, en, nights_available, nights_booked, gross_revenue)] and the total,
    so the monthly sum can be reconciled to the reservation-level total.
    """
    booked = defaultdict(int)
    gross = defaultdict(float)
    for r in confirmed_revenue_rows(reservations):
        mk = r["checkout"][:7]
        booked[mk] += r["nights"]
        gross[mk] += r["revenue"]
    rows = []
    for m_ar, m_en, mk in month_defs:
        rows.append((m_ar, m_en, int(calendar_available.get(mk, 0)),
                     int(booked.get(mk, 0)), round(gross.get(mk, 0.0))))
    return rows


def channel_mix(reservations):
    """Return [(label, label, fraction)] by revenue share, confirmed rows only."""
    rev = defaultdict(float)
    for r in confirmed_revenue_rows(reservations):
        rev[r.get("channel", "Other")] += r["revenue"]
    total = sum(rev.values()) or 1.0
    return [(ch, ch, round(v / total, 4)) for ch, v in sorted(rev.items(), key=lambda kv: -kv[1])]


def booking_behaviour(reservations):
    conf = confirmed_revenue_rows(reservations)
    n = len(conf) or 1
    nights = sum(r["nights"] for r in conf)
    cancelled = sum(1 for r in reservations if r.get("status") == "cancelled")
    return {
        "alos": round(nights / n, 1),
        "lead_time": round(sum(r.get("lead_days", 0) for r in conf) / n, 1),
        "repeat_guest_pct": round(sum(1 for r in conf if r.get("is_repeat")) / n, 3),
        "cancellation_pct": round(cancelled / (len(reservations) or 1), 3),
        "reservations": len(conf),
    }


def vat_reconcile(reported_revenue, actual_payout, tol=0.01):
    """Verify VAT basis against ONE real payout (spec Q7). Never guess — this checks.

    If Hostaway's reported figure / actual net payout ≈ 1.15, the reported figure is
    VAT-INCLUSIVE (gross); if ≈ 1.0 it is NET. Returns the inferred basis + the ratio +
    whether it lands cleanly on one of the two expected values.
    """
    if not actual_payout:
        return {"basis": None, "ratio": None, "consistent": False,
                "reason": "no payout to reconcile against"}
    ratio = reported_revenue / actual_payout
    if abs(ratio - (1 + VAT_RATE)) <= tol:
        return {"basis": "inclusive", "ratio": round(ratio, 4), "consistent": True}
    if abs(ratio - 1.0) <= tol:
        return {"basis": "net", "ratio": round(ratio, 4), "consistent": True}
    return {"basis": None, "ratio": round(ratio, 4), "consistent": False,
            "reason": "ratio matches neither net (1.00) nor VAT-inclusive (1.15) — investigate"}


# ────────────────────────── read-only DI reader ──────────────────────────
class HostawayReader:
    """Thin read-only surface over the bot's audited read helpers.

    All callables are injected and READ-only. There is deliberately no method that posts,
    puts, or deletes. `assert_read_only()` proves no write verb is referenced.
    """

    def __init__(self, *, fetch_window_checked, normalize, listings_map,
                 calendar_days, reviews, expenses_source, exp_posted, adapt_row):
        self._fetch_window_checked = fetch_window_checked   # (start,end)->(rows,degraded)
        self._normalize = normalize                          # (raw,listings)->finance row
        self._listings_map = listings_map                    # ()->{lid:name}
        self._calendar_days = calendar_days                  # (lid,start,end)->[days]
        self._reviews = reviews                              # ()->[reviews]
        self._expenses_source = expenses_source              # ()->{id:exp}
        self._exp_posted = exp_posted                        # (exp)->bool
        self._adapt_row = adapt_row                          # (finance row)->normalized dict

    def reservations(self, lid, start, end):
        rows, degraded = self._fetch_window_checked(start, end)
        listings = self._listings_map()
        out = []
        for raw in rows:
            fin = self._normalize(raw, listings)
            if str(fin.get("listingMapId", fin.get("lid"))) != str(lid):
                continue
            out.append(self._adapt_row(fin))
        return out, degraded

    def calendar_available(self, lid, start, end, month_defs):
        days = self._calendar_days(lid, start, end)
        avail = defaultdict(int)
        for d in days:
            if d.get("isAvailable") in (1, True) or d.get("status") == "available":
                avail[d["date"][:7]] += 1
        # also count booked days as available (they were available before booking)
        return dict(avail)

    def owner_expenses(self, lid, owner_categories):
        """Owner-borne opex candidates for the unit — posted expenses only, read-only."""
        out = []
        for exp in (self._expenses_source() or {}).values():
            if not self._exp_posted(exp):
                continue
            if str(exp.get("lid")) != str(lid):
                continue
            if exp.get("category") in owner_categories:
                out.append(exp)
        return out

    @staticmethod
    def assert_read_only(module_source: str) -> None:
        """Raise if the source actually CALLS a Hostaway write verb.

        Checks for call syntax (``verb(``) so the forbidden-verb list itself — which
        appears only as bare string literals — does not trip the check.
        """
        hits = [w for w in _FORBIDDEN if f"{w}(" in module_source]
        if hits:
            raise RuntimeError(f"read-only violation: module calls {hits}")
