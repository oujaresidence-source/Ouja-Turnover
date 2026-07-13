# -*- coding: utf-8 -*-
"""
===========================================================
 OUJA — OWNER PERFORMANCE REPORT  ::  DATA CONFIG
===========================================================
 EVERY number in the PDF comes from this file.
 Change values here -> re-run build_report.py -> new PDF.
 Nothing else needs to be touched.
===========================================================
"""

# ----------------------------------------------------------
# 1. UNIT & OWNER IDENTITY
# ----------------------------------------------------------
UNIT = {
    "listing_name_en": "Ouja | Majdiah 2BR",
    "listing_name_ar": "عوجا | المجدية غرفتين",
    "compound_en": "Al Majdiah Residence, Riyadh",
    "compound_ar": "مجمع المجدية السكني، الرياض",
    "unit_ref": "B-207",
    "bedrooms": 2,
    "area_sqm": 118,
    "furnished": True,
    "onboarded": "2024-11-01",
    "mot_licence": "MT-STR-2024-118203",   # Ministry of Tourism licence no.
}

OWNER = {
    "name_en": "Unit Owner",
    "name_ar": "مالك الوحدة",
}

REPORT = {
    "type_en": "Half-Year Performance Report",
    "type_ar": "تقرير الأداء النصف سنوي",
    "period_label_en": "H1 2026  ·  1 January – 30 June 2026",
    "period_label_ar": "النصف الأول 2026  ·  1 يناير – 30 يونيو 2026",
    "issue_date_en": "13 July 2026",
    "issue_date_ar": "13 يوليو 2026",
    "doc_ref": "OJ-OPR-2026-H1-B207",
    "prepared_by_en": "Ouja Residence — Revenue & Asset Management",
    "prepared_by_ar": "عوجا لإدارة الأملاك — إدارة الإيرادات والأصول",
}

# ----------------------------------------------------------
# 1b. THE ASSET  — what the owner actually paid
# ----------------------------------------------------------
ASSET = {
    "purchase_price": 1_300_000,     # SAR — what the apartment cost
    "purchase_note_en": "Owner acquisition cost of the unit",
    "purchase_note_ar": "تكلفة شراء الوحدة على المالك",
}

# Riyadh residential yield benchmarks (published market data, H1 2026)
MARKET_YIELD = {
    "riyadh_gross_low": 0.058,   # Riyadh citywide avg gross yield (~5.8%)
    "riyadh_gross_high": 0.089,  # Riyadh avg gross yield, higher-yield sources (~8.9%)
    "riyadh_net_avg": 0.043,     # Riyadh avg NET residential yield (~4.3%)
    "ksa_gross_avg": 0.0684,     # Saudi national avg gross yield, Q1 2026
    "note_en": "Riyadh residential gross yields are reported between ~5.8% and ~8.9% depending on district and source; net yields run roughly 1–1.5 points below gross, averaging ~4.3%.",
    "note_ar": "تتراوح العوائد الإجمالية السكنية في الرياض بين 5.8% و 8.9% تقريبًا حسب الحي والمصدر، والعائد الصافي أقل من الإجمالي بنحو 1–1.5 نقطة، بمتوسط 4.3% تقريبًا.",
}

# Riyadh rent freeze — Royal Decree / REGA, effective 25 Sept 2025 for 5 years
RENT_FREEZE = {
    "start": "25 September 2025",
    "years": 5,
    "ends": "September 2030",
    "ends_ar": "سبتمبر 2030",
    "start_ar": "25 سبتمبر 2025",
}

# ----------------------------------------------------------
# 2. THE EJAR BENCHMARK  <-- the long-term lease alternative
#    Source: Ejar platform (Saudi Ministry of Housing)
# ----------------------------------------------------------
EJAR = {
    "annual_rent": 85_000,          # SAR / year, as registered in Ejar
    "source_en": "Ejar Platform — registered annual lease rate for a comparable unit in the same compound",
    "source_ar": "منصة إيجار — قيمة العقد السنوي المسجّل لوحدة مماثلة في نفس المجمع",
    "ref": "Ejar contract benchmark, Al Majdiah, 2BR, unfurnished",
    # Costs the owner still carries under a normal annual lease:
    "broker_pct": 0.025,            # agency / brokerage commission
    "vacancy_pct": 0.05,            # void period between tenants (~18 days)
    "owner_maintenance": 4_000,     # AC service, repairs owner pays under annual lease
    "admin_fees": 400,              # Ejar registration + municipal admin
}

