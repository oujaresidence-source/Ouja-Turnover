# -*- coding: utf-8 -*-
"""
mot.photos — evidence photos, stored LOCALLY under $STATE_DIR/mot_photos/<round>/.

Why local and not a Discord URL like cleaning photos: Discord links are signed and expire,
and evidence for the ministry cannot expire after a day. Why small: 74 units x 61 components
x 3 photos explodes a volume fast, so every image is re-encoded to JPEG, longest side
MAX_SIDE, quality tuned toward ~TARGET_KB. The DB stores a RELATIVE path.
"""
import io
import os
import re

MAX_SIDE = 1600
TARGET_KB = 200
MAX_PER_COMPONENT = 3
MAX_UPLOAD_MB = 12
ROOT = "mot_photos"

_SAFE = re.compile(r"[^A-Za-z0-9_.\-]")


def shrink(data):
    """bytes -> (jpeg bytes, width, height). Falls back to the original bytes if Pillow
    cannot read them (a HEIC without the plugin, for instance) — a stored original beats
    a lost photo."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data, None, None
    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        w, h = im.size
        scale = MAX_SIDE / float(max(w, h))
        if scale < 1:
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        out = b""
        for qlt in (82, 72, 62, 52, 42):
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=qlt, optimize=True, progressive=True)
            out = buf.getvalue()
            if len(out) <= TARGET_KB * 1024:
                break
        return out, im.size[0], im.size[1]
    except Exception:
        return data, None, None


def rel_path(rid, comp_key, n):
    key = _SAFE.sub("_", str(comp_key or "unit"))
    return "%s/%d/%s_%d.jpg" % (ROOT, int(rid), key, int(n))


def save(state_dir, rid, comp_key, n, data):
    """Write the shrunk image; return the RELATIVE path the DB stores."""
    rel = rel_path(rid, comp_key, n)
    full = os.path.join(state_dir, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    small, _, _ = shrink(data)
    with open(full, "wb") as f:
        f.write(small)
    return rel


def abs_path(state_dir, rel):
    """Resolve a stored relative path, refusing anything that escapes the photo root."""
    rel = str(rel or "")
    if not rel.startswith(ROOT + "/") or ".." in rel:
        return None
    return os.path.join(state_dir, rel)
