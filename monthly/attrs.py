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

# ─────────────────────────── THE ANCHOR IS THE CALIBRATION ───────────────────────────
# Every score is RELATIVE TO OUR OWN PORTFOLIO, not to an abstract idea of good.
# The multiplier formula is 1 + beta x (score - 5)/5, so a score of 5 means "this
# unit sits exactly at the middle of the 53" and contributes nothing.
#
# This matters more than any individual weight. If a scorer reads 5 as "fine,
# nothing special" instead of "the median Ouja unit", everything lands at 7-8,
# every multiplier points up, and THE WHOLE PORTFOLIO INFLATES BY THE SAME AMOUNT
# — invisibly, because nothing looks wrong on any single unit. Twelve attributes
# all multiplying upward until the clamp catches them is the signature of a bad
# anchor, not of an exceptional apartment.
SCORE_ANCHOR_AR = ("5 = الوحدة المتوسطة عندنا في عوجا · 1 = الأضعف في محفظتنا · "
                   "10 = الأفضل في محفظتنا")
SCORE_ANCHOR_EN = ("5 = the median Ouja unit · 1 = worst in our portfolio · "
                   "10 = best in our portfolio")
# A bool is anchored the same way: yes/no against the portfolio, not the world.
BOOL_ANCHOR_AR = "نعم / لا — بالمقارنة مع بقية وحداتنا"
BOOL_ANCHOR_EN = "Yes / no, judged against the rest of our units"

# ───────────────────────────── THE SCORING PROTOCOL ─────────────────────────────
# How the 53 get scored decides whether every price is right or wrong. This lives
# here, next to the scale it governs, because a protocol in a document is a
# protocol nobody reads while typing a 7.
#
#   1. ONE PERSON SCORES ALL 53, IN ONE SITTING.
#      A single consistently-wrong anchor is fixable with one correction applied
#      to everything. Five people with five private anchors is not fixable at all,
#      because the error is different on every unit and invisible on each.
#
#   2. SET THE POLES FIRST.
#      Before scoring anything, name the best unit and the worst unit in the
#      portfolio FOR THAT ATTRIBUTE. Those two are the 10 and the 1. Everything
#      else is placed between two real apartments rather than against an idea.
#
#   3. RANK BEFORE SCORING.
#      For each attribute, order all 53 best to worst FIRST, then assign numbers
#      down the list. Absolute scoring drifts upward — everything feels "pretty
#      good" — and forced ranking cannot drift, because someone has to be last.
#
#   4. ONE ATTRIBUTE ACROSS ALL 53 BEFORE MOVING TO THE NEXT.
#      Never score one unit across all 16. Doing it unit-by-unit lets an overall
#      impression of the apartment bleed into every individual attribute, which
#      turns 16 measurements into one opinion recorded 16 times.
#
SCORING_PROTOCOL_AR = [
    "شخص واحد يقيّم الـ53 كلها، بجلسة وحدة",
    "قبل ما تبدأ: حدّد أفضل وحدة وأسوأ وحدة بهذي الصفة — هذي 10 وهذي 1",
    "رتّب قبل ما تعطي أرقام: صفّ الـ53 من الأفضل للأسوأ، بعدين اكتب الأرقام",
    "أكمل صفة وحدة على كل الـ53 قبل ما تنتقل للصفة اللي بعدها",
]
SCORING_PROTOCOL_EN = [
    "One person scores all 53, in one sitting",
    "Set the poles first: name the best and worst unit for this attribute — 10 and 1",
    "Rank before scoring: order all 53 best to worst, then assign the numbers",
    "Finish one attribute across all 53 before moving to the next",
]

# If the MEDIAN score of an attribute across the portfolio sits materially above
# 5, the anchor is wrong and every price built on it is wrong in the same
# direction. Half a point is materially.
ANCHOR_MEDIAN_TOL = 0.5

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
            # Carried on every row so the anchor is in front of whoever is
            # scoring, not buried in a doc nobody opens while typing a 7.
            "anchor_ar": (BOOL_ANCHOR_AR + " (5 = المتوسط)") if kd == "bool" else SCORE_ANCHOR_AR,
            "anchor_en": (BOOL_ANCHOR_EN + " (5 = median)") if kd == "bool" else SCORE_ANCHOR_EN,
        })
    return out


def median_report(all_unit_values):
    """Median score per attribute across the whole portfolio — the anchor check.

    A median materially above 5 means the scale is mis-anchored, and every price
    built on it is wrong in the same direction. That is invisible on any single
    unit, which is exactly why it needs a portfolio-level report.
    """
    import statistics
    out = []
    for k in KEYS:
        scores = []
        for vals in (all_unit_values or []):
            s = to_score(k, (vals or {}).get(k))
            if s is not None:
                scores.append(s)
        med = statistics.median(scores) if scores else None
        out.append({
            "key": k, "label_ar": label_ar(k), "label_en": label_en(k),
            "beta": beta(k), "n_scored": len(scores), "median": med,
            "anchor_suspect": med is not None and abs(med - 5.0) > ANCHOR_MEDIAN_TOL,
            "direction": None if med is None else ("high" if med > 5 else
                                                   ("low" if med < 5 else "even")),
        })
    out.sort(key=lambda r: (not r["anchor_suspect"], -r["beta"]))
    return out