# ----------------------------------------------------------
# 3. MONTHLY ACTUALS  (from Hostaway)
#    revenue = accommodation revenue only, EXCLUDING VAT
#    and EXCLUDING cleaning fees (pass-through to guest)
# ----------------------------------------------------------
MONTHS = [
    # month_ar,  month_en,  nights_available, nights_booked, gross_revenue
    ("يناير",   "Jan",  31, 24, 15_840),
    ("فبراير",  "Feb",  28, 19, 11_780),
    ("مارس",    "Mar",  31, 22, 15_840),
    ("أبريل",   "Apr",  30, 26, 19_760),
    ("مايو",    "May",  31, 25, 17_875),
    ("يونيو",   "Jun",  30, 22, 14_190),
]

# ----------------------------------------------------------
# 4. DEDUCTIONS & COSTS FOR THE PERIOD
# ----------------------------------------------------------
COSTS = {
    "channel_fees": 3_240,          # blended Airbnb / Booking / Gathern host fees
    "mgmt_fee_pct": 0.20,           # Ouja management fee, on NET rental revenue
    "opex": [
        ("الكهرباء والمياه والإنترنت", "Utilities (elec / water / internet)", 3_450),
        ("المستهلكات ومستلزمات الضيوف", "Consumables & guest amenities",       1_880),
        ("الصيانة وخدمة المكيفات",      "Maintenance & AC servicing",          1_790),
    ],
}

# The unit was DELIVERED FURNISHED — no furnishing capex is charged to the owner.
FURNISHING = {
    "delivered_furnished": True,
    "capex": 0,
    "amort_years": 5,
    "owner_funded": False,
}

# ----------------------------------------------------------
# 5. CHANNEL MIX & BOOKING BEHAVIOUR
# ----------------------------------------------------------
CHANNELS = [
    ("Airbnb",                    "Airbnb",              0.64),
    ("الحجز المباشر (عوجا)",       "Direct (Ouja)",       0.21),
    ("Booking.com",               "Booking.com",         0.09),
    ("جاذر",                       "Gathern",             0.06),
]

BOOKING_BEHAVIOUR = {
    "alos": 2.9,                    # average length of stay, nights
    "lead_time": 6.8,               # avg days booked in advance
    "repeat_guest_pct": 0.17,
    "cancellation_pct": 0.041,
    "reservations": 48,
}

# ----------------------------------------------------------
# 6. COMPETITIVE SET  (same tier, same period)
#    Source: Ouja market tracking — comparable 2BR STR units
# ----------------------------------------------------------
COMP_SET = [
    # label_ar, label_en, adr, occupancy
    ("منافس أ — المجدية",   "Comp A — Al Majdiah",  640, 0.680),
    ("منافس ب — قذ",        "Comp B — Gadh",        705, 0.640),
    ("منافس ج — حطين",      "Comp C — Hittin",      580, 0.740),
    ("منافس د — الياسمين",  "Comp D — Al Yasmin",   750, 0.580),
    ("منافس هـ — النرجس",   "Comp E — Al Narjis",   615, 0.700),
]

# ----------------------------------------------------------
# 7. GUEST EXPERIENCE
# ----------------------------------------------------------
GUEST = {
    "overall": 4.89,
    "reviews": 31,
    "response_rate": 1.00,
    "median_response_min": 4,
    "superhost": True,
    "sub": [
        ("النظافة",       "Cleanliness",  4.94),
        ("دقة الوصف",     "Accuracy",     4.91),
        ("تسجيل الدخول",  "Check-in",     4.96),
        ("التواصل",       "Communication",4.97),
        ("القيمة",        "Value",        4.78),
    ],
}

