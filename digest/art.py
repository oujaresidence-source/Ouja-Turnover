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
MAX_BYTES = 6000000
GENERATED_ONLY = ("cinema", "fixtures")


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


def image_ok(raw, ctype):
    if not (ctype or "").lower().startswith("image/"):
        return False
    if not raw or len(raw) > MAX_BYTES:
        return False
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(raw))
        return max(im.size) >= MIN_LONG_EDGE
    except Exception:
        return False


def _fetch_image(url, http):
    try:
        status, final, ctype, raw = http.get_bytes(url, timeout=10, max_bytes=MAX_BYTES + 1)
    except Exception:
        return None
    if status != 200 or not image_ok(raw, ctype):
        return None
    return {"src": thumb_jpeg_b64(raw), "sha256": hashlib.sha256(raw).hexdigest(), "origin": final or url}


def owned_for(item, owned, http):
    key = item.get("slug") or ""
    entry = owned.get(key) if key else None
    if not entry or not entry.get("url"):
        return None
    got = _fetch_image(entry["url"], http)
    if not got:
        return None
    return {"kind": "owned", "src": got["src"], "sha256": got["sha256"], "origin": got["origin"]}


def og_for(item, http):
    og = (item.get("art_hint") or {}).get("og") or ""
    if not og or not og.lower().startswith("https://"):
        return None
    if not same_site(og, item.get("url", "")):
        return None
    got = _fetch_image(og, http)
    if not got:
        return None
    return {"kind": "og", "src": got["src"], "sha256": got["sha256"], "origin": got["origin"]}


def generated_for(item, section, issue_no, slot):
    shape = "portrait" if section == "cinema" else "square"
    svg = art_generated.svg("%s|%s|%s" % (issue_no, section, slot), item.get("ttl", ""), shape, label=item.get("ttl", ""))
    return {"kind": "generated", "src": "", "sha256": art_generated.sha256_of(svg), "origin": ""}


def resolve(item, section, issue_no, slot, http, owned=None):
    """-> {"kind", "src", "sha256", "origin"} — A → B → C → D."""
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
        return {"kind": "none", "src": "", "sha256": "", "origin": ""}
