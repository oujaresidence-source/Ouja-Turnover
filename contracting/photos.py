# -*- coding: utf-8 -*-
"""
contracting.photos — a small copy of every proof photo, kept next to brain.db.

Why: Discord attachment links expire, and the owner's file (contracting.ownerpdf) needs the
pictures weeks later. Each photo is shrunk to 1280px JPEG (~150–250 KB) the moment it lands.

The 2026-06-23 outage (cleaning photos filled /data) is why there is a hard ceiling:
CONTRACTING_PHOTO_CAP_MB (default 1500). Over it, nothing new is copied — the line still
closes on the Discord link, only the owner's file goes without that picture. Never raises.
"""

import io
import os
import uuid

from brain import db as _bdb

MAX_PX = 1280
QUALITY = 74
_size_cache = {"bytes": None}


def root():
    return os.path.join(os.path.dirname(os.path.abspath(_bdb.db_path())), "contracting_photos")


def cap_bytes():
    try:
        return int(float(os.environ.get("CONTRACTING_PHOTO_CAP_MB") or 1500) * 1024 * 1024)
    except ValueError:
        return 1500 * 1024 * 1024


def used_bytes():
    if _size_cache["bytes"] is None:
        total = 0
        for dp, _dn, fns in os.walk(root()):
            for fn in fns:
                try:
                    total += os.path.getsize(os.path.join(dp, fn))
                except OSError:
                    pass
        _size_cache["bytes"] = total
    return _size_cache["bytes"]


def shrink(raw):
    """bytes → small JPEG bytes, or None if it is not a picture Pillow can read (HEIC)."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((MAX_PX, MAX_PX))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=QUALITY, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def keep(url, project_id, raw=None):
    """Download (unless `raw` is given), shrink, store. → relative path or ''."""
    try:
        if raw is None:
            if not str(url or "").startswith("http"):
                return ""
            import requests
            r = requests.get(url, timeout=20)
            if r.status_code != 200 or not r.content:
                return ""
            raw = r.content
        small = shrink(raw)
        if not small:
            return ""
        if used_bytes() + len(small) > cap_bytes():
            print("[contracting] photo cap reached — not copying", url)
            return ""
        rel = os.path.join(str(project_id), uuid.uuid4().hex[:16] + ".jpg")
        path = os.path.join(root(), rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(small)
        _size_cache["bytes"] = used_bytes() + len(small)
        return rel
    except Exception as e:
        print("[contracting] photo copy failed:", e)
        return ""


def path_of(rel):
    """Absolute path of a kept copy, or '' if it is missing (never outside root)."""
    if not rel:
        return ""
    base = os.path.realpath(root())
    p = os.path.realpath(os.path.join(base, str(rel)))
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        return ""
    return p
