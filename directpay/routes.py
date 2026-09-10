# -*- coding: utf-8 -*-
"""
directpay.routes — aiohttp handlers, ALL behind HOST.dash_auth (login) and, in bot.py's role
middleware, the `dpay` permission tab.

  GET  /api/directpay/board        {open[], verified_recent[], written_off[], totals{}, aging{}}
  GET  /api/directpay/ticket/{id}  one ticket + its audit trail
  POST /api/directpay/note         add a note to a ticket (any authenticated staff)

THERE IS NO CLOSE ENDPOINT ON THE WEB — on purpose. The close happens in Discord, where the
proof file lives and where the administrator identity is unambiguous. A web close would need
its own upload path and its own gate, and would become the soft way around the money gate.
Do not add one.
"""
import json
import traceback

from . import db, service
from .host import HOST

_MAX_BODY = 8192


def _safe(fn):
    async def _w(request):
        if not (HOST.dash_auth and HOST.dash_auth(request)):
            return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
        try:
            return await fn(request)
        except Exception:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "صار خطأ مؤقت"}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    raw = await request.content.read(_MAX_BODY + 1)
    if len(raw) > _MAX_BODY:
        return {}
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}


def _actor(request):
    for name in ("req_actor", "actor"):
        fn = getattr(HOST, name, None)
        if fn:
            try:
                return fn(request) or "—"
            except Exception:
                pass
    return "—"


def _room_link(channel_id):
    gid = getattr(HOST, "guild_id", None)
    if not gid or not channel_id:
        return ""
    return "https://discord.com/channels/%s/%s" % (gid, channel_id)


@_safe
async def board(request):
    b = service.board(room_link=_room_link)
    b["ok"] = True
    return HOST.json_response(b)


@_safe
async def ticket(request):
    tid = str(request.match_info.get("id") or "").strip()
    t = db.ticket(tid)
    if not t:
        return HOST.json_response({"ok": False, "error": "not found"}, 404)
    t = dict(t)
    t["room_url"] = _room_link(t.get("channel_id"))
    return HOST.json_response({"ok": True, "ticket": t, "events": db.events(tid)})


@_safe
async def note(request):
    body = await _body(request)
    tid = str(body.get("ticket_id") or "").strip()
    text = str(body.get("text") or "").strip()
    if not tid or not text:
        return HOST.json_response({"ok": False, "error": "ticket_id and text are required"}, 400)
    t = service.add_note(tid, text, _actor(request))
    if not t:
        return HOST.json_response({"ok": False, "error": "not found"}, 404)
    return HOST.json_response({"ok": True, "events": db.events(tid)})


def register_routes(app):
    r = app.router
    r.add_get("/api/directpay/board", board)
    r.add_get("/api/directpay/ticket/{id}", ticket)
    r.add_post("/api/directpay/note", note)
