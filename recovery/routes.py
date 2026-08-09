# -*- coding: utf-8 -*-
"""
recovery.routes — the dashboard tab's data endpoint.

ONE route for now, and it is READ-ONLY: GET /api/recovery/status. There is deliberately no
write endpoint yet. The buttons, the modals and the /call/{token} redirect arrive with the
Discord phase; shipping a write door before the state machine that guards it is how a
feature ends up with a half-enforced workflow.

Auth mirrors coverage_study/routes.py: login required via HOST.dash_auth, and bot.py's
_ROLE_READ_RULES additionally gates /api/recovery/ on the «rec» page permission, so a
viewer who was never granted the tab gets a 403 from the server as well as a hidden tab in
the UI. Two independent gates, same as every other sensitive page.
"""

import traceback

from . import status
from .host import HOST


def _json(obj, code=200):
    return HOST.json_response(obj, code)


def _safe(fn):
    async def _w(request):
        try:
            if HOST.dash_auth and not HOST.dash_auth(request):
                return _json({"error": "unauthorized"}, 401)
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return _json({"error": "server_error", "detail": str(e)[:300]}, 500)
    _w.__name__ = getattr(fn, "__name__", "recovery_handler")
    return _w


async def api_status(request):
    """Everything the «استرداد التجربة» tab renders. Blocking (SQLite reads), so it runs in
    a thread — the aiohttp loop also serves the guest-facing pages."""
    mk = (request.query.get("month") or "").strip() or None
    try:
        import asyncio
        data = await asyncio.to_thread(status.payload, mk)
    except AttributeError:                       # Python < 3.9 has no asyncio.to_thread
        data = status.payload(mk)
    return _json(data)


def register_routes(app):
    app.router.add_get("/api/recovery/status", _safe(api_status))
    return app
