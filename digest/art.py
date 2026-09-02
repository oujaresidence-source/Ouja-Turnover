# -*- coding: utf-8 -*-
"""digest.art — artwork per item, tried in order (brief §7):
  A owned      Ouja's own photography (digest/data/owned.json → url on our site)
  B og         the official page's og:image, SAME SITE as the item's verified url,
               image/*, long edge >= 800 px, <= 6 MB; sha256 stored
  C generated  deterministic seeded SVG (digest.art_generated) — the ONLY kind for
               cinema and fixtures (no posters, no crests)
  D none       type-only card
Never a stock photo, never a scraped search image, never a real person's photo. Pillow
steps are unit_tiles()'s: thumbnail((760,760), LANCZOS) → JPEG q78 → base64.
"same site" = same registrable domain (cdn.platinumlist.net serves riyadh.platinumlist.net's
own images) — the publisher is the same, which is what makes the claim defensible."""

import base64
import hashlib
import io
import json
import os
from urllib.parse import urlsplit

from . import art_generated

HERE = os.path.dirname(os.path.abspath(__file__))
OWNED_SEED = os.path.join(HERE, "data", "owned.json")
MIN_LONG_EDGE = 800
MIN_POSTER_EDGE = 600        # elcinema serves 640×960
MIN_LOGO_EDGE = 200          # the FA's club PNGs are 400×400
MAX_BYTES = 6000000
MAX_RATIO = 3.0              # wider than 3:1 → type-only rather than a crop (owner rule 2026-09-03)
GENERATED_ONLY = ("fixtures",)


def site_of(url):
    host = (urlsplit(url or "").netloc or "").lower().split(":")[0]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def same_site(a, b):
    return bool(a and b) and site_of(a) == site_of(b)


def load_owned(override_path=None):
    for p in (override_path, OWNED_SEED):
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    d = json.load(fh)
                if isinstance(d.get("images"), dict):
                    return d["images"]
            except Exception:
                continue
    return {}


def thumb_jpeg_b64(raw):
    """unit_tiles() verbatim: Pillow → thumbnail(760) → JPEG q78 → base64 data uri.
    On any Pillow failure the original bytes are embedded unchanged (cp does the same)."""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((760, 760), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=78, optimize=True)
        raw = buf.getvalue()
    except Exception:
        pass
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def image_size(raw):
    try:
        from PIL import Image
        return Image.open(io.BytesIO(raw)).size
    except Exception:
        return None


def image_ok(raw, ctype, min_edge=MIN_LONG_EDGE):
    if not (ctype or "").lower().startswith("image/"):
        return False
    if not raw or len(raw) > MAX_BYTES:
        return False
    size = image_size(raw)
    if not size:
        return False
    w, h = size
    if max(w, h) < min_edge:
        return False
    return max(w, h) / float(max(1, min(w, h))) <= MAX_RATIO


def _fetch_image(url, http, min_edge=MIN_LONG_EDGE, keep_png=False):
    try:
        status, final, ctype, raw = http.get_bytes(url, timeout=10, max_bytes=MAX_BYTES + 1)
    except Exception:
        return None
    if status != 200 or not image_ok(raw, ctype, min_edge):
        return None
    w, h = image_size(raw)
    if keep_png:
        src = "data:%s;base64," % ((ctype or "image/png").split(";")[0]) + base64.b64encode(raw).decode("ascii")
    else:
        src = thumb_jpeg_b64(raw)
    return {"src": src, "sha256": hashlib.sha256(raw).hexdigest(), "origin": final or url, "w": w, "h": h}


def _pack(kind, got):
    return {"kind": kind, "src": got["src"], "sha256": got["sha256"], "origin": got["origin"], "w": got["w"], "h": got["h"]}


def owned_for(item, owned, http):
    key = item.get("slug") or ""
    entry = owned.get(key) if key else None
    if not entry or not entry.get("url"):
        return None
    got = _fetch_image(entry["url"], http)
    return _pack("owned", got) if got else None


def og_for(item, http):
    og = (item.get("art_hint") or {}).get("og") or ""
    if not og or not og.lower().startswith("https://"):
        return None
    if not same_site(og, item.get("url", "")):
        return None
    got = _fetch_image(og, http)
    return _pack("og", got) if got else None


def poster_for(item, http):
    """The film's poster from the film page's own site (elcinema, 640×960)."""
    url = (item.get("art_hint") or {}).get("poster") or ""
    if not url or not url.lower().startswith("https://"):
        return None
    if not same_site(url, item.get("url", "")):
        return None
    got = _fetch_image(url, http, min_edge=MIN_POSTER_EDGE)
    return _pack("poster", got) if got else None


def logos_for(fixture, http):
    """Both club logos from the FA's site (same site as the fixture url). -> {"kind":
    "logos", "home": datauri, "away": datauri, "sha256"} or None when either is missing."""
    out = {"kind": "logos", "home": "", "away": "", "sha256": "", "src": "", "origin": ""}
    hashes = []
    for side in ("home", "away"):
        url = fixture.get(side + "_logo") or ""
        if not (url and url.lower().startswith("https://") and same_site(url, fixture.get("url", ""))):
            return None
        got = _fetch_image(url, http, min_edge=MIN_LOGO_EDGE, keep_png=True)
        if not got:
            return None
        out[side] = got["src"]
        hashes.append(got["sha256"])
    out["sha256"] = hashlib.sha256("|".join(hashes).encode("ascii")).hexdigest()
    return out


def generated_for(item, section, issue_no, slot):
    shape = "portrait" if section == "cinema" else "square"
    w, h = art_generated.KINDS[shape]
    svg = art_generated.svg("%s|%s|%s" % (issue_no, section, slot), item.get("ttl", ""), shape, label=item.get("ttl", ""))
    return {"kind": "generated", "src": "", "sha256": art_generated.sha256_of(svg), "origin": "", "w": w, "h": h}


def resolve(item, section, issue_no, slot, http, owned=None):
    """-> {"kind", "src", "sha256", "origin", "w", "h"}.
    cinema:  poster → generated.   events/worth: owned → og → generated.   fixtures: logos (build.py)."""
    if section == "cinema":
        got = poster_for(item, http)
        if got:
            return got
        return generated_for(item, section, issue_no, slot)
    if section in GENERATED_ONLY:
        return generated_for(item, section, issue_no, slot)
    got = owned_for(item, owned if owned is not None else load_owned(), http)
    if got:
        return got
    got = og_for(item, http)
    if got:
        return got
    try:
        return generated_for(item, section, issue_no, slot)
    except Exception:
        return {"kind": "none", "src": "", "sha256": "", "origin": "", "w": 0, "h": 0}
