# -*- coding: utf-8 -*-
"""Place photos from Wikimedia Commons — rights-clean, credited (2026-09-03: Bujairi's
official site blocks bots and its ticket page has only a logo; the owner wants a
picture on every place). Only free licences are accepted (CC0, public domain, CC BY,
CC BY-SA) and the credit («الصورة: <artist> · <licence> · Wikimedia Commons») is
printed on the page. The query per place lives in riyadh.json (`commons_query`)."""

import html as _html
import json
import re

API = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
       "&gsrsearch=%s&gsrnamespace=6&gsrlimit=8&prop=imageinfo&iiprop=url|extmetadata|size|mime&iiurlwidth=1200")
FREE = ("cc0", "public domain", "cc by", "cc-by", "cc by-sa", "cc-by-sa")
NOT_FREE = ("nc", "nd", "gfdl-only", "fair use")
MIN_WIDTH = 800
_TAG = re.compile(r"<[^>]+>")


def _free(licence):
    l = (licence or "").lower()
    if not l or any(b in l for b in NOT_FREE):
        return False
    return any(f in l for f in FREE)


def parse(txt, query=""):
    """-> best candidate {url, w, h, licence, artist, credit, page} or None (pure)."""
    try:
        d = json.loads(txt or "")
    except Exception:
        return None
    pages = list(((d.get("query") or {}).get("pages") or {}).values())
    best = None
    for pg in pages:
        ii = (pg.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        licence = (md.get("LicenseShortName") or {}).get("value", "")
        mime = ii.get("mime") or ""
        w, h = int(ii.get("width") or 0), int(ii.get("height") or 0)
        if not (_free(licence) and mime.startswith("image/") and "svg" not in mime and w >= MIN_WIDTH):
            continue
        if max(w, h) / float(max(1, min(w, h))) > 3.0:
            continue
        artist = _html.unescape(_TAG.sub("", (md.get("Artist") or {}).get("value", ""))).strip()[:60]
        thumb = (ii.get("thumburl") or ii.get("url") or "").split("?")[0]
        if not (thumb.lower().startswith("https://") and "wikimedia.org" in thumb.lower()):
            continue
        cand = {"url": thumb, "w": min(w, 1200), "h": int(h * min(w, 1200) / float(w)) if w else h, "licence": licence,
                "artist": artist, "page": ii.get("descriptionurl") or "",
                "credit": "الصورة: %s · %s · Wikimedia Commons" % (artist or "Wikimedia", licence)}
        score = (1 if "cc0" in licence.lower() or "public" in licence.lower() else 0, w)
        if best is None or score > best[0]:
            best = (score, cand)
    return best[1] if best else None


def find(query, http):
    """Live: search Commons for `query`. -> candidate dict or None."""
    if not query:
        return None
    try:
        status, final, ctype, txt = http.get_text(API % query.replace(" ", "%20"))
    except Exception:
        return None
    if status != 200:
        return None
    return parse(txt, query)
