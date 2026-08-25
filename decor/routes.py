# -*- coding: utf-8 -*-
"""
decor.routes — aiohttp handlers.

PUBLIC (a guest opens the guide with nothing, exactly like /guide itself):
  POST /api/decor/inquire        → writes ONE decor_leads row and returns. Nothing else.

SUPERVISOR (dashboard login AND role in admin/ops — double-gated like schedule writes):
  GET  /api/decor/board          → leads + orders + cakes + counts (the whole tab in one call)
  POST /api/decor/lead/dismiss   → «تجاهل»
  POST /api/decor/lead/open      → THE GATE. The only path to an order.
  POST /api/decor/order/inputs   → guest details as they arrive
  POST /api/decor/order/update   → price, deadline, assignee, notes
  POST /api/decor/order/dispatch → refused while anything required is empty
  POST /api/decor/order/done | /cancel
  POST /api/decor/cake           → the cake's own state
  GET|POST /api/decor/features   → the pool/jacuzzi/bathtub sheet
  POST /api/decor/features/import→ paste the owner's filled CSV

WHY THE PUBLIC ENDPOINT TOUCHES NO NETWORK: it is unauthenticated by necessity, so it does
zero Hostaway calls and zero Discord posts. Guest context (which reservation, which guest) is
resolved later, on the authenticated board. A flood of taps costs one INSERT each, nothing more.
"""

import csv
import datetime
import io
import json
import re
import time
import traceback

from . import db, engine, notify, packs
from .host import HOST

EDIT_ROLES = ("admin", "ops")
_SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,63}$")
_MAX_BODY = 8192
_DEDUPE_MIN = 30          # a second tap within half an hour is the same interest
_RATE_MAX = 12            # per slug per hour — a bored guest cannot fill the table
_RATE_WINDOW = 3600
_rate = {}


def _can_edit(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in EDIT_ROLES
    except Exception:
        return False


def _actor(request):
    try:
        return (HOST.actor(request) if HOST.actor else "") or ""
    except Exception:
        return ""


def _deny():
    return HOST.json_response({"ok": False, "error": "غير مصرّح لك بإدارة طلبات التنسيق"}, 403)


def _safe_public(fn):
    async def _w(request):
        try:
            return await fn(request)
        except Exception:
            traceback.print_exc()
            return HOST.json_response({"ok": True}, 200)      # never leak, never 500 a guest
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _safe(fn):
    async def _w(request):
        if not (HOST.dash_auth and HOST.dash_auth(request)):
            return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
        try:
            return await fn(request)
        except Exception:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "صار خطأ مؤقت"}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    raw = await request.content.read(_MAX_BODY + 1)
    if len(raw) > _MAX_BODY:
        return {}
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}


def _rate_ok(slug):
    now = time.time()
    hits = [t for t in _rate.get(slug, []) if now - t < _RATE_WINDOW]
    if len(hits) >= _RATE_MAX:
        _rate[slug] = hits
        return False
    hits.append(now)
    _rate[slug] = hits
    return True


# ---------------- PUBLIC: the guest tapped «أنا مهتم» ----------------

@_safe_public
async def inquire(request):
    """Records an interest. Creates no order, no thread, no task, no assignment, and notifies
    nobody but DEC. There is deliberately no code path from here to db.open_order."""
    body = await _body(request)
    slug = str(body.get("slug") or "").strip().lower()
    pack_id = str(body.get("pack_id") or "").strip()
    lang = "en" if str(body.get("lang") or "").lower().startswith("en") else "ar"
    if not _SLUG_RX.match(slug):
        return HOST.json_response({"ok": True})
    pack = packs.get(pack_id)
    if not pack:
        return HOST.json_response({"ok": True})
    if not _rate_ok(slug):
        return HOST.json_response({"ok": True})
    since = (datetime.datetime.utcnow()
             - datetime.timedelta(minutes=_DEDUPE_MIN)).isoformat(timespec="seconds")
    if db.recent_lead(slug, pack_id, since):
        return HOST.json_response({"ok": True, "dedupe": True})
    lead = db.create_lead(slug, pack_id, lang=lang, source="guide")
    try:
        cap = engine.capability_check(pack, db.unit_features(slug))
        notify.fire("lead", {"text": notify.lead_line(lead, pack, cap), "lead_id": lead["id"]})
    except Exception as e:
        print("[decor] lead notify skipped (non-fatal):", e)
    return HOST.json_response({"ok": True})


