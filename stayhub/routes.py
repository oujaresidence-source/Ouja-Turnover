# -*- coding: utf-8 -*-
"""
stayhub.routes — aiohttp handlers.

PUBLIC (StayHub calls these; outside /api/ so the login middleware never touches them; every
request must carry a valid HMAC-SHA256 signature or it is refused with 401):
  POST /stayhub/webhook      outbound events (availability.changed, property.*, message.new …)
                             → verify, ack 200 at once, then pull /sync in the background
  POST /stayhub/sync-probe   "what do you hold for property X?" → answered from the local cache
                             within 10 s (probe.answer). Required for certification.

LOGGED-IN dashboard API (admin for anything that changes state):
  GET  /api/stayhub/status    credentials set? dry-run? last sync, counts, catalog + unit map,
                              name-match suggestions for unmapped units, recent events
  GET  /api/stayhub/bookings  ledger rows (no guest names — the ledger never stores them)
  POST /api/stayhub/map       {listing_id, property_id, rate_plan_id?} | {listing_id, remove:true}
  POST /api/stayhub/retry     {ha_reservation_id} — push this one reservation now
  POST /api/stayhub/sync-now  pull /sync now
"""
import datetime
import json
import re
import time
import traceback

from . import config, db, engine, probe, push, sync
from .host import HOST

_MAX_BODY = 256 * 1024


def _json(data, status=200):
    return HOST.json_response(data, status)


async def _run(fn, *a):
    runner = getattr(HOST, "run", None)
    if runner:
        return await runner(fn, *a)
    return fn(*a)


def _bg(fn):
    b = getattr(HOST, "background", None)
    if b:
        try:
            b(fn)
            return True
        except Exception as e:
            print("[stayhub] background schedule failed:", e)
    return False


def _now():
    fn = getattr(HOST, "now", None)
    d = fn() if fn else datetime.datetime.utcnow()
    return d.replace(tzinfo=None) if getattr(d, "tzinfo", None) else d


async def _raw(request):
    raw = await request.content.read(_MAX_BODY + 1)
    return raw if len(raw) <= _MAX_BODY else None


def _verified(raw, sig, ts):
    return engine.verify_signature(config.webhook_secrets(), raw, sig, ts, now_ts=time.time(),
                                   max_age_s=config.signature_max_age_s())


# ---------------- public: StayHub → us ----------------

async def webhook(request):
    raw = await _raw(request)
    if raw is None:
        return _json({"ok": False, "error": "too_large"}, 413)
    sig = request.headers.get("X-StayHub-Signature")
    ts = request.headers.get("X-StayHub-Timestamp")
    if not _verified(raw, sig, ts):
        print("[stayhub] webhook refused: bad or missing signature (delivery=%s)"
              % request.headers.get("X-StayHub-Delivery"))
        return _json({"ok": False, "error": "invalid_signature"}, 401)
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        body = {}
    event = str(request.headers.get("X-StayHub-Event") or body.get("event") or "").strip()
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    try:
        await _run(db.add_event, "", "webhook", "%s property=%s delivery=%s" % (
            event, payload.get("propertyId") or "", request.headers.get("X-StayHub-Delivery") or body.get("eventId") or ""))
    except Exception:
        traceback.print_exc()
    if event != "message.new":
        _bg(sync.run_sync)                 # the webhook is a hint; /sync is the truth
    return _json({"ok": True})


async def sync_probe(request):
    raw = await _raw(request)
    if raw is None:
        return _json({"ok": False, "error": "too_large"}, 413)
    sig = request.headers.get("X-StayHub-Probe-Signature") or request.headers.get("X-StayHub-Signature")
    ts = request.headers.get("X-StayHub-Probe-Timestamp") or request.headers.get("X-StayHub-Timestamp")
    if not _verified(raw, sig, ts):
        print("[stayhub] sync probe refused: bad or missing signature")
        return _json({"ok": False, "error": "invalid_signature"}, 401)
    try:
        req = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return _json({"ok": False, "error": "bad_json"}, 400)
    now = _now()
    try:
        ans = await _run(probe.answer, req, db.now_iso(), now.date())
    except Exception:
        traceback.print_exc()
        return _json({"ok": False, "error": "internal"}, 500)
    try:
        await _run(db.add_event, "", "sync_probe", "probe=%s property=%s scope=%s" % (
            req.get("probeId"), req.get("propertyId"), req.get("scope")))
    except Exception:
        pass
    return _json(ans)


# ---------------- logged-in dashboard API ----------------

def _authed(request):
    return bool(HOST.dash_auth and HOST.dash_auth(request))


def _is_admin(request):
    try:
        return HOST.req_role(request) in ("admin", "owner")
    except Exception:
        return False


def _safe(admin=False):
    def deco(fn):
        async def _w(request):
            if not _authed(request):
                return _json({"ok": False, "error": "unauthorized"}, 401)
            if admin and not _is_admin(request):
                return _json({"ok": False, "error": "admin_only", "message": "هذي للإدارة فقط"}, 403)
            try:
                return await fn(request)
            except Exception:
                traceback.print_exc()
                return _json({"ok": False, "error": "صار خطأ مؤقت"}, 200)
        _w.__name__ = getattr(fn, "__name__", "w")
        return _w
    return deco


