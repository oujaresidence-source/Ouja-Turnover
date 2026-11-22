# -*- coding: utf-8 -*-
"""
hatif.service — one inbound WhatsApp message → at most one answer. Blocking; the webhook
route runs it in the background after acknowledging Hatif with 200.

handle(payload) returns {"outcome": ...}:
    ignored     not an inbound typed text on our channel (our own messages, taps, media)
    duplicate   this delivery was already handled
    observed    listen-only (no API credentials): the would-be reply went to Discord
    not_ours    the conversation is not assigned to the bot seat — the bot stays silent
    dryrun      would have answered; nothing sent (HATIF_DRYRUN=1 or number not allowlisted)
    sent        answered on WhatsApp, conversation handed back to the menu
    help        dates unreadable — asked the guest to write them again
    handoff     dates unreadable twice, or a monthly request — given to a person
    throttled   over HATIF_MAX_PER_MIN — silent, protects Hostaway
    error       something failed; reported once on Discord, never raised
"""
import collections
import threading
import time
import traceback

from . import answers, brain, client, config, db, engine, parse
from .host import HOST

_rate_lock = threading.Lock()
_recent = collections.deque()


_ai_lock = threading.Lock()
_ai_recent = collections.deque()
_catalog = {"at": 0.0, "units": []}


def reset_for_tests():
    with _rate_lock:
        _recent.clear()
    with _ai_lock:
        _ai_recent.clear()
    _catalog.update(at=0.0, units=[])


def _allow_now():
    cap = config.max_per_min()
    now = time.time()
    with _rate_lock:
        while _recent and now - _recent[0] > 60:
            _recent.popleft()
        if len(_recent) >= cap:
            return False
        _recent.append(now)
        return True


def _notify(text):
    fn = getattr(HOST, "notify", None)
    if fn:
        try:
            fn(str(text)[:1900])
        except Exception:
            traceback.print_exc()


def _today():
    d = HOST.require("now")()
    return d.date() if hasattr(d, "date") else d


def _hoods():
    fn = getattr(HOST, "neighborhoods", None)
    try:
        return fn() if fn else []
    except Exception:
        return []


def _site():
    fn = getattr(HOST, "site_host", None)
    try:
        return (fn() if fn else "") or "oujares.com"
    except Exception:
        return "oujares.com"


def _answer(req):
    out = HOST.require("search")(req["check_in"], req["check_out"], req.get("guests"),
                                 req.get("type"), req.get("neighborhood"))
    return engine.build_reply(req, out, _site(), config.max_units())


def _report(tag, shown, reply):
    _notify("📲 هاتف — %s\nرسالة الضيف: «%s»\n— الرد —\n%s" % (tag, shown, reply))


def handle(p):
    try:
        return _handle(p if isinstance(p, dict) else {})
    except Exception as e:                     # never let a webhook job die loudly
        traceback.print_exc()
        return {"outcome": "error", "error": type(e).__name__}


def _handle(p):
    if not config.enabled():
        return {"outcome": "ignored"}
    body = str(p.get("body") or "").strip()
    if (p.get("direction") != "Inbound" or p.get("messageType") != "Text"
            or p.get("interactiveReply") or not body):
        return {"outcome": "ignored"}
    ch = config.channel_id()
    if ch and str(p.get("channelId") or "") != ch:
        return {"outcome": "ignored"}
    eid = p.get("conversationEventId") or p.get("messageId")
    cid = p.get("conversationId")
    if not eid or not cid:
        return {"outcome": "ignored"}

    shown = engine.mask(body)
    req = parse.parse_request(body, _today(), _hoods(), config.max_nights())

    # ---- listen-only: no API credentials yet. Show what we WOULD say, on Discord only. ----
    if not config.configured():
        if not req.get("ok"):
            return {"outcome": "ignored"}
        if not db.claim(eid, cid, shown):
            return {"outcome": "duplicate"}
        if not _allow_now():
            db.finish(eid, "throttled", req)
            return {"outcome": "throttled"}
        reply = _answer(req)
        db.finish(eid, "observed", req, reply)
        _report("استماع فقط، ما انرسل شي للضيف", shown, reply)
        return {"outcome": "observed", "reply": reply}

    if not db.claim(eid, cid, shown):
        return {"outcome": "duplicate"}

    def done(outcome, reply=None, error=None):
        db.finish(eid, outcome, req, reply, error)
        return {"outcome": outcome, "reply": reply}

    try:
        conv = client.get_conversation(cid)
    except client.HatifError as e:
        _notify("⚠️ هاتف: تعذر قراءة المحادثة من Hatif (%s)" % e)
        return done("error", error=e)

    assignee = conv.get("assigneeId")
    bot_seat = config.bot_user_id()
    if config.gate() == "assigned":
        if not bot_seat or assignee != bot_seat:
            return done("not_ours")
    else:
        if (assignee and assignee != bot_seat) or conv.get("isAiAssignee") or not req.get("ok"):
            return done("not_ours")

    phone = engine.normalize_phone(conv.get("phoneNumber"))
    allow = config.test_numbers()
    live = bool(phone) and not config.dryrun() and (not allow or phone in allow)
    channel = str(p.get("channelId") or conv.get("channelId") or ch)
    held = "تجربة، ما انرسل شي للضيف"

    def say(text):
        client.send_text(channel, phone, text)

    def give_back(to_user=None):
        if config.gate() == "assigned" and (to_user or config.release_after_reply()):
            client.assign(cid, to_user or None)

    try:
        # ---- the dates could not be read ----
        if not req.get("ok"):
            reason = req.get("reason") or "no_dates"
            text = engine.help_text(reason)
            fails = 1 if reason == "monthly" else db.bump_fail(cid)
            to_person = reason == "monthly" or fails >= 2
            if not live:
                _report(held + (" — كان بيتحول لموظف" if to_person else ""), shown, text)
                return done("dryrun", text)
            if to_person:
                say(text if reason == "monthly" else engine.HANDOFF)
                client.assign(cid, config.human_user_id() or None)
                db.clear_fail(cid)
                _notify("🤝 هاتف: محادثة تحولت لموظف (%s). رسالة الضيف: «%s»"
                        % ("طلب شهري" if reason == "monthly" else "ما قدرت أفهم التواريخ", shown))
                return done("handoff", text)
            say(text)
            return done("help", text)

        # ---- a readable request ----
        if not _allow_now():
            return done("throttled")
        if live and config.ack():
            try:
                say(engine.ACK)
            except client.HatifError:
                pass                              # the real answer still goes out below
        reply = _answer(req)
        if not live:
            _report(held, shown, reply)
            return done("dryrun", reply)
        say(reply)
        db.clear_fail(cid)
        try:
            give_back()
        except client.HatifError as e:
            _notify("⚠️ هاتف: انرسل الرد لكن تعذر إرجاع المحادثة للقائمة (%s)" % e)
        return done("sent", reply)
    except client.HatifError as e:
        _notify("⚠️ هاتف: تعذر إرسال الرد للضيف (%s). رسالة الضيف: «%s»" % (e, shown))
        return done("error", error=e)


