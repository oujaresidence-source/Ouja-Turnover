# -*- coding: utf-8 -*-
"""
directpay.service — the orchestration: reservations in, ledger rows + notifications out.
Reaches the world only through HOST (Hostaway reads, the Discord notifier, the activity log)
and db (brain.db). No discord, no sockets. bot.py's poller, webhook path and buttons all call
these functions, so the poller and the webhook take the SAME path.

THE START-DATE CUTOFF — the single most dangerous thing in this build.
    start_date() persists the first-boot date into directpay_settings on first run and never
    recomputes it. Without it the first tick opens a Discord room for every historical direct
    booking. On top of it: a per-tick cap (DIRECTPAY_MAX_OPEN_PER_TICK) and DRY-RUN by default.
"""
import datetime
import json

from . import config, db, engine, notify
from .host import HOST

_ROOM_RETRY_HOURS = 1          # a room whose creation failed is re-requested after this long


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


def _log(text):
    fn = getattr(HOST, "log_event", None)
    if fn:
        try:
            fn("finance", text)
            return
        except Exception as e:
            print("[directpay] log_event failed (non-fatal):", e)
    print("[finance] " + text)


# ---------------- settings ----------------

def start_date():
    """Persisted on first run (env DIRECTPAY_START_DATE seeds it, else today); never recomputed."""
    saved = db.setting_get("start_date")
    d = _parse_date(saved)
    if d:
        return d
    d = _parse_date(config.start_date_env()) or _naive(_now()).date()
    db.setting_set("start_date", d.isoformat())
    return d


def _parse_date(s):
    s = str(s or "").strip()[:10]
    if len(s) != 10:
        return None
    try:
        return datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except (TypeError, ValueError):
        return None


# ---------------- opening ----------------

def _listing_name(lid):
    try:
        m = HOST.listings() if getattr(HOST, "listings", None) else {}
    except Exception:
        m = {}
    if not m:
        return None
    return m.get(lid) or m.get(str(lid)) or (m.get(int(lid)) if str(lid).isdigit() else None)


def _payment(r):
    fn = getattr(HOST, "payment_signal", None)
    if not fn:
        return None, None, None, []
    try:
        st, paid, rem, fields = fn(r)
        return st, paid, rem, list(fields or [])
    except Exception:
        return None, None, None, []


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fields_from(r, now):
    st, paid, rem, fields = _payment(r)
    lid = r.get("listingMapId") or r.get("listingId")
    try:
        lid = int(lid) if lid is not None else None
    except (TypeError, ValueError):
        lid = None
    total = _num(r.get("totalPrice"))
    return {
        "reservation_id": str(r.get("id")).strip(),
        "confirmation_code": r.get("confirmationCode") or r.get("hostawayReservationId") or None,
        "listing_id": lid,
        "unit_name": _listing_name(lid) or r.get("listingName") or ("unit-%s" % lid if lid else None),
        "guest_name": r.get("guestName") or (" ".join(x for x in (r.get("guestFirstName"), r.get("guestLastName")) if x) or None),
        "guest_phone": r.get("phone") or r.get("guestPhone") or None,
        "channel_raw": engine.raw_channel(r),
        "arrival": (r.get("arrivalDate") or "")[:10] or None,
        "departure": (r.get("departureDate") or "")[:10] or None,
        "nights": int(r.get("nights") or 0) or None,
        "total_sar": total,
        "total_sar_current": total,
        "booked_at": str(r.get("reservationDate") or "")[:19] or None,
        "ha_status": str(r.get("status") or "").lower() or None,
        "ha_payment_status": st,
        "ha_paid_amount": paid,
        "ha_remaining": rem,
        "ha_payment_fields": ",".join(fields),
        "created_at": _iso(now),
        "refreshed_at": _iso(now),
    }


def _request_room(ticket, now):
    """Fire the 'open' notification (bot.py creates the room) and stamp room_requested_at so
    the same row is not re-requested every tick; a failed creation retries after an hour."""
    db.update(ticket["id"], room_requested_at=_iso(now))
    notify.fire("open", {"ticket_id": ticket["id"], "text": notify.open_text(ticket)})


