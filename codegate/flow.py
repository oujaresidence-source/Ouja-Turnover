# codegate/flow.py
# -*- coding: utf-8 -*-
"""
codegate.flow — the tick and the buttons of «تسليم الرموز» (revision 2, spec §9).

The card lives in the unit's turnover room for the day; with no turnover coming, in a code-only
room (live only). The bot never decides that a guest agreed: a person reads the reply (the card
shows a hint) and presses «✅ وافق — أرسل الرمز», the ONLY path that sends a door code, or
«📝 أرسلته يدوياً» for a code sent by hand. A turnover room the bot held for the code, and every
code-only room, closes once the code is with the guest. Soak (switch OFF): cards in existing
turnover rooms only — no rooms opened, no holds, no re-posts, no alerts, no send button.
"""

import asyncio
import concurrent.futures
import datetime
import functools
import os
import time

from . import db, engine
from .host import HOST, wire

_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="codegate")
_locks = {}
_units_cache = {"key": None, "ids": set()}
_REPO_UNITS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "units.json")
_live_cache = {"v": None, "at": 0.0}
LIVE_TTL_SEC = 30
# Hostaway's "Doorcodera" sends the code 3 hours before check-in. At go-live, an arrival whose
# check-in is within this window of the switch already had its code sent (if the guest agreed).
PRELIVE_WINDOW_H = 3
PRELIVE_NAME = "Hostaway (قبل التشغيل)"
# A room delete that keeps failing is given up after this many tries (or at once for a row more
# than DELETE_GIVE_UP_DAYS old), with one «⚠️ ما قدرت أقفل الغرفة» line for a person to act on.
DELETE_MAX_TRIES = 3
DELETE_GIVE_UP_DAYS = 2


def wire_for_tests(caps):
    _units_cache.update({"key": None, "ids": set()})
    _live_cache.update({"v": None, "at": 0.0})
    wire(caps)


def enabled():
    return os.environ.get("CODEGATE_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")


def live():
    """The SOAK switch, stored in brain.db (the owner never edits Railway). OFF by default:
    while Hostaway still runs the old e-sign flow the list and cards run, but no alert, no
    escalation, no honesty check, and every other bot path treats the units as before.
    Turned on with `!ouja رموز-تشغيل تشغيل` in the Hostaway-switch sitting."""
    now = time.monotonic()
    if _live_cache["v"] is not None and now - _live_cache["at"] < LIVE_TTL_SEC:
        return _live_cache["v"]
    try:
        v = db.get_setting("live", "0") == "1"
    except Exception as e:
        print("[codegate] live switch unreadable, keeping %s: %s" % (_live_cache["v"], e))
        v = bool(_live_cache["v"])
    _live_cache.update({"v": v, "at": now})
    return v


def _now_riyadh():
    try:
        if HOST.now:
            return HOST.now()
    except Exception:
        pass
    return datetime.datetime.now(engine.tz())


def set_live(on, by=""):
    """On an OFF→ON transition also store `live_since` (Riyadh ISO with offset): the go-live
    moment that anchors the one-time pre-live chat check. ON→ON keeps the old value, so a
    repeated command can't widen the window. OFF keeps it too (harmless: nothing reads it
    while off, and the next OFF→ON overwrites it)."""
    was_on = db.get_setting("live", "0") == "1"
    if on and not was_on:
        db.set_setting("live_since", _now_riyadh().isoformat(timespec="seconds"), by)
    db.set_setting("live", "1" if on else "0", by)
    db.event("_switch", "live_on" if on else "live_off", by)
    _live_cache.update({"v": bool(on), "at": time.monotonic()})
    return bool(on)


def _state_units_path():
    try:
        return HOST.state_path("codegate_units.json") if HOST.state_path else None
    except Exception:
        return None


def units():
    """Gated listing ids, re-read when either file's mtime changes."""
    paths = [p for p in (_state_units_path(), _REPO_UNITS) if p]
    key = tuple((p, os.path.getmtime(p)) for p in paths if os.path.exists(p))
    if key != _units_cache["key"]:
        _units_cache.update({"key": key, "ids": engine.load_units(_REPO_UNITS,
                                                                   _state_units_path())})
    return _units_cache["ids"]


def is_gated(lid):
    try:
        return int(lid) in units()
    except (TypeError, ValueError):
        return False


def released(res_id):
    it = db.get(res_id) if res_id else None
    return bool(it and it.get("released_at"))


async def run_blocking(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_pool, functools.partial(fn, *args, **kwargs))


def _lock(name):
    if name not in _locks:
        _locks[name] = asyncio.Lock()
    return _locks[name]


def _dt(iso):
    if not iso:
        return None
    d = datetime.datetime.fromisoformat(str(iso))
    return d if d.tzinfo else d.replace(tzinfo=engine.tz())


