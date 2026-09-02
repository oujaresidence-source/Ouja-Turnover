# -*- coding: utf-8 -*-
"""Film ratings — IMDb and Rotten Tomatoes, CITED not scraped.

imdb.com refuses non-browser fetches and Rotten Tomatoes' terms forbid scraping its
pages, so the digest does what a newspaper does: it asks the search tool
(HOST.claude_search, restricted to the two domains) and keeps a number ONLY when the
tool's opened-pages list contains that title's page. The source url is stored and
printed in the page foot. No opened page → no rating; the card still ships."""

import json
import re

DOMAINS = ("imdb.com", "rottentomatoes.com")
SYSTEM = (
    "You look up film ratings. Return JSON only: "
    "{\"imdb\": number or null, \"imdb_url\": \"https://www.imdb.com/title/tt.../\" or null, "
    "\"rt\": integer percent or null, \"rt_url\": \"https://www.rottentomatoes.com/m/...\" or null}. "
    "Use only pages you actually opened. Never guess a number."
)
_IMDB_ID = re.compile(r"imdb\.com/title/(tt\d+)")
_RT_PAGE = re.compile(r"rottentomatoes\.com/(m|tv)/[a-z0-9_\-]+")


def _norm(u):
    return (u or "").strip().split("#")[0].split("?")[0].rstrip("/")


def fetch(title, imdb_id, search, model=None, max_uses=3):
    """-> {"imdb": float|None, "rt": int|None, "sources": [urls]}. Offline-safe: any
    failure returns the empty shape."""
    empty = {"imdb": None, "rt": None, "sources": []}
    if not search or not title:
        return empty
    user = "Film: %s%s. Riyadh cinemas, this week." % (title, (" (IMDb %s)" % imdb_id) if imdb_id else "")
    try:
        got = search(SYSTEM, user, max_tokens=600, model=model, max_uses=max_uses, allowed_domains=list(DOMAINS))
    except Exception:
        return empty
    data, urls = (got if isinstance(got, tuple) and len(got) == 2 else (got, []))
    if not isinstance(data, dict):
        return empty
    opened = [u for u in (urls or []) if isinstance(u, str)]
    out = dict(empty)
    # IMDb: the opened page must be THIS title (by id when we have it)
    imdb_pages = [u for u in opened if "imdb.com/title/" in u]
    if imdb_id:
        imdb_pages = [u for u in imdb_pages if (_IMDB_ID.search(u) or [None, ""])[1] == imdb_id or imdb_id in u]
    try:
        v = float(data.get("imdb")) if data.get("imdb") is not None else None
    except (TypeError, ValueError):
        v = None
    if v is not None and 0 < v <= 10 and imdb_pages:
        out["imdb"] = round(v, 1)
        out["sources"].append(imdb_pages[0])
    rt_pages = [u for u in opened if _RT_PAGE.search(u)]
    try:
        r = int(data.get("rt")) if data.get("rt") is not None else None
    except (TypeError, ValueError):
        r = None
    if r is not None and 0 <= r <= 100 and rt_pages:
        out["rt"] = r
        out["sources"].append(rt_pages[0])
    return out


def as_json(r):
    return json.dumps(r, ensure_ascii=False)