async def _body(request):
    raw = await request.content.read(8193)
    if len(raw) > 8192:
        return {}
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}


def _norm_name(s):
    s = str(s or "").lower()
    s = re.sub(r"^ouja\s*\|\s*", "", s)
    return re.sub(r"[\s\-_|·]+", "", s)


def status_payload():
    props = db.properties()
    maps = {m["property_id"]: m for m in db.maps()}
    try:
        listings = HOST.listings() if getattr(HOST, "listings", None) else {}
    except Exception:
        listings = {}
    mapped_lids = {m["listing_id"] for m in maps.values()}
    by_name = {}
    for lid, name in (listings or {}).items():
        try:
            lid = int(lid)
        except (TypeError, ValueError):
            continue
        if lid not in mapped_lids:
            by_name.setdefault(_norm_name(name), []).append({"listing_id": lid, "name": name})
    catalog = []
    for p in props:
        m = maps.get(p["property_id"])
        item = {"property_id": p["property_id"], "title": p.get("title"), "version": p.get("version"),
                "status": p.get("status"), "rate_plans": json.loads(p.get("rate_plans") or "[]"),
                "listing_id": m["listing_id"] if m else None,
                "listing_name": (listings or {}).get(m["listing_id"]) if m else None,
                "rate_plan_id": m.get("rate_plan_id") if m else None}
        if not m:
            item["suggest"] = by_name.get(_norm_name(p.get("title")), [])[:3]
        catalog.append(item)
    return {
        "ok": True,
        "configured": config.configured(),
        "dryrun": config.dryrun(),
        "base_url": config.host_base(),
        "channels": sorted(config.push_channels()),
        "last_sync_at": db.setting_get("last_sync_at"),
        "last_sync_error": db.setting_get("last_sync_error") or "",
        "cursor_set": bool(db.setting_get("cursor")),
        "recon_date": db.setting_get("recon_date"),
        "counts": db.counts(),
        "catalog": catalog,
        "mapped": len(maps),
        "webhook_secret_set": bool(config.webhook_secrets()),
        "events": db.events(limit=40),
    }


@_safe()
async def status(request):
    return _json(await _run(status_payload))


@_safe()
async def bookings(request):
    st = str(request.query.get("status") or "").strip() or None
    rows = await _run(db.bookings, st, 300)
    for r in rows:
        r["status_ar"] = engine.STATUS_AR.get(r.get("status"), r.get("status"))
    return _json({"ok": True, "bookings": rows})


@_safe(admin=True)
async def set_map(request):
    b = await _body(request)
    try:
        lid = int(b.get("listing_id"))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "listing_id مطلوب"}, 400)
    actor = HOST.req_actor(request) if getattr(HOST, "req_actor", None) else "—"
    if b.get("remove"):
        await _run(db.unmap, lid)
        await _run(db.add_event, "", "unmapped", "listing=%s by=%s" % (lid, actor))
        return _json({"ok": True})
    pid = str(b.get("property_id") or "").strip()
    if not pid:
        return _json({"ok": False, "error": "property_id مطلوب"}, 400)
    prop = await _run(db.property_row, pid)
    if not prop:
        return _json({"ok": False, "error": "الوحدة مو موجودة في ستاي هب — اسحب المزامنة أول"}, 400)
    if prop.get("status") == "deauthorized":
        return _json({"ok": False, "error": "المالك سحب صلاحية عوجا على هذي الوحدة"}, 400)
    rp = str(b.get("rate_plan_id") or "").strip() or None
    plans = json.loads(prop.get("rate_plans") or "[]")
    if rp and plans and rp not in plans:
        return _json({"ok": False, "error": "خطة الأسعار مو تابعة لهذي الوحدة"}, 400)
    await _run(db.set_map, lid, pid, rp or (plans[0] if plans else None), actor)
    await _run(db.add_event, "", "mapped", "listing=%s property=%s by=%s" % (lid, pid, actor))
    return _json({"ok": True})


@_safe(admin=True)
async def retry(request):
    b = await _body(request)
    rid = str(b.get("ha_reservation_id") or "").strip()
    if not rid:
        return _json({"ok": False, "error": "ha_reservation_id مطلوب"}, 400)
    action, res = await _run(push.retry_now, rid)
    row = res if isinstance(res, dict) else await _run(db.booking, rid)
    return _json({"ok": True, "action": action, "result": res if isinstance(res, str) else None, "booking": row})


@_safe(admin=True)
async def sync_now(request):
    out = await _run(sync.run_sync)
    return _json({"ok": True, "result": out})


def register_routes(app):
    r = app.router
    r.add_post("/stayhub/webhook", webhook)
    r.add_post("/stayhub/sync-probe", sync_probe)
    r.add_get("/api/stayhub/status", status)
    r.add_get("/api/stayhub/bookings", bookings)
    r.add_post("/api/stayhub/map", set_map)
    r.add_post("/api/stayhub/retry", retry)
    r.add_post("/api/stayhub/sync-now", sync_now)
