# -*- coding: utf-8 -*-
"""
site_home.identity — the ONE place the company's official details live.

Every value here must match the commercial register exactly as business.sa displays it
(tests/test_home_site.py locks them). The owner never edits Railway variables, so the
pending slots are filled here, in code, when the documents arrive:

  travel_licence_no      Ministry of Tourism licence, category «وكالة السفر والسياحة».
                         Empty = the licence block is not rendered anywhere.
  business_sa_cert_url   business.sa e-commerce verification certificate link.
  business_sa_badge_img  its badge image URL (https). Link alone = a text badge.

email / phone empty = fall back to bot.py's OUJA_CONTACT_EMAIL / STAY_WHATSAPP (wired
in by site_home.wire). Still empty = the field is hidden; a contact is never invented.
"""

SITE_IDENTITY = {
    "site_url": "https://oujares.com",

    # ---- commercial register ----
    "legal_name_ar": "شركة أحمد مساعد بن نصار",
    "legal_name_en": "AHMED MUSAED NASSAR Company",
    "brand_ar": "عوجا ريزيدنس",
    "brand_en": "Ouja Residence",
    "cr_number": "7050158810",

    # ---- national address (Arabic is the official form) ----
    "national_address_short": "RGMB7388",
    "address_ar": "مبنى 7388، الرقم الإضافي 3052، طريق التخصصي، حي المعذر الشمالي، الرياض 12314",
    "address_unit_ar": "مبنى نقوه، الدور الثاني، مكتب 16",
    "address_en": "Building 7388, Additional No. 3052, Al Takhassusi Road, "
                  "Al Maather Al Shamali District, Riyadh 12314",
    "address_unit_en": "Naqwa Building, 2nd Floor, Office 16",

    # ---- contact ----
    "email": "",            # "" = OUJA_CONTACT_EMAIL
    "phone": "",            # digits, intl format (9665XXXXXXXX); "" = STAY_WHATSAPP; both empty = hidden
    "tiktok_url": "",       # contact channels only — rendered as small footer icons
    "instagram_url": "",

    # ---- REGA «فال» licences (issued) ----
    "fal_marketing_no": "1200050611",
    "fal_management_no": "2200005540",

    # ---- Ministry of Tourism travel licence (pending) ----
    "travel_licence_no": "",
    "travel_licence_category_ar": "وكالة السفر والسياحة",
    "travel_licence_category_en": "Travel and Tourism Agency",

    # ---- business.sa e-commerce verification (pending) ----
    "business_sa_cert_url": "",
    "business_sa_badge_img": "",
}
