# -*- coding: utf-8 -*-
"""
rrdesk.routes — «طلبات سام» endpoints.

    GET  /rrdesk/static/rrdesk_tab.js   PUBLIC code, no data (the dashboard tab)
    GET  /rrdesk/health                 PUBLIC, counts only — no names, no text
    GET  /api/rrdesk/state              login + «rrdesk» read (bot.py _ROLE_READ_RULES)
    GET  /api/rrdesk/perf?period=week|month&offset=0
    GET  /api/rrdesk/request?id=<n>     one request's full timeline
    GET  /api/rrdesk/translation        cost, cache hit rate, failures, glossary
    POST /api/rrdesk/settings           ADMIN — SLAs, Sam ids, detection, cap, switches
    POST /api/rrdesk/glossary           ADMIN — the owner-editable glossary
    POST /api/rrdesk/excuse             admin/ops — MERCY only (a miss stops counting)
Every write: login + «rrdesk» write (bot.py _ROLE_WRITE_RULES) AND the role re-checked here.
There is deliberately NO endpoint that creates a miss or a warning.
"""

import datetime
import json
import os
import traceback

from . import db, engine, flow, translate
from .host import HOST

STATIC_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "rrdesk_tab.js")
_js_cache = {"mtime": None, "text": ""}
SETTINGS_ROLES = ("admin",)
MERCY_ROLES = ("admin", "ops")


