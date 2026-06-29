# -*- coding: utf-8 -*-
"""
brain.gap_routes — aiohttp handlers for the Elite v5 "Brain" screen (/api/brain/gaps*).

READ-ONLY against the business: the list endpoint computes today's ranked pushes + the 20-campaign
catalogue from the live grid + member base; NOTHING here messages a guest. Campaigns are pushed
MANUALLY through Karzoun → WhatsApp. The one write is the fatigue log: when an agent exports a
campaign's send list (the handoff to Karzoun), we record it in contact_log so the ≤1-msg/guest/7d
and never-the-same-campaign-within-14d guardrails hold across days. Kill-on-book is free: the
audience is recomputed live, so anyone who books drops out instantly.

The heavy work (live calendar pull, re-tiering many reservation windows) runs in a thread executor
so it never blocks the bot's single event loop.
"""

import asyncio
import json
import traceback
from datetime import date
from . import db, settings, cards, retier, playbook, triggers
from .host import HOST
from .util import now_iso, today_iso


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"error": "unauthorized"}, 401)
    return None


def _safe(fn):
    async def _wrapped(request):
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _wrapped.__name__ = getattr(fn, "__name__", "wrapped")
    return _wrapped


async def _body(request):
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _in_thread(fn, *a):
    return await asyncio.get_event_loop().run_in_executor(None, fn, *a)


# --------------------------- reads ---------------------------

async def api_gaps(request):
    g = _guard(request)
    if g:
        return g
    payload = await _in_thread(cards.build_cards)
    return HOST.json_response({"ok": True, **payload})


async def api_conversion(request):
    """Per-campaign handoff counts (how many guests were exported to Karzoun) + any attributed
    bookings. Read-only learning surface; no live data is needed."""
    g = _guard(request)
    if g:
        return g
    sent = {r["campaign_code"]: {"handed_off": r["c"]}
            for r in db.q("SELECT campaign_code, COUNT(*) c FROM contact_log GROUP BY campaign_code")}
    for r in db.q("SELECT campaign_code, COUNT(*) c, SUM(revenue) rev FROM attributions GROUP BY campaign_code"):
        row = sent.setdefault(r["campaign_code"], {"handed_off": 0})
        row["bookings"] = r["c"]
        row["revenue"] = round(r["rev"] or 0)
    return HOST.json_response({"ok": True, "conversion": sent})


async def api_calendar(request):
    """The editable Saudi trigger calendar (holiday dates resolved for the year + per-campaign
    trigger rules)."""
    g = _guard(request)
    if g:
        return g
    try:
        yr = int(request.query.get("year") or today_iso()[:4])
    except (ValueError, TypeError):
        yr = date.today().year
    overrides = cards._holiday_overrides()
    return HOST.json_response({"ok": True, "calendar": triggers.calendar_table(yr, overrides)})


# --------------------------- writes (settings / handoff log) ---------------------------

async def api_assumptions(request):
    """GET current assumptions; POST {click_through_pct, click_to_book_pct} to edit them. These
    flow straight into the conversion math + Y on the next load."""
    g = _guard(request)
    if g:
        return g
    if request.method == "POST":
        d = await _body(request)
        if "click_through_pct" in d:
            settings.set_value("assume_click_through_pct", d.get("click_through_pct"))
        if "click_to_book_pct" in d:
            settings.set_value("assume_click_to_book_pct", d.get("click_to_book_pct"))
        db.audit("dashboard", "gap_assumptions_set",
                 {"ct": settings.get_int("assume_click_through_pct"),
                  "cb": settings.get_int("assume_click_to_book_pct")})
    return HOST.json_response({"ok": True, "assumptions": cards._assumptions_from_settings()})


async def api_holidays(request):
    """POST {holidays: {NAME: 'YYYY-MM-DD', ...}} to override exact Saudi holiday dates."""
    g = _guard(request)
    if g:
        return g
    d = await _body(request)
    hol = d.get("holidays")
    if isinstance(hol, dict):
        settings.set_value("gap_holidays", json.dumps(hol, ensure_ascii=False))
        db.audit("dashboard", "gap_holidays_set", {"keys": sorted(hol.keys())})
    return HOST.json_response({"ok": True, "holidays": cards._holiday_overrides()})


def _log_handoff(code, audience):
    """Record a manual Karzoun handoff so the fatigue guardrails hold across days. Inserts one
    contact_log row per member (status 'queued'); the dashboard itself never sends anything."""
    if not audience:
        return 0
    db.init_db()
    sent_at = now_iso()
    db.executemany(
        "INSERT INTO contact_log(member_id, campaign_code, sent_at, status, replied) "
        "VALUES(?,?,?,?,0)",
        [(m.get("id"), code, sent_at, "queued") for m in audience if m.get("id")])
    ids = [m.get("id") for m in audience if m.get("id")]
    if ids:
        marks = ",".join("?" for _ in ids)
        db.execute("UPDATE members SET last_contacted=? WHERE id IN (%s)" % marks,
                   tuple([sent_at] + ids))
    db.audit("dashboard", "gap_handoff", {"campaign": code, "count": len(ids)})
    return len(ids)


async def api_export(request):
    """Download one campaign's segment as a send list (first_name, phone, tier, campaign, language)
    — deduped, opt-out + fatigue + kill-on-book filtered — and log the handoff for the fatigue cap."""
    g = _guard(request)
    if g:
        return g
    code = (request.query.get("campaign") or "").strip()
    lang = "en" if (request.query.get("lang") == "en") else "ar"
    if code not in playbook.CAMPAIGNS:
        return HOST.json_response({"ok": False, "error": "unknown_campaign"}, 400)

    def work():
        guests = cards.load_guests()
        aud = cards.segment_audience(code, guests)
        fn, text = cards.build_send_list_csv(code, guests, lang)
        _log_handoff(code, aud)
        return fn, text

    filename, text = await _in_thread(work)
    return HOST.web.Response(text=text, content_type="text/csv", charset="utf-8",
                            headers={"Content-Disposition": 'attachment; filename="%s"' % filename})


async def api_templates_export(request):
    """Download ALL 20 campaigns × both languages (40 rows) as the Meta/Karzoun one-time
    template-submission CSV. Static catalogue — variables left as {{1}}."""
    g = _guard(request)
    if g:
        return g
    filename, text = playbook.build_templates_csv()
    return HOST.web.Response(text=text, content_type="text/csv", charset="utf-8",
                            headers={"Content-Disposition": 'attachment; filename="%s"' % filename})


async def api_retier(request):
    """Rebuild the member base from realized Hostaway stays. Runs in a thread."""
    g = _guard(request)
    if g:
        return g
    lookback = settings.get_int("retier_lookback_days")
    res = await _in_thread(retier.recompute_tiers, lookback)
    return HOST.json_response({"ok": True, "result": res})


def register(app):
    app.router.add_get("/api/brain/gaps", _safe(api_gaps))
    app.router.add_get("/api/brain/gaps/conversion", _safe(api_conversion))
    app.router.add_get("/api/brain/gaps/calendar", _safe(api_calendar))
    app.router.add_get("/api/brain/gaps/assumptions", _safe(api_assumptions))
    app.router.add_post("/api/brain/gaps/assumptions", _safe(api_assumptions))
    app.router.add_post("/api/brain/gaps/holidays", _safe(api_holidays))
    app.router.add_get("/api/brain/gaps/export", api_export)
    app.router.add_get("/api/brain/gaps/templates-export", api_templates_export)
    app.router.add_post("/api/brain/gaps/retier", _safe(api_retier))