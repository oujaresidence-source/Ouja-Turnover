# -*- coding: utf-8 -*-
"""
onboarding.routes — aiohttp handlers for «ضم الوحدات» (build spec §9).

Every handler is _safe-wrapped: 401 when not logged in, 403 on the wrong role, and an
unhandled exception returns HTTP 200 with {"ok": false, "error": ...} — never a 500. That is
this codebase's rule; the front end always parses JSON.

Error shape contract (there is no fourth):
  not logged in           -> 401 {"ok": false, "error": "unauthorized"}
  logged in, wrong role   -> 403 {"ok": false, "error": "<Arabic>"}
  business-rule refusal   -> 200 {"ok": false, "error": "<Arabic>", "blockers": [...]}
  success                 -> 200 {"ok": true, ...}

The publish gate is NEVER re-implemented here. Every blocker comes from engine.readiness(), so
the API, the page and the Discord message cannot drift.
"""

import traceback

from . import catalogue, db, emp_page, engine, page
from .host import HOST

EDIT_ROLES = ("admin", "ops")       # may edit an onboarding project
PUBLISH_ROLES = ("admin",)          # ONLY the owner/admin may publish (build spec R5)

CLIENT_TYPES = ("owner", "tenant", "prospect")
UNIT_KINDS = ("tower", "compound", "standalone")
FURNISH_STATES = ("furnished", "partial", "unfurnished")
STRATEGIES = ("yearly", "monthly", "weekly_nightly")
RESOLUTIONS = ("done", "na", "blocked")
NEEDS_REASON = ("na", "blocked")

UNIT_PREFIX = "Ouja |"
UNIT_NAME_MAX = 50


# ---------------------------------------------------------------- guards --------------------

