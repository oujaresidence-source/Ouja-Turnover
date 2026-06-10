# -*- coding: utf-8 -*-
"""Ouja Finance ERP v2 — المركز المالي الجديد.

The new finance system. Lives ENTIRELY in this package — never inside bot.py.
bot.py mounts it with a ~6-line patch inside start_web_server():

    import sys as _erp_sys, finance as _finance_erp
    _finance_erp.mount(app, _erp_sys.modules[__name__])

DESIGN CONTRACT (META-1 of the build prompt):
- We NEVER `import bot`. bot.py runs as __main__; importing it by name would
  execute the whole 45k-line monolith a SECOND time (second Discord client,
  second web server). Instead bot.py hands us its live module object at mount
  time and every reuse of existing functions/data goes through `api.B.<name>`.
- Auth is the dashboard's own: B._dash_auth (login) + B._user_can (roles).
- STATE_DIR data files are sacred: this package reuses bot.py's loaders and
  stores; it does not invent parallel copies of existing data.

Files:
    __init__.py        routes + handlers (this file)
    api.py             thin bridge to bot.py's functions/data + auth helpers
    statements.py      financial statements + budget math (pure, testable)
    templates/erp.html SPA shell (re-read per request — no stale-template pain)
    static/erp.js      front-end
    static/erp.css     styles (Ouja OS tokens copied from the dashboard)
"""

import os
import time
import pathlib
from datetime import datetime, timezone, timedelta

from aiohttp import web

from . import api

# Bumped on EVERY shipped slice — this string + commit + build time is the
# owner's 5-second proof that a deploy actually reached production.
ERP_VERSION = "2.0.0-s0"

_DIR = pathlib.Path(__file__).resolve().parent
_BOOT = time.time()
_KSA = timezone(timedelta(hours=3))


def _detect_commit():
    """Short git hash of the running build. Railway injects RAILWAY_GIT_COMMIT_SHA;
    local dev falls back to reading .git directly (no subprocess)."""
    for k in ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT", "SOURCE_VERSION", "COMMIT_SHA"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v[:10]
    try:
        root = _DIR.parent
        head = (root / ".git" / "HEAD").read_text("utf-8").strip()
        if not head.startswith("ref:"):
            return head[:10]
        ref = head.split(None, 1)[1].strip()
        ref_file = root / ".git" / ref
        if ref_file.exists():
            return ref_file.read_text("utf-8").strip()[:10]
        packed = root / ".git" / "packed-refs"
        if packed.exists():
            for line in packed.read_text("utf-8").splitlines():
                if line.endswith(ref):
                    return line.split(" ", 1)[0][:10]
    except Exception:
        pass
    return "unknown"


_COMMIT = _detect_commit()
_BUILT = datetime.fromtimestamp(_BOOT, _KSA).strftime("%Y-%m-%d %H:%M") + " KSA"


def version_info():
    return {
        "ok": True,
        "app": "ouja-finance-erp",
        "version": ERP_VERSION,
        "commit": _COMMIT,
        "built": _BUILT,
        "uptime_s": int(time.time() - _BOOT),
    }


# Branded "open it from the dashboard" gate — same idea as the invest 403 page.
_GATE_HTML = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>عوجا — المركز المالي</title>
<style>body{margin:0;font-family:'Tajawal',-apple-system,system-ui,sans-serif;background:#F5F5F7;color:#1D1D1F;
display:flex;align-items:center;justify-content:center;min-height:100vh}
.c{background:#fff;border:1px solid #E8E8ED;border-radius:18px;padding:40px 44px;max-width:420px;text-align:center;
box-shadow:0 4px 12px rgba(0,0,0,.06)}
h1{font-size:19px;margin:0 0 10px}p{font-size:14.5px;color:#6E6E73;line-height:1.9;margin:0}</style></head>
<body><div class="c"><h1>هالصفحة محمية 🔒</h1>
<p>المركز المالي يفتح من داخل لوحة عوجا.<br>ارجع للوحة وافتحه من القائمة الجانبية.</p></div></body></html>"""


async def _h_version(request):
    """Ungated build stamp — no business data, just proof of what's deployed."""
    return web.json_response(version_info())


async def _h_erp(request):
    if not api.authed(request):
        return web.Response(text=_GATE_HTML, content_type="text/html", status=401)
    try:
        html = (_DIR / "templates" / "erp.html").read_text("utf-8")
    except Exception as e:
        return web.Response(text="erp.html missing: %r" % (e,), status=500)
    html = (html.replace("__ERP_VERSION__", ERP_VERSION)
                .replace("__ERP_COMMIT__", _COMMIT)
                .replace("__ERP_BUILT__", _BUILT))
    return web.Response(text=html, content_type="text/html")


def mount(app, botmod):
    """Attach ERP v2 to the running aiohttp app. Called once from bot.py."""
    api.attach(botmod)
    app.router.add_get("/erp", _h_erp)
    app.router.add_get("/erp/version", _h_version)
    app.router.add_static("/erp/static/", path=str(_DIR / "static"), name="erp-static")
    return True
