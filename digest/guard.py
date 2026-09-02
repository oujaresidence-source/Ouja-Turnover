# -*- coding: utf-8 -*-
"""digest.guard — the truth guard (brief §6). Runs on the ASSEMBLED HTML plus the
payload before Chromium is launched, and raises DigestError on anything that would
make the poster wrong: a fact without a fresh source, a date outside Thu–Sat, a
Western numeral in prose, a title/sub over its word cap, a banned phrase, a link that
was not verified, a section over its cap, an empty or placeholder card.

`fold_digits` and `visible_text` come from cp.guard (owner-approved reuse 2026-09-02):
a fix to one is a fix to both. cp.guard's disclosure denylist is NOT applied here —
the digest publishes no company figures. Pure: no host, no network."""

import html as _html
import re
from datetime import datetime, timedelta

from cp.guard import fold_digits, visible_text

from . import schema, voice
from .dates import AR_MONTHS, RIYADH, in_week

MAX_SOURCE_AGE_DAYS = 7
PROSE_CLASSES = ("claim", "sub", "ttl", "eyebrow", "when", "kicker", "lede")
PLACEHOLDER_WORDS = ("قريباً", "قريبا", "placeholder", "lorem", "TBD", "TODO")
OFF_WINDOW_DAYS = ("الأحد", "الاثنين", "الإثنين", "الثلاثاء", "الأربعاء", "اثنين", "إثنين", "ثلاثاء", "أربعاء")

_MONTH_INDEX = {name: i for i, name in AR_MONTHS.items()}
_MONTH_RX = re.compile(r"(\d{1,2})\s+(%s)" % "|".join(AR_MONTHS.values()))
_OFFDAY_RX = re.compile("|".join(OFF_WINDOW_DAYS))
_LTR_RX = re.compile(r"<span\b[^>]*dir=\"ltr\"[^>]*>.*?</span>", re.S | re.I)
_TAG_RX = re.compile(r"<[^>]+>")
_URL_ATTR_RX = re.compile(r"\b(?:href|data-url)\s*=\s*[\"']([^\"']+)[\"']", re.I)
_WESTERN_RX = re.compile(r"[0-9]")


class DigestError(AssertionError):
    """The digest must not render — the message names every reason."""


def _elements(markup, classes):
    """Inner HTML of every element whose class list contains one of `classes`
    (leaf-ish: the renderer keeps these elements flat), plus bare <p> blocks when
    'p' is in classes."""
    out = []
    for cls in classes:
        if cls == "p":
            rx = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S | re.I)
            out += [(cls, m.group(1)) for m in rx.finditer(markup)]
            continue
        rx = re.compile(r"<(\w+)\b[^>]*class=\"[^\"]*\b%s\b[^\"]*\"[^>]*>(.*?)</\1>" % re.escape(cls),
                        re.S | re.I)
        out += [(cls, m.group(2)) for m in rx.finditer(markup)]
    return out


def _text(inner):
    return re.sub(r"\s+", " ", _html.unescape(_TAG_RX.sub(" ", inner or ""))).strip()


def _parse_ts(s):
    try:
        d = datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=RIYADH)
    return d


def _check_sources(errs, payload, now):
    for key, i, it in schema.primaries(payload):
        src = it.get("source") or {}
        where = "%s[%d]" % (key, i)
        if not src:
            continue                      # schema.validate already reports the missing source
        ts = _parse_ts(src.get("fetched_at"))
        if ts is None:
            errs.append("%s: source.fetched_at unreadable (%r)" % (where, src.get("fetched_at")))
        elif now - ts > timedelta(days=MAX_SOURCE_AGE_DAYS):
            errs.append("%s: source.fetched_at is older than %d days (%s)" % (where, MAX_SOURCE_AGE_DAYS, src.get("fetched_at")))


def _check_dates(errs, markup, week):
    prose = _elements(markup, PROSE_CLASSES + ("p",))
    for cls, inner in prose:
        t = fold_digits(_text(inner))
        if _OFFDAY_RX.search(t):
            errs.append("date outside the Thu–Sat window in .%s: «%s»" % (cls, t[:60]))
            continue
        for m in _MONTH_RX.finditer(t):
            day, month = int(m.group(1)), _MONTH_INDEX[m.group(2)]
            ok = False
            for year in (week.thu.year, week.sat.year):
                try:
                    if in_week(week, datetime(year, month, day).date()):
                        ok = True
                except ValueError:
                    pass
            if not ok:
                errs.append("date outside the Thu–Sat window in .%s: «%s»" % (cls, m.group(0)))


