# -*- coding: utf-8 -*-
"""«بودكاست الأسبوع» — Apple's official Saudi top-podcasts feed (marketing tools RSS,
JSON): show name, host, Apple Podcasts page, artwork. One show per issue, never the same
show twice in the last 6 issues (rank.py's novelty term does that with recent urls)."""

import json

from . import base
from ..dates import AR_DAY, ar_date

SOURCE = "Apple Podcasts"
FEED_URL = "https://rss.marketingtools.apple.com/api/v2/sa/podcasts/top/10/podcasts.json"
LOOKUP_URL = "https://itunes.apple.com/lookup?id=%s&country=sa&entity=podcastEpisode&limit=1"
SHORT_URL = "https://podcasts.apple.com/sa/podcast/id%s"     # stable, short → a clean link
ARTWORK_SIZE = "600x600"
FRESH_DAYS = 7


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
        show_id = (r.get("id") or "").strip() or (url.rsplit("/id", 1)[-1] if "/id" in url else "")
        if show_id.isdigit():
            url = SHORT_URL % show_id
        sub = " · ".join(("%s %s" % (AR_DAY["fri"], ar_date(week.fri)), base.short_place(artist, 3) or "بودكاست", "مجاني"))
        cands.append(base.make(
            "podcast", base.short_title(name), sub, "بودكاست", url, "fri", SOURCE, page_url, fetched,
            category="podcast", district="", raw_conf=base.TIER_PRIMARY,
            extra={"name": name, "artist": artist, "chart_rank": i + 1, "show_id": show_id,
                   "art_hint": {"artwork": artwork_url(r.get("artworkUrl100") or "")},
                   "agreement": base.AGREE_YES}))
    return cands, dropped


def parse_lookup(txt):
    """-> {"episode": title, "released": iso, "url"} for the newest episode, or None."""
    try:
        d = json.loads(txt or "")
    except Exception:
        return None
    eps = [x for x in d.get("results") or [] if x.get("wrapperType") == "podcastEpisode"]
    if not eps:
        return None
    e = max(eps, key=lambda x: x.get("releaseDate") or "")
    return {"episode": base.text(e.get("trackName", "")), "released": (e.get("releaseDate") or "")[:10], "url": e.get("trackViewUrl") or ""}


def enrich(cand, http, now):
    """Newest episode via the iTunes lookup: the card says which episode is new, and
    `fresh` marks shows with an episode from the last FRESH_DAYS days (the owner's
    complaint 2026-09-03: «why old podcasts» — a chart leader can be years old)."""
    sid = cand.get("show_id") or ""
    if not sid.isdigit():
        return cand
    try:
        status, final, ctype, txt = http.get_text(LOOKUP_URL % sid)
    except Exception:
        return cand
    if status != 200:
        return cand
    ep = parse_lookup(txt)
    if not ep:
        return cand
    cand["episode"] = ep["episode"]
    cand["episode_released"] = ep["released"]
    try:
        from datetime import date
        age = (now.date() - date.fromisoformat(ep["released"])).days
        cand["fresh"] = 0 <= age <= FRESH_DAYS
    except Exception:
        cand["fresh"] = False
    if cand["episode"]:
        cand["hook"] = "حلقة جديدة: %s" % base.short_place(cand["episode"], 6)
    return cand


def fetch(week, http, now, enrich_top=10):
    status, final, ctype, txt = http.get_text(FEED_URL)
    if status != 200 or not txt:
        return [], [{"ttl": SOURCE, "reason": "الخلاصة ما ردت (%s)" % status}], ""
    cands, dropped = parse(txt, week, now, final or FEED_URL)
    for c in cands[:enrich_top]:
        enrich(c, http, now)
    # a show with a new episode this week outranks the chart order
    cands.sort(key=lambda c: (0 if c.get("fresh") else 1, c.get("chart_rank", 99)))
    return cands, dropped, txt