def process_reservations(reservations, now=None, known_ids=(), known_rooms=None, max_open=None):
    """The one path (poller AND webhook). Returns
        {opened: [tickets], waiting: n, skipped: {reason: n}, refreshed: n, backfilled: n}
    * eligibility per engine.eligibility, against the ledger + `known_ids` (channel topics)
    * at most `max_open` (default DIRECTPAY_MAX_OPEN_PER_TICK) rows opened per call — the rest
      is counted in `waiting`, never dropped
    * DRY-RUN writes the row (dryrun=1) and fires nothing
    * existing rows seen in the batch are refreshed (price drift / cancellation, §5.7)
    * rows without a room (dry-run days, failed creations) get one within the same cap
    """
    now = _now(now)
    dry = config.dryrun()
    sd = start_date()
    fc = HOST.require("finance_channel")
    cs = HOST.confirmed_statuses() if getattr(HOST, "confirmed_statuses", None) else {"new", "modified"}
    extra = config.extra_channels()
    known = set(db.known_reservation_ids()) | {str(k) for k in (known_ids or ())}
    known_rooms = dict(known_rooms or {})
    cap = config.max_open_per_tick() if max_open is None else max(0, int(max_open))

    skipped, eligible, refreshed = {}, [], 0
    for r in reservations or []:
        rid = str((r or {}).get("id") or "").strip()
        existing = db.by_reservation(rid) if rid else None
        if existing:
            if _refresh_row(existing, r, now):
                refreshed += 1
            skipped["duplicate"] = skipped.get("duplicate", 0) + 1
            continue
        ok, why = engine.eligibility(r, fc, cs, sd, extra, known)
        if ok:
            eligible.append(r)
            known.add(rid)
        else:
            skipped[why] = skipped.get(why, 0) + 1

    # self-heal: a room already exists in Discord (topic) but the ledger lost the row
    rehydrated = []
    still = []
    for r in eligible:
        rid = str(r.get("id"))
        if rid in known_rooms:
            f = _fields_from(r, now)
            room = known_rooms[rid] or {}
            f.update(channel_id=str(room.get("channel_id") or "") or None, seq=room.get("seq"))
            t = db.open_ticket(**f)
            if t:
                db.add_event(t["id"], "rehydrated", actor="bot", detail="row rebuilt from channel topic", at=_iso(now))
                rehydrated.append(t)
            continue
        still.append(r)

    take, waiting = engine.select_openable(still, cap)
    opened = []
    for r in take:
        f = _fields_from(r, now)
        f["dryrun"] = 1 if dry else 0
        t = db.open_ticket(**f)
        if not t:
            skipped["duplicate"] = skipped.get("duplicate", 0) + 1
            continue
        db.add_event(t["id"], "opened", actor="bot",
                     detail="channel=%r total=%s booked=%s%s" % (f["channel_raw"], f["total_sar"], f["booked_at"],
                                                                " (dryrun)" if dry else ""), at=_iso(now))
        opened.append(t)
        if dry:
            print("[directpay] DRYRUN would open a room: %s · %s · %s · channel=%r"
                  % (t["unit_name"], t["guest_name"], notify.fmt_sar(t["total_sar"]), f["channel_raw"]))
        else:
            _request_room(t, now)

    backfilled = 0
    if not dry:
        remaining = max(0, cap - len(opened))
        cutoff = _iso(_naive(now) - datetime.timedelta(hours=_ROOM_RETRY_HOURS))
        pending = db.roomless_count(cutoff)
        if remaining and pending:
            for t in db.roomless(cutoff, limit=remaining):
                _request_room(t, now)
                backfilled += 1
        waiting += max(0, pending - backfilled)
    if waiting:
        print("[directpay] %d ticket(s) waiting for the next tick (cap %d/tick)" % (waiting, cap))
    return {"opened": opened, "rehydrated": rehydrated, "waiting": waiting, "skipped": skipped,
            "refreshed": refreshed, "backfilled": backfilled, "dryrun": dry}


# ---------------- §5.7 changes after the fact ----------------

