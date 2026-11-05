# -*- coding: utf-8 -*-
"""
stayhub.push — Hostaway reservations → StayHub bookings (the channel-partner request path).

Per reservation (guide steps 4–6 + StayHub's written answers of 5 Nov 2026):
    create  : pre-booking probe → hold (partnerSnapshot = the probe's OWN rates/rooms/version,
              never the Airbnb price) → confirm (financial.total = what the guest paid on Airbnb,
              externalReservationId = Airbnb code, paymentReference = Hostaway id, revision 1)
    modify  : dates changed  → probe the new dates → modify with partnerSnapshot + financial
              amount changed → financial-only modify
    cancel  : Hostaway cancelled → cancel (revision + 1)
Every StayHub refusal is logged on the row + in stayhub_events and reported daily (their ask).

The poller (tick) and the Hostaway webhook (on_hook) take the SAME path. A per-reservation
lock stops the two from pushing the same reservation at the same moment; UNIQUE(ha id) on
stayhub_bookings stops a second row forever.
"""
import datetime
import json
import threading

from . import client, config, db, engine, notify
from .client import StayHubError
from .host import HOST

E = engine

_locks = {}
_locks_guard = threading.Lock()


class _Busy(Exception):
    pass


def _acquire(rid):
    with _locks_guard:
        lk = _locks.get(rid)
        if lk is None:
            lk = _locks[rid] = threading.Lock()
    if not lk.acquire(blocking=False):
        raise _Busy(rid)
    return lk


# ---------------- time ----------------

def _now(now=None):
    if now is not None:
        return now
    fn = getattr(HOST, "now", None)
    return fn() if fn else datetime.datetime.utcnow()


def _naive(dt):
    return dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) is not None else dt


def _iso(dt):
    return _naive(dt).isoformat(timespec="seconds")


def _later(now, minutes):
    return _iso(_naive(now) + datetime.timedelta(minutes=minutes))


def _log(text):
    fn = getattr(HOST, "log_event", None)
    if fn:
        try:
            fn("stayhub", text)
            return
        except Exception:
            pass
    print("[stayhub] " + text)


# ---------------- helpers ----------------

def _channel(r):
    fn = getattr(HOST, "finance_channel", None)
    if fn:
        try:
            return fn(r)
        except Exception:
            pass
    ch = str((r or {}).get("channelName") or "").lower()
    return "airbnb" if "airbnb" in ch else "other"


def _confirmed_statuses():
    fn = getattr(HOST, "confirmed_statuses", None)
    try:
        return fn() if fn else {"new", "modified"}
    except Exception:
        return {"new", "modified"}


def _guest(r):
    g = {"fullName": E.guest_name(r)}
    email = (r or {}).get("guestEmail") or (r or {}).get("email")
    if email and "@" in str(email):
        g["email"] = str(email).strip()
    phone = E.normalize_phone((r or {}).get("phone") or (r or {}).get("guestPhone"))
    if phone:
        g["phone"] = phone
    return g, bool(phone)


def _rate_plan(mapping, prop_row):
    rp = (mapping or {}).get("rate_plan_id")
    if rp:
        return rp
    try:
        plans = json.loads((prop_row or {}).get("rate_plans") or "[]")
        return plans[0] if plans else None
    except Exception:
        return None


def _num_out(v):
    f = float(v)
    return int(f) if f == int(f) else round(f, 2)


def _event(row, kind, detail="", trace=None, now=None):
    db.add_event(row["ha_reservation_id"], kind, detail, trace, _iso(_now(now)))


def _retry_minutes(attempts):
    return min(60, 2 ** max(1, int(attempts or 0)))


# ---------------- the failure playbook ----------------

