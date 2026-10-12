# -*- coding: utf-8 -*-
"""
site_home.routes — the oujares.com company pages.

Public, no login, no token. Every handler is pure string rendering from SITE_IDENTITY
(no Hostaway, no database, no thread — CLAUDE.md trap 6), so none of them belongs in
tests/test_web_lane.py's GUEST_HANDLERS (that list is for handlers that DO need the web
pool); tests/test_home_site.py instead fails if this package ever reaches for one.
"""
from pathlib import Path

from . import render
from .host import HOST

_CP_ASSETS = Path(__file__).resolve().parent.parent / "cp" / "assets"


def _asset(name):
    try:
        return (_CP_ASSETS / name).read_bytes()
    except OSError:
        return b""


# Read once at import: the official Ouja mark and the 1200x630 share card (both already
# shipped by the company profile). Served from memory — no disk read per request.
_ASSETS = {"logo.png": _asset("logo-mark.png"), "share.png": _asset("share.png")}

_HTML_CACHE = "public, max-age=300"


def _html(page, lang):
    async def handler(request):
        web = HOST.require("web")
        return web.Response(text=render.render(page, lang), content_type="text/html",
                            headers={"Cache-Control": _HTML_CACHE})
    handler.__name__ = "site_%s_%s" % (page, lang)
    return handler


def _redirect(to):
    async def handler(request):
        raise HOST.require("web").HTTPMovedPermanently(to)
    return handler


async def handle_asset(request):
    web = HOST.require("web")
    data = _ASSETS.get(request.match_info.get("name", ""))
    if not data:
        raise web.HTTPNotFound()
    return web.Response(body=data, content_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


def site_paths():
    """[(ar_path, en_path)] — robots.txt and sitemap.xml read this, so a new page
    added to render.PATHS is advertised without touching bot.py again."""
    return list(render.PATHS.values())


def register(app):
    g = app.router.add_get
    for page, (ar, en) in render.PATHS.items():
        g(ar, _html(page, "ar"))
        g(en, _html(page, "en"))
        g(en + "/", _redirect(en))
        if ar != "/":
            g(ar + "/", _redirect(ar))
    g("/site/{name:(?:logo|share)[.]png}", handle_asset)