def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def can_edit(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in EDIT_ROLES
    except Exception:
        return False


def can_publish(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in PUBLISH_ROLES
    except Exception:
        return False


def _deny(msg="غير مصرّح لك بالتعديل"):
    return HOST.json_response({"ok": False, "error": msg}, 403)


def _refuse(msg, **extra):
    """A business-rule refusal is a 200 with ok:false — it is an answer, not a failure."""
    body = {"ok": False, "error": msg}
    body.update(extra)
    return HOST.json_response(body, 200)


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


def _safe_public(fn):
    """PUBLIC wrapper — NO login. Used ONLY by the assigned employee's token link. Full detail
    stays in the server log; the anonymous caller gets a generic Arabic message and never a
    stack trace."""
    async def _w(request):
        try:
            return await fn(request)
        except Exception:
            traceback.print_exc()
            return HOST.json_response(
                {"ok": False, "error": "صار خطأ مؤقت — حدّث الصفحة وجرّب مرة ثانية"}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _actor(request):
    try:
        return HOST.actor(request) if HOST.actor else "—"
    except Exception:
        return "—"


def _qs(request, key, default=""):
    try:
        return request.query.get(key, default)
    except Exception:
        return default


def _blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


# ---------------------------------------------------------------- employees -----------------

def _employees():
    """The ONLY legal source of people (build spec R6): the Employee Calendar. Never a
    free-text box — free text is exactly why pmo and the maintenance tickets already carry
    unusable assignee data. Degrades to an empty list when the schedule package is off."""
    try:
        from schedule import owners as _sowners
        return list((_sowners.permanent_map() or {}).get("employees") or [])
    except Exception as e:
        print("[onboarding] employee roster unavailable:", e)
        return []


def _discord_id_for(name):
    try:
        ids = HOST.discord_ids() if HOST.discord_ids else {}
    except Exception:
        ids = {}
    return str((ids or {}).get(name) or "")


def _base_url():
    try:
        b = HOST.public_base() if HOST.public_base else ""
    except Exception:
        b = ""
    return (b or "").rstrip("/")


def _emp_link(token):
    return "%s/onb/t/%s" % (_base_url(), token)


# ---------------------------------------------------------------- shaping -------------------

def _project_view(p, tasks, asg):
    """One project, with everything the page needs to draw it — including the gate, so the
    list and the project screen agree about what is ready."""
    r = engine.readiness(p, tasks, asg, today=_today())
    return {
        "project": p,
        "tasks": tasks,
        "assignees": asg,
        "readiness": r,
        "progress": engine.progress(tasks),
        "stage_counts": engine.stage_counts(tasks),
    }


def _today():
    try:
        return HOST.now().date() if HOST.now else None
    except Exception:
        return None


def _stages_meta():
    return [{"id": s, "label": catalogue.STAGE_LABEL[s]} for s in catalogue.UNIT_STAGES]


# ---------------------------------------------------------------- read endpoints ------------

async def api_list(request):
    if not can_edit(request):
        return _deny("ما عندك صلاحية لعرض ضم الوحدات")
    rows = []
    ready = active = published = 0
    for p in db.projects():
        ts = db.tasks(p["id"])
        asg = db.assignees(p["id"])
        r = engine.readiness(p, ts, asg, today=_today())
        state = p.get("status") or "active"
        if state == "published":
            published += 1
        elif state == "active":
            active += 1
            if r["ok"]:
                ready += 1
        rows.append({
            "id": p["id"], "ref": p.get("ref"),
            "unit_name": p.get("unit_name"), "client_name": p.get("client_name"),
            "district": p.get("district"), "stage": p.get("stage"),
            "stage_label": catalogue.STAGE_LABEL.get(p.get("stage") or "", ""),
            "status": state, "progress": engine.progress(ts),
            "ready": bool(r["ok"]), "blocker_count": len(r["blockers"]),
            "assignees": [{"employee_id": a["employee_id"], "employee_name": a["employee_name"],
                           "is_primary": a.get("is_primary")} for a in asg],
            "published_at": p.get("published_at"), "updated_at": p.get("updated_at"),
        })
    return HOST.json_response({"ok": True, "projects": rows,
                               "counters": {"active": active, "ready": ready,
                                            "published": published},
                               "stages": _stages_meta()})


async def api_get(request):
    if not can_edit(request):
        return _deny("ما عندك صلاحية لعرض ضم الوحدات")
    pid = _qs(request, "id")
    p = db.project(pid) if pid else None
    if not p:
        return _refuse("ما لقيت المشروع")
    ts = db.tasks(p["id"])
    asg = db.assignees(p["id"])
    view = _project_view(p, ts, asg)
    view.update({
        "ok": True,
        "log": db.logs(p["id"]),
        "stages": _stages_meta(),
        "ongoing": [{"catalogue_key": k, "stage": s, "seq": q, "title_ar": t,
                     "owner_role": o, "gate": g}
                    for (k, s, q, t, o, g) in catalogue.ongoing_rows()],
        "owner_role_ar": catalogue.OWNER_ROLE_AR,
        "can_publish": can_publish(request),
        "handover": (db.handover(p["id"]) or {}).get("snapshot"),
        "emp_links": [{"employee_name": a["employee_name"], "link": _emp_link(a["access_token"])}
                      for a in asg],
    })
    return HOST.json_response(view)


async def api_readiness(request):
    if not can_edit(request):
        return _deny("ما عندك صلاحية لعرض ضم الوحدات")
    pid = _qs(request, "id")
    p = db.project(pid) if pid else None
    if not p:
        return _refuse("ما لقيت المشروع")
    ts = db.tasks(p["id"])
    asg = db.assignees(p["id"])
    r = engine.readiness(p, ts, asg, today=_today())
    return HOST.json_response({"ok": True, "readiness": r, "progress": engine.progress(ts),
                               "stage_counts": engine.stage_counts(ts)})


async def api_employees(request):
    if not can_edit(request):
        return _deny("ما عندك صلاحية لعرض ضم الوحدات")
    emps = _employees()
    load = db.assignee_project_counts()
    out = [{"id": e["id"], "name": e["name"], "emoji": e.get("emoji"), "color": e.get("color"),
            "projects": load.get(int(e["id"]), 0),
            "reachable": bool(_discord_id_for(e["name"]))} for e in emps]
    hint = "" if out else "تقويم الموظفين غير متاح — افتح صفحة تقويم الموظفين أول"
    return HOST.json_response({"ok": True, "employees": out, "hint": hint})


async def api_handover(request):
    if not can_edit(request):
        return _deny("ما عندك صلاحية لعرض ضم الوحدات")
    pid = _qs(request, "id")
    p = db.project(pid) if pid else None
    if not p:
        return _refuse("ما لقيت المشروع")
    row = db.handover(p["id"])
    if not row:
        return _refuse("الوحدة ما انشرت بعد — ما فيه ملف تسليم")
    snap = row.get("snapshot") or {}
    return HOST.json_response({"ok": True, "snapshot": snap,
                               "text": engine.handover_text(p, snap),
                               "created_at": row.get("created_at")})


# ---------------------------------------------------------------- create / update -----------

def _clean_unit_name(raw):
    """(name, error). Every Ouja unit name starts with 'Ouja |' and stays under 50 chars —
    an owner convention, enforced once here so no caller can bypass it."""
    name = (raw or "").strip()
    if not name:
        return "", "اسم الوحدة مطلوب"
    if not name.startswith(UNIT_PREFIX):
        name = "%s %s" % (UNIT_PREFIX, name.lstrip("| ").strip())
    name = " ".join(name.split())
    if len(name) > UNIT_NAME_MAX:
        return "", "اسم الوحدة طويل — الحد %d حرف (الحالي %d)" % (UNIT_NAME_MAX, len(name))
    return name, ""


async def api_create(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    fields = {}
    missing = {}
    for key, label in (("client_name", "اسم العميل"), ("client_whatsapp", "واتساب العميل"),
                       ("district", "الحي")):
        v = (b.get(key) or "").strip() if isinstance(b.get(key), str) else b.get(key)
        if _blank(v):
            missing[key] = label + " مطلوب"
        else:
            fields[key] = v
    ctype = (b.get("client_type") or "").strip()
    if ctype not in CLIENT_TYPES:
        missing["client_type"] = "نوع العميل مطلوب"
    else:
        fields["client_type"] = ctype
    name, err = _clean_unit_name(b.get("unit_name"))
    if err:
        missing["unit_name"] = err
    else:
        fields["unit_name"] = name
    kind = (b.get("unit_kind") or "").strip()
    if kind not in UNIT_KINDS:
        missing["unit_kind"] = "نوع الوحدة مطلوب"
    else:
        fields["unit_kind"] = kind
    fstate = (b.get("furnish_state") or "").strip()
    if fstate not in FURNISH_STATES:
        missing["furnish_state"] = "حالة التأثيث مطلوبة"
    else:
        fields["furnish_state"] = fstate
    try:
        fields["bedrooms"] = int(b.get("bedrooms"))
    except (TypeError, ValueError):
        missing["bedrooms"] = "عدد الغرف مطلوب"
    if missing:
        return _refuse("فيه بيانات ناقصة — كمّلها قبل لا نفتح المشروع", fields=missing)

    # optional at create; the gate will ask for them before publish
    for k in ("client_email", "area_sqm", "listing_id", "amenities", "sublet_ok",
              "strategy", "ouja_rate_pct", "cleaning_sar", "cleaning_absorbed",
              "contract_signed_at", "ceo_approval", "pmo_project_id", "handover_target"):
        if k in b and not _blank(b.get(k)):
            fields[k] = b.get(k)

    who = _actor(request)
    p = db.create_project(fields, created_by=who)
    db.log(p["id"], who, "فُتح المشروع وتولّدت قائمة المهام تلقائيًا")
    ts = db.tasks(p["id"])
    return HOST.json_response({"ok": True, "project": p, "task_count": len(ts),
                               "readiness": engine.readiness(p, ts, [], today=_today())})


async def api_update(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    p = db.project(b.get("id")) if b.get("id") else None
    if not p:
        return _refuse("ما لقيت المشروع")
    if (p.get("status") or "") == "published":
        return _refuse("الوحدة منشورة — ما ينفع تعديلها")
    patch = {k: v for k, v in b.items() if k in db.EDITABLE_FIELDS}
    if "unit_name" in patch:
        name, err = _clean_unit_name(patch.get("unit_name"))
        if err:
            return _refuse(err)
        patch["unit_name"] = name
    if not patch:
        return _refuse("ما فيه شي تغيّر")
    p = db.update_project(p["id"], **patch)
    # A change of shape (client type / furnishing / a linked fit-out project) may make tasks
    # inapplicable. This only ever touches tasks still `open` — a human resolution is never
    # reopened or overwritten.
    db.apply_auto_na(p["id"])
    ts = db.tasks(p["id"])
    asg = db.assignees(p["id"])
    db.log(p["id"], _actor(request), "تحديث بيانات: %s" % "، ".join(sorted(patch.keys())))
    return HOST.json_response({"ok": True, "project": db.project(p["id"]),
                               "tasks": ts,
                               "readiness": engine.readiness(db.project(p["id"]), ts, asg,
                                                             today=_today()),
                               "progress": engine.progress(ts),
                               "stage_counts": engine.stage_counts(ts)})


async def api_walk_away(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    p = db.project(b.get("id")) if b.get("id") else None
    if not p:
        return _refuse("ما لقيت المشروع")
    if (p.get("status") or "") == "published":
        return _refuse("الوحدة منشورة — ما ينفع الانسحاب منها")
    reason = (b.get("reason") or "").strip()
    if not reason:
        return _refuse("اكتب سبب الانسحاب — السبب هو السجل")
    p = db.walk_away(p["id"], reason, _actor(request))
    return HOST.json_response({"ok": True, "project": p})


# ---------------------------------------------------------------- tasks ---------------------

async def api_task_resolve(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    p = db.project(b.get("project_id")) if b.get("project_id") else None
    if not p:
        return _refuse("ما لقيت المشروع")
    if (p.get("status") or "") == "published":
        return _refuse("الوحدة منشورة — ما ينفع تعديلها")
    t = db.task(b.get("task_id")) if b.get("task_id") else None
    if not t or int(t.get("project_id")) != int(p["id"]):
        return _refuse("ما لقيت المهمة في هذا المشروع")
    res = (b.get("resolution") or "").strip()
    if res not in RESOLUTIONS:
        return _refuse("اختر: تم أو ما ينطبق أو متوقف")
    reason = (b.get("reason") or "").strip()
    if res in NEEDS_REASON and not reason:
        return _refuse("اكتب السبب — «ما ينطبق» و«متوقف» لازم لها سبب")
    who = _actor(request)
    t = db.resolve_task(t["id"], res, reason, who)
    label = {"done": "تم", "na": "ما ينطبق", "blocked": "متوقف"}[res]
    db.log(p["id"], who, "%s: %s%s" % (label, t.get("title_ar") or "",
                                       (" — %s" % reason) if reason else ""))
    ts = db.tasks(p["id"])
    asg = db.assignees(p["id"])
    return HOST.json_response({"ok": True, "task": t, "progress": engine.progress(ts),
                               "stage_counts": engine.stage_counts(ts),
                               "readiness": engine.readiness(p, ts, asg, today=_today())})


async def task_assign(request):
    """The batch endpoint (build spec §9.1) — one save, one ticket per person.

    All-or-nothing: one bad employee id writes NOTHING. A half-applied delegation is worse
    than a rejected one.

    Any task may go to either of the project's two people. The catalogue's role label is
    deliberately never consulted here (build spec R7) and a test asserts this function's
    source never mentions it.
    """
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    p = db.project(b.get("project_id")) if b.get("project_id") else None
    if not p:
        return _refuse("ما لقيت المشروع")
    if (p.get("status") or "") != "active":
        return _refuse("المشروع مو نشط — ما ينفع توزيع مهام عليه")

    asg = db.assignees(p["id"])
    by_emp = {int(a["employee_id"]): a for a in asg}
    changes = b.get("changes") or []
    if not isinstance(changes, list) or not changes:
        return _refuse("ما فيه توزيع للحفظ")

    # ---- validate the WHOLE batch before a single row is written ---------------------------
    plan = []
    for c in changes:
        if not isinstance(c, dict):
            return _refuse("صيغة التوزيع غير صحيحة")
        t = db.task(c.get("task_id")) if c.get("task_id") else None
        if not t or int(t.get("project_id")) != int(p["id"]):
            return _refuse("فيه مهمة مو من هذا المشروع — ما انحفظ شي")
        raw = c.get("employee_id")
        if raw in (None, "", "none"):
            plan.append((t, None))
            continue
        try:
            eid = int(raw)
        except (TypeError, ValueError):
            return _refuse("رقم الموظف غير صحيح — ما انحفظ شي")
        who = by_emp.get(eid)
        if not who:
            nm = next((e["name"] for e in _employees() if int(e["id"]) == eid), str(eid))
            return _refuse("«%s» مو ضمن فريق المشروع — ضِفه أول" % nm)
        plan.append((t, who))

    # ---- write it all in ONE transaction ---------------------------------------------------
    now = db.now_iso()
    fresh = {}
    with db.transaction() as cx:
        for t, who in plan:
            if who is None:
                cx.execute("UPDATE onb_tasks SET assignee_id=NULL, assignee_name=NULL, "
                           "notified_at=NULL, updated_at=? WHERE id=?", (now, int(t["id"])))
                continue
            eid = int(who["employee_id"])
            changed = (t.get("assignee_id") is None or int(t["assignee_id"]) != eid)
            if changed:
                cx.execute("UPDATE onb_tasks SET assignee_id=?, assignee_name=?, "
                           "notified_at=NULL, updated_at=? WHERE id=?",
                           (eid, who["employee_name"], now, int(t["id"])))
            # newly assigned = the person changed, or the same person was never announced
            if changed or not t.get("notified_at"):
                fresh.setdefault(eid, []).append(int(t["id"]))

    # ---- announce, OUTSIDE the transaction, one payload per person -------------------------
    notified = []
    for eid, task_ids in fresh.items():
        who = by_emp[eid]
        rows = [db.task(i) for i in task_ids]
        rows = [r for r in rows if r]
        if not rows:
            continue
        link = _emp_link(who.get("access_token"))
        text = engine.assignment_card(p, who, rows, link)
        sent = True
        fn = HOST.notify
        if fn:
            try:
                fn({"kind": "assign", "project_id": p["id"], "employee_id": eid,
                    "employee_name": who["employee_name"], "text": text, "link": link,
                    "count": len(rows)})
            except Exception:
                traceback.print_exc()
                sent = False        # leave notified_at NULL so the next save retries the ping
        if sent:
            db.stamp_notified(task_ids, now)
        db.log(p["id"], _actor(request),
               "انفتح تكت لـ%s — %d مهام" % (who["employee_name"], len(rows)))
        notified.append({"name": who["employee_name"], "count": len(rows),
                         "reachable": bool(who.get("employee_did")), "sent": sent})

    ts = db.tasks(p["id"])
    return HOST.json_response({"ok": True, "project": db.project(p["id"]), "tasks": ts,
                               "notified": notified,
                               "progress": engine.progress(ts),
                               "readiness": engine.readiness(p, ts, asg, today=_today())})


# ---------------------------------------------------------------- assignees -----------------

async def api_assignee_add(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    p = db.project(b.get("project_id")) if b.get("project_id") else None
    if not p:
        return _refuse("ما لقيت المشروع")
    if (p.get("status") or "") == "published":
        return _refuse("الوحدة منشورة — ما ينفع تعديلها")
    try:
        eid = int(b.get("employee_id"))
    except (TypeError, ValueError):
        return _refuse("اختر موظف من القائمة")
    emp = next((e for e in _employees() if int(e["id"]) == eid), None)
    if not emp:
        return _refuse("ما لقيت الموظف في تقويم الموظفين")
    current = db.assignees(p["id"])
    ok, err = engine.can_add_assignee(current, eid)
    if not ok:
        return _refuse(err)
    did = _discord_id_for(emp["name"])
    row = db.add_assignee(p["id"], eid, emp["name"], did,
                          is_primary=1 if not current else 0, added_by=_actor(request))
    db.log(p["id"], _actor(request), "أُضيف %s لفريق المشروع" % emp["name"])
    return HOST.json_response({"ok": True, "assignee": row,
                               "assignees": db.assignees(p["id"]),
                               "link": _emp_link(row.get("access_token")),
                               "reachable": bool(did)})


async def api_assignee_remove(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    p = db.project(b.get("project_id")) if b.get("project_id") else None
    if not p:
        return _refuse("ما لقيت المشروع")
    if (p.get("status") or "") == "published":
        return _refuse("الوحدة منشورة — ما ينفع تعديلها")
    try:
        eid = int(b.get("employee_id"))
    except (TypeError, ValueError):
        return _refuse("اختر موظف")
    row = db.assignee(p["id"], eid)
    if not row:
        return _refuse("هذا الموظف مو على المشروع")
    db.remove_assignee(p["id"], eid)
    db.log(p["id"], _actor(request), "انحذف %s من فريق المشروع" % row.get("employee_name"))
    ts = db.tasks(p["id"])
    asg = db.assignees(p["id"])
    return HOST.json_response({"ok": True, "assignees": asg, "tasks": ts,
                               "readiness": engine.readiness(p, ts, asg, today=_today())})


# ---------------------------------------------------------------- publish (R4 + R5) ---------

async def publish(request):
    """One-way, stamped, audited. The gate is engine.readiness() and nothing else — a
    structural test asserts this function's source still mentions it, so no future edit can
    add a publish path that skips it."""
    if not can_publish(request):
        return _deny("النشر للمالك فقط")
    b = await _body(request)
    p = db.project(b.get("id")) if b.get("id") else None
    if not p:
        return _refuse("ما لقيت المشروع")
    if (p.get("status") or "") != "active":
        return _refuse("الوحدة منشورة أصلاً أو منسحب منها")
    ts = db.tasks(p["id"])
    asg = db.assignees(p["id"])
    r = engine.readiness(p, ts, asg, today=_today())
    if not r["ok"]:
        return _refuse("ما ينفع النشر — فيه نواقص", blockers=r["blockers"])
    snapshot = engine.handover_snapshot(p, ts, asg)
    who = _actor(request)
    p = db.publish(p["id"], snapshot, who)

    # Best effort, each in its own try/except. A Discord outage does NOT un-publish a unit.
    try:
        _link_schedule_apartment(p, asg)
    except Exception:
        traceback.print_exc()
    try:
        if HOST.notify:
            HOST.notify({"kind": "publish", "project_id": p["id"],
                         "text": engine.publish_card(p, snapshot)})
    except Exception:
        traceback.print_exc()
    try:
        if HOST.log_event:
            HOST.log_event("ops", "ضم الوحدات · نُشرت %s (%s)"
                           % (p.get("unit_name"), p.get("ref")))
    except Exception:
        traceback.print_exc()

    return HOST.json_response({"ok": True, "project": p, "handover": snapshot,
                               "text": engine.handover_text(p, snapshot)})


def _link_schedule_apartment(p, asg):
    """Hand the unit to the Employee Calendar: create its apartment row (owned by the PRIMARY
    assignee) if it is not already there. Never overwrites an existing row — the calendar is
    its own source of truth and the owner may already have set it up by hand."""
    from schedule import db as sdb
    name = p.get("unit_name") or ""
    lid = p.get("listing_id")
    for a in sdb.apartments():
        if (lid is not None and a.get("listing_id") is not None
                and str(a["listing_id"]) == str(lid)):
            return
        if a.get("name") == name:
            return
    primary = next((a for a in asg if int(a.get("is_primary") or 0) == 1), None) or \
        (asg[0] if asg else None)
    sdb.execute("INSERT INTO schedule_apartments (name, owner_id, listing_id, sort_order, "
                "created_at) VALUES (?,?,?,?,?)",
                (name, (primary or {}).get("employee_id"), lid, 999, db.now_iso()))


# ---------------------------------------------------------------- the employee link ---------

def _emp_context(a, p, tasks):
    """What the assigned employee sees. An ALLOW-LIST, built field by field.

    The client's phone and email are deliberately absent: this link carries no login and gets
    forwarded around, so it must never leak a client's contact details. Same reasoning as the
    public team calendar, which strips the leave type and note.
    """
    return {
        "ok": True,
        "employee": {"name": a.get("employee_name")},
        "project": {
            "ref": p.get("ref"),
            "unit_name": p.get("unit_name"),
            "district": p.get("district"),
            "unit_kind": p.get("unit_kind"),
            "bedrooms": p.get("bedrooms"),
            "handover_target": p.get("handover_target"),
            "client_name": p.get("client_name"),
            "client_type": p.get("client_type"),
            "stage": p.get("stage"),
            "stage_label": catalogue.STAGE_LABEL.get(p.get("stage") or "", ""),
            "status": p.get("status"),
        },
        "handover": {
            "access_notes": p.get("access_notes"),
            "wifi_notes": p.get("wifi_notes"),
            "house_rules": p.get("house_rules"),
            "checkin_time": p.get("checkin_time"),
            "checkout_time": p.get("checkout_time"),
        },
        "tasks": [{"id": t["id"], "catalogue_key": t.get("catalogue_key"),
                   "stage": t.get("stage"),
                   "stage_label": catalogue.STAGE_LABEL.get(t.get("stage") or "", ""),
                   "seq": t.get("seq"), "title_ar": t.get("title_ar"),
                   "gate": t.get("gate"), "resolution": t.get("resolution"),
                   "reason": t.get("reason")} for t in tasks],
        "progress": engine.progress(db.tasks(p["id"])),
        "buddy": None,
        "readonly": (p.get("status") or "") != "active",
        "stages": _stages_meta(),
    }


BAD_TOKEN = "الرابط ما عاد شغّال — كلّم مدير الحسابات"


async def api_token_get(request):
    token = request.match_info.get("token") if hasattr(request, "match_info") else None
    a = db.assignee_by_token(token)
    if not a:
        return _refuse(BAD_TOKEN)
    p = db.project(a["project_id"])
    if not p:
        return _refuse(BAD_TOKEN)
    mine = db.tasks(p["id"], assignee_id=a["employee_id"])
    ctx = _emp_context(a, p, mine)
    other = [o for o in db.assignees(p["id"])
             if int(o["employee_id"]) != int(a["employee_id"])]
    ctx["buddy"] = other[0]["employee_name"] if other else None
    return HOST.json_response(ctx)


async def api_token_submit(request):
    """The employee resolves ONE of their OWN tasks. Both the project and the assignee are
    re-checked server-side on every call — the id in the body is never trusted."""
    b = await _body(request)
    a = db.assignee_by_token(b.get("token"))
    if not a:
        return _refuse(BAD_TOKEN)
    p = db.project(a["project_id"])
    if not p:
        return _refuse(BAD_TOKEN)
    if (p.get("status") or "") != "active":
        return _refuse("الوحدة انسلّمت — شكرًا")
    t = db.task(b.get("task_id")) if b.get("task_id") else None
    if (not t or int(t.get("project_id")) != int(p["id"])
            or t.get("assignee_id") is None
            or int(t["assignee_id"]) != int(a["employee_id"])):
        return _refuse("هذي المهمة مو مسندة لك")
    res = (b.get("resolution") or "").strip()
    if res not in RESOLUTIONS:
        return _refuse("اختر: تم أو ما ينطبق أو متوقف")
    reason = (b.get("reason") or "").strip()
    if res in NEEDS_REASON and not reason:
        return _refuse("اكتب السبب — «ما ينطبق» و«متوقف» لازم لها سبب")
    who = "%s (رابط)" % a.get("employee_name")
    t = db.resolve_task(t["id"], res, reason, who)
    label = {"done": "تم", "na": "ما ينطبق", "blocked": "متوقف"}[res]
    db.log(p["id"], who, "%s: %s%s" % (label, t.get("title_ar") or "",
                                       (" — %s" % reason) if reason else ""))
    mine = db.tasks(p["id"], assignee_id=a["employee_id"])
    return HOST.json_response({"ok": True, "task": t, "tasks": mine,
                               "progress": engine.progress(db.tasks(p["id"]))})


# ---------------------------------------------------------------- pages ---------------------

async def handle_page(request):
    return HOST.web.Response(text=page.ONBOARDING_PAGE_HTML, content_type="text/html")


async def handle_emp_page(request):
    return HOST.web.Response(text=emp_page.EMP_PAGE_HTML, content_type="text/html")


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    g("/api/onb/list", _safe(api_list))
    g("/api/onb/get", _safe(api_get))
    g("/api/onb/readiness", _safe(api_readiness))
    g("/api/onb/employees", _safe(api_employees))
    g("/api/onb/handover", _safe(api_handover))
    p("/api/onb/create", _safe(api_create))
    p("/api/onb/update", _safe(api_update))
    p("/api/onb/walk-away", _safe(api_walk_away))
    p("/api/onb/task/resolve", _safe(api_task_resolve))
    p("/api/onb/task/assign", _safe(task_assign))
    p("/api/onb/assignee/add", _safe(api_assignee_add))
    p("/api/onb/assignee/remove", _safe(api_assignee_remove))
    p("/api/onb/publish", _safe(publish))
    # The assigned employee's phone link: NO login, the token is the credential (same shape as
    # the ops appeal link). The READ deliberately sits OUTSIDE the /api/onb/ prefix, because
    # that prefix is role-gated in bot.py's _ROLE_READ_RULES and would 403 an anonymous phone.
    # The write keeps its spec'd path and is listed in _ROLE_EXEMPT_WRITES (exact-path match).
    g("/api/onb-t/{token}", _safe_public(api_token_get))
    p("/api/onb/t/submit", _safe_public(api_token_submit))
    # The page itself is plain HTML with no data in it (same as the ERP login form). Serving
    # it unwrapped is what lets it render the Arabic "sign in first" state — every /api/onb/*
    # call it makes is the thing that actually enforces the login.
    g("/onboarding", handle_page)
    g("/onb/t/{token}", handle_emp_page)
