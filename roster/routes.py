"""
roster.routes — aiohttp handlers for the 7 NOW endpoints (build spec §6) + the standalone
/roster page. Reads/writes go through roster.db; the board comes from the pure roster.engine
so the dashboard tab, the standalone page, and every Discord message render IDENTICAL numbers
for the same date. All mutating routes are role-gated and idempotent; reads need dash auth.
"""

import datetime
import traceback

from . import db, engine, hostaway, notify, page
from .host import HOST

# The turnover workforce the board balances across. Managers (ops_manager/team_leader) can
# be marked active for absences/visibility but do NOT carry turnovers in v1.
COVERAGE_ROLES = ("employee", "owner")
ABSENCE_TYPES = ("sick", "vacation", "emergency", "half_day", "late", "training", "no_show", "unpaid")


# ---------------- auth helpers ----------------

def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def _role(request):
    try:
        return HOST.req_role(request) if HOST.req_role else "viewer"
    except Exception:
        return "viewer"


def _can_write(request):
    """admin/ops may mutate the roster (owner mgmt, sync, override, any leave). Maps the
    multi-user roles onto the spec's owner/ops_manager/team_leader powers; finer team_leader
    gating arrives when that role is added to the users system (NEXT)."""
    return _role(request) in ("admin", "ops")


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
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _today_iso():
    try:
        return HOST.now().date().isoformat()
    except Exception:
        return datetime.date.today().isoformat()


# ---------------- the shared, enriched roster (single source) ----------------

def roster_for(date_iso):
    """Compute + enrich the board for a date. Used by the API, the standalone page,
    and the notifier so they can never disagree."""
    emps_all = db.employees()
    emps = [e for e in emps_all if e["is_active"] and e["role"] in COVERAGE_ROLES]
    props = db.properties()
    by_id = {e["id"]: e for e in emps_all}

    absences = db.absences_on(date_iso)
    locks = db.locks_on(date_iso)
    r = engine.compute_roster(date_iso, emps, props, absences, locks=locks)

    def _nm(eid):
        e = by_id.get(eid)
        return e["name_ar"] if e else "—"

    board = []
    for e in emps:
        if e["id"] not in r["board"]:
            continue
        cell = r["board"][e["id"]]
        board.append({
            "id": e["id"], "name": e["name_ar"], "initial": e.get("initial_ar"),
            "role": e["role"], "weekly_off": e.get("weekly_off"),
            "discord_id": e.get("discord_id"), "load": r["load"].get(e["id"], 0),
            "primary": [{"id": p["id"], "name": p["display_name_ar"]} for p in cell["primary"]],
            "covered": [{"id": c["property"]["id"], "name": c["property"]["display_name_ar"],
                         "orig_id": c["original_owner_id"], "orig_name": _nm(c["original_owner_id"])}
                        for c in cell["covered"]],
        })
    board.sort(key=lambda b: (-b["load"], b["id"]))

    # absent custodians, with reason (weekly off vs approved leave)
    wd = r["weekday"]
    on_leave = {a["employee_id"]: a for a in absences if a.get("status") == "approved"}
    absent = []
    for eid in r["absent"]:
        e = by_id.get(eid)
        if not e:
            continue
        if eid in on_leave:
            absent.append({"id": eid, "name": e["name_ar"], "reason": "leave",
                           "type": on_leave[eid].get("type")})
        else:
            absent.append({"id": eid, "name": e["name_ar"], "reason": "off"})

    gaps = [{"id": p["id"], "name": p["display_name_ar"],
             "orig_id": p.get("primary_owner_id"), "orig_name": _nm(p.get("primary_owner_id"))}
            for p in r["gap_properties"]]
    unassigned = [{"id": p["id"], "name": p["display_name_ar"]}
                  for p in props if p.get("status") == "active" and not p.get("primary_owner_id")]

    return {
        "date": date_iso, "weekday": wd,
        "status": {"total": r["total"], "assigned": r["assigned"], "gaps": r["gaps"],
                   "available": len(r["available"]), "absent": len(r["absent"]),
                   "overloads": r["overloads"]},
        "board": board, "absent": absent, "gaps": gaps, "unassigned": unassigned,
        "escalate": r["escalate"],
    }


