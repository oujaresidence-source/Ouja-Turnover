# -*- coding: utf-8 -*-
"""
campaigns.routes — one LOGGED-IN read endpoint. There is no write endpoint and no public door:
the code words come from Hostaway messages and the taps through Hatif's own signed webhook
(/hatif/webhook, which hands taps to campaigns.service.on_hatif).

  GET /api/campaigns/status   switches, the code words, the opt-out count, the last weekly
                              report date and the last 30 taps (label, template, last 4 digits
                              and the SHAPE Hatif delivered — never a number or a message).
"""
from . import service
from .host import HOST


async def status(request):
    if not (HOST.dash_auth and HOST.dash_auth(request)):
        return HOST.json_response({"error": "unauthorized"}, 401)
    run = getattr(HOST, "run", None)
    data = await run(service.status) if run else service.status()
    return HOST.json_response(dict({"ok": True}, **data))


def register_routes(app):
    app.router.add_get("/api/campaigns/status", status)
