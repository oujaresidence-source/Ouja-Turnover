# -*- coding: utf-8 -*-
"""digest.links — the link rule (brief §5.2). Every url becomes a printed link, so:
  1. a url may only enter a candidate if it appeared in a fetched page or in the
     search tool's list of opened pages (`provenance_ok`) — never constructed;
  2. HEAD (ranged-GET fallback) must return 200 + text/html;
  3. the FINAL url after redirects is what gets stored and encoded;
  4. verification runs twice — at collection and again right before render.
Network only through the injected `http` (HOST.http / FakeHttp)."""

from urllib.parse import urlsplit

HTML_TYPES = ("text/html", "application/xhtml+xml")
KEEP_SHORT_HOSTS = ("podcasts.apple.com",)     # the redirect only adds a slug; the short form is the clean link


def origin(url):
    p = urlsplit(url or "")
    return (p.scheme.lower(), p.netloc.lower())


def same_origin(a, b):
    return origin(a) == origin(b)


def provenance_ok(url, seen):
    """`seen` is the set of urls that were actually present in fetched pages / search
    results. A url that was assembled by hand is not in it and must not ship."""
    return bool(url) and url in (seen or ())


def check_one(url, http):
    """-> final url (str) when the link is good, else None."""
    if not url or not url.lower().startswith("https://"):
        return None
    try:
        status, final, ctype = http.head(url)
    except Exception:
        return None
    if status != 200:
        return None
    if (ctype or "").lower() not in HTML_TYPES:
        return None
    final = final or url
    if not final.lower().startswith("https://"):
        return None
    if any(h in url.lower() for h in KEEP_SHORT_HOSTS) and same_origin(url, final):
        return url
    return final


def verify(urls, http):
    """-> {original_url: final_url} for every url that passed; failures are absent."""
    out = {}
    for u in urls or []:
        if u in out:
            continue
        final = check_one(u, http)
        if final:
            out[u] = final
    return out
