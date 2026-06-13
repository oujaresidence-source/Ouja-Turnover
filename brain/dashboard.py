"""
brain.dashboard — serves the /brain page. The HTML lives in a REAL file (dashboard.html),
not a Python triple-quoted string, so the project's #1 trap (Python eating \n/\t inside
embedded JS) cannot happen here. We read it once and cache it in memory.
"""

import os

_cache = {"page": None}
_DIR = os.path.dirname(__file__)


def page_html():
    if _cache["page"] is None:
        with open(os.path.join(_DIR, "dashboard.html"), "r", encoding="utf-8") as f:
            _cache["page"] = f.read()
    return _cache["page"]


def locked_html():
    return (
        "<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>أوجا برين</title>"
        "<style>body{margin:0;min-height:100vh;display:grid;place-items:center;"
        "background:#161310;color:#F7F1E6;font-family:system-ui,'Segoe UI',Tahoma,sans-serif}"
        ".card{text-align:center;padding:40px 48px;border:1px solid rgba(200,169,110,.3);"
        "border-radius:18px;background:#1d1a16}.g{color:#C8A96E;font-size:22px;font-weight:800}"
        "p{opacity:.7;margin:.6em 0 0}</style></head><body><div class='card'>"
        "<div class='g'>🔒 أوجا برين</div><p>افتح الصفحة من رابط لوحة التحكم (يحمل التوكن).</p>"
        "<p style='font-size:13px'>Open this page from the dashboard link (it carries your token).</p>"
        "</div></body></html>")