# ----------------------------------------------------------
# 8. FACTORS THAT MOVED THE NUMBERS
#    impact: "up" | "down" | "flat"
# ----------------------------------------------------------
FACTORS = [
    ("up",   "موسم الرياض — امتداد الطلب (يناير–مارس)",
             "Riyadh Season demand tail (Jan–Mar)",
             "رفع الإشغال في الربع الأول إلى 73%.",
             "Lifted Q1 occupancy to 73%."),
    ("down", "رمضان (17 فبراير – 19 مارس 2026)",
             "Ramadan (17 Feb – 19 Mar 2026)",
             "انخفاض طلب السياحة الترفيهية وضغط على السعر خلال فبراير.",
             "Leisure demand fell and rate came under pressure through February."),
    ("up",   "عيد الفطر (20–23 مارس)",
             "Eid Al-Fitr (20–23 Mar)",
             "إشغال 100% بسعر أعلى من المتوسط بـ 41%.",
             "100% occupancy at a rate 41% above period average."),
    ("up",   "تشغيل محرك التسعير الديناميكي (فبراير)",
             "Dynamic pricing engine live (Feb)",
             "التقط ذروة العيد وأبريل؛ رفع متوسط السعر اليومي ~6%.",
             "Captured the Eid and April peaks; lifted ADR by ~6%."),
    ("down", "عرض جديد في الحي — 14 وحدة مرخّصة",
             "New supply — 14 newly licensed units in district",
             "ضغط على السعر في الفترات منخفضة الطلب.",
             "Rate pressure during soft-demand windows."),
    ("up",   "نمو القناة المباشرة وبرنامج عوجا إيليت",
             "Direct channel & Ouja Elite growth",
             "21% من الإيراد بدون عمولة منصات — يحمي صافي المالك.",
             "21% of revenue booked commission-free — protects owner net."),
    ("down", "بداية الصيف (يونيو)",
             "Summer onset (June)",
             "تراجع الطلب الترفيهي؛ بدأنا التحول للإقامات الطويلة والشركات.",
             "Leisure demand softened; we began shifting to long-stay and corporate."),
    ("up",   "تجميد الإيجارات في الرياض (5 سنوات من 25 سبتمبر 2025)",
             "Riyadh rent freeze (5 years from 25 Sept 2025)",
             "قيمة العقد السنوي مجمّدة حتى 2030 — بينما التأجير قصير الأجل يُسعَّر يوميًا.",
             "The annual lease value is frozen until 2030 — while short-term rates reprice daily."),
    ("flat", "تشديد تراخيص وزارة السياحة",
             "Ministry of Tourism licensing enforcement",
             "لا أثر علينا (الترخيص ساري) — ويرفع حاجز الدخول للمنافسين.",
             "No impact on us (licence current) — and it raises the barrier to entry."),
]

# ----------------------------------------------------------
# 9. RISKS & MITIGATIONS
#    level: "high" | "med" | "low"
# ----------------------------------------------------------
RISKS = [
    ("med",  "نمو العرض في الحي", "Supply growth in the district",
             "مرونة تسعير يومية + توسيع القناة المباشرة.",
             "Daily rate agility + expand the direct channel."),
    ("high", "ركود الصيف (يوليو–أغسطس)", "Summer trough (Jul–Aug)",
             "أسعار إقامة 28+ ليلة، عروض شهرية، واستهداف شركات ونقل موظفين.",
             "28-night+ rates, monthly offers, corporate & relocation targeting."),
    ("med",  "التركّز على منصة واحدة (Airbnb 64%)", "Platform concentration (Airbnb 64%)",
             "هدف رفع الحجز المباشر إلى 30% بنهاية 2026.",
             "Target: grow direct bookings to 30% by end-2026."),
    ("low",  "التنظيم والامتثال الضريبي", "Regulatory & tax compliance",
             "الترخيص ساري والضريبة تُحصّل وتُورّد نظاميًا.",
             "Licence current; VAT charged and remitted per regulation."),
    ("low",  "تغيّر تنظيمي يشمل التأجير قصير الأجل", "Regulatory change reaching short-term rentals",
             "متابعة مستمرة لقرارات الهيئة العامة للعقار ووزارة السياحة.",
             "We monitor REGA and Ministry of Tourism decisions continuously."),
    ("med",  "استهلاك المفروشات (السنة الثانية)", "Soft-goods wear (year two)",
             "تحديث الكنب والمراتب والمفارش مجدول في سبتمبر.",
             "Sofa, mattress and linen refresh scheduled for September."),
]

