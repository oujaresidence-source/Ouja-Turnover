# -*- coding: utf-8 -*-
"""
reviewask.routes — the web doors of «رفع التقييم».

    /rv/<token>                      PUBLIC. The one-tap WhatsApp link a Discord button points
                                     at: 302 → wa.me with the owner's message typed. The token is
                                     random (16 chars), the hit is logged, rate-limited per IP.
    /reviewask/static/reviewask_tab.js   PUBLIC code, no data (the dashboard tab).
    /api/reviewask/*                 login (bot.py _dash_auth) + the «rvpush» page permission
                                     (bot.py _ROLE_READ_RULES / _ROLE_WRITE_RULES). Pins and the
                                     template editor are re-checked for admin here.

EVERY database call from a handler runs on HOST.web_thread — never asyncio.to_thread
(CLAUDE.md trap 6: the shared pool jams and the page waits forever).
"""

import os
import time
import traceback

from . import config, db, engine, flow, texts
from .host import HOST

STATIC_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "reviewask_tab.js")
_RATE = {}
RATE_MAX = 30                  # /rv hits per IP per minute
TEMPLATE_MAX = 4000            # Discord's modal cap — the two editors must agree


# ---------------- roles ----------------

def _role(request):
    try:
        return HOST.req_role(request) if HOST.req_role else "viewer"
    except Exception:
        return "viewer"


def _actor(request):
    try:
        return HOST.actor(request) if HOST.actor else ""
    except Exception:
        return ""


def _json(body, status=200):
    return HOST.json_response(body, status)


def _safe(fn):
    async def _w(request):
        if not HOST.dash_auth(request):
            return _json({"ok": False, "error": "unauthorized", "error_ar": "سجّل دخول"}, 401)
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return _json({"ok": False, "error_ar": "صار خطأ غير متوقع — جرّب مرة ثانية",
                          "error_en": "%s: %s" % (type(e).__name__, e)}, 500)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _need_admin(request):
    if _role(request) != "admin":
        return _json({"ok": False, "error_ar": "هذي للمدير بس", "error_en": "admin only"}, 403)
    return None


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


async def _run(fn, *a, **kw):
    return await HOST.web_thread(fn, *a, **kw)


def _reply(pair):
    st, body = pair
    return _json(body, st)


def _room_url(cid):
    if cid and HOST.guild_id:
        return "https://discord.com/channels/%s/%s" % (HOST.guild_id, cid)
    return ""


# ---------------- read models (plain values in, (status, dict) out) ----------------

def _ticket_view(r):
    return {"id": r["id"], "reservation_id": r["reservation_id"], "lid": r.get("lid"),
            "unit": engine.unit_short(r.get("unit")), "guest": r.get("guest") or "",
            "day": r.get("day"), "mode": r.get("mode"), "mode_ar": texts.MODE_AR.get(r.get("mode"), ""),
            "state": r.get("state"), "state_ar": texts.STATE_AR.get(r.get("state"), r.get("state")),
            "responsible": r.get("responsible") or "", "state_by": r.get("state_by") or "",
            "state_at": r.get("state_at"), "calls_used": r.get("calls_used") or 0,
            "review_stars": r.get("review_stars"), "closed_at": r.get("closed_at"),
            "deleted_at": r.get("deleted_at"), "close_note": r.get("close_note") or "",
            "room_url": "" if r.get("deleted_at") else _room_url(r.get("channel_id")),
            "avg_at_open": r.get("avg_at_open"), "needed_at_open": r.get("needed_at_open")}


def core_summary():
    prog = flow.program()
    return 200, {"ok": True, "live": flow.live(), "open": len(db.open_tickets()),
                 "weak": sum(1 for s in prog.values() if s.get("in_program")),
                 "threshold": config.threshold()}


def core_apartments(role="viewer"):
    prog = flow.program()
    names = flow._names()
    lids = set(prog) | set(names)
    rows = []
    for lid in lids:
        st = prog.get(lid) or engine.apartment_status([], {}, {lid: 0}, config.threshold(),
                                                     config.min_reviews())[lid]
        rows.append(dict(st, name=engine.unit_short(names.get(lid) or "#%s" % lid)))
    rows.sort(key=lambda r: (not r["in_program"], r["avg"] is not None, r["avg"] or 0, r["name"]))
    return 200, {"ok": True, "rows": rows, "is_admin": role == "admin",
                 "threshold": config.threshold(), "min_reviews": config.min_reviews()}


def core_pin(b, by):
    try:
        lid = int(b.get("lid"))
    except (TypeError, ValueError):
        return 400, {"ok": False, "error_ar": "اختر الشقة"}
    mode = str(b.get("mode") or "")
    reason = str(b.get("reason") or "").strip()
    if mode not in ("in", "out", "clear"):
        return 400, {"ok": False, "error_ar": "اختيار غير صحيح"}
    if mode != "clear" and not (3 <= len(reason) <= 300):
        return 400, {"ok": False, "error_ar": "اكتب السبب (٣ أحرف على الأقل)"}
    db.set_override(lid, mode if mode != "clear" else None, reason, by)
    return 200, {"ok": True}