def _fail(row, e, now, stage):
    """Apply engine.action_for_error to the row. Returns the new row."""
    code = getattr(e, "code", "UNKNOWN")
    action = E.action_for_error(code, getattr(e, "status", None))
    attempts = int(row.get("attempts") or 0) + 1
    base = {"attempts": attempts, "last_code": code, "last_error": (getattr(e, "message", "") or "")[:300],
            "last_trace": getattr(e, "trace_id", None), "hold_id": None, "hold_expires": None}
    _event(row, "error", "%s at %s (%s)" % (code, stage, action), getattr(e, "trace_id", None), now)
    live = row.get("status") == E.CONFIRMED
    if action == "reject":
        if live:
            # a modify StayHub refused — the booking stays, the change waits
            row = db.update_booking(row["ha_reservation_id"], next_try_at=_later(now, config.retry_rejected_hours() * 60),
                                    **{k: v for k, v in base.items() if k not in ("hold_id", "hold_expires")})
            if not row.get("notified"):
                notify.send(notify.rejected_text(row, code))
                db.update_booking(row["ha_reservation_id"], notified=1)
            return row
        status = E.FAILED if attempts >= config.max_rejected_attempts() else E.REJECTED
        row = db.update_booking(row["ha_reservation_id"], status=status,
                                next_try_at=_later(now, config.retry_rejected_hours() * 60), **base)
        if not row.get("notified"):
            notify.send(notify.rejected_text(row, code, _detail(e)))
            db.update_booking(row["ha_reservation_id"], notified=1)
        return row
    if action == "deauthorized":
        if row.get("property_id"):
            db.set_property_status(row["property_id"], "deauthorized")
        row = db.update_booking(row["ha_reservation_id"], status=row["status"] if live else E.FAILED, **base)
        notify.send(notify.failed_text(row, code))
        return row
    if action == "suspended":
        if row.get("property_id"):
            db.set_property_status(row["property_id"], "suspended")
        _kick_sync()
        return db.update_booking(row["ha_reservation_id"], status=row["status"] if live else E.RETRY,
                                 next_try_at=_later(now, 10), **base)
    if action in ("hard_fail", "conflict"):
        row = db.update_booking(row["ha_reservation_id"], status=row["status"] if live else E.FAILED,
                                next_try_at=None if not live else _later(now, 24 * 60), **base)
        if stage == "cancel":
            notify.send(notify.cancel_failed_text(row, code))
        else:
            notify.send(notify.failed_text(row, code))
        return row
    # retry / backoff / refresh_token / resync_retry / restart_hold / network
    if action == "resync_retry":
        _kick_sync()
    return db.update_booking(row["ha_reservation_id"], status=row["status"] if live else E.RETRY,
                             next_try_at=_later(now, _retry_minutes(attempts)), **base)


def _detail(e):
    d = getattr(e, "detail", None)
    if isinstance(d, dict) and d.get("date"):
        return "ليلة %s" % d.get("date")
    return ""


def _kick_sync():
    fn = getattr(HOST, "background", None)
    if fn:
        try:
            from . import sync
            fn(sync.run_sync)
        except Exception:
            pass


# ---------------- adopt (recover our own booking after a lost ledger) ----------------

def _find_existing(row):
    """StayHub may already hold this booking (ledger wiped, or a confirm whose answer we never
    got). Look it up by externalReservationId on that property. Returns the StayHub dict or None."""
    pid, ext = row.get("property_id"), row.get("external_id")
    if not pid or not ext:
        return None
    try:
        for page in range(1, 6):
            data = client.list_reservations(pid, page=page, limit=200)
            items = data if isinstance(data, list) else (data or {}).get("reservations") or (data or {}).get("items") or []
            for it in items:
                if str(it.get("externalReservationId") or "") == str(ext) and str(it.get("status") or "") != "cancelled":
                    return it
            pag = (data or {}).get("pagination") if isinstance(data, dict) else None
            if not pag or page >= int(pag.get("pages") or 1):
                break
    except StayHubError as e:
        print("[stayhub] lookup by external id failed: %s" % e.code)
    return None


def _adopt(row, found, view, now):
    row = db.update_booking(row["ha_reservation_id"], status=E.CONFIRMED,
                            sh_reservation_id=str(found.get("reservationId") or found.get("id") or ""),
                            revision=int(found.get("externalRevision") or 1),
                            pushed_check_in=found.get("checkIn") or view.get("check_in"),
                            pushed_check_out=found.get("checkOut") or view.get("check_out"),
                            pushed_total=((found.get("financial") or {}).get("total")),
                            last_code=None, last_error=None, next_try_at=None, hold_id=None)
    _event(row, "adopted", "found existing StayHub reservation %s" % row.get("sh_reservation_id"), None, now)
    return row


# ---------------- create ----------------

