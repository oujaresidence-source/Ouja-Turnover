# -*- coding: utf-8 -*-
"""
ops.routes — «نظام الالتزام» endpoints.

WHAT A HUMAN IS ALLOWED TO DO HERE, exhaustively:
    excuse  — before the deadline, block a warning that has not happened yet
    waive   — forgive an obligation, or void a warning that already exists, with a reason
    decide  — accept / reject / escalate an appeal
There is deliberately NO endpoint that issues a warning. `db.issue_warning` is not imported
by any handler in this file; only the deadline path in notify.tick() can reach it.

Every write also re-checks the role, and every rejection needs a written reason. The two
appeal endpoints the employee uses are token-gated and need NO login (same public pattern as
/team-calendar), because a person who has just been warned should not have to hunt for a
password to answer it.
"""

import json
import traceback

from . import db, engine, notify, page, scorecard, turnover
from .host import HOST

EDIT_ROLES = ("admin", "ops")


# ------------------------------------------------------------------ guards

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


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def _deny():
    return HOST.json_response({"ok": False, "error": "غير مصرّح لك بالتعديل"}, 403)


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
    """Token-gated, NO login. Full detail stays in the server log; the visitor gets a
    generic Arabic line."""
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


# ================================================================== plain logic
# Everything below is callable without aiohttp, so the lifecycle tests exercise the real
# rules instead of a mock of them.

def do_excuse(employee, period_key, reason, by):
    """«عذر مسبق» — a leader blocks a warning BEFORE it is issued. Refused after the fact:
    once a warning exists the honest route is a waive or an appeal, both of which leave a
    record of who forgave what."""
    if not (employee or "").strip() or not (period_key or "").strip():
        return {"ok": False, "error": "ناقص اسم الموظف أو الأسبوع"}
    if not (reason or "").strip():
        return {"ok": False, "error": "لازم تكتب سبب العذر"}
    oid = db.obligation_id(notify.WEEKLY_KIND, employee, period_key)
    ob = db.obligation(oid)
    if not ob:
        return {"ok": False, "error": "ما فيه التزام مسجّل لهذا الأسبوع"}
    if db.warning_for_obligation(oid):
        return {"ok": False, "error": "انسجل إنذار بالفعل — استخدم «إلغاء الإنذار» أو الاعتراض"}
    if ob["status"] not in ("pending", "missed"):
        return {"ok": False, "error": "الحالة الحالية: %s — ما يحتاج عذر" % ob["status"]}
    db.set_status(oid, "excused", waived_by=by, waived_reason=reason)
    notify._send({"kind": "mercy", "employee": employee,
                  "employee_did": ob.get("employee_did"), "period_key": period_key,
                  "text": notify.mercy_dm("excused", employee, period_key, reason),
                  "channel": notify.channel_name(employee)})
    return {"ok": True, "obligation": db.obligation(oid)}


def parse_discord_id(raw):
    """Accept whatever the owner has in their hand: a raw id (1134973768159203418), a pasted
    mention (<@1134…> or <@!1134…>), or the same with spaces. Returns '' for a deliberate
    clear, or None when the text is not an id at all.

    Discord ids are snowflakes — 17-19 digits today, so 15-25 is a deliberately generous
    window that still rejects a phone number or a typo'd name."""
    s = (raw or "").strip()
    if not s:
        return ""
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits or not (15 <= len(digits) <= 25):
        return None
    return digits


def do_set_identity(employee, raw_id, by):
    """Tell the system how to reach one person. The ONLY way a name enters this table is by
    already being in the Employee Calendar — you cannot invent a person here."""
    employee = (employee or "").strip()
    known = [e["name"] for e in notify.employees()]
    if employee not in known:
        return {"ok": False, "error": "هذا الاسم مو موجود في تقويم الموظفين"}
    did = parse_discord_id(raw_id)
    if did is None:
        return {"ok": False, "error": "هذا مو معرّف ديسكورد — لازم أرقام فقط (١٧ رقم تقريباً)"}
    if not did:
        # Recorded as a deliberate blank, NOT deleted — otherwise assignments.json would
        # refill the box with the very number the owner just removed.
        db.set_identity(employee, "", by)
        return {"ok": True, "employee": employee, "discord_id": "",
                "message": "انشال المعرّف — هذا الشخص ما راح يوصله شي وما ينسجل عليه إنذار"}
    taken = [n for n, (v, _s) in notify._id_map().items()
             if v == did and n != notify._norm(employee)]
    if taken:
        return {"ok": False, "error": "هذا المعرّف مربوط بموظف ثاني — كل واحد له معرّف خاص"}
    db.set_identity(employee, did, by)
    return {"ok": True, "employee": employee, "discord_id": did,
            "message": "انحفظ ✅ من الحين بتوصله التذكيرات"}


