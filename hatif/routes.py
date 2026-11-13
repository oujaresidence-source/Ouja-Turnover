# -*- coding: utf-8 -*-
"""
hatif.routes — aiohttp handlers.

PUBLIC (Hatif calls it; outside /api/ so the login middleware never touches it):
  POST /hatif/webhook   every WhatsApp message on the channel. The request must carry a valid
                        X-Voxa-Signature (HMAC-SHA256 of the raw body) or it is refused with
                        401. Answered 200 at once; the work runs in the background, because
                        Hatif retries a slow or failed delivery up to 5 times.
  GET  /hatif/webhook   a plain "listening" line, so the address can be checked in a browser.

LOGGED-IN:
  GET  /api/hatif/status   switches (never the secrets) + the last 30 messages the bot looked at
"""
import json

from . import config, engine, service
from .host import HOST

_MAX_BODY = 256 * 1024


def _json(data, status=200):
    return HOST.json_response(data, status)


async def webhook(request):
    raw = await request.content.read(_MAX_BODY + 1)
    if len(raw) > _MAX_BODY:
        return _json({"ok": False, "error": "too_large"}, 413)
    if not engine.verify_signature(config.webhook_secret(), raw, request.headers.get("X-Voxa-Signature")):
        print("[hatif] webhook refused: bad or missing signature")
        return _json({"ok": False, "error": "invalid_signature"}, 401)
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        payload = {}
    if isinstance(payload, dict) and payload.get("direction") == "Inbound":
        bg = getattr(HOST, "background", None)
        if bg:
            try:
                bg(lambda: service.handle(payload))
            except Exception as e:
                print("[hatif] background schedule failed:", e)
    return _json({})


async def webhook_probe(request):
    return _json({"ok": True, "hatif": "listening", "signed": bool(config.webhook_secret())})


async def status(request):
    if not (HOST.dash_auth and HOST.dash_auth(request)):
        return _json({"error": "unauthorized"}, 401)
    run = getattr(HOST, "run", None)
    data = await run(service.status) if run else service.status()
    return _json(dict({"ok": True}, **data))


def register_routes(app):
    r = app.router
    r.add_post("/hatif/webhook", webhook)
    r.add_get("/hatif/webhook", webhook_probe)
    r.add_get("/api/hatif/status", status)