def _view_item(it):
    """A db row in the shape engine.card/alert_due expect (datetimes, parsed replies)."""
    v = dict(it)
    v["checkin_at"] = _dt(it.get("checkin_at"))
    v["rules_at"] = _dt(it.get("rules_at"))
    v["replies"] = [{"at": _dt(r.get("at")), "text": r.get("text") or ""}
                    for r in (it.get("replies") or [])]
    return v


def _mention(it):
    if it.get("cover_did"):
        return "<@%s>" % it["cover_did"]
    if it.get("cover_role_id"):
        return "<@&%s>" % it["cover_role_id"]
    return ""


def _buttons(it, is_live):
    """Soak: none (the soak note explains; Hostaway still auto-sends). Live: send + manual
    until released, then admin undo."""
    if it.get("cancelled") or not is_live:
        return []
    return ["undo"] if it.get("released_at") else ["send", "manual"]


async def _render(it, now_, is_live):
    """Post the card into its room if it has none; edit it only when its content changed.
    No room yet → nothing. Returns "posted" | "edited" | "lost" | None."""
    if it.get("cancelled") and not it.get("card_message_id"):
        return None                     # never had a card, never will
    channel_id = it.get("channel_id")
    if not channel_id:
        return None                     # placement hasn't found or opened a room yet
    view = _view_item(it)
    embed = engine.card(view, now_, soak=not is_live)
    buttons = _buttons(it, is_live)
    h = engine.content_hash({"e": embed, "b": buttons})
    if not it.get("card_message_id"):
        mid = await HOST.post(channel_id, _mention(it) or None, embed=embed, buttons=buttons)
        if mid:
            await run_blocking(db.set_card, it["res_id"], channel_id, mid, h)
            await run_blocking(db.event, it["res_id"], "card_posted", "", str(channel_id))
            return "posted"
        return None
    if h != it.get("card_hash"):
        ok = await HOST.edit(channel_id, it["card_message_id"], embed=embed, buttons=buttons)
        if ok:
            await run_blocking(db.set_hash, it["res_id"], h)
            return "edited"
        if is_live:
            await _card_lost(it)
            return "lost"
        # soak: leave it (no re-posts in soak)
    return None


async def _card_lost(it):
    """Live: the card (or its whole room) was deleted. Forget the card's room so placement runs
    again next tick (a held room is tracked separately and is untouched). A code-only room whose
    card alone was deleted would otherwise be orphaned, so it is closed (if the room itself is
    gone, delete_room reports that as closed)."""
    rid = it["res_id"]
    await run_blocking(db.event, rid, "card_lost", "", str(it.get("channel_id") or ""))
    if it.get("room_kind") == "code" and it.get("channel_id"):
        # success or give-up forgets the room (room_closed); a failed try KEEPS channel_id so
        # the next tick's edit fails again and retries the close (under the per-room cap) —
        # wiping it here would orphan the room
        await _close_room(it, it["channel_id"], "codegate: card lost",
                          "🗑️ غرفة رمز انحذفت بطاقتها — بفتح غيرها · %s · %s · %s"
                          % (it.get("unit") or "", it.get("guest") or "", _hhmm_now()))
        return
    await run_blocking(db.set_room, rid, None, None)


def _hhmm_now():
    return _now_riyadh().strftime("%H:%M")


def _too_old(it):
    """A row whose day is more than DELETE_GIVE_UP_DAYS behind today: one failure is enough."""
    try:
        d = datetime.date.fromisoformat(str(it.get("day")))
    except (TypeError, ValueError):
        return False
    return (_now_riyadh().date() - d).days > DELETE_GIVE_UP_DAYS


async def _delete_failed(it, ch, reason, held):
    """Count one failed close of THIS room (the card's room or the held room each have their own
    tally). After DELETE_MAX_TRIES for that room (or at once for an old row) stop trying: forget
    the room and tell #oujact-review so a person deletes it by hand."""
    rid = it["res_id"]
    try:
        n = await run_blocking(db.delete_failed, rid, held)
        await run_blocking(db.event, rid, "room_delete_failed", "", "%s %s" % (reason, ch or ""))
        if n < DELETE_MAX_TRIES and not _too_old(it):
            return
        await run_blocking(db.room_closed, rid, ch, held)
        await run_blocking(db.event, rid, "room_delete_gave_up", "", "%s %s" % (reason, ch or ""))
    except Exception as e:
        print("[codegate] delete-failure bookkeeping %s failed: %s" % (rid, e))
        return
    try:
        if HOST.log_review:
            await HOST.log_review("⚠️ ما قدرت أقفل الغرفة %s · %s · %s · %s — احذفها يدوياً"
                                  % ("<#%s>" % ch if ch else "(ما لقيتها)", it.get("unit") or "",
                                     it.get("guest") or "", reason))
    except Exception as e:
        print("[codegate] give-up audit line for %s failed: %s" % (rid, e))


