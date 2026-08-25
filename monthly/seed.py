# -*- coding: utf-8 -*-
"""
monthly.seed — fill in what we already know from elsewhere, and REFUSE to guess
the rest.

PURE. Everything arrives as an argument; nothing here opens a socket or a file.
data.py gathers the raw material (S8) and hands it in, which is what makes the
mapping decisions below testable and arguable.

WHAT THIS DELIBERATELY DOES NOT MAP
The brief suggested seeding several attributes from match/facts.py. Read closely,
most of those pairs are near-synonyms rather than the same fact, and seeding them
would put invented data behind a number we show to an owner:

  * match «موقف خاص» (private parking) is NOT «موقف مغطّى» (covered parking).
    A private uncovered bay in a Riyadh summer is a different product. We map
    covered parking only from words that actually mean covered — garage, carport,
    كراج, مغطى.
  * match «مدخل مستقل» (private entrance) is NOT «دخول ذاتي» (self check-in).
    One is architecture, the other is how the key is handed over.
  * match «إطلالة» is a yes/no. Our view_light is a 1..10 judgement of view AND
    natural light. Turning a bool into a 7 is inventing a precision nobody
    measured — exactly the thing the three-state rule exists to prevent.
  * «مرافق المجمّع» cannot be derived from a compound's NAME. Knowing a unit is
    in Calma 90 does not tell you what score its facilities deserve.

All of those stay unanswered until a human scores them, and the UI says
«غير مسجّل». An honest blank is worth more than a confident invention: the blank
gets filled in, the invention gets quoted to an owner.
"""

import re

from . import attrs

# Words that genuinely mean COVERED parking. «موقف»/«parking» alone is not here.
_COVERED_WORDS = ("garage", "carport", "covered parking", "underground parking",
                  "كراج", "كراچ", "قراج", "موقف مغطى", "موقف مغطّى", "مواقف مغطاة",
                  "بدروم سيارات")
_MAJLIS_WORDS = ("majlis", "مجلس")
_SELF_ENTRY_WORDS = ("self check-in", "self check in", "self checkin", "smart lock",
                     "keypad", "lockbox", "دخول ذاتي", "الدخول الذاتي", "قفل ذكي")

# Bayesian smoothing constants, taken from match.engine so there is ONE rating
# model in this codebase and not two that disagree on the same unit.
PRIOR_RATING = 4.6
PRIOR_WEIGHT = 12


def smoothed_rating(rating, count):
    """A 5.0 from two reviews must not outrank a 4.9 from ninety. Returns None
    when there is nothing to smooth — no reviews is not a rating of 4.6."""
    if rating is None or not count:
        return None
    try:
        r, n = float(rating), int(count)
    except (TypeError, ValueError):
        return None
    if n <= 0 or r <= 0:
        return None
    return ((r * n) + (PRIOR_RATING * PRIOR_WEIGHT)) / (n + PRIOR_WEIGHT)


def _haystack(listing):
    parts = [str(listing.get("name") or ""), str(listing.get("desc") or ""),
             str(listing.get("public_desc") or "")]
    parts += [str(a) for a in (listing.get("amenities") or [])]
    return " ".join(parts).lower()


def _has(hay, words):
    return any(w in hay for w in words)


def _bathrooms(listing):
    v = listing.get("bathrooms")
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _wifi_score(wifi_mbps):
    """Download speed -> a 1..10 tier. Anchored on what a remote worker actually
    notices: 25 Mbps is a bad video call, 300 is indistinguishable from an office."""
    if wifi_mbps in (None, ""):
        return None
    try:
        m = float(wifi_mbps)
    except (TypeError, ValueError):
        return None
    if m <= 0:
        return None
    lo, hi = 25.0, 300.0
    s = 1.0 + 9.0 * (m - lo) / (hi - lo)
    return max(1.0, min(s, 10.0))


def seed_for_unit(listing, rating=None, rating_count=None, wifi_mbps=None):
    """One unit -> {attr_key: value} for ONLY the attributes we can honestly fill.
    Keys we cannot answer are simply absent, which is how they stay unanswered."""
    out = {}
    hay = _haystack(listing or {})

    rs = smoothed_rating(rating, rating_count)
    if rs is not None:
        out["review_score"] = round(rs, 3)

    b = _bathrooms(listing or {})
    if b is not None:
        out["bathrooms"] = b

    w = _wifi_score(wifi_mbps)
    if w is not None:
        out["wifi_tier"] = round(w, 2)

    # Text evidence is one-directional: finding the word proves the feature is
    # there. NOT finding it proves only that nobody wrote it down, so absence is
    # left unanswered rather than recorded as False.
    if _has(hay, _COVERED_WORDS):
        out["parking_covered"] = True
    if _has(hay, _MAJLIS_WORDS):
        out["majlis"] = True
    if _has(hay, _SELF_ENTRY_WORDS):
        out["self_entry"] = True

    return out


def seed_all(listings, ratings=None, wifi=None):
    """[listing] -> {unit_id: {attr_key: value}}. ratings is
    {lid: {"rating": x, "count": n}} as _gw_ratings_map returns it."""
    ratings = ratings or {}
    wifi = wifi or {}
    out = {}
    for l in (listings or []):
        try:
            lid = int(l.get("id"))
        except (TypeError, ValueError):
            continue
        r = ratings.get(lid) or {}
        vals = seed_for_unit(l, r.get("rating"), r.get("count"), wifi.get(lid))
        if vals:
            out[lid] = vals
    return out


def coverage_report(seeded, total_units):
    """What the seed could NOT answer — the data-capture worklist, in priority
    order by beta. This is the most useful thing this module produces: it names,
    in weight order, the facts that are costing us pricing accuracy."""
    counts = {k: 0 for k in attrs.keys()}
    for vals in (seeded or {}).values():
        for k in vals:
            if k in counts:
                counts[k] += 1
    rows = []
    for k in attrs.keys():
        have = counts[k]
        rows.append({
            "key": k, "label_ar": attrs.label_ar(k), "label_en": attrs.label_en(k),
            "beta": attrs.beta(k), "have": have,
            "missing": max(0, int(total_units or 0) - have),
        })
    rows.sort(key=lambda r: (-r["missing"] * r["beta"], -r["beta"]))
    return rows


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(name):
    return _SLUG_RE.sub("-", str(name or "").lower()).strip("-")
