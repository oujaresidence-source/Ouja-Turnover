# -*- coding: utf-8 -*-
"""
schedule.routes — aiohttp handlers for the Employee Schedule & Coverage Calendar (build spec
§2/§6/§8). Reads need dash auth; every WRITE re-checks canEditSchedule (admin/ops). The board
comes from the pure schedule.engine so the dashboard tab, the standalone /team-calendar page,
and notifications all show identical numbers.
"""

import datetime
import re
import traceback

from . import db, engine, seed, notify, page, coverage, owners, period, workload
from .host import HOST

# Editing is gated on the existing multi-user roles (build spec §2). admin/ops may edit; every
# other authenticated user is a viewer. Documented in the README section.
EDIT_ROLES = ("admin", "ops")
ABSENCE_TYPES = ("sick", "vacation", "emergency", "half_day", "late", "training", "no_show", "unpaid")
# What the PLANNER is allowed to create. half_day / late / training are deliberately absent:
# the engine drops an absent person for the WHOLE day regardless of type, so recording a
# two-hour تأخير silently dumps that person's apartments on everyone else — and that error
# flows straight into the OujaCT Discord channel emojis. Owner's ruling (2026-08-18): do not
# offer a tool that is known to miscalculate. They come back in step 4 with a real capacity
# model. The legacy /api/schedule/absence endpoint still accepts all eight.
PLANNER_ABSENCE_TYPES = ("vacation", "sick", "emergency", "unpaid", "half_day")
# Approval is per TYPE (owner, 2026-08-18): nobody requests being ill in advance. Sick and
# emergency (and a same-day no-show) take effect the moment ops records them — the owner is
# told and can reverse it. Annual and unpaid wait for the owner.
NEEDS_OWNER_TYPES = ("vacation", "unpaid")
DECIDE_ROLES = ("admin",)
HALF_DAY_SHIFTS = ("morning", "evening")
ABSENCE_LABEL_AR = {"vacation": "إجازة سنوية", "sick": "مرضية", "emergency": "طارئة",
                    "no_show": "غياب بدون إذن", "unpaid": "بدون راتب", "half_day": "نصف يوم",
                    "late": "تأخير", "training": "تدريب"}
SHIFT_LABEL_AR = {"morning": "صباحي (ما يلحق التنظيف)", "evening": "مسائي (يلحق التنظيف)"}
SHIFT_LABEL_EN = {"morning": "Morning (misses the cleaning)",
                  "evening": "Evening (covers the cleaning)"}
ABSENCE_LABEL_EN = {"vacation": "Annual leave", "sick": "Sick", "emergency": "Emergency",
                    "no_show": "No-show", "unpaid": "Unpaid", "half_day": "Half day",
                    "late": "Late", "training": "Training"}
_DAY_AR = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]


def can_decide_leave(request):
    """Only the owner approves or reverses a leave."""
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in DECIDE_ROLES
    except Exception:
        return False


def _fire_change(dates=None):
    """Announce a coverage change so downstream caches drop it. Without this the ops
    attribution cache would keep blaming somebody who was recorded absent an hour ago."""
    fn = getattr(HOST, "on_change", None)
    if not fn:
        return
    try:
        fn(dates)
    except Exception:
        traceback.print_exc()


def _affects_coverage(typ, shift):
    """A half-day only takes somebody off the board when it is the MORNING one — every
    cleaning starts after the 12:00 checkout, so an evening half-day misses nothing."""
    if typ == "half_day":
        return 1 if shift == "morning" else 0
    return 1


def _status_for(typ, request):
    if can_decide_leave(request):
        return "approved"                     # the owner never waits for themselves
    return "pending" if typ in NEEDS_OWNER_TYPES else "approved"


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
        except Exception:
            traceback.print_exc()          # full detail stays in the server log only —
            return HOST.json_response(     # anonymous callers get a generic message
                {"ok": False, "error": "صار خطأ مؤقت — حدّث الصفحة وجرّب مرة ثانية"}, 200)
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

def schedule_day(date_iso, extra_absent=None, extra_date_overrides=None):
    """The ONE board every surface renders from.

    `extra_absent` / `extra_date_overrides` are the DRY-RUN inputs the period planner passes to
    ask "what would this look like" — they are never persisted here and default to nothing, so
    every existing caller behaves exactly as before."""
    emps = db.employees()
    apts = db.apartments()
    ovs = db.overrides()
    absent_ids = {a["employee_id"] for a in db.absences_on(date_iso)}
    if extra_absent:
        absent_ids |= set(extra_absent)
    dovs = db.date_overrides_on(date_iso)
    if extra_date_overrides:
        pinned = {d.get("apartment_id") for d in extra_date_overrides}
        dovs = [d for d in dovs if d.get("apartment_id") not in pinned] + list(extra_date_overrides)
    wd = engine.to_weekday(date_iso)
    r = engine.compute_day(wd, emps, apts, ovs, absent_ids=absent_ids, date_overrides=dovs)
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
    # M11: the weekly matrix must honor ad-hoc leave too — resolve each weekday
    # to its CONCRETE upcoming date (today..+6) and pass that date's absences,
    # exactly like schedule_day does. Without this the week view showed someone
    # working on their approved leave day.
    today = datetime.date.fromisoformat(_today_iso())
    date_for_wd = {}
    for i in range(7):
        d = today + datetime.timedelta(days=i)
        date_for_wd.setdefault(engine.to_weekday(d), d.isoformat())
    rows = []
    for wd in range(7):
        date_iso = date_for_wd.get(wd)
        absent_ids = ({a["employee_id"] for a in db.absences_on(date_iso)}
                      if date_iso else set())
        # Same M11 rule for date pins: the weekly matrix resolves each weekday to a CONCRETE
        # date, so it must read that date's pins or it will disagree with the Today tab.
        dovs = db.date_overrides_on(date_iso) if date_iso else []
        r = engine.compute_day(wd, emps, apts, ovs, absent_ids=absent_ids, date_overrides=dovs)
        cells = {}
        for w in r["working"]:
            cells[w["id"]] = {"load": w["load"], "base": len(w["own"]),
                              "cov": len(w["coverage"]), "off": False}
        for o in r["off"]:
            cells[o["id"]] = {"load": 0, "base": base.get(o["id"], 0), "cov": 0, "off": True}
        rows.append({"weekday": wd, "weekday_ar": _DAY_AR[wd], "date": date_iso,
                     "has_coverage": r["has_coverage"], "cells": cells})
    cols = [{"id": e["id"], "name": e["name"], "color": e.get("color"),
             "emoji": e.get("emoji"), "sort_order": e.get("sort_order", 0)} for e in emps]
    return {"columns": cols, "rows": rows, "today": engine.to_weekday(_today_iso()),
            "leave": _public_leave_strip(today)}