def _persist_log(date_iso, enriched):
    """Write a fresh assignment snapshot for the date (audit trail). Locked override rows are
    preserved; only the engine-computed (unlocked) rows are replaced."""
    db.execute("DELETE FROM roster_assignment_log WHERE date=? AND locked=0", (date_iso,))
    rows = []
    now = db.now_iso()
    for e in enriched["board"]:
        for p in e["primary"]:
            rows.append((date_iso, p["id"], e["id"], 0, e["id"], 0, None, None, now))
        for c in e["covered"]:
            rows.append((date_iso, c["id"], e["id"], 1, c["orig_id"], 0, None, None, now))
    if rows:
        db.executemany(
            "INSERT INTO roster_assignment_log(date,property_id,responsible_id,is_coverage,"
            "original_owner_id,locked,override_by,override_reason,computed_at) VALUES(?,?,?,?,?,?,?,?,?)",
            rows)
    # coverage ledger (fairness over time — NEXT consumes this)
    for e in enriched["board"]:
        n = len(e["covered"])
        if n:
            db.execute("INSERT INTO roster_coverage_ledger(employee_id,date,covered_count) VALUES(?,?,?) "
                       "ON CONFLICT(employee_id,date) DO UPDATE SET covered_count=excluded.covered_count",
                       (e["id"], date_iso, n))


def _notify_change(date_iso, reason):
    """Recompute + fire notifications only for changes affecting today or tomorrow (§8)."""
    today = _today_iso()
    tomorrow = (datetime.date.fromisoformat(today) + datetime.timedelta(days=1)).isoformat()
    if date_iso not in (today, tomorrow):
        return
    enriched = roster_for(date_iso)
    _persist_log(date_iso, enriched)
    notify.fire(date_iso, enriched["weekday"], enriched, reason=reason)


# ---------------- 1) GET /api/roster ----------------

async def api_roster(request):
    date_iso = (request.query.get("date") or _today_iso())[:10]
    try:
        datetime.date.fromisoformat(date_iso)
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad date"}, 200)
    return HOST.json_response({"ok": True, "roster": roster_for(date_iso),
                               "can_write": _can_write(request), "role": _role(request)})


# ---------------- 2) POST /api/absence ----------------

