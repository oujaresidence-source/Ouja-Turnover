"""
brain.gap_routes — aiohttp handlers for the Weekday-Gap Engine screen (/api/brain/gaps*).

READ-ONLY against the business: the list endpoint computes live gaps + cards and overlays each
agent's claim/snooze/sent state from gap_actions; nothing here messages a guest. The heavier work
(building cards = a live calendar pull; re-tiering = many reservation windows) runs in a thread
executor so it never blocks the bot's single event loop.

Kill-on-book is free: cards are recomputed from the live grid every load, so a card vanishes the
instant Hostaway shows its night booked.
"""

import asyncio
import json
import traceback
from . import db, settings, cards, retier
from .host import HOST
from .util import now_iso, today_iso, now_dt


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
    """Run a blocking host/DB call off the event loop."""
    return await asyncio.get_event_loop().run_in_executor(None, fn, *a)


def _actions_map():
    rows = db.q("SELECT * FROM gap_actions")
    return {r["card_key"]: dict(r) for r in rows}


# --------------------------- reads ---------------------------

def _build_payload(show_snoozed):
    out = cards.build_cards()
    acts = _actions_map()
    now = now_dt().isoformat(timespec="seconds")
    visible = []
    for c in out.get("cards", []):
        a = acts.get(c.get("card_key")) or {}
        c["claimed_by"] = a.get("claimed_by")
        c["claimed_at"] = a.get("claimed_at")
        c["sent_at"] = a.get("sent_at")
        c["sent_by"] = a.get("sent_by")
        c["sent_count"] = a.get("sent_count") or 0
        snz = a.get("snoozed_until")
        c["snoozed"] = bool(snz and snz > now)
        if c["snoozed"] and not show_snoozed:
            continue
        visible.append(c)
    out["cards"] = visible
    # refresh the summary to reflect what's actually shown
    out["summary"]["card_count"] = len(visible)
    out["summary"]["p1_count"] = len([c for c in visible if c.get("priority_num") == 1])
    return out


async def api_gaps(request):
    g = _guard(request)
    if g:
        return g
    show_snoozed = request.query.get("snoozed") in ("1", "true", "yes")
    payload = await _in_thread(_build_payload, show_snoozed)
    return HOST.json_response({"ok": True, **payload})


async def api_conversion(request):
    g = _guard(request)
    if g:
        return g
    # per-campaign: how many cards were sent, and any attributed bookings/revenue
    sent = {r["campaign"]: {"sent_cards": r["c"], "sent_targets": r["t"] or 0}
            for r in db.q("SELECT campaign, COUNT(*) c, SUM(sent_count) t FROM gap_actions "
                          "WHERE sent_at IS NOT NULL GROUP BY campaign")}
    for r in db.q("SELECT campaign_code, COUNT(*) c, SUM(revenue) rev FROM attributions GROUP BY campaign_code"):
        row = sent.setdefault(r["campaign_code"], {"sent_cards": 0, "sent_targets": 0})
        row["bookings"] = r["c"]
        row["revenue"] = round(r["rev"] or 0)
    return HOST.json_response({"ok": True, "conversion": sent})


# --------------------------- actions (writes) ---------------------------

def _upsert(card_key, fields, meta=None):
    """Insert-or-update a gap_actions row, setting `fields` (dict). meta carries date/lid/unit/
    campaign on first touch so the row is self-describing."""
    db.init_db()
    meta = meta or {}
    existing = db.q1("SELECT card_key FROM gap_actions WHERE card_key=?", (card_key,))
    now = now_iso()
    if not existing:
        db.execute("INSERT INTO gap_actions(card_key, date, lid, unit, campaign, updated_at) "
                   "VALUES(?,?,?,?,?,?)",
                   (card_key, meta.get("date") or today_iso(), meta.get("lid"), meta.get("unit"),
                    meta.get("campaign"), now))
    sets = ", ".join("%s=?" % k for k in fields) + ", updated_at=?"
    db.execute("UPDATE gap_actions SET %s WHERE card_key=?" % sets,
               tuple(list(fields.values()) + [now, card_key]))


