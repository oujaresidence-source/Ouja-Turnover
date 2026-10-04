# -*- coding: utf-8 -*-
"""
oncall.routes — «المناوبة» endpoints.

    GET  /oncall/static/oncall_tab.js   PUBLIC code, no data (the dashboard tab)
    GET  /api/oncall/state              login + «oncall» read (bot.py _ROLE_READ_RULES)
    POST /api/oncall/slot               reassign a slot (reason required)
    POST /api/oncall/rebuild            redistribute a night (only before its first check)
    POST /api/oncall/switch             master ON/OFF
    POST /api/oncall/settings           roster + supervisor
Every write: login + «oncall» write (bot.py _ROLE_WRITE_RULES) AND role in admin/ops here.
There is deliberately NO endpoint that issues, voids or forgives a warning — forgiveness is
ops' appeal flow at /compliance, unchanged.
"""

import datetime
import json
import os
import traceback

from . import db, engine, notify, roster, texts
from .host import HOST

EDIT_ROLES = ("admin", "ops")
STATIC_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "oncall_tab.js")
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
        return await request.json()
    except Exception:
        return {}


# ------------------------------------------------------------------ the state

def _night_view(d):
    di = d.isoformat()
    n = db.night(di)
    if not n:
        return {"date": di, "label": texts.day_label(d), "status": "none", "slots": [],
                "unavailable": [], "rebuildable": False}
    try:
        roster_rows = json.loads(n.get("roster_json") or "[]")
    except Exception:
        roster_rows = []
    checks = db.checks_on(di)
    slots = []
    for s in db.slots_for(di):
        mine = [c for c in checks if c["slot_id"] == s["id"]]
        slots.append({"id": s["id"], "employee": s["employee"], "linked": bool(s["employee_did"]),
                      "from": engine.hm(s["start_min"]), "to": engine.hm(s["end_min"]),
                      "source": s["source"], "edited_by": s["edited_by"] or "",
                      "edit_reason": s["edit_reason"] or "",
                      "answered": sum(1 for c in mine if c["status"] == "answered"),
                      "missed": sum(1 for c in mine if c["status"] in ("missed", "late")),
                      "voided": sum(1 for c in mine if c["status"] == "voided")})
    return {"date": di, "label": texts.day_label(d), "status": n["status"], "slots": slots,
            "unavailable": [r for r in roster_rows if not r.get("ok")],
            "rebuildable": not checks}


def state_payload(now):
    today = now.date()
    cur = notify.owner_now(now)
    nd, m = engine.night_minute(now)
    on_now = None
    if cur:
        last = db.last_answered(cur["employee"], cur["date"])
        nxt = next((x for x in engine.check_minutes(cur["start_min"], cur["end_min"]) if x > m), None)
        on_now = {"employee": cur["employee"], "from": engine.hm(cur["start_min"]),
                  "to": engine.hm(cur["end_min"]),
                  "last_answered": (last or {}).get("answered_at") or "",
                  "next_check": engine.hm(nxt) if nxt is not None else ""}
    sup = roster.supervisor()
    issues = []
    for i in db.open_issues() + [x for x in db.recent_issues(30) if x["resolved_at"]]:
        issues.append({"kind": i["kind"], "title": i["title"] or "", "owner": i["owner"],
                       "helper": i["helper"] or "", "opened_at": i["opened_at"],
                       "claimed_at": i["claimed_at"] or "", "resolved_at": i["resolved_at"] or "",
                       "resolved_by": i["resolved_by"] or ""})
    problems = [{"employee": c["employee"], "date": c["date"], "due_at": c["due_at"],
                 "status": c["status"], "void_reason": c["void_reason"] or ""}
                for c in db.recent_problems(60)]
    warnings = [{"employee": e["employee"], "at": e["at"], "detail": e["detail"]}
                for e in db.events("warning", 30)]
    return {"ok": True, "enabled": notify.enabled(), "in_window": nd is not None,
            "now": on_now,
            "tonight": _night_view(today),
            "tomorrow": _night_view(today + datetime.timedelta(days=1)),
            "issues": issues, "problems": problems, "warnings": warnings,
            "settings": {"roster": roster.roster_names(), "supervisor_name": sup["name"],
                         "first_slot": roster.first_slot(),
                         "supervisor_linked": bool(sup["did"]),
                         "supervisor_did": db.config_get("supervisor_did", ""),
                         "every_min": engine.CHECK_EVERY_MIN,
                         "window_min": engine.ANSWER_WINDOW_MIN,
                         "channel": notify.channel_name()},
            "availability_tomorrow": roster.availability(today + datetime.timedelta(days=1))}


async def api_state(request):
    now = HOST.now()
    data = await _run(state_payload, now)
    data["can_edit"] = can_edit(request)
    return _json(data)


async def api_slot(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    ok, err = await _run(notify.edit_slot, int(b.get("slot_id") or 0),
                         (b.get("employee") or "").strip(), _actor(request),
                         (b.get("reason") or "").strip())
    return _json({"ok": ok, "error": err})


async def api_rebuild(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    ok, err = await _run(notify.rebuild_night, str(b.get("date") or ""), _actor(request))
    return _json({"ok": ok, "error": err})


async def api_switch(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    await _run(notify.set_enabled, bool(b.get("on")), _actor(request), HOST.now())
    return _json({"ok": True, "enabled": bool(b.get("on"))})


def _save_settings(b, by, now):
    if "roster" in b:
        names = [str(n).strip() for n in (b.get("roster") or []) if str(n).strip()]
        if not names:
            return False, "لازم يبقى شخص واحد على الأقل في المناوبة."
        db.config_set("roster", json.dumps(names, ensure_ascii=False), by, db.iso(now))
    if "first_slot" in b:
        name = str(b.get("first_slot") or "").strip()
        if name and not any(engine.same_person(name, r) for r in roster.roster_names()):
            return False, "الاسم مو من فريق المناوبة."
        db.config_set("first_slot", name, by, db.iso(now))
    if "supervisor_did" in b:
        did = "".join(ch for ch in str(b.get("supervisor_did") or "") if ch.isdigit())
        db.config_set("supervisor_did", did, by, db.iso(now))
    db.log("settings", now, by, {k: b.get(k) for k in ("roster", "supervisor_did", "first_slot")
                                 if k in b})
    return True, ""


async def api_settings(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    ok, err = await _run(_save_settings, b, _actor(request), HOST.now())
    return _json({"ok": ok, "error": err})


# ------------------------------------------------------------------ the tab script

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
    g("/oncall/static/oncall_tab.js", handle_static_js)
    g("/api/oncall/state", _safe(api_state))
    p("/api/oncall/slot", _safe(api_slot))
    p("/api/oncall/rebuild", _safe(api_rebuild))
    p("/api/oncall/switch", _safe(api_switch))
    p("/api/oncall/settings", _safe(api_settings))
