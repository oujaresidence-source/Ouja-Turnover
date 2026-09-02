# -*- coding: utf-8 -*-
"""digest.collect.base — the Candidate shape, the category classifier, the confidence
formula (brief §5.4) and small HTML helpers shared by every collector. Pure."""

import html as _html
import re
from datetime import datetime, timedelta

from ..dates import RIYADH

CATEGORIES = ("exhibition", "museum", "season", "family", "concert", "market",
              "comedy", "theatre", "sport", "cinema", "park", "b2b", "other")

# keyword → category, checked in order (first hit wins). Arabic + English, lowercase.
_CATEGORY_KEYS = (
    ("b2b", ("مؤتمر", "منتدى", "ورشة عمل", "conference", "summit", "forum", "b2b", "expo ", "معرض تجاري", "أعمال")),
    ("family", ("عائل", "أطفال", "family", "kids", "children", "سبيستون", "spacetoon", "سيرك", "circus", "كرتون")),
    ("exhibition", ("معرض", "بينالي", "فنون", "تركيب", "exhibition", "biennale", "art ", "gallery", "نور الرياض", "noor")),
    ("museum", ("متحف", "museum", "تراث", "heritage", "أثر")),
    ("season", ("موسم", "season", "مهرجان", "festival", "كرنفال", "carnival")),
    ("comedy", ("كوميدي", "ستاند أب", "stand-up", "standup", "comedy", "ضحك")),
    ("theatre", ("مسرحية", "theatre", "theater", "play ")),
    ("concert", ("حفل", "غنائ", "concert", "live in", "مباشرة", "أمسية", "ليلة", "موسيق", "music", "دي جي", "dj ", "sound", "session")),
    ("market", ("سوق", "بازار", "market", "bazaar", "souq", "flea")),
    ("sport", ("مباراة", "بطولة", "match", "tournament", "سباق", "race", "marathon", "ماراثون")),
    ("park", ("حديقة", "وادي", "park", "wadi", "trail", "مسار", "ممشى")),
)

_WS = re.compile(r"\s+")
_TAG = re.compile(r"<[^>]+>")


def text(fragment):
    """Tags stripped, entities decoded, whitespace collapsed."""
    return _WS.sub(" ", _html.unescape(_TAG.sub(" ", fragment or ""))).strip()


def category_of(*texts):
    blob = " ".join(t for t in texts if t).lower()
    for cat, keys in _CATEGORY_KEYS:
        if any(k in blob for k in keys):
            return cat
    return "other"


def make(section, ttl, sub, chip, url, day, source_name, source_url, fetched_at,
         category="other", district="", og=None, raw_conf=1.0, extra=None):
    """A Candidate: the dict the ranker, the voice pass and the schema all read."""
    c = {
        "section": section,
        "ttl": ttl or "",
        "sub": sub or "",
        "chip": chip or "الرياض",
        "url": url or "",
        "day": day or "",
        "source": {"name": source_name, "url": source_url, "fetched_at": fetched_at},
        "tags": {"category": category, "district": district},
        "art_hint": {"og": og} if og else {},
        "raw_conf": float(raw_conf),
    }
    if extra:
        c.update(extra)
    return c


def now_iso(now):
    return now.astimezone(RIYADH).isoformat(timespec="seconds")


def confidence(tier, agreement, fetched_at, now):
    """§5.4: 0.55·tier + 0.30·agreement + 0.15·freshness.
    tier: primary 1.0 / secondary 0.7 / search-only 0.5.
    agreement: 1.0 when a second source confirms date+venue, else 0.5.
    freshness: 1.0 today, linear to 0 at 7 days."""
    try:
        ts = datetime.fromisoformat((fetched_at or "").replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=RIYADH)
        age = max(0.0, (now - ts).total_seconds() / 86400.0)
    except Exception:
        age = 7.0
    fresh = max(0.0, 1.0 - age / 7.0)
    return round(0.55 * float(tier) + 0.30 * float(agreement) + 0.15 * fresh, 3)


TIER_PRIMARY, TIER_SECONDARY, TIER_SEARCH = 1.0, 0.7, 0.5
AGREE_YES, AGREE_NO = 1.0, 0.5


_STRIP = ("في الرياض", "بالرياض", "الرياض 2026", "2026", "2027", "حفل", "live in riyadh", "in riyadh", "- riyadh", "riyadh")
_FILLER = ("في", "مع", "the", "of", "a", "an")


def short_title(name, max_words=4, strip=_STRIP):
    """A ≤4-word title from a listing name: drop venue/city/year suffixes and filler,
    keep the first words, KEEP the original casing (film titles are often Latin).
    The voice pass may rewrite it later; this is the honest fallback that already
    obeys the cap."""
    n = name or ""
    for sfx in strip:
        n = re.sub(re.escape(sfx), " ", n, flags=re.I)
    n = re.sub(r"[·|–\-]+", " ", n)
    words = [w for w in _WS.split(n) if w]
    kept = [w for w in words if w.lower() not in _FILLER] or words
    out = " ".join(kept[:max_words]).strip(" ,.:")
    return out or (name or "")[:40]


def short_place(name, max_words=3):
    """A venue name trimmed to the facts line («مسرح بكر الشدي», not a full address)."""
    words = [w for w in _WS.split(name or "") if w]
    return " ".join(words[:max_words])


def week_window(week, days_before=0):
    """(start, end) dates inclusive for 'this weekend', optionally reaching back."""
    return week.thu - timedelta(days=days_before), week.sat