# ============ the WhatsApp «reader» — Phase 1: SILENT (never sends, never assigns) ============

def _ai_allow_now():
    cap = config.ai_max_per_min()
    now = time.time()
    with _ai_lock:
        while _ai_recent and now - _ai_recent[0] > 60:
            _ai_recent.popleft()
        if len(_ai_recent) >= cap:
            return False
        _ai_recent.append(now)
        return True


def _units():
    """Browse-mode catalogue (names, area, map pin) — no availability claims. Cached 10 min."""
    if time.time() - _catalog["at"] < 600 and _catalog["units"]:
        return _catalog["units"]
    fn = getattr(HOST, "catalog", None)
    try:
        units = list(fn() or []) if fn else []
    except Exception:
        traceback.print_exc()
        units = []
    if units:
        _catalog.update(at=time.time(), units=units)
    return units


def shadow(p):
    """Read one typed guest message, compose the reply the reader WOULD send, post it to
    Discord. Sends nothing to the guest and never touches the conversation. Never raises."""
    try:
        return _shadow(p if isinstance(p, dict) else {})
    except Exception as e:
        traceback.print_exc()
        return {"outcome": "error", "error": type(e).__name__}


def _shadow(p):
    if not (config.enabled() and config.ai_enabled()):
        return {"outcome": "ignored"}
    body = str(p.get("body") or "").strip()
    if (p.get("direction") != "Inbound" or p.get("messageType") != "Text"
            or p.get("interactiveReply") or not body):
        return {"outcome": "ignored"}
    ch = config.channel_id()
    if ch and str(p.get("channelId") or "") != ch:
        return {"outcome": "ignored"}
    eid = p.get("conversationEventId") or p.get("messageId")
    if not eid:
        return {"outcome": "ignored"}
    classify = getattr(HOST, "classify", None)
    if classify is None:
        return {"outcome": "ignored"}
    shown = engine.mask(body)
    if not db.ai_claim(eid, shown):
        return {"outcome": "duplicate"}
    if not _ai_allow_now():
        db.ai_finish(eid, "throttled")
        return {"outcome": "throttled"}
    bank = answers.bank()
    decision = brain.decide(body, classify, bank)
    composed = brain.compose(body, _today(), _hoods(), decision, bank, _units(),
                             HOST.require("search"), _site(), config.max_units(), config.max_nights())
    db.ai_finish(eid, composed["door"], composed["reply"], composed["violations"])
    if composed["door"] == "menu":
        return {"outcome": "menu"}
    head = "🧪 قارئ الواتساب (صامت، ما انرسل شي)"
    why = brain.explain(decision, composed)
    lines = [head, "الضيف: «%s»" % shown, "القرار: " + why]
    if decision.get("summary_ar"):
        lines.append("للموظف: " + engine.mask(decision["summary_ar"], 200))
    if composed["violations"]:
        lines.append("⛔ انحجز الرد: " + "، ".join(composed["violations"]))
    lines += ["— كان بيرد —", composed["reply"] or "(لا شي)"]
    fn = getattr(HOST, "notify_reader", None) or getattr(HOST, "notify", None)
    if fn:
        try:
            fn("\n".join(lines)[:1900])
        except Exception:
            traceback.print_exc()
    return {"outcome": "shadow", "door": composed["door"], "reply": composed["reply"],
            "violations": composed["violations"]}


def status():
    return {
        "enabled": config.enabled(), "configured": config.configured(), "dryrun": config.dryrun(),
        "gate": config.gate(), "webhook_secret_set": bool(config.webhook_secret()),
        "channel_set": bool(config.channel_id()), "bot_seat_set": bool(config.bot_user_id()),
        "human_seat_set": bool(config.human_user_id()), "test_numbers": len(config.test_numbers()),
        "ack": config.ack(), "max_per_min": config.max_per_min(), "events": db.recent(30),
        "reader": {"enabled": config.ai_enabled(), "mode": "silent",
                   "max_per_min": config.ai_max_per_min(), "events": db.ai_recent(30)},
    }
