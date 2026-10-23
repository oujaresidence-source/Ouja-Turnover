# -*- coding: utf-8 -*-
"""
rrdesk.study — the history study of RR rooms, READ-ONLY and pure.

The same analysis runs in three places, on the same message shape:
    * tools/rr_history_export.py --analyze   (offline, on a raw export)
    * the one-time study behind docs/rrdesk/history_study.md
    * /rrdesk-study and the monthly run inside the bot (bridge.collect_rooms feeds it)
It never writes to Discord. Its only write is store_suggestions(): «suggested» SLA numbers the
dashboard shows next to the current ones — NOTHING is ever auto-applied.

Message shape: {mid, who, whoid?, whoav?, isbot, at (ISO), txt, media, files, voice,
                ments (ids or '@names'), rep_who?/rep_whoid?, emb [text]}
"""

import datetime
import json
import re

from . import db, engine

NL = chr(10)

# ------------------------------------------------------------------ which rooms (brief §4.2)

_ROOM_PATTERNS = (re.compile(r"^rr-[0-9]"), re.compile(r"^مغلق[ةه]-rr-"),
                  re.compile(r"^ticket-[0-9]+"), re.compile(r"تعويض"),
                  re.compile(r"^rr-general$"), re.compile(r"^متابعه$"))
_PANELS = ("rr-tickets", "فتح-تذكرة-rr", "فتح-تذكرة")


def is_history_room(name, topic="", category=""):
    n = (name or "").strip().lower()
    if any(n.startswith(p) for p in _PANELS):
        return False
    cat = (category or "").strip()
    if "ouja-ticket:rr" in (topic or ""):
        return True
    rr_cat = cat == "RR" or cat.startswith("RR ")
    if rr_cat and not n.startswith("sp-"):
        return True
    if cat.startswith("📦 أرشيف") or cat == "Airbnb Requests" or not cat:
        return any(p.search(n) for p in _ROOM_PATTERNS)
    return False


# ------------------------------------------------------------------ request heuristics

_ASK_WORDS = ("send", "upload", "share", "provide", "need", "where", "can you", "could you",
              "please", "pls", "plz", "clarify", "what is", "what's", "whats", "any update",
              "update?", "waiting", "give me", "do we have", "is there", "check", "confirm",
              "who handles", "how much", "when", "did you", "have you", "let me know")
_NOT_ASK = ("thank", "thanks", "noted", "received", "got it", "done", "submitted", "ok", "okay",
            "perfect", "great", "approved", "paid", "closed")
_ASK_MAP = (("photo", "photos"), ("pic", "photos"), ("picture", "photos"), ("image", "photos"),
            ("video", "video"), ("invoice", "invoice"), ("quote", "quote"), ("quotation", "quote"),
            ("receipt", "receipt"), ("chat", "guest_chat"), ("conversation", "guest_chat"),
            ("screenshot", "airbnb_screens"), ("screen shot", "airbnb_screens"),
            ("report", "ops_report"), ("what is", "info"), ("clarify", "info"), ("how much", "info"),
            ("who", "info"), ("where", "info"))

_FOLLOWUP = ("following up", "folllowing up", "follow up", "followup", "any update", "any updates",
             "update on this", "hello", "hi", "sir")


def is_followup(text):
    """A nudge on an EARLIER ask (the clearest sign of being ignored): 'following up', 'any
    update', or a bare greeting / ping with nothing else in it."""
    t = " ".join((text or "").lower().replace("?", " ").replace("!", " ").split())
    if not t:
        return False
    if any(w in t for w in _FOLLOWUP[:7]):
        return True
    words = [w for w in t.split() if not w.startswith("@") and not w.startswith("<@")]
    return len(words) <= 2 and all(w in ("hello", "hi", "sir", "team", "pls", "please", "hey") for w in words)