def core_live():
    return 200, {"ok": True, "rows": [_ticket_view(r) for r in db.open_tickets()]}


def core_archive(offset=0):
    try:
        offset = max(0, int(offset or 0))
    except (TypeError, ValueError):
        offset = 0
    rows = db.archive(100, offset)
    return 200, {"ok": True, "rows": [_ticket_view(r) for r in rows], "offset": offset,
                 "more": len(rows) == 100}


def core_ticket(tid):
    try:
        row = db.ticket(int(tid))
    except (TypeError, ValueError):
        row = None
    if not row:
        return 404, {"ok": False, "error_ar": "ما لقيناها"}
    evs = db.events(row["id"])
    return 200, {"ok": True, "ticket": _ticket_view(row), "events": evs,
                 "transcript": db.transcript(row["id"])}


def core_performance(days=7):
    try:
        days = 30 if int(days) >= 30 else 7
    except (TypeError, ValueError):
        days = 7
    people, apts = flow.report_data(flow.now(), days)
    return 200, {"ok": True, "days": days, "people": people, "apartments": apts}


def core_templates():
    t = db.templates()
    hist = [{"at": h["at"], "by": h["by"]} for h in db.template_history(10)]
    return 200, {"ok": True, "templates": t, "preview": flow.preview(t), "history": hist,
                 "placeholders": list(engine.PLACEHOLDERS), "max": TEMPLATE_MAX}


def _clean_templates(b):
    out = {}
    for k in ("ar", "en", "call_script"):
        v = str(b.get(k) or "")
        if len(v) > TEMPLATE_MAX:
            return None, "النص أطول من %d حرف" % TEMPLATE_MAX
        out[k] = v
    if not out["ar"].strip():
        return None, "النص العربي مطلوب"
    return out, ""


def core_preview(b):
    t, err = _clean_templates(b)
    if t is None:
        return 400, {"ok": False, "error_ar": err}
    return 200, {"ok": True, "preview": flow.preview(t)}


def core_save_templates(b, by):
    t, err = _clean_templates(b)
    if t is None:
        return 400, {"ok": False, "error_ar": err}
    saved = db.save_templates(t["ar"], t["en"], t["call_script"], by)
    return 200, {"ok": True, "templates": saved, "preview": flow.preview(saved)}


# ---------------- handlers ----------------

async def api_summary(request):
    return _reply(await _run(core_summary))


async def api_apartments(request):
    return _reply(await _run(core_apartments, _role(request)))


async def api_pin(request):
    g = _need_admin(request)
    if g:
        return g
    b = await _body(request)
    return _reply(await _run(core_pin, b, _actor(request)))


async def api_live(request):
    return _reply(await _run(core_live))


async def api_archive(request):
    return _reply(await _run(core_archive, request.query.get("offset")))


async def api_ticket(request):
    return _reply(await _run(core_ticket, request.query.get("id")))


async def api_performance(request):
    return _reply(await _run(core_performance, request.query.get("days")))


async def api_templates(request):
    return _reply(await _run(core_templates))


async def api_preview(request):
    b = await _body(request)
    return _reply(await _run(core_preview, b))


async def api_templates_save(request):
    g = _need_admin(request)
    if g:
        return g
    b = await _body(request)
    return _reply(await _run(core_save_templates, b, _actor(request)))


# ---------------- the public one-tap link ----------------

def _rate_ok(ip, now_=None):
    t = now_ if now_ is not None else time.time()
    hits = [x for x in _RATE.get(ip, []) if t - x < 60]
    if len(hits) >= RATE_MAX:
        _RATE[ip] = hits
        return False
    hits.append(t)
    _RATE[ip] = hits
    if len(_RATE) > 5000:
        _RATE.clear()
    return True


async def handle_rv(request):
    """GET /rv/<token> → 302 wa.me. Unknown token / no phone → 404. Web pool, never to_thread."""
    ip = (request.headers.get("X-Forwarded-For") or request.remote or "?").split(",")[0].strip()
    if not _rate_ok(ip):
        raise HOST.web.HTTPTooManyRequests()
    token = request.match_info.get("token", "")
    url = await HOST.web_thread(flow.wa_redirect, token)
    if not url:
        raise HOST.web.HTTPNotFound()
    raise HOST.web.HTTPFound(url)


# ---------------- the tab's script (public: code, no data) ----------------

_js_cache = {"mtime": None, "text": ""}


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


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    g("/rv/{token}", handle_rv)
    g("/reviewask/static/reviewask_tab.js", handle_static_js)
    g("/api/reviewask/summary", _safe(api_summary))
    g("/api/reviewask/apartments", _safe(api_apartments))
    g("/api/reviewask/live", _safe(api_live))
    g("/api/reviewask/archive", _safe(api_archive))
    g("/api/reviewask/ticket", _safe(api_ticket))
    g("/api/reviewask/performance", _safe(api_performance))
    g("/api/reviewask/templates", _safe(api_templates))
    p("/api/reviewask/preview", _safe(api_preview))
    p("/api/reviewask/templates", _safe(api_templates_save))
    p("/api/reviewask/pin", _safe(api_pin))
