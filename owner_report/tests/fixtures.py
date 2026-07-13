# -*- coding: utf-8 -*-
"""Canonical VALID fixtures for the owner_report tests.

`valid_cfg()` mirrors the approved reference unit (Ouja | Majdiah 2BR, B-207) as the
plain dict the renderer consumes. `valid_meta()` is a fully-confirmed, fully-acknowledged
operator context that passes every gate. Tests break one thing at a time from these.
"""


def valid_cfg():
    return {
        "UNIT": {
            "listing_name_en": "Ouja | Majdiah 2BR",
            "listing_name_ar": "عوجا | المجدية غرفتين",
            "compound_en": "Al Majdiah Residence, Riyadh",
            "compound_ar": "مجمع المجدية السكني، الرياض",
            "unit_ref": "B-207", "bedrooms": 2, "area_sqm": 118,
            "furnished": True, "onboarded": "2024-11-01",
            "mot_licence": "MT-STR-2024-118203",
        },
        "OWNER": {"name_en": "Unit Owner", "name_ar": "مالك الوحدة"},
        "REPORT": {
            "type_en": "Half-Year Performance Report", "type_ar": "تقرير الأداء النصف سنوي",
            "period_label_en": "H1 2026", "period_label_ar": "النصف الأول 2026",
            "issue_date_en": "13 July 2026", "issue_date_ar": "13 يوليو 2026",
            "doc_ref": "OJ-OPR-2026-H1-B207",
            "prepared_by_en": "Ouja Residence", "prepared_by_ar": "عوجا",
        },
        "ASSET": {"purchase_price": 1_300_000, "purchase_note_en": "cost", "purchase_note_ar": "تكلفة"},
        "MARKET_YIELD": {
            "riyadh_gross_low": 0.058, "riyadh_gross_high": 0.089,
            "riyadh_net_avg": 0.043, "ksa_gross_avg": 0.0684,
            "note_en": "Riyadh gross yields ~5.8-8.9%.", "note_ar": "عوائد الرياض ~5.8-8.9%.",
        },
        "RENT_FREEZE": {"start": "25 September 2025", "years": 5, "ends": "September 2030",
                        "ends_ar": "سبتمبر 2030", "start_ar": "25 سبتمبر 2025"},
        "EJAR": {"annual_rent": 85_000, "source_en": "Ejar", "source_ar": "إيجار",
                 "ref": "Ejar Al Majdiah 2BR", "broker_pct": 0.025, "vacancy_pct": 0.05,
                 "owner_maintenance": 4_000, "admin_fees": 400},
        "MONTHS": [
            ("يناير", "Jan", 31, 24, 15_840), ("فبراير", "Feb", 28, 19, 11_780),
            ("مارس", "Mar", 31, 22, 15_840), ("أبريل", "Apr", 30, 26, 19_760),
            ("مايو", "May", 31, 25, 17_875), ("يونيو", "Jun", 30, 22, 14_190),
        ],
        "COSTS": {"channel_fees": 3_240, "mgmt_fee_pct": 0.20,
                  "opex": [("الكهرباء", "Utilities", 3_450), ("المستهلكات", "Consumables", 1_880),
                           ("الصيانة", "Maintenance", 1_790)]},
        "FURNISHING": {"delivered_furnished": True, "capex": 0, "amort_years": 5, "owner_funded": False},
        "CHANNELS": [("Airbnb", "Airbnb", 0.64), ("مباشر", "Direct (Ouja)", 0.21),
                     ("Booking", "Booking.com", 0.09), ("جاذر", "Gathern", 0.06)],
        "BOOKING_BEHAVIOUR": {"alos": 2.9, "lead_time": 6.8, "repeat_guest_pct": 0.17,
                              "cancellation_pct": 0.041, "reservations": 48},
        "COMP_SET": [("منافس أ", "Comp A", 640, 0.680), ("منافس ب", "Comp B", 705, 0.640),
                     ("منافس ج", "Comp C", 580, 0.740), ("منافس د", "Comp D", 750, 0.580),
                     ("منافس هـ", "Comp E", 615, 0.700)],
        "GUEST": {"overall": 4.89, "reviews": 31, "response_rate": 1.00, "median_response_min": 4,
                  "superhost": True, "sub": [("النظافة", "Cleanliness", 4.94), ("الدقة", "Accuracy", 4.91),
                  ("الدخول", "Check-in", 4.96), ("التواصل", "Communication", 4.97), ("القيمة", "Value", 4.78)]},
        "FACTORS": [("up", "أ", "Riyadh Season", "رفع", "Lifted Q1 occupancy."),
                    ("down", "ب", "Ramadan", "انخفاض", "Leisure demand fell."),
                    ("up", "ج", "Eid", "إشغال", "100% occupancy."),
                    ("up", "د", "Dynamic pricing", "التقط", "Lifted ADR ~6%."),
                    ("down", "هـ", "New supply", "ضغط", "Rate pressure."),
                    ("up", "و", "Direct growth", "21%", "Commission-free."),
                    ("down", "ز", "Summer onset", "تراجع", "Softened."),
                    ("up", "ح", "Rent freeze", "مجمّد", "Frozen to 2030."),
                    ("flat", "ط", "Licensing", "لا أثر", "No impact.")],
        "RISKS": [("med", "أ", "Supply growth", "مرونة", "Daily agility."),
                  ("high", "ب", "Summer trough", "أسعار", "28-night rates."),
                  ("med", "ج", "Platform concentration", "هدف", "Grow direct."),
                  ("low", "د", "Regulatory", "ساري", "Licence current."),
                  ("low", "هـ", "Reg change", "متابعة", "We monitor."),
                  ("med", "و", "Soft-goods wear", "تحديث", "Refresh Sept.")],
        "PROJECTION": {"h2_2026": {"low": 94_000, "base": 104_700, "high": 116_000},
                       "fy_2027": {"low": 196_000, "base": 214_000, "high": 236_000},
                       "channel_pct": 0.034, "opex_annual": 15_200,
                       "assumptions_ar": ["فرضية"], "assumptions_en": ["assumption"]},
        "ACTIONS": [("يوليو", "Jul", "الصيف", "Summer", "الإيرادات", "Revenue"),
                    ("أغسطس", "Aug", "حملة", "Campaign", "التسويق", "Marketing"),
                    ("أغسطس", "Aug", "صور", "Photos", "المحتوى", "Content"),
                    ("سبتمبر", "Sep", "مفروشات", "Soft-goods", "العمليات", "Ops"),
                    ("سبتمبر", "Sep", "أسعار", "Rate ladder", "الإيرادات", "Revenue"),
                    ("سبتمبر", "Sep", "صيانة", "AC service", "الصيانة", "Maintenance")],
        "SOURCES": [("Hostaway", "Hostaway PMS", "الإيرادات"), ("Airbnb", "Airbnb", "التقييمات"),
                    ("إيجار", "Ejar", "العقد"), ("رصد عوجا", "Ouja tracking", "المنافسين"),
                    ("وزارة السياحة", "Ministry", "العرض"), ("REGA", "REGA", "التجميد"),
                    ("Bayut/JLL", "Bayut/JLL", "العوائد")],
    }


