# -*- coding: utf-8 -*-
"""
business.routes — aiohttp handlers for /business (superprompt §1).

The trust core is PUBLIC (no auth, indexable). Corporate/vendor form submissions
route into the EXISTING ticketing intake (HOST.ticket_create) — no new inbox — and
are additionally appended to a durable business_leads.json so a lead is never lost
even if ticket creation hiccups.
"""
import asyncio
import time
import traceback

from . import manage, page
from .host import HOST

_301 = ("/partners", "/profile", "/b2b")  # different words, same page


def _links():
    return HOST.links or {}


async def handle_en(request):
    html = page.render_page("en", base=HOST.base_url, links=_links())
    return HOST.web.Response(text=html, content_type="text/html", charset="utf-8")


async def handle_ar(request):
    html = page.render_page("ar", base=HOST.base_url, links=_links())
    return HOST.web.Response(text=html, content_type="text/html", charset="utf-8")


async def handle_redirect(request):
    raise HOST.web.HTTPMovedPermanently("/business")


async def _read_body(request):
    try:
        return await request.json()
    except Exception:
        try:
            data = await request.post()
            return dict(data)
        except Exception:
            return {}


_ALLOWED_FIELDS = (
    "company", "contact", "email", "phone", "dates", "units", "city",
    "category", "pricing", "min", "entity", "clients", "message",
)


def _clean(data):
    out = {}
    for k in _ALLOWED_FIELDS:
        v = data.get(k)
        if v is None:
            continue
        out[k] = str(v).strip()[:2000]
    return out


def _summary(kind, d):
    who = d.get("company") or d.get("contact") or d.get("email") or d.get("phone") or "—"
    label = "Corporate housing request" if kind == "lead" else "Vendor proposal"
    lines = ["%s — %s" % (label, who)]
    for k in _ALLOWED_FIELDS:
        if d.get(k):
            lines.append("%s: %s" % (k, d[k]))
    return "\n".join(lines)


async def _submit(request, kind):
    raw = await _read_body(request)
    d = _clean(raw)
    if not d.get("email") and not d.get("phone"):
        return HOST.json_response({"ok": False, "error": "contact_required"}, 400)

    rec = {"kind": kind, "at": int(time.time()), "fields": d}

    # 1) durable append — a lead is never dropped
    try:
        if HOST.save_json and HOST.load_json:
            store = HOST.load_json("business_leads.json", {"leads": []}) or {"leads": []}
            store.setdefault("leads", []).append(rec)
            store["leads"] = store["leads"][-500:]
            HOST.save_json("business_leads.json", store)
    except Exception:
        traceback.print_exc()

    # 2) into the existing ticketing intake (no new inbox)
    ticket_ok = False
    try:
        if HOST.ticket_create:
            title = ("Corporate housing — " if kind == "lead" else "Vendor proposal — ") + \
                    (d.get("company") or d.get("contact") or d.get("email") or d.get("phone") or "web")
            HOST.ticket_create(
                title,
                description=_summary(kind, d),
                category=("corporate" if kind == "lead" else "vendor"),
                source="business",
            )
            ticket_ok = True
    except Exception:
        traceback.print_exc()

    # 3) optional Discord nudge
    try:
        if HOST.notify:
            HOST.notify({"kind": kind, "summary": _summary(kind, d)})
    except Exception:
        pass

    return HOST.json_response({"ok": True, "ticket": ticket_ok})


def _safe_public(fn):
    """PUBLIC wrapper — the trust core and lead forms need no auth. Errors return a
    clean JSON 200 rather than a stack trace to a prospect."""
    async def _w(request):
        try:
            return await fn(request)
        except Exception as e:
            if isinstance(e, HOST.web.HTTPException):
                raise
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s" % type(e).__name__}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def api_lead(request):
    return await _submit(request, "lead")


async def api_proposal(request):
    return await _submit(request, "proposal")


# --------------------------------------------------------------------------- #
# featured-residences picker (login-gated)
# --------------------------------------------------------------------------- #
def _authed(request):
    try:
        return bool(HOST.dash_auth and HOST.dash_auth(request))
    except Exception:
        return False


def _safe_auth(fn):
    """Login-gated wrapper for the manage page + its write endpoints."""
    async def _w(request):
        if not _authed(request):
            return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
        try:
            return await fn(request)
        except Exception as e:
            if isinstance(e, HOST.web.HTTPException):
                raise
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s" % type(e).__name__}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def handle_manage(request):
    if not _authed(request):
        return HOST.web.Response(text="Unauthorized. Open this from the dashboard while signed in.",
                                 status=401, content_type="text/plain")
    return HOST.web.Response(text=manage.MANAGE_HTML, content_type="text/html", charset="utf-8")


async def api_manage(request):
    options = []
    try:
        if HOST.hostaway_listings:
            options = await asyncio.to_thread(HOST.hostaway_listings)
    except Exception:
        traceback.print_exc()
        options = []
    saved = {"listings": []}
    try:
        if HOST.load_json:
            saved = HOST.load_json("business_listings.json", {"listings": []}) or {"listings": []}
    except Exception:
        traceback.print_exc()
    return HOST.json_response({"ok": True, "options": options, "saved": saved})


_LST_FIELDS = ("title", "area", "tagline", "photo")


async def api_listings_save(request):
    raw = await _read_body(request)
    items = raw.get("listings") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return HOST.json_response({"ok": False, "error": "bad_payload"}, 400)
    clean = []
    for it in items[:20]:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        rec = {"id": str(it.get("id"))}
        for f in _LST_FIELDS:
            v = it.get(f)
            if v is not None:
                rec[f] = str(v).strip()[:400]
        try:
            rec["order"] = int(it.get("order", 999))
        except Exception:
            rec["order"] = 999
        clean.append(rec)
    clean.sort(key=lambda r: r.get("order", 999))
    if HOST.save_json:
        HOST.save_json("business_listings.json", {"listings": clean})
    return HOST.json_response({"ok": True, "saved": len(clean)})


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    g("/business", _safe_public(handle_en))
    g("/business/ar", _safe_public(handle_ar))
    for path in _301:
        g(path, handle_redirect)
    p("/api/business/lead", _safe_public(api_lead))
    p("/api/business/proposal", _safe_public(api_proposal))
    # featured-residences picker (login-gated)
    g("/business/manage", handle_manage)
    g("/api/business/manage", _safe_auth(api_manage))
    p("/api/business/listings", _safe_auth(api_listings_save))