# ---------------- context enrichment (authenticated side only) ----------------

_ctx_cache = {"at": 0, "units": {}, "inhouse": []}


def _units_map():
    """slug -> {listing_id, name}. Cached for a few minutes; failures are non-fatal.

    The APARTMENT NAME comes from the Hostaway API (the live source of truth the owner
    edits), matched to the guide's slug by listing_id. The slug still has to come from the
    guide, because the slug is the only thing the guest's button can send — but the name the
    supervisor reads is always the current Hostaway one, never a stale stored copy."""
    now = time.time()
    if now - _ctx_cache["at"] < 300 and _ctx_cache["units"]:
        return _ctx_cache["units"], _ctx_cache["inhouse"]
    units, rows = {}, []
    live = {}
    try:
        live = (HOST.listings() if HOST.listings else {}) or {}
    except Exception as e:
        print("[decor] hostaway listings unavailable (non-fatal):", e)
    try:
        for u in (HOST.guide_units() if HOST.guide_units else []) or []:
            slug = str(u.get("slug") or "").lower()
            if slug:
                lid = u.get("listing_id")
                units[slug] = {"listing_id": lid,
                               "name": live.get(lid) or u.get("listing_name") or slug,
                               "from_hostaway": bool(live.get(lid))}
    except Exception as e:
        print("[decor] guide units unavailable (non-fatal):", e)
    try:
        today = (HOST.now().date() if HOST.now else datetime.date.today())
        rows = (HOST.inhouse(today) if HOST.inhouse else []) or []
    except Exception as e:
        print("[decor] in-house lookup unavailable (non-fatal):", e)
    _ctx_cache.update({"at": now, "units": units, "inhouse": rows})
    return units, rows


def _context_for(slug):
    """Which apartment, which reservation, which guest — resolved with the TARGETED in-house
    query (never the truncated reservation cache; see CLAUDE.md trap 4)."""
    units, rows = _units_map()
    u = units.get(str(slug or "").lower()) or {}
    out = {"apartment": u.get("name"), "listing_id": u.get("listing_id"),
           "reservation_id": None, "guest_name": None, "checkin_date": None,
           "checkout_date": None}
    lid = u.get("listing_id")
    if lid:
        for r in rows:
            if str(r.get("listingMapId")) == str(lid):
                out.update({"reservation_id": str(r.get("id") or ""),
                            "guest_name": r.get("guestName"),
                            "checkin_date": r.get("arrivalDate"),
                            "checkout_date": r.get("departureDate")})
                break
    return out


def _pack_or_none(pid):
    try:
        return packs.get(pid)
    except Exception:
        return None


def _lead_view(lead):
    pack = _pack_or_none(lead.get("pack_id")) or {}
    ctx = _context_for(lead.get("slug")) if lead.get("status") == "new" else {}
    cap = engine.capability_check(pack, db.unit_features(lead.get("slug"))) if pack else {}
    out = dict(lead)
    out.update({k: v for k, v in (ctx or {}).items() if v and not out.get(k)})
    out["pack_name_ar"] = pack.get("name_ar")
    out["price_from_sar"] = pack.get("price_from_sar")
    out["capability"] = cap
    if cap.get("verdict") in ("missing", "unknown"):
        out["capability_stamp_preview"] = engine.capability_stamp(
            pack, cap.get("missing") or [], "", "", cap.get("verdict"))
    return out


def _order_view(o):
    pack = _pack_or_none(o.get("pack_id")) or {}
    out = dict(o)
    out["pack_name_ar"] = pack.get("name_ar")
    out["missing_inputs"] = engine.missing_inputs(pack, o.get("inputs") or {},
                                                  o.get("na_input_keys") or [])
    out["dispatch"] = engine.dispatch_check(pack, o)
    out["money"] = engine.order_money(pack, o)
    out["ask_text"] = engine.ask_guest_message(pack, out["missing_inputs"])
    out["cake"] = db.cake_for_order(o["id"])
    out["vendor_text"] = notify.vendor_message(o, pack)
    return out


