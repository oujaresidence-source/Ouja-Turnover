# -*- coding: utf-8 -*-
"""
kb.routes — /api/kb/* for «قاعدة المعرفة».

ONE DOOR. Unlike wifi/ there is no public share link: this data is who owns what and what
we charge them, so every endpoint sits behind login AND the `kb` permission (enforced by
bot.py's role middleware via the /api/kb/ prefix). Non-admin users see the tab only after
the owner ticks it in «الصلاحيات» — the whitelist model denies unknown tabs by default.

Each endpoint is a thin wrapper around a `core_*` function that takes plain dicts, so the
rules stay reachable from tests without a web server.
"""

import traceback

from . import db, engine
from .host import HOST


# ---------------- cores ----------------

def core_search(q, type="all", district=None, owned="all", gaps=False, who=""):
    r = db.search(q or "", type=type, district=district, owned=owned,
                  gaps=bool(gaps), log_as=who)
    r["ok"] = True
    r["counts"] = db.counts()
    r["districts"] = db.districts()
    r["policy_ar"] = engine.POLICY_AR
    r["cycle_ar"] = engine.CYCLE_AR
    return 200, r


def core_unit(unit_id):
    u = db.unit(unit_id)
    if not u:
        return 404, {"ok": False, "error": "not_found", "message": "الوحدة غير موجودة"}
    return 200, {"ok": True, "unit": u, "audit": db.audit_for("unit", unit_id),
                 "policy_ar": engine.POLICY_AR, "cycle_ar": engine.CYCLE_AR}


def core_owner(owner_id):
    o = db.owner(owner_id)
    if not o:
        return 404, {"ok": False, "error": "not_found", "message": "المالك غير موجود"}
    return 200, {"ok": True, "owner": o}


def core_save_unit(body, actor=""):
    unit_id = (body.get("unit_id") or "").strip()
    patch = {k: v for k, v in (body.get("patch") or body).items() if k in db.UNIT_FIELDS}
    if unit_id:
        n, err = db.update_unit(unit_id, patch, actor=actor)
        if err:
            return 200, {"ok": False, "message": err}
        return 200, {"ok": True, "changed": n, "unit": db.unit(unit_id),
                     "message": "انحفظ ✓" if n else "ما فيه تغيير"}
    uid, err = db.create_unit(patch, actor=actor)
    if err:
        return 200, {"ok": False, "message": err}
    return 200, {"ok": True, "created": True, "unit": db.unit(uid), "message": "انضافت الشقة ✓"}


def core_delete_unit(body, actor=""):
    unit_id = (body.get("unit_id") or "").strip()
    if not unit_id:
        return 200, {"ok": False, "message": "ما فيه وحدة"}
    db.soft_delete_unit(unit_id, actor=actor)
    # Soft: the row and its whole history stay, it just stops answering searches.
    return 200, {"ok": True, "message": "انخفت من البحث — تنرجع من سجل التعديلات"}


def core_save_faq(body, actor=""):
    fid = (body.get("faq_id") or "").strip()
    if fid:
        n, err = db.update_faq(fid, body, actor=actor)
        if err:
            return 200, {"ok": False, "message": err}
        return 200, {"ok": True, "changed": n, "message": "انحفظ ✓" if n else "ما فيه تغيير"}
    fid, err = db.create_faq(body, actor=actor)
    if err:
        return 200, {"ok": False, "message": err}
    return 200, {"ok": True, "faq_id": fid, "message": "انضاف ✓"}


def core_delete_faq(body, actor=""):
    fid = (body.get("faq_id") or "").strip()
    if not fid:
        return 200, {"ok": False, "message": "ما فيه سؤال"}
    db.soft_delete_faq(fid, actor=actor)
    return 200, {"ok": True, "message": "انحذف ✓"}


def core_log_question(body, actor=""):
    qid = db.log_question(body.get("text"), asked_by=(body.get("asked_by") or actor))
    if not qid:
        return 200, {"ok": False, "message": "اكتب السؤال أول"}
    return 200, {"ok": True, "question_id": qid,
                 "message": "انسجّل السؤال — بيوصل لمن يعرف الجواب"}


def core_questions(status=None):
    return 200, {"ok": True, "questions": db.questions(status),
                 "open": len(db.questions("open"))}


def core_resolve_question(body, actor=""):
    ok, err = db.resolve_question(body.get("question_id"),
                                  status=body.get("status") or "answered",
                                  faq_id=body.get("faq_id"), actor=actor)
    if err:
        return 200, {"ok": False, "message": err}
    return 200, {"ok": True, "message": "تم ✓"}


def core_quality():
    return 200, {"ok": True, "quality": db.quality(), "stats": db.stats()}


# ---------------- aiohttp wrappers ----------------

def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def _actor(request):
    try:
        return (HOST.actor(request) if HOST.actor else "") or ""
    except Exception:
        return ""


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
        return await request.json()
    except Exception:
        return {}


def _reply(pair):
    status, data = pair
    return HOST.json_response(data, status)


async def api_search(request):
    q = request.rel_url.query
    return _reply(core_search(q.get("q", ""), type=q.get("type", "all"),
                              district=q.get("district") or None,
                              owned=q.get("owned", "all"),
                              gaps=q.get("gaps") in ("1", "true"),
                              who=_actor(request)))


async def api_unit(request):
    return _reply(core_unit(request.match_info.get("unit_id")))


async def api_owner(request):
    return _reply(core_owner(request.match_info.get("owner_id")))


async def api_save_unit(request):
    return _reply(core_save_unit(await _body(request), actor=_actor(request)))


async def api_delete_unit(request):
    return _reply(core_delete_unit(await _body(request), actor=_actor(request)))


async def api_save_faq(request):
    return _reply(core_save_faq(await _body(request), actor=_actor(request)))


async def api_delete_faq(request):
    return _reply(core_delete_faq(await _body(request), actor=_actor(request)))


async def api_question(request):
    return _reply(core_log_question(await _body(request), actor=_actor(request)))


async def api_questions(request):
    return _reply(core_questions(request.rel_url.query.get("status") or None))


async def api_resolve_question(request):
    return _reply(core_resolve_question(await _body(request), actor=_actor(request)))


async def api_quality(request):
    return _reply(core_quality())


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    g("/api/kb/search", _safe(api_search))
    g("/api/kb/unit/{unit_id}", _safe(api_unit))
    g("/api/kb/owner/{owner_id}", _safe(api_owner))
    g("/api/kb/quality", _safe(api_quality))
    g("/api/kb/questions", _safe(api_questions))
    p("/api/kb/unit-save", _safe(api_save_unit))
    p("/api/kb/unit-delete", _safe(api_delete_unit))
    p("/api/kb/faq-save", _safe(api_save_faq))
    p("/api/kb/faq-delete", _safe(api_delete_faq))
    p("/api/kb/question", _safe(api_question))
    p("/api/kb/question-resolve", _safe(api_resolve_question))
