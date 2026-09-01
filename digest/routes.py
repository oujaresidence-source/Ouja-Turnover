# -*- coding: utf-8 -*-
"""digest.routes — /digest (the owner's web preview) and /api/digest/*.

Everything is behind the dashboard login (`_safe`, same wrapper as studio/routes.py);
bot.py additionally maps /api/digest/ to the «digest» permission tab in _ROLE_*_RULES,
so non-admins see it only after the owner ticks it in الصلاحيات. Files are served
from $STATE_DIR/digest/<issue_no>/ through aiohttp's FileResponse."""

import asyncio
import os
import traceback

from . import approval, build, db, notify
from .host import HOST
from .page import DIGEST_PAGE_HTML

FILE_KINDS = {"pdf": ("digest-%s.pdf", "application/pdf"), "png": ("digest-%s.png", "image/png"),
              "json": ("digest-%s.json", "application/json"), "html": ("digest-%s.html", "text/html")}


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
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
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


def _who(request):
    try:
        return HOST.req_role(request) if HOST.req_role else "web"
    except Exception:
        return "web"


def _issue_view(row):
    if not row:
        return None
    p = row.get("payload") or {}
    return {
        "id": row["id"], "issue_no": row["issue_no"], "week_of": row["week_of"], "status": row["status"],
        "issue": p.get("issue", ""), "dateLabel": p.get("dateLabel", ""), "error": row.get("error", ""),
        "rebuilds": row.get("rebuilds", 0), "updated_at": row.get("updated_at", ""),
        "status_line": notify.status_line(row), "allowed": approval.allowed(row["status"]),
        "sections": [{"key": s.get("key"), "title": s.get("title"),
                      "items": [{"ttl": it.get("ttl") or ("%s × %s" % (it.get("home", ""), it.get("away", ""))),
                                 "sub": it.get("sub") or it.get("when", ""), "url": it.get("url", "")}
                                for it in s.get("items") or []]} for s in p.get("sections") or []],
        "dropped": p.get("dropped") or [],
        "alternates": {k: [{"rank": i + 1, "ttl": a.get("ttl", ""), "reasons": a.get("reasons", [])} for i, a in enumerate(v)]
                       for k, v in (p.get("alternates") or {}).items()},
        "message": notify.build_message(p, row["issue_no"], p.get("dropped"), ""),
    }


async def page(request):
    return HOST.web.Response(text=DIGEST_PAGE_HTML, content_type="text/html")


async def api_status(request):
    row = await asyncio.to_thread(db.latest_issue)
    return HOST.json_response({"ok": True, "issue": _issue_view(row), "dryrun": bool(getattr(HOST, "dryrun", True))})


async def api_issue(request):
    n = int(request.match_info.get("n", "0") or 0)
    row = await asyncio.to_thread(db.q1, "SELECT * FROM digest_issues WHERE issue_no=?", (n,))
    if row:
        row = db._hydrate_issue(row)
    return HOST.json_response({"ok": bool(row), "issue": _issue_view(row)})


async def api_act(request):
    b = await _body(request)
    action = (b.get("action") or "").strip()
    if action not in approval.ACTIONS:
        return HOST.json_response({"ok": False, "error": "unknown action"}, 200)
    issue_id = int(b.get("issue") or 0)
    now = HOST.require("now")()
    http = HOST.require("http")
    try:
        res = await asyncio.to_thread(
            approval.act, issue_id, action, _who(request), now, http,
            b.get("section"), b.get("slot"), b.get("rank"),
            getattr(HOST, "claude_json", None), getattr(HOST, "model_premium", None),
            getattr(HOST, "claude_search", None), getattr(HOST, "load_json", None),
            getattr(HOST, "public_base", None), bool(getattr(HOST, "dryrun", True)),
            getattr(HOST, "publisher", None), None)
    except approval.ApprovalError as e:
        return HOST.json_response({"ok": False, "error": str(e)}, 200)
    row = await asyncio.to_thread(db.issue, issue_id)
    return HOST.json_response({"ok": True, "result": {"status": res["status"], "message": res["message"]}, "issue": _issue_view(row)})


async def api_build(request):
    now = HOST.require("now")()
    if await asyncio.to_thread(build.already_built, now):
        row = await asyncio.to_thread(db.latest_issue)
        return HOST.json_response({"ok": False, "error": "فيه عدد لهالأسبوع — استخدم «ابنِ من جديد»", "issue": _issue_view(row)}, 200)
    rep = await asyncio.to_thread(
        build.build_issue, now, HOST.require("http"), getattr(HOST, "claude_search", None),
        getattr(HOST, "load_json", None), True, None, getattr(HOST, "claude_json", None),
        getattr(HOST, "model_premium", None), getattr(HOST, "public_base", None))
    row = await asyncio.to_thread(db.issue, rep["issue_id"])
    return HOST.json_response({"ok": rep["status"] == "preview", "status": rep["status"], "errors": rep["errors"], "issue": _issue_view(row)})


async def api_file(request):
    n = request.match_info.get("n", "")
    kind = request.match_info.get("kind", "")
    if kind not in FILE_KINDS or not n.isdigit():
        return HOST.json_response({"ok": False, "error": "not found"}, 404)
    name, ctype = FILE_KINDS[kind]
    path = os.path.join(build._out_root(None), n, name % n)
    if not os.path.isfile(path):
        return HOST.json_response({"ok": False, "error": "file not found"}, 404)
    return HOST.web.FileResponse(path, headers={"Content-Type": ctype, "Cache-Control": "no-store"})


def register(app):
    app.router.add_get("/digest", _safe(page))
    app.router.add_get("/api/digest/status", _safe(api_status))
    app.router.add_get("/api/digest/issue/{n}", _safe(api_issue))
    app.router.add_post("/api/digest/act", _safe(api_act))
    app.router.add_post("/api/digest/build", _safe(api_build))
    app.router.add_get("/digest/file/{n}/{kind}", _safe(api_file))
