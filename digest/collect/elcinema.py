# -*- coding: utf-8 -*-
"""Cinema — elcinema.com/now/sa/ (films showing in Saudi cinemas, Arabic).

VOX (ksa.voxcinemas.com) drops non-browser connections at the Akamai edge, so the
"new this week" signal comes from elcinema's per-film «تاريخ العرض» instead: a film whose
release date falls in [Thu−6d, Sat] is new; everything else on the page is "showing".
The digest wants exactly three films that are releasing OR showing that weekend, newest
first. Fixture tests/fixtures/digest/elcinema-now-sa-20260902.html (2026-09-02)."""

import re
from datetime import date, timedelta

from . import base
from ..dates import AR_MONTHS, ar_date

SOURCE = "elcinema"
NOW_URL = "https://elcinema.com/now/sa/"
ORIGIN = "https://elcinema.com"
NEW_WINDOW_DAYS = 6

_ROW_RX = re.compile(r'<div class="row" id="w(\d+)">')
_TITLE_RX = re.compile(r'<h3><a href="/work/(\d+)/">(.*?)</a></h3>', re.S)
_RELEASE_RX = re.compile(r'تاريخ العرض:</strong>\s*<a[^>]*>\s*(\d{1,2})\s+(\S+)\s*</a>\s*<a[^>]*>\s*(\d{4})\s*</a>', re.S)
_GENRE_RX = re.compile(r'/index/work/genre/\d+"[^>]*>([^<]+)</a>')
_AGE_RX = re.compile(r'<li>\+(\d{1,2})</li>')
_MONTH_INDEX = {v: k for k, v in AR_MONTHS.items()}
_MONTH_ALIASES = {"يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "إبريل": 4, "مايو": 5,
                  "يونيو": 6, "يوليو": 7, "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10,
                  "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}


def _month(name):
    return _MONTH_INDEX.get(name) or _MONTH_ALIASES.get(name)


def _genres_ar(genres):
    g = [base.text(x) for x in genres if base.text(x)]
    g = g[:2]
    if not g:
        return ""
    return " و".join(g) if len(g) == 2 else g[0]


def parse(html, week, now, page_url=NOW_URL):
    """-> (candidates, dropped). Candidates carry `new_this_week` and `release_iso`."""
    cands, dropped = [], []
    fetched = base.now_iso(now)
    starts = [m.start() for m in _ROW_RX.finditer(html)]
    new_from = week.thu - timedelta(days=NEW_WINDOW_DAYS)
    seen = set()
    for i, s in enumerate(starts):
        row = html[s:starts[i + 1] if i + 1 < len(starts) else len(html)]
        t = _TITLE_RX.search(row)
        if not t:
            continue
        wid, title = t.group(1), base.text(t.group(2))
        url = "%s/work/%s/" % (ORIGIN, wid)
        if not title or url in seen:
            continue
        seen.add(url)
        rel = _RELEASE_RX.search(row)
        release = None
        if rel:
            mon = _month(rel.group(2))
            if mon:
                try:
                    release = date(int(rel.group(3)), mon, int(rel.group(1)))
                except ValueError:
                    release = None
        if release is None:
            dropped.append({"ttl": base.short_title(title), "reason": "بدون تاريخ عرض", "url": url})
            continue
        if release > week.sat:
            continue                                   # not yet showing that weekend
        genres = _GENRE_RX.findall(row)
        age = _AGE_RX.search(row)
        # a date in the copy must fall inside Thu–Sat (the guard enforces it): a film
        # releasing that weekend carries its date, one already showing says so instead.
        if release >= week.thu:
            dk = {0: "thu", 1: "fri", 2: "sat"}[(release - week.thu).days]
            lead = ar_date(release)
        else:
            dk = "thu"
            lead = "يعرض حاليًا"
        sub = "%s · %s" % (lead, _genres_ar(genres)) if genres else lead
        cands.append(base.make(
            "cinema", base.short_title(title), sub, "سينما", url, dk, SOURCE, page_url, fetched,
            category="cinema", district="", raw_conf=base.TIER_PRIMARY,
            extra={"name": title, "release_iso": release.isoformat(),
                   "new_this_week": release >= new_from,
                   "genres": [base.text(g) for g in genres][:3],
                   "age": int(age.group(1)) if age else None}))
    # new-this-week first, then newest release first
    cands.sort(key=lambda c: (0 if c["new_this_week"] else 1, -int(c["release_iso"].replace("-", ""))))
    return cands, dropped


def fetch(week, http, now):
    status, final, ctype, html = http.get_text(NOW_URL)
    if status != 200 or not html:
        return [], [{"ttl": SOURCE, "reason": "الصفحة ما ردت (%s)" % status}], ""
    cands, dropped = parse(html, week, now, final or NOW_URL)
    return cands, dropped, html