async def _close_room(it, ch, reason, audit, held=False):
    """Delete room `ch` of this item. delete_room is True when deleted OR already gone. Success →
    the item forgets that room (the card's room and/or the held room) and one audit line goes to
    #oujact-review. Failure → counted (_delete_failed), retried by later ticks, never raises."""
    rid = it["res_id"]
    if not ch:
        return False
    try:
        ok = bool(await HOST.delete_room(ch, reason)) if HOST.delete_room else False
    except Exception as e:
        print("[codegate] room delete %s (%s) raised: %s" % (ch, rid, e))
        ok = False
    if not ok:
        print("[codegate] room delete %s (%s) failed: %s" % (ch, rid, reason))
        await _delete_failed(it, ch, reason, held)
        return False
    try:
        await run_blocking(db.room_closed, rid, ch, held)
        await run_blocking(db.event, rid, "room_deleted", "", "%s %s" % (reason, ch))
    except Exception as e:
        print("[codegate] room %s deleted but not recorded (%s): %s" % (ch, rid, e))
    try:
        if HOST.log_review:
            await HOST.log_review(audit)
    except Exception as e:
        print("[codegate] audit line for %s failed: %s" % (rid, e))
    return True


async def _close_held(it, reason, audit):
    """The deferred close of the turnover room the bot held: held_channel_id, or (not resolved at
    hold time) the unit's turnover room for that day looked up now. No such room any more → the
    hold is simply done."""
    if not it or not it.get("room_close_pending"):
        return False
    rid, ch = it["res_id"], it.get("held_channel_id")
    if not ch:
        try:
            ch = await run_blocking(HOST.find_room, it.get("lid"), it.get("day")) \
                if HOST.find_room else None
        except Exception as e:
            print("[codegate] held room lookup %s failed: %s" % (rid, e))
            await _delete_failed(it, None, reason, True)
            return False
        if not ch:
            await run_blocking(db.room_closed, rid, None, True)
            await run_blocking(db.event, rid, "held_room_gone", "", reason)
            return False
    return await _close_room(it, ch, reason, audit, held=True)


async def _close_owned(it, reason, audit):
    """Close every room codegate owes a close for: the code-only room the card is in, and the held
    turnover room. Returns (closed, still_owed). Never touches an unheld turnover room."""
    rid = it["res_id"]
    closed = 0
    if it.get("room_kind") == "code" and it.get("channel_id"):
        closed += bool(await _close_room(it, it["channel_id"], reason, audit))
        it = await run_blocking(db.get, rid) or it
    if it.get("room_close_pending"):
        closed += bool(await _close_held(it, reason, audit))
        it = await run_blocking(db.get, rid) or it
    owed = bool((it.get("room_kind") == "code" and it.get("channel_id")) or
                it.get("room_close_pending"))
    return closed, owed


def _delivered(it):
    """The code is known to be with the guest: the bot sent it, or the honesty check (or the
    go-live look) saw it in the chat after a manual record."""
    return bool(it.get("released_at")) and bool(it.get("sent_by_bot") or it.get("code_seen") == 1)


async def _after_code_sent(it):
    """Once the code is with the guest: the code-only room closes, and so does a turnover room the
    bot held (cleaning already asked to delete it) — whichever room the card is in. Idempotent:
    the tick calls it again for a delete that failed. Returns how many rooms it closed."""
    if not it or not _delivered(it):
        return 0
    audit = "🔑 أُرسل الرمز · %s · %s · %s · %s" % (
        it.get("unit") or "", it.get("guest") or "", it.get("released_by") or "",
        engine._hhmm(it.get("released_at")) or _hhmm_now())
    closed, _ = await _close_owned(it, "codegate: code sent", audit)
    return closed


async def _departures(ctx, day):
    """Listing ids with a departure today, fetched at most once per tick. None = unknown."""
    if "departures" not in ctx:
        try:
            got = await run_blocking(HOST.departures_today, day) if HOST.departures_today \
                else None
            ctx["departures"] = None if got is None else {int(x) for x in got}
        except Exception as e:
            print("[codegate] departures lookup failed: %s" % e)
            ctx["departures"] = None
    return ctx["departures"]


