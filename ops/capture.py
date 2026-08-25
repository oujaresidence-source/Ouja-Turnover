# -*- coding: utf-8 -*-
"""
ops.capture — persist the two things «كرت التقييم» had nothing to read.

WHY THIS EXISTS
    «الاستجابة على وحداتك» is the biggest line on the scorecard at 25%, and it rendered
    «بيانات ناقصة» because nothing kept first-response times: the reply log was a 500-item
    deque and the escalation map was a dict that died on every restart. Both are now rows on
    disk.

THE ATTRIBUTION RULE (spec §A.1) — READ BEFORE CHANGING ANYTHING HERE
    A live !ouja-msgdump against the real account proved Hostaway CANNOT identify which human
    replied: every outgoing message carries sentUsingHostaway=0 and userId=null, because the
    team answers inside the Airbnb app. There is no field for it and there never will be.
    So this module NEVER looks at a sender. For a guest message on apartment X at time T, the
    responsible person is whoever the coverage calendar assigns X to on date(T) — the owner if
    working, the coverer if the owner is off. We measure whether YOUR units' guests were
    handled on YOUR watch, not who typed.

    Attribution is resolved ONCE, here, and frozen into the row. Re-deriving it at scoring
    time would silently rewrite history every time the roster changes.

SAFETY
    `on_conversation` runs inside the live guest-messaging path. Every public function in this
    file swallows everything: a bug here must never stop a guest from being answered. That is
    also why the whole layer has its own kill switch, OPS_CAPTURE_ENABLED=0.
"""

import datetime
import os

from . import db, engine
from .host import HOST

# date -> {listing_id: {"name":…, "did":…, "kind": "own"|"coverage"}}. One calendar
# resolution per date rather than per message; the backfill walks thousands of messages.
_attrib_cache = {}
_ATTRIB_CACHE_MAX = 400


def enabled():
    """The kill switch for the whole capture layer. Turning it off stops recording and
    nothing else — the scorecard line simply returns to «بيانات ناقصة»."""
    return (os.environ.get("OPS_CAPTURE_ENABLED", "1") or "1").strip() == "1"


def target_minutes():
    """First-reply target, in WORKING minutes."""
    try:
        return float((os.environ.get("OPS_RESPONSE_TARGET_MIN", "30") or "30").strip())
    except Exception:
        return 30.0


def _window():
    """The ONE work window: bot.py's constants, passed in at wire time. Never re-declared —
    a second copy of a business rule is a second thing to forget to change."""
    return {
        "work_start": int(getattr(HOST, "work_start_hour", None) or engine.WORK_START_DEFAULT),
        "work_end_hour": int(getattr(HOST, "work_end_hour", None) or engine.WORK_END_HOUR_DEFAULT),
        "work_end_min": int(getattr(HOST, "work_end_min", None)
                            if getattr(HOST, "work_end_min", None) is not None
                            else engine.WORK_END_MIN_DEFAULT),
    }


# ------------------------------------------------------------------ attribution

def invalidate(dates=None):
    """Drop cached attribution. Called from schedule.HOST.on_change after ANY coverage write,
    because this cache is what decides who gets warned — serving it stale means warning
    somebody who was recorded absent an hour ago. `dates` is advisory; clearing all is cheap
    and always correct."""
    if not dates:
        _attrib_cache.clear()
        return
    for d in dates:
        _attrib_cache.pop(str(d)[:10], None)
    # a range was passed (start, end) rather than every day in it — be safe
    if len(dates) == 2 and str(dates[0])[:10] != str(dates[1])[:10]:
        _attrib_cache.clear()


def attribution_for(day):
    """{listing_id -> {name, did, kind}} for ONE date, from the coverage calendar.

    `kind` is 'own' when the apartment's permanent owner was working, 'coverage' when
    somebody was standing in. Cached per date because the backfill resolves the same handful
    of dates thousands of times."""
    key = day.isoformat() if hasattr(day, "isoformat") else str(day)[:10]
    if key in _attrib_cache:
        return _attrib_cache[key]
    out = {}
    try:
        from schedule import routes as _sroutes
        board = _sroutes.schedule_day(key)
        for w in board.get("working") or []:
            for apt in (w.get("own") or []):
                if apt.get("listing_id"):
                    out[int(apt["listing_id"])] = {"name": w["name"], "kind": "own"}
            for entry in (w.get("coverage") or []):
                apt = entry.get("apartment") or {}
                if apt.get("listing_id"):
                    out[int(apt["listing_id"])] = {"name": w["name"], "kind": "coverage"}
    except Exception as e:
        print("[ops.capture] calendar unavailable for", key, e)
    for lid, rec in out.items():
        rec["did"] = _did_for(rec["name"])
    if len(_attrib_cache) >= _ATTRIB_CACHE_MAX:
        _attrib_cache.clear()
    _attrib_cache[key] = out
    return out


