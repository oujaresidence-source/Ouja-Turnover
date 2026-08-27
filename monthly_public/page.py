"""Accessible, Arabic-first shell for the public monthly-stay application."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

from .fonts import FONT_CSS_PATH, PRELOAD_FONT_PATH


ASSET_VERSION = "v20260827e"
CSS_PATH = "/monthly/static/monthly.%s.css" % ASSET_VERSION
JS_PATH = "/monthly/static/monthly.%s.js" % ASSET_VERSION

PAGE_ROUTES = {
    "/monthly": "home",
    "/monthly/": "home",
    "/monthly/search": "browse",
    "/monthly/match": "match",
    "/monthly/id/{lid}": "listing",
    "/monthly/showcase/{showcase_slug}": "showcase",
    "/monthly/{slug}": "listing",
}
ASSET_ROUTES = {CSS_PATH: "css", JS_PATH: "js"}

_ROUTES = frozenset({"home", "match", "browse", "listing", "showcase"})
_SAFE_ROUTE_VALUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_SAFE_SHOWCASE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,78}[a-z0-9]$|^[a-z0-9]$")


def _safe_optional(value: Any, field: str) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not _SAFE_ROUTE_VALUE.fullmatch(text):
        raise ValueError("invalid %s" % field)
    return text


def page_state(
    route: str,
    *,
    slug: Any = None,
    listing_id: Any = None,
    showcase_slug: Any = None,
    preview: bool = False,
    staff_review_available: bool = False,
) -> Dict[str, Any]:
    """Return the only server-authored state embedded in the public shell."""

    if route not in _ROUTES:
        raise ValueError("invalid monthly page route")
    safe_slug = _safe_optional(slug, "slug")
    safe_listing_id = _safe_optional(listing_id, "listing_id")
    safe_showcase_slug = _safe_optional(showcase_slug, "showcase_slug")
    if safe_showcase_slug and not _SAFE_SHOWCASE_SLUG.fullmatch(safe_showcase_slug):
        raise ValueError("invalid showcase_slug")
    if route != "listing" and (safe_slug or safe_listing_id):
        raise ValueError("listing state is only valid on a listing route")
    if route != "showcase" and safe_showcase_slug:
        raise ValueError("showcase state is only valid on a showcase route")
    if route == "showcase" and not safe_showcase_slug:
        raise ValueError("showcase route requires a slug")
    if safe_slug and safe_listing_id:
        raise ValueError("choose one listing route identifier")
    return {
        "route": route,
        "slug": safe_slug,
        "listing_id": safe_listing_id,
        "showcase_slug": safe_showcase_slug,
        "default_lang": "ar",
        "preview": bool(preview),
        "staff_review_available": bool(staff_review_available),
    }


def _json_script(value: Dict[str, Any]) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_monthly_page(
    route: str,
    *,
    slug: Any = None,
    listing_id: Any = None,
    showcase_slug: Any = None,
    preview: bool = False,
    staff_review_available: bool = False,
) -> str:
    """Render one CSP-friendly shell; listing content is loaded from local APIs."""

    state = _json_script(
        page_state(
            route,
            slug=slug,
            listing_id=listing_id,
            showcase_slug=showcase_slug,
            preview=preview,
            staff_review_available=staff_review_available,
        )
    )
    robots = (
        '  <meta name="robots" content="noindex,nofollow,noarchive">\n'
        if preview
        else ""
    )
    body_class = ' class="preview-mode"' if preview else ""
    preview_banner = (
        '''  <aside class="preview-banner" role="note" data-preview-en="Internal preview">
    <strong data-copy="previewLabel">تجربة داخلية</strong>
    <span data-copy="previewBanner">تعرض كل الشقق للتجربة، بما فيها البيانات الناقصة. لا تنشر ولا تحذف أي معلومة.</span>
  </aside>
'''
        if preview
        else ""
    )
    staff_review_entry = (
        '''  <aside id="staff-review-entry" class="staff-review-entry" role="note">
    <span data-copy="staffReviewHint">أنت تشاهد نسخة العملاء المعتمدة.</span>
    <a class="button button-primary" href="/monthly/ops/preview" data-copy="staffReviewAction">وضع المراجعة: عرض كل الشقق</a>
  </aside>
'''
        if staff_review_available and not preview
        else ""
    )
    return """<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#173d32">
  <meta name="description" content="شقق عوجا المفروشة للإقامة الشهرية في الرياض، مع سعر رسمي واضح ودعم طوال الإقامة.">
