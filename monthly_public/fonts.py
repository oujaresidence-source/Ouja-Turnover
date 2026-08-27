"""Versioned, allow-listed typography assets shared by Ouja Monthly pages."""

from __future__ import annotations

from pathlib import Path


ASSET_VERSION = "v20260827a"
STATIC_DIR = Path(__file__).resolve().parent / "static"
FONT_CSS_PATH = "/monthly/static/monthly_fonts.%s.css" % ASSET_VERSION
FONT_CSS_FILE = STATIC_DIR / ("monthly_fonts.%s.css" % ASSET_VERSION)


def _font_route(stem: str) -> str:
    return "/monthly/static/fonts/%s.%s.woff2" % (stem, ASSET_VERSION)


FONT_ASSETS = {
    _font_route("thmanyah-sans-regular"): "thmanyah-sans-regular",
    _font_route("thmanyah-sans-medium"): "thmanyah-sans-medium",
    _font_route("thmanyah-sans-bold"): "thmanyah-sans-bold",
    _font_route("thmanyah-sans-black"): "thmanyah-sans-black",
    _font_route("thmanyah-serif-display-bold"): "thmanyah-serif-display-bold",
    _font_route("thmanyah-serif-display-black"): "thmanyah-serif-display-black",
}
FONT_ASSET_FILES = {
    route: STATIC_DIR / "fonts" / ("%s.%s.woff2" % (stem, ASSET_VERSION))
    for route, stem in FONT_ASSETS.items()
}
PRELOAD_FONT_PATH = _font_route("thmanyah-sans-regular")


__all__ = [
    "ASSET_VERSION",
    "FONT_ASSETS",
    "FONT_ASSET_FILES",
    "FONT_CSS_FILE",
    "FONT_CSS_PATH",
    "PRELOAD_FONT_PATH",
]