async def _place(it, now_, is_live, ctx, rep):
    """Give a waiting card a room: the unit's turnover room if it exists; live only, a code-only
    room — unless a departure today means the turnover room is still coming, in which case wait
    until check-in − 2h. Soak never opens a room."""
    if it.get("channel_id") or it.get("cancelled") or it.get("released_at"):
        return it
    rid, day = it["res_id"], it.get("day")
    try:
        room = await run_blocking(HOST.find_room, it.get("lid"), day) if HOST.find_room else None
    except Exception as e:      # don't open a code room just because the lookup hiccupped
        print("[codegate] find_room %s failed: %s" % (rid, e))
        return it
    if room:
        await run_blocking(db.set_room, rid, room, "turnover")
        return await run_blocking(db.get, rid)
    if not is_live:
        return it
    ci = _dt(it.get("checkin_at"))
    fallback = ci is None or now_ >= ci - datetime.timedelta(minutes=engine.ALERT_LEAD_MIN)
    if not fallback:
        deps = await _departures(ctx, day)
        try:
            lid = int(it.get("lid"))
        except (TypeError, ValueError):
            lid = None
        if deps is None or lid in deps:
            rep["waiting"] += 1
            return it               # the turnover room is (maybe) still coming
    ch = await HOST.create_code_room(it) if HOST.create_code_room else None
    if not ch:
        await run_blocking(db.event, rid, "code_room_failed")
        return it                   # the bot side alerted; try again next tick
    await run_blocking(db.set_room, rid, ch, "code")
    await run_blocking(db.event, rid, "code_room_opened", "", str(ch))
    rep["rooms"] += 1
    return await run_blocking(db.get, rid)


async def _prelive_check(it, now_, rep, msgs):
    """Go-live, ONCE per item (per go-live): did Hostaway's auto-send already give this guest the
    code? Uses the chat this same pass just fetched (`msgs`; None = that fetch failed), so it
    costs no extra Hostaway call. Returns 'skip' (couldn't look: no alert this tick, ask again
    next tick) or None (decided: carry on, either released quietly or genuinely no code)."""
    rid = it["res_id"]
    try:
        if not it.get("conversation_id"):
            seen = False
        elif msgs is None:
            raise RuntimeError("chat not fetched this tick")
        elif HOST.code_in:
            seen = bool(await run_blocking(HOST.code_in, msgs))
        else:                       # host without code_in: ask Hostaway again
            seen = bool(await run_blocking(HOST.code_sent, it.get("conversation_id")))
    except Exception as e:      # Hostaway down != "no code": say nothing, ask again next tick
        print("[codegate] pre-live check %s failed, retrying next tick: %s" % (rid, e))
        return "skip"
    stamp = now_.isoformat(timespec="seconds")
    if seen and await run_blocking(db.release, rid, PRELIVE_NAME, "", stamp):
        await run_blocking(db.set_code_seen, rid, True)     # nothing left for the honesty check
        await run_blocking(db.event, rid, "prelive_auto")
        rep["prelive"] += 1
    await run_blocking(db.set_prelive_checked, rid, stamp)
    return None