URGENT_WORDS = ("urgent", "asap", "now", "today", "immediately", "deadline")
CONFUSION = ("what does this mean", "english please", "in english", "translate", "i don't understand",
             "i dont understand", "can't read", "cant read", "what is this")


def looks_like_request(text):
    t = " " + (text or "").lower().strip() + " "
    if engine.meaningful_letters(t) < 2 or is_followup(text):
        return False
    if any(t.strip() == w or t.strip().startswith(w + " ") for w in _NOT_ASK) and "?" not in t:
        return False
    if "?" in t:
        return True
    return any(w in t for w in _ASK_WORDS)


def guess_asks(text):
    t = (text or "").lower()
    out = [v for k, v in _ASK_MAP if k in t]
    return list(dict.fromkeys(out)) or ["other"]


# ------------------------------------------------------------------ identity helpers

def _id(m):
    return str(m.get("whoid") or m.get("whoav") or m.get("who") or "")


def _is_sam(m, sam):
    return (not m.get("isbot")) and (_id(m) in sam or (m.get("who") or "") in sam)


def _dt(s):
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(engine.oeng.tz())


def _has_file(m):
    return int(m.get("media") or 0) + int(m.get("files") or 0) > 0


# ------------------------------------------------------------------ the analysis

def analyze(rooms, sam_ids_or_names, now=None, team_names=None):
    """rooms: [{room:{id,name,cat}, msgs:[...]}]. Returns the study dict (no names of staff —
    callers redact before committing anything)."""
    now = now or datetime.datetime.now(engine.oeng.tz())
    sam = {str(x) for x in (sam_ids_or_names or []) if x}
    reqs, rooms_out = [], []
    lang = {"msgs_ar": 0, "msgs_en": 0, "confusion": 0}
    bot_kinds, voice = {}, 0
    sam_last_long = 0
    for r in rooms or []:
        msgs = [m for m in (r.get("msgs") or []) if _dt(m.get("at"))]
        msgs.sort(key=lambda m: _dt(m["at"]))
        has_sam = any(_is_sam(m, sam) for m in msgs)
        rooms_out.append({"name": (r.get("room") or {}).get("name"), "n": len(msgs), "sam": has_sam})
        for m in msgs:
            if m.get("isbot"):
                head = engine.normalize((m.get("txt") or "") or " ".join(m.get("emb") or []))[:28]
                if head:
                    bot_kinds[head] = bot_kinds.get(head, 0) + 1
                continue
            if m.get("voice"):
                voice += 1
            if has_sam:
                d = engine.direction(m.get("txt") or "")
                if d == "ar2en":
                    lang["msgs_ar"] += 1
                elif d == "en2ar":
                    lang["msgs_en"] += 1
                if _is_sam(m, sam) and any(c in (m.get("txt") or "").lower() for c in CONFUSION):
                    lang["confusion"] += 1
        human = [m for m in msgs if not m.get("isbot")]
        if human and _is_sam(human[-1], sam) and now - _dt(human[-1]["at"]) > datetime.timedelta(days=2):
            sam_last_long += 1
        pending = []
        for i, m in enumerate(msgs):
            if m.get("isbot"):
                continue
            if _is_sam(m, sam):
                if looks_like_request(m.get("txt")):
                    item = {"room": (r.get("room") or {}).get("name"), "at": _dt(m["at"]),
                            "text": (m.get("txt") or "")[:300], "asks": guess_asks(m.get("txt")),
                            "urgent": any(w in (m.get("txt") or "").lower() for w in URGENT_WORDS),
                            "reply_at": None, "reply_by": None, "deliver_at": None,
                            "deliver_by": None, "re_asked": False}
                    if pending and not any(p["reply_at"] for p in pending):
                        for p in pending:
                            p["re_asked"] = True
                    pending.append(item)
                    reqs.append(item)
                continue
            # a team message answers every pending ask; a file delivers the file asks
            for p in pending:
                if p["reply_at"] is None:
                    p["reply_at"], p["reply_by"] = _dt(m["at"]), m.get("who")
                if p["deliver_at"] is None:
                    file_ask = bool(set(p["asks"]) & engine.FILE_ASKS)
                    if (file_ask and _has_file(m)) or not file_ask:
                        p["deliver_at"], p["deliver_by"] = _dt(m["at"]), m.get("who")
            pending = [p for p in pending if p["deliver_at"] is None]
    for p in reqs:
        p["resp_wmin"] = engine.worked_minutes(p["at"], p["reply_at"]) if p["reply_at"] else None
        p["deliv_wmin"] = engine.worked_minutes(p["at"], p["deliver_at"]) if p["deliver_at"] else None
        p["resp_wall_h"] = round((p["reply_at"] - p["at"]).total_seconds() / 3600.0, 2) if p["reply_at"] else None
    resp = [p["resp_wmin"] for p in reqs if p["resp_wmin"] is not None]
    deliv = [p["deliv_wmin"] for p in reqs if p["deliv_wmin"] is not None]
    cal = engine.calibrate(resp, deliv)
    by_ask, by_person = {}, {}
    for p in reqs:
        for a in p["asks"]:
            by_ask.setdefault(a, []).append(p)
        if p["reply_by"]:
            by_person.setdefault(p["reply_by"], []).append(p)

    def dist(vals):
        v = [x for x in vals if x is not None]
        return {"n": len(v), "p50": _r(engine.percentile(v, 50)), "p60": _r(engine.percentile(v, 60)),
                "p75": _r(engine.percentile(v, 75)), "p90": _r(engine.percentile(v, 90))}
    times = [p["at"] for p in reqs]
    return {
        "rooms": len(rooms_out), "rooms_with_sam": sum(1 for x in rooms_out if x["sam"]),
        "messages": sum(x["n"] for x in rooms_out), "requests": len(reqs),
        "first": min(times).isoformat() if times else None,
        "last": max(times).isoformat() if times else None,
        "never_answered": sum(1 for p in reqs if p["reply_at"] is None),
        "waited_24wh": sum(1 for p in reqs if (p["resp_wmin"] or 0) > 24 * 60 or
                           (p["reply_at"] is None and engine.worked_minutes(p["at"], now) > 24 * 60)),
        "re_asked": sum(1 for p in reqs if p["re_asked"]),
        "sam_last_speaker_2d": sam_last_long,
        "voice": voice,
        "response_wmin": dist(resp), "delivery_wmin": dist(deliv),
        "response_wall_h": dist([p["resp_wall_h"] for p in reqs]),
        "by_ask": {a: {"n": len(v), "resp": dist([p["resp_wmin"] for p in v]),
                       "deliv": dist([p["deliv_wmin"] for p in v])} for a, v in sorted(by_ask.items())},
        "by_person": {k: {"n": len(v), "resp": dist([p["resp_wmin"] for p in v])}
                      for k, v in sorted(by_person.items())},
        "language": lang, "bot_kinds": dict(sorted(bot_kinds.items(), key=lambda kv: -kv[1])[:25]),
        "calibration": cal,
        "breach_at_default": {
            "resp": _share([x > 60 for x in resp]), "deliv": _share([x > 480 for x in deliv])},
        "_requests": reqs,
    }


