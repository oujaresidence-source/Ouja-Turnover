# -*- coding: utf-8 -*-
"""
onboarding.engine — every rule of «ضم الوحدات», as pure functions over plain dicts.

No DB, no HTTP, no event loop, no clock it did not receive. That is deliberate and it is the
reason schedule/engine.py has never regressed: the tests drive the real rules directly, and the
routes are left with nothing to get wrong except plumbing.

The single most important promise here is `readiness()`. It is the ONLY producer of a publish
blocker in this package. The API, the account manager's page and the Discord handover message
all render this one list, so they cannot drift apart — the same lesson decor learned with
capability_stamp (CLAUDE.md).
"""

import datetime

from . import catalogue

# Build spec R3. Three owners means no owner; two means a primary and a backup. This lives HERE,
# not in a route handler — a rule that lives in one handler is a rule the next handler forgets.
MAX_OPS_PER_PROJECT = 2

# Below the standard band (20–25%) the CEO has to sign it off before the unit can be published.
STANDARD_RATE_MIN = 20.0


def _blank(v):
    """Empty for gate purposes: None, '', whitespace. 0 and 0.0 are REAL answers and must not
    read as missing — a zero cleaning fee is a decision, not a hole."""
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    return False


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- assignees (R3) ------------

def can_add_assignee(current, employee_id):
    """(ok, error_ar) for adding one person to a project.

    The two refusals are DIFFERENT messages on purpose: "already on it" is not a capacity
    problem and must never be reported as one, or the account manager deletes somebody to make
    room that was never needed.
    """
    current = list(current or [])
    try:
        want = int(employee_id)
    except (TypeError, ValueError):
        return False, "رقم الموظف غير صحيح"
    for a in current:
        try:
            if int(a.get("employee_id")) == want:
                return False, "هذا الموظف مضاف أصلاً على هالمشروع"
        except (TypeError, ValueError):
            continue
    if len(current) >= MAX_OPS_PER_PROJECT:
        names = "، ".join(str(a.get("employee_name") or "") for a in current)
        return False, ("ما ينفع أكثر من موظفين اثنين على نفس المشروع. "
                       "الحاليين: %s — احذف واحد قبل لا تضيف غيره." % names)
    return True, ""


# ---------------------------------------------------------------- the publish gate (R4) -----

def _today_iso(today=None):
    if today is None:
        return datetime.date.today().isoformat()
    if isinstance(today, datetime.datetime):
        return today.date().isoformat()
    if isinstance(today, datetime.date):
        return today.isoformat()
    return str(today)[:10]


def readiness(project, tasks, assignees, today=None):
    """{'ok': bool, 'blockers': [{code, ar, field|stage, count?}]}

    Ordered, deterministic, and the ONLY place a blocker is born. `field` / `stage` is what the
    page uses to jump the user straight to the thing that fixes it — that is R4 and it is not
    decoration.
    """
    p = project or {}
    tasks = list(tasks or [])
    assignees = list(assignees or [])
    out = []

    def add(code, ar, **kw):
        b = {"code": code, "ar": ar}
        b.update(kw)
        out.append(b)

    # -- client ------------------------------------------------------------------------------
    if any(_blank(p.get(k)) for k in ("client_name", "client_type", "client_whatsapp")):
        add("client_incomplete", "بيانات العميل ناقصة", field="client_name")
    if (p.get("client_type") or "") == "tenant" and p.get("sublet_ok") is None:
        add("sublet_unchecked", "ما تم فحص بند التأجير من الباطن", field="sublet_ok")

    # -- unit --------------------------------------------------------------------------------
    if any(_blank(p.get(k)) for k in ("unit_name", "district", "unit_kind", "bedrooms",
                                      "furnish_state")):
        add("unit_incomplete", "بيانات الوحدة ناقصة", field="unit_name")

    # -- commercial --------------------------------------------------------------------------
    if any(_blank(p.get(k)) for k in ("strategy", "ouja_rate_pct", "cleaning_sar",
                                      "contract_signed_at")):
        add("terms_incomplete", "الشروط التجارية أو العقد ناقص", field="strategy")
    rate = _num(p.get("ouja_rate_pct"))
    if rate is not None and rate < STANDARD_RATE_MIN and (p.get("ceo_approval") or "") != "approved":
        add("ceo_pending", "نسبة أقل من القياسي تحتاج اعتماد الرئيس التنفيذي", field="ceo_approval")

    # -- licence -----------------------------------------------------------------------------
    if _blank(p.get("license_no")) or _blank(p.get("license_expiry")):
        add("license_missing", "رقم الرخصة أو تاريخ انتهائها ناقص", field="license_no")
    else:
        exp = str(p.get("license_expiry"))[:10]
        if exp < _today_iso(today):
            add("license_expired", "الرخصة منتهية", field="license_expiry")

    # -- photos ------------------------------------------------------------------------------
    try:
        approved = int(p.get("photos_approved") or 0)
    except (TypeError, ValueError):
        approved = 0
    if _blank(p.get("photos_url")) or approved != 1:
        add("photos_missing", "الصور مو مرفوعة أو مو معتمدة", field="photos_url")

    # -- the handover package: the whole reason this feature exists --------------------------
    if any(_blank(p.get(k)) for k in ("access_notes", "wifi_notes", "house_rules",
                                      "checkin_time", "checkout_time")):
        add("handover_incomplete", "ملف التسليم ناقص — العمليات بترجع تسألك", field="access_notes")

    # -- people ------------------------------------------------------------------------------
    if len(assignees) == 0:
        add("no_assignee", "ما فيه أحد من فريق العمليات مسؤول عن الوحدة", field="assignees")
    elif len(assignees) > MAX_OPS_PER_PROJECT:
        add("too_many_assignees", "أكثر من موظفين اثنين على المشروع", field="assignees")

    # -- tasks -------------------------------------------------------------------------------
    gate_tasks = [t for t in tasks if int(t.get("gate") or 0) == 1]
    n_open = sum(1 for t in gate_tasks if (t.get("resolution") or "open") == "open")
    if n_open:
        add("open_gate_tasks", "فيه %d مهمة أساسية ما انحلّت" % n_open, stage="tasks", count=n_open)
    n_blocked = sum(1 for t in gate_tasks if (t.get("resolution") or "") == "blocked")
    if n_blocked:
        add("blocked_gate_tasks", "فيه %d مهمة أساسية متوقفة" % n_blocked, stage="tasks",
            count=n_blocked)
    n_unreasoned = sum(1 for t in tasks
                       if (t.get("resolution") or "") in ("na", "blocked") and _blank(t.get("reason")))
    if n_unreasoned:
        add("unreasoned_resolution", "فيه %d مهمة معلّمة بدون سبب" % n_unreasoned, stage="tasks",
            count=n_unreasoned)

    return {"ok": len(out) == 0, "blockers": out}