def _refresh_row(ticket, r, now):
    """Refresh total / payment / status from a fresh Hostaway read. Never auto-voids a
    cancellation and never auto-closes anything. Returns True when something changed."""
    if ticket.get("status") in engine.TERMINAL:
        return False
    st, paid, rem, fields = _payment(r)
    new_total = _num(r.get("totalPrice"))
    ha_status = str(r.get("status") or "").lower() or None
    patch = {"refreshed_at": _iso(now), "ha_payment_status": st, "ha_paid_amount": paid,
             "ha_remaining": rem, "ha_payment_fields": ",".join(fields), "ha_status": ha_status}
    old_total = engine.row_amount(ticket)
    changed = False

    if ticket.get("status") == "verified":
        if new_total is not None and _within_watch(ticket, now):
            ok, _why, tp = engine.transition(ticket, "open", {"total_sar_current": new_total})
            if ok:
                patch.update(tp)
                patch["reopened_at"] = _iso(now)
                db.add_event(ticket["id"], "reopened", actor="bot",
                             detail="price rose after close: %s -> %s" % (old_total, new_total), at=_iso(now))
                notify.fire("price_up", {"ticket_id": ticket["id"],
                                         "text": notify.price_up_text(ticket, old_total, new_total)})
                _log("رجعت غرفة التحصيل %s مفتوحة · زاد المبلغ من %s إلى %s"
                     % (ticket.get("unit_name") or ticket["id"], notify.fmt_sar(old_total), notify.fmt_sar(new_total)))
                changed = True
    elif ticket.get("status") == "open":
        if new_total is not None and abs(new_total - old_total) > 0.005:
            patch["total_sar_current"] = new_total
            db.add_event(ticket["id"], "price_changed", actor="bot",
                         detail="%s -> %s" % (old_total, new_total), at=_iso(now))
            notify.fire("price_changed", {"ticket_id": ticket["id"],
                                          "text": notify.price_changed_text(old_total, new_total)})
            changed = True
        if engine.is_cancelled(ha_status) and not engine.is_cancelled(ticket.get("ha_status")):
            db.add_event(ticket["id"], "cancelled_in_hostaway", actor="bot", detail=ha_status or "", at=_iso(now))
            notify.fire("cancelled", {"ticket_id": ticket["id"], "text": notify.cancelled_text()})
            changed = True
    db.update(ticket["id"], **patch)
    return changed


def _within_watch(ticket, now):
    closed = _parse_date(ticket.get("closed_at"))
    if not closed:
        return False
    return (_naive(now).date() - closed).days <= config.watch_days()


def refresh_unseen(seen_ids, now=None):
    """Live rows the arrival-window batch did not contain (already checked in / departed) get
    ONE targeted GET each, at most every DIRECTPAY_REFRESH_HOURS, at most N per tick."""
    now = _now(now)
    fn = getattr(HOST, "ha_reservation", None)
    if not fn:
        return 0
    seen = {str(s) for s in (seen_ids or ())}
    cutoff = _iso(_naive(now) - datetime.timedelta(hours=config.refresh_every_hours()))
    budget = config.refresh_max_per_tick()
    done = 0
    for t in db.live_tickets():
        if done >= budget:
            break
        if t["reservation_id"] in seen:
            continue
        if t.get("status") == "verified" and not _within_watch(t, now):
            continue
        if (t.get("refreshed_at") or "") > cutoff:
            continue
        try:
            r = fn(t["reservation_id"])
        except Exception as e:
            print("[directpay] refresh fetch failed (non-fatal):", e)
            continue
        done += 1
        if isinstance(r, dict) and r.get("id") is not None:
            _refresh_row(t, r, now)
        else:
            db.update(t["id"], refreshed_at=_iso(now))
    return done


def refresh_ticket(ticket_id, now=None):
    """The «تحديث» button: one targeted GET for this ticket's reservation, then §5.7."""
    t = db.ticket(ticket_id)
    fn = getattr(HOST, "ha_reservation", None)
    if not t or not fn:
        return None
    try:
        r = fn(t["reservation_id"])
    except Exception as e:
        print("[directpay] refresh fetch failed (non-fatal):", e)
        return None
    if isinstance(r, dict) and r.get("id") is not None:
        _refresh_row(t, r, _now(now))
    return db.ticket(ticket_id)


# ---------------- the poller ----------------

def _chunks(start, end, days=120):
    a = start
    while a <= end:
        b = min(end, a + datetime.timedelta(days=days - 1))
        yield a, b
        a = b + datetime.timedelta(days=1)


def tick(now=None, known_ids=(), known_rooms=None):
    """One poll. A targeted arrival window (today - lookback → today + 400), NEVER the truncated
    reservation cache, in ≤120-day slices so no slice hits _ha_reservations_window's page cap."""
    if not config.enabled():
        return {"skipped": "disabled"}
    now = _now(now)
    today = _naive(now).date()
    start = today - datetime.timedelta(days=config.lookback_days())
    end = today + datetime.timedelta(days=config.horizon_days())
    win = HOST.require("ha_reservations_window")
    rows, seen = [], set()
    for a, b in _chunks(start, end):
        try:
            batch = win("arrivalStartDate", "arrivalEndDate", a.isoformat(), b.isoformat()) or []
        except Exception as e:
            print("[directpay] Hostaway window %s..%s failed (non-fatal, next tick retries): %s" % (a, b, e))
            continue
        for r in batch:
            rid = str((r or {}).get("id") or "")
            if rid and rid not in seen:
                seen.add(rid)
                rows.append(r)
    out = process_reservations(rows, now=now, known_ids=known_ids, known_rooms=known_rooms)
    out["fetched"] = len(rows)
    try:
        out["unseen_refreshed"] = refresh_unseen(seen, now)
    except Exception as e:
        print("[directpay] unseen refresh failed (non-fatal):", e)
    print("[directpay] tick · fetched=%d opened=%d waiting=%d skipped=%s dryrun=%s"
          % (len(rows), len(out["opened"]), out["waiting"], out["skipped"], out["dryrun"]))
    return out