%s  <title>عوجا بالشهر · الرياض</title>
  <link rel="preload" href="%s" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="%s">
  <link rel="stylesheet" href="%s">
  <script src="%s" defer></script>
</head>
<body%s>
  <a class="skip-link" href="#monthly-main">انتقل إلى المحتوى</a>
  <svg class="icon-library" aria-hidden="true" focusable="false">
    <symbol id="icon-arrow" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></symbol>
    <symbol id="icon-back" viewBox="0 0 24 24"><path d="M19 12H5m6-6-6 6 6 6"/></symbol>
    <symbol id="icon-home" viewBox="0 0 24 24"><path d="m4 10 8-7 8 7v10h-6v-6h-4v6H4Z"/></symbol>
    <symbol id="icon-check" viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></symbol>
    <symbol id="icon-pin" viewBox="0 0 24 24"><path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/></symbol>
    <symbol id="icon-users" viewBox="0 0 24 24"><path d="M16 20v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2M9.5 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM17 11a4 4 0 0 1 4 4v2"/></symbol>
    <symbol id="icon-calendar" viewBox="0 0 24 24"><path d="M6 2v4m12-4v4M3 9h18M5 4h14a2 2 0 0 1 2 2v15H3V6a2 2 0 0 1 2-2Z"/></symbol>
    <symbol id="icon-bed" viewBox="0 0 24 24"><path d="M3 19v-8m18 8v-6a2 2 0 0 0-2-2H9a3 3 0 0 0-3 3v5m-3-3h18M8 8a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z"/></symbol>
    <symbol id="icon-message" viewBox="0 0 24 24"><path d="M21 12a8 8 0 0 1-9 8 9 9 0 0 1-4-.9L3 21l1.8-4A9 9 0 1 1 21 12Z"/></symbol>
    <symbol id="icon-alert" viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Zm0 6v5m0 3v.1"/></symbol>
  </svg>
%s%s  <div class="site-shell">
    <header class="site-header">
      <a class="brand" href="/monthly" aria-label="عوجا بالشهر، الرئيسية">
        <span class="brand-mark" aria-hidden="true">عوجا</span>
        <span class="brand-name" data-copy="brand">عوجا بالشهر</span>
      </a>
      <nav class="site-nav" aria-label="التنقل الرئيسي" data-copy-aria="primaryNav">
        <a href="/monthly/search" data-copy="browseNav">تصفح البيوت</a>
        <button class="language-switch" id="language-switch" type="button" aria-label="Switch to English">English</button>
      </nav>
    </header>
    <main id="monthly-main" tabindex="-1">
      <section class="boot-state" aria-labelledby="boot-title">
        <p class="eyebrow">OUJA MONTHLY · RIYADH</p>
        <h1 id="boot-title">بيتك في الرياض، جاهز من أول يوم.</h1>
        <div class="loading-lines" aria-hidden="true"><span></span><span></span><span></span></div>
        <p>نجهز لك البيوت الشهرية المتاحة.</p>
      </section>
      <noscript><p class="noscript-message">يلزم تفعيل JavaScript لعرض البيوت والتحقق من الأسعار والتوفر.</p></noscript>
    </main>
    <footer class="site-footer">
      <p data-copy="footer">عوجا ريزدنس · إقامة شهرية مُدارة في الرياض</p>
    </footer>
  </div>
  <div id="monthly-status" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></div>
  <div id="monthly-errors" class="sr-only" role="alert" aria-live="assertive" aria-atomic="true"></div>
  <script id="monthly-page-state" type="application/json">%s</script>
</body>
</html>""" % (
        robots,
        PRELOAD_FONT_PATH,
        FONT_CSS_PATH,
        CSS_PATH,
        JS_PATH,
        body_class,
        preview_banner,
        staff_review_entry,
        state,
    )


__all__ = [
    "ASSET_ROUTES",
    "ASSET_VERSION",
    "CSS_PATH",
    "JS_PATH",
    "PAGE_ROUTES",
    "page_state",
    "render_monthly_page",
]