def _check_numerals(errs, markup):
    for cls, inner in _elements(markup, PROSE_CLASSES + ("p",)):
        t = _text(_LTR_RX.sub(" ", inner))
        if _WESTERN_RX.search(t):
            errs.append("Western numeral in prose (.%s): «%s»" % (cls, t[:60]))


def _check_cards(errs, markup):
    for _, inner in _elements(markup, ("ttl",)):
        t = _text(inner)
        if not t:
            errs.append("empty card title")
        elif any(w.lower() in t.lower() for w in PLACEHOLDER_WORDS):
            errs.append("placeholder card: «%s»" % t)
        elif voice.word_count(t) > voice.MAX_TITLE_WORDS:
            errs.append("ttl over %d words: «%s»" % (voice.MAX_TITLE_WORDS, t))
    for _, inner in _elements(markup, ("sub",)):
        t = _text(inner)
        if voice.word_count(t) > voice.MAX_SUB_WORDS:
            errs.append("sub over %d words: «%s»" % (voice.MAX_SUB_WORDS, t))


def _check_urls(errs, markup, payload):
    verified = set(payload.get("verified_urls") or [])
    for u in _URL_ATTR_RX.findall(markup):
        u = _html.unescape(u.strip())
        if not u.lower().startswith(("http://", "https://")):
            continue
        if u not in verified:
            errs.append("url not in the verified set: %s" % u)


_PRICE_TOKENS = ("ريال", "مجاني", "حسب التذكرة", "حسب العرض")
_DAY_WORDS = ("الخميس", "الجمعة", "السبت")
MAX_ART_RATIO = 3.0


def _check_facts(errs, payload):
    """Owner rule (2026-09-03): every card says WHEN · WHERE · HOW MUCH, in that order."""
    for key, i, it in schema.primaries(payload):
        if key == "fixtures":
            continue
        where = "%s[%d]" % (key, i)
        parts = [p.strip() for p in (it.get("sub") or "").split("·")]
        if len(parts) < 3:
            errs.append("%s: sub must be «اليوم والتاريخ · المكان · السعر» (got «%s»)" % (where, it.get("sub", "")))
            continue
        if not any(parts[0].startswith(d) for d in _DAY_WORDS):
            errs.append("%s: sub must start with the day (got «%s»)" % (where, parts[0]))
        if not parts[1]:
            errs.append("%s: sub has no place" % where)
        if not any(t in parts[-1] for t in _PRICE_TOKENS):
            errs.append("%s: sub has no price (got «%s»)" % (where, parts[-1]))
        art = it.get("art") or {}
        w, h = art.get("w") or 0, art.get("h") or 0
        if w and h and max(w, h) / float(min(w, h)) > MAX_ART_RATIO:
            errs.append("%s: image ratio %.1f would need a crop — type-only instead" % (where, max(w, h) / float(min(w, h))))
        r = it.get("ratings") or {}
        if (r.get("imdb") is not None or r.get("rt") is not None) and not r.get("sources"):
            errs.append("%s: a rating without an opened source page" % where)
        if key == "worth" and not it.get("verified_on"):
            errs.append("%s: a place without a verified_on date" % where)


def scan(markup, payload, week, now):
    """Every reason this digest must not render; [] means clean."""
    errs = list(schema.validate(payload))
    _check_sources(errs, payload, now)
    _check_facts(errs, payload)
    _check_dates(errs, markup, week)
    _check_numerals(errs, markup)
    _check_cards(errs, markup)
    for label in voice.slop_hits(visible_text(markup)):
        errs.append("banned phrase «%s»" % label)
    _check_urls(errs, markup, payload)
    return errs


def assert_clean(markup, payload, week, now):
    hits = scan(markup, payload, week, now)
    if hits:
        raise DigestError("digest guard failed (%d):\n  " % len(hits) + "\n  ".join(hits))
    return True
