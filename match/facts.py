"""Owner-declared apartment facts. The single source of truth for what a unit
actually has — deliberately NOT derived from Hostaway amenities, which proved
unreliable enough to produce false statements to guests.

Three states per fact: True (yes), False (no), missing/None (not answered).
Missing must never be rendered as either yes or no — silence beats a guess.
"""

# (key, ar, en, group)
FACTS = [
    ("parking",          "موقف خاص",              "Private parking",         "basics"),
    ("elevator",         "مصعد",                  "Elevator",                "basics"),
    ("ground_floor",     "دور أرضي",              "Ground floor",            "basics"),
    ("full_kitchen",     "مطبخ كامل",             "Full kitchen",            "basics"),
    ("washer",           "غسالة",                 "Washer",                  "basics"),
    ("workspace",        "مكتب للشغل",            "Workspace",               "basics"),
    ("pool",             "مسبح",                  "Pool",                    "basics"),
    ("driver_room",      "غرفة سائق",             "Driver room",             "basics"),
    ("elderly_friendly", "مناسبة لكبار السن",     "Elderly friendly",        "basics"),
    ("kids_ok",          "تسمح أطفال",            "Kids welcome",            "basics"),
    ("private_entrance", "مدخل مستقل",            "Private entrance",        "privacy"),
    ("gated_compound",   "مجمّع مغلق بحراسة",     "Gated compound",          "privacy"),
    ("ladies_entrance",  "مدخل نسائي منفصل",      "Separate ladies entrance","privacy"),
    ("home_cinema",      "سينما منزلية",          "Home cinema",             "fun"),
    ("big_screen",       "شاشة كبيرة",            "Big screen",              "fun"),
    ("balcony",          "بلكونة",                "Balcony",                 "fun"),
    ("view",             "إطلالة",                "View",                    "fun"),
]

GROUPS = [("basics", "الأساسيات"), ("privacy", "الخصوصية والمدخل"), ("fun", "الترفيه")]

_BY_KEY = {k: (ar, en, grp) for k, ar, en, grp in FACTS}


def keys():
    """Ordered list of every known fact key."""
    return [k for k, _ar, _en, _grp in FACTS]


def label_ar(key):
    """Arabic label for a fact key, or None if unknown."""
    row = _BY_KEY.get(key)
    return row[0] if row else None


def label_en(key):
    """English label for a fact key, or None if unknown."""
    row = _BY_KEY.get(key)
    return row[1] if row else None


def by_group():
    """GROUPS with each group's facts nested under it:
    [(group_key, group_ar, [(key, ar, en), ...]), ...] — same order as FACTS/GROUPS."""
    out = []
    for gkey, gar in GROUPS:
        rows = [(k, ar, en) for k, ar, en, grp in FACTS if grp == gkey]
        out.append((gkey, gar, rows))
    return out


def normalize(raw):
    """Arbitrary dict -> only known fact keys with strictly boolean values.

    Unknown keys are dropped. Non-boolean values (None, strings, ints,
    "true"/"false" text, etc.) are dropped too — this function NEVER coerces
    truthiness; a bool is the only value that counts as an actual answer.
    Missing stays missing rather than being guessed at.
    """
    if not isinstance(raw, dict):
        return {}
    valid = set(keys())
    out = {}
    for k, v in raw.items():
        if k in valid and isinstance(v, bool):
            out[k] = v
    return out