def do_waive(warning_id, reason, by):
    """Forgive a warning that already exists. Commission is recomputed in the same breath —
    a voided warning that still shows as money lost is worse than no mercy at all."""
    if not (reason or "").strip():
        return {"ok": False, "error": "لازم تكتب سبب الإلغاء"}
    w = db.warning(warning_id)
    if not w:
        return {"ok": False, "error": "ما لقينا الإنذار"}
    if w["status"] != "active":
        return {"ok": False, "error": "الإنذار حالته %s — ما ينلغى مرة ثانية" % w["status"]}
    db.void_warning(warning_id, by, reason)
    led = db.recompute_commission(w["employee"], w["month_key"])
    notify._send({"kind": "mercy", "employee": w["employee"], "employee_did": w.get("employee_did"),
                  "text": notify.appeal_stage_dm("s1", w["employee"], "accepted", reason),
                  "channel": notify.channel_name(w["employee"])})
    return {"ok": True, "warning": db.warning(warning_id), "commission": led}


def do_open_appeal(token, text, evidence=None):
    """The employee answers. Token-gated, no login."""
    w = db.warning_by_token(token)
    if not w:
        return {"ok": False, "error": "الرابط غير صحيح أو انتهى"}
    if w["status"] != "active":
        return {"ok": False, "error": "هذا الإنذار ملغي أصلاً — ما يحتاج اعتراض"}
    if not (text or "").strip():
        return {"ok": False, "error": "اكتب لنا وش صار"}
    a = db.open_appeal(w["id"], text, evidence or [], notify.appeal_sla_hours())
    db.add_decision(a["id"], "s1", "opened", w["employee"], (text or "")[:300])
    notify._send({"kind": "appeal", "employee": w["employee"],
                  "employee_did": w.get("employee_did"),
                  "text": "استلمنا اعتراضك ✅ راح يوصل " + notify.APPROVER_NAMES["s1"] +
                          " ولازم يرد خلال ٢٤ ساعة.",
                  "approver_id": notify.approver_ids().get("s1", ""),
                  "approver_text": notify.appeal_notice("s1", w["employee"], w["id"], text)})
    return {"ok": True, "appeal": db.appeal(a["id"])}


def do_decide_appeal(appeal_id, action, reason, by):
    """accept | reject | escalate. A rejection with no written reason is REFUSED — silence
    from an approver reads to the employee exactly like contempt."""
    a = db.appeal(appeal_id)
    if not a:
        return {"ok": False, "error": "ما لقينا الاعتراض"}
    if a["stage"] == "closed":
        return {"ok": False, "error": "الاعتراض مقفل"}
    w = db.warning(a["warning_id"])
    if not w:
        return {"ok": False, "error": "ما لقينا الإنذار"}

    if action == "reject" and not engine.can_reject(reason):
        return {"ok": False, "error": "لازم تكتب سبب الرفض — الرفض بدون سبب مرفوض"}
    if action == "accept" and not (reason or "").strip():
        return {"ok": False, "error": "لازم تكتب سبب القبول"}

    stage = a["stage"]
    if action == "accept":
        db.void_warning(w["id"], by, reason)
        led = db.recompute_commission(w["employee"], w["month_key"])
        db.add_decision(appeal_id, stage, "accepted", by, reason)
        db.move_appeal(appeal_id, "closed", outcome="accepted")
        notify._send({"kind": "appeal", "employee": w["employee"],
                      "employee_did": w.get("employee_did"),
                      "text": notify.appeal_stage_dm(stage, w["employee"], "accepted", reason),
                      "channel": notify.channel_name(w["employee"])})
        return {"ok": True, "outcome": "accepted", "commission": led,
                "warning": db.warning(w["id"])}

    if action == "reject":
        db.add_decision(appeal_id, stage, "rejected", by, reason)
        db.move_appeal(appeal_id, "closed", outcome="rejected")
        notify._send({"kind": "appeal", "employee": w["employee"],
                      "employee_did": w.get("employee_did"),
                      "text": notify.appeal_stage_dm(stage, w["employee"], "rejected", reason),
                      "channel": notify.channel_name(w["employee"])})
        return {"ok": True, "outcome": "rejected"}

    nxt = engine.next_stage(stage)
    db.add_decision(appeal_id, stage, "escalated", by, reason or "")
    db.move_appeal(appeal_id, nxt, notify.appeal_sla_hours())
    notify._send({"kind": "appeal", "employee": w["employee"],
                  "employee_did": w.get("employee_did"),
                  "text": notify.appeal_stage_dm(nxt, w["employee"], "escalated", reason),
                  "approver_id": notify.approver_ids().get(nxt, ""),
                  "approver_text": notify.appeal_notice(nxt, w["employee"], w["id"],
                                                        a.get("employee_text"))})
    return {"ok": True, "outcome": "escalated", "stage": nxt}


