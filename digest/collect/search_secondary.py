# -*- coding: utf-8 -*-
"""The fallback rung of the ladder: HOST.claude_search (Anthropic server-side web
search) restricted to an allow-list of domains. The tool returns (data, urls) where
`urls` are the pages it actually opened — an item is kept ONLY if its url is in that
list (the anti-fabrication gate, same as studio.external). Search-only items carry
TIER_SEARCH confidence and can never outrank a primary-source item on their own."""

import json
from datetime import date

from . import base
from .. import places
from ..dates import AR_DAY, day_key

SYSTEM = (
    "أنت باحث فعاليات للرياض. رجّع JSON فقط بالشكل "
    "{\"items\": [{\"ttl\": \"عنوان قصير\", \"sub\": \"سطر واحد\", \"venue\": \"المكان\", "
    "\"date\": \"YYYY-MM-DD\", \"url\": \"https://...\"}]}. "
    "كل عنصر لازم يكون من صفحة فتحتها فعلاً ورابطها بالضبط. لا تخترع فعالية ولا تاريخ ولا رابط. "
    "إذا ما لقيت شي موثوق رجّع {\"items\": []}."
)


def _norm_url(u):
    return (u or "").strip().split("#")[0].rstrip("/")


def run(section, week, search, allowed_domains, now, query, max_uses=4, model=None):
    """-> (candidates, opened_urls). `search` = HOST.claude_search."""
    user = "القسم: %s. الأيام: %s إلى %s. %s" % (section, week.thu.isoformat(), week.sat.isoformat(), query)
    try:
        got = search(SYSTEM, user, max_tokens=2000, model=model, max_uses=max_uses,
                     allowed_domains=list(allowed_domains))
    except Exception:
        return [], []
    if isinstance(got, tuple) and len(got) == 2:
        data, urls = got
    else:
        data, urls = got, []
    urls = [u for u in (urls or []) if isinstance(u, str)]
    opened = {_norm_url(u): u for u in urls}
    out = []
    fetched = base.now_iso(now)
    items = (data or {}).get("items") if isinstance(data, dict) else None
    for it in items or []:
        if not isinstance(it, dict):
            continue
        key = _norm_url(it.get("url"))
        if not key or key not in opened:
            continue                                   # not a page the tool opened → drop
        url = opened[key]
        if not url.lower().startswith("https://"):
            continue
        try:
            d = date.fromisoformat((it.get("date") or "")[:10])
        except ValueError:
            continue
        dk = day_key(week, d)
        if not dk:
            continue
        venue = base.text(it.get("venue") or "")
        district = places.district_for(venue)
        out.append(base.make(
            section, base.short_title(base.text(it.get("ttl") or "")), base.text(it.get("sub") or "") or AR_DAY[dk],
            district, url, dk, "بحث", url, fetched,
            category=base.category_of(it.get("ttl") or "", it.get("sub") or ""),
            district=district, raw_conf=base.TIER_SEARCH,
            extra={"venue": venue, "latlng": places.coords_for(venue), "date_iso": d.isoformat()}))
    return out, urls


def resolve_place_url(place, search, allowed_domains, model=None, max_uses=2):
    """For a worth.json entry without a url: ask the search tool, keep a url only if
    it was actually opened and sits on an allowed domain. -> url or ''."""
    q = place.get("search") or place.get("ttl") or ""
    if not q:
        return ""
    try:
        got = search("رجّع JSON فقط: {\"url\": \"الصفحة الرسمية للمكان\"}. لا تخترع رابط.",
                     "المكان: %s — الرياض" % q, max_tokens=400, model=model, max_uses=max_uses,
                     allowed_domains=list(allowed_domains))
    except Exception:
        return ""
    data, urls = (got if isinstance(got, tuple) and len(got) == 2 else (got, []))
    opened = {_norm_url(u): u for u in (urls or []) if isinstance(u, str)}
    want = _norm_url((data or {}).get("url") if isinstance(data, dict) else "")
    if want and want in opened:
        return opened[want]
    for u in opened.values():
        if any(dom in u for dom in allowed_domains):
            return u
    return ""


def opened_urls_json(urls):
    return json.dumps(list(urls or []), ensure_ascii=False)