def _r(v):
    return None if v is None else round(v, 1)


def _share(bools):
    b = list(bools)
    return round(sum(1 for x in b if x) / float(len(b)), 3) if b else None


def store_suggestions(rep):
    """The settings view shows these next to the live values. Nothing is auto-applied."""
    keep = {k: v for k, v in rep.items() if not k.startswith("_")}
    keep["at"] = db.iso(db.now())
    db.set_setting("study:last", json.dumps(keep, ensure_ascii=False, default=str), "study")
    return keep


def report_text(rep):
    c = rep.get("calibration") or {}
    r = rep.get("response_wmin") or {}
    return NL.join([
        "📊 دراسة غرف RR (قراءة فقط):",
        "• %d غرفة · %d رسالة · %d طلب من سام" % (rep.get("rooms", 0), rep.get("messages", 0),
                                                 rep.get("requests", 0)),
        "• ما أحد رد: %d · انتظر أكثر من ٢٤ ساعة عمل: %d · سام كرر الطلب: %d"
        % (rep.get("never_answered", 0), rep.get("waited_24wh", 0), rep.get("re_asked", 0)),
        "• وسيط أول رد: %s دقيقة عمل" % (r.get("p50") if r.get("p50") is not None else "—"),
        "• المقترح: رد خلال %s دقيقة، تسليم خلال %s ساعة (معروض في الإعدادات — ما يتطبق تلقائياً)"
        % (c.get("resp_min"), int((c.get("deliv_min") or 480) / 60)),
    ] + (["• فحص الاكتشاف على %s رسالة: الوضع المقترح %s (حد %s)"
          % ((rep.get("eval") or {}).get("n"), (rep.get("eval") or {}).get("mode"),
             (rep.get("eval") or {}).get("threshold"))] if rep.get("eval") else [])) + engine.INVISIBLE_MARK