def _probe_snapshot(pid, rate_plan, check_in, check_out, own_nights=()):
    probe = client.availability(pid, check_in, check_out, rate_plan, pre_booking=True)
    snap, why = E.snapshot_from_probe(probe, check_in, check_out, own_nights)
    return probe, snap, why


def _create(row, view, r, now):
    pid = row["property_id"]
    prop = db.property_row(pid) or {}
    if prop.get("status") == "deauthorized":
        return _fail(row, StayHubError("FORBIDDEN_PROPERTY", 403), now, "precheck")
    if prop.get("status") == "suspended":
        return _fail(row, StayHubError("PROPERTY_SUSPENDED_STALE_SYNC", 409), now, "precheck")
    rate_plan = row.get("rate_plan_id") or _rate_plan(db.map_for_listing(row["listing_id"]), prop)
    guest, has_phone = _guest(r)
    for attempt in (1, 2):                       # one immediate re-probe for price/version races
        try:
            probe, snap, why = _probe_snapshot(pid, rate_plan, view["check_in"], view["check_out"])
        except StayHubError as e:
            return _fail(row, e, now, "probe")   # guide: probe failed ⇒ abort, never fall back to cache
        if snap is None:
            found = _find_existing(row)          # the full night may be OUR booking (ledger lost)
            if found:
                return _adopt(row, found, view, now)
            return _fail(row, StayHubError("NO_AVAILABILITY", 409, why), now, "probe")
        rate_plan = rate_plan or probe.get("ratePlanId")
        hold_body = {
            "propertyId": pid, "ratePlanId": rate_plan,
            "checkIn": view["check_in"], "checkOut": view["check_out"],
            "occupancy": {"adults": int(view.get("adults") or 1)},
            "externalHoldId": "ouja_%s_%d" % (row["ha_reservation_id"], int(row.get("attempts") or 0) * 2 + attempt),
            "partnerSnapshot": snap,
        }
        total = view.get("total")
        confirm_body = {
            "externalReservationId": row["external_id"],
            "externalRevision": int(row.get("revision") or 0) + 1,
            "guest": guest,
            "financial": {"total": _num_out(total if total is not None else snap["totalAmount"]),
                          "currency": view.get("currency") or config.default_currency()},
            "paymentReference": row["ha_reservation_id"],
        }
        if config.dryrun():
            _event(row, "dryrun", "would hold %s nights total_snapshot=%s then confirm total=%s"
                   % (len(snap["days"]), snap["totalAmount"], confirm_body["financial"]["total"]), None, now)
            return db.update_booking(row["ha_reservation_id"], status=E.PENDING, dryrun=1,
                                     next_try_at=_later(now, 60))
        try:
            held, trace = client.hold(hold_body)
        except StayHubError as e:
            if E.action_for_error(e.code) == "resync_retry" and attempt == 1:
                _event(row, "hold_retry", e.code, e.trace_id, now)
                continue
            if e.code in ("SNAPSHOT_AVAILABILITY_MISMATCH", "INVENTORY_RACE"):
                found = _find_existing(row)
                if found:
                    return _adopt(row, found, view, now)
            return _fail(row, e, now, "hold")
        row = db.update_booking(row["ha_reservation_id"], status=E.HELD, hold_id=held.get("holdId"),
                                hold_expires=str(held.get("expiresAt") or "")[:19] or None, last_trace=trace,
                                rate_plan_id=rate_plan)
        _event(row, "held", "hold=%s total=%s" % (held.get("holdId"), held.get("totalAmount")), trace, now)
        confirm_body["holdId"] = held.get("holdId")
        try:
            done, trace = client.confirm(confirm_body)
        except StayHubError as e:
            if e.code == "HOLD_EXPIRED" and attempt == 1:
                _event(row, "hold_expired", "restart from probe", e.trace_id, now)
                continue
            if e.code == "IDEMPOTENCY_CONFLICT":
                found = _find_existing(row)
                if found:
                    return _adopt(row, found, view, now)
            return _fail(row, e, now, "confirm")
        row = db.update_booking(
            row["ha_reservation_id"], status=E.CONFIRMED, sh_reservation_id=str(done.get("reservationId") or ""),
            revision=confirm_body["externalRevision"], pushed_check_in=view["check_in"],
            pushed_check_out=view["check_out"], pushed_total=confirm_body["financial"]["total"],
            hold_id=None, hold_expires=None, last_code=None, last_error=None, next_try_at=None,
            last_trace=trace, attempts=0, notified=0, dryrun=0)
        _event(row, "confirmed", "reservation=%s idempotent=%s" % (row["sh_reservation_id"], bool(done.get("idempotent"))),
               trace, now)
        _log("وصل حجز Airbnb لستاي هب · %s · %s→%s" % (notify._unit(row.get("listing_id")), view["check_in"], view["check_out"]))
        if not has_phone:
            notify.send(notify.no_phone_text(row))
        return row
    return row


