# -*- coding: utf-8 -*-
"""
owner_report.live — bridge between the wired bot caps and the pure pipeline.

Responsibilities:
  * list_units()            — units for the wizard picker (Hostaway listings map).
  * make_reader()           — a READ-ONLY HostawayReader built from HOST caps.
  * gather_hostaway(...)    — pull the H sections (MONTHS, CHANNELS, BOOKING_BEHAVIOUR,
                              GUEST, channel_fees) for a unit + period. No fabrication:
                              if Hostaway can't be read, it raises.
  * operator_template(...)  — the O/M portion of `inputs`, stored per unit and edited in
                              the wizard. Defaults to a complete, editable template so a
                              first-run report is well-formed; every value is operator-
                              confirmed before it renders.
  * assemble_inputs(...)    — merge operator answers (O/M) with freshly-pulled H data.

⚠️ adapt_row() maps the bot's normalize_reservation output into the reader's normalized
shape. The exact source field names must be validated against the live Hostaway account
(the build session had no credentials). It is written defensively with fallbacks.
"""
from __future__ import annotations

from .host import HOST
from .hostaway_fetch import HostawayReader, monthly_rows, channel_mix, booking_behaviour

_MONTH_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
_MONTH_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def list_units():
    lm = HOST.require("listings_map")()
    return [{"lid": str(lid), "name": name} for lid, name in sorted(lm.items(), key=lambda kv: str(kv[1]))]


def _adapt_row(fin):
    """bot finance row -> reader's normalized reservation dict. Defensive field access."""
    def g(*keys, default=None):
        for k in keys:
            if k in fin and fin[k] not in (None, ""):
                return fin[k]
        return default
    status = "cancelled" if (g("status", "reservationStatus", default="") in
                             ("cancelled", "canceled") or g("isCancelled")) else "confirmed"
    return {
        "checkout": str(g("departureDate", "checkout", "departure", default=""))[:10],
        "nights": int(g("nights", "numberOfNights", default=0) or 0),
        "revenue": float(g("owner_income", "income", "net_revenue", "accommodation",
                           "totalPrice", default=0) or 0),
        "channel": g("channel", "channelName", "source", default="Other"),
        "lead_days": float(g("lead_days", "leadTime", default=0) or 0),
        "is_repeat": bool(g("is_repeat", "repeat_guest", default=False)),
        "status": status,
    }


def make_reader():
    return HostawayReader(
        fetch_window_checked=HOST.require("fetch_window_checked"),
        normalize=HOST.require("normalize"),
        listings_map=HOST.require("listings_map"),
        calendar_days=HOST.require("calendar_days"),
        reviews=HOST.require("reviews"),
        expenses_source=HOST.require("expenses_source"),
        exp_posted=HOST.require("exp_posted"),
        adapt_row=_adapt_row,
    )


def month_defs(start_iso, months):
    """Ordered [(ar,en,'YYYY-MM')] for `months` consecutive months from start (YYYY-MM-..)."""
    y, m = int(start_iso[:4]), int(start_iso[5:7])
    out = []
    for _ in range(months):
        out.append((_MONTH_AR[m - 1], _MONTH_EN[m - 1], f"{y:04d}-{m:02d}"))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def gather_hostaway(lid, start_iso, end_iso, months, vat_basis, reader=None):
    """Pull the H sections for the period. Raises on read failure (never fabricates)."""
    reader = reader or make_reader()
    rows, degraded = reader.reservations(lid, start_iso, end_iso)
    mdefs = month_defs(start_iso, months)
    cal = reader.calendar_available(lid, start_iso, end_iso, mdefs)
    from .model import _net_of_vat
    vat_included = vat_basis == "inclusive"
    norm = []
    for r in rows:
        rr = dict(r)
        rr["revenue"] = _net_of_vat(rr["revenue"], vat_included)
        norm.append(rr)
    mrows = monthly_rows(norm, mdefs, cal)
    from .hostaway_fetch import reservation_revenue_total
    return {
        "months": [(a, e, na, nb, g) for (a, e, na, nb, g) in mrows],
        "channels": channel_mix(norm),
        "booking_behaviour": booking_behaviour(norm),
        "reservation_revenue_total": reservation_revenue_total(norm),
        "degraded": degraded,
        "channel_fees": None,   # operator confirms actual/blended (spec Q12)
    }


