# -*- coding: utf-8 -*-
"""
aqd.routes — the HTTP doors of «العقود».

Logged in (tab `aqd`, double-gated: bot.py's role middleware + the role re-checks below):
  GET  /api/aqd/schema · /api/aqd/list · /api/aqd/get · /api/aqd/file · /api/aqd/settings
  POST /api/aqd/preview · save · send · void · resend · countersign · settings
Public — the token is the credential (onboarding employee-link pattern). The READ sits OUTSIDE
/api/aqd/ so the role-read rule never 403s an anonymous phone; the writes are exact paths in
bot.py's _ROLE_EXEMPT_WRITES:
  GET  /sign/{token} (HTML shell, no data) · /api/aqd-t/{token} · /api/aqd-t/{token}/file
  POST /api/aqd-t/open · /api/aqd-t/verify · /api/aqd-t/sign
Static: GET /aqd/static/aqd_tab.js · /aqd/static/sign.js (code, no data; allow-list).

Error contract (there is no fourth): 401 not logged in · 403 wrong role · 200 {ok:false, error}
business refusal · 200 {ok:true, …}. Public handlers never show a stack trace. Every blocking
call goes through HOST.web_thread (the web pool), never the default executor.
"""

import collections
import datetime
import json
import os
import re
import secrets
import threading
import time
import traceback
import urllib.parse

from . import catalogue, config, db, engine, files, notify, pdf, sign_page
from .host import HOST

EDIT_ROLES = ("admin", "ops")
ADMIN_ROLES = ("admin",)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_ALLOW = ("aqd_tab.js", "sign.js")
RIYADH = datetime.timezone(datetime.timedelta(hours=3))

GENERIC_VERIFY_FAIL = "البيانات غير صحيحة — تأكد من آخر 4 أرقام"
INVALID_LINK = "الرابط غير صحيح"
PUBLIC_TEMP_ERR = "صار خطأ مؤقت — حدّث الصفحة وجرّب مرة ثانية"
DISABLED = "العقود متوقفة حالياً"


# ================================================================== plumbing

def _json(body, status=200):
    return HOST.json_response(body, status)


def _role(request):
    try:
        return HOST.req_role(request) if HOST.req_role else "viewer"
    except Exception:
        return "viewer"


def can_edit(request):
    return _role(request) in EDIT_ROLES


def is_admin(request):
    return _role(request) in ADMIN_ROLES


def _actor(request):
    try:
        return HOST.actor(request) if HOST.actor else "—"
    except Exception:
        return "—"


def _refuse(msg, **extra):
    body = {"ok": False, "error": msg}
    body.update(extra)
    return 200, body


def _deny(msg="ما عندك صلاحية لهذا الإجراء"):
    return _json({"ok": False, "error": msg}, 403)