def clear_attribution_cache():
    _attrib_cache.clear()


def _did_for(name):
    try:
        from . import notify as _n
        return next((e["did"] for e in _n.employees() if e["name"] == name), "")
    except Exception:
        return ""


def responsible_for(listing_id, day):
    """Who was on the hook for this apartment on this date. Unknown apartment or a calendar
    we cannot read gives ('', '', 'unknown') — never a guess."""
    try:
        lid = int(listing_id)
    except (TypeError, ValueError):
        return "", "", "unknown"
    rec = attribution_for(day).get(lid)
    if not rec:
        return "", "", "unknown"
    return rec["name"], rec.get("did") or "", ("coverer" if rec["kind"] == "coverage" else "owner")


def match_person(claim_name):
    """Map a name typed in the escalation claim picker onto a calendar name.

    CLAIM_NAMES is a THIRD spelling of the same people — «ماثر» there vs «مآثر» in the
    calendar vs «ماذر» in assignments.json, «نوره» vs «نورة», «محمد» vs «محمد اليامي». An
    unmatched name is returned as-is and simply does not match the responsible person; it is
    never quietly attributed to somebody else."""
    if not (claim_name or "").strip():
        return ""
    try:
        from . import notify as _n
        want = _n._norm(_n._aliases().get(claim_name.strip(), claim_name))
        for e in _n.employees():
            en = _n._norm(e["name"])
            if en == want or en.startswith(want) or want.startswith(en):
                return e["name"]
    except Exception:
        pass
    return claim_name.strip()


# ------------------------------------------------------------------ response capture

def on_conversation(conversation_id, listing_id, unit, msgs, now=None):
    """Record every guest-wait in ONE conversation. Called from the existing scan, using the
    messages it has ALREADY fetched — no second poller, no second API client.

    Returns {written, completed, skipped}. Never raises: this runs in the live guest path."""
    out = {"written": 0, "completed": 0, "skipped": 0}
    if not enabled():
        return out
    try:
        pairs = engine.response_pairs(
            msgs,
            is_inbound=HOST.msg_is_inbound or (lambda m: False),
            msg_time=HOST.msg_time or (lambda m: ""),
            is_automated=HOST.msg_is_automated)
    except Exception as e:
        print("[ops.capture] pairing failed:", e)
        return out

    win = _window()
    for p in pairs:
        try:
            inc = p["incoming"]
            inc_id = str((inc or {}).get("id") or "")
            inc_at = p.get("incoming_at")
            if not inc_id or not inc_at:
                continue
            day = engine.as_date(str(inc_at).replace("T", " ")[:10])
            resp_at = p.get("responded_at")
            out_id = str(((p.get("outgoing") or {}) or {}).get("id") or "")

            mins_raw = mins_worked = None
            if resp_at:
                s, e = engine._as_dt(inc_at), engine._as_dt(resp_at)
                if s and e and e > s:
                    mins_raw = round((e - s).total_seconds() / 60.0, 2)
                    mins_worked = engine.worked_minutes(s, e, **win)
                else:
                    mins_raw = mins_worked = 0.0

            existing = db.response_event(conversation_id, inc_id)
            if existing:
                # A wait we already know about. Fill in the reply if it has just arrived —
                # and only if it is still blank, because the FIRST reply is the one scored.
                if resp_at and not (existing.get("responded_at") or ""):
                    db.complete_response_event(conversation_id, inc_id, out_id, resp_at,
                                               mins_raw, mins_worked)
                    out["completed"] += 1
                else:
                    out["skipped"] += 1
                continue

            name, did, how = responsible_for(listing_id, day)
            wrote = db.record_response_event({
                "conversation_id": conversation_id, "incoming_msg_id": inc_id,
                "outgoing_msg_id": out_id, "listing_id": listing_id, "unit": unit,
                "incoming_at": inc_at, "responded_at": resp_at,
                "minutes_raw": mins_raw, "minutes_worked": mins_worked,
                "responsible": name, "responsible_did": did, "attribution": how,
                "day_key": day.isoformat(), "month_key": engine.month_key(day),
            })
            out["written" if wrote else "skipped"] += 1
        except Exception as e:
            print("[ops.capture] event skipped:", e)
            out["skipped"] += 1
    return out