def _public_leave_strip(today, days=7):
    """«إجازات هذا الأسبوع» for the PUBLIC /team-calendar link.

    That URL needs no login and gets forwarded, so this carries NAME AND DATES ONLY. The type
    would announce «مرضية» about a real person and the note is where the actual reason is
    written — neither belongs on a link anyone can open. Today forward only; a pending request
    is not news yet, and an evening half-day is not an absence at all."""
    end = (today + datetime.timedelta(days=days - 1)).isoformat()
    start = today.isoformat()
    emps = {e["id"]: e for e in db.employees()}
    out = []
    for r in db.q("SELECT employee_id, start_date, end_date FROM schedule_absences "
                  "WHERE status='approved' AND COALESCE(affects_coverage,1)=1 "
                  "AND end_date>=? AND start_date<=? ORDER BY start_date", (start, end)):
        e = emps.get(r["employee_id"])
        if not e:
            continue
        out.append({"employee_id": e["id"], "name": e["name"], "color": e.get("color"),
                    "emoji": e.get("emoji"),
                    "start": max(r["start_date"], start), "end": r["end_date"]})
    return out


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


async def api_owners(request):
    """Permanent-owner snapshot (employees + apartment→owner). The weekly report's
    employee dropdown / auto-fill and any assignee default read THIS — one resolver
    (schedule.owners), one answer. Login-gated read; no role needed."""
    return HOST.json_response({"ok": True, **owners.permanent_map()})


def _hostaway_listings():
    """All Hostaway listings for the picker, best-effort (never raises). [] when unavailable."""
    try:
        return list(HOST.listings() or []) if HOST.listings else []
    except Exception:
        traceback.print_exc()
        return []


async def api_manage(request):
    """Everything the editor UI needs in one shot."""
    return HOST.json_response({
        "ok": True, "can_edit": can_edit_schedule(request),
        "employees": db.employees(), "apartments": db.apartments(),
        "overrides": db.overrides(), "settings": db.settings() or {},
        "hostaway": _hostaway_listings(),
        "day_names": _DAY_AR,
    })


async def api_hostaway_listings(request):
    """The Hostaway listing list for the picker (editor-only)."""
    if not can_edit_schedule(request):
        return _deny()
    linked = {int(a["listing_id"]): a["id"] for a in db.apartments()
              if a.get("listing_id") is not None}
    return HOST.json_response({"ok": True, "listings": _hostaway_listings(), "linked": linked})


# ---------------- employee CRUD ----------------

async def api_employee_save(request):
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    name = (b.get("name") or "").strip()
    if not name:
        return HOST.json_response({"ok": False, "error": "الاسم مطلوب"}, 200)
    off_day = b.get("off_day")
    try:
        off_day = int(off_day) if off_day not in (None, "") else None
    except (TypeError, ValueError):
        return HOST.json_response({"ok": False, "error": "يوم الإجازة غير صحيح"}, 200)
    if off_day is not None and not (0 <= off_day <= 6):
        return HOST.json_response({"ok": False, "error": "يوم الإجازة لازم يكون بين الأحد (0) والسبت (6)"}, 200)
    color = b.get("color") or "#6A3A5D"
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(color)):
        return HOST.json_response({"ok": False, "error": "اللون لازم يكون بصيغة ‎#RRGGBB"}, 200)
    emoji = (b.get("emoji") or "").strip()[:8] or None   # free-text marker; cap length, keep NULL when blank
    sort_order = int(b.get("sort_order") or 0)
    eid = b.get("id")
    if eid:
        db.execute("UPDATE schedule_employees SET name=?,off_day=?,color=?,emoji=?,sort_order=? WHERE id=?",
                   (name, off_day, color, emoji, sort_order, int(eid)))
    else:
        eid = db.execute("INSERT INTO schedule_employees(name,off_day,color,emoji,sort_order,created_at) "
                         "VALUES(?,?,?,?,?,?)", (name, off_day, color, emoji, sort_order, db.now_iso()))
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
    db.execute("DELETE FROM schedule_date_overrides WHERE covering_employee_id=?", (eid,))
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
    # listing_id is only touched when the caller actually sends it (so the plain owner/name save
    # from the apartment row never wipes an existing Hostaway link).
    has_lid = "listing_id" in b
    lid = b.get("listing_id")
    lid = int(lid) if lid not in (None, "", 0, "0") else None
    aid = b.get("id")
    if aid:
        if has_lid:
            db.execute("UPDATE schedule_apartments SET name=?,owner_id=?,sort_order=?,listing_id=? WHERE id=?",
                       (name, owner_id, sort_order, lid, int(aid)))
        else:
            db.execute("UPDATE schedule_apartments SET name=?,owner_id=?,sort_order=? WHERE id=?",
                       (name, owner_id, sort_order, int(aid)))
    else:
        aid = db.execute("INSERT INTO schedule_apartments(name,owner_id,listing_id,sort_order,created_at) "
                         "VALUES(?,?,?,?,?)", (name, owner_id, lid, sort_order, db.now_iso()))
    return HOST.json_response({"ok": True, "id": aid})


async def api_apartment_link(request):
    """Set/clear ONLY the Hostaway listing link for an apartment (no name/owner change). Pass
    listing_id null to unlink. Used by the picker on existing rows."""
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    try:
        aid = int(b.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "id required"}, 200)
    lid = b.get("listing_id")
    lid = int(lid) if lid not in (None, "", 0, "0") else None
    db.execute("UPDATE schedule_apartments SET listing_id=? WHERE id=?", (lid, aid))
    return HOST.json_response({"ok": True, "id": aid, "listing_id": lid})


def autolink_listings():
    """One-time best-effort: fill the Hostaway listing_id for apartments that don't have one yet,
    by name-matching against the Hostaway listing list. Only fills blanks — never overwrites an
    owner-set link. Returns a report. Safe to call repeatedly (idempotent once linked)."""
    listings = _hostaway_listings()
    if not listings:
        return {"linked": 0, "total": 0, "unmatched": 0, "skipped": "no_hostaway_listings"}
    apts = db.apartments()
    linked, unmatched = 0, 0
    for a in apts:
        if a.get("listing_id") is not None:
            continue
        lid = coverage.best_listing(a.get("name"), listings)
        if lid is not None:
            db.execute("UPDATE schedule_apartments SET listing_id=? WHERE id=?", (int(lid), a["id"]))
            linked += 1
        else:
            unmatched += 1
    return {"linked": linked, "total": len(apts), "unmatched": unmatched}


async def api_autolink(request):
    if not can_edit_schedule(request):
        return _deny()
    return HOST.json_response({"ok": True, "report": autolink_listings()})


