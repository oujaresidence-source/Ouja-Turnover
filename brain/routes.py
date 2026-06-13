"""
brain.routes — aiohttp handlers for /brain (page) and /api/brain/* (data + actions).
Every handler is guarded by the existing dashboard auth (HOST.dash_auth). JSON goes through
HOST.json_response (Arabic-safe). Nothing here sends WhatsApp live; Approve = CSV export.
"""

import json
from . import db, settings, signals, members, recommend, campaigns, adapters, governor
from . import dashboard
from .host import HOST


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"error": "unauthorized"}, 401)
    return None


async def _body(request):
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ---------------- page ----------------

async def page(request):
    if not HOST.dash_auth(request):
        return HOST.web.Response(text=dashboard.locked_html(), content_type="text/html", status=401)
    return HOST.web.Response(text=dashboard.page_html(), content_type="text/html")


# ---------------- reads ----------------

async def api_today(request):
    g = _guard(request)
    if g:
        return g
    force = request.query.get("force") in ("1", "true", "yes")
    return HOST.json_response({"ok": True, "move": recommend.todays_view(force=force)})


async def api_heatmap(request):
    g = _guard(request)
    if g:
        return g
    try:
        days = int(request.query.get("days", "30"))
    except (ValueError, TypeError):
        days = 30
    return HOST.json_response({"ok": True, "heatmap": signals.build_heatmap(days=max(7, min(45, days)))})


async def api_health(request):
    g = _guard(request)
    if g:
        return g
    members.ensure_seeded()
    hc = members.health_counts()
    last_sync = db.q1("SELECT created_at, payload FROM audit_log WHERE action='sync_upcoming_and_inhouse' "
                      "ORDER BY id DESC LIMIT 1")
    sync_info = None
    if last_sync:
        try:
            sync_info = {"at": last_sync["created_at"], **json.loads(last_sync["payload"] or "{}")}
        except (ValueError, TypeError):
            sync_info = {"at": last_sync["created_at"]}
    return HOST.json_response({"ok": True, "health": hc,
                               "daily_cap": governor.effective_daily_cap(),
                               "sent_today": governor.sent_today(),
                               "remaining_today": governor.remaining_today(),
                               "adapter": adapters.get_active().name,
                               "last_sync": sync_info})


async def api_campaigns(request):
    g = _guard(request)
    if g:
        return g
    return HOST.json_response({"ok": True, "campaigns": campaigns.list_campaigns()})


async def api_settings_get(request):
    g = _guard(request)
    if g:
        return g
    return HOST.json_response({"ok": True, "settings": settings.all_grouped()})


async def api_audience(request):
    g = _guard(request)
    if g:
        return g
    rec_id = request.match_info.get("rec_id")
    view = recommend.get_view(rec_id)
    if not view:
        return HOST.json_response({"error": "not_found"}, 404)
    return HOST.json_response({"ok": True, "move": view})


# ---------------- actions (writes) ----------------

async def api_recompute(request):
    g = _guard(request)
    if g:
        return g
    return HOST.json_response({"ok": True, "move": recommend.todays_view(force=True)})


async def api_settings_set(request):
    g = _guard(request)
    if g:
        return g
    data = await _body(request)
    updates = data.get("settings") if isinstance(data.get("settings"), dict) else data
    changed = {}
    for k, v in (updates or {}).items():
        if k in settings.DEFAULTS:
            changed[k] = settings.set_value(k, v)
    db.audit("dashboard", "settings_update", {"changed": changed})
    return HOST.json_response({"ok": True, "changed": changed, "settings": settings.all_grouped()})


async def api_approve(request):
    g = _guard(request)
    if g:
        return g
    data = await _body(request)
    rec_id = data.get("rec_id")
    res = recommend.approve(rec_id, actor="dashboard")
    # don't ship the whole CSV back in the JSON; the download route serves it
    res.pop("csv_text", None)
    status = 200 if res.get("ok") else 400
    return HOST.json_response(res, status)


async def api_reject(request):
    g = _guard(request)
    if g:
        return g
    data = await _body(request)
    return HOST.json_response(recommend.reject(data.get("rec_id"), actor="dashboard"))


async def api_seed(request):
    g = _guard(request)
    if g:
        return g
    return HOST.json_response({"ok": True, "result": members.recompute(full=True)})


async def api_seed_import(request):
    """Upload the cleaned member file (JSON array, or {members:[...]}). Saved to the volume
    (PII stays off git) and seeded immediately; auto-reseeds on future redeploys."""
    g = _guard(request)
    if g:
        return g
    try:
        data = await request.json()
    except Exception:
        return HOST.json_response({"ok": False, "error": "bad_json"}, 400)
    rows = data.get("members") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        return HOST.json_response({"ok": False, "error": "expected_member_array"}, 400)
    res = members.import_member_file(rows)
    return HOST.json_response({"ok": True, "total": members.count(), **res})


async def api_optout(request):
    g = _guard(request)
    if g:
        return g
    data = await _body(request)
    phone = (data.get("phone") or "").strip()
    if HOST.normalize_phone and phone:
        phone = HOST.normalize_phone(phone)
    if not phone:
        return HOST.json_response({"ok": False, "error": "no_phone"}, 400)
    governor.opt_out(phone, source="dashboard")
    return HOST.json_response({"ok": True, "phone": phone})


async def api_export(request):
    """Download the Karzoum-ready CSV for a recommendation (rebuilt on demand)."""
    g = _guard(request)
    if g:
        return g
    rec_id = request.match_info.get("rec_id")
    row = db.q1("SELECT * FROM recommendations WHERE id=?", (rec_id,))
    if not row:
        return HOST.json_response({"error": "not_found"}, 404)
    if row["status"] == "silent":
        return HOST.json_response({"error": "silent_day"}, 400)
    pkg = recommend._build_package(row)
    if not pkg:
        return HOST.json_response({"error": "empty_audience"}, 400)
    filename, text = adapters.build_csv(pkg)
    return HOST.web.Response(
        text=text, content_type="text/csv", charset="utf-8",
        headers={"Content-Disposition": 'attachment; filename="%s"' % filename})


def register(app):
    """Wire every Brain route onto the existing aiohttp app."""
    app.router.add_get("/brain", page)
    app.router.add_get("/api/brain/today", api_today)
    app.router.add_get("/api/brain/heatmap", api_heatmap)
    app.router.add_get("/api/brain/health", api_health)
    app.router.add_get("/api/brain/campaigns", api_campaigns)
    app.router.add_get("/api/brain/settings", api_settings_get)
    app.router.add_get("/api/brain/audience/{rec_id}", api_audience)
    app.router.add_get("/api/brain/export/{rec_id}", api_export)
    app.router.add_post("/api/brain/recompute", api_recompute)
    app.router.add_post("/api/brain/settings", api_settings_set)
    app.router.add_post("/api/brain/approve", api_approve)
    app.router.add_post("/api/brain/reject", api_reject)
    app.router.add_post("/api/brain/seed", api_seed)
    app.router.add_post("/api/brain/seed-import", api_seed_import)
    app.router.add_post("/api/brain/optout", api_optout)