def valid_inp():
    """Operator+Hostaway inputs that, through model.build_cfg, reproduce the reference
    unit with NO active disclosures (furnished comparable, single-contract off)."""
    c = valid_cfg()
    return {
        "vat_basis": "net",  # reference revenue is already ex-VAT
        "unit": c["UNIT"], "owner": c["OWNER"], "report": c["REPORT"],
        "asset": c["ASSET"], "market_yield": c["MARKET_YIELD"],
        "rent_freeze": {"start": "25 September 2025", "years": 5, "ends": "September 2030",
                        "ends_ar": "سبتمبر 2030", "start_ar": "25 سبتمبر 2025"},
        "ejar": {"annual_rent": 85_000,
                 "ref": "Ejar contract benchmark, Al Majdiah, 2BR",
                 "source_en": "Ejar", "source_ar": "إيجار",
                 "broker_pct": 0.025, "vacancy_pct": 0.05,
                 "owner_maintenance": 4_000, "admin_fees": 400,
                 "comparable_furnished": True, "furnished_uplift_pct": 0.0},
        "ejar_is_single_contract": False,
        # months as raw calendar-available + booked + gross (net of VAT here)
        "months": [(a, e, na, nb, g) for (a, e, na, nb, g) in c["MONTHS"]],
        "blocked_by_month": [0, 0, 0, 0, 0, 0],
        "owner_blocked_treatment": "exclude",
        "costs": {"channel_fees": 3_240, "mgmt_fee_pct": 0.20,
                  "opex": [("الكهرباء", "Utilities", 3_450), ("المستهلكات", "Consumables", 1_880),
                           ("الصيانة", "Maintenance", 1_790)]},
        "furnishing": {"delivered_furnished": True, "capex": 0, "amort_years": 5, "owner_funded": False},
        "channels": c["CHANNELS"], "booking_behaviour": c["BOOKING_BEHAVIOUR"],
        "guest": c["GUEST"], "comp_set": [(a, e, adr, occ) for (a, e, adr, occ) in c["COMP_SET"]],
        "comp_stale": False, "manual_bookings": 0,
        "factors": c["FACTORS"], "risks": c["RISKS"], "actions": c["ACTIONS"],
        "sources": c["SOURCES"], "projection": c["PROJECTION"],
    }


def valid_meta():
    return {
        "vat_resolved": True,
        "vat_reconciled_against_payout": True,
        "reconciliation_signed": True,
        "reservation_revenue_total": 95_285,  # == sum of MONTHS gross
        "cancelled_in_revenue": 0,
        "lease_sections_enabled": True,
        "owner_blocked_nights": 0,
        "owner_blocked_treatment": "exclude",
        "ejar_is_single_contract": False,
        "ejar_unfurnished_no_uplift": False,
        "comp_stale": False,
        "manual_bookings": 0,
        "acknowledged": [],
        "disclosures": [],
        "required_fields_confirmed": True,
    }
