# -*- coding: utf-8 -*-
"""
contracting.routes — the «المقاولات» dashboard tab's API. Every endpoint needs a dashboard
login (_safe) AND the «contr» tab permission (bot.py's role middleware). Writes also need
role admin/ops (re-checked here, like decor and oncall).

  GET  /contracting/static/contracting_tab.js   PUBLIC code, no data (the tab script)
  GET  /api/contr/board      everything the tab shows, in one call
  POST /api/contr/new        a draft from pasted quote lines
  POST /api/contr/save       a draft's header + each line's date
  POST /api/contr/start      THE GATE — refused unless engine.start_check passes
  POST /api/contr/due        move one line's date on a running project (logged)
  POST /api/contr/people     a team member's Discord id / role
  POST /api/contr/delete     drop a draft (never a running project)
  POST /api/contr/retry      try opening a project's Discord channel again
"""

import os
import traceback

from . import db, engine, notify, seed
from .host import HOST

EDIT_ROLES = ("admin", "ops")
ROLES = ("site", "lead", "boss", "account")
STATIC_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "contracting_tab.js")
_js_cache = {"mtime": None, "text": ""}


def can_edit(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in EDIT_ROLES
    except Exception:
        return False


def _actor(request):
    try:
        return (HOST.actor(request) if HOST.actor else "") or "غير معروف"
    except Exception:
        return "غير معروف"


def _json(data, status=200):
    return HOST.json_response(data, status)


async def _run(fn, *a, **kw):
    return await HOST.web_thread(fn, *a, **kw)


def _safe(fn):
    async def _w(request):
        if not HOST.dash_auth(request):
            return _json({"ok": False, "error": "unauthorized"}, 401)
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return _json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _deny():
    return _json({"ok": False, "error": "غير مصرّح لك بالتعديل"}, 403)


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


# ---------------------------------------------------------------- the board

def _project_view(p, today):
    h = engine.health(p["items"], today)
    return dict(p, health={"done": h["done"], "total": h["total"], "state": h["state"],
                           "late": [i["id"] for i in h["late"]],
                           "next": h["next"]["id"] if h["next"] else None},
                gate=engine.start_check(p, [i for i in p["items"] if not i["is_handover"]]),
                problems=engine.order_problems(p["items"]),
                channel_name=notify.channel_name(p))


def board_payload():
    seed.seed_if_empty()
    today = notify.local_now().date()
    people = []
    for x in db.people():
        own = bool(x.get("did"))
        found = own or bool(notify.did_for(x["name"]))
        people.append(dict(x, linked=found, linked_from=("typed" if own else ("ops" if found else ""))))
    return {"ok": True, "dryrun": notify.dryrun(), "enabled": notify.enabled(),
            "category": notify.category_name(), "admin_channel": notify.admin_channel_name(),
            "today": today.isoformat(),
            "projects": [_project_view(p, today) for p in db.projects()],
            "people": people, "log": db.sent_log(60), "photos_needed": db.PHOTOS_NEEDED}


async def api_board(request):
    return _json(await _run(board_payload))


# ---------------------------------------------------------------- writes

def _new(b, by):
    title = str(b.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "اكتب اسم المشروع"}
    lines = engine.parse_lines(b.get("lines") or "")
    if not lines:
        return {"ok": False, "error": "الصق بنود عرض السعر — كل بند بسطر، والمبلغ آخر السطر"}
    try:
        total = float(str(b.get("total_sar") or "").replace(",", "")) if b.get("total_sar") else None
    except ValueError:
        total = None
    p = db.create_project(title, lines, by=by, owner=str(b.get("owner") or "").strip(),
                          unit=str(b.get("unit") or "").strip(), total_sar=total,
                          signed=0, paid=0, source="لصق من عرض السعر")
    return {"ok": True, "id": p["id"]}


async def api_new(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _json(await _run(_new, b, _actor(request)))


def _save(b, by):
    pid = str(b.get("id") or "")
    fields = {k: b[k] for k in db.DRAFT_FIELDS if k in b}
    dues = b.get("dues") if isinstance(b.get("dues"), dict) else {}
    today = notify.local_now().date()
    for iid, v in list(dues.items()):
        if v and not engine.parse_date(v, today):
            return {"ok": False, "error": "تاريخ مو مفهوم"}
        dues[iid] = engine.parse_date(v, today) if v else ""
    p, err = db.save_draft(pid, fields, dues, by)
    return {"ok": bool(p), "error": err}


async def api_save(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _json(await _run(_save, b, _actor(request)))


def _start(pid, by):
    p = db.project(pid)
    if not p:
        return {"ok": False, "error": "المشروع مو موجود"}
    if p["status"] != "draft":
        return {"ok": False, "error": "المشروع بادي من قبل"}
    gate = engine.start_check(p, [i for i in p["items"] if not i["is_handover"]])
    probs = engine.order_problems(p["items"])
    if probs and gate["ok"]:
        gate = {"ok": False, "why": ["ترتيب التواريخ"]}
    if not gate["ok"]:
        return {"ok": False, "error": "ما يبدأ لين: " + "، ".join(gate["why"]), "why": gate["why"]}
    started = notify.local_now().isoformat(timespec="seconds")
    if not db.start_project(pid, by, started):
        return {"ok": False, "error": "ما قدرت أبدأه — حدّث الصفحة"}
    opened = notify.kick_open(pid)
    return {"ok": True, "dryrun": notify.dryrun(), "opening": opened}


async def api_start(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _json(await _run(_start, str(b.get("id") or ""), _actor(request)))


def _due(b, by):
    it = db.item(str(b.get("item_id") or ""))
    if not it:
        return {"ok": False, "error": "ما لقيت البند"}
    p = db.project(it["project_id"], with_items=False)
    if p["status"] == "draft":
        return {"ok": False, "error": "المشروع لسا ما بدأ — احفظ من الشاشة"}
    if it["status"] == "done":
        return {"ok": False, "error": "البند خالص"}
    today = notify.local_now().date()
    nd = engine.parse_date(b.get("due"), today)
    err = engine.check_new_due(nd, today) if nd else "تاريخ مو مفهوم"
    if err:
        return {"ok": False, "error": err}
    db.set_due(it["id"], nd, by, str(b.get("reason") or "تعديل من الداشبورد")[:200])
    return {"ok": True, "due": nd}


async def api_due(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _json(await _run(_due, b, _actor(request)))


def _people(b, by):
    name = str(b.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "اكتب الاسم"}
    role = b.get("role") if b.get("role") in ROLES else None
    did = b.get("did")
    if did is not None:
        did = "".join(ch for ch in str(did) if ch.isdigit())
        if did and not (15 <= len(did) <= 21):
            return {"ok": False, "error": "رقم ديسكورد غلط — انسخه من «Copy User ID»"}
    return {"ok": True, "person": db.set_person(name, role, did, by)}


async def api_people(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _json(await _run(_people, b, _actor(request)))


async def api_delete(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    ok = await _run(db.delete_draft, str(b.get("id") or ""), _actor(request))
    return _json({"ok": ok, "error": "" if ok else "ينحذف المشروع قبل ما يبدأ بس"})


async def api_retry(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    sent = await _run(notify.retry_open, str(b.get("id") or ""))
    return _json({"ok": True, "sent": sent, "dryrun": notify.dryrun()})


# ---------------------------------------------------------------- the tab script

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


async def handle_static_js(request):
    text = await _run(_js_text)
    return HOST.web.Response(text=text, content_type="application/javascript",
                             headers={"Cache-Control": "no-cache"})


def register_routes(app):
    g, p = app.router.add_get, app.router.add_post
    g("/contracting/static/contracting_tab.js", handle_static_js)
    g("/api/contr/board", _safe(api_board))
    p("/api/contr/new", _safe(api_new))
    p("/api/contr/save", _safe(api_save))
    p("/api/contr/start", _safe(api_start))
    p("/api/contr/due", _safe(api_due))
    p("/api/contr/people", _safe(api_people))
    p("/api/contr/delete", _safe(api_delete))
    p("/api/contr/retry", _safe(api_retry))