async def _process_item(it, now_, rep, is_live=True, prelive=None, ctx=None):
    """`prelive` = (live_since, live_since + 3 h) when a go-live moment is stored."""
    ctx = {} if ctx is None else ctx
    rid = it["res_id"]
    msgs = None                     # the chat as fetched THIS pass (None = not / failed)
    if not it.get("cancelled") and it.get("conversation_id"):
        try:
            msgs = await run_blocking(HOST.messages, it["conversation_id"]) or []
            r = engine.guest_replies(msgs)
            await run_blocking(
                db.set_replies, rid,
                r["rules_at"].isoformat(timespec="seconds") if r["rules_at"] else None,
                [{"at": x["at"].isoformat(timespec="seconds") if x["at"] else None,
                  "text": x["text"]} for x in r["replies"]])
        except Exception as e:      # stale replies are better than a skipped alert
            print("[codegate] replies refresh %s failed: %s" % (rid, e))
    it = await run_blocking(db.get, rid)
    # SOAK: cards in turnover rooms that already exist, nothing else. No honesty check, no
    # alert, no code-only room and nothing stamped, so all of it runs normally from the first
    # tick after the switch is turned on.
    if not is_live:
        it = await _place(it, now_, False, ctx, rep)
        res = await _render(it, now_, False)
        if res:
            rep[res] += 1
        return
    # a cancelled booking needs no code: its code-only room goes, and a turnover room the bot
    # held for the code gets the delete cleaning already asked for. (A booking moved to another
    # date also lands here — not arriving today — and the tick can't tell which.)
    if it.get("cancelled") and ((it.get("room_kind") == "code" and it.get("channel_id")) or
                                it.get("room_close_pending")):
        closed, _ = await _close_owned(it, "codegate: booking cancelled",
                                       "🗑️ قفلت الغرفة — الحجز ملغي أو انتقل · %s · %s · %s"
                                       % (it.get("unit") or "", it.get("guest") or "",
                                          _hhmm_now()))
        rep["deleted"] += closed
        return
    # GO-LIVE: arrivals inside Doorcodera's window are looked at once before any alert (and
    # before placement, so an already-sent code never opens a code-only room).
    hold_alerts = False
    if prelive and not it.get("released_at") and not it.get("cancelled"):
        # a check older than the current go-live doesn't count: after a rollback and a second
        # `رموز-تشغيل`, Doorcodera may have sent the code in between
        last = _dt(it.get("prelive_checked_at"))
        ci = _dt(it.get("checkin_at"))
        if (last is None or last < prelive[0]) and ci and ci <= prelive[1]:
            hold_alerts = (await _prelive_check(it, now_, rep, msgs)) == "skip"
            it = await run_blocking(db.get, rid)
    # honesty check: recorded by hand, but is the code really in the chat?
    if it.get("released_at") and it.get("code_seen") is None and not it.get("cancelled"):
        rel = _dt(it["released_at"])
        if rel and now_ >= rel + datetime.timedelta(minutes=engine.CODE_CHECK_MIN):
            try:
                seen = await run_blocking(HOST.code_sent, it.get("conversation_id"))
            except Exception as e:      # Hostaway down ≠ "no code": look again next tick
                print("[codegate] code check %s failed, retrying next tick: %s" % (rid, e))
                seen = None
        else:
            seen = None
        if seen is not None:
            await run_blocking(db.set_code_seen, rid, seen)
            await run_blocking(db.stamp, rid, "code_check_at",
                               now_.isoformat(timespec="seconds"))
            if not seen and not it.get("code_warned_at"):
                who = ("<@%s>" % it["released_by_did"]) if it.get("released_by_did") else ""
                text = ((who + " " if who else "") +
                        "⚠️ ضُغط الزر على **%s** بس ما شفت رسالة الرمز في "
                        "المحادثة — تأكد إنها انرسلت." % (it.get("unit") or ""))
                if it.get("channel_id"):
                    await HOST.post(it["channel_id"], text)
                else:                   # its room is gone: #escalations still hears it
                    await HOST.escalate("⚠️ ما شفت رسالة الرمز · " + (it.get("unit") or ""),
                                        text)
                await run_blocking(db.stamp, rid, "code_warned_at",
                                   now_.isoformat(timespec="seconds"))
                rep["warned"] += 1
            it = await run_blocking(db.get, rid)
    it = await _place(it, now_, True, ctx, rep)
    kind = None if hold_alerts else engine.alert_due(_view_item(it), now_)
    if kind:
        stamp = now_.isoformat(timespec="seconds")
        await run_blocking(db.stamp, rid, "alert_late_at" if kind == "late"
                           else "alert_2h_at", stamp)
        if kind == "late" and not it.get("alert_2h_at"):
            await run_blocking(db.stamp, rid, "alert_2h_at", stamp)
        # a release (or cancel) may have landed while we were busy: look again before sending
        it = await run_blocking(db.get, rid)
        if not it.get("released_at") and not it.get("cancelled"):
            text = engine.alert_text(kind, _view_item(it), _mention(it))
            if it.get("channel_id"):        # into the card's room; no room yet → escalate only
                await HOST.post(it["channel_id"], text)
            await HOST.escalate(("🔑 باقي ساعتين وما أُرسل الرمز · " if kind == "2h"
                                 else "🚨 حلّ الدخول وما أُرسل الرمز · ") + (it.get("unit") or ""),
                                text)
            await run_blocking(db.event, rid, "alert_" + kind)
            rep["alerts"] += 1
    it = await run_blocking(db.get, rid)        # never repaint from a stale copy
    res = await _render(it, now_, True)
    if res:
        rep[res] += 1
    # the code is with the guest (manual record seen by the honesty check, or a delete that
    # failed earlier): close the room it no longer needs
    it = await run_blocking(db.get, rid)
    rep["deleted"] += await _after_code_sent(it)


def _prelive_window():
    """(live_since, live_since + 3 h), or None when no go-live moment is stored (then nothing
    is pre-checked)."""
    try:
        ls = _dt(db.get_setting("live_since"))
    except Exception as e:
        print("[codegate] live_since unreadable: %s" % e)
        return None
    return (ls, ls + datetime.timedelta(hours=PRELIVE_WINDOW_H)) if ls else None


