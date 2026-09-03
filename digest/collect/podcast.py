# -*- coding: utf-8 -*-
"""«بودكاست الأسبوع» — Apple's official Saudi top-podcasts feed (marketing tools RSS,
JSON): show name, host, Apple Podcasts page, artwork. One show per issue, never the same
show twice in the last 6 issues (rank.py's novelty term does that with recent urls)."""

import json

from . import base
from ..dates import AR_DAY, ar_date

SOURCE = "Apple Podcasts"
FEED_URL = "https://rss.marketingtools.apple.com/api/v2/sa/podcasts/top/10/podcasts.json"
ARTWORK_SIZE = "600x600"


def artwork_url(u):
    """Apple serves artwork at any size by rewriting the last path segment."""
    if not u:
        return ""
    head, _, tail = u.rpartition("/")
    if "x" in tail and "bb" in tail:
        ext = tail.rsplit(".", 1)[-1] if "." in tail else "jpg"
        return "%s/%sbb.%s" % (head, ARTWORK_SIZE, ext)
    return u


def parse(txt, week, now, page_url=FEED_URL):
    """-> (candidates, dropped) from the feed JSON (pure)."""
    cands, dropped = [], []
    try:
        d = json.loads(txt or "")
        results = (d.get("feed") or {}).get("results") or []
    except Exception:
        return [], [{"ttl": SOURCE, "reason": "الخلاصة ما انقرأت"}]
    fetched = base.now_iso(now)
    for i, r in enumerate(results):
        name, artist, url = base.text(r.get("name", "")), base.text(r.get("artistName", "")), (r.get("url") or "").strip()
        if not (name and url.startswith("https://podcasts.apple.com/")):
            continue
        sub = " · ".join(("%s %s" % (AR_DAY["fri"], ar_date(week.fri)), base.short_place(artist, 3) or "بودكاست", "مجاني"))
        cands.append(base.make(
            "podcast", base.short_title(name), sub, "بودكاست", url, "fri", SOURCE, page_url, fetched,
            category="podcast", district="", raw_conf=base.TIER_PRIMARY,
            extra={"name": name, "artist": artist, "chart_rank": i + 1,
                   "art_hint": {"artwork": artwork_url(r.get("artworkUrl100") or "")},
                   "agreement": base.AGREE_YES}))
    return cands, dropped


def fetch(week, http, now):
    status, final, ctype, txt = http.get_text(FEED_URL)
    if status != 200 or not txt:
        return [], [{"ttl": SOURCE, "reason": "الخلاصة ما ردت (%s)" % status}], ""
    cands, dropped = parse(txt, week, now, final or FEED_URL)
    return cands, dropped, txt