def state(period_key=None):
    """Everything /compliance renders. Read-only."""
    now = db.now_dt()
    period = period_key or notify.current_period(now)
    month = engine.month_key(now.date())
    roster = notify.employees()
    rows = []
    for e in roster:
        oid = db.obligation_id(notify.WEEKLY_KIND, e["name"], period)
        ob = db.obligation(oid) or {}
        active = db.warnings_for(e["name"], "active")
        led = db.commission(e["name"], month) or {}
        rows.append({
            "employee": e["name"], "reachable": e["reachable"],
            "did": e["did"], "id_source": e.get("source_ar") or "",
            "status": ob.get("status") or "—",
            "due_at": ob.get("due_at") or notify.due_at(period).isoformat(timespec="minutes"),
            "active_warnings": len(active),
            "multiplier": led.get("multiplier",
                                  engine.compute_multiplier(len(active))),
            "sent": db.sent_levels(oid),
        })
    appeals = []
    for a in db.open_appeals():
        w = db.warning(a["warning_id"]) or {}
        appeals.append({"id": a["id"], "employee": w.get("employee"), "stage": a["stage"],
                        "stage_name": notify.APPROVER_NAMES.get(a["stage"], a["stage"]),
                        "stage_due_at": a.get("stage_due_at"),
                        "text": a.get("employee_text"),
                        "decisions": db.appeal_decisions(a)})
    return {
        "ok": True, "period": period, "month": month,
        "dryrun": notify.dryrun(), "enabled": notify.enabled(),
        "due_at": notify.due_at(period).isoformat(timespec="minutes"),
        "rows": rows,
        "warnings": db.all_warnings(200),
        "appeals": appeals,
        "unreachable": db.unreachable_report(),
        "dry_log": db.dry_rows(200),
        "summary": notify.monthly_summary(month)["text"],
        "turnover": turnover.state(),
    }


# ================================================================== handlers

async def api_state(request):
    p = request.query.get("period") or None
    return HOST.json_response(state(p))


async def api_tick(request):
    """Owner-triggered pass of the ladder — the button that fills the dry-run log without
    waiting for the 5-minute loop."""
    if not can_edit(request):
        return _deny()
    return HOST.json_response({"ok": True, "report": notify.tick()})


