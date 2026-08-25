# -*- coding: utf-8 -*-
"""
pricecheck.routes — /pricecheck (the page) and /api/pricecheck/scan (the data).

READ-ONLY BY CONSTRUCTION. There is no POST, PUT or DELETE in this package, and no
call anywhere in it that writes to Hostaway. Correcting a price is a separate,
explicitly approved step; until then this tool can only look.

Gated on login AND role in ADMIN_ROLES — this exposes every booking's money fields
across the whole portfolio. It is deliberately NOT wired into the per-page permission
matrix: that matrix denies unknown tabs by default, so adding a new tab id would have
silently locked out the accountants until the owner ticked a box nobody told them about.
"""

import traceback
from datetime import date, timedelta

from . import page, scan
from .host import HOST

ADMIN_ROLES = ("admin",)
MAX_DAYS = 400          # one scan is one question, not the whole history


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    role = "viewer"
    try:
        role = HOST.req_role(request) if HOST.req_role else "viewer"
    except Exception:
        role = "viewer"
    if role not in ADMIN_ROLES:
        return HOST.json_response(
            {"ok": False, "error": "forbidden",
             "message": "هذه الصفحة للمالك فقط"}, 403)
    return None


def _safe(fn):
    async def _w(request):
        g = _guard(request)
        if g:
            return g
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response(
                {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _parse_day(s, fallback):
    try:
        y, m, d = str(s)[:10].split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError, TypeError):
        return fallback


async def _api_scan(request):
    import asyncio
    q = request.rel_url.query
    today = date.today()
    start = _parse_day(q.get("start"), today - timedelta(days=60))
    end = _parse_day(q.get("end"), today + timedelta(days=30))
    if end <= start:
        return HOST.json_response(
            {"ok": False, "error": "bad_range",
             "message": "تاريخ النهاية لازم يكون بعد تاريخ البداية"}, 200)
    if (end - start).days > MAX_DAYS:
        return HOST.json_response(
            {"ok": False, "error": "range_too_wide",
             "message": "أقصى مدة للفحص %d يوم — قسّمها على فترات" % MAX_DAYS}, 200)
    channel = (q.get("channel") or "direct").strip().lower()
    if channel not in ("direct", "airbnb", "other", "all"):
        channel = "direct"
    lid = q.get("lid") or None
    deep = q.get("deep") in ("1", "true", "yes")
    include_cancelled = q.get("cancelled") in ("1", "true", "yes")
    out = await asyncio.to_thread(scan.scan, start, end, channel, lid,
                                  include_cancelled, deep)
    out["ok"] = True
    return HOST.json_response(out)


async def _api_one(request):
    """Everything Hostaway holds about ONE booking. The portfolio scan can say two
    numbers differ; only this can say where a third number lives."""
    import asyncio
    rid = (request.rel_url.query.get("id") or "").strip()
    if not rid.isdigit():
        return HOST.json_response(
            {"ok": False, "error": "bad_id",
             "message": "اكتب رقم الحجز بالأرقام فقط"}, 200)
    out = await asyncio.to_thread(scan.probe, int(rid))
    out["ok"] = not out.get("error")
    return HOST.json_response(out)


async def _page(request):
    g = _guard(request)
    if g:
        return HOST.web.Response(
            text="<h3 dir=rtl style=font-family:system-ui>تحتاج تسجيل دخول المالك"
                 " — افتح /dashboard وسجّل الدخول ثم ارجع لهذي الصفحة.</h3>",
            content_type="text/html", status=403)
    return HOST.web.Response(text=page.HTML, content_type="text/html")


def register(app):
    app.router.add_get("/pricecheck", _page)
    app.router.add_get("/api/pricecheck/scan", _safe(_api_scan))
    app.router.add_get("/api/pricecheck/one", _safe(_api_one))