async def api_absence_add(request):
    if not _can_write(request):
        return HOST.json_response({"ok": False, "error": "forbidden"}, 403)
    b = await _body(request)
    try:
        emp_id = int(b.get("employee_id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "employee_id required"}, 200)
    start = (b.get("start_date") or _today_iso())[:10]
    end = (b.get("end_date") or start)[:10]
    typ = b.get("type") or "sick"
    if typ not in ABSENCE_TYPES:
        return HOST.json_response({"ok": False, "error": "bad type"}, 200)
    if end < start:
        return HOST.json_response({"ok": False, "error": "end before start"}, 200)
    if not db.q1("SELECT id FROM roster_employees WHERE id=?", (emp_id,)):
        return HOST.json_response({"ok": False, "error": "unknown employee"}, 200)
    # reject if an approved absence already overlaps this window (idempotent guard)
    dup = db.q1("SELECT id FROM roster_absences WHERE employee_id=? AND status='approved' "
                "AND start_date<=? AND end_date>=?", (emp_id, end, start))
    if dup:
        return HOST.json_response({"ok": False, "error": "already off in this range",
                                   "existing_id": dup["id"]}, 200)
    status = "approved" if _can_write(request) else "requested"
    aid = db.execute(
        "INSERT INTO roster_absences(employee_id,start_date,end_date,type,status,note,created_by,created_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (emp_id, start, end, typ, status, b.get("note"), _role(request), db.now_iso()))
    _notify_change(start, "absence")
    return HOST.json_response({"ok": True, "id": aid, "status": status,
                               "roster": roster_for(start)})


# ---------------- 3) DELETE /api/absence/{id} ----------------

async def api_absence_del(request):
    if not _can_write(request):
        return HOST.json_response({"ok": False, "error": "forbidden"}, 403)
    try:
        aid = int(request.match_info.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    row = db.q1("SELECT * FROM roster_absences WHERE id=?", (aid,))
    if not row:
        return HOST.json_response({"ok": True, "deleted": 0})   # idempotent
    db.execute("DELETE FROM roster_absences WHERE id=?", (aid,))
    _notify_change(row["start_date"], "absence-removed")
    return HOST.json_response({"ok": True, "deleted": 1, "roster": roster_for(row["start_date"])})


# ---------------- 4) GET /api/properties ----------------

async def api_properties(request):
    props = db.properties()
    emps = {e["id"]: e["name_ar"] for e in db.employees()}
    out = [{"id": p["id"], "name": p["display_name_ar"], "owner_id": p.get("primary_owner_id"),
            "owner_name": emps.get(p.get("primary_owner_id")), "zone": p.get("zone"),
            "hostaway_listing_id": p.get("hostaway_listing_id"), "status": p.get("status"),
            "weight": p.get("turnover_weight")} for p in props]
    unassigned = [p for p in out if p["status"] == "active" and not p["owner_id"]]
    employees = [{"id": e["id"], "name": e["name_ar"], "role": e["role"],
                  "weekly_off": e.get("weekly_off"), "active": e["is_active"]}
                 for e in db.employees()]
    return HOST.json_response({"ok": True, "properties": out, "unassigned": unassigned,
                               "employees": employees, "can_write": _can_write(request)})


# ---------------- 5) POST /api/properties/{id}/owner ----------------

async def api_property_owner(request):
    if not _can_write(request):
        return HOST.json_response({"ok": False, "error": "forbidden"}, 403)
    try:
        pid = int(request.match_info.get("id"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    b = await _body(request)
    owner_id = b.get("owner_id")
    if owner_id in ("", None):
        owner_id = None
    else:
        try:
            owner_id = int(owner_id)
        except Exception:
            return HOST.json_response({"ok": False, "error": "bad owner_id"}, 200)
        if not db.q1("SELECT id FROM roster_employees WHERE id=?", (owner_id,)):
            return HOST.json_response({"ok": False, "error": "unknown employee"}, 200)
    if not db.q1("SELECT id FROM roster_properties WHERE id=?", (pid,)):
        return HOST.json_response({"ok": False, "error": "unknown property"}, 200)
    # optional rename + status from the unassigned-panel flow
    sets, args = ["primary_owner_id=?"], [owner_id]
    if b.get("name"):
        sets.append("display_name_ar=?"); args.append(str(b["name"]).strip())
    if b.get("status") in ("active", "paused", "offboarded"):
        sets.append("status=?"); args.append(b["status"])
    args.append(pid)
    db.execute("UPDATE roster_properties SET %s WHERE id=?" % ",".join(sets), tuple(args))
    _notify_change(_today_iso(), "owner-change")
    return HOST.json_response({"ok": True})


# ---------------- 6) POST /api/hostaway/sync ----------------

async def api_sync(request):
    if not _can_write(request):
        return HOST.json_response({"ok": False, "error": "forbidden"}, 403)
    return HOST.json_response({"ok": True, "report": hostaway.sync()})


# ---------------- 7) POST /api/assignment/override ----------------

async def api_override(request):
    if not _can_write(request):
        return HOST.json_response({"ok": False, "error": "forbidden"}, 403)
    b = await _body(request)
    date_iso = (b.get("date") or _today_iso())[:10]
    try:
        pid = int(b.get("property"))
        to_id = int(b.get("to"))
    except Exception:
        return HOST.json_response({"ok": False, "error": "property + to required"}, 200)
    reason = (b.get("reason") or "").strip()
    if not reason:
        return HOST.json_response({"ok": False, "error": "reason required"}, 200)
    prop = db.q1("SELECT * FROM roster_properties WHERE id=?", (pid,))
    if not prop:
        return HOST.json_response({"ok": False, "error": "unknown property"}, 200)
    if not db.q1("SELECT id FROM roster_employees WHERE id=?", (to_id,)):
        return HOST.json_response({"ok": False, "error": "unknown employee"}, 200)
    # upsert a LOCKED row for (date, property): replace any prior lock for the same pair
    db.execute("DELETE FROM roster_assignment_log WHERE date=? AND property_id=? AND locked=1",
               (date_iso, pid))
    db.execute(
        "INSERT INTO roster_assignment_log(date,property_id,responsible_id,is_coverage,"
        "original_owner_id,locked,override_by,override_reason,computed_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (date_iso, pid, to_id, 1 if to_id != prop.get("primary_owner_id") else 0,
         prop.get("primary_owner_id"), 1, _role(request), reason, db.now_iso()))
    _notify_change(date_iso, "override")
    return HOST.json_response({"ok": True, "roster": roster_for(date_iso)})


# ---------------- standalone page ----------------

async def handle_page(request):
    return HOST.web.Response(text=page.ROSTER_ROUTE_HTML, content_type="text/html")


def register(app):
    add = app.router.add_get
    add("/api/roster", _safe(api_roster))
    app.router.add_post("/api/absence", _safe(api_absence_add))
    app.router.add_delete("/api/absence/{id}", _safe(api_absence_del))
    add("/api/properties", _safe(api_properties))
    app.router.add_post("/api/properties/{id}/owner", _safe(api_property_owner))
    app.router.add_post("/api/hostaway/sync", _safe(api_sync))
    app.router.add_post("/api/assignment/override", _safe(api_override))
    app.router.add_get("/roster", handle_page)
