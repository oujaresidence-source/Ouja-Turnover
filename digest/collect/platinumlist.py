# -*- coding: utf-8 -*-
"""Events — riyadh.platinumlist.net/ar/calendar/this-weekend.

The page is grouped by day: a `section__title` carrying data-events-by-day="/ar/calendar/
YYYY-MM-DD", then `event-grid-item` cards (title link → /ar/event-tickets/<id>/<slug>,
a price span, a date span). Venue and category are NOT on the card, so `enrich()` opens
the event page once per shortlisted candidate (og:description names the venue, og:image
is the same-origin artwork). Verified 2026-09-02; fixture tests/fixtures/digest/
platinumlist-this-weekend-20260902.html. Parsing is pure; only fetch/enrich touch http."""

import re
from datetime import date

from . import base
from .. import places
from ..dates import AR_DAY, ar_digits, day_key

SOURCE = "Platinumlist"
CALENDAR_URL = "https://riyadh.platinumlist.net/ar/calendar/this-weekend"
ORIGIN = "https://riyadh.platinumlist.net"

_DAY_RX = re.compile(r'data-events-by-day="/ar/calendar/(\d{4}-\d{2}-\d{2})"')
_CARD_RX = re.compile(r'<div class="event-grid-item">')
_TITLE_RX = re.compile(r'<a class="event-grid-item__title"\s+href="([^"]+)"\s*>(.*?)</a>', re.S)
_PRICE_RX = re.compile(r'<span class="price[^"]*">(.*?)</span>', re.S)
_DATE_RX = re.compile(r'<span class="date[^"]*">(.*?)</span>', re.S)
_SOLD_OUT = ("بيعت جميع التذاكر", "sold out", "نفدت")
_OG_IMG_RX = re.compile(r'property="og:image"\s+content="([^"]+)"')
_OG_DESC_RX = re.compile(r'property="og:description"\s+content="([^"]*)"')
_VENUE_IN_DESC = re.compile(r"(?:.*\s)?في\s+([^،.]{3,60}?)\s+في\s+الرياض")
_VENUE_BLOCK = re.compile(r'buy-block__venue"[^>]*>(.{0,900}?)</div>\s*</div>', re.S)


def _price_ar(txt):
    t = base.text(txt)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:SAR|ر\.س|ريال)", t)
    if m:
        n = m.group(1).split(".")[0]
        return "من %s ريال" % ar_digits(n)
    if "مجان" in t or "free" in t.lower():
        return "الدخول مجاني"
    return ""


def parse(html, week, now, page_url=CALENDAR_URL):
    """-> (candidates, dropped). Only cards under a day heading inside the week."""
    cands, dropped = [], []
    marks = [(m.start(), m.group(1)) for m in _DAY_RX.finditer(html)]
    if not marks:
        return cands, dropped
    fetched = base.now_iso(now)
    seen = set()
    for i, (pos, iso) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(html)
        try:
            d = date.fromisoformat(iso)
        except ValueError:
            continue
        dk = day_key(week, d)
        if not dk:
            continue
        block = html[pos:end]
        starts = [m.start() for m in _CARD_RX.finditer(block)]
        for j, s in enumerate(starts):
            card = block[s:starts[j + 1] if j + 1 < len(starts) else len(block)]
            t = _TITLE_RX.search(card)
            if not t:
                continue
            url = t.group(1).strip()
            name = base.text(t.group(2))
            if not url.startswith(ORIGIN) or not name or url in seen:
                continue
            seen.add(url)
            price = _PRICE_RX.search(card)
            price_txt = base.text(price.group(1)) if price else ""
            if any(k in price_txt.lower() for k in _SOLD_OUT):
                dropped.append({"ttl": base.short_title(name), "reason": "التذاكر نفدت", "url": url})
                continue
            sub_bits = [AR_DAY[dk]]
            p = _price_ar(price_txt)
            if p:
                sub_bits.append(p)
            cands.append(base.make(
                "events", base.short_title(name), " · ".join(sub_bits), places.DEFAULT_DISTRICT,
                url, dk, SOURCE, page_url, fetched,
                category=base.category_of(name), district="",
                raw_conf=base.TIER_PRIMARY,
                extra={"name": name, "price": price_txt, "date_iso": iso}))
    return cands, dropped


def parse_event_page(html, page_url):
    """-> {"venue","og","description"} from one event page (pure)."""
    og = _OG_IMG_RX.search(html)
    desc = _OG_DESC_RX.search(html)
    desc_txt = base.text(desc.group(1)) if desc else ""
    venue = ""
    m = _VENUE_IN_DESC.search(desc_txt)
    if m:
        venue = m.group(1).strip(" .،")
    if not venue:
        b = _VENUE_BLOCK.search(html)
        if b:
            venue = base.text(b.group(1))[:80]
    og_url = og.group(1).strip() if og else ""
    return {"venue": venue, "og": og_url, "description": desc_txt}


def enrich(cand, http):
    """Open the event page for venue → district/coords and the og:image hint."""
    try:
        status, final, ctype, html = http.get_text(cand["url"])
    except Exception:
        return cand
    if status != 200 or not html:
        return cand
    info = parse_event_page(html, final)
    venue = info.get("venue") or ""
    if venue:
        cand["venue"] = venue
        cand["tags"]["district"] = places.district_for(venue, info.get("description", ""))
        cand["chip"] = cand["tags"]["district"]
        ll = places.coords_for(venue, info.get("description", ""))
        if ll:
            cand["latlng"] = ll
    if info.get("description"):
        cand["tags"]["category"] = base.category_of(cand.get("name", ""), info["description"])
    if info.get("og"):
        cand["art_hint"] = {"og": info["og"]}
    return cand


def fetch(week, http, now, enrich_top=8):
    """Live: calendar page → parse → enrich the first `enrich_top` candidates."""
    status, final, ctype, html = http.get_text(CALENDAR_URL)
    if status != 200 or not html:
        return [], [{"ttl": SOURCE, "reason": "الصفحة ما ردت (%s)" % status}], ""
    cands, dropped = parse(html, week, now, final or CALENDAR_URL)
    for c in cands[:enrich_top]:
        enrich(c, http)
    return cands, dropped, html
