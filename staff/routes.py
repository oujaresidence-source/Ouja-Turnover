# -*- coding: utf-8 -*-
"""
staff.routes — «عوجا فريق», the employees' phone app.

    GET /team                       the app (HTML shell; the data below is what is gated)
    GET /team/manifest.webmanifest  its own install identity (separate from /dashboard)
    GET /api/staff/today            ONE employee's day — login required

Who sees what (owner decision 2026-11-17: no extra permission box):
    * a login linked to an employee («مين هو مين» in «أهدافي») sees ONLY that employee's
      apartments, tasks and week, plus who is working today;
    * an unlinked login sees nothing but a note telling them to ask the manager;
    * admin / the ops manager may look «كأنه» any employee (?as=);
    * supervisor extras (photos to review, Musaed replies, escalations) appear only for admin,
      the manager, or a login that may already write on those pages — and they only LINK to
      the dashboard page that does the job, which checks the permission again.

Read-only: this package writes nothing. The one action in the app (opening a maintenance
ticket) posts to the existing /api/tickets/create, which the role middleware gates on the
«tickets» create permission.
"""

import json
import traceback

from . import engine, page
from .gather import gather
from .host import HOST

_NO_STORE = {"Cache-Control": "no-store"}


def _json(data, status=200):
    resp = HOST.json_response(data, status)
    try:
        resp.headers.update(_NO_STORE)
    except Exception:
        pass
    return resp


def _role(request):
    return HOST.call("req_role", "", request) or ""


def _can(request, tab, action):
    return bool(HOST.call("can", False, request, tab, action))


def is_admin(request):
    return _role(request) == "admin"


def can_view_as(request):
    return is_admin(request) or bool(HOST.call("is_manager", False, request))


def is_supervisor(request):
    if can_view_as(request):
        return True
    return _can(request, "clean_center", "write") or _can(request, "inbox", "write")


def _names(day):
    out = []
    for w in (day or {}).get("working") or []:
        out.append(w.get("name") or "")
    for o in (day or {}).get("off") or []:
        out.append(o.get("name") or "")
    return [n for n in out if n]


def resolve_employee(request, names):
    """(employee, viewing_as). ?as= is honoured only for admin / the manager, and only for a
    real employee name — anyone else always gets their own link."""
    asked = (request.query.get("as") or "").strip()
    if asked and can_view_as(request) and asked in names:
        return asked, True
    return (HOST.call("employee_of", "", request) or ""), False


def build_payload(request, g, today_iso, now_iso):
    day = g.get("day") or {}
    names = _names(day)
    emp, viewing_as = resolve_employee(request, names)
    role = _role(request)
    perms = {
        "ticket_create": _can(request, "tickets", "create"),
        "targets": bool(HOST.call("has_targets", False)) and _can(request, "targets", "read"),
        "book": bool(HOST.call("has_targets", False)) and _can(request, "book", "read"),
        "dashboard": role in ("admin", "ops"),
        "photos": role in ("admin", "ops"),
        "view_as": can_view_as(request),
    }
    me = {"name": HOST.call("actor", "", request) or "", "role": role}
    base = {"ok": True, "me": me, "perms": perms, "viewing_as": viewing_as,
            "employees": names if perms["view_as"] else [],
            "snap_age_min": g.get("snap_age_min"), "today": today_iso,
            # a source that failed is NAMED, so an empty list never passes for «nothing to do»
            "missing": [k for k in ("day", "tickets", "promises", "cleaning") if k not in g],
            "team": engine.team(day, emp), "weekday_ar": day.get("weekday_ar") or "",
            "oncall": {"now": (g.get("oncall") or {}).get("now"),
                       "tonight": list((g.get("oncall") or {}).get("tonight") or [])}}
    if not emp:
        base["status"] = "pick" if perms["view_as"] else "unlinked"
        return base
    out = engine.build_today(emp, day, g.get("snap"), g.get("tickets"), g.get("promises"),
                             g.get("cleaning"), g.get("oncall"), today_iso, now_iso,
                             g.get("name_to_lid"))
    out.update(base)
    out["status"] = out.get("status") or "unknown"
    out["week"] = engine.my_week(g.get("week_days") or [], emp)
    out["supervisor"] = (engine.supervisor_items(g.get("reviews"), g.get("replies"),
                                                 g.get("escalations"))
                         if is_supervisor(request) else [])
    return out


async def api_today(request):
    if not HOST.dash_auth(request):
        return _json({"ok": False, "error": "unauthorized"}, 401)
    try:
        today = HOST.today_iso()
        now = HOST.now_iso()
        g = await HOST.web_thread(gather, today)
        return _json(build_payload(request, g or {}, today, now))
    except Exception as e:
        traceback.print_exc()
        return _json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)


async def handle_page(request):
    return HOST.web.Response(text=page.HTML, content_type="text/html", charset="utf-8",
                             headers={"Cache-Control": "no-cache"})


MANIFEST = {
    "id": "/team",
    "name": "عوجا فريق",
    "short_name": "عوجا فريق",
    "description": "يومك في عوجا: شققك، مهامك، والفريق.",
    "lang": "ar",
    "dir": "rtl",
    "start_url": "/team",
    "scope": "/team",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#F4EFE7",
    "theme_color": "#F4EFE7",
    "icons": [
        {"src": "/pwa/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/pwa/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/pwa/icons/icon-maskable-192.png", "sizes": "192x192", "type": "image/png",
         "purpose": "maskable"},
        {"src": "/pwa/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "maskable"},
    ],
}


async def handle_manifest(request):
    return HOST.web.Response(text=json.dumps(MANIFEST, ensure_ascii=False),
                             content_type="application/manifest+json", charset="utf-8",
                             headers={"Cache-Control": "no-cache"})


def register_routes(app):
    g = app.router.add_get
    g("/team", handle_page)
    g("/team/", handle_page)
    g("/team/manifest.webmanifest", handle_manifest)
    g("/api/staff/today", api_today)