# The O/M portion of `inputs`, stored per-unit and edited in the wizard. Rich, complete
# defaults so a first report is well-formed; every value is re-confirmed before render.
def operator_template(unit_meta=None):
    unit_meta = unit_meta or {}
    return {
        "vat_basis": "net",
        "unit": {
            "listing_name_en": unit_meta.get("listing_name_en", ""),
            "listing_name_ar": unit_meta.get("listing_name_ar", ""),
            "compound_en": unit_meta.get("compound_en", ""),
            "compound_ar": unit_meta.get("compound_ar", ""),
            "unit_ref": unit_meta.get("unit_ref", ""),
            "bedrooms": unit_meta.get("bedrooms", 1),
            "area_sqm": unit_meta.get("area_sqm", 0),
            "furnished": unit_meta.get("furnished", True),
            "onboarded": unit_meta.get("onboarded", ""),
            "mot_licence": unit_meta.get("mot_licence", ""),
        },
        "owner": {"name_en": "Unit Owner", "name_ar": "مالك الوحدة"},
        "report": {
            "type_en": "Half-Year Performance Report", "type_ar": "تقرير الأداء النصف سنوي",
            "period_label_en": "", "period_label_ar": "",
            "issue_date_en": "", "issue_date_ar": "",
            "doc_ref": "", "prepared_by_en": "Ouja Residence — Revenue & Asset Management",
            "prepared_by_ar": "عوجا لإدارة الأملاك — إدارة الإيرادات والأصول",
        },
        "asset": {"purchase_price": 0, "purchase_note_en": "Owner acquisition cost of the unit",
                  "purchase_note_ar": "تكلفة شراء الوحدة على المالك"},
        "market_yield": {"riyadh_gross_low": 0.058, "riyadh_gross_high": 0.089,
                         "riyadh_net_avg": 0.043, "ksa_gross_avg": 0.0684,
                         "note_en": "", "note_ar": ""},
        "rent_freeze": {"start": "25 September 2025", "years": 5, "ends": "September 2030",
                        "ends_ar": "سبتمبر 2030", "start_ar": "25 سبتمبر 2025"},
        "ejar": {"annual_rent": 0, "ref": "Ejar registered lease",
                 "source_en": "Ejar Platform", "source_ar": "منصة إيجار",
                 "broker_pct": 0.025, "vacancy_pct": 0.05, "owner_maintenance": 0, "admin_fees": 0,
                 "comparable_furnished": False, "furnished_uplift_pct": 0.0},
        "ejar_is_single_contract": True,
        "blocked_by_month": [], "owner_blocked_treatment": "exclude",
        "costs": {"channel_fees": 0, "mgmt_fee_pct": 0.20, "opex": []},
        "furnishing": {"delivered_furnished": True, "capex": 0, "amort_years": 5, "owner_funded": False},
        "comp_set": [], "comp_stale": False, "manual_bookings": 0,
        "factors": [], "risks": [], "actions": [], "sources": [],
        "projection": {"h2_2026": {"low": 0, "base": 0, "high": 0},
                       "fy_2027": {"low": 0, "base": 0, "high": 0},
                       "channel_pct": 0.034, "opex_annual": 0,
                       "assumptions_ar": [], "assumptions_en": []},
    }


def assemble_inputs(operator_answers, hostaway):
    """Merge the stored/confirmed operator (O/M) answers with freshly-pulled H data.

    H sections always come from Hostaway (never operator-typed): months, channels,
    booking_behaviour. channel_fees stays operator-confirmed (Q12). vat_basis is applied
    upstream in gather_hostaway, so the two agree.
    """
    inp = dict(operator_answers)
    inp["months"] = hostaway["months"]
    inp["channels"] = hostaway["channels"]
    inp["booking_behaviour"] = hostaway["booking_behaviour"]
    if len(inp.get("blocked_by_month") or []) != len(inp["months"]):
        inp["blocked_by_month"] = [0] * len(inp["months"])
    return inp