# ---------------------------------------------------------------- progress ------------------

def progress(tasks):
    """(done + na) / total as an int percent, `ongoing` excluded. Blocked counts as NOT done —
    a stalled task is not progress, and rounding it away is how a project looks finished while
    somebody is still waiting on a supplier."""
    rows = [t for t in (tasks or []) if (t.get("stage") or "") != "ongoing"]
    if not rows:
        return 0
    resolved = sum(1 for t in rows if (t.get("resolution") or "open") in ("done", "na"))
    return int(round(100.0 * resolved / len(rows)))


def stage_counts(tasks):
    """{stage: {resolved, total}} for the accordion headers, in catalogue stage order."""
    out = {}
    for s in catalogue.UNIT_STAGES:
        out[s] = {"resolved": 0, "total": 0}
    for t in (tasks or []):
        s = t.get("stage") or ""
        if s not in out:
            continue
        out[s]["total"] += 1
        if (t.get("resolution") or "open") in ("done", "na"):
            out[s]["resolved"] += 1
    return out


# ---------------------------------------------------------------- the Discord card (R8) -----

MAX_CARD_TASKS = 12
NL = chr(10)


def assignment_card(project, employee, tasks, link):
    """The Arabic Discord message for ONE batch of newly-assigned tasks, for ONE person.

    Pure — bot.py never composes Arabic. Newlines are chr(10); this function contains no
    backslash escape and a test asserts the output carries none either.

    An unreachable person (no Discord id) still gets a visible card under their plain name. A
    silent skip would hide the hole; a broken '<@>' would look like a bug. Same principle as
    ops.notify.employees().
    """
    p = project or {}
    e = employee or {}
    rows = list(tasks or [])
    did = str(e.get("employee_did") or "").strip()
    name = str(e.get("employee_name") or "").strip()
    who = ("<@%s>" % did) if did else name

    head = "🏠 %s   ·   %s" % (p.get("unit_name") or "", p.get("ref") or "")
    lines = [head, "%s — انسند لك %d مهام" % (who, len(rows))]

    shown = rows[:MAX_CARD_TASKS]
    hidden = len(rows) - len(shown)
    # group by stage, in catalogue stage order — never in whatever order the rows arrived
    for stage in catalogue.STAGE_ORDER:
        grp = [t for t in shown if (t.get("stage") or "") == stage]
        if not grp:
            continue
        lines.append(catalogue.STAGE_LABEL.get(stage, stage))
        for t in sorted(grp, key=lambda r: (int(r.get("seq") or 0), str(r.get("catalogue_key") or ""))):
            mark = "🔒 " if int(t.get("gate") or 0) == 1 else ""
            lines.append("  %s%s" % (mark, t.get("title_ar") or ""))
    if hidden > 0:
        lines.append("… و%d مهمة ثانية — كلها في الرابط" % hidden)

    meta = []
    if p.get("client_name"):
        meta.append("العميل: %s" % p["client_name"])
    if p.get("district"):
        meta.append("الحي: %s" % p["district"])
    if p.get("handover_target"):
        meta.append("التسليم المستهدف: %s" % p["handover_target"])
    if meta:
        lines.append(" · ".join(meta))

    lines.append("كل التفاصيل والتحديث من هنا:")
    lines.append(str(link or ""))
    return NL.join(lines)