async def api_claim(request):
    g = _guard(request)
    if g:
        return g
    d = await _body(request)
    key = (d.get("card_key") or "").strip()
    agent = (d.get("agent") or "agent").strip()
    if not key:
        return HOST.json_response({"ok": False, "error": "no_card_key"}, 400)
    row = db.q1("SELECT claimed_by FROM gap_actions WHERE card_key=?", (key,))
    if row and row["claimed_by"] and row["claimed_by"] != agent:
        # one agent owns a card (dedup / no double-send) — refuse a second claim
        return HOST.json_response({"ok": False, "error": "already_claimed", "by": row["claimed_by"]}, 200)
    _upsert(key, {"claimed_by": agent, "claimed_at": now_iso()},
            meta={"date": d.get("date"), "lid": d.get("lid"), "unit": d.get("unit"),
                  "campaign": d.get("campaign")})
    db.audit(agent, "gap_claim", {"card_key": key})
    return HOST.json_response({"ok": True, "claimed_by": agent})


async def api_snooze(request):
    g = _guard(request)
    if g:
        return g
    d = await _body(request)
    key = (d.get("card_key") or "").strip()
    if not key:
        return HOST.json_response({"ok": False, "error": "no_card_key"}, 400)
    from datetime import timedelta
    hours = int(d.get("hours") or 6)
    until = (now_dt() + timedelta(hours=hours)).isoformat(timespec="seconds")
    _upsert(key, {"snoozed_until": until},
            meta={"date": d.get("date"), "lid": d.get("lid"), "unit": d.get("unit"),
                  "campaign": d.get("campaign")})
    db.audit("dashboard", "gap_snooze", {"card_key": key, "until": until})
    return HOST.json_response({"ok": True, "snoozed_until": until})


async def api_sent(request):
    """Mark a card as sent (agent logs that they pushed the message). Records the send for the
    Governor + the per-campaign conversion learning. Does NOT itself message anyone."""
    g = _guard(request)
    if g:
        return g
    d = await _body(request)
    key = (d.get("card_key") or "").strip()
    agent = (d.get("agent") or "agent").strip()
    count = int(d.get("count") or 0)
    if not key:
        return HOST.json_response({"ok": False, "error": "no_card_key"}, 400)
    _upsert(key, {"sent_by": agent, "sent_at": now_iso(), "sent_count": count,
                  "claimed_by": agent, "claimed_at": now_iso()},
            meta={"date": d.get("date"), "lid": d.get("lid"), "unit": d.get("unit"),
                  "campaign": d.get("campaign")})
    db.audit(agent, "gap_sent", {"card_key": key, "count": count})
    return HOST.json_response({"ok": True})


async def api_export(request):
    """Download the current cards' targets as a today-first send-list CSV (change 3)."""
    g = _guard(request)
    if g:
        return g
    payload = await _in_thread(_build_payload, False)
    filename, text = cards.build_today_csv(payload)
    return HOST.web.Response(text=text, content_type="text/csv", charset="utf-8",
                            headers={"Content-Disposition": 'attachment; filename="%s"' % filename})


async def api_retier(request):
    """Rebuild the member base from realized Hostaway stays (build spec §1). Runs in a thread."""
    g = _guard(request)
    if g:
        return g
    lookback = settings.get_int("retier_lookback_days")
    res = await _in_thread(retier.recompute_tiers, lookback)
    return HOST.json_response({"ok": True, "result": res})


def register(app):
    app.router.add_get("/api/brain/gaps", _safe(api_gaps))
    app.router.add_get("/api/brain/gaps/conversion", _safe(api_conversion))
    app.router.add_get("/api/brain/gaps/export", api_export)
    app.router.add_post("/api/brain/gaps/claim", _safe(api_claim))
    app.router.add_post("/api/brain/gaps/snooze", _safe(api_snooze))
    app.router.add_post("/api/brain/gaps/sent", _safe(api_sent))
    app.router.add_post("/api/brain/gaps/retier", _safe(api_retier))
