# -*- coding: utf-8 -*-
"""
schedule.coverage — best-effort bridge from a Hostaway *listing name* to the emoji of whoever
covers that apartment on a given date.

The schedule package and the OujaCT cleaning channels use TWO independent apartment-name lists
(the schedule has short owner-typed names like «الملقا 1» / «A5»; Hostaway names are «Ouja | …»).
They are not linked anywhere, so we match by *normalized name tokens* — by design this is
best-effort: when no schedule apartment lines up with a listing, the caller falls back to a
neutral placeholder (per the owner's choice). Everything here is read-only and never raises out
to the caller (channel creation must never break on a match miss).
"""

import re

from . import db, engine

# Arabic letter folding so «أ/إ/آ»→«ا», «ة»→«ه», «ى»→«ي», drop tatweel + diacritics.
_AR_FOLD = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"}
# Brand / filler tokens that carry no apartment identity — ignored on both sides of the match.
_STOP = {"ouja", "عوجا", "self", "entry", "selfentry", "apartment", "apt", "شقه", "شقة", "unit"}


def _norm(s):
    s = (s or "").lower().replace("ـ", "")
    s = re.sub(r"[ً-ْ]", "", s)            # Arabic diacritics
    for k, v in _AR_FOLD.items():
        s = s.replace(k, v)
    return s


def _tokens(s):
    """Distinctive alphanumeric/Arabic tokens, brand/filler removed."""
    return [t for t in re.findall(r"[0-9a-zء-ي]+", _norm(s)) if t and t not in _STOP]


def _distinctive(toks):
    """A match must rest on at least one token of length >= 2 (e.g. «A5», «الملقا», «Jood13») so a
    lone single character/digit — which would be a substring of almost every listing — can't drag
    in a false positive on its own."""
    return any(len(t) >= 2 for t in toks)


def cover_map(date_iso):
    """{apartment_id: {name, emoji, color}} for whoever covers each schedule apartment on `date_iso`
    (own base + coverage of off/leave colleagues), plus the apartments list. Read-only."""
    emps = db.employees()
    apts = db.apartments()
    ovs = db.overrides()
    absent = {a["employee_id"] for a in db.absences_on(date_iso)}
    wd = engine.to_weekday(date_iso)
    r = engine.compute_day(wd, emps, apts, ovs, absent_ids=absent)
    m = {}
    for w in r["working"]:
        who = {"name": w.get("name"), "emoji": w.get("emoji"), "color": w.get("color")}
        for a in w["own"]:
            m[a["id"]] = who
        for c in w["coverage"]:
            m[c["apartment"]["id"]] = who
    return m, apts


def match_apartment(listing_name, apts):
    """Best schedule apartment for a Hostaway listing name, or None. All of the apartment's
    distinctive tokens must appear in the listing; the longest such match wins (so «Jood13»
    beats «Jood1» and «202 الملقا» beats a bare «الملقا»)."""
    hay = _norm(listing_name)
    if not hay:
        return None
    best, best_score = None, 0
    for a in apts:
        toks = _tokens(a.get("name"))
        if not toks or not _distinctive(toks):
            continue
        if all(t in hay for t in toks):
            score = sum(len(t) for t in toks)
            if score > best_score:
                best, best_score = a, score
    return best


def best_listing(apt_name, listings):
    """Reverse of match_apartment: for a schedule apartment NAME, the best Hostaway listing id whose
    name contains all the apartment's distinctive tokens (longest match wins), or None. Used by the
    one-time auto-link. `listings` = [{id, name}, ...]."""
    toks = _tokens(apt_name)
    if not toks or not _distinctive(toks):
        return None
    best, best_score = None, 0
    for L in listings or []:
        hay = _norm(L.get("name"))
        if hay and all(t in hay for t in toks):
            score = sum(len(t) for t in toks)
            if score > best_score:
                best, best_score = L.get("id"), score
    return best


def cover_for_listing_id(listing_id, date_iso):
    """EXACT cover lookup: {name, emoji, color, apartment} of whoever covers the schedule apartment
    linked to Hostaway `listing_id` on `date_iso`, or None if no apartment is linked to it / no
    covering employee. Preferred over the fuzzy name match. Never raises."""
    try:
        listing_id = int(listing_id)
    except (TypeError, ValueError):
        return None
    try:
        m, apts = cover_map(date_iso)
        for a in apts:
            if a.get("listing_id") is not None and int(a["listing_id"]) == listing_id:
                cov = m.get(a["id"])
                if not cov:
                    return None
                out = dict(cov)
                out["apartment"] = a.get("name")
                return out
        return None
    except Exception:
        return None


def cover_for_listing(listing_name, date_iso):
    """{name, emoji, color, apartment} of whoever covers the apartment behind `listing_name` on
    `date_iso`, or None on any miss. Never raises."""
    try:
        m, apts = cover_map(date_iso)
        apt = match_apartment(listing_name, apts)
        if not apt:
            return None
        cov = m.get(apt["id"])
        if not cov:
            return None
        out = dict(cov)
        out["apartment"] = apt.get("name")
        return out
    except Exception:
        return None


def cover_emoji_for_listing(listing_name, date_iso, placeholder=""):
    """Emoji of the employee covering the apartment behind `listing_name` on `date_iso`.
    Returns `placeholder` on any miss (no name match, no covering employee, or no emoji set).
    Never raises."""
    cov = cover_for_listing(listing_name, date_iso)
    emoji = ((cov or {}).get("emoji") or "").strip()
    return emoji or placeholder
