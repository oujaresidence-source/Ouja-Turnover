# -*- coding: utf-8 -*-
"""
campaigns.routes — one LOGGED-IN read endpoint. There is no write endpoint and no public door:
the code words come from Hostaway messages and the taps through Hatif's own signed webhook
(/hatif/webhook, which hands taps to campaigns.service.on_hatif).

  GET /api/campaigns/status   switches, the code words, the opt-out count, the last weekly
                              report date and the last 30 taps (label, template, last 4 digits
                              and the SHAPE Hatif delivered — never a number or a message).
"""
from . import personal, service
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


def register_routes(app):
    app.router.add_get("/api/campaigns/status", status)
    app.router.add_get("/api/campaigns/queue", queue_status)
    app.router.add_post("/api/campaigns/queue", queue_load)
    app.router.add_post("/api/campaigns/queue/cancel", queue_cancel)