async def api_apartment_owner(request):
    """Auto-save the cleaner for one apartment. {id, owner_id|null}. owner_id null = «بدون»
    (apartment joins the auto-distributed pool). Rejects an unknown employee."""
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    try:
        aid = int(b.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "id required"}, 200)
    owner_id = b.get("owner_id")
    owner_id = int(owner_id) if owner_id not in (None, "", 0, "0") else None
    if owner_id is not None and not db.q1("SELECT id FROM schedule_employees WHERE id=?", (owner_id,)):
        return HOST.json_response({"ok": False, "error": "موظف غير معروف"}, 200)
    db.execute("UPDATE schedule_apartments SET owner_id=? WHERE id=?", (owner_id, aid))
    return HOST.json_response({"ok": True, "id": aid, "owner_id": owner_id})


async def api_sync(request):
    """Hostaway-driven sync: add a schedule apartment for every Hostaway listing not already
    linked, and refresh the name of linked ones whose Hostaway name changed. Never deletes (keeps
    owner assignments). Returns {added, updated}."""
    if not can_edit_schedule(request):
        return _deny()
    listings = _hostaway_listings()
    if not listings:
        return HOST.json_response({"ok": False, "error": "تعذّر جلب قائمة Hostaway — حاول مرة ثانية"}, 200)
    by_lid = {int(a["listing_id"]): a for a in db.apartments() if a.get("listing_id") is not None}
    added, updated = 0, 0
    sort_at = len(db.apartments())
    for L in listings:
        lid = int(L["id"])
        name = L.get("name") or ("unit-" + str(lid))
        cur = by_lid.get(lid)
        if cur is None:
            db.execute("INSERT INTO schedule_apartments(name,owner_id,listing_id,sort_order,created_at) "
                       "VALUES(?,?,?,?,?)", (name, None, lid, sort_at, db.now_iso()))
            sort_at += 1
            added += 1
        elif (cur.get("name") or "") != name:
            db.execute("UPDATE schedule_apartments SET name=? WHERE id=?", (name, cur["id"]))
            updated += 1
    return HOST.json_response({"ok": True, "report": {"added": added, "updated": updated}})


async def api_remove_unlinked(request):
    """Delete apartments not backed by a Hostaway listing (the pre-Hostaway typed leftovers).
    Returns {removed}. Coverage overrides cascade with the apartment."""
    if not can_edit_schedule(request):
        return _deny()
    rows = db.q("SELECT id FROM schedule_apartments WHERE listing_id IS NULL")
    for r in rows:
        db.execute("DELETE FROM schedule_coverage_overrides WHERE apartment_id=?", (r["id"],))
        db.execute("DELETE FROM schedule_date_overrides WHERE apartment_id=?", (r["id"],))
        db.execute("DELETE FROM schedule_apartments WHERE id=?", (r["id"],))
    return HOST.json_response({"ok": True, "report": {"removed": len(rows)}})


async def api_import_all(request):
    """Bulk-create a schedule apartment for EVERY Hostaway listing not already linked to one
    (skips already-linked so re-running never duplicates). Owner is left blank — the editor
    assigns each one's employee afterwards. Pass {oujact_only:true} to limit to cleaning units."""
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)
    only_oujact = bool(b.get("oujact_only"))
    listings = _hostaway_listings()
    if not listings:
        return HOST.json_response({"ok": False, "error": "تعذّر جلب قائمة Hostaway — حاول مرة ثانية"}, 200)
    linked = {int(a["listing_id"]) for a in db.apartments() if a.get("listing_id") is not None}
    added, skipped = 0, 0
    sort_at = len(db.apartments())
    for L in listings:
        if only_oujact and not L.get("oujact"):
            continue
        lid = int(L["id"])
        if lid in linked:
            skipped += 1
            continue
        db.execute("INSERT INTO schedule_apartments(name,owner_id,listing_id,sort_order,created_at) "
                   "VALUES(?,?,?,?,?)", (L.get("name") or ("unit-" + str(lid)), None, lid, sort_at, db.now_iso()))
        linked.add(lid)
        sort_at += 1
        added += 1
    return HOST.json_response({"ok": True, "report": {"added": added, "skipped": skipped, "total": len(listings)}})


async def api_apartment_delete(request):
    if not can_edit_schedule(request):
        return _deny()
    try:
        aid = int(request.match_info.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    db.execute("DELETE FROM schedule_coverage_overrides WHERE apartment_id=?", (aid,))  # cascade
    db.execute("DELETE FROM schedule_date_overrides WHERE apartment_id=?", (aid,))
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
    try:
        datetime.date.fromisoformat(start)
        datetime.date.fromisoformat(end)
    except ValueError:
        return HOST.json_response({"ok": False, "error": "تاريخ غير صحيح — الصيغة YYYY-MM-DD"}, 200)
    typ = b.get("type") or "sick"
    if typ not in ABSENCE_TYPES:
        return HOST.json_response({"ok": False, "error": "نوع غير صحيح"}, 200)
    if end < start:
        return HOST.json_response({"ok": False, "error": "تاريخ النهاية قبل البداية"}, 200)
    if db.q1("SELECT id FROM schedule_absences WHERE employee_id=? AND status='approved' "
             "AND start_date<=? AND end_date>=?", (emp, end, start)):
        return HOST.json_response({"ok": False, "error": "الموظف مسجّل إجازة في هذه الفترة"}, 200)
    shift = b.get("shift") if typ == "half_day" else None
    if typ == "half_day" and shift not in HALF_DAY_SHIFTS:
        return HOST.json_response({"ok": False, "error": "حدّد نصف اليوم: صباحي أو مسائي"}, 200)
    affects = _affects_coverage(typ, shift)
    status = _status_for(typ, request)
    actor = _actor(request) or "editor"
    aid = db.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                     "note,created_by,created_at,shift,affects_coverage) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (emp, start, end, typ, status, b.get("note"), actor, db.now_iso(),
                      shift, affects))
    # A no-show recorded at 10am has to land NOW: the board is computed fresh on every read,
    # but downstream caches (ops attribution) must be told to drop the day.
    _fire_change([start, end])
    return HOST.json_response({"ok": True, "id": aid, "status": status,
                               "affects_coverage": bool(affects)})