# ----------------------------------------------------------
# 10. FORWARD PROJECTION
#     H2 2026 gross revenue scenarios + FY2027
# ----------------------------------------------------------
PROJECTION = {
    "h2_2026": {"low": 94_000,  "base": 104_700, "high": 116_000},
    "fy_2027": {"low": 196_000, "base": 214_000, "high": 236_000},
    # cost ratios used to convert gross -> owner net in the projection
    "channel_pct": 0.034,
    "opex_annual": 15_200,
    "assumptions_ar": [
        "إشغال أساسي 74–78% على مدار العام، مع تراجع صيفي وذروة في موسم الرياض.",
        "متوسط سعر يومي 690–730 ريال، بنمو 4–6% سنويًا تماشيًا مع السوق.",
        "استمرار محرك التسعير الديناميكي ورفع الحجز المباشر إلى 26–30%.",
        "لا تغييرات تنظيمية جوهرية؛ الترخيص السياحي ساري.",
        "لا نفقات رأسمالية كبيرة غير تحديث المفروشات المجدول.",
    ],
    "assumptions_en": [
        "Base occupancy 74–78% across the year, with a summer trough and a Riyadh Season peak.",
        "ADR of SAR 690–730, growing 4–6% annually in line with the market.",
        "Dynamic pricing engine stays live; direct bookings rise to 26–30%.",
        "No material regulatory change; tourism licence remains current.",
        "No major capex beyond the scheduled soft-goods refresh.",
    ],
}

# ----------------------------------------------------------
# 11. 90-DAY ACTION PLAN
# ----------------------------------------------------------
ACTIONS = [
    ("يوليو–أغسطس", "Jul–Aug", "استراتيجية الصيف: أسعار 28+ ليلة وشركات",
     "Summer strategy: 28-night+ and corporate rates", "فريق الإيرادات", "Revenue"),
    ("أغسطس", "Aug", "حملة عوجا إيليت — 4,500 عضو",
     "Ouja Elite campaign — 4,500 members", "التسويق", "Marketing"),
    ("أغسطس", "Aug", "تحديث الصور ووصف الإعلان",
     "Photography & listing copy refresh", "المحتوى", "Content"),
    ("سبتمبر", "Sep", "تحديث المفروشات الناعمة (مفارش، وسائد، ستائر)",
     "Soft-goods refresh (linen, cushions, drapes)", "العمليات", "Operations"),
    ("سبتمبر", "Sep", "تحميل سلّم أسعار موسم الرياض",
     "Load the Riyadh Season rate ladder", "فريق الإيرادات", "Revenue"),
    ("سبتمبر", "Sep", "صيانة وقائية للمكيفات قبل الموسم",
     "Preventive AC service ahead of season", "الصيانة", "Maintenance"),
]

# ----------------------------------------------------------
# 12. DATA SOURCES
# ----------------------------------------------------------
SOURCES = [
    ("نظام إدارة العقارات Hostaway", "Hostaway PMS", "الإيرادات، الليالي المحجوزة، الحجوزات"),
    ("لوحة مضيف Airbnb", "Airbnb Host Dashboard", "التقييمات، معدل الاستجابة"),
    ("منصة إيجار — وزارة الإسكان", "Ejar Platform — Ministry of Housing", "قيمة العقد السنوي المرجعية"),
    ("رصد السوق الداخلي — عوجا", "Ouja internal market tracking", "بيانات المنافسين"),
    ("سجل تراخيص وزارة السياحة", "Ministry of Tourism licence registry", "العرض الجديد في الحي"),
    ("الهيئة العامة للعقار (REGA)", "Real Estate General Authority (REGA)", "تجميد الإيجارات في الرياض"),
    ("Global Property Guide · Bayut · JLL", "Global Property Guide · Bayut · JLL", "عوائد الإيجار المرجعية في الرياض"),
]