def on_hook_reservation(reservation_id, now=None):
    """The webhook path: ONE targeted GET for that reservation, then the same path as the
    poller. Never raises — the hook must ack 200 fast regardless."""
    try:
        if not config.enabled():
            return None
        fn = getattr(HOST, "ha_reservation", None)
        if not fn or not reservation_id:
            return None
        r = fn(reservation_id)
        if not isinstance(r, dict) or r.get("id") is None:
            return None
        return process_reservations([r], now=now)
    except Exception as e:
        print("[directpay] hook path failed (non-fatal):", e)
        return None


# ---------------- closing (called from the Discord buttons) ----------------

def attest_verified(ticket_id, received_sar, stayhub_ref, proof_rel, proof_meta, by, by_id,
                    note="", variance_reason="", now=None):
    """The normal close. engine.transition decides; this writes the row + the event + the log."""
    t = db.ticket(ticket_id)
    if not t:
        return False, "ما لقيت التذكرة.", {"code": "missing"}
    now = _now(now)
    ok, why, patch = engine.transition(t, "verified", {
        "received_sar": received_sar, "stayhub_ref": stayhub_ref, "proof_path": proof_rel,
        "proof_meta": json.dumps(proof_meta or {}, ensure_ascii=False) if not isinstance(proof_meta, str) else proof_meta,
        "note": note, "variance_reason": variance_reason, "by": by, "by_id": by_id, "now": _iso(now),
        "abs_tol": config.variance_sar(), "pct_tol": config.variance_pct()})
    if not ok:
        db.add_event(t["id"], "close_refused", actor=by, actor_id=by_id,
                     detail="%s: %s" % (patch.get("code"), why), at=_iso(now))
        return False, why, patch
    if patch:
        db.update(t["id"], **patch)
        db.add_event(t["id"], "verified", actor=by, actor_id=by_id,
                     detail="received=%s ref=%s variance=%s proof=%s" % (patch.get("received_sar"), patch.get("stayhub_ref"),
                                                                       patch.get("variance_sar"), proof_rel), at=_iso(now))
        _log("تم تحصيل حجز مباشر · %s · %s · %s · مرجع StayHub %s · بواسطة %s"
             % (t.get("unit_name") or "—", t.get("guest_name") or "—", notify.fmt_sar(patch.get("received_sar")),
                patch.get("stayhub_ref"), by))
    return True, "", db.ticket(t["id"])


def write_off(ticket_id, reason, by, by_id, now=None):
    t = db.ticket(ticket_id)
    if not t:
        return False, "ما لقيت التذكرة.", {"code": "missing"}
    now = _now(now)
    ok, why, patch = engine.transition(t, "written_off", {"reason": reason, "by": by, "by_id": by_id, "now": _iso(now)})
    if not ok:
        db.add_event(t["id"], "writeoff_refused", actor=by, actor_id=by_id, detail="%s: %s" % (patch.get("code"), why), at=_iso(now))
        return False, why, patch
    db.update(t["id"], **patch)
    db.add_event(t["id"], "written_off", actor=by, actor_id=by_id, detail=reason, at=_iso(now))
    _log("🔴 إغلاق بدون إثبات · %s · %s · %s · بواسطة %s · السبب: %s"
         % (t.get("unit_name") or "—", t.get("guest_name") or "—", notify.fmt_sar(engine.row_amount(t)), by, reason))
    return True, "", db.ticket(t["id"])


def void_ticket(ticket_id, reason, by, by_id, now=None):
    t = db.ticket(ticket_id)
    if not t:
        return False, "ما لقيت التذكرة.", {"code": "missing"}
    now = _now(now)
    ok, why, patch = engine.transition(t, "void", {"reason": reason, "by": by, "by_id": by_id, "now": _iso(now)})
    if not ok:
        db.add_event(t["id"], "void_refused", actor=by, actor_id=by_id, detail="%s: %s" % (patch.get("code"), why), at=_iso(now))
        return False, why, patch
    db.update(t["id"], **patch)
    db.add_event(t["id"], "void", actor=by, actor_id=by_id,
                 detail="reason=%s channel_raw=%r" % (reason, t.get("channel_raw")), at=_iso(now))
    _log("أُلغيت غرفة تحصيل · %s · %s · القناة «%s» · بواسطة %s · %s"
         % (t.get("unit_name") or "—", t.get("guest_name") or "—", t.get("channel_raw") or "", by, reason))
    return True, "", db.ticket(t["id"])