async def api_absence_decide(request):
    """POST /api/schedule/absence-decide — the owner approves a pending request, or reverses
    a sick/emergency leave that ops applied immediately. Owner only."""
    if not can_decide_leave(request):
        return HOST.json_response(
            {"ok": False, "error": "الموافقة على الإجازات للمالك فقط"}, 403)
    b = await _body(request)
    try:
        aid = int(b.get("id"))
    except (TypeError, ValueError):
        return HOST.json_response({"ok": False, "error": "id required"}, 200)
    decision = b.get("decision")
    if decision not in ("approved", "rejected"):
        return HOST.json_response({"ok": False, "error": "القرار لازم يكون موافقة أو رفض"}, 200)
    row = db.q1("SELECT * FROM schedule_absences WHERE id=?", (aid,))
    if not row:
        return HOST.json_response({"ok": False, "error": "الإجازة غير موجودة"}, 200)
    db.execute("UPDATE schedule_absences SET status=?, decided_by=?, decided_at=?, "
               "decision_reason=? WHERE id=?",
               (decision, _actor(request) or "admin", db.now_iso(),
                (b.get("reason") or "")[:300], aid))
    _fire_change([row["start_date"], row["end_date"]])
    return HOST.json_response({"ok": True, "id": aid, "status": decision})


async def api_absence_del(request):
    if not can_edit_schedule(request):
        return _deny()
    try:
        aid = int(request.match_info.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    row = db.q1("SELECT start_date, end_date FROM schedule_absences WHERE id=?", (aid,))
    db.execute("DELETE FROM schedule_absences WHERE id=?", (aid,))
    if row:
        _fire_change([row["start_date"], row["end_date"]])
    return HOST.json_response({"ok": True, "deleted": 1})


# ---------------- PERIOD SIMULATION («مخطط الإجازات») ----------------
# "ناصر off 20-27 August" answered BEFORE it is saved. Every day is built by schedule_day(), so
# the preview can never disagree with the Today tab; the Hostaway pull happens ONCE for the whole
# window and degrades to apartment counts instead of failing.

_PERIOD_MAX_DAYS = 62
_CAPS_HISTORY_DAYS = 60


def _dates(start_iso, end_iso):
    d = datetime.date.fromisoformat(start_iso)
    end = datetime.date.fromisoformat(end_iso)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def _parse_sims(raw):
    """'EMP:START:END,EMP:START:END' -> [{employee_id, start, end, name}]. Raises ValueError."""
    sims = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) != 3:
            raise ValueError("simulate_absence must be EMP_ID:START:END")
        eid = int(parts[0])
        start, end = parts[1][:10], parts[2][:10]
        datetime.date.fromisoformat(start)
        datetime.date.fromisoformat(end)
        if end < start:
            raise ValueError("simulated leave ends before it starts")
        emp = db.q1("SELECT id, name FROM schedule_employees WHERE id=?", (eid,))
        if not emp:
            raise ValueError("unknown employee %d" % eid)
        sims.append({"employee_id": eid, "name": emp["name"], "start": start, "end": end})
    return sims


def _events_for(date_iso):
    fn = getattr(HOST, "events_for_date", None)
    if not fn:
        return []
    try:
        return [e.get("name") for e in (fn(date_iso) or []) if e.get("name")]
    except Exception:
        return []


def _enrich_day(day, date_iso, demand, unassigned):
    """Turn one coverage board into a workload board. Apartment counts stay, but the numbers
    that matter — real turnovers, same-day check-ins, estimated minutes — come from Hostaway."""
    outs = demand["checkouts"].get(date_iso) or set()
    ins = demand["checkins"].get(date_iso) or set()
    deep = demand["deep_cleans"].get(date_iso) or set()
    units, mdef = demand["units"], demand["minutes_default"]
    emps = []
    for w in day["working"]:
        apts = list(w["own"]) + [c["apartment"] for c in w["coverage"]]
        turns = mins = checkins = deeps = 0
        districts = []
        for a in apts:
            lid = a.get("listing_id")
            if lid is None:
                continue
            lid = int(lid)
            cfg = units.get(lid) or {}
            if lid in deep:
                deeps += 1
            if lid not in outs:
                continue                     # no checkout today = no cleaning today
            turns += 1
            mins += cfg.get("minutes") or mdef
            if cfg.get("district"):
                districts.append(cfg["district"])
            if lid in ins:
                checkins += 1                # same-day arrival — the urgent ones
        emps.append({"id": w["id"], "name": w["name"], "color": w.get("color"),
                     "emoji": w.get("emoji"), "sort_order": w.get("sort_order", 0),
                     "own": len(w["own"]), "coverage": len(w["coverage"]), "load": w["load"],
                     "real_turnovers": turns, "checkins": checkins, "deep_cleans": deeps,
                     "est_minutes": mins, "districts": sorted(set(districts))})
    return {"date": date_iso, "weekday_ar": day["weekday_ar"], "employees": emps,
            "off": [{"id": o["id"], "name": o["name"], "color": o.get("color"),
                     "emoji": o.get("emoji"), "reason": o.get("reason"),
                     "units": len(o.get("apartments") or [])} for o in day["off"]],
            "unassigned": unassigned,
            "skipped_date_overrides": day.get("skipped_date_overrides") or [],
            "total_turnovers": sum(e["real_turnovers"] for e in emps),
            "checkins": sum(e["checkins"] for e in emps),
            "balanced": day.get("balanced"),
            "events": _events_for(date_iso)}


def _unassigned_apartments():
    return [{"id": a["id"], "name": a.get("name")} for a in db.apartments()
            if a.get("owner_id") is None]


def build_period(start_iso, end_iso, sims=None, demand=None, caps=None,
                 extra_date_overrides=None):
    """The days of a window, enriched and risk-flagged, plus the rollup vs the normal week."""
    dates = _dates(start_iso, end_iso)
    demand = demand or workload.fetch_window(start_iso, end_iso)
    caps = caps if caps is not None else current_caps()
    unassigned = _unassigned_apartments()
    sims = sims or []
    edo = extra_date_overrides or {}

    def _absent_on(date_iso):
        return {s["employee_id"] for s in sims if s["start"] <= date_iso <= s["end"]}

    days, baseline = [], []
    for d in dates:
        plan_day = schedule_day(d, extra_absent=_absent_on(d),
                                extra_date_overrides=edo.get(d))
        days.append(_enrich_day(plan_day, d, demand, unassigned))
        if sims or edo:
            baseline.append(_enrich_day(schedule_day(d), d, demand, unassigned))
    if not (sims or edo):
        baseline = days

    period.mark_peaks(days)
    for d in days:
        d["risks"] = period.day_risks(d, caps)
    return {"start": start_iso, "end": end_iso, "count": len(dates),
            "demand_source": demand["source"], "caps": caps,
            "simulated": sims, "days": days,
            "rollup": period.summarize(days, baseline=baseline, caps=caps)}


# ---- overload caps: derived from THIS team's history, never guessed ----