async def _sweep_old_rooms(day, rep):
    """Live: rooms codegate owns from days before `day` are closed — code-only rooms, and turnover
    rooms the bot held for a code that was never recorded (cleaning already asked to delete
    them; the day is over, so the hold has no purpose left). A db error skips the sweep this
    tick; it never aborts the tick."""
    try:
        code_rows = await run_blocking(db.code_room_items, day)
        held_rows = await run_blocking(db.held_room_items, day)
    except Exception as e:
        print("[codegate] old-room sweep skipped: %s" % e)
        return
    # a frozen move is retried by the move path only (one try per tick per room)
    code_rows = [r for r in code_rows if not r.get("moving_to")]
    held_rows = [r for r in held_rows if not r.get("moving_to")]
    for it in code_rows:
        try:
            if await _close_room(it, it.get("channel_id"), "codegate: day over",
                                 "🗑️ حذفت غرفة رمز من يوم فات (%s) · %s · %s · %s"
                                 % (it.get("day") or "", it.get("unit") or "",
                                    it.get("guest") or "", _hhmm_now())):
                rep["deleted"] += 1
        except Exception as e:
            print("[codegate] old room %s failed: %s" % (it.get("res_id"), e))
    for it in held_rows:
        try:
            it = await run_blocking(db.get, it["res_id"]) or it
            if await _close_held(it, "codegate: day over",
                                 "🗑️ حذفت غرفة تنظيف كانت معلّقة للرمز — يوم فات (%s) وما سُجل "
                                 "إرسال الرمز · %s · %s · %s"
                                 % (it.get("day") or "", it.get("unit") or "",
                                    it.get("guest") or "", _hhmm_now())):
                rep["deleted"] += 1
        except Exception as e:
            print("[codegate] old held room %s failed: %s" % (it.get("res_id"), e))


def _moved(prev, a, day):
    if not prev:
        return False
    if prev.get("day") != day:
        return True
    try:
        return int(prev.get("lid")) != int(a.get("lid"))
    except (TypeError, ValueError):
        return str(prev.get("lid")) != str(a.get("lid"))


async def _close_for_move(prev, a, day, rep):
    """Before upsert_arrival resets a moved booking's room: close its old code-only room and its
    old HELD turnover room (cleaning asked for that delete). An unheld turnover room — another
    unit's, or the same unit's on another day — is NEVER deleted. Returns True when something is
    still owed (a failed delete): the caller then skips the upsert so channel ids survive for the
    retry; _delete_failed's cap bounds how long."""
    closed, owed = await _close_owned(
        prev, "codegate: booking moved",
        "🗑️ قفلت الغرفة — الحجز انتقل لـ %s · %s · %s" % (
            day if prev.get("day") != day else "شقة ثانية", prev.get("unit") or "",
            prev.get("guest") or ""))
    rep["deleted"] += closed
    return owed


async def tick(now_=None, force=False):
    if not enabled():
        return {"skipped": "off"}
    async with _lock("tick"):
        now_ = now_ or HOST.now()
        day = now_.date().isoformat()
        is_live = await run_blocking(live)
        rep = {"live": int(is_live), "seen": 0, "posted": 0, "edited": 0, "lost": 0,
               "alerts": 0, "cancelled": 0, "warned": 0, "prelive": 0, "rooms": 0,
               "waiting": 0, "deleted": 0}
        gated = await run_blocking(units)
        # the tick's OWN day, so a tick that straddles midnight can't mix two days
        arrivals = await run_blocking(HOST.today_arrivals, day) or []
        keep = set()
        frozen = set()              # moved, but a close on the old arrival is still owed
        for a in arrivals:
            if str(a.get("day")) != day or not is_gated(a.get("lid")):
                continue
            try:
                cov = await run_blocking(HOST.cover, a["lid"], day) or {}
            except Exception as e:
                print("[codegate] cover lookup failed for %s: %s" % (a.get("res_id"), e))
                cov = {}
            prev = await run_blocking(db.get, str(a["res_id"]))
            if _moved(prev, a, day):
                # moved from another date or unit: db.upsert_arrival starts its card, room, hold
                # and alerts over, so what codegate owes on the old arrival is closed first
                await run_blocking(db.event, str(a["res_id"]), "moved", "",
                                   "%s/%s → %s/%s" % (prev.get("day"), prev.get("lid"), day,
                                                      a.get("lid")))
                if is_live:
                    try:
                        owed = await _close_for_move(prev, a, day, rep)
                    except Exception as e:
                        print("[codegate] moved rooms %s failed: %s" % (a.get("res_id"), e))
                        owed = True
                    if owed:
                        # FREEZE: keep the old ids for the retry next tick, and stop the row
                        # acting as an arrival of the old unit meanwhile (no room, no alert, no
                        # hold, no press); _delete_failed's per-room cap bounds how long
                        try:
                            await run_blocking(db.set_moving, str(a["res_id"]),
                                               int(a.get("lid")), day)
                        except Exception as e:
                            print("[codegate] freeze %s failed: %s" % (a.get("res_id"), e))
                        frozen.add(str(a["res_id"]))
                        keep.add(str(a["res_id"]))
                        continue
            if not (cov.get("name") or cov.get("did") or cov.get("role_id")):
                # a failed lookup must not blank who may press: keep what we stored
                if prev and prev.get("day") == day:
                    cov = {"name": prev.get("cover_name"), "did": prev.get("cover_did"),
                           "role_id": prev.get("cover_role_id"),
                           "owner_did": cov.get("owner_did") or prev.get("owner_did")}
            await run_blocking(db.upsert_arrival, dict(a, res_id=str(a["res_id"]),
                                                       cover_name=cov.get("name") or "",
                                                       cover_did=cov.get("did") or "",
                                                       cover_role_id=cov.get("role_id") or "",
                                                       owner_did=cov.get("owner_did") or ""))
            keep.add(str(a["res_id"]))
        # a row frozen by an earlier tick whose move did not show up again (cancelled, or moved
        # back) is unfrozen, so it is handled as what it now is
        await run_blocking(db.clear_moving_except, frozen)
        rep["seen"] = len(keep)
        rep["frozen"] = len(frozen)
        rep["cancelled"] = len(await run_blocking(db.mark_cancelled, day, keep))
        if not gated or (not force and now_.hour < engine.START_HOUR):
            return rep
        if is_live:
            await _sweep_old_rooms(day, rep)
        items = await run_blocking(db.day_items, day)
        prelive = await run_blocking(_prelive_window) if is_live else None
        ctx = {}                    # per-tick memo (departures fetched once)
        for it in items:
            if it.get("moving_to") or it["res_id"] in frozen:
                continue            # frozen move: no placement, no alert, no render
            try:
                await _process_item(it, now_, rep, is_live=is_live, prelive=prelive, ctx=ctx)
            except Exception as e:
                print("[codegate] item %s failed: %s" % (it.get("res_id"), e))
        return rep