def refuse(ticket_id, actor, actor_id, action, now=None):
    """Someone without the gate pressed a button. Logged with their name — the owner's early
    warning that somebody is trying."""
    db.add_event(ticket_id, "refused", actor=actor, actor_id=actor_id, detail="action=%s" % action, at=_iso(_now(now)))


def add_note(ticket_id, text, actor, actor_id="", now=None):
    t = db.ticket(ticket_id)
    if not t:
        return None
    db.add_event(t["id"], "note", actor=actor, actor_id=actor_id, detail=str(text or "")[:400], at=_iso(_now(now)))
    return t


def set_room(ticket_id, channel_id, card_msg_id=None, seq=None):
    patch = {"channel_id": str(channel_id)}
    if card_msg_id is not None:
        patch["card_msg_id"] = str(card_msg_id)
    if seq is not None:
        patch["seq"] = int(seq)
    return db.update(ticket_id, **patch)


# ---------------- nudges + daily summary ----------------

def nudges(now=None):
    """One nudge per window per open room. Counters move only when something was really sent,
    so dry-run never burns a window."""
    now = _now(now)
    out = []
    after, every = config.nudge_after_days(), config.nudge_every_days()
    for t in db.open_tickets():
        if not t.get("channel_id"):
            continue
        if not engine.nudge_due(t, _naive(now), after, every):
            continue
        age = engine.age_days(t, _naive(now))
        sent = notify.fire("nudge", {"ticket_id": t["id"], "text": notify.nudge_text(t, age), "age": age})
        if sent:
            db.update(t["id"], nudge_count=int(t.get("nudge_count") or 0) + 1, last_nudge_at=_iso(now))
            db.add_event(t["id"], "nudged", actor="bot", detail="age=%d" % age, at=_iso(now))
        out.append(t["id"])
    return out


def board(now=None, room_link=None):
    now = _naive(_now(now))
    today = now.date()
    rows = db.tickets(limit=2000)
    opens = [dict(r, age_days=engine.age_days(r, today), amount=engine.row_amount(r))
             for r in rows if r.get("status") == "open"]
    opens.sort(key=lambda r: (r.get("created_at") or ""))
    month = today.isoformat()[:7]
    wo = [dict(r, amount=engine.row_amount(r)) for r in rows if r.get("status") == "written_off"]
    wo_month = [r for r in wo if str(r.get("closed_at") or "")[:7] == month]
    recent_cut = (today - datetime.timedelta(days=30)).isoformat()
    ver = [dict(r, amount=engine.row_amount(r)) for r in rows
           if r.get("status") == "verified" and str(r.get("closed_at") or "")[:10] >= recent_cut]
    void = [r for r in rows if r.get("status") == "void"][:50]
    if room_link:
        for r in opens + wo + ver:
            r["room_url"] = room_link(r.get("channel_id")) if r.get("channel_id") else ""
    return {
        "date": today.isoformat(),
        "open": opens,
        "oldest": opens[:5],
        "verified_recent": ver,
        "written_off": wo,
        "written_off_month": wo_month,
        "void": void,
        "totals": {"open_count": len(opens), "outstanding_sar": engine.outstanding_total(rows),
                   "written_off_count": len(wo), "written_off_sar": engine.written_off_total(rows),
                   "written_off_month_sar": round(sum(engine.row_amount(r) for r in wo_month), 2),
                   "verified_recent_count": len(ver),
                   "verified_recent_sar": round(sum(float(r.get("received_sar") or 0) for r in ver), 2)},
        "aging": engine.aging_buckets(rows, today),
        "dryrun": config.dryrun(),
        "start_date": db.setting_get("start_date"),
        "counts": db.counts(),
    }


def daily_summary(now=None, room_link=None):
    """Once per Riyadh day at DIRECTPAY_SUMMARY_HOUR, latched in directpay_settings (a
    redeploy re-runs a loop's first iteration; an in-memory latch would post twice)."""
    now = _now(now)
    local = _naive(now)
    if not engine.summary_due(local, db.setting_get("summary_date"), config.summary_hour()):
        return None
    b = board(now, room_link)
    text = notify.summary_text(b, room_link)
    sent = notify.fire("summary", {"text": text, "date": b["date"]})
    if sent:
        db.setting_set("summary_date", b["date"])
    return {"date": b["date"], "sent": sent, "text": text}
