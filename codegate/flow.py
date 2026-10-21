# codegate/flow.py
# -*- coding: utf-8 -*-
"""
codegate.flow — the tick and the two buttons of «تسليم الرموز».

The bot LISTS, RECORDS and ALERTS. It never decides that a guest agreed and never sends a code:
a person reads the quoted reply, sends the code from Hostaway's saved reply, and presses
«✅ وافق وأرسلت الرمز».
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


def _buttons(it):
    if it.get("cancelled"):
        return []
    return ["undo"] if it.get("released_at") else ["release"]


async def _render(it, now_, channel_id, soak=False):
    """Post the card if it has none; edit it only when its content changed."""
    if it.get("cancelled") and not it.get("card_message_id"):
        return None                     # never had a card, never will
    view = _view_item(it)
    embed = engine.card(view, now_, soak=soak)
    h = engine.content_hash({"e": embed, "b": _buttons(it)})
    if not it.get("card_message_id"):
        mid = await HOST.post(channel_id, _mention(it) or None, embed=embed, buttons=_buttons(it))
        if mid:
            await run_blocking(db.set_card, it["res_id"], channel_id, mid, h)
            await run_blocking(db.event, it["res_id"], "card_posted")
            return "posted"
        return None
    if h != it.get("card_hash"):
        ok = await HOST.edit(it.get("channel_id") or channel_id, it["card_message_id"],
                             embed=embed, buttons=_buttons(it))
        if ok:
            await run_blocking(db.set_hash, it["res_id"], h)
            return "edited"
    return None


async def _prelive_check(it, now_, rep):
    """Go-live, ONCE per item: did Hostaway's auto-send already give this guest the code?
    Returns 'skip' (couldn't ask: no alert this tick, retry next), or None (decided: carry on —
    either released quietly, or genuinely no code so the normal alerts proceed)."""
    rid = it["res_id"]
    try:
        seen = await run_blocking(HOST.code_sent, it.get("conversation_id"))
    except Exception as e:      # Hostaway down ≠ "no code": say nothing, ask again next tick
        print("[codegate] pre-live check %s failed, retrying next tick: %s" % (rid, e))
        return "skip"
    stamp = now_.isoformat(timespec="seconds")
    if seen and await run_blocking(db.release, rid, PRELIVE_NAME, "", stamp):
        await run_blocking(db.set_code_seen, rid, True)     # nothing left for the honesty check
        await run_blocking(db.event, rid, "prelive_auto")
        rep["prelive"] += 1
    await run_blocking(db.set_prelive_checked, rid, stamp)
    return None


async def _process_item(it, now_, channel_id, rep, is_live=True, prelive_until=None):
    rid = it["res_id"]
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
    # SOAK: list and cards only. No honesty check, no alert, and nothing stamped, so both run
    # normally from the first tick after the switch is turned on.
    if not is_live:
        res = await _render(it, now_, channel_id, soak=True)
        if res:
            rep[res] += 1
        return
    # GO-LIVE: arrivals inside Doorcodera's window are looked at once before any alert.
    hold_alerts = False
    if (prelive_until is not None and not it.get("released_at") and not it.get("cancelled")
            and not it.get("prelive_checked_at")):
        ci = _dt(it.get("checkin_at"))
        if ci and ci <= prelive_until:
            hold_alerts = (await _prelive_check(it, now_, rep)) == "skip"
            it = await run_blocking(db.get, rid)
    # honesty check: pressed, but is the code really in the chat?
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
                await HOST.post(channel_id, (who + " " if who else "") +
                                "⚠️ ضُغط الزر على **%s** بس ما شفت رسالة الرمز في "
                                "المحادثة — تأكد إنها انرسلت." % (it.get("unit") or ""))
                await run_blocking(db.stamp, rid, "code_warned_at",
                                   now_.isoformat(timespec="seconds"))
                rep["warned"] += 1
            it = await run_blocking(db.get, rid)
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
            await HOST.post(channel_id, text)
            await HOST.escalate(("🔑 باقي ساعتين وما أُرسل الرمز · " if kind == "2h"
                                 else "🚨 حلّ الدخول وما أُرسل الرمز · ") + (it.get("unit") or ""),
                                text)
            await run_blocking(db.event, rid, "alert_" + kind)
            rep["alerts"] += 1
    it = await run_blocking(db.get, rid)        # never repaint from a stale copy
    res = await _render(it, now_, channel_id)
    if res:
        rep[res] += 1


def _prelive_until():
    """live_since + 3 h, or None when no go-live moment is stored (then nothing is pre-checked)."""
    try:
        ls = _dt(db.get_setting("live_since"))
    except Exception as e:
        print("[codegate] live_since unreadable: %s" % e)
        return None
    return ls + datetime.timedelta(hours=PRELIVE_WINDOW_H) if ls else None


async def tick(now_=None, force=False):
    if not enabled():
        return {"skipped": "off"}
    async with _lock("tick"):
        now_ = now_ or HOST.now()
        day = now_.date().isoformat()
        is_live = await run_blocking(live)
        rep = {"live": int(is_live), "seen": 0, "posted": 0, "edited": 0, "alerts": 0,
               "headers": 0, "cancelled": 0, "warned": 0, "prelive": 0}
        gated = await run_blocking(units)
        # the tick's OWN day, so a tick that straddles midnight can't mix two days
        arrivals = await run_blocking(HOST.today_arrivals, day) or []
        keep = set()
        for a in arrivals:
            if str(a.get("day")) != day or not is_gated(a.get("lid")):
                continue
            try:
                cov = await run_blocking(HOST.cover, a["lid"], day) or {}
            except Exception as e:
                print("[codegate] cover lookup failed for %s: %s" % (a.get("res_id"), e))
                cov = {}
            prev = await run_blocking(db.get, str(a["res_id"]))
            if prev and prev.get("day") != day:
                # moved from another date: db.upsert_arrival starts its card/alerts over
                await run_blocking(db.event, str(a["res_id"]), "moved", "",
                                   "%s → %s" % (prev.get("day"), day))
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
        rep["seen"] = len(keep)
        rep["cancelled"] = len(await run_blocking(db.mark_cancelled, day, keep))
        if not gated or (not force and now_.hour < engine.START_HOUR):
            return rep
        channel_id = await HOST.channel()
        items = await run_blocking(db.day_items, day)
        # one header per person, before their first card
        groups = {}
        for it in items:
            if not it.get("cancelled"):
                k = it.get("cover_did") or it.get("cover_role_id") or it.get("cover_name") or "ops"
                groups.setdefault(k, []).append(it)
        for k, rows in groups.items():
            try:
                if await run_blocking(db.header_posted, day, k):
                    continue
                mid = await HOST.post(channel_id, engine.header_text(_mention(rows[0]),
                                                                     rows[0].get("cover_name"),
                                                                     len(rows)))
                if mid:                 # a failed post is retried on the next tick
                    await run_blocking(db.mark_header, day, k, mid)
                    rep["headers"] += 1
            except Exception as e:
                print("[codegate] header %s failed: %s" % (k, e))
        prelive_until = await run_blocking(_prelive_until) if is_live else None
        for it in items:
            try:
                await _process_item(it, now_, channel_id, rep, is_live=is_live,
                                    prelive_until=prelive_until)
            except Exception as e:
                print("[codegate] item %s failed: %s" % (it.get("res_id"), e))
        return rep


async def _rerender(res_id):
    it = await run_blocking(db.get, res_id)
    if it:
        await _render(it, HOST.now(), it.get("channel_id"),
                      soak=not await run_blocking(live))


async def press_release(message_id, presser):
    it = await run_blocking(db.item_by_message, message_id)
    if not it:
        return False, "ما لقيت هذا الحجز في السجل."
    if it.get("cancelled"):
        return False, "الحجز ملغي — ما يحتاج رمز."
    if it.get("released_at"):
        return False, "أُرسل من قبل — %s %s" % (it.get("released_by") or "",
                                                str(it["released_at"])[11:16])
    if not engine.may_release(presser.get("did"), it.get("cover_did"), it.get("owner_did"),
                              presser.get("is_admin"), presser.get("is_ops")):
        return False, "هذي الشقة على %s اليوم — هو أو المشرف يضغط الزر." % (
            it.get("cover_name") or "فريق العمليات")
    now_ = HOST.now().isoformat(timespec="seconds")
    if not await run_blocking(db.release, it["res_id"], presser.get("name") or "",
                              presser.get("did") or "", now_):
        fresh = await run_blocking(db.get, it["res_id"])
        return False, "أُرسل من قبل — %s" % ((fresh or {}).get("released_by") or "")
    await run_blocking(db.event, it["res_id"], "released", presser.get("name") or "")
    await _rerender(it["res_id"])
    return True, "تم ✅ — سجّلت إنك أرسلت الرمز."


async def press_undo(message_id, presser):
    if not presser.get("is_admin"):
        return False, "التراجع للمشرفين فقط."
    it = await run_blocking(db.item_by_message, message_id)
    if not it or not it.get("released_at"):
        return False, "ما فيه تسليم أتراجع عنه."
    await run_blocking(db.undo, it["res_id"], presser.get("name") or "",
                       HOST.now().isoformat(timespec="seconds"))
    await run_blocking(db.event, it["res_id"], "undone", presser.get("name") or "")
    await _rerender(it["res_id"])
    return True, "تم التراجع — رجعت البطاقة بانتظار التسليم."