async def _rerender(res_id):
    """Repaint after a press. A Discord failure here must not turn a done press into an error
    (the code may already be with the guest): it is logged, and the next tick repaints."""
    it = await run_blocking(db.get, res_id)
    if it:
        try:
            await _render(it, HOST.now(), await run_blocking(live))
        except Exception as e:
            print("[codegate] repaint %s failed, the tick retries: %s" % (res_id, type(e).__name__))
    return it


def _whose(it):
    return "هذي الشقة على %s اليوم — هو أو المشرف يضغط الزر." % (
        it.get("cover_name") or "فريق العمليات")


async def _press_checks(message_id, presser, need_live):
    """(item, None) when the press may go ahead, else (item|None, refusal text)."""
    it = await run_blocking(db.item_by_message, message_id)
    if not it:
        return None, "ما لقيت هذا الحجز في السجل."
    if it.get("cancelled"):
        return it, "الحجز ملغي — ما يحتاج رمز."
    if it.get("moving_to"):
        return it, "الحجز انتقل لشقة أو يوم ثاني — انتظر بطاقته الجديدة."
    if need_live and not await run_blocking(live):
        return it, "وضع التجربة — Hostaway يرسل الرمز تلقائياً حالياً، ما يحتاج تضغط."
    if it.get("released_at"):
        return it, "أُرسل من قبل — %s %s" % (it.get("released_by") or "",
                                             str(it["released_at"])[11:16])
    if not engine.may_release(presser.get("did"), it.get("cover_did"), it.get("owner_did"),
                              presser.get("is_admin"), presser.get("is_ops")):
        return it, _whose(it)
    return it, None


_SEND_FAIL = {
    "no_code": "Hostaway ما فيه رمز لهذا الحجز — أرسله يدوياً من Hostaway ثم اضغط "
               "«%s»." % engine.LABEL_MANUAL,
    "killed": "الإرسال للضيوف موقوف حالياً (مفتاح الإيقاف).",
    "duplicate": "هذي الرسالة انرسلت قبل شوي — ما أرسلتها مرتين.",
    "error": "Hostaway ما رد — جرّب بعد دقيقة.",
}


async def press_send(message_id, presser):
    """«✅ وافق — أرسل الرمز»: the ONLY path that sends a door code. The release is recorded
    FIRST (first press wins, so a double press can't send twice) and undone if the send fails."""
    it, refusal = await _press_checks(message_id, presser, need_live=True)
    if refusal:
        return False, refusal
    rid = it["res_id"]
    now_ = HOST.now().isoformat(timespec="seconds")
    if not await run_blocking(db.release, rid, presser.get("name") or "",
                              presser.get("did") or "", now_):
        fresh = await run_blocking(db.get, rid)
        return False, "أُرسل من قبل — %s" % ((fresh or {}).get("released_by") or "")
    try:
        if not HOST.send_code:
            raise RuntimeError("send_code not wired")
        res = await run_blocking(HOST.send_code, rid, it.get("conversation_id"))
        ok, why = bool(res[0]), str(res[1])
    except Exception as e:      # the sender must not raise; if it does, it did not send
        print("[codegate] send_code %s raised: %s" % (rid, type(e).__name__))
        ok, why = False, "error"
    if not ok:
        await run_blocking(db.undo, rid, "system", HOST.now().isoformat(timespec="seconds"))
        await run_blocking(db.event, rid, "code_send_failed", presser.get("name") or "", why)
        await _rerender(rid)
        return False, _SEND_FAIL.get(why, _SEND_FAIL["error"])
    await run_blocking(db.mark_sent_by_bot, rid)
    await run_blocking(db.set_code_seen, rid, True)     # nothing left for the honesty check
    await run_blocking(db.event, rid, "code_sent_bot", presser.get("name") or "")
    fresh = await _rerender(rid)
    try:
        await _after_code_sent(fresh)
    except Exception as e:      # the code is sent; a room that won't close is the tick's job
        print("[codegate] after-send %s failed: %s" % (rid, e))
    return True, "تم ✅ — أرسلت الرمز للضيف."