def stored_caps():
    s = db.settings() or {}
    if s.get("max_minutes_per_day") or s.get("max_units_per_day"):
        return {"units": s.get("max_units_per_day"), "minutes": s.get("max_minutes_per_day"),
                "source": s.get("caps_source") or "manual",
                "computed_at": s.get("caps_computed_at")}
    return None


def compute_caps(days_back=_CAPS_HISTORY_DAYS, save=True):
    """The 90th percentile of what this team actually carried per person per day over the last
    `days_back` days. Refuses to answer from a degraded Hostaway pull — a cap computed from
    zeroes would flag every single day as an overload."""
    end = datetime.date.fromisoformat(_today_iso())
    start = end - datetime.timedelta(days=days_back)
    demand = workload.fetch_window(start.isoformat(), end.isoformat())
    if demand["source"] != "hostaway":
        return {"units": None, "minutes": None, "source": "unknown", "reason": "hostaway_down"}
    unassigned = _unassigned_apartments()
    hist = []
    for d in _dates(start.isoformat(), end.isoformat()):
        for e in _enrich_day(schedule_day(d), d, demand, unassigned)["employees"]:
            if e["real_turnovers"]:            # a day somebody actually worked
                hist.append({"units": e["load"], "minutes": e["est_minutes"]})
    caps = period.observed_caps(hist)
    if caps["source"] != "observed" or not caps.get("minutes"):
        return {"units": None, "minutes": None, "source": "unknown", "reason": "no_history"}
    if save:
        s = db.settings() or {}
        db.execute("INSERT OR REPLACE INTO schedule_settings(id,title,subtitle,"
                   "max_units_per_day,max_minutes_per_day,caps_source,caps_computed_at) "
                   "VALUES(1,?,?,?,?,?,?)",
                   (s.get("title"), s.get("subtitle"), caps["units"], caps["minutes"],
                    "observed", db.now_iso()))
        caps["computed_at"] = db.now_iso()
    return caps


def current_caps():
    """Stored caps, else derive them once from history. Unknown caps raise NO overload flag."""
    st = stored_caps()
    if st:
        return st
    try:
        return compute_caps()
    except Exception:
        traceback.print_exc()
        return {"units": None, "minutes": None, "source": "unknown", "reason": "error"}


