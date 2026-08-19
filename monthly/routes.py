# -*- coding: utf-8 -*-
"""
monthly.routes — endpoints for «التسعير الشهري», all under /api/mrent/.

READ-ONLY AGAINST HOSTAWAY. Writes in this package touch our own SQLite only
(attribute scores, Ejar references, frozen quotes, overrides) — never a price
in Hostaway.

GATING. Everything here is double-gated: login (dash_auth) AND role in
ADMIN_ROLES. This surface exposes floors, margins, the management fee and an
owner's Ejar position across the whole portfolio — the same reasoning that made
/pricecheck owner-only. Like pricecheck, it is deliberately NOT wired into the
per-page permission matrix: that matrix denies unknown tabs by default, so a new
id there would silently lock people out until the owner ticked a box nobody told
them about.
"""

import traceback

from .host import HOST

ADMIN_ROLES = ("admin",)


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
             "message": "هذي الصفحة للمالك فقط"}, 403)
    return None


def _safe(fn):
    """Guard, then never leak a traceback to the browser. Status 200 with
    ok:false so the page can say what went wrong in Arabic instead of dying."""
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


async def _api_health(request):
    """Proves the whole chain end to end — routing, login gate, role gate, JSON —
    with no user-facing surface to get wrong. The page arrives at S10."""
    return HOST.json_response({
        "ok": True,
        "stage": "S2",
        "package": "monthly",
        "read_only": True,
    })


def register(app):
    app.router.add_get("/api/mrent/health", _safe(_api_health))
