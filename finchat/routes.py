# -*- coding: utf-8 -*-
"""finchat.routes — /erp/api/finchat/*. Service functions (svc_*) hold the logic and are
unit-tested; thin aiohttp handlers wrap them with the auth gates from HOST."""
import asyncio
import json

from . import answer as _ans
from . import db as _db

HOST = {
    # set by finchat.wire():
    # dash_auth(request)->bool, can_finance(request)->bool, is_admin(request)->bool,
    # actor(request)->str, notify(payload)->None, web (aiohttp web module)
}


def _jres(data, status=200):
    web = HOST["web"]
    return web.json_response(data, status=status,
                             dumps=lambda o: json.dumps(o, ensure_ascii=False))


# ---------------- services (unit-tested) ----------------

def svc_escalate(username, question):
    esc_id = _db.esc_create(username, question,
                            context={"last_msgs": [m["text"] for m in _db.msgs_for(username, limit=6)]})
    _db.msg_add(username, "bot", "تم تصعيد سؤالك لفيصل — بيوصلك الرد هنا 🔔")
    try:
        n = HOST.get("notify")
        if n:
            n({"esc_id": esc_id, "username": username, "question": question})
    except Exception as e:
        print("[finchat] escalation notify failed (row saved):", e)
    return {"ok": True, "esc_id": esc_id}


def svc_inbox_answer(esc_id, answer_text, save_kb=False, kb_tags=""):
    row = _db.esc_get(esc_id)
    if not row:
        return {"error": "not_found"}
    if not _db.esc_answer(esc_id, answer_text, saved_as_kb=1 if save_kb else 0):
        return {"error": "already_answered",
                "message_ar": "هذا التصعيد مجاوب عليه من قبل."}
    _db.msg_add(row["username"], "owner", answer_text)
    if save_kb:
        _db.kb_upsert(row["question"], answer_text, tags=kb_tags or "", source="learned")
    return {"ok": True}


# ---------------- aiohttp handlers ----------------

def _gate(request, admin=False):
    """Returns an error response or None if allowed."""
    if not HOST["dash_auth"](request):
        return _jres({"error": "unauthorized"}, 401)
    if not HOST["can_finance"](request):
        return _jres({"error": "forbidden"}, 403)
    if admin and not HOST["is_admin"](request):
        return _jres({"error": "forbidden", "detail": "admin only"}, 403)
    return None


async def h_ask(request):
    err = _gate(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return _jres({"error": "bad_json"}, 400)
    q = str(body.get("q") or "").strip()[:2000]
    if not q:
        return _jres({"error": "empty"}, 400)
    user = HOST["actor"](request)
    r = await asyncio.to_thread(_ans.answer_question, user, q)
    if r.get("error") == "daily_cap":
        return _jres(r, 429)
    if r.get("error"):
        return _jres(r, 502 if r["error"] == "api_error" else 400)
    return _jres(r)


async def h_history(request):
    err = _gate(request)
    if err:
        return err
    user = HOST["actor"](request)
    msgs = await asyncio.to_thread(_db.msgs_for, user, 60)
    return _jres({"ok": True, "msgs": [
        {"role": m["role"], "text": m["text"], "links": m["links"],
         "ts": m["ts"], "confidence": m.get("confidence")} for m in msgs]})


async def h_escalate(request):
    err = _gate(request)
    if err:
        return err
    try:
        body = await request.json()
    except Exception:
        return _jres({"error": "bad_json"}, 400)
    q = str(body.get("q") or "").strip()[:2000]
    if not q:
        return _jres({"error": "empty"}, 400)
    r = await asyncio.to_thread(svc_escalate, HOST["actor"](request), q)
    return _jres(r)


async def h_inbox(request):
    err = _gate(request, admin=True)
    if err:
        return err
    items = await asyncio.to_thread(_db.esc_open_list)
    return _jres({"ok": True, "items": items, "open_count": len(items)})


async def _body(request):
    """Parse the JSON body or None — unguarded request.json() would 500 on malformed JSON."""
    try:
        return await request.json()
    except Exception:
        return None


async def h_inbox_answer(request):
    err = _gate(request, admin=True)
    if err:
        return err
    body = await _body(request)
    if body is None:
        return _jres({"error": "bad_json"}, 400)
    r = await asyncio.to_thread(
        svc_inbox_answer, int(body.get("esc_id") or 0),
        str(body.get("answer") or "").strip(),
        bool(body.get("save_kb")), str(body.get("kb_tags") or ""))
    if r.get("error"):
        return _jres(r, 409 if r["error"] == "already_answered" else 404)
    return _jres(r)


async def h_kb_list(request):
    err = _gate(request, admin=True)
    if err:
        return err
    items = await asyncio.to_thread(_db.kb_all, False)
    return _jres({"ok": True, "items": items, "count": len(items)})


async def h_kb_save(request):
    err = _gate(request, admin=True)
    if err:
        return err
    b = await _body(request)
    if b is None:
        return _jres({"error": "bad_json"}, 400)
    if not (b.get("q_ar") and b.get("answer_ar")):
        return _jres({"error": "missing_fields"}, 400)
    links = [l for l in (b.get("links") or [])
             if isinstance(l, dict) and str(l.get("route", "")).startswith("#")]
    kid = await asyncio.to_thread(
        _db.kb_upsert, b["q_ar"], b["answer_ar"], links, b.get("tags") or "",
        "manual", b.get("id"))
    if kid is None:
        return _jres({"error": "not_found"}, 404)
    return _jres({"ok": True, "id": kid})


async def h_kb_toggle(request):
    err = _gate(request, admin=True)
    if err:
        return err
    b = await _body(request)
    if b is None:
        return _jres({"error": "bad_json"}, 400)
    await asyncio.to_thread(_db.kb_set_enabled, int(b.get("id") or 0), bool(b.get("enabled")))
    return _jres({"ok": True})


async def h_kb_delete(request):
    err = _gate(request, admin=True)
    if err:
        return err
    b = await _body(request)
    if b is None:
        return _jres({"error": "bad_json"}, 400)
    await asyncio.to_thread(_db.kb_delete, int(b.get("id") or 0))
    return _jres({"ok": True})


def register(app):
    app.router.add_post("/erp/api/finchat/ask", h_ask)
    app.router.add_get("/erp/api/finchat/history", h_history)
    app.router.add_post("/erp/api/finchat/escalate", h_escalate)
    app.router.add_get("/erp/api/finchat/inbox", h_inbox)
    app.router.add_post("/erp/api/finchat/inbox/answer", h_inbox_answer)
    app.router.add_get("/erp/api/finchat/kb", h_kb_list)
    app.router.add_post("/erp/api/finchat/kb/save", h_kb_save)
    app.router.add_post("/erp/api/finchat/kb/toggle", h_kb_toggle)
    app.router.add_post("/erp/api/finchat/kb/delete", h_kb_delete)