async def press_manual(message_id, presser):
    """«📝 أرسلته يدوياً»: records a code sent by hand from Hostaway (manual-code units). Works
    in soak too. The honesty check (live) later confirms it, and only then is the room closed."""
    it, refusal = await _press_checks(message_id, presser, need_live=False)
    if refusal:
        return False, refusal
    now_ = HOST.now().isoformat(timespec="seconds")
    if not await run_blocking(db.release, it["res_id"], presser.get("name") or "",
                              presser.get("did") or "", now_):
        fresh = await run_blocking(db.get, it["res_id"])
        return False, "أُرسل من قبل — %s" % ((fresh or {}).get("released_by") or "")
    await run_blocking(db.event, it["res_id"], "code_manual", presser.get("name") or "")
    await _rerender(it["res_id"])
    return True, "تم ✅ — سجّلت إنك أرسلت الرمز بنفسك."


async def press_undo(message_id, presser):
    """Admin only. Corrects the RECORD; a message already sent to the guest cannot be unsent."""
    if not presser.get("is_admin"):
        return False, "التراجع للمشرفين فقط."
    it = await run_blocking(db.item_by_message, message_id)
    if not it or not it.get("released_at"):
        return False, "ما فيه تسليم أتراجع عنه."
    await run_blocking(db.undo, it["res_id"], presser.get("name") or "",
                       HOST.now().isoformat(timespec="seconds"))
    await run_blocking(db.event, it["res_id"], "undone", presser.get("name") or "")
    # the sender's dedupe claim would refuse a legitimate re-send for hours: free it
    try:
        if HOST.release_send_claim:
            await run_blocking(HOST.release_send_claim, it["res_id"])
    except Exception as e:
        print("[codegate] send claim release %s failed: %s" % (it["res_id"], type(e).__name__))
    await _rerender(it["res_id"])
    return True, "صححت السجل — الرسالة اللي انرسلت ما تنحذف."


def should_hold(lid, day):
    """BLOCKING, for bot.py's three automatic turnover-room deletes: True = don't delete this
    room yet (live, gated, and that day's arrival still has no code). Never raises — on any
    error it answers False, i.e. today's behaviour.

    A FROZEN row (moved; a close on its old arrival still owed) holds neither unit: it is no
    longer the old unit's arrival, and it does not hold the new unit's room either, because
    defer_close could only attach that hold to the frozen row, where the move would treat it
    as the OLD hold and close it early. The window is bounded by the per-room delete cap
    (≤ DELETE_MAX_TRIES ticks); a new-unit room deleted by cleaning in it costs only a later
    code-only room (placement's normal fallback), never a wrong delete."""
    try:
        if not live() or not is_gated(lid):
            return False
        return any(not r.get("cancelled") and not r.get("released_at")
                   and not r.get("moving_to")
                   for r in db.items_for(lid, day))
    except Exception as e:
        print("[codegate] should_hold %s/%s failed, not holding: %s" % (lid, day, e))
        return False


def defer_close(lid, day, channel_id=None):
    """BLOCKING: the bot held this unit's turnover room instead of deleting it; codegate deletes
    it once the code is sent (or the booking is cancelled/moved, or the day is over). The room
    is remembered by its own id — `channel_id` when the bot passes it, else looked up now — so
    the close never depends on which room the card is in. Never raises.

    Returns True only when a hold was RECORDED. False (no waiting arrival — e.g. the code went
    out between should_hold and this call — or any error) tells the caller to delete the room
    exactly as it always did, so a room is never kept open with nobody owing its close."""
    try:
        rows = [r for r in db.items_for(lid, day)
                if not r.get("cancelled") and not r.get("moving_to")   # frozen: holds nothing
                and not r.get("released_at")]                          # code out: nothing owed
        if not rows:
            return False
        ch = channel_id
        if ch is None and HOST.find_room:
            try:
                ch = HOST.find_room(lid, day)
            except Exception as e:      # stored as "held, look it up at close time"
                print("[codegate] defer_close room lookup %s/%s failed: %s" % (lid, day, e))
                ch = None
        for r in rows:
            db.set_held(r["res_id"], ch)
            db.event(r["res_id"], "close_deferred", "", str(ch or ""))
        return True
    except Exception as e:
        print("[codegate] defer_close %s/%s failed: %s" % (lid, day, e))
        return False