async def api_excuse(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return HOST.json_response(do_excuse(b.get("employee"), b.get("period_key"),
                                        b.get("reason"), _actor(request)))


async def api_waive(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return HOST.json_response(do_waive(b.get("warning_id"), b.get("reason"), _actor(request)))


async def api_identity(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return HOST.json_response(do_set_identity(b.get("employee"), b.get("discord_id"),
                                              _actor(request)))


async def api_decide(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return HOST.json_response(do_decide_appeal(b.get("appeal_id"), (b.get("action") or "").strip(),
                                               b.get("reason"), _actor(request)))


async def api_turnover(request):
    return HOST.json_response({"ok": True, **turnover.state(request.query.get("date"))})


async def api_turnover_tick(request):
    if not can_edit(request):
        return _deny()
    return HOST.json_response({"ok": True, "report": turnover.tick()})


# ---- phase 3 «كرت التقييم» ----

async def api_scorecard(request):
    """The owner sees the score AND the raw numbers behind every single line."""
    month = request.query.get("month") or engine.month_key(db.now_dt().date())
    stored = db.scorecards(month)
    cards = [json.loads(r["card_json"]) for r in stored]
    for r, c in zip(stored, cards):
        c["released_at"] = r.get("released_at")
    return HOST.json_response({"ok": True, "month": month, "cards": cards,
                               "dryrun": scorecard.dryrun(),
                               "enabled": scorecard.enabled()})


async def api_scorecard_compute(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    month = (b.get("month") or engine.month_key(db.now_dt().date()))
    rep = scorecard.gather(month)
    scorecard.save(month, rep.get("cards") or [], _actor(request))
    return HOST.json_response({"ok": True, **rep})


async def api_scorecard_override(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return HOST.json_response(scorecard.override(b.get("month"), b.get("employee"),
                                                 b.get("line"), b.get("score"),
                                                 b.get("reason"), _actor(request)))


async def api_scorecard_release(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return HOST.json_response(scorecard.release(b.get("month"), _actor(request)))


async def api_summary(request):
    return HOST.json_response({"ok": True, **notify.monthly_summary(request.query.get("month"))})


# ---- the two the employee touches: token only, no login ----

async def api_appeal_get(request):
    token = request.match_info.get("token") or request.query.get("token") or ""
    w = db.warning_by_token(token)
    if not w:
        return HOST.json_response({"ok": False, "error": "الرابط غير صحيح أو انتهى"}, 200)
    a = db.appeal_for_warning(w["id"])
    return HOST.json_response({
        "ok": True,
        "warning": {"id": w["id"], "employee": w["employee"], "issued_at": w["issued_at"],
                    "reason_ar": w["reason_ar"], "status": w["status"]},
        "appeal": ({"id": a["id"], "stage": a["stage"],
                    "stage_name": notify.APPROVER_NAMES.get(a["stage"], a["stage"]),
                    "opened_at": a["opened_at"], "outcome": a.get("outcome"),
                    "decisions": db.appeal_decisions(a)} if a else None),
        "stages": [notify.APPROVER_NAMES[s] for s in engine.APPEAL_STAGES],
    })


async def api_appeal_submit(request):
    b = await _body(request)
    token = (b.get("token") or request.match_info.get("token") or "")
    ev = b.get("evidence")
    if isinstance(ev, str):
        try:
            ev = json.loads(ev)
        except Exception:
            ev = [ev]
    return HOST.json_response(do_open_appeal(token, b.get("text"), ev if isinstance(ev, list) else []))


# ---- pages ----

async def handle_compliance(request):
    if not HOST.dash_auth(request):
        return HOST.web.Response(text=page.LOGIN_HINT_HTML, content_type="text/html",
                                 charset="utf-8", status=401)
    return HOST.web.Response(text=page.COMPLIANCE_HTML, content_type="text/html", charset="utf-8")


async def handle_appeal_page(request):
    return HOST.web.Response(text=page.APPEAL_HTML, content_type="text/html", charset="utf-8")


def register(app):
    g, p = app.router.add_get, app.router.add_post
    # employee-facing, token only (no login) — same public pattern as /team-calendar
    g("/appeal/{token}", handle_appeal_page)
    g("/api/ops/appeal/{token}", _safe_public(api_appeal_get))
    p("/api/ops/appeal/submit", _safe_public(api_appeal_submit))
    # owner / leader surface — login, and every write re-checks admin|ops
    g("/compliance", handle_compliance)
    g("/api/ops/state", _safe(api_state))
    g("/api/ops/summary", _safe(api_summary))
    g("/api/ops/turnover", _safe(api_turnover))
    p("/api/ops/turnover-tick", _safe(api_turnover_tick))
    g("/api/ops/scorecard", _safe(api_scorecard))
    p("/api/ops/scorecard-compute", _safe(api_scorecard_compute))
    p("/api/ops/scorecard-override", _safe(api_scorecard_override))
    p("/api/ops/scorecard-release", _safe(api_scorecard_release))
    p("/api/ops/tick", _safe(api_tick))
    p("/api/ops/excuse", _safe(api_excuse))
    p("/api/ops/identity", _safe(api_identity))
    p("/api/ops/waive", _safe(api_waive))
    p("/api/ops/appeal/decide", _safe(api_decide))


def register_routes(app):
    register(app)