# ---------------- modify / cancel ----------------

def _revision_from_stayhub(row):
    try:
        cur = client.get_reservation(row["sh_reservation_id"])
        return int(cur.get("externalRevision") or row.get("revision") or 0)
    except (StayHubError, TypeError, ValueError):
        return None


def _send_change(row, kind, body_fn, now):
    """modify/cancel with one recovery for a revision StayHub already moved past."""
    for attempt in (1, 2):
        rev = int(row.get("revision") or 0) + 1
        body = body_fn(rev)
        if config.dryrun():
            _event(row, "dryrun", "would %s rev=%s" % (kind, rev), None, now)
            return row, None
        try:
            if kind == "cancel":
                data, trace = client.cancel(row["sh_reservation_id"], body)
            else:
                data, trace = client.modify(row["sh_reservation_id"], body)
            return row, (rev, data, trace)
        except StayHubError as e:
            if e.code == "IDEMPOTENCY_CONFLICT" and attempt == 1:
                live_rev = _revision_from_stayhub(row)
                if live_rev is not None and live_rev >= rev:
                    row = db.update_booking(row["ha_reservation_id"], revision=live_rev)
                    continue
            return _fail(row, e, now, kind), None
    return row, None


def _modify_dates(row, view, now):
    try:
        own = E.nights(row.get("pushed_check_in"), row.get("pushed_check_out"))
        probe, snap, why = _probe_snapshot(row["property_id"], row.get("rate_plan_id"), view["check_in"],
                                           view["check_out"], own)
    except StayHubError as e:
        return _fail(row, e, now, "probe")
    if snap is None:
        return _fail(row, StayHubError("NO_AVAILABILITY", 409, why), now, "modify")
    total = view.get("total") if view.get("total") is not None else snap["totalAmount"]

    def body(rev):
        return {"externalRevision": rev, "checkIn": view["check_in"], "checkOut": view["check_out"],
                "partnerSnapshot": snap,
                "financial": {"total": _num_out(total), "currency": view.get("currency") or config.default_currency()}}
    row, ok = _send_change(row, "modify", body, now)
    if not ok:
        return row
    rev, _data, trace = ok
    row = db.update_booking(row["ha_reservation_id"], revision=rev, pushed_check_in=view["check_in"],
                            pushed_check_out=view["check_out"], pushed_total=_num_out(total), last_code=None,
                            last_error=None, next_try_at=None, last_trace=trace, attempts=0, notified=0)
    _event(row, "modified_dates", "rev=%s %s→%s" % (rev, view["check_in"], view["check_out"]), trace, now)
    return row


def _modify_amount(row, view, now):
    total = _num_out(view["total"])

    def body(rev):
        return {"externalRevision": rev,
                "financial": {"total": total, "currency": view.get("currency") or config.default_currency()}}
    row, ok = _send_change(row, "modify", body, now)
    if not ok:
        return row
    rev, _data, trace = ok
    row = db.update_booking(row["ha_reservation_id"], revision=rev, pushed_total=total, last_code=None,
                            last_error=None, next_try_at=None, last_trace=trace, attempts=0)
    _event(row, "modified_amount", "rev=%s total=%s" % (rev, total), trace, now)
    return row


def _cancel(row, now, reason="Cancelled on Airbnb"):
    def body(rev):
        return {"externalRevision": rev, "reason": reason}
    row, ok = _send_change(row, "cancel", body, now)
    if not ok:
        return row
    rev, _data, trace = ok
    row = db.update_booking(row["ha_reservation_id"], status=E.CANCELLED, revision=rev, last_code=None,
                            last_error=None, next_try_at=None, last_trace=trace, attempts=0)
    _event(row, "cancelled", "rev=%s" % rev, trace, now)
    _log("انلغى حجز في ستاي هب بعد إلغائه في Airbnb · %s" % notify._unit(row.get("listing_id")))
    return row