async def api_period(request):
    """GET /api/schedule/period?start&end[&simulate_absence=EMP:START:END,...]

    Plain read is PUBLIC (same rule as day/week — the ops team opens /team-calendar with no
    login). SIMULATE mode is a planning tool and needs an editor."""
    q = request.query
    start = (q.get("start") or _today_iso())[:10]
    end = (q.get("end") or start)[:10]
    try:
        datetime.date.fromisoformat(start)
        datetime.date.fromisoformat(end)
    except ValueError:
        return HOST.json_response({"ok": False, "error": "تاريخ غير صحيح — الصيغة YYYY-MM-DD"}, 200)
    if end < start:
        return HOST.json_response({"ok": False, "error": "تاريخ النهاية قبل البداية"}, 200)
    span = (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days + 1
    if span > _PERIOD_MAX_DAYS:
        return HOST.json_response(
            {"ok": False, "error": "الفترة أطول من %d يوم — قسّمها على فترات" % _PERIOD_MAX_DAYS}, 200)
    try:
        sims = _parse_sims(q.get("simulate_absence"))
    except (ValueError, TypeError) as e:
        return HOST.json_response({"ok": False, "error": "طلب المحاكاة غير صحيح: %s" % e}, 200)
    try:
        pins = _parse_pins(q.get("pins"))
    except (ValueError, TypeError) as e:
        return HOST.json_response({"ok": False, "error": "تعيين غير صحيح: %s" % e}, 200)
    editor = can_edit_schedule(request)
    if (sims or pins) and not editor:
        return _deny()
    # Deriving the caps costs a 60-day Hostaway pull. Only an editor (the planner) may trigger
    # that; an anonymous /team-calendar reader gets the stored caps or none at all, so a public
    # URL can never be used to hammer Hostaway.
    caps = stored_caps() or (compute_caps() if editor else
                             {"units": None, "minutes": None, "source": "unknown",
                              "reason": "not_computed"})
    return HOST.json_response({"ok": True,
                               "period": build_period(start, end, sims=sims, caps=caps,
                                                      extra_date_overrides=pins),
                               "can_edit": editor})


async def api_caps_recompute(request):
    """Re-derive the overload caps from the last 60 days (editor only)."""
    if not can_edit_schedule(request):
        return _deny()
    return HOST.json_response({"ok": True, "caps": compute_caps()})


# ---------------- the PLAN: one leave + every apartment moved because of it ----------------

def _actor(request):
    fn = getattr(HOST, "req_actor", None)
    try:
        return (fn(request) or "").strip() if fn else ""
    except Exception:
        return ""


def _plan_caps():
    """Caps for the save-time re-check. Uses only what is STORED — saving a plan must never
    trigger a 60-day Hostaway pull."""
    return stored_caps() or {"units": None, "minutes": None, "source": "unknown"}


async def api_plan_save(request):
    """POST /api/schedule/plan — the leave(s) and the pins, saved as ONE thing.

    The simulation is re-run here, server-side: a client that never previewed, or previewed an
    hour ago, still cannot save a day with nobody on it."""
    if not can_edit_schedule(request):
        return _deny()
    b = await _body(request)

    emps, seen = [], set()
    for raw in (b.get("employees") or []):
        try:
            eid = int(raw.get("employee_id"))
        except (TypeError, ValueError):
            return HOST.json_response({"ok": False, "error": "موظف غير صحيح"}, 200)
        emp = db.q1("SELECT id, name FROM schedule_employees WHERE id=?", (eid,))
        if not emp:
            return HOST.json_response({"ok": False, "error": "موظف غير معروف"}, 200)
        start = (raw.get("start") or _today_iso())[:10]
        end = (raw.get("end") or start)[:10]
        try:
            datetime.date.fromisoformat(start)
            datetime.date.fromisoformat(end)
        except ValueError:
            return HOST.json_response({"ok": False, "error": "تاريخ غير صحيح — الصيغة YYYY-MM-DD"}, 200)
        if end < start:
            return HOST.json_response({"ok": False, "error": "تاريخ النهاية قبل البداية"}, 200)
        typ = raw.get("type") or "vacation"
        if typ not in PLANNER_ABSENCE_TYPES:
            return HOST.json_response(
                {"ok": False, "error": "نوع الإجازة غير متاح في المخطط حالياً"}, 200)
        shift = raw.get("shift")
        if typ == "half_day":
            if shift not in HALF_DAY_SHIFTS:
                return HOST.json_response(
                    {"ok": False,
                     "error": "حدّد نصف اليوم: صباحي أو مسائي — الفرق إنه يلحق التنظيف أو لا"}, 200)
        else:
            shift = None
        if (eid, start, end) in seen:
            continue
        seen.add((eid, start, end))
        if db.q1("SELECT id FROM schedule_absences WHERE employee_id=? AND status='approved' "
                 "AND start_date<=? AND end_date>=?", (eid, end, start)):
            return HOST.json_response(
                {"ok": False, "code": "overlap",
                 "error": "%s مسجّل إجازة في هذه الفترة أصلاً" % emp["name"]}, 200)
        emps.append({"employee_id": eid, "name": emp["name"], "start": start, "end": end,
                     "type": typ, "shift": shift,
                     "affects": _affects_coverage(typ, shift),
                     "status": _status_for(typ, request),
                     "note": (raw.get("note") or "")[:300]})
    if not emps:
        return HOST.json_response({"ok": False, "error": "أضف موظفاً واحداً على الأقل"}, 200)

    pins, edo = [], {}
    for raw in (b.get("overrides") or []):
        try:
            d = str(raw.get("date"))[:10]
            datetime.date.fromisoformat(d)
            aid = int(raw.get("apartment_id"))
            cov = int(raw.get("covering_employee_id"))
        except (TypeError, ValueError):
            return HOST.json_response({"ok": False, "error": "تعيين غير صحيح"}, 200)
        pins.append({"date": d, "apartment_id": aid, "covering_employee_id": cov})
        edo.setdefault(d, []).append({"apartment_id": aid, "covering_employee_id": cov})

    win_start = min([e["start"] for e in emps] + [p["date"] for p in pins])
    win_end = max([e["end"] for e in emps] + [p["date"] for p in pins])
    span = (datetime.date.fromisoformat(win_end) - datetime.date.fromisoformat(win_start)).days + 1
    if span > _PERIOD_MAX_DAYS:
        return HOST.json_response(
            {"ok": False, "error": "الخطة أطول من %d يوم" % _PERIOD_MAX_DAYS}, 200)

    # A pending request and an evening half-day change nothing, so they must not be
    # simulated into the save-time risk check either.
    sims = [{"employee_id": e["employee_id"], "name": e["name"],
             "start": e["start"], "end": e["end"]} for e in emps
            if e["affects"] and e["status"] == "approved"]
    per = build_period(win_start, win_end, sims=sims, caps=_plan_caps(),
                       extra_date_overrides=edo)
    blocking = [r for d in per["days"] for r in d["risks"] if r["severity"] == "block"]
    if blocking:
        return HOST.json_response({"ok": False, "code": blocking[0]["code"],
                                   "error": blocking[0]["ar"], "risks": blocking}, 200)
    warnings = [r for d in per["days"] for r in d["risks"] if r["severity"] == "warn"]
    if warnings and not b.get("accept_warnings"):
        seen_codes, uniq = set(), []
        for r in warnings:
            if r["code"] in seen_codes:
                continue
            seen_codes.add(r["code"])
            uniq.append(r)
        return HOST.json_response({"ok": False, "code": "needs_confirm",
                                   "error": "فيه تنبيهات — راجعها وأكّد",
                                   "warnings": uniq}, 200)

    actor = _actor(request) or "editor"
    now = db.now_iso()
    with db.transaction() as cx:
        pid = cx.execute(
            "INSERT INTO schedule_plans(note,start_date,end_date,created_by,created_at) "
            "VALUES(?,?,?,?,?)",
            ((b.get("note") or "")[:300], win_start, win_end, actor, now)).lastrowid
        for e in emps:
            cx.execute(
                "INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                "note,created_by,created_at,plan_id,shift,affects_coverage) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (e["employee_id"], e["start"], e["end"], e["type"], e["status"],
                 e["note"], actor, now, pid, e["shift"], e["affects"]))
        for pn in pins:
            cx.execute(
                "INSERT INTO schedule_date_overrides(date,apartment_id,covering_employee_id,"
                "plan_id,note,created_by,created_at) VALUES(?,?,?,?,?,?,?) "
                "ON CONFLICT(date,apartment_id) DO UPDATE SET "
                "covering_employee_id=excluded.covering_employee_id, plan_id=excluded.plan_id",
                (pn["date"], pn["apartment_id"], pn["covering_employee_id"], pid, None,
                 actor, now))
    _fire_change([win_start, win_end])
    pending = [e for e in emps if e["status"] == "pending"]
    immediate = [e for e in emps if e["status"] == "approved" and e["affects"]
                 and not can_decide_leave(request)]
    if immediate:
        _notify_owner_immediate(immediate, actor)
    return HOST.json_response({"ok": True, "plan_id": pid, "start": win_start, "end": win_end,
                               "employees": len(emps), "overrides": len(pins),
                               "pending": len(pending),
                               "warnings_accepted": bool(warnings)})


def _notify_owner_immediate(entries, actor):
    """Sick/emergency applied without waiting — the owner has to hear about it, and can
    reverse it. Delivery is HOST.notify, DRY-RUN by default like every other schedule post."""
    try:
        lines = ["تسجيل غياب فوري بواسطة %s" % (actor or "-")]
        for e in entries:
            lines.append("• %s: %s %s الى %s"
                         % (e["name"], ABSENCE_LABEL_AR.get(e["type"], e["type"]),
                            e["start"], e["end"]))
        lines.append("سرت على التوزيع فوراً — تقدر تلغيها من «الإجازات».")
        fn = getattr(HOST, "notify", None)
        if fn:
            fn({"channel": "\n".join(lines), "date": entries[0]["start"]})
    except Exception:
        traceback.print_exc()


async def api_plan_delete(request):
    """DELETE /api/schedule/plan/{id} — undo the WHOLE plan, and nothing that is not part of it."""
    if not can_edit_schedule(request):
        return _deny()
    try:
        pid = int(request.match_info.get("id"))
    except (TypeError, ValueError):
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    if not db.q1("SELECT id FROM schedule_plans WHERE id=?", (pid,)):
        return HOST.json_response({"ok": False, "error": "الخطة غير موجودة"}, 200)
    n_ov = len(db.q("SELECT id FROM schedule_date_overrides WHERE plan_id=?", (pid,)))
    n_ab = len(db.q("SELECT id FROM schedule_absences WHERE plan_id=?", (pid,)))
    with db.transaction() as cx:
        cx.execute("DELETE FROM schedule_date_overrides WHERE plan_id=?", (pid,))
        cx.execute("DELETE FROM schedule_absences WHERE plan_id=?", (pid,))
        cx.execute("DELETE FROM schedule_plans WHERE id=?", (pid,))
    _fire_change()
    return HOST.json_response({"ok": True, "removed": {"absences": n_ab, "overrides": n_ov}})


