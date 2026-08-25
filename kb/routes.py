# -*- coding: utf-8 -*-
"""
kb.routes — /api/kb/* (private) and /api/kbp/* (the share link) for «قاعدة المعرفة».

TWO DOORS, AND THE PREFIXES ARE DIFFERENT ON PURPOSE
  • /api/kb/*   the dashboard door — login AND the `kb` permission, on both reads and
    writes, via bot.py's role middleware.
  • /api/kbp/*  the share link — NO login. `p` for public. It is a separate prefix so
    that "/api/kbp/…".startswith("/api/kb/") is FALSE: one broad rule keeps gating the
    private door with no chance of a public path slipping through it. Do not rename
    either prefix to something where one is a prefix of the other.

The public door is gated ONLY by an unguessable token in the URL, at the owner's explicit
instruction (2026-08-03): anyone holding the link can read AND edit, and is not asked for
a name. That is a real trade — every edit through it is stamped «رابط عام» in kb_audit,
which records the door, not the person. If a wrong number ever has to be traced back to a
human, that trail ends here. Rotating the token (dashboard → «رابط عام» → «غيّر الرابط»)
kills every copy at once.

Each endpoint is a thin wrapper around a `core_*` function that takes plain dicts, so the
rules stay reachable from tests without a web server.
"""

import traceback

from . import db, engine, page
from .host import HOST

# What the audit log records for an edit made through the share link. Honest about the
# door rather than blank: "someone with the link" is more useful than "".
PUBLIC_ACTOR = "رابط عام"


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


def core_share(base_url=""):
    t = db.share_token()
    return 200, {"ok": True, "token": t,
                 "url": (base_url or "").rstrip("/") + "/kb/" + t}


def core_rotate_share(actor="", base_url=""):
    t = db.rotate_share_token(actor=actor)
    return 200, {"ok": True, "token": t,
                 "url": (base_url or "").rstrip("/") + "/kb/" + t,
                 "message": "انتغيّر الرابط — الروابط القديمة ما عادت تشتغل"}


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


async def api_share(request):
    return _reply(core_share(_base(request)))


async def api_rotate_share(request):
    return _reply(core_rotate_share(actor=_actor(request), base_url=_base(request)))


# ---------------- the public door (share link) ----------------

def _base(request):
    try:
        return str(request.url.origin())
    except Exception:
        return ""


def _tok(request):
    """The token travels in the query string for reads and in the body for writes; the
    page passes it on every call. Nothing else identifies the caller."""
    return request.rel_url.query.get("t") or ""


def _pub(fn, body_token=False):
    """PUBLIC wrapper — no login. The ONLY gate is the token, so it is checked here, once,
    for every public endpoint. A handler is never reachable without passing through it."""
    async def _w(request):
        t = _tok(request)
        body = None
        if body_token and not t:
            body = await _body(request)
            t = body.get("t") or ""
        if not db.token_ok(t):
            return HOST.json_response(
                {"ok": False, "error": "bad_link",
                 "message": "الرابط ما عاد يشتغل — اطلب رابط جديد"}, 403)
        try:
            request["kb_body"] = body
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _pbody(request):
    b = request.get("kb_body")
    return b if b is not None else await _body(request)


async def api_pub_search(request):
    q = request.rel_url.query
    return _reply(core_search(q.get("q", ""), type=q.get("type", "all"),
                              district=q.get("district") or None,
                              owned=q.get("owned", "all"),
                              gaps=q.get("gaps") in ("1", "true"),
                              who=PUBLIC_ACTOR))


async def api_pub_unit(request):
    return _reply(core_unit(request.match_info.get("unit_id")))


async def api_pub_quality(request):
    return _reply(core_quality())


async def api_pub_save(request):
    return _reply(core_save_unit(await _pbody(request), actor=PUBLIC_ACTOR))


async def api_pub_delete(request):
    return _reply(core_delete_unit(await _pbody(request), actor=PUBLIC_ACTOR))


async def api_pub_question(request):
    return _reply(core_log_question(await _pbody(request), actor=PUBLIC_ACTOR))


async def handle_page(request):
    """/kb/{token}. A wrong or retired token gets a plain Arabic page, not a stack trace
    and not a redirect to the login — the person holding an old link needs to understand
    that the link changed, not think the site is broken."""
    if not db.token_ok(request.match_info.get("token")):
        return HOST.web.Response(text=page.DEAD_HTML, content_type="text/html", status=403)
    return HOST.web.Response(text=page.HTML, content_type="text/html")


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    # ---- public: token in the URL is the only gate ----
    g("/kb/{token}", handle_page)
    g("/api/kbp/search", _pub(api_pub_search))
    g("/api/kbp/unit/{unit_id}", _pub(api_pub_unit))
    g("/api/kbp/quality", _pub(api_pub_quality))
    p("/api/kbp/unit-save", _pub(api_pub_save, body_token=True))
    p("/api/kbp/unit-delete", _pub(api_pub_delete, body_token=True))
    p("/api/kbp/question", _pub(api_pub_question, body_token=True))
    # ---- dashboard: login + the `kb` permission ----
    g("/api/kb/share", _safe(api_share))
    p("/api/kb/share-rotate", _safe(api_rotate_share))
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
