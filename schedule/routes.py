# -*- coding: utf-8 -*-
"""
schedule.routes — aiohttp handlers for the Employee Schedule & Coverage Calendar (build spec
§2/§6/§8). Reads need dash auth; every WRITE re-checks canEditSchedule (admin/ops). The board
comes from the pure schedule.engine so the dashboard tab, the standalone /team-calendar page,
and notifications all show identical numbers.
"""

import datetime
import traceback

from . import db, engine, seed, notify, page
from .host import HOST

# Editing is gated on the existing multi-user roles (build spec §2). admin/ops may edit; every
# other authenticated user is a viewer. Documented in the README section.
EDIT_ROLES = ("admin", "ops")
ABSENCE_TYPES = ("sick", "vacation", "emergency", "half_day", "late", "training", "no_show", "unpaid")
_DAY_AR = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]


def can_edit_schedule(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in EDIT_ROLES
    except Exception:
        return False


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def _deny():
    return HOST.json_response({"ok": False, "error": "غير مصرّح لك بالتعديل"}, 403)


def _safe(fn):
    """Auth-required wrapper: needs a valid dashboard/session token (used for manage + writes)."""
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


def _safe_public(fn):
    """PUBLIC read wrapper — NO auth. Used ONLY for the read-only day/week endpoints the shared
    /team-calendar link calls (no login, no token). These never write and always report
    can_edit=False for anonymous callers, so the share link is strictly view-only."""
    async def _w(request):
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _today_iso():
    try:
        return HOST.now().date().isoformat()
    except Exception:
        return datetime.date.today().isoformat()


# ---------------- shared compute (single source) ----------------

def schedule_day(date_iso):
    emps = db.employees()
    apts = db.apartments()
    ovs = db.overrides()
    absent_ids = {a["employee_id"] for a in db.absences_on(date_iso)}
    wd = engine.to_weekday(date_iso)
    r = engine.compute_day(wd, emps, apts, ovs, absent_ids=absent_ids)
    r["date"] = date_iso
    r["weekday_ar"] = _DAY_AR[wd]
    return r


def schedule_week():
    emps = db.employees()
    apts = db.apartments()
    ovs = db.overrides()
    base = {}
    for a in apts:
        base[a.get("owner_id")] = base.get(a.get("owner_id"), 0) + 1
    rows = []
    for wd in range(7):
        r = engine.compute_day(wd, emps, apts, ovs)
        cells = {}
        for w in r["working"]:
            cells[w["id"]] = {"load": w["load"], "base": len(w["own"]),
                              "cov": len(w["coverage"]), "off": False}
        for o in r["off"]:
            cells[o["id"]] = {"load": 0, "base": base.get(o["id"], 0), "cov": 0, "off": True}
        rows.append({"weekday": wd, "weekday_ar": _DAY_AR[wd],
                     "has_coverage": r["has_coverage"], "cells": cells})
    cols = [{"id": e["id"], "name": e["name"], "color": e.get("color"),
             "sort_order": e.get("sort_order", 0)} for e in emps]
    return {"columns": cols, "rows": rows, "today": engine.to_weekday(_today_iso())}


# ---------------- reads ----------------

async def api_day(request):
    qd = request.query.get("date")
    if not qd:
        wd = request.query.get("weekday")
        date_iso = _today_iso()
        if wd is not None:
            # map a requested weekday onto the nearest date that lands on it (display only)
            try:
                want = int(wd)
                base = datetime.date.fromisoformat(_today_iso())
                for i in range(7):
                    d = base + datetime.timedelta(days=i)
                    if engine.to_weekday(d) == want:
                        date_iso = d.isoformat()
                        break
            except Exception:
                pass
    else:
        date_iso = qd[:10]
    try:
        datetime.date.fromisoformat(date_iso)
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad date"}, 200)
    s = db.settings() or {}
    return HOST.json_response({"ok": True, "day": schedule_day(date_iso),
                               "can_edit": can_edit_schedule(request),
                               "title": s.get("title"), "subtitle": s.get("subtitle")})


async def api_week(request):
    return HOST.json_response({"ok": True, "week": schedule_week(),
                               "can_edit": can_edit_schedule(request)})


async def api_manage(request):
    """Everything the editor UI needs in one shot."""
    return HOST.json_response({
        "ok": True, "can_edit": can_edit_schedule(request),
        "employees": db.employees(), "apartments": db.apartments(),
        "overrides": db.overrides(), "settings": db.settings() or {},
        "day_names": _DAY_AR,
    })


# ---------------- employee CRUD ----------------

async def api_employee_save(request):
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    name = (b.get("name") or "").strip()
    if not name:
        return HOST.json_response({"ok": False, "error": "الاسم مطلوب"}, 200)
    off_day = b.get("off_day")
    off_day = int(off_day) if off_day not in (None, "") else None
    color = b.get("color") or "#6A3A5D"
    sort_order = int(b.get("sort_order") or 0)
    eid = b.get("id")
    if eid:
        db.execute("UPDATE schedule_employees SET name=?,off_day=?,color=?,sort_order=? WHERE id=?",
                   (name, off_day, color, sort_order, int(eid)))
    else:
        eid = db.execute("INSERT INTO schedule_employees(name,off_day,color,sort_order,created_at) "
                         "VALUES(?,?,?,?,?)", (name, off_day, color, sort_order, db.now_iso()))
    return HOST.json_response({"ok": True, "id": eid})


async def api_employee_delete(request):
    if not can_edit_schedule(request):
        return _deny()
    try:
        eid = int(request.match_info.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    owned = db.q1("SELECT COUNT(*) n FROM schedule_apartments WHERE owner_id=?", (eid,))
    if owned and owned["n"]:
        return HOST.json_response(
            {"ok": False, "error": "لا يمكن حذف موظف يملك شققاً (%d). أعد تعيين شققه أولاً." % owned["n"]}, 200)
    db.execute("DELETE FROM schedule_coverage_overrides WHERE covering_employee_id=?", (eid,))
    db.execute("DELETE FROM schedule_absences WHERE employee_id=?", (eid,))
    db.execute("DELETE FROM schedule_employees WHERE id=?", (eid,))
    return HOST.json_response({"ok": True, "deleted": 1})


# ---------------- apartment CRUD ----------------

async def api_apartment_save(request):
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    name = (b.get("name") or "").strip()
    if not name:
        return HOST.json_response({"ok": False, "error": "اسم الشقة مطلوب"}, 200)
    owner_id = b.get("owner_id")
    owner_id = int(owner_id) if owner_id not in (None, "") else None
    if owner_id and not db.q1("SELECT id FROM schedule_employees WHERE id=?", (owner_id,)):
        return HOST.json_response({"ok": False, "error": "موظف غير معروف"}, 200)
    sort_order = int(b.get("sort_order") or 0)
    aid = b.get("id")
    if aid:
        db.execute("UPDATE schedule_apartments SET name=?,owner_id=?,sort_order=? WHERE id=?",
                   (name, owner_id, sort_order, int(aid)))
    else:
        aid = db.execute("INSERT INTO schedule_apartments(name,owner_id,sort_order,created_at) "
                         "VALUES(?,?,?,?)", (name, owner_id, sort_order, db.now_iso()))
    return HOST.json_response({"ok": True, "id": aid})


async def api_apartment_delete(request):
    if not can_edit_schedule(request):
        return _deny()
    try:
        aid = int(request.match_info.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    db.execute("DELETE FROM schedule_coverage_overrides WHERE apartment_id=?", (aid,))  # cascade
    db.execute("DELETE FROM schedule_apartments WHERE id=?", (aid,))
    return HOST.json_response({"ok": True, "deleted": 1})


# ---------------- coverage override (recurring per weekday) ----------------

async def api_override_set(request):
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    try:
        dow = int(b.get("day_of_week"))
        apt = int(b.get("apartment_id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "day_of_week + apartment_id required"}, 200)
    cov = b.get("covering_employee_id")
    if cov in (None, "", 0):
        # "إرجاع للتلقائي" — clear any override for this (day, apartment)
        db.execute("DELETE FROM schedule_coverage_overrides WHERE day_of_week=? AND apartment_id=?",
                   (dow, apt))
        return HOST.json_response({"ok": True, "cleared": True})
    cov = int(cov)
    db.execute(
        "INSERT INTO schedule_coverage_overrides(day_of_week,apartment_id,covering_employee_id,created_at) "
        "VALUES(?,?,?,?) ON CONFLICT(day_of_week,apartment_id) DO UPDATE SET covering_employee_id=excluded.covering_employee_id",
        (dow, apt, cov, db.now_iso()))
    return HOST.json_response({"ok": True})


# ---------------- ad-hoc leave (Ouja extension) ----------------

async def api_absence_add(request):
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    try:
        emp = int(b.get("employee_id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "employee_id required"}, 200)
    start = (b.get("start_date") or _today_iso())[:10]
    end = (b.get("end_date") or start)[:10]
    typ = b.get("type") or "sick"
    if typ not in ABSENCE_TYPES:
        return HOST.json_response({"ok": False, "error": "نوع غير صحيح"}, 200)
    if end < start:
        return HOST.json_response({"ok": False, "error": "تاريخ النهاية قبل البداية"}, 200)
    if db.q1("SELECT id FROM schedule_absences WHERE employee_id=? AND status='approved' "
             "AND start_date<=? AND end_date>=?", (emp, end, start)):
        return HOST.json_response({"ok": False, "error": "الموظف مسجّل إجازة في هذه الفترة"}, 200)
    aid = db.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,note,created_by,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?)",
                     (emp, start, end, typ, "approved", b.get("note"), "editor", db.now_iso()))
    return HOST.json_response({"ok": True, "id": aid})


async def api_absence_del(request):
    if not can_edit_schedule(request):
        return _deny()
    try:
        aid = int(request.match_info.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    db.execute("DELETE FROM schedule_absences WHERE id=?", (aid,))
    return HOST.json_response({"ok": True, "deleted": 1})


# ---------------- settings + reset ----------------

async def api_settings_set(request):
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    db.execute("INSERT OR REPLACE INTO schedule_settings(id,title,subtitle) VALUES(1,?,?)",
               (b.get("title"), b.get("subtitle")))
    return HOST.json_response({"ok": True})


async def api_reset(request):
    if not can_edit_schedule(request):
        return _deny()
    return HOST.json_response({"ok": True, "report": seed.reset_to_default()})


# ---------------- standalone page ----------------

async def handle_page(request):
    return HOST.web.Response(text=page.SCHEDULE_PAGE_HTML, content_type="text/html")


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    # READ-ONLY + PUBLIC: the shared /team-calendar link calls these with no login/token.
    g("/api/schedule/day", _safe_public(api_day))
    g("/api/schedule/week", _safe_public(api_week))
    # manage = editor data (employee/apartment lists) -> stays behind login.
    g("/api/schedule/manage", _safe(api_manage))
    p("/api/schedule/employee", _safe(api_employee_save))
    app.router.add_delete("/api/schedule/employee/{id}", _safe(api_employee_delete))
    p("/api/schedule/apartment", _safe(api_apartment_save))
    app.router.add_delete("/api/schedule/apartment/{id}", _safe(api_apartment_delete))
    p("/api/schedule/override", _safe(api_override_set))
    p("/api/schedule/absence", _safe(api_absence_add))
    app.router.add_delete("/api/schedule/absence/{id}", _safe(api_absence_del))
    p("/api/schedule/settings", _safe(api_settings_set))
    p("/api/schedule/reset", _safe(api_reset))
    g("/team-calendar", handle_page)