async def api_absences(request):
    """GET /api/schedule/absences?from=&to= — the leave list, upcoming first. Login-gated read."""
    today = _today_iso()
    q = request.query
    frm = (q.get("from") or (datetime.date.fromisoformat(today)
                             - datetime.timedelta(days=30)).isoformat())[:10]
    to = (q.get("to") or (datetime.date.fromisoformat(today)
                          + datetime.timedelta(days=120)).isoformat())[:10]
    try:
        datetime.date.fromisoformat(frm)
        datetime.date.fromisoformat(to)
    except ValueError:
        return HOST.json_response({"ok": False, "error": "تاريخ غير صحيح"}, 200)
    rows = db.q(
        "SELECT a.*, e.name employee_name, e.color, e.emoji FROM schedule_absences a "
        "LEFT JOIN schedule_employees e ON a.employee_id=e.id "
        "WHERE a.end_date>=? AND a.start_date<=? AND COALESCE(a.status,'approved')<>'rejected' "
        "ORDER BY a.start_date", (frm, to))
    out = []
    for r in rows:
        try:
            days = (datetime.date.fromisoformat(r["end_date"])
                    - datetime.date.fromisoformat(r["start_date"])).days + 1
        except ValueError:
            days = 1
        pid = r.get("plan_id")
        n_ov = (len(db.q("SELECT id FROM schedule_date_overrides WHERE plan_id=?", (pid,)))
                if pid else 0)
        typ = r.get("type")
        label_ar = ABSENCE_LABEL_AR.get(typ, typ)
        label_en = ABSENCE_LABEL_EN.get(typ, typ)
        if typ == "half_day" and r.get("shift"):
            label_ar += " — " + SHIFT_LABEL_AR.get(r["shift"], r["shift"])
            label_en += " - " + SHIFT_LABEL_EN.get(r["shift"], r["shift"])
        out.append({"id": r["id"], "employee_id": r["employee_id"],
                    "employee_name": r.get("employee_name"), "color": r.get("color"),
                    "emoji": r.get("emoji"), "start_date": r["start_date"],
                    "end_date": r["end_date"], "days": days, "type": typ,
                    "type_ar": label_ar, "type_en": label_en,
                    "shift": r.get("shift"),
                    "affects_coverage": bool(r.get("affects_coverage", 1)),
                    "needs_decision": (r.get("status") == "pending"),
                    "decided_by": r.get("decided_by"),
                    "status": r.get("status"), "note": r.get("note"),
                    "created_by": r.get("created_by"), "plan_id": pid,
                    "override_count": n_ov, "past": r["end_date"] < today})
    out.sort(key=lambda x: (x["past"], x["start_date"] if not x["past"] else ""),)
    return HOST.json_response({"ok": True, "absences": out, "from": frm, "to": to,
                               "types": [{"id": t, "ar": ABSENCE_LABEL_AR[t],
                                          "en": ABSENCE_LABEL_EN[t]}
                                         for t in PLANNER_ABSENCE_TYPES],
                               "can_edit": can_edit_schedule(request)})


async def api_suggest(request):
    """GET /api/schedule/suggest?date=&apartment_id=[&simulate_absence=...]

    Who should take this apartment on this date, ranked, each with the reason shown. The
    ranking itself lives in the pure engine; this only gathers the day's facts."""
    q = request.query
    date_iso = (q.get("date") or _today_iso())[:10]
    try:
        datetime.date.fromisoformat(date_iso)
        aid = int(q.get("apartment_id"))
    except (TypeError, ValueError):
        return HOST.json_response({"ok": False, "error": "date + apartment_id required"}, 200)
    apt = db.q1("SELECT * FROM schedule_apartments WHERE id=?", (aid,))
    if not apt:
        return HOST.json_response({"ok": False, "error": "شقة غير معروفة"}, 200)
    try:
        sims = _parse_sims(q.get("simulate_absence"))
    except (ValueError, TypeError) as e:
        return HOST.json_response({"ok": False, "error": "%s" % e}, 200)
    absent = {x["employee_id"] for x in sims if x["start"] <= date_iso <= x["end"]}
    day = schedule_day(date_iso, extra_absent=absent)
    demand = workload.fetch_window(date_iso, date_iso)
    enriched = _enrich_day(day, date_iso, demand, _unassigned_apartments())

    units = demand["units"]
    lid = apt.get("listing_id")
    apt_district = (units.get(int(lid)) or {}).get("district") if lid is not None else None
    # how often each employee has actually covered THIS apartment before (pins already made +
    # the recurring weekday rules) — "يغطّيها عادة" has to mean something real
    history = {}
    for r in db.q("SELECT covering_employee_id c, COUNT(*) n FROM schedule_date_overrides "
                  "WHERE apartment_id=? GROUP BY covering_employee_id", (aid,)):
        history[r["c"]] = history.get(r["c"], 0) + (r["n"] or 0)
    for r in db.q("SELECT covering_employee_id c, COUNT(*) n FROM schedule_coverage_overrides "
                  "WHERE apartment_id=? GROUP BY covering_employee_id", (aid,)):
        history[r["c"]] = history.get(r["c"], 0) + (r["n"] or 0)
    if apt.get("owner_id"):
        history[apt["owner_id"]] = history.get(apt["owner_id"], 0) + 1   # its permanent owner

    cands = [{"id": e["id"], "name": e["name"], "color": e.get("color"),
              "emoji": e.get("emoji"), "sort_order": e.get("sort_order", 0),
              "load": e["load"], "minutes": e["est_minutes"]}
             for e in enriched["employees"]]
    ranked = engine.rank_candidates(
        {"id": apt["id"], "name": apt.get("name")}, cands,
        {"apartment_district": apt_district,
         "districts": {e["id"]: e["districts"] for e in enriched["employees"]},
         "history": history,
         "minutes": {e["id"]: e["est_minutes"] for e in enriched["employees"]}})
    current = None
    for e in day["working"]:
        if aid in [a["id"] for a in e["own"]]:
            current = {"id": e["id"], "name": e["name"], "kind": "own"}
        for c in e["coverage"]:
            if c["apartment"]["id"] == aid:
                current = {"id": e["id"], "name": e["name"],
                           "kind": "pinned" if c["overridden"] else "auto"}
    return HOST.json_response({"ok": True, "date": date_iso, "apartment": apt.get("name"),
                               "apartment_id": aid, "district": apt_district,
                               "current": current, "candidates": ranked,
                               "demand_source": demand["source"]})


