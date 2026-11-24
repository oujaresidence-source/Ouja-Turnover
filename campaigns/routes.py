# -*- coding: utf-8 -*-
"""
campaigns.routes — one LOGGED-IN read endpoint. There is no write endpoint and no public door:
the code words come from Hostaway messages and the taps through Hatif's own signed webhook
(/hatif/webhook, which hands taps to campaigns.service.on_hatif).

  GET /api/campaigns/status   switches, the code words, the opt-out count, the last weekly
                              report date and the last 30 taps (label, template, last 4 digits
                              and the SHAPE Hatif delivered — never a number or a message).

«الحملات» board (2026-11-24, campaigns/board.py):
  GET  /campaigns/static/campaigns_tab.js   PUBLIC code, no data (the dashboard tab script)
  GET  /api/campaigns/board                 login + the «camp» page permission
  POST /api/campaigns/board/numbers         ADMIN: Hatif's own counts, a moved / cancelled send
  POST /api/campaigns/audience              ADMIN: who got a campaign → salted keys only
"""
import os
import traceback

from . import board, personal, service
from .host import HOST


async def status(request):
    if not (HOST.dash_auth and HOST.dash_auth(request)):
        return HOST.json_response({"error": "unauthorized"}, 401)
    run = getattr(HOST, "run", None)
    data = await run(service.status) if run else service.status()
    return HOST.json_response(dict({"ok": True}, **data))


def _admin(request):
    fn = getattr(HOST, "is_admin", None)
    return bool(HOST.dash_auth and HOST.dash_auth(request) and fn and fn(request))


async def queue_status(request):
    """Counts per batch / campaign / state — never a number."""
    if not (HOST.dash_auth and HOST.dash_auth(request)):
        return HOST.json_response({"error": "unauthorized"}, 401)
    run = getattr(HOST, "run", None)
    data = await run(personal.summary) if run else personal.summary()
    return HOST.json_response(dict({"ok": True}, **data))


async def queue_load(request):
    """ADMIN ONLY. {batch, rows:[{phone, campaign, template, values, image_url, send_at}]}.
    Loading sends nothing by itself: the minute loop sends only when CAMPAIGN_PERSONAL_DRYRUN=0."""
    if not _admin(request):
        return HOST.json_response({"error": "admin only"}, 403)
    try:
        body = await request.json()
    except Exception:
        return HOST.json_response({"error": "bad json"}, 400)
    rows = (body or {}).get("rows") or []
    if not isinstance(rows, list) or len(rows) > 20000:
        return HOST.json_response({"error": "rows must be a list (max 20000)"}, 400)
    run = getattr(HOST, "run", None)
    res = await run(personal.load, body.get("batch"), rows) if run else personal.load(body.get("batch"), rows)
    return HOST.json_response(dict({"ok": True}, **res))


async def queue_cancel(request):
    """ADMIN ONLY. {batch} → everything of that batch not sent yet is cancelled."""
    if not _admin(request):
        return HOST.json_response({"error": "admin only"}, 403)
    try:
        body = await request.json()
    except Exception:
        return HOST.json_response({"error": "bad json"}, 400)
    run = getattr(HOST, "run", None)
    n = await run(personal.cancel, (body or {}).get("batch")) if run else personal.cancel((body or {}).get("batch"))
    return HOST.json_response({"ok": True, "cancelled": n})


# ---------------------------------------------------------------- «الحملات» board
STATIC_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "campaigns_tab.js")
_js_cache = {"mtime": None, "text": ""}


def js_version():
    try:
        return str(int(os.path.getmtime(STATIC_JS)))
    except OSError:
        return "0"


def _js_text():
    m = os.path.getmtime(STATIC_JS)
    if _js_cache["mtime"] != m:
        with open(STATIC_JS, encoding="utf-8") as f:
            _js_cache["text"] = f.read()
        _js_cache["mtime"] = m
    return _js_cache["text"]


async def static_js(request):
    """PUBLIC code, no data — the tab script (a real file: no DASHBOARD_HTML backslash trap)."""
    run = getattr(HOST, "run", None)
    text = await run(_js_text) if run else _js_text()
    return HOST.web.Response(text=text, content_type="application/javascript",
                             headers={"Cache-Control": "no-cache"})


async def board_get(request):
    """Logged in (and the «camp» page permission, enforced by bot.py's role middleware)."""
    if not (HOST.dash_auth and HOST.dash_auth(request)):
        return HOST.json_response({"error": "unauthorized"}, 401)
    run = getattr(HOST, "run", None)
    try:
        data = await run(board.board) if run else board.board()
    except Exception as e:
        traceback.print_exc()
        return HOST.json_response({"ok": False, "error": type(e).__name__}, 500)
    data["can_edit"] = _admin(request)
    return HOST.json_response(dict({"ok": True}, **data))


async def board_numbers(request):
    """ADMIN ONLY. {campaign, sent?, delivered?, read_n?, replied?, signed?, send_at?, status?, note?}
    — what only Hatif's own page shows, or a moved / cancelled send."""
    if not _admin(request):
        return HOST.json_response({"error": "admin only"}, 403)
    try:
        body = await request.json()
    except Exception:
        return HOST.json_response({"error": "bad json"}, 400)
    body = body or {}
    run = getattr(HOST, "run", None)
    try:
        args = (body.get("campaign"), body, "admin")
        await run(board.set_numbers, *args) if run else board.set_numbers(*args)
    except (ValueError, TypeError) as e:
        return HOST.json_response({"error": "bad value: %s" % e}, 400)
    return HOST.json_response({"ok": True})


async def audience_load(request):
    """ADMIN ONLY. {campaign, phones:[...], role: sent|holdout, replace?} — the numbers are turned
    into salted keys on arrival and never stored; the answer carries counts only."""
    if not _admin(request):
        return HOST.json_response({"error": "admin only"}, 403)
    try:
        body = await request.json()
    except Exception:
        return HOST.json_response({"error": "bad json"}, 400)
    body = body or {}
    phones = body.get("phones") or []
    if not isinstance(phones, list) or len(phones) > 5000:
        return HOST.json_response({"error": "phones must be a list (max 5000)"}, 400)
    run = getattr(HOST, "run", None)
    args = (body.get("campaign"), phones, body.get("role") or "sent", bool(body.get("replace")))
    try:
        res = await run(board.load_audience, *args) if run else board.load_audience(*args)
    except ValueError as e:
        return HOST.json_response({"error": "bad value: %s" % e}, 400)
    return HOST.json_response(dict({"ok": True}, **res))


def register_routes(app):
    app.router.add_get("/campaigns/static/campaigns_tab.js", static_js)
    app.router.add_get("/api/campaigns/board", board_get)
    app.router.add_post("/api/campaigns/board/numbers", board_numbers)
    app.router.add_post("/api/campaigns/audience", audience_load)
    app.router.add_get("/api/campaigns/status", status)
    app.router.add_get("/api/campaigns/queue", queue_status)
    app.router.add_post("/api/campaigns/queue", queue_load)
    app.router.add_post("/api/campaigns/queue/cancel", queue_cancel)