# ---------------- the one path ----------------

def process(r, now=None, force=False):
    """One Hostaway reservation. Returns (action, row_or_reason). Never raises for StayHub errors."""
    now = _now(now)
    view = E.reservation_view(r, config.default_currency())
    rid = view["ha_reservation_id"]
    if not rid:
        return None, "no_id"
    try:
        lk = _acquire(rid)
    except _Busy:
        return None, "busy"
    try:
        return _process_locked(r, view, now, force)
    finally:
        lk.release()


def _due(row, now):
    nt = row.get("next_try_at")
    return not nt or nt <= _iso(now)


def _process_locked(r, view, now, force):
    rid = view["ha_reservation_id"]
    row = db.booking(rid)
    cancelled = E.is_cancelled(view["status"])
    mapping = db.map_for_listing(view["listing_id"]) if view["listing_id"] is not None else None

    # the unit moved to another listing in Hostaway: release the old StayHub booking first
    if row and row.get("status") == E.CONFIRMED and view["listing_id"] is not None \
            and row.get("listing_id") != view["listing_id"]:
        row = _cancel(row, now, reason="Moved to another unit")
        if row.get("status") != E.CANCELLED:
            return "cancel", row

    action = E.plan(view, row, cancelled)
    if action is None and row and row.get("status") in (E.PENDING, E.RETRY, E.REJECTED, E.HELD) and not cancelled:
        action = "retry"
    if action is None:
        if row:
            db.update_booking(rid, check_in=view["check_in"], check_out=view["check_out"], total=view["total"])
        return None, "nothing"

    if action == "skip_cancel":
        row = db.update_booking(rid, status=E.SKIPPED, next_try_at=None)
        _event(row, "skipped", "cancelled in Hostaway before reaching StayHub", None, now)
        return action, row
    if action == "cancel":
        if not force and not _due(row, now):
            return None, "waiting"
        return action, _cancel(row, now)
    if action in ("modify_dates", "modify_amount"):
        if not force and not _due(row, now):
            return None, "waiting"
        db.update_booking(rid, check_in=view["check_in"], check_out=view["check_out"], total=view["total"])
        return action, (_modify_dates(row, view, now) if action == "modify_dates" else _modify_amount(row, view, now))

    # create / retry
    ok, why = E.eligibility(view, _channel(r), config.push_channels(), _confirmed_statuses(), bool(mapping), now)
    if not ok:
        if row and why in ("unmapped", "channel", "started", "status"):
            db.update_booking(rid, status=E.SKIPPED if why != "unmapped" else row["status"], last_code=why.upper())
        return None, why
    if row is None or row.get("status") in (E.CANCELLED, E.SKIPPED):
        ext = view["external_id"]
        if row is not None:
            # re-booking after a cancel: StayHub refuses a reused code with a new revision
            n = len([e for e in db.events(rid, 500) if e.get("kind") == "confirmed"]) + 1
            ext = "%s-R%d" % (view["external_id"], n)
            db.update_booking(rid, status=E.PENDING, external_id=ext, sh_reservation_id=None, revision=0,
                              attempts=0, notified=0, next_try_at=None, listing_id=view["listing_id"],
                              property_id=mapping["property_id"], rate_plan_id=mapping.get("rate_plan_id"))
            row = db.booking(rid)
        else:
            row = db.insert_booking(ha_reservation_id=rid, external_id=ext, listing_id=view["listing_id"],
                                    property_id=mapping["property_id"], rate_plan_id=mapping.get("rate_plan_id"),
                                    status=E.PENDING, check_in=view["check_in"], check_out=view["check_out"],
                                    adults=view["adults"], total=view["total"], currency=view["currency"],
                                    created_at=_iso(now)) or db.booking(rid)
    elif not force and not _due(row, now):
        return None, "waiting"
    row = db.update_booking(rid, check_in=view["check_in"], check_out=view["check_out"], adults=view["adults"],
                            total=view["total"], currency=view["currency"], property_id=mapping["property_id"],
                            rate_plan_id=mapping.get("rate_plan_id") or row.get("rate_plan_id"))
    return "create", _create(row, view, r, now)