def _role(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") or "viewer"
    except Exception:
        return "viewer"


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


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


# ------------------------------------------------------------------ views

def _req_view(r, now):
    age = engine.worked_minutes(db.parse(r["asked_at"]), now)
    dd = db.parse(r.get("deliv_due"))
    rd = db.parse(r.get("resp_due"))
    late = bool(r["state"] in engine.LIVE and ((r["state"] == "open" and rd and rd <= now) or (dd and dd <= now)))
    return {"id": r["id"], "seq": r.get("ticket_seq"), "code": r.get("ticket_code"),
            "channel_id": r["channel_id"], "state": r["state"], "path": r["path"],
            "asks": r["asks"], "urgent": bool(r["urgent"]), "urgent_why": r.get("urgent_why"),
            "owner": r.get("owner_name") or "", "owner_rule": r.get("owner_rule"),
            "unowned": bool(r.get("unowned")), "summary_en": r.get("summary_en") or "",
            "summary_ar": r.get("summary_ar") or "", "asked_at": r["asked_at"],
            "resp_due": r.get("resp_due"), "deliv_due": r.get("deliv_due"),
            "age_min": round(age), "late": late, "rework": r.get("rework") or 0,
            "link": flow._link(flow._card_channel(r), r.get("card_message_id"))}


def state_view(now=None):
    now = now or flow._now()
    live = db.live_requests()
    rows = [_req_view(r, now) for r in live]
    open_rows = [x for x in rows if x["state"] in engine.LIVE]
    day = datetime.datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
    month = datetime.datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
    t_day, t_month = db.translation_stats(day), db.translation_stats(month)
    return {
        "ok": True, "now": db.iso(now), "rows": rows,
        "team": {
            "open": len(open_rows),
            "awaiting_sam": len([x for x in rows if x["state"] == engine.DELIVERED]),
            "oldest_min": max([x["age_min"] for x in open_rows] or [0]),
            "late": len([x for x in open_rows if x["late"]]),
            "tickets_blocked": len({x["channel_id"] for x in open_rows}),
            "aircover_risk": len([x for x in open_rows if x["urgent_why"] == "aircover"]),
            "unowned": len([x for x in open_rows if x["unowned"]]),
            "cost_today_usd": t_day["usd"], "cost_month_usd": t_month["usd"],
            "cost_today_sar": round(t_day["usd"] * translate.SAR_PER_USD, 2),
            "cost_month_sar": round(t_month["usd"] * translate.SAR_PER_USD, 2),
        },
        "health": flow.health(now),
        "recent": [_req_view(r, now) for r in db.recent_requests(40)],
    }


def perf_view(period="week", offset=0, now=None):
    now = now or flow._now()
    off = max(0, int(offset or 0))
    if period == "month":
        y, m = now.year, now.month - off
        while m <= 0:
            m += 12
            y -= 1
        start = datetime.datetime(y, m, 1, tzinfo=now.tzinfo)
        end = datetime.datetime(y + (m // 12), (m % 12) + 1, 1, tzinfo=now.tzinfo)
        label = "%04d-%02d" % (y, m)
    else:
        monday = now.date() - datetime.timedelta(days=now.weekday()) - datetime.timedelta(weeks=off)
        start = datetime.datetime(monday.year, monday.month, monday.day, tzinfo=now.tzinfo)
        end = start + datetime.timedelta(days=7)
        label = engine.week_key(monday)
    people = flow.person_kpis(start, end, now)
    return {"ok": True, "period": period, "label": label, "start": db.iso(start), "end": db.iso(end),
            "targets": {"resp_on_time": engine.TARGETS["resp_on_time"],
                        "deliv_on_time": engine.TARGETS["deliv_on_time"],
                        "rework": engine.TARGETS["rework"], "sla": flow.sla_cfg()},
            "people": people, "min_sample": engine.MIN_SAMPLE}


def request_view(rid, now=None):
    now = now or flow._now()
    r = db.request(int(rid))
    if not r:
        return {"ok": False, "error": "not found"}
    ev = list(reversed(db.events(request_id=r["id"], limit=300)))
    return {"ok": True, "request": _req_view(r, now), "text": r.get("text") or "",
            "ladder": db.ladder_rows(r["id"]), "misses": db.misses_for(r["id"]),
            "events": [{"at": e["at"], "kind": e["kind"], "actor": e.get("actor") or "",
                        "detail": e.get("detail") or {}} for e in ev]}


def translation_view(now=None):
    now = now or flow._now()
    day = datetime.datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)
    month = datetime.datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
    terms, ver = translate.glossary()
    t_day, t_month = db.translation_stats(day), db.translation_stats(month)
    for t in (t_day, t_month):
        t["sar"] = round(t["usd"] * translate.SAR_PER_USD, 2)
    fails = [{"at": e["at"], "where": (e.get("detail") or {}).get("where") or "",
              "error": str((e.get("detail") or {}).get("e") or "")[:160]}
             for e in db.events(kinds=["tr_failed"], limit=20)]
    return {"ok": True, "today": t_day, "month": t_month, "cap": translate.daily_cap(),
            "calls_today": translate.calls_today(now),
            "price_in": translate.price_in(), "price_out": translate.price_out(),
            "failures": fails, "glossary": terms, "glossary_version": ver}


def settings_view():
    sug = db.loads(db.setting("study:last"), {}) or {}
    return {"sla": flow.sla_cfg(), "sam_ids": flow.sam_ids(),
            "sam_source": ("setting" if db.setting("sam_ids") else
                           ("env" if os.environ.get("RRDESK_SAM_IDS") else
                            ("closeouts" if db.setting("sam_ids_auto") else "none"))),
            "detect_mode": flow.detect_mode(), "threshold": flow.threshold(),
            "daily_calls": translate.daily_cap(),
            "switches": {k: flow.switch(k) for k in flow.SWITCH_DEFAULTS},
            "suggested": {"calibration": sug.get("calibration"), "at": sug.get("at"),
                          "requests": sug.get("requests"), "eval": db.loads(db.setting("eval:last"), None)}}


SLA_KEYS = tuple(engine.DEFAULT_SLA)


def save_settings(b, by):
    # refuse BEFORE writing anything: a half-saved form is worse than none
    if (b.get("switches") or {}).get("warn_live") and (b.get("confirm") or "").strip() != "تشغيل":
        return False, "اكتب «تشغيل» لتأكيد تشغيل الإنذارات الفعلية."
    for k in SLA_KEYS:
        if k in b:
            v = int(b[k])
            if not 5 <= v <= 7 * 24 * 60:
                return False, "قيمة غير منطقية: " + k
            db.set_setting("sla:" + k, str(v), by)
    if "sam_ids" in b:
        ids = [x.strip() for x in str(b["sam_ids"] or "").replace("،", ",").split(",") if x.strip().isdigit()]
        db.set_setting("sam_ids", ",".join(ids) or None, by)
    if "detect_mode" in b:
        if b["detect_mode"] not in ("auto", "confirm", "explicit"):
            return False, "detect_mode"
        db.set_setting("detect_mode", b["detect_mode"], by)
    if "threshold" in b:
        t = float(b["threshold"])
        if not 0.4 <= t <= 0.99:
            return False, "threshold"
        db.set_setting("threshold", str(t), by)
    if "daily_calls" in b:
        db.set_setting("daily_calls", str(max(0, int(b["daily_calls"]))), by)
    for k, v in (b.get("switches") or {}).items():
        if k in flow.SWITCH_DEFAULTS:
            flow.set_switch(k, bool(v), by)
    db.log("settings", actor=by, detail={k: b.get(k) for k in b if k != "confirm"})
    return True, ""


def save_glossary(terms, by):
    clean = []
    for t in terms or []:
        a, e = str(t.get("term_ar") or "").strip(), str(t.get("term_en") or "").strip()
        if t.get("deleted") and (a or e):
            clean.append({"term_ar": a, "term_en": e, "deleted": True})
        elif a and e:
            clean.append({"term_ar": a[:80], "term_en": e[:80], "note": str(t.get("note") or "")[:160]})
    db.set_setting("glossary", json.dumps(clean, ensure_ascii=False), by)
    translate.reset_glossary_cache()
    db.log("glossary", actor=by, detail={"n": len(clean)})
    return True


# ------------------------------------------------------------------ handlers

async def api_state(request):
    return _json(await _run(state_view))


async def api_perf(request):
    q = request.query
    return _json(await _run(perf_view, q.get("period") or "week", q.get("offset") or 0))


async def api_request(request):
    try:
        rid = int(request.query.get("id") or 0)
    except ValueError:
        return _json({"ok": False, "error": "bad id"}, 400)
    return _json(await _run(request_view, rid))


async def api_translation(request):
    data = await _run(translation_view)
    data["settings"] = await _run(settings_view)
    data["can_edit"] = _role(request) in SETTINGS_ROLES
    return _json(data)


async def api_settings(request):
    if _role(request) not in SETTINGS_ROLES:
        return _json({"ok": False, "error": "للإدارة فقط"}, 403)
    b = await _body(request)
    try:
        ok, err = await _run(save_settings, b, _actor(request))
    except (TypeError, ValueError) as e:
        return _json({"ok": False, "error": str(e)}, 400)
    return _json({"ok": ok, "error": err, "settings": await _run(settings_view)})


async def api_glossary(request):
    if _role(request) not in SETTINGS_ROLES:
        return _json({"ok": False, "error": "للإدارة فقط"}, 403)
    b = await _body(request)
    await _run(save_glossary, b.get("terms") or [], _actor(request))
    return _json({"ok": True})


def _excuse_by_request(rid, by, reason, now):
    ms = db.miss(rid)
    if not ms:
        return False, "ما فيه تأخير على هذا الطلب."
    if not ms.get("line_message_id"):
        db.set_miss(rid, ms["gen"], line_message_id="dash:%d:%d" % (rid, ms["gen"]))
        ms = db.miss(rid)
    return flow.excuse(ms["line_message_id"], "", by, True, reason, now)


async def api_excuse(request):
    if _role(request) not in MERCY_ROLES:
        return _json({"ok": False, "error": "غير مصرّح"}, 403)
    b = await _body(request)
    ok, text = await _run(_excuse_by_request, int(b.get("request_id") or 0), _actor(request),
                          str(b.get("reason") or ""), flow._now())
    return _json({"ok": ok, "message": text})


async def health(request):
    try:
        return _json(await _run(flow.health))
    except Exception as e:
        return _json({"ok": False, "error_class": type(e).__name__}, 200)


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
    g("/rrdesk/static/rrdesk_tab.js", handle_static_js)
    g("/rrdesk/health", health)
    g("/api/rrdesk/state", _safe(api_state))
    g("/api/rrdesk/perf", _safe(api_perf))
    g("/api/rrdesk/request", _safe(api_request))
    g("/api/rrdesk/translation", _safe(api_translation))
    p("/api/rrdesk/settings", _safe(api_settings))
    p("/api/rrdesk/glossary", _safe(api_glossary))
    p("/api/rrdesk/excuse", _safe(api_excuse))