def _safe(fn):
    """Logged-in wrapper: 401 when not signed in; an unhandled exception is a 200 ok:false."""
    async def _w(request):
        try:
            if not HOST.dash_auth(request):
                return _json({"ok": False, "error": "unauthorized"}, 401)
        except Exception:
            return _json({"ok": False, "error": "unauthorized"}, 401)
        if not config.enabled():
            return _json({"ok": False, "error": DISABLED})
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return _json({"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _safe_public(fn):
    """PUBLIC wrapper — no login. Full detail stays in the server log; the phone gets one
    generic Arabic sentence and never a stack trace."""
    async def _w(request):
        try:
            return await fn(request)
        except Exception:
            traceback.print_exc()
            return _json({"ok": False, "error": PUBLIC_TEMP_ERR})
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _run(fn, *a, **kw):
    return await HOST.web_thread(fn, *a, **kw)


def _reply(pair):
    st, body = pair
    return _json(body, st)


async def _body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _qs(request, key, default=""):
    try:
        return request.query.get(key, default)
    except Exception:
        return default


def _ip(request):
    try:
        xff = request.headers.get("X-Forwarded-For") or ""
        if xff.strip():
            return xff.split(",")[0].strip()[:64]
    except Exception:
        pass
    return str(getattr(request, "remote", "") or "")[:64]


def _ua(request):
    try:
        return (request.headers.get("User-Agent") or "")[:300]
    except Exception:
        return ""


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).replace(microsecond=0)


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def _dt(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None


def riyadh_text(iso_utc):
    d = _dt(iso_utc)
    if not d:
        return "—"
    r = d.replace(tzinfo=datetime.timezone.utc).astimezone(RIYADH)
    return "%02d/%02d/%04dم %02d:%02d" % (r.day, r.month, r.year, r.hour, r.minute)


def _now_riyadh():
    try:
        if HOST.now:
            return HOST.now()
    except Exception:
        pass
    return datetime.datetime.now(RIYADH)


def _today():
    return _now_riyadh().date()


def _base_url():
    try:
        b = HOST.public_base() if HOST.public_base else ""
    except Exception:
        b = ""
    return (b or "").rstrip("/")


def sign_link(token):
    return "%s/sign/%s" % (_base_url(), token)


# ================================================================== rate limit (in-process)

class _Limiter:
    def __init__(self):
        self.hits = collections.defaultdict(collections.deque)
        self.lock = threading.Lock()

    def allow(self, key, limit, window=60.0):
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self.hits) > 5000:          # never grow without bound
                for k in [k for k, v in self.hits.items() if not v][:2500]:
                    self.hits.pop(k, None)
            return True

    def reset(self):
        with self.lock:
            self.hits.clear()


LIMITER = _Limiter()
IP_PER_MIN = 30
TOKEN_PER_MIN = 10


def _limited(ip, token=None):
    if not LIMITER.allow("ip:" + ip, IP_PER_MIN):
        return True
    if token and not LIMITER.allow("tk:" + str(token)[:64], TOKEN_PER_MIN):
        return True
    return False


SLOW_DOWN = "طلبات كثيرة — انتظر دقيقة وجرّب"


# ================================================================== settings

def settings_values():
    stored = db.settings()
    out = {}
    for k, default in config.SETTINGS_DEFAULTS.items():
        v = (stored.get(k) or {}).get("value")
        out[k] = v if (v is not None and str(v).strip() != "") else default
    return out


def approval(template_name=None):
    key = config.approval_key(template_name)
    row = db.settings().get(key) or {}
    return {"approved": (row.get("value") == "1"), "by": row.get("updated_by"),
            "at": row.get("updated_at"), "template": template_name or config.template_name(),
            "version": config.template_version(template_name)}


OPERATOR_FIELDS = (("op_rep_name", "اسم ممثل المشغّل"), ("op_wakala_no", "رقم الوكالة"),
                   ("op_wakala_date", "تاريخ الوكالة"), ("op_cr_expiry", "تاريخ انتهاء السجل التجاري"))
DATE_SETTINGS = ("op_wakala_date", "op_cr_expiry")


def operator_missing():
    """R4: the operator block is frozen into the document at send time, so a send (and the
    template approval) waits until every one of these is filled."""
    v = settings_values()
    return [label for key, label in OPERATOR_FIELDS if str(v.get(key) or "").strip() in ("", "—")]


def operator_refusal(missing):
    return "أكمل بيانات المشغّل في الإعدادات أول: " + "، ".join(missing)


def is_approved(template_name=None):
    return approval(template_name)["approved"]


def ttl_days():
    try:
        v = int(str(settings_values().get("link_ttl_days") or "").strip())
        return max(1, min(90, v))
    except ValueError:
        return config.env_ttl_days()


# ================================================================== contract helpers

def touch(c):
    """Persist a computed expiry on the next touch. -> the fresh row."""
    if c and engine.is_expired(c, _iso(_now_utc())):
        if db.transition(c["id"], engine.TRANSITIONS["expire"][0], "expired"):
            db.add_event(c["id"], "النظام", "expired", {})
        c = db.get(c["id"])
    return c


def _signer_of(c):
    a = db.answers(c)
    return engine.signer(a), a


def _last4_kind(a):
    s = engine.signer(a)
    return "alnum" if s["kind"] == "alnum" else "digits"


def _overlay(c, *, approved, with_owner_sig, with_operator_sig):
    """Fill the frozen document's three slots for display / signed / final."""
    a = db.answers(c)
    label = engine.sig_owner_label(a)
    st = settings_values()
    if with_owner_sig and files.exists(c["id"], "signature.png"):
        import base64
        b64 = base64.b64encode(files.read_bytes(c["id"], "signature.png")).decode("ascii")
        so = engine.sig_owner_html(label, b64, riyadh_text(c.get("signed_at")), c.get("signer_typed_name"))
    else:
        so = engine.sig_owner_html(label)
    if with_operator_sig and c.get("countersigned_at"):
        sop = engine.sig_operator_html(st.get("op_rep_name"), files.settings_png_b64("op_sig.png"),
                                       files.settings_png_b64("op_stamp.png"),
                                       riyadh_text(c.get("countersigned_at")))
    else:
        sop = engine.sig_operator_html(st.get("op_rep_name"))
    return engine.fill_slots(files.read_text(c["id"], "frozen.html"),
                             version_banner=engine.banner_html(approved), sig_owner=so, sig_operator=sop)


def evidence(c):
    first = c.get("first_open_at")
    return {
        "ref": c.get("ref"), "doc_sha256": c.get("doc_sha256"),
        "template_version": c.get("template_version"),
        "created": "%s — %s" % (c.get("created_by") or "—", riyadh_text(c.get("created_at"))),
        "sent_at": riyadh_text(c.get("sent_at")),
        "first_open": ("%s — %s مرة" % (riyadh_text(first), c.get("open_count") or 0)) if first else "—",
        "verified_at": riyadh_text(c.get("verified_at")),
        "signed_at": riyadh_text(c.get("signed_at")),
        "signed_at_utc": (c.get("signed_at") + "Z") if c.get("signed_at") else "—",
        "typed_name": c.get("signer_typed_name") or "—",
        "id_last4": c.get("id_last4") or "—",
        "ip": c.get("signer_ip") or "—",
        "ua": c.get("signer_ua") or "—",
        "link_id": (c.get("token") or "")[:6] or "—",
        "countersigned": ("%s — %s" % (c.get("countersigned_by"), riyadh_text(c.get("countersigned_at"))))
                         if c.get("countersigned_at") else "—",
    }


def _artifact(c, kind):
    """-> (path, content_type, filename) for draft|signed|final; builds draft lazily."""
    cid = c["id"]
    name = {"draft": "draft", "signed": "signed", "final": "final"}[kind]
    if kind == "draft" and is_approved(c.get("template_name")):
        name = "draft-a"                # the watermark differs once approved — never serve a stale copy
    for ext, ctype in ((".pdf", "application/pdf"), (".html", "text/html; charset=utf-8")):
        if files.exists(cid, name + ext):
            return files.path(cid, name + ext), ctype, "%s-%s%s" % (c.get("ref"), name, ext)
    if kind != "draft":
        return None, None, None
    if files.exists(cid, "frozen.html"):
        html = _overlay(c, approved=is_approved(c.get("template_name")), with_owner_sig=False,
                        with_operator_sig=False)
    else:
        answers = files.read_json(cid, "draft_answers.json", {}) or {}
        clean, _e = catalogue.validate(answers, _today())
        html = _preview_for(clean, c.get("ref"))
    ok = pdf.to_pdf(html, files.path(cid, name + ".pdf"))
    if ok:
        return files.path(cid, name + ".pdf"), "application/pdf", "%s-draft.pdf" % c.get("ref")
    return files.path(cid, name + ".html"), "text/html; charset=utf-8", "%s-draft.html" % c.get("ref")


def _render_preview(clean, ref, frozen, created=None, template_name=None, routed=True):
    """routed=False: there is no approved template for this kind of contract — render v2.1 for
    reading only, under a red «معاينة فقط» banner (never frozen, never sent)."""
    tname = template_name or config.template_name()
    banner = None if routed else '<div class="ver draft">%s</div>' % catalogue.UNROUTED_PREVIEW
    ctx = engine.build_context(
        clean, ref=ref or "OUJA-CT-%04d-____" % _today().year, created=created or _now_riyadh(),
        settings=settings_values(), font_css=files.font_css_embedded(), contract_css=files.contract_css(),
        template_version=config.template_version(tname), approved=is_approved(tname), frozen=frozen,
        banner=banner)
    return engine.render(files.template_text(tname), ctx)


def _preview_for(clean, ref):
    name, _why = engine.template_for(clean)
    return _render_preview(clean, ref, frozen=False, template_name=name, routed=bool(name))


def _row_view(c):
    c = touch(c)
    last = db.last_event_at(c["id"])
    return {
        "id": c["id"], "ref": c.get("ref"), "status": c.get("status"),
        "status_ar": engine.STATUS_AR.get(c.get("status"), c.get("status")),
        "client_name": c.get("client_name"), "client_kind": c.get("client_kind"),
        "units_count": c.get("units_count"), "op_pct": c.get("op_pct"),
        "created_by": c.get("created_by"), "created_at": c.get("created_at"),
        "last_event_at": last.get("at") or c.get("updated_at"), "last_event": last.get("kind"),
        "signed_at": c.get("signed_at"), "expires_at": c.get("expires_at"),
    }


# ================================================================== logged-in cores

def core_schema():
    out = catalogue.schema()
    try:
        lst = HOST.listings() if HOST.listings else []
        out["listings"] = [{"id": x.get("id"), "name": x.get("name")} for x in (lst or [])
                           if x.get("active", True)]
    except Exception as e:
        print("[aqd] listings unavailable:", e)
        out["listings"] = []
    return 200, dict(out, ok=True)


def core_list(status=None, query=None, role="viewer"):
    try:
        notify.retry_pending()
    except Exception as e:
        print("[aqd] notify retry skipped:", e)
    rows = [_row_view(c) for c in db.contracts()]
    counts = collections.Counter(r["status"] for r in rows)
    awaiting = counts.get("signed_owner", 0)
    if status:
        rows = [r for r in rows if r["status"] == status]
    if query:
        ql = query.strip().lower()
        rows = [r for r in rows if ql in ("%s %s %s" % (r["ref"], r["client_name"], r["created_by"])).lower()]
    ap = approval()
    return 200, {"ok": True, "rows": rows, "counts": dict(counts), "awaiting_countersign": awaiting,
                 "approval": ap, "can_edit": role in EDIT_ROLES, "is_admin": role in ADMIN_ROLES,
                 "status_ar": engine.STATUS_AR, "total": sum(counts.values()),
                 "operator_missing": operator_missing()}


def core_get(cid, role, actor, edit=False):
    c = db.get(cid)
    if not c:
        return _refuse("ما لقيت العقد")
    c = touch(c)
    a = db.answers(c)
    st = c["status"]
    view = {k: c.get(k) for k in ("id", "ref", "status", "client_kind", "client_name", "gender", "mobile",
                                  "units_count", "op_pct", "template_version", "doc_sha256",
                                  "created_by", "created_at", "sent_at", "expires_at", "first_open_at",
                                  "open_count", "verified_at", "signed_at", "signer_typed_name",
                                  "countersigned_by", "countersigned_at", "voided_by", "voided_at",
                                  "void_reason")}
    view["notified_signed_at"] = (c.get("notified_signed_at") or "") if not str(
        c.get("notified_signed_at") or "").startswith("claim:") else ""
    view["id_masked"] = ("••••••" + c["id_last4"]) if c.get("id_last4") else ""
    view["status_ar"] = engine.STATUS_AR.get(st, st)
    out = {"ok": True, "contract": view, "answers": a, "events": db.events(c["id"]),
           "warnings": json.loads(c.get("warnings_json") or "[]")}
    if c.get("token") and st in ("sent", "opened", "verified", "signed_owner", "completed"):
        out["link"] = sign_link(c["token"])
        out["wa_url"] = wa_url(c, out["link"])
    out["files"] = {k: bool(files.exists(c["id"], k + ".pdf") or files.exists(c["id"], k + ".html"))
                    for k in ("draft", "signed", "final")}
    out["can"] = {
        "edit": role in EDIT_ROLES and st == "draft",
        "send": role in EDIT_ROLES and st == "draft",
        "void": (role in ADMIN_ROLES or (role in EDIT_ROLES and actor == c.get("created_by")))
                and engine.can("void", c)[0],
        "resend": role in EDIT_ROLES and st == "expired",
        "countersign": role in ADMIN_ROLES and st == "signed_owner",
    }
    out["needs_reissue"] = db.has_event(c["id"], "needs_reissue") and st not in ("void", "completed")
    if edit and out["can"]["edit"]:
        out["draft_answers"] = files.read_json(c["id"], "draft_answers.json", {}) or {}
    return 200, out


def wa_url(c, link):
    a = db.answers(c)
    digits = "".join(ch for ch in str(c.get("mobile") or "") if ch.isdigit())
    name = engine.greeting_name(a)
    hon = "" if engine.is_company(a) else engine.honorific(a) + " "
    msg = ("السلام عليكم %s%s، هذا رابط عقد تشغيل وحداتك مع عوجا (%s). افتحه من جوالك، "
           "اكتب آخر 4 أرقام من %s للتحقق، اقرأ العقد ووقّعه من نفس الصفحة: %s"
           % (hon, name, c.get("ref"), "السجل التجاري" if engine.is_company(a) else "هويتك", link))
    return "https://wa.me/%s?text=%s" % (digits, urllib.parse.quote(msg))


def core_preview(body):
    answers = body.get("answers") if isinstance(body.get("answers"), dict) else {}
    clean, errors = catalogue.validate(answers, _today())
    ref = None
    if body.get("id"):
        c = db.get(body.get("id"))
        ref = c.get("ref") if c else None
    html = files.for_screen(_preview_for(clean, ref))
    return 200, {"ok": True, "html": html, "errors": errors, "warnings": catalogue.warnings(clean),
                 "blockers": catalogue.send_blockers(clean)}


def _summary_fields(clean):
    s = engine.signer(clean)
    return {
        "client_kind": clean.get("client_kind"), "client_name": engine.client_name(clean),
        "gender": clean.get("gender") or ("company" if engine.is_company(clean) else ""),
        "id_last4": engine.last4(s["secret"]), "mobile": clean.get("mobile") or "",
        "units_count": len(clean.get("units") or []), "op_pct": catalogue.op_pct_value(clean),
        "answers_json": json.dumps(engine.masked_answers(clean), ensure_ascii=False),
        "warnings_json": json.dumps(catalogue.warnings(clean), ensure_ascii=False),
    }


def core_save(body, actor):
    answers = body.get("answers") if isinstance(body.get("answers"), dict) else {}
    clean, errors = catalogue.validate(answers, _today())
    if not clean.get("client_kind"):
        return _refuse("اختر نوع العميل على الأقل قبل الحفظ", fields=errors)
    fields = _summary_fields(clean)
    cid = body.get("id")
    if cid:
        c = db.get(cid)
        if not c:
            return _refuse("ما لقيت العقد")
        ok, why = engine.can("edit", c)
        if not ok:
            return _refuse(why)
        if not db.update_where_status(c["id"], ("draft",), **fields):
            return _refuse("العقد ما عاد مسودة")
        files.write_json(c["id"], "draft_answers.json", answers)
        db.add_event(c["id"], actor, "saved", {})
    else:
        tname = engine.template_for(clean)[0] or config.template_name()
        fields.update({"created_by": actor, "template_name": tname,
                       "template_version": config.template_version(tname)})
        new_id = db.create(fields)
        db.update(new_id, ref=engine.contract_ref(new_id, _today().year))
        files.write_json(new_id, "draft_answers.json", answers)
        db.add_event(new_id, actor, "created", {})
        c = db.get(new_id)
    c = db.get(c["id"])
    return 200, {"ok": True, "id": c["id"], "ref": c["ref"], "errors": errors,
                 "warnings": catalogue.warnings(clean), "blockers": catalogue.send_blockers(clean)}


def core_send(body, actor):
    c = db.get(body.get("id"))
    if not c:
        return _refuse("ما لقيت العقد")
    ok, why = engine.can("send", c)
    if not ok:
        return _refuse(why)
    answers = files.read_json(c["id"], "draft_answers.json", None)
    if answers is None:
        return _refuse("بيانات المسودة غير موجودة — عبّي الاستبيان من جديد")
    clean, errors = catalogue.validate(answers, _today())
    if errors:
        return _refuse("فيه خانات ناقصة أو غير صحيحة", fields=errors)
    blockers = catalogue.send_blockers(clean)
    if blockers:
        return _refuse(blockers[0], blockers=blockers)
    missing = operator_missing()
    if missing:
        return _refuse(operator_refusal(missing), operator_missing=missing)
    tname, why = engine.template_for(clean)
    if not tname:                                   # unreachable after send_blockers; defence in depth
        return _refuse(why)
    frozen = _render_preview(clean, c["ref"], frozen=True, template_name=tname)
    files.write_text(c["id"], "frozen.html", frozen)
    sha = engine.doc_hash(frozen.encode("utf-8"))
    now = _now_utc()
    token = secrets.token_urlsafe(32)
    fields = dict(_summary_fields(clean), template_name=tname, template_version=config.template_version(tname),
                  doc_sha256=sha, token=token, token_created_at=_iso(now), sent_at=_iso(now),
                  expires_at=_iso(now + datetime.timedelta(days=ttl_days())))
    if not db.transition(c["id"], ("draft",), "sent", **fields):
        files.remove(c["id"], "frozen.html")
        return _refuse("العقد ما عاد مسودة")
    files.remove(c["id"], "draft_answers.json")          # PDPL: the full ID now lives only in frozen.html
    for n in ("draft.pdf", "draft.html", "draft-a.pdf", "draft-a.html"):
        files.remove(c["id"], n)
    db.add_event(c["id"], actor, "sent", {"doc_sha256": sha[:16]})
    c = db.get(c["id"])
    link = sign_link(token)
    return 200, {"ok": True, "id": c["id"], "ref": c["ref"], "link": link, "wa_url": wa_url(c, link),
                 "send_via": clean.get("send_via"), "approved": is_approved(tname)}


def core_void(body, actor, admin):
    c = db.get(body.get("id"))
    if not c:
        return _refuse("ما لقيت العقد")
    c = touch(c)
    if not admin and actor != c.get("created_by"):
        return 403, {"ok": False, "error": "الإلغاء للمدير أو لمن أنشأ العقد"}
    reason = str(body.get("reason") or "").strip()
    if len(reason) < 3:
        return _refuse("اكتب سبب الإلغاء")
    ok, why = engine.can("void", c)
    if not ok:
        return _refuse(why)
    if not db.transition(c["id"], engine.TRANSITIONS["void"][0], "void", voided_by=actor,
                         voided_at=_iso(_now_utc()), void_reason=reason[:500], view_key=None):
        return _refuse("تغيّرت حالة العقد — حدّث الصفحة")
    files.remove(c["id"], "draft_answers.json")
    db.add_event(c["id"], actor, "void", {"reason": reason[:500]})
    return 200, {"ok": True}


def core_resend(body, actor):
    c = db.get(body.get("id"))
    if not c:
        return _refuse("ما لقيت العقد")
    c = touch(c)
    ok, why = engine.can("resend", c)
    if not ok:
        return _refuse(why)
    now = _now_utc()
    token = secrets.token_urlsafe(32)
    if not db.transition(c["id"], ("expired",), "sent", token=token, token_created_at=_iso(now),
                         expires_at=_iso(now + datetime.timedelta(days=ttl_days())), view_key=None,
                         view_key_until=None, verify_fails=0, verify_fails_total=0, locked_until=None):
        return _refuse("تغيّرت حالة العقد — حدّث الصفحة")
    db.add_event(c["id"], actor, "resent", {})
    c = db.get(c["id"])
    link = sign_link(token)
    return 200, {"ok": True, "link": link, "wa_url": wa_url(c, link)}


def core_countersign(body, actor):
    c = db.get(body.get("id"))
    if not c:
        return _refuse("ما لقيت العقد")
    ok, why = engine.can("countersign", c)
    if not ok:
        return _refuse(why)
    if not (files.settings_png_b64("op_sig.png") and files.settings_png_b64("op_stamp.png")):
        return _refuse("ارفع توقيع المشغّل والختم من الإعدادات أول")
    st = settings_values()
    if not (st.get("op_rep_name") or "").strip():
        return _refuse("اكتب اسم ممثل المشغّل وبيانات الوكالة في الإعدادات أول")
    now = _iso(_now_utc())
    if not db.transition(c["id"], ("signed_owner",), "completed", countersigned_by=actor, countersigned_at=now):
        return _refuse("العقد اكتمل مسبقاً أو تغيّرت حالته")
    c = db.get(c["id"])
    doc = engine.append_evidence(_overlay(c, approved=True, with_owner_sig=True, with_operator_sig=True),
                                 evidence(c))
    files.write_json(c["id"], "evidence.json", evidence(c))
    made = pdf.to_pdf(doc, files.path(c["id"], "final.pdf"))
    db.add_event(c["id"], actor, "countersigned", {"pdf": bool(made)})
    notify.completed(c)
    return 200, {"ok": True, "pdf": bool(made)}


def core_file(cid, kind):
    c = db.get(cid)
    if not c or kind not in ("draft", "signed", "final"):
        return None, None, None
    return _artifact(c, kind)


def core_settings_get(admin):
    out = {"ok": True, "values": settings_values(), "approval": approval(),
           "confirm_word": config.CONFIRM_WORD, "template": config.template_name(),
           "template_version": config.template_version(), "env_ttl_days": config.env_ttl_days(),
           "channel": config.channel(), "is_admin": admin, "operator_missing": operator_missing()}
    sig, stamp = files.settings_png_b64("op_sig.png"), files.settings_png_b64("op_stamp.png")
    out["has_sig"], out["has_stamp"] = bool(sig), bool(stamp)
    if admin:
        out["sig_png"], out["stamp_png"] = sig, stamp
    return 200, out


def core_settings_save(body, actor):
    vals = body.get("values") if isinstance(body.get("values"), dict) else {}
    for k, v in vals.items():
        if k in config.EDITABLE_SETTINGS:
            if k == "link_ttl_days" and str(v).strip():
                try:
                    if not 1 <= int(str(v).strip()) <= 90:
                        raise ValueError
                except ValueError:
                    return _refuse("مدة الرابط بين 1 و 90 يوم")
            val = str(v).strip()[:500]
            if k in DATE_SETTINGS and re.fullmatch(r"\d{4}-\d{2}-\d{2}", val):
                val = engine.date_g(val)          # stored as the text the contract prints
            db.set_setting(k, val, actor)
    for field, name in (("op_sig_png", "op_sig.png"), ("op_stamp_png", "op_stamp.png")):
        if body.get(field):
            data = files.decode_png_b64(body.get(field))
            err = files.check_png(data)
            if err:
                return _refuse(err)
            files.save_settings_png(name, data)
            db.set_setting(name, "1", actor)
    if "approve" in body:
        key = config.approval_key()
        if body.get("approve"):
            if str(body.get("confirm") or "").strip() != config.CONFIRM_WORD:
                return _refuse("للاعتماد اكتب «%s» بالضبط" % config.CONFIRM_WORD)
            missing = operator_missing()
            if missing:
                return _refuse(operator_refusal(missing), operator_missing=missing)
            db.set_setting(key, "1", actor)
        else:
            db.set_setting(key, "0", actor)
    return core_settings_get(True)


# ================================================================== public cores

def _public_state(c):
    st = c["status"]
    if st == "draft":
        return "invalid"
    return st


def _locked(c):
    lu = _dt(c.get("locked_until"))
    return bool(lu and _now_utc() < lu)


def core_public_get(token):
    if not config.enabled():
        return 200, {"ok": False, "state": "invalid", "error": INVALID_LINK}
    c = db.by_token(token)
    if not c or c["status"] == "draft":
        return 200, {"ok": False, "state": "invalid", "error": INVALID_LINK}
    c = touch(c)
    s, a = _signer_of(c)
    return 200, {
        "ok": True, "state": _public_state(c), "ref": c.get("ref"),
        "greeting": engine.greeting_name(a), "honorific": "" if engine.is_company(a) else engine.honorific(a),
        "gender": c.get("gender"), "client_kind": c.get("client_kind"),
        "units_count": c.get("units_count"), "op_pct": c.get("op_pct"),
        "approved": is_approved(c.get("template_name")), "last4_kind": _last4_kind(a),
        "locked": _locked(c), "expires_at": c.get("expires_at"),
    }


def core_public_open(token, ip, ua):
    if not config.enabled():
        return _refuse(INVALID_LINK)
    c = db.by_token(token)
    if not c or c["status"] == "draft":
        return _refuse(INVALID_LINK)
    c = touch(c)
    if c["status"] in ("void", "expired"):
        return 200, {"ok": True}
    since = _iso(_now_utc() - datetime.timedelta(minutes=10))
    if db.recent_event(c["id"], "opened", since, ip=ip):
        return 200, {"ok": True}
    now = _iso(_now_utc())
    db.transition(c["id"], ("sent",), "opened")
    if not c.get("first_open_at"):
        db.update(c["id"], first_open_at=now)
    db.bump(c["id"], "open_count")
    db.add_event(c["id"], "العميل", "opened", {"ip": ip, "ua": ua[:120]})
    return 200, {"ok": True}


def core_public_verify(token, last4, ip):
    if not config.enabled():
        return _refuse(GENERIC_VERIFY_FAIL)
    c = db.by_token(token)
    if not c or c["status"] == "draft":
        return _refuse(GENERIC_VERIFY_FAIL)
    c = touch(c)
    if c["status"] == "void":
        return _refuse("هذا العقد أُلغي")
    if c["status"] == "expired":
        return _refuse("انتهت صلاحية الرابط — تواصل مع مدير حسابك")
    if _locked(c):
        return _refuse("حاولت كثير — جرّب بعد ساعة", locked=True)
    given = str(last4 or "").translate(catalogue.DIGITS).strip().upper()
    want = str(c.get("id_last4") or "").upper()
    if not want or len(given) != 4 or not secrets.compare_digest(given, want):
        db.bump(c["id"], "verify_fails")
        db.bump(c["id"], "verify_fails_total")
        c2 = db.get(c["id"])
        if int(c2.get("verify_fails_total") or 0) >= config.VERIFY_MAX_TOTAL:
            # R5: the link stops for good. The phone sees the ordinary expired card (no reason
            # leaks); the team gets ONE line and sends a fresh link (resend resets the counter).
            db.update(c["id"], expires_at=_iso(_now_utc() - datetime.timedelta(seconds=1)), view_key=None)
            c2 = touch(db.get(c["id"]))
            if not db.has_event(c["id"], "attempts_cap"):
                db.add_event(c["id"], "النظام", "attempts_cap", {"ip": ip})
                notify.attempts_cap(c2)
            return _refuse(GENERIC_VERIFY_FAIL)
        if int(c2.get("verify_fails") or 0) >= config.VERIFY_MAX_FAILS:
            db.update(c["id"], verify_fails=0,
                      locked_until=_iso(_now_utc() + datetime.timedelta(minutes=config.LOCK_MINUTES)))
            db.add_event(c["id"], "النظام", "locked", {"ip": ip})
        return _refuse(GENERIC_VERIFY_FAIL)
    now = _now_utc()
    key = secrets.token_urlsafe(24)
    db.transition(c["id"], ("sent", "opened"), "verified")
    db.update(c["id"], verify_fails=0, view_key=key,
              view_key_until=_iso(now + datetime.timedelta(minutes=config.VIEW_KEY_MINUTES)))
    # verified_at is EVIDENCE: it only moves before the signature. A client re-checking later
    # to download their copy must not rewrite the certificate.
    db.update_where_status(c["id"], ("verified",), verified_at=_iso(now))
    db.add_event(c["id"], "العميل", "verified", {"ip": ip})
    c = db.get(c["id"])
    approved = is_approved(c.get("template_name"))
    done = c["status"] in ("signed_owner", "completed")
    html = files.for_screen(_overlay(c, approved=approved or done, with_owner_sig=done,
                                     with_operator_sig=c["status"] == "completed"))
    return 200, {"ok": True, "view_key": key, "html": html, "state": c["status"], "approved": approved,
                 "can_sign": approved and c["status"] == "verified",
                 "signer_name": _signer_of(c)[0]["name"]}


def _view_ok(c, key):
    if not c or not key or not c.get("view_key"):
        return False
    until = _dt(c.get("view_key_until"))
    return bool(until and _now_utc() <= until and secrets.compare_digest(str(key), str(c["view_key"])))


def core_public_sign(body, ip, ua):
    token = body.get("token")
    c = db.by_token(token) if config.enabled() else None
    if not c or c["status"] == "draft":
        return _refuse(INVALID_LINK)
    c = touch(c)
    st = c["status"]
    if st == "void":
        return _refuse("هذا العقد أُلغي")
    if st == "expired":
        return _refuse("انتهت صلاحية الرابط — تواصل مع مدير حسابك")
    if st in ("signed_owner", "completed"):
        return _refuse("العقد موقّع مسبقاً", state=st)
    if not _view_ok(c, body.get("view_key")) or st != "verified":
        return _refuse("انتهت جلسة التحقق — اكتب آخر 4 أرقام مرة ثانية", reverify=True)
    if not engine.template_for(db.answers(c))[0]:
        # R2 defence in depth: sent before the routing rule (a company / Ouja-account contract
        # on v2.1). It can never be signed, even after v2.1 is approved.
        return _refuse("هذا العقد يحتاج إعادة إصدار — تواصل مع مدير حسابك")
    if not is_approved(c.get("template_name")):
        return _refuse("التوقيع غير متاح — النموذج قيد المراجعة القانونية")
    if body.get("consent") is not True:
        return _refuse("لازم توافق على الإقرار قبل التوقيع")
    typed = " ".join(str(body.get("typed_name") or "").split())[:200]
    signer, _a = _signer_of(c)
    if engine.name_similarity(typed, signer["name"]) < config.NAME_MIN_SIMILARITY:
        return _refuse("الاسم المكتوب ما يطابق الاسم في العقد — اكتبه كما في الهوية")
    data = files.decode_png_b64(body.get("signature_png_b64"))
    err = files.check_png(data, min_ink=config.SIG_MIN_INK)
    if err:
        return _refuse(err)
    tmp_name = "signature.%s.tmp" % secrets.token_hex(6)
    files.write_bytes(c["id"], tmp_name, data)
    now = _iso(_now_utc())
    if not db.transition(c["id"], ("verified",), "signed_owner", signed_at=now, signer_typed_name=typed,
                         signer_ip=ip, signer_ua=ua):
        files.remove(c["id"], tmp_name)
        return _refuse("العقد موقّع مسبقاً")
    os.replace(files.path(c["id"], tmp_name), files.path(c["id"], "signature.png"))
    c = db.get(c["id"])
    ev = evidence(c)
    files.write_json(c["id"], "evidence.json", ev)
    db.add_event(c["id"], "العميل", "signed", {"ip": ip})
    try:
        doc = engine.append_evidence(_overlay(c, approved=True, with_owner_sig=True, with_operator_sig=False), ev)
        made = pdf.to_pdf(doc, files.path(c["id"], "signed.pdf"))
    except Exception:
        traceback.print_exc()           # the signature is stored; the PDF is rebuilt on download
        made = False
    notify.signed(c)
    return 200, {"ok": True, "state": "signed_owner", "pdf": bool(made),
                 "download": "/api/aqd-t/%s/file?k=%s" % (token, body.get("view_key"))}


def core_public_file(token, key):
    c = db.by_token(token) if config.enabled() else None
    if not c or c["status"] == "draft" or not _view_ok(c, key):
        return None, None, None
    if c["status"] == "completed":
        p = _artifact(c, "final")
        if p[0]:
            return p
    if c["status"] in ("signed_owner", "completed"):
        p = _artifact(c, "signed")
        if p[0]:
            return p
        # the PDF step failed at signing time: rebuild it now from the stored signature
        doc = engine.append_evidence(_overlay(c, approved=True, with_owner_sig=True, with_operator_sig=False),
                                     evidence(c))
        pdf.to_pdf(doc, files.path(c["id"], "signed.pdf"))
        return _artifact(c, "signed")
    if c["status"] in ("void", "expired"):
        return None, None, None
    return _artifact(c, "draft")


# ================================================================== handlers

async def api_schema(request):
    return _reply(await _run(core_schema))


async def api_list(request):
    return _reply(await _run(core_list, _qs(request, "status") or None, _qs(request, "q") or None,
                             _role(request)))


async def api_get(request):
    return _reply(await _run(core_get, _qs(request, "id"), _role(request), _actor(request),
                             _qs(request, "edit") == "1"))


async def api_preview(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _reply(await _run(core_preview, b))


async def api_save(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _reply(await _run(core_save, b, _actor(request)))


async def api_send(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _reply(await _run(core_send, b, _actor(request)))


async def api_void(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _reply(await _run(core_void, b, _actor(request), is_admin(request)))


async def api_resend(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return _reply(await _run(core_resend, b, _actor(request)))


async def api_countersign(request):
    if not is_admin(request):
        return _deny("توقيع المشغّل للمدير فقط")
    b = await _body(request)
    return _reply(await _run(core_countersign, b, _actor(request)))


async def api_settings(request):
    if request.method == "POST":
        if not is_admin(request):
            return _deny("الإعدادات للمدير فقط")
        b = await _body(request)
        return _reply(await _run(core_settings_save, b, _actor(request)))
    return _reply(await _run(core_settings_get, is_admin(request)))


def _file_response(p, ctype, fname, inline=False):
    data = open(p, "rb").read()
    disp = "%s; filename*=UTF-8''%s" % ("inline" if inline else "attachment", urllib.parse.quote(fname or "contract"))
    return HOST.web.Response(body=data, headers={"Content-Type": ctype, "Content-Disposition": disp,
                                                 "Cache-Control": "private, no-store"})


async def api_file(request):
    p, ctype, fname = await _run(core_file, _qs(request, "id"), _qs(request, "kind") or "draft")
    if not p:
        return _json({"ok": False, "error": "الملف غير متاح"})
    data_resp = await _run(_file_response, p, ctype, fname, _qs(request, "inline") == "1")
    return data_resp


# ---- public

async def handle_sign_page(request):
    return HOST.web.Response(text=sign_page.html(), content_type="text/html",
                             headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


async def api_public_get(request):
    token = request.match_info.get("token") or ""
    if _limited(_ip(request), token):
        return _json({"ok": False, "state": "busy", "error": SLOW_DOWN})
    return _reply(await _run(core_public_get, token))


async def api_public_open(request):
    b = await _body(request)
    if _limited(_ip(request), b.get("token")):
        return _json({"ok": False, "error": SLOW_DOWN})
    return _reply(await _run(core_public_open, str(b.get("token") or ""), _ip(request), _ua(request)))


async def api_public_verify(request):
    b = await _body(request)
    if _limited(_ip(request), b.get("token")):
        return _json({"ok": False, "error": SLOW_DOWN})
    return _reply(await _run(core_public_verify, str(b.get("token") or ""), b.get("last4"), _ip(request)))


async def api_public_sign(request):
    b = await _body(request)
    if _limited(_ip(request), b.get("token")):
        return _json({"ok": False, "error": SLOW_DOWN})
    return _reply(await _run(core_public_sign, b, _ip(request), _ua(request)))


async def api_public_file(request):
    token = request.match_info.get("token") or ""
    if _limited(_ip(request), token):
        return _json({"ok": False, "error": SLOW_DOWN})
    p, ctype, fname = await _run(core_public_file, token, _qs(request, "k"))
    if not p:
        return _json({"ok": False, "error": "انتهت جلسة التحقق — اكتب آخر 4 أرقام مرة ثانية"})
    return await _run(_file_response, p, ctype, fname)


# ---- static (code, no data)

_js_cache = {}


def js_version(name="aqd_tab.js"):
    try:
        return str(int(os.path.getmtime(os.path.join(STATIC_DIR, name))))
    except OSError:
        return "0"


def _js_text(name):
    p = os.path.join(STATIC_DIR, name)
    m = os.path.getmtime(p)
    hit = _js_cache.get(name)
    if not hit or hit[0] != m:
        with open(p, encoding="utf-8") as f:
            _js_cache[name] = (m, f.read())
    return _js_cache[name][1]


async def handle_static(request):
    name = request.match_info.get("name") or ""
    if name not in STATIC_ALLOW:
        return HOST.web.Response(status=404, text="not found")
    text = await _run(_js_text, name)
    return HOST.web.Response(text=text, content_type="application/javascript",
                             headers={"Cache-Control": "no-cache"})


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    g("/aqd/static/{name}", handle_static)
    g("/api/aqd/schema", _safe(api_schema))
    g("/api/aqd/list", _safe(api_list))
    g("/api/aqd/get", _safe(api_get))
    g("/api/aqd/file", _safe(api_file))
    g("/api/aqd/settings", _safe(api_settings))
    p("/api/aqd/settings", _safe(api_settings))
    p("/api/aqd/preview", _safe(api_preview))
    p("/api/aqd/save", _safe(api_save))
    p("/api/aqd/send", _safe(api_send))
    p("/api/aqd/void", _safe(api_void))
    p("/api/aqd/resend", _safe(api_resend))
    p("/api/aqd/countersign", _safe(api_countersign))
    # Public — the token is the credential. The read sits OUTSIDE /api/aqd/ on purpose.
    g("/sign/{token}", handle_sign_page)
    g("/api/aqd-t/{token}", _safe_public(api_public_get))
    g("/api/aqd-t/{token}/file", _safe_public(api_public_file))
    p("/api/aqd-t/open", _safe_public(api_public_open))
    p("/api/aqd-t/verify", _safe_public(api_public_verify))
    p("/api/aqd-t/sign", _safe_public(api_public_sign))