def _parse_pins(raw):
    """'DATE:APT:EMP,DATE:APT:EMP' -> {date: [{apartment_id, covering_employee_id}]}. The manual
    moves the owner is trying out, carried through a dry run without ever being written."""
    out = {}
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        if len(parts) != 3:
            raise ValueError("pins must be DATE:APT:EMP")
        d = parts[0][:10]
        datetime.date.fromisoformat(d)
        out.setdefault(d, []).append({"apartment_id": int(parts[1]),
                                      "covering_employee_id": int(parts[2])})
    return out


def _cover_history():
    """{apartment_id: {employee_id: times}} in TWO queries — who has actually covered what
    before. Called once per sheet, never once per apartment."""
    hist = {}
    for sql in ("SELECT apartment_id a, covering_employee_id c, COUNT(*) n "
                "FROM schedule_date_overrides GROUP BY apartment_id, covering_employee_id",
                "SELECT apartment_id a, covering_employee_id c, COUNT(*) n "
                "FROM schedule_coverage_overrides GROUP BY apartment_id, covering_employee_id"):
        for r in db.q(sql):
            hist.setdefault(r["a"], {})
            hist[r["a"]][r["c"]] = hist[r["a"]].get(r["c"], 0) + (r["n"] or 0)
    return hist


async def api_suggest_day(request):
    """GET /api/schedule/suggest-day?date=[&simulate_absence=][&pins=]

    Every apartment that needs covering on this date, each with the working team ranked and the
    reason shown. ONE Hostaway window call for the whole sheet, not one per apartment."""
    q = request.query
    date_iso = (q.get("date") or _today_iso())[:10]
    try:
        datetime.date.fromisoformat(date_iso)
    except ValueError:
        return HOST.json_response({"ok": False, "error": "تاريخ غير صحيح"}, 200)
    try:
        sims = _parse_sims(q.get("simulate_absence"))
        pins = _parse_pins(q.get("pins"))
    except (ValueError, TypeError) as e:
        return HOST.json_response({"ok": False, "error": "%s" % e}, 200)
    if (sims or pins) and not can_edit_schedule(request):
        return _deny()
    absent = {x["employee_id"] for x in sims if x["start"] <= date_iso <= x["end"]}
    day = schedule_day(date_iso, extra_absent=absent,
                       extra_date_overrides=pins.get(date_iso))
    demand = workload.fetch_window(date_iso, date_iso)
    enriched = _enrich_day(day, date_iso, demand, _unassigned_apartments())
    units = demand["units"]
    hist = _cover_history()
    apts_by_id = {a["id"]: a for a in db.apartments()}
    cands = [{"id": e["id"], "name": e["name"], "color": e.get("color"),
              "emoji": e.get("emoji"), "sort_order": e.get("sort_order", 0),
              "load": e["load"], "est_minutes": e["est_minutes"]}
             for e in enriched["employees"]]
    ctx_districts = {e["id"]: e["districts"] for e in enriched["employees"]}
    ctx_minutes = {e["id"]: e["est_minutes"] for e in enriched["employees"]}
    outs = demand["checkouts"].get(date_iso) or set()

    rows = []
    for o in day["off"]:
        for item in o.get("apartments") or []:
            apt = item["apartment"]
            row_hist = dict(hist.get(apt["id"]) or {})
            if apt.get("owner_id"):
                row_hist[apt["owner_id"]] = row_hist.get(apt["owner_id"], 0) + 1
            lid = apt.get("listing_id")
            district = (units.get(int(lid)) or {}).get("district") if lid is not None else None
            ranked = engine.rank_candidates(
                {"id": apt["id"], "name": apt.get("name")},
                [dict(c) for c in cands],
                {"apartment_district": district, "districts": ctx_districts,
                 "history": row_hist, "minutes": ctx_minutes})
            pinned = any(p["apartment_id"] == apt["id"] for p in pins.get(date_iso, []))
            rows.append({
                "apartment_id": apt["id"], "name": apt.get("name"),
                "owner_id": o["id"], "owner_name": o["name"], "district": district,
                "has_turnover": (lid is not None and int(lid) in outs),
                "current_id": item.get("covering_id"), "current_name": item.get("covering_name"),
                "pinned": pinned,
                "candidates": [{"id": c["id"], "name": c["name"], "color": c.get("color"),
                                "emoji": c.get("emoji"), "reason": c["reason"],
                                "reason_ar": c["reason_ar"], "reason_en": c["reason_en"],
                                "load": c.get("load"), "est_minutes": c.get("est_minutes")}
                               for c in ranked]})
    rows.sort(key=lambda r: (not r["has_turnover"],
                             apts_by_id.get(r["apartment_id"], {}).get("sort_order", 0),
                             r["apartment_id"]))
    return HOST.json_response({"ok": True, "date": date_iso, "weekday_ar": day["weekday_ar"],
                               "units": rows, "demand_source": demand["source"]})


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
    # period: plain read PUBLIC like day/week; simulate mode re-checks the editor role inside.
    g("/api/schedule/period", _safe_public(api_period))
    p("/api/schedule/caps-recompute", _safe(api_caps_recompute))
    g("/api/schedule/absences", _safe(api_absences))
    g("/api/schedule/suggest", _safe(api_suggest))
    g("/api/schedule/suggest-day", _safe(api_suggest_day))
    p("/api/schedule/plan", _safe(api_plan_save))
    app.router.add_delete("/api/schedule/plan/{id}", _safe(api_plan_delete))
    g("/api/schedule/manage", _safe(api_manage))
    g("/api/schedule/owners", _safe(api_owners))
    g("/api/schedule/hostaway-listings", _safe(api_hostaway_listings))
    p("/api/schedule/apartment-link", _safe(api_apartment_link))
    p("/api/schedule/autolink", _safe(api_autolink))
    p("/api/schedule/import-all", _safe(api_import_all))
    p("/api/schedule/apartment-owner", _safe(api_apartment_owner))
    p("/api/schedule/sync", _safe(api_sync))
    p("/api/schedule/remove-unlinked", _safe(api_remove_unlinked))
    p("/api/schedule/employee", _safe(api_employee_save))
    app.router.add_delete("/api/schedule/employee/{id}", _safe(api_employee_delete))
    p("/api/schedule/apartment", _safe(api_apartment_save))
    app.router.add_delete("/api/schedule/apartment/{id}", _safe(api_apartment_delete))
    p("/api/schedule/override", _safe(api_override_set))
    p("/api/schedule/absence", _safe(api_absence_add))
    p("/api/schedule/absence-decide", _safe(api_absence_decide))
    app.router.add_delete("/api/schedule/absence/{id}", _safe(api_absence_del))
    p("/api/schedule/settings", _safe(api_settings_set))
    p("/api/schedule/reset", _safe(api_reset))
    g("/team-calendar", handle_page)
