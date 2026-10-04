# -*- coding: utf-8 -*-
"""
aqd.files — everything «العقود» keeps on disk, under $STATE_DIR/aqd/ (never inside the repo).

  $STATE_DIR/aqd/<id>/draft_answers.json  full answers while a DRAFT (deleted on send)
  $STATE_DIR/aqd/<id>/frozen.html         the sent document — immutable, hashed
  $STATE_DIR/aqd/<id>/draft.pdf           the unsigned copy the client may download
  $STATE_DIR/aqd/<id>/signature.png       the client's drawn signature
  $STATE_DIR/aqd/<id>/signed.pdf          contract + owner signature + evidence page
  $STATE_DIR/aqd/<id>/final.pdf           + operator signature and stamp
  $STATE_DIR/aqd/<id>/evidence.json       the evidence record, machine-readable
  $STATE_DIR/aqd/_settings/op_sig.png, op_stamp.png

PDPL: full ID numbers exist ONLY in these files. The database holds the last 4.
"""

import base64
import io
import json
import os
import shutil
import threading

from . import config
from .host import HOST

_cache = {}
_lock = threading.Lock()
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FONT_WEIGHTS = (("Regular", 400), ("Medium", 500), ("Bold", 700))


# ------------------------------------------------------------------ repo assets (cached)

def _read_cached(path, binary=False):
    m = os.path.getmtime(path)
    with _lock:
        hit = _cache.get(path)
        if hit and hit[0] == m:
            return hit[1]
    with open(path, "rb" if binary else "r", **({} if binary else {"encoding": "utf-8"})) as f:
        data = f.read()
    with _lock:
        _cache[path] = (m, data)
    return data


def template_text(name=None):
    return _read_cached(config.template_path(name))


def contract_css():
    return _read_cached(os.path.join(config.TEMPLATES_DIR, "contract.css"))


def font_css_embedded():
    """@font-face × 3 (OujaSans 400/500/700) as base64 — the PDF renders offline."""
    out = []
    for name, w in FONT_WEIGHTS:
        data = _read_cached(os.path.join(config.FONTS_DIR, "ThmanyahSans-%s.woff2" % name), binary=True)
        out.append("@font-face{font-family:'OujaSans';font-weight:%d;font-style:normal;"
                   "src:url(data:font/woff2;base64,%s) format('woff2')}"
                   % (w, base64.b64encode(data).decode("ascii")))
    return "".join(out)


def font_css_urls():
    return "".join("@font-face{font-family:'OujaSans';font-weight:%d;font-style:normal;"
                   "src:url(/guide/fonts/thmanyahsans-%s.woff2) format('woff2')}" % (w, name)
                   for name, w in FONT_WEIGHTS)


def for_screen(doc):
    """Same document, fonts by URL instead of ~320 KB of base64 (phone + dashboard preview).
    Never applied to the bytes that are hashed or printed."""
    try:
        return doc.replace(font_css_embedded(), font_css_urls(), 1)
    except OSError:
        return doc


# ------------------------------------------------------------------ per-contract files

def root():
    base = HOST.state_dir or os.environ.get("STATE_DIR") or "."
    return os.path.join(base, "aqd")


def cdir(cid, create=True):
    d = os.path.join(root(), str(int(cid)))
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def path(cid, name):
    return os.path.join(cdir(cid), name)


def exists(cid, name):
    return os.path.isfile(os.path.join(cdir(cid, create=False), name))


def write_text(cid, name, text):
    p = path(cid, name)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)
    return p


def read_text(cid, name):
    with open(path(cid, name), encoding="utf-8") as f:
        return f.read()


def write_bytes(cid, name, data):
    p = path(cid, name)
    tmp = p + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, p)
    return p


def read_bytes(cid, name):
    with open(path(cid, name), "rb") as f:
        return f.read()


def remove(cid, name):
    try:
        os.remove(path(cid, name))
    except FileNotFoundError:
        pass


def write_json(cid, name, obj):
    return write_text(cid, name, json.dumps(obj, ensure_ascii=False, indent=1))


def read_json(cid, name, default=None):
    try:
        return json.loads(read_text(cid, name))
    except (OSError, ValueError):
        return default


def drop_contract_dir(cid):
    shutil.rmtree(cdir(cid, create=False), ignore_errors=True)


# ------------------------------------------------------------------ settings images

def settings_path(name):
    d = os.path.join(root(), "_settings")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def settings_png_b64(name):
    try:
        with open(settings_path(name), "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except OSError:
        return ""


def save_settings_png(name, data):
    p = settings_path(name)
    with open(p + ".tmp", "wb") as f:
        f.write(data)
    os.replace(p + ".tmp", p)


# ------------------------------------------------------------------ PNG checks

def decode_png_b64(b64):
    """'data:image/png;base64,…' or bare base64 -> bytes, or None."""
    s = str(b64 or "")
    if s.startswith("data:"):
        s = s.split(",", 1)[-1]
    try:
        return base64.b64decode(s, validate=True)
    except Exception:
        return None


def check_png(data, min_ink=0):
    """-> Arabic refusal or ''. A real PNG (magic bytes), ≤ 300 KB, and — for a signature —
    at least `min_ink` non-transparent pixels (a blank canvas is not a signature)."""
    if not data:
        return "ما وصلت الصورة"
    if len(data) > config.SIG_MAX_BYTES:
        return "الصورة أكبر من 300 KB"
    if not data.startswith(PNG_MAGIC):
        return "الملف لازم يكون PNG"
    if not min_ink:
        return ""
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.width * im.height > 4000 * 4000:
            return "الصورة كبيرة جداً"
        # Ink = a visibly dark pixel once the image sits on white paper. Counting alpha alone
        # would let an opaque white canvas pass as "signed".
        rgba = im.convert("RGBA")
        paper = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        gray = Image.alpha_composite(paper, rgba).convert("L")
        ink = sum(gray.histogram()[:200])
        if ink < min_ink:
            return "التوقيع فاضي — ارسم توقيعك"
    except Exception:
        return "تعذّر قراءة صورة التوقيع"
    return ""