# ------------------------------------------------------------------ redaction (PDPL)

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}")
_IBAN = re.compile(r"SA[0-9]{22}", re.I)
_PHONE = re.compile(r"(?:[+]?966|00966)[ 0-9]{8,12}|(?<![0-9])05[0-9]{8}(?![0-9])")
_NATID = re.compile(r"(?<![0-9])[12][0-9]{9}(?![0-9])")
_LONGNUM = re.compile(r"(?<![0-9,.])[0-9]{7,20}(?![0-9,.])")
_HM = re.compile(r"(?<![A-Za-z])HM[A-Za-z0-9]{8}(?![A-Za-z0-9])", re.I)
_GUEST_AR = re.compile(r"(الضيف)[ :]+[^·|،,]{2,40}?( ·| [|]|،|,)")
_GUEST_EN = re.compile(r"(Guest(?: name)?(?: [(]from PMS[)])?:)[^·|" + NL + r",]{1,60}")


def redact(text, names=None):
    """Strip personal data before anything is committed. `names` maps real staff names to role
    labels (Sam stays «Sam»). Guest names → «الضيف»; phones, emails, IBANs, national ids
    removed; HM codes → HMXXXX; long numbers (Hostaway / Discord ids) → RES-n."""
    t = str(text or "")
    t = _EMAIL.sub("[email]", t)
    t = _IBAN.sub("[iban]", t)
    t = _PHONE.sub("[phone]", t)
    t = _NATID.sub("[id]", t)
    t = _HM.sub("HMXXXX", t)
    seen = {}

    def res(m):
        seen.setdefault(m.group(0), "RES-%d" % (len(seen) + 1))
        return seen[m.group(0)]
    t = _LONGNUM.sub(res, t)
    t = _GUEST_AR.sub(lambda m: m.group(1) + " «الضيف»" + m.group(2), t)
    t = _GUEST_EN.sub(lambda m: m.group(1) + " «الضيف»", t)
    for real, label in sorted((names or {}).items(), key=lambda kv: -len(kv[0])):
        if real:
            t = t.replace(real, label)
    return t


PII_CHECKS = (("phone", _PHONE), ("national_id", _NATID), ("hm_code", re.compile(r"HM[A-Z0-9]{8}")),
              ("email", _EMAIL), ("iban", _IBAN))


def pii_hits(text):
    """[(kind, match)] — the structure test runs this over every committed fixture."""
    out = []
    for kind, rx in PII_CHECKS:
        for m in rx.finditer(str(text or "")):
            if kind == "hm_code" and m.group(0) == "HMXXXXXXXX":
                continue
            out.append((kind, m.group(0)))
    return out