# ---------------- SUPERVISOR ----------------

@_safe
async def board(request):
    if not _can_edit(request):
        return _deny()
    leads = [_lead_view(l) for l in db.leads(status="new", limit=100)]
    recent = [_lead_view(l) for l in db.leads(limit=60) if l.get("status") != "new"]
    orders = [_order_view(o) for o in db.orders(limit=200)]
    return HOST.json_response({
        "ok": True, "leads": leads, "recent_leads": recent, "orders": orders,
        "counts": db.counts(), "packs": [
            {"id": p.get("id"), "name_ar": p.get("name_ar"), "name_en": p.get("name_en"),
             "price_from_sar": p.get("price_from_sar"), "includes_cake": p.get("includes_cake"),
             "requires_unit_features": p.get("requires_unit_features") or [],
             "setup_minutes": p.get("setup_minutes")} for p in packs.all_packs()],
        "features": db.all_unit_features(), "packs_file": packs.status(),
        "dryrun": notify.dryrun(), "supervisor_role": notify.supervisor_role(),
    })


@_safe
async def lead_dismiss(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    lead = db.dismiss_lead(str(b.get("lead_id") or ""), _actor(request), str(b.get("reason") or ""))
    return HOST.json_response({"ok": bool(lead), "lead": lead})


def _deadline_for(lead_ctx, event_at):
    """Event time wins; otherwise the decoration must be finished by check-in (3 PM default)."""
    if event_at:
        try:
            return datetime.datetime.fromisoformat(str(event_at).replace("Z", ""))
        except ValueError:
            return None
    ci = lead_ctx.get("checkin_date")
    if not ci:
        return None
    try:
        return engine.default_deadline(datetime.date.fromisoformat(str(ci)[:10]))
    except ValueError:
        return None


def _sync_cake(order, pack):
    """Create or re-time the cake job. Bronze never gets one — engine.cake_task_for returns
    None and this function does nothing."""
    if not order.get("deadline_at"):
        return None
    try:
        deadline = datetime.datetime.fromisoformat(order["deadline_at"])
    except (ValueError, TypeError):
        return None
    task = engine.cake_task_for(pack, deadline, packs.cake_lead_hours())
    existing = db.cake_for_order(order["id"])
    if not task:
        return None
    due = task["due_at"].isoformat(timespec="minutes")
    if existing:
        if existing.get("due_at") != due and existing.get("state") in ("pending",):
            return db.update_cake(existing["id"], due_at=due)
        return existing
    vals = order.get("inputs") or {}
    return db.create_cake_task(order["id"], due, vals.get("cake_flavor"), vals.get("cake_writing"))


@_safe
async def lead_open(request):
    """THE GATE. Refuses on a capability problem unless the supervisor explicitly overrides,
    and an accept_gap override stamps the order permanently."""
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    lead = db.lead(str(b.get("lead_id") or ""))
    if not lead or lead.get("status") != "new":
        return HOST.json_response({"ok": False, "error": "الاهتمام مو موجود أو انفتح/انتجاهل من قبل"})
    pack = _pack_or_none(lead.get("pack_id"))
    if not pack:
        return HOST.json_response({"ok": False, "error": "الباقة مو موجودة في الملف"})
    actor = _actor(request)
    chk = engine.open_check(pack, db.unit_features(lead["slug"]),
                            override_kind=(b.get("override_kind") or None),
                            overridden_by=actor, reason=str(b.get("reason") or ""))
    if not chk["allowed"]:
        cap = engine.capability_check(pack, db.unit_features(lead["slug"]))
        return HOST.json_response({
            "ok": False, "error": chk["error"], "capability": cap,
            "message": engine.capability_stamp(pack, cap.get("missing") or [], "", "",
                                               cap.get("verdict")),
            "affected_items": engine.affected_checklist_items(pack, cap.get("missing") or []),
            "can_override": ["correction", "accept_gap"]})

    ctx = _context_for(lead["slug"])
    for k in ("apartment", "listing_id", "reservation_id", "guest_name", "checkin_date"):
        if lead.get(k) and not ctx.get(k):
            ctx[k] = lead[k]
    if chk["learn_features"]:
        db.add_unit_features(lead["slug"], chk["learn_features"], by=actor)

    deadline = _deadline_for(ctx, b.get("event_at"))
    dl = engine.deadlines(pack, deadline, packs.cake_lead_hours()) if deadline else {}
    order = db.open_order(
        lead["id"], lead["slug"], lead["pack_id"], actor,
        apartment=ctx.get("apartment"), listing_id=ctx.get("listing_id"),
        reservation_id=ctx.get("reservation_id"), guest_name=ctx.get("guest_name"),
        checkin_date=ctx.get("checkin_date"),
        deadline_at=deadline.isoformat(timespec="minutes") if deadline else None,
        event_at=str(b.get("event_at") or "") or None,
        work_start_at=dl["work_start"].isoformat(timespec="minutes") if dl else None,
        na_input_keys=chk["na_input_keys"], capability_verdict=chk["verdict"],
        capability_stamp=chk["stamp"], override_kind=(b.get("override_kind") or None),
        overridden_by=actor if b.get("override_kind") else None,
        overridden_at=db.now_iso() if b.get("override_kind") else None,
        override_reason=str(b.get("reason") or "") or None,
        assignee=str(b.get("assignee") or "") or None,
        final_price_sar=b.get("final_price_sar"))
    _sync_cake(order, pack)
    order = db.order(order["id"])
    notify.fire("open", {"text": notify.thread_header(order, pack),
                         "thread_name": notify.thread_name(order, pack),
                         "order_id": order["id"]})
    return HOST.json_response({"ok": True, "order": _order_view(order)})


@_safe
async def order_inputs(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    o = db.set_inputs(str(b.get("order_id") or ""), b.get("inputs") or {})
    if not o:
        return HOST.json_response({"ok": False, "error": "الطلب مو موجود"})
    pack = _pack_or_none(o["pack_id"]) or {}
    cake = db.cake_for_order(o["id"])
    if cake and cake.get("state") == "pending":
        vals = o.get("inputs") or {}
        db.update_cake(cake["id"], flavor=vals.get("cake_flavor"), writing=vals.get("cake_writing"))
    chk = engine.dispatch_check(pack, o)
    if chk["ok"] and o.get("state") == "awaiting_guest":
        o = db.update_order(o["id"], state="ready")
    elif not chk["ok"] and o.get("state") == "ready":
        o = db.update_order(o["id"], state="awaiting_guest")
    return HOST.json_response({"ok": True, "order": _order_view(db.order(o["id"]))})


@_safe
async def order_update(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    o = db.order(str(b.get("order_id") or ""))
    if not o:
        return HOST.json_response({"ok": False, "error": "الطلب مو موجود"})
    pack = _pack_or_none(o["pack_id"]) or {}
    fields = {}
    for k in ("final_price_sar", "vendor_cost_sar", "assignee", "vendor", "notes"):
        if k in b:
            fields[k] = b[k]
    if b.get("event_at") is not None:
        deadline = _deadline_for(o, b.get("event_at")) or _deadline_for(
            {"checkin_date": o.get("checkin_date")}, None)
        if deadline:
            dl = engine.deadlines(pack, deadline, packs.cake_lead_hours())
            fields["deadline_at"] = deadline.isoformat(timespec="minutes")
            fields["work_start_at"] = dl["work_start"].isoformat(timespec="minutes")
        fields["event_at"] = str(b.get("event_at") or "") or None
    o = db.update_order(o["id"], **fields)
    _sync_cake(o, pack)
    chk = engine.dispatch_check(pack, o)
    if chk["ok"] and o.get("state") == "awaiting_guest":
        o = db.update_order(o["id"], state="ready")
    return HOST.json_response({"ok": True, "order": _order_view(db.order(o["id"]))})


@_safe
async def order_dispatch(request):
    """A partial order never reaches a vendor — they cannot work without the phrases."""
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    o = db.order(str(b.get("order_id") or ""))
    if not o:
        return HOST.json_response({"ok": False, "error": "الطلب مو موجود"})
    if o.get("state") in ("dispatched", "done", "cancelled"):
        return HOST.json_response({"ok": False, "error": "الطلب حالته %s" % o["state"],
                                   "order": _order_view(o)})
    pack = _pack_or_none(o["pack_id"]) or {}
    chk = engine.dispatch_check(pack, o)
    if not chk["ok"]:
        return HOST.json_response({
            "ok": False, "error": "incomplete", "missing_inputs": chk["missing_inputs"],
            "needs_price": chk["needs_price"],
            "ask_text": engine.ask_guest_message(pack, chk["missing_inputs"]),
            "order": _order_view(o)})
    o = db.update_order(o["id"], state="dispatched", dispatched_by=_actor(request),
                        dispatched_at=db.now_iso(),
                        assignee=str(b.get("assignee") or o.get("assignee") or "") or None)
    notify.fire("dispatch", {"text": notify.vendor_message(o, pack), "order_id": o["id"]})
    return HOST.json_response({"ok": True, "order": _order_view(o),
                               "vendor_text": notify.vendor_message(o, pack)})


@_safe
async def order_done(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    o = db.order(str(b.get("order_id") or ""))
    if not o:
        return HOST.json_response({"ok": False, "error": "الطلب مو موجود"})
    o = db.update_order(o["id"], state="done", done_by=_actor(request), done_at=db.now_iso())
    return HOST.json_response({"ok": True, "order": _order_view(o)})


@_safe
async def order_cancel(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    o = db.order(str(b.get("order_id") or ""))
    if not o:
        return HOST.json_response({"ok": False, "error": "الطلب مو موجود"})
    o = db.update_order(o["id"], state="cancelled", cancel_reason=str(b.get("reason") or ""))
    cake = db.cake_for_order(o["id"])
    if cake and cake.get("state") == "pending":
        db.update_cake(cake["id"], state="cancelled")
    return HOST.json_response({"ok": True, "order": _order_view(o)})


@_safe
async def cake_update(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    cake = db.cake_task(str(b.get("cake_id") or ""))
    if not cake:
        return HOST.json_response({"ok": False, "error": "مهمة الكيك مو موجودة"})
    state = str(b.get("state") or "")
    fields = {}
    if state in ("pending", "ordered", "delivered", "cancelled"):
        fields["state"] = state
        if state == "ordered":
            fields["ordered_by"] = _actor(request)
            fields["ordered_at"] = db.now_iso()
        if state == "delivered":
            fields["delivered_at"] = db.now_iso()
    for k in ("flavor", "writing", "supplier"):
        if k in b:
            fields[k] = b[k]
    if state == "ordered":
        o = db.order(cake["order_id"])
        pack = _pack_or_none((o or {}).get("pack_id")) or {}
        ready = engine.cake_ready(pack, o or {})
        if ready["applies"] and not ready["ok"]:
            return HOST.json_response({"ok": False, "error": "cake_incomplete",
                                       "missing": ready["missing"]})
    return HOST.json_response({"ok": True, "cake": db.update_cake(cake["id"], **fields)})


# ---------------- the unit-features sheet ----------------

def _feature_rows():
    """Every apartment a guest could tap a package on, named from Hostaway."""
    units, _ = _units_map()
    have = db.all_unit_features()
    rows = [{"slug": s, "apartment": (u or {}).get("name") or s,
             "listing_id": (u or {}).get("listing_id"),
             "from_hostaway": (u or {}).get("from_hostaway", False),
             "features": have.get(s), "known": s in have}
            for s, u in sorted(units.items())]
    for s, f in sorted(have.items()):
        if s not in units:
            rows.append({"slug": s, "apartment": s, "listing_id": None,
                         "from_hostaway": False, "features": f, "known": True})
    return rows


def _unlinked_listings():
    """Hostaway units with no guide page. A guest can never tap a package on these — there is
    no page to tap it on — so they are reported, not silently dropped."""
    try:
        live = (HOST.listings() if HOST.listings else {}) or {}
    except Exception:
        return []
    linked = {u.get("listing_id") for u in _units_map()[0].values() if u.get("listing_id")}
    return [{"listing_id": lid, "name": nm} for lid, nm in sorted(live.items(), key=lambda x: str(x[1]))
            if lid not in linked]


@_safe
async def features_get(request):
    if not _can_edit(request):
        return _deny()
    rows = _feature_rows()
    unlinked = _unlinked_listings()
    return HOST.json_response({"ok": True, "rows": rows, "unlinked": unlinked,
                               "hostaway_ok": any(r.get("from_hostaway") for r in rows),
                               "vocabulary": sorted(engine.FEATURE_AR.items())})


@_safe
async def features_export(request):
    """The fill-in sheet, generated from LIVE Hostaway names — not a stale export. Opens
    straight in Excel/Numbers (utf-8-sig), and imports back through features_import."""
    if not _can_edit(request):
        return _deny()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["رمز الشقة (لا تغيّره)", "اسم الشقة", "مسبح؟", "جاكوزي؟", "بانيو؟", "ملاحظة"])
    yes = "نعم"
    for r in _feature_rows():
        have = r.get("features") or []
        known = r.get("known")
        note = "" if known else "ما عبّيناها بعد"
        nm = str(r.get("apartment") or "")
        if "pool" not in have and ("pool" in nm.lower() or "مسبح" in nm):
            note = (note + " · " if note else "") + "الاسم يذكر مسبح — تأكد"
        w.writerow([r["slug"], nm,
                    yes if "pool" in have else "", yes if "jacuzzi" in have else "",
                    yes if "bathtub" in have else "", note])
    body = ("﻿" + buf.getvalue()).encode("utf-8")
    return HOST.web.Response(
        body=body, content_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ouja_decor_apartments.csv"'})


@_safe
async def features_set(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    slug = str(b.get("slug") or "").lower()
    if not _SLUG_RX.match(slug):
        return HOST.json_response({"ok": False, "error": "رمز شقة غير صالح"})
    feats = [f for f in (b.get("features") or []) if f in engine.FEATURE_AR]
    db.set_unit_features(slug, feats, apartment=b.get("apartment"), by=_actor(request))
    return HOST.json_response({"ok": True, "features": db.unit_features(slug)})


@_safe
async def features_import(request):
    """Paste the filled sheet back in. Accepts the exact CSV that was sent out:
    رمز الشقة | اسم الشقة | مسبح؟ | جاكوزي؟ | بانيو؟ | ملاحظة — anything non-empty that
    isn't «لا»/no/0 counts as yes."""
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    text = str(b.get("csv") or "")
    if not text.strip():
        return HOST.json_response({"ok": False, "error": "ما وصل شي"})
    order = ("pool", "jacuzzi", "bathtub")
    no = {"", "لا", "no", "n", "0", "false", "-"}
    done, skipped = 0, 0
    for row in csv.reader(io.StringIO(text.lstrip("﻿"))):
        if not row:
            continue
        slug = str(row[0] or "").strip().lower()
        if not _SLUG_RX.match(slug):
            skipped += 1
            continue
        feats = []
        for i, feat in enumerate(order, start=2):
            val = str(row[i]).strip().lower() if len(row) > i else ""
            if val not in no:
                feats.append(feat)
        db.set_unit_features(slug, feats,
                             apartment=(str(row[1]).strip() if len(row) > 1 else None),
                             by=_actor(request))
        done += 1
    return HOST.json_response({"ok": True, "saved": done, "skipped": skipped})


def register_routes(app):
    app.router.add_post("/api/decor/inquire", inquire)
    app.router.add_get("/api/decor/board", board)
    app.router.add_post("/api/decor/lead/dismiss", lead_dismiss)
    app.router.add_post("/api/decor/lead/open", lead_open)
    app.router.add_post("/api/decor/order/inputs", order_inputs)
    app.router.add_post("/api/decor/order/update", order_update)
    app.router.add_post("/api/decor/order/dispatch", order_dispatch)
    app.router.add_post("/api/decor/order/done", order_done)
    app.router.add_post("/api/decor/order/cancel", order_cancel)
    app.router.add_post("/api/decor/cake", cake_update)
    app.router.add_get("/api/decor/features", features_get)
    app.router.add_get("/api/decor/features/export", features_export)
    app.router.add_post("/api/decor/features", features_set)
    app.router.add_post("/api/decor/features/import", features_import)
