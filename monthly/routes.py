# -*- coding: utf-8 -*-
"""
monthly.routes — endpoints for «التسعير الشهري», all under /api/mrent/.

READ-ONLY AGAINST HOSTAWAY. Writes in this package touch our own SQLite only
(attribute scores, Ejar references, frozen quotes, overrides) — never a price
in Hostaway.

GATING. Everything here is double-gated: login (dash_auth) AND role in
ADMIN_ROLES. This surface exposes floors, margins, the management fee and an
owner's Ejar position across the whole portfolio — the same reasoning that made
/pricecheck owner-only. Like pricecheck, it is deliberately NOT wired into the
per-page permission matrix: that matrix denies unknown tabs by default, so a new
id there would silently lock people out until the owner ticked a box nobody told
them about.
"""

import traceback

from .host import HOST

ADMIN_ROLES = ("admin",)


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    role = "viewer"
    try:
        role = HOST.req_role(request) if HOST.req_role else "viewer"
    except Exception:
        role = "viewer"
    if role not in ADMIN_ROLES:
        return HOST.json_response(
            {"ok": False, "error": "forbidden",
             "message": "هذي الصفحة للمالك فقط"}, 403)
    return None


def _safe(fn):
    """Guard, then never leak a traceback to the browser. Status 200 with
    ok:false so the page can say what went wrong in Arabic instead of dying."""
    async def _w(request):
        g = _guard(request)
        if g:
            return g
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response(
                {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _api_health(request):
    """Proves the whole chain end to end — routing, login gate, role gate, JSON —
    with no user-facing surface to get wrong. The page arrives at S10."""
    return HOST.json_response({
        "ok": True,
        "stage": "S2",
        "package": "monthly",
        "read_only": True,
    })


async def _api_diagnose(request):
    """The S8 diagnosis, run where the Hostaway credentials actually live.

    It cannot run on a developer laptop — there are no credentials and no cached
    reservations there — so it is exposed as an endpoint rather than a script.
    Read-only: it prices units in memory and stores nothing.
    """
    import asyncio
    from . import collect
    raw = (request.rel_url.query.get("month") or "").strip()
    months = [m.strip() for m in raw.split(",") if m.strip()]
    if not months or any(len(m) != 7 or m[4] != "-" for m in months):
        return HOST.json_response(
            {"ok": False, "error": "bad_month",
             "message": "اكتب الشهر بالصيغة YYYY-MM — أو عدة شهور مفصولة بفواصل، "
                        "مثل 2026-08,2026-10,2027-01"}, 200)
    if len(months) > 6:
        return HOST.json_response(
            {"ok": False, "error": "too_many_months",
             "message": "أقصى 6 شهور في المرة الوحدة"}, 200)
    out = await asyncio.to_thread(collect.diagnose_months, ",".join(months))
    out["ok"] = True
    if (request.rel_url.query.get("format") or "").lower() == "text":
        from . import diagnose as _diag
        return HOST.web.Response(text=_diag.render_text(out),
                                 content_type="text/plain", charset="utf-8")
    return HOST.json_response(out)


async def _api_trace(request):
    """Every step for one unit, so a join failure is visible rather than inferred."""
    import asyncio
    from . import collect
    q = request.rel_url.query
    lid, month = (q.get("lid") or "").strip(), (q.get("month") or "").strip()
    if not lid.isdigit() or len(month) != 7 or month[4] != "-":
        return HOST.json_response(
            {"ok": False, "error": "bad_args",
             "message": "استخدم ?lid=457230&month=2026-08"}, 200)
    out = await asyncio.to_thread(collect.trace, int(lid), month)
    out["ok"] = True
    return HOST.json_response(out)


def register(app):
    app.router.add_get("/api/mrent/health", _safe(_api_health))
    app.router.add_get("/api/mrent/diagnose", _safe(_api_diagnose))
    app.router.add_get("/api/mrent/trace", _safe(_api_trace))
