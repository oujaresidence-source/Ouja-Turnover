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
    try:
        years = max(1, min(3, int(request.rel_url.query.get("years") or 2)))
    except ValueError:
        years = 2
    out = await asyncio.to_thread(collect.diagnose_months, ",".join(months),
                                  None, years)
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
    try:
        windows = max(1, min(4, int(q.get("windows") or 1)))
    except ValueError:
        windows = 1
    out = await asyncio.to_thread(collect.trace, int(lid), month, None, windows)
    out["ok"] = True
    return HOST.json_response(out)


async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


def _bad(msg):
    return HOST.json_response({"ok": False, "error": "bad_args", "message": msg}, 200)


def _month_of(request):
    m = (request.rel_url.query.get("month") or "").strip()
    return m if (len(m) == 7 and m[4] == "-") else None


async def _api_units(request):
    import asyncio
    from . import collect
    month = _month_of(request)
    if not month:
        return _bad("اكتب الشهر بالصيغة YYYY-MM مثل 2026-10")
    force = request.rel_url.query.get("refresh") in ("1", "true")
    out = await asyncio.to_thread(collect.units_report, month, force)
    out["ok"] = True
    return HOST.json_response(out)


async def _api_price(request):
    import asyncio
    from . import collect
    month = _month_of(request)
    lid = (request.rel_url.query.get("lid") or "").strip()
    if not month or not lid.isdigit():
        return _bad("استخدم ?lid=457230&month=2026-10")
    out = await asyncio.to_thread(collect.price_one, int(lid), month)
    return HOST.json_response({"ok": True, "price": out})


async def _api_attrs_get(request):
    from . import attrs, db
    lid = (request.rel_url.query.get("lid") or "").strip()
    if not lid.isdigit():
        return _bad("استخدم ?lid=457230")
    vals = db.unit_attrs(int(lid))
    detail = db.unit_attrs_detailed(int(lid))
    rows = attrs.rows_for_ui(vals)
    for r in rows:
        d = detail.get(r["key"]) or {}
        r["scored_by"] = d.get("scored_by")
        r["scored_at"] = d.get("scored_at")
    return HOST.json_response({
        "ok": True, "lid": int(lid), "rows": rows,
        "anchor_ar": attrs.SCORE_ANCHOR_AR, "anchor_en": attrs.SCORE_ANCHOR_EN,
        "protocol_ar": attrs.SCORING_PROTOCOL_AR,
        "protocol_en": attrs.SCORING_PROTOCOL_EN,
        "unanswered": attrs.unanswered(vals),
    })


async def _api_attrs_set(request):
    from . import attrs, db
    b = await _body(request)
    lid, key = b.get("lid"), b.get("key")
    if not str(lid or "").isdigit() or not attrs.is_known(key):
        return _bad("بيانات ناقصة أو صفة غير معروفة")
    value = b.get("value")
    if isinstance(value, str) and not value.strip():
        value = None
    actor = HOST.actor(request) if HOST.actor else None
    db.set_attr(int(lid), key, value, actor=actor)
    from . import collect
    collect._CACHE.pop((b.get("month") or ""), None)
    return HOST.json_response({"ok": True, "lid": int(lid), "key": key,
                               "value": value, "scored_by": actor})


async def _api_quote(request):
    """Freeze a quote. The override needs a typed reason or the write is refused —
    a price moved by a human with no recorded why is one nobody can defend to an
    owner six weeks later."""
    import asyncio
    from . import attrs, collect, db
    b = await _body(request)
    lid, month = b.get("lid"), (b.get("month") or "").strip()
    if not str(lid or "").isdigit() or len(month) != 7:
        return _bad("بيانات ناقصة")
    try:
        pct = float(b.get("override_pct") or 0.0)
    except (TypeError, ValueError):
        return _bad("نسبة التعديل لازم تكون رقم")
    if pct < -0.20 or pct > 0.40:
        return _bad("نسبة التعديل لازم بين -20% و +40%")
    reason = (b.get("reason") or "").strip()
    if abs(pct) > 1e-9 and not reason:
        return _bad("اكتب سبب التعديل — ما ينحفظ تعديل بدون سبب")
    p = await asyncio.to_thread(collect.price_one, int(lid), month)
    if p.get("price") is None:
        return _bad("ما فيه سعر لهذي الوحدة هذا الشهر — %s"
                    % ", ".join(p.get("warnings") or []))
    final = p["price"] * (1.0 + pct)
    qid = db.save_quote(int(lid), month, p["price"], final, p["bound_by"],
                        p["confidence"], attrs.BETA_VERSION, p,
                        override_pct=pct,
                        created_by=(HOST.actor(request) if HOST.actor else None))
    if abs(pct) > 1e-9:
        db.log_override(qid, 0.0, pct, reason,
                        actor=(HOST.actor(request) if HOST.actor else None))
    return HOST.json_response({"ok": True, "quote_id": qid, "price": p["price"],
                               "final_price": final, "override_pct": pct})


async def _api_override(request):
    from . import db
    b = await _body(request)
    qid = b.get("quote_id")
    if not str(qid or "").isdigit():
        return _bad("رقم التسعيرة ناقص")
    try:
        pct = float(b.get("to_pct") or 0.0)
    except (TypeError, ValueError):
        return _bad("نسبة التعديل لازم تكون رقم")
    q = db.get_quote(int(qid))
    if not q:
        return _bad("ما لقينا التسعيرة")
    try:
        db.log_override(int(qid), q.get("override_pct") or 0.0, pct,
                        b.get("reason") or "",
                        actor=(HOST.actor(request) if HOST.actor else None))
    except db.ReasonRequired as e:
        return _bad(str(e))
    return HOST.json_response({"ok": True, "quote_id": int(qid), "to_pct": pct})


async def _page(request):
    g = _guard(request)
    if g:
        return HOST.web.Response(
            text="<h3 dir=rtl style=font-family:system-ui>تحتاج تسجيل دخول المالك"
                 " — افتح /dashboard وسجّل الدخول ثم ارجع لهذي الصفحة.</h3>",
            content_type="text/html", status=403)
    from . import page
    return HOST.web.Response(text=page.HTML, content_type="text/html")


def register(app):
    app.router.add_get("/api/mrent/health", _safe(_api_health))
    app.router.add_get("/api/mrent/diagnose", _safe(_api_diagnose))
    app.router.add_get("/api/mrent/trace", _safe(_api_trace))
    app.router.add_get("/monthly-lab", _page)
    app.router.add_get("/api/mrent/units", _safe(_api_units))
    app.router.add_get("/api/mrent/price", _safe(_api_price))
    app.router.add_get("/api/mrent/attrs", _safe(_api_attrs_get))
    app.router.add_post("/api/mrent/attrs", _safe(_api_attrs_set))
    app.router.add_post("/api/mrent/quote", _safe(_api_quote))
    app.router.add_post("/api/mrent/override", _safe(_api_override))