def publish_card(project, snapshot):
    """The handover summary posted into the project's room at publish."""
    p = project or {}
    s = snapshot or {}
    lines = [
        "✅ %s   ·   %s" % (p.get("unit_name") or "", p.get("ref") or ""),
        "الوحدة انسلّمت لفريق العمليات.",
    ]
    people = ["%s%s" % (a.get("employee_name") or "", " (الأساسي)" if a.get("is_primary") else "")
              for a in (s.get("assignees") or [])]
    if people:
        lines.append("المسؤولون: %s" % "، ".join(people))
    h = s.get("handover") or {}
    for label, key in (("الدخول", "access_notes"), ("الواي فاي", "wifi_notes"),
                       ("قواعد المنزل", "house_rules")):
        if h.get(key):
            lines.append("%s: %s" % (label, h[key]))
    if h.get("checkin_time") or h.get("checkout_time"):
        lines.append("الدخول %s · الخروج %s" % (h.get("checkin_time") or "—",
                                                h.get("checkout_time") or "—"))
    if p.get("published_by"):
        lines.append("نشرها: %s" % p["published_by"])
    return NL.join(lines)


# ---------------------------------------------------------------- the frozen snapshot (R5) --

def handover_snapshot(project, tasks, assignees):
    """The JSON frozen into onb_handover at publish. Written ONCE, never updated — an owner
    statement or a dispute months later needs to know what was actually handed over, not what
    the record looks like today."""
    p = project or {}

    def g(*keys):
        return {k: p.get(k) for k in keys}

    return {
        "ref": p.get("ref"),
        "client": g("client_name", "client_type", "client_whatsapp", "client_email", "sublet_ok"),
        "unit": g("unit_name", "district", "unit_kind", "bedrooms", "area_sqm", "listing_id",
                  "amenities", "furnish_state"),
        "terms": g("strategy", "ouja_rate_pct", "cleaning_sar", "cleaning_absorbed",
                   "contract_signed_at", "ceo_approval", "ceo_approval_note"),
        "license": g("license_no", "license_expiry"),
        "photos": g("photos_url", "photos_approved"),
        "handover": g("access_notes", "wifi_notes", "house_rules", "checkin_time",
                      "checkout_time", "client_promises", "client_prefs"),
        "assignees": [{"employee_id": a.get("employee_id"),
                       "employee_name": a.get("employee_name"),
                       "is_primary": int(a.get("is_primary") or 0)}
                      for a in (assignees or [])],
        "tasks": [{"catalogue_key": t.get("catalogue_key"), "stage": t.get("stage"),
                   "title_ar": t.get("title_ar"), "owner_role": t.get("owner_role"),
                   "gate": int(t.get("gate") or 0),
                   "resolution": t.get("resolution") or "open", "reason": t.get("reason"),
                   "assignee_name": t.get("assignee_name"),
                   "resolved_by": t.get("resolved_by"), "resolved_at": t.get("resolved_at")}
                  for t in (tasks or [])],
        "progress": progress(tasks),
        "pmo_project_id": p.get("pmo_project_id"),
    }


def handover_text(project, snapshot):
    """The plain-text rendering the «نسخ ملف التسليم» button copies into WhatsApp."""
    p = project or {}
    s = snapshot or {}
    h = s.get("handover") or {}
    u = s.get("unit") or {}
    c = s.get("client") or {}
    lines = ["ملف تسليم الوحدة", "%s · %s" % (p.get("unit_name") or "", p.get("ref") or ""), ""]
    lines.append("الحي: %s" % (u.get("district") or "—"))
    lines.append("النوع: %s · غرف: %s" % (u.get("unit_kind") or "—", u.get("bedrooms") or "—"))
    lines.append("العميل: %s" % (c.get("client_name") or "—"))
    lines.append("")
    lines.append("الدخول: %s" % (h.get("access_notes") or "—"))
    lines.append("الواي فاي: %s" % (h.get("wifi_notes") or "—"))
    lines.append("قواعد المنزل: %s" % (h.get("house_rules") or "—"))
    lines.append("وقت الدخول: %s · وقت الخروج: %s" % (h.get("checkin_time") or "—",
                                                      h.get("checkout_time") or "—"))
    if h.get("client_promises"):
        lines.append("وعود للعميل: %s" % h["client_promises"])
    if h.get("client_prefs"):
        lines.append("تفضيلات العميل: %s" % h["client_prefs"])
    lic = s.get("license") or {}
    lines.append("")
    lines.append("الرخصة: %s (تنتهي %s)" % (lic.get("license_no") or "—",
                                            lic.get("license_expiry") or "—"))
    people = [a.get("employee_name") or "" for a in (s.get("assignees") or [])]
    if people:
        lines.append("المسؤولون: %s" % "، ".join(people))
    return NL.join(lines)
