# -*- coding: utf-8 -*-
"""
monthly.attrs — the 16 scored unit attributes and their starting betas.

THESE BETAS ARE PRIORS, NOT TRUTH. They are a starting guess written down so it
can be argued with and later corrected against evidence. Every computed price
records (predicted, actual) in monthly_outcomes when a monthly booking lands, so
BETA_VERSION 1 can be refit once there is something to fit it to. Until
PAIRED_OBS reaches CALIBRATED_AT, the UI says «تقدير» and never «سعر» — a
published number that turns out wrong is a fine under the REGA advertising
regulation, not a typo.

sqm carries the largest weight because floor area is the strongest predictor in
every rental model there is. We currently record it for NOT ONE unit. That is
not a reason to lower the weight; it is the single most valuable piece of data
capture available to this company, and the model saying so is useful.

THREE STATES, NEVER TWO (the match/facts.py rule)
    True / False / None(unanswered)
An unanswered attribute contributes a multiplier of exactly 1.0. It is never
silently scored as 5, never rendered as a yes, and never rendered as a no. It is
rendered as «غير مسجّل», because the gaps are the point: an owner reading a
quote should see what we know and what we do not.
"""

# (key, ar, en, beta, kind)   kind: "score" 1..10 | "bool" | "number"
BETAS = [
    ("sqm",              "المساحة الكلية",      "Total sqm",            0.25, "number"),
    ("design",           "التشطيب والتصميم",    "Design / finish",      0.15, "score"),
    ("compound",         "مرافق المجمّع",       "Compound amenities",   0.10, "score"),
    ("furniture",        "جودة الأثاث",         "Furniture quality",    0.10, "score"),
    ("review_score",     "تقييم الوحدة",        "Unit review score",    0.10, "number"),
    ("living_room",      "حجم الصالة",          "Living room size",     0.08, "score"),
    ("new_build",        "بناء جديد",           "New build (<3 yrs)",   0.08, "bool"),
    ("view_light",       "الإطلالة والإضاءة",   "View & light",         0.07, "score"),
    ("parking_covered",  "موقف مغطّى",          "Covered parking",      0.06, "bool"),
    ("majlis",           "مجلس منفصل",          "Separate majlis",      0.06, "bool"),
    ("bathrooms",        "دورات المياه",        "Bathrooms / ensuite",  0.05, "number"),
    ("metro",            "قرب المترو",          "Metro proximity",      0.05, "score"),
    ("ac_central",       "تكييف مركزي",         "Central AC",           0.04, "bool"),
    ("floor_lift",       "الدور والمصعد",       "Floor + lift",         0.04, "score"),
    ("self_entry",       "دخول ذاتي",           "Self-entry",           0.03, "bool"),
    ("wifi_tier",        "سرعة الإنترنت",       "WiFi tier",            0.03, "score"),
]

BETA_VERSION = 1

# Below this many (predicted, actual) pairs the model has never been checked
# against reality, so its output is «تقدير» and is labelled as such everywhere.
CALIBRATED_AT = 200

# More than this many unanswered attributes and confidence drops to "low": we are
# no longer describing a unit, we are describing a shape.
MAX_UNANSWERED_BEFORE_LOW = 6

_BY_KEY = {k: (ar, en, beta, kind) for (k, ar, en, beta, kind) in BETAS}

KEYS = [k for (k, _a, _e, _b, _kd) in BETAS]

# A bool that is TRUE scores this; FALSE scores this. Chosen so that a plain
# yes/no attribute moves the price by roughly its beta, and a "no" is a mild
# penalty rather than a cliff — a unit without a majlis is a normal unit, not a
# broken one.
_BOOL_TRUE_SCORE = 9.0
_BOOL_FALSE_SCORE = 4.0

# «number» attributes are read on their own real-world scale and mapped to 1..10
# by these anchors: (value_at_score_1, value_at_score_10). Anything outside is
# clamped, so one absurd typed number cannot run away with the price.
_NUMBER_ANCHORS = {
    "sqm":          (60.0, 260.0),    # a small 1BR .. a large 3BR, Riyadh stock
    "review_score": (4.0, 5.0),       # the live range that actually separates units
    "bathrooms":    (1.0, 4.0),
}


def keys():
    return list(KEYS)


def label_ar(key):
    row = _BY_KEY.get(key)
    return row[0] if row else key


def label_en(key):
    row = _BY_KEY.get(key)
    return row[1] if row else key


def beta(key):
    row = _BY_KEY.get(key)
    return row[2] if row else 0.0


def kind(key):
    row = _BY_KEY.get(key)
    return row[3] if row else "score"


def is_known(key):
    return key in _BY_KEY


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


def to_score(key, value):
    """One stored attribute value -> a 1..10 score, or None if unanswered.

    None in, None out. This function is the ONLY place a raw value becomes a
    score, so the three-state rule cannot be broken somewhere else and quietly
    turn a missing answer into a mediocre one.
    """
    if value is None:
        return None
    kd = kind(key)

    if kd == "bool":
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("", "none", "null", "unknown", "غير مسجل", "غير مسجّل"):
                return None
            value = s in ("1", "true", "yes", "y", "on", "نعم")
        return _BOOL_TRUE_SCORE if bool(value) else _BOOL_FALSE_SCORE

    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:                      # NaN is not an answer
        return None

    if kd == "number":
        lo, hi = _NUMBER_ANCHORS.get(key, (0.0, 10.0))
        if hi <= lo:
            return None
        return _clamp(1.0 + 9.0 * (v - lo) / (hi - lo), 1.0, 10.0)

    return _clamp(v, 1.0, 10.0)     # "score" is already 1..10


def multiplier(key, value):
    """The factor this one attribute contributes. Unanswered contributes EXACTLY
    1.0 — it does not nudge the price in either direction."""
    s = to_score(key, value)
    if s is None:
        return 1.0
    return 1.0 + beta(key) * (s - 5.0) / 5.0


def unanswered(values):
    """How many of the 16 we do not know for this unit."""
    return sum(1 for k in KEYS if to_score(k, (values or {}).get(k)) is None)


def rows_for_ui(values):
    """Every attribute, answered or not, in render order. Unanswered rows carry
    answered=False so the UI can say «غير مسجّل» instead of hiding them."""
    values = values or {}
    out = []
    for (k, ar, en, b, kd) in BETAS:
        raw = values.get(k)
        s = to_score(k, raw)
        out.append({
            "key": k, "label_ar": ar, "label_en": en, "beta": b, "kind": kd,
            "value": raw, "score": s, "answered": s is not None,
            "mult": multiplier(k, raw),
        })
    return out