# ------------------------------------------------------------------ escalation capture

def on_escalation_opened(eid, unit, listing_id, opened_at=None, source="escalation"):
    """Record WHO WAS ON THE HOOK the moment an escalation opens."""
    if not enabled():
        return False
    try:
        opened_at = opened_at or db.now_iso()
        day = engine.as_date(str(opened_at).replace("T", " ")[:10])
        name, did, _how = responsible_for(listing_id, day)
        return db.record_escalation_event({
            "id": str(eid), "source": source, "unit": unit, "listing_id": listing_id,
            "opened_at": opened_at, "responsible": name, "responsible_did": did,
            "day_key": day.isoformat(), "month_key": engine.month_key(day)})
    except Exception as e:
        print("[ops.capture] escalation open not recorded:", e)
        return False


def on_escalation_taken(eid, claim_name, taken_at=None):
    """Record who actually stepped up. `taken_by_responsible` is the scorecard signal: did the
    person on the hook take it, or did a colleague cover for them?"""
    if not enabled():
        return False
    try:
        row = db.escalation_event(eid)
        if not row:
            return False
        who = match_person(claim_name)
        matched = bool(who) and who == (row.get("responsible") or "")
        db.take_escalation_event(eid, who, _did_for(who), matched, taken_at)
        return True
    except Exception as e:
        print("[ops.capture] escalation take not recorded:", e)
        return False


# ------------------------------------------------------------------ backfill

def backfill(days=30, fetch_conversations=None, fetch_messages=None, listings=None,
             pause=None, log=None):
    """Walk Hostaway conversation history and populate ops_response_events retroactively.

    Without this, the first August scorecard would be scored on three weeks of data and the
    25% line would still be thin. Idempotent by the UNIQUE key: running it twice writes
    nothing the second time and reports every event as a duplicate.

    The three fetchers are injected so this is testable with no network at all."""
    # `int(days or 30)` would swallow an explicit 0 and silently run a 30-day backfill.
    try:
        days = int(days) if days not in (None, "") else 30
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(90, days))
    fetch_conversations = fetch_conversations or HOST.fetch_conversations
    fetch_messages = fetch_messages or HOST.fetch_messages
    if not (fetch_conversations and fetch_messages):
        return {"ok": False, "error": "no Hostaway reader wired"}

    today = db.now_dt().date()
    cutoff = today - datetime.timedelta(days=days)
    rep = {"ok": True, "days": days, "since": cutoff.isoformat(), "conversations": 0,
           "written": 0, "completed": 0, "skipped": 0, "unresolved_days": set(), "errors": 0}
    lmap = listings or {}

    for c in (fetch_conversations(days) or []):
        cid = c.get("id")
        if not cid:
            continue
        rep["conversations"] += 1
        try:
            msgs = fetch_messages(cid) or []
        except Exception as e:
            print("[ops.capture] backfill messages failed for", cid, e)
            rep["errors"] += 1
            continue
        lid = c.get("listingMapId")
        unit = lmap.get(lid) or c.get("listingName") or ("unit-%s" % lid)
        r = on_conversation(cid, lid, unit, msgs)
        for k in ("written", "completed", "skipped"):
            rep[k] += r[k]
        if callable(pause):
            pause()
        if callable(log) and rep["conversations"] % 25 == 0:
            log(rep)

    # How much of the window the calendar could actually explain. If the roster was edited
    # during those weeks without the calendar being updated at the time, attribution for those
    # days is only as good as what the calendar says now — and the owner should know that
    # before trusting the first month.
    rows = db.response_events_since(cutoff.isoformat())
    rep["events_in_window"] = len(rows)
    rep["unattributed"] = sum(1 for r in rows if (r.get("attribution") or "unknown") == "unknown")
    rep.pop("unresolved_days", None)
    return rep