# ---------------- the poller + the webhook path ----------------

def _chunks(start, end, days=120):
    a = start
    while a <= end:
        b = min(end, a + datetime.timedelta(days=days - 1))
        yield a, b
        a = b + datetime.timedelta(days=1)


def tick(now=None):
    """One push poll. Does nothing (and costs no Hostaway call) until StayHub credentials are
    set AND at least one unit is mapped."""
    if not config.configured():
        return {"skipped": "not_configured"}
    maps = {m["listing_id"] for m in db.maps()}
    if not maps:
        return {"skipped": "no_units_mapped"}
    now = _now(now)
    today = _naive(now).date()
    win = HOST.require("ha_reservations_window")
    known = {b["ha_reservation_id"] for b in db.q("SELECT ha_reservation_id FROM stayhub_bookings")}
    rows, seen = [], set()
    for a, b in _chunks(today - datetime.timedelta(days=3), today + datetime.timedelta(days=config.horizon_days())):
        try:
            batch = win("arrivalStartDate", "arrivalEndDate", a.isoformat(), b.isoformat()) or []
        except Exception as e:
            print("[stayhub] Hostaway window %s..%s failed (next tick retries): %s" % (a, b, e))
            continue
        for r in batch:
            rid = str((r or {}).get("id") or "")
            lid = (r or {}).get("listingMapId") or (r or {}).get("listingId")
            try:
                lid = int(lid)
            except (TypeError, ValueError):
                lid = None
            if rid and rid not in seen and (lid in maps or rid in known):
                seen.add(rid)
                rows.append(r)
    budget = config.max_push_per_tick()
    out = {"fetched": len(rows), "actions": {}, "reasons": {}, "waiting": 0}
    for r in sorted(rows, key=lambda x: str(x.get("arrivalDate") or "")):
        if budget <= 0:
            out["waiting"] += 1
            continue
        action, res = process(r, now)
        if action:
            budget -= 1
            out["actions"][action] = out["actions"].get(action, 0) + 1
        elif isinstance(res, str):
            out["reasons"][res] = out["reasons"].get(res, 0) + 1
    # rows due for a retry that the window did not return (e.g. a lookup failed earlier)
    fetch = getattr(HOST, "ha_reservation", None)
    for row in db.due_retries(_iso(now), limit=max(0, budget)):
        if row["ha_reservation_id"] in seen or not fetch:
            continue
        try:
            r = fetch(row["ha_reservation_id"])
        except Exception:
            r = None
        if isinstance(r, dict) and r.get("id") is not None:
            action, _res = process(r, now)
            if action:
                out["actions"][action] = out["actions"].get(action, 0) + 1
    if out["actions"] or out["waiting"]:
        print("[stayhub] push tick · fetched=%d actions=%s waiting=%d reasons=%s dryrun=%s"
              % (out["fetched"], out["actions"], out["waiting"], out["reasons"], config.dryrun()))
    return out


def on_hook(reservation_id, now=None):
    """Hostaway webhook path: ONE targeted GET, then process(). Never raises."""
    try:
        if not config.configured() or not reservation_id:
            return None
        fn = getattr(HOST, "ha_reservation", None)
        if not fn:
            return None
        r = fn(reservation_id)
        if not isinstance(r, dict) or r.get("id") is None:
            return None
        lid = r.get("listingMapId") or r.get("listingId")
        if not db.map_for_listing(lid) and not db.booking(r.get("id")):
            return None
        return process(r, now)
    except Exception as e:
        print("[stayhub] hook path failed (non-fatal):", e)
        return None


def retry_now(ha_reservation_id, now=None):
    """The dashboard «أعد المحاولة» button: clear the wait and push this one reservation now."""
    row = db.booking(ha_reservation_id)
    fn = getattr(HOST, "ha_reservation", None)
    if not row or not fn:
        return None, "not_found"
    if row.get("status") == E.FAILED:
        db.update_booking(ha_reservation_id, status=E.RETRY, attempts=0, notified=0, next_try_at=None)
    r = fn(ha_reservation_id)
    if not isinstance(r, dict) or r.get("id") is None:
        return None, "hostaway_unreachable"
    return process(r, now, force=True)
