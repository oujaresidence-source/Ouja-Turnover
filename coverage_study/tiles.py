# -*- coding: utf-8 -*-
"""A real street map of Riyadh with NO API key — OpenStreetMap raster tiles, stitched
into one image on our server.

The owner does not want to register a Google Maps key (2026-08-02), so this replaces
Google Static Maps entirely. Same Web Mercator projection the dashboard uses to place
its dots, so the circles land on the right buildings either way.

We fetch the tiles server-side rather than from the browser: it keeps the page making
no third-party requests, lets us cache hard (street layouts do not move), and keeps us
inside the OSM tile policy — a descriptive User-Agent and a small, cached tile count.
Attribution is rendered by the page: © OpenStreetMap contributors.
"""

import math
import threading

TILE = 256
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
# OSM's policy requires a real, identifying User-Agent — a default library string gets
# blocked, and rightly so.
UA = "OujaResidence-CoverageMap/1.0 (+https://oujares.com; ops@oujares.com)"
ATTRIBUTION = "© OpenStreetMap contributors"

MAX_TILES = 40          # one view; a runaway request must never hammer the tile servers
_tile_cache = {}        # (z,x,y) -> png bytes
_TILE_CACHE_MAX = 400
_lock = threading.Lock()


def world_px(lat, lng, z):
    """(lat, lng) -> absolute pixel on the Web Mercator world at zoom z."""
    scale = TILE * (2 ** z)
    s = min(0.9999, max(-0.9999, math.sin(math.radians(lat))))
    x = (lng + 180.0) / 360.0 * scale
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * scale
    return x, y


def _fetch_tile(z, x, y, session):
    key = (z, x, y)
    hit = _tile_cache.get(key)
    if hit is not None:
        return hit
    r = session.get(TILE_URL.format(z=z, x=x, y=y), timeout=15,
                    headers={"User-Agent": UA, "Accept": "image/png"})
    r.raise_for_status()
    data = r.content
    with _lock:
        if len(_tile_cache) >= _TILE_CACHE_MAX:
            _tile_cache.clear()
        _tile_cache[key] = data
    return data


def render(lat, lng, z, w, h):
    """PNG bytes of a w×h map centred on (lat, lng) at zoom z.

    Raises on a hard failure (no Pillow, no network) so the caller can fall back to a
    plain background — the dots stay correct either way, they just lose their streets.
    """
    from PIL import Image          # Pillow is already a dependency (requirements.txt)
    import io
    import requests

    z = max(1, min(19, int(z)))
    cx, cy = world_px(lat, lng, z)
    left, top = cx - w / 2.0, cy - h / 2.0
    n = 2 ** z

    x0, x1 = int(math.floor(left / TILE)), int(math.floor((left + w) / TILE))
    y0, y1 = int(math.floor(top / TILE)), int(math.floor((top + h) / TILE))
    if (x1 - x0 + 1) * (y1 - y0 + 1) > MAX_TILES:
        raise ValueError("requested view needs too many tiles")

    canvas = Image.new("RGB", (int(w), int(h)), (233, 231, 226))   # OSM land colour
    session = requests.Session()
    got = 0
    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            if ty < 0 or ty >= n:
                continue                       # above the pole / below it: leave blank
            wrapped = tx % n                   # the world repeats east-west
            try:
                data = _fetch_tile(z, wrapped, ty, session)
                img = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception:
                continue                       # one missing tile must not lose the map
            canvas.paste(img, (int(round(tx * TILE - left)), int(round(ty * TILE - top))))
            got += 1
    if not got:
        raise RuntimeError("no tiles could be fetched")

    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
