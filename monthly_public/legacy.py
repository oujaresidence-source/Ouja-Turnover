"""Safe, dependency-free browse page for an explicit public UI rollback."""

from __future__ import annotations

import html
import re
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlsplit


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _text(value: Any) -> str:
    return html.escape(str(value or "").strip(), quote=True)


def _image(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    return _text(value) if parsed.scheme in ("http", "https") and parsed.netloc else ""


def _path(listing: Mapping[str, Any]) -> str:
    slug = str(listing.get("slug") or "").strip()
    if _SAFE_ID.fullmatch(slug):
        return "/monthly/%s" % slug
    listing_id = str(listing.get("id") or "").strip()
    return "/monthly/id/%s" % listing_id if _SAFE_ID.fullmatch(listing_id) else "/monthly/search"


def _facts(listing: Mapping[str, Any]) -> str:
    values = []
    bedrooms = listing.get("bedrooms", listing.get("beds"))
    capacity = listing.get("capacity")
    if isinstance(bedrooms, int) and not isinstance(bedrooms, bool) and bedrooms >= 0:
        values.append("استديو" if bedrooms == 0 else "%s غرف نوم" % bedrooms)
    if isinstance(capacity, int) and not isinstance(capacity, bool) and capacity > 0:
        values.append("يسع %s" % capacity)
    return " · ".join(values)


def _card(listing: Mapping[str, Any]) -> str:
    title = _text(listing.get("name_ar") or listing.get("name_en") or "بيت عوجا")
    area = _text(listing.get("area") or listing.get("neighborhood_ar") or "الرياض")
    cover = _image(listing.get("cover") or ((listing.get("images") or [""])[0]))
    photo = (
        '<img src="%s" alt="صورة %s" loading="lazy" decoding="async">' % (cover, title)
        if cover
        else ""
    )
    facts = _facts(listing)
    return (
        '<article class="home-card"><a href="%s">%s<div class="home-copy">'
        '<p>%s</p><h2>%s</h2>%s</div></a></article>'
        % (
            _path(listing),
            photo,
            area,
            title,
            '<p class="facts">%s</p>' % _text(facts) if facts else "",
        )
    )


def render_legacy_monthly_page(
    route: str,
    *,
    listing: Optional[Mapping[str, Any]] = None,
    catalog: Iterable[Mapping[str, Any]] = (),
) -> str:
    """Render a browse-only fallback that cannot create a commercial claim."""

    homes = tuple(item for item in catalog if isinstance(item, Mapping))
    title = "عوجا بالشهر"
    if route == "listing" and isinstance(listing, Mapping):
        title = _text(listing.get("name_ar") or listing.get("name_en") or title)
        images = []
        for raw in listing.get("images") or ():
            url = _image(raw)
            if url:
                images.append('<img src="%s" alt="صورة %s" loading="lazy" decoding="async">' % (url, title))
            if len(images) == 4:
                break
        main = (
            '<main id="main"><a class="back" href="/monthly/search">رجوع لكل البيوت</a>'
            '<div class="gallery">%s</div><h1>%s</h1><p>%s</p>'
            '<section class="notice" aria-labelledby="fallback-status"><h2 id="fallback-status">التصفح متاح بأمان</h2>'
            '<p>التواصل والتسعير غير متاحين في النسخة الاحتياطية. ارجع لاحقًا لإكمال طلبك من المسار الرسمي.</p></section></main>'
            % ("".join(images), title, _text(_facts(listing)))
        )
    else:
        cards = "".join(_card(item) for item in homes)
        main = (
            '<main id="main"><section class="intro"><p>OUJA MONTHLY · RIYADH</p>'
            '<h1>بيتك في الرياض، جاهز من أول يوم.</h1>'
            '<a class="primary" href="/monthly/search">تصفح كل البيوت (%s)</a></section>'
            '<section class="catalog" aria-labelledby="catalog-title"><h2 id="catalog-title">البيوت الشهرية</h2>'
            '<div class="grid">%s</div></section></main>' % (len(homes), cards)
        )
    return """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s · عوجا بالشهر</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#fbf8f2;color:#17201d;font-family:"IBM Plex Sans Arabic",Tahoma,Arial,sans-serif;line-height:1.65}a{color:inherit}.skip{position:absolute;inset:8px;transform:translateY(-160%%)}.skip:focus{transform:none}.header{display:flex;justify-content:space-between;align-items:center;min-height:68px;padding:12px max(20px,calc((100vw - 1120px)/2));border-bottom:1px solid #d8cdbb}.header a{min-height:44px;display:inline-flex;align-items:center;font-weight:700;text-decoration:none}.intro,.catalog,#main{width:min(100%% - 40px,1120px);margin:auto}.intro{padding:64px 0 40px}.intro h1{max-width:14ch;font-size:clamp(2.3rem,8vw,5rem);line-height:1.1}.primary{display:inline-flex;align-items:center;min-height:44px;padding:11px 18px;background:#d4b27c;color:#102d26;border-radius:8px;font-weight:700;text-decoration:none}.catalog{padding:24px 0 64px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px}.home-card{overflow:hidden;background:#fff;border-radius:12px}.home-card a{text-decoration:none}.home-card img{display:block;width:100%%;aspect-ratio:4/3;object-fit:cover}.home-copy{padding:16px}.home-copy p{margin:0;color:#4b5752}.home-copy h2{margin:4px 0;font-size:1.2rem}.gallery{display:grid;gap:8px;padding-top:28px}.gallery img{display:block;width:100%%;height:auto;border-radius:8px}.back{display:inline-flex;min-height:44px;align-items:center;margin-top:20px}.notice{max-width:680px;margin:36px 0;padding:24px;background:#f2ece2;border-radius:12px}@media(min-width:700px){.gallery{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body><a class="skip" href="#main">انتقل للمحتوى</a><header class="header"><a href="/monthly">عوجا بالشهر</a><a href="/monthly/search">كل البيوت</a></header>%s</body></html>""" % (title, main)


__all__ = ["render_legacy_monthly_page"]
