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
from ..dates import AR_DAY, AR_MONTHS, ar_date

SOURCE = "elcinema"
NOW_URL = "https://elcinema.com/now/sa/"
# The card link must send a guest to a SAUDI cinema, not the Egyptian info site (owner 2026-09-03).
# muvi's Arabic movie finder is the one Saudi chain that answers a plain request (VOX,
# AMC, Empire, Reel all refuse); it lists films and showtimes by date.
TICKETS_URL = "https://www.muvicinemas.com/ar/movie-finder"
TICKETS_NAME = "muvi"
ORIGIN = "https://elcinema.com"
NEW_WINDOW_DAYS = 6

_ROW_RX = re.compile(r'<div class="row" id="w(\d+)">')
_TITLE_RX = re.compile(r'<h3><a href="/work/(\d+)/">(.*?)</a></h3>', re.S)
_RELEASE_RX = re.compile(r'تاريخ العرض:</strong>\s*<a[^>]*>\s*(\d{1,2})\s+(\S+)\s*</a>\s*<a[^>]*>\s*(\d{4})\s*</a>', re.S)
_GENRE_RX = re.compile(r'/index/work/genre/\d+"[^>]*>([^<]+)</a>')
_AGE_RX = re.compile(r'<li>\+(\d{1,2})</li>')
_MONTH_INDEX = {v: k for k, v in AR_MONTHS.items()}
_OG_IMG_RX = re.compile(r'property="og:image"\s+content="([^"]+)"')
_IMDB_RX = re.compile(r"imdb\.com/title/(tt\d+)")
_POSTER_SIZE_RX = re.compile(r"/uploads/_\d*x\d*_")
POSTER_WIDTH = "_640x_"      # elcinema serves _320x_ (og), _640x_ (640×960) and the original
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
        # facts line (owner rule 2026-09-03): day+date · place · price — place is the
        # cinema chain page («السينما»), price «حسب العرض» (elcinema lists no prices).
        sub = " · ".join(x for x in (
            "%s %s" % (AR_DAY[dk], ar_date({"thu": week.thu, "fri": week.fri, "sat": week.sat}[dk])),
            "%s، %s" % (TICKETS_NAME, _genres_ar(genres) or lead), "حسب العرض") if x)
        cands.append(base.make(
            "cinema", base.short_title(title), sub, "سينما", TICKETS_URL, dk, SOURCE, page_url, fetched,
            category="cinema", district="", raw_conf=base.TIER_PRIMARY,
            extra={"name": title, "release_iso": release.isoformat(), "info_url": url,
                   "new_this_week": release >= new_from, "release_label": lead,
                   "genres": [base.text(g) for g in genres][:3],
                   "age": int(age.group(1)) if age else None}))
    # new-this-week first, then newest release first
    cands.sort(key=lambda c: (0 if c["new_this_week"] else 1, -int(c["release_iso"].replace("-", ""))))
    return cands, dropped


def parse_film_page(html):
    """-> {"poster": url|'' (same site, 640 wide), "imdb_id": 'tt…'|''} (pure)."""
    og = _OG_IMG_RX.search(html or "")
    poster = og.group(1).strip() if og else ""
    if poster and _POSTER_SIZE_RX.search(poster):
        poster = _POSTER_SIZE_RX.sub("/uploads/%s" % POSTER_WIDTH, poster, 1)
    m = _IMDB_RX.search(html or "")
    return {"poster": poster, "imdb_id": m.group(1) if m else ""}


def enrich(cand, http):
    """Open the film's own info page: poster (same site as that page) + IMDb id."""
    try:
        status, final, ctype, html = http.get_text(cand.get("info_url") or cand["url"])
    except Exception:
        return cand
    if status != 200 or not html:
        return cand
    info = parse_film_page(html)
    if info["poster"]:
        cand["art_hint"] = {"poster": info["poster"]}
    if info["imdb_id"]:
        cand["imdb_id"] = info["imdb_id"]
    return cand


def fetch(week, http, now, enrich_top=6):
    status, final, ctype, html = http.get_text(NOW_URL)
    if status != 200 or not html:
        return [], [{"ttl": SOURCE, "reason": "الصفحة ما ردت (%s)" % status}], ""
    cands, dropped = parse(html, week, now, final or NOW_URL)
    for c in cands[:enrich_top]:
        enrich(c, http)
    return cands, dropped, html
