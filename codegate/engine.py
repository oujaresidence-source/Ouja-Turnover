# codegate/engine.py
# -*- coding: utf-8 -*-
"""
codegate.engine — PURE. Every decision and every word of «تسليم الرموز».

The owner's rule (2026-10-21): a HUMAN releases the door code after the guest writes «أوافق».
So nothing here decides whether a reply is agreement — replies are quoted word for word — and
nothing here ever sees a code. No I/O except load_units (two small JSON files).
"""

import hashlib
import json
import os
import unicodedata
from datetime import timedelta
from zoneinfo import ZoneInfo

MARKERS = ("i agree to the house rules", "أوافق على قواعد الشقة")
ALERT_LEAD_MIN = 120
CODE_CHECK_MIN = 15
START_HOUR = 9
MAX_QUOTES = 3
QUOTE_CHARS = 300

LABEL_RELEASE = "✅ وافق وأرسلت الرمز"
LABEL_UNDO = "↩️ تراجع"
CONFIRM_TEXT = "الضيف كتب «أوافق» في المحادثة، وأرسلت له الرمز من Hostaway؟"

COLOR_WAIT = 0xC9A227    # the dashboard gold
COLOR_DONE = 0x2E8B57
COLOR_ALERT = 0xD64545
COLOR_OFF = 0x8A8580

_AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def tz():
    return ZoneInfo("Asia/Riyadh")


def _ids(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {int(x) for x in (raw.get("listing_ids") or [])}


def load_units(repo_path, state_path):
    """The gated listing ids. A readable $STATE_DIR copy wins; a broken one is ignored (the
    repo seed keeps serving) — the decor_packs.json rule."""
    for p in (state_path, repo_path):
        if p and os.path.exists(p):
            try:
                return _ids(p)
            except Exception as e:
                print("[codegate] unit list unreadable (%s): %s" % (p, e))
    return set()


def _fold(s):
    return unicodedata.normalize("NFKC", str(s or "")).casefold()


def is_rules_message(body):
    low = _fold(body)
    return any(_fold(m) in low for m in MARKERS)


def _key(m):
    a = m.get("at")
    return (a is None, a.timestamp() if a is not None else 0)


def _clip(text):
    t = " ".join(str(text or "").split())
    return t if len(t) <= QUOTE_CHARS else t[:QUOTE_CHARS] + "…"


def guest_replies(messages):
    """The guest's words since our LATEST house-rules message (inbound only — our own message
    contains the very words "I agree to the house rules"). No rules message → the last few
    inbound messages, and rules_at None so the card can say so."""
    ordered = sorted(messages or [], key=_key)
    found, rules_at, start = False, None, 0
    for i, m in enumerate(ordered):
        if not m.get("inbound") and is_rules_message(m.get("body")):
            found, rules_at, start = True, m.get("at"), i + 1
    pool = ordered[start:] if found else ordered
    inbound = [m for m in pool if m.get("inbound") and str(m.get("body") or "").strip()]
    return {"rules_at": rules_at,
            "replies": [{"at": m.get("at"), "text": _clip(m.get("body"))}
                        for m in inbound[-MAX_QUOTES:]]}


def alert_due(item, now):
    if item.get("released_at") or item.get("cancelled"):
        return None
    ci = item["checkin_at"]
    if now >= ci:
        return None if item.get("alert_late_at") else "late"
    if now >= ci - timedelta(minutes=ALERT_LEAD_MIN) and not item.get("alert_2h_at"):
        return "2h"
    return None


def may_release(presser_did, cover_did, owner_did, is_admin, is_ops):
    if is_admin or is_ops:
        return True
    p = str(presser_did or "")
    return bool(p) and p in {str(cover_did or ""), str(owner_did or "")} - {""}


def _hhmm(v):
    if not v:
        return ""
    if isinstance(v, str):
        return v[11:16]
    return v.strftime("%H:%M")


def ar_num(n):
    return str(n).translate(_AR_DIGITS)


def card(item, now):
    replies = item.get("replies") or []
    if replies:
        quoted = "\n".join("> " + r["text"] + ("  · " + _hhmm(r.get("at")) if r.get("at") else "")
                           for r in replies)
    else:
        quoted = "لا يوجد رد بعد ⏳"
    rules = ("وصلت للضيف ✅ " + _hhmm(item.get("rules_at"))) if item.get("rules_at") \
        else "ما لقيت رسالة القواعد في المحادثة ⚠️"
    if item.get("cancelled"):
        status, color = "🚫 الحجز ملغي", COLOR_OFF
    elif item.get("released_at"):
        status = "أُرسل الرمز ✅ — %s %s" % (item.get("released_by") or "", _hhmm(item["released_at"]))
        color = COLOR_DONE
    elif item.get("alert_2h_at") or item.get("alert_late_at"):
        status, color = "⏰ متأخر — ما أُرسل الرمز بعد", COLOR_ALERT
    else:
        status, color = "⏳ بانتظار «أوافق» ثم إرسال الرمز", COLOR_WAIT
    fields = [
        {"name": "الدخول", "value": _hhmm(item.get("checkin_at")) or "—", "inline": True},
        {"name": "المسؤول اليوم", "value": item.get("cover_name") or "— (فريق العمليات)",
         "inline": True},
        {"name": "رسالة القواعد", "value": rules, "inline": False},
        {"name": "ردود الضيف (حرفياً)", "value": quoted[:1024], "inline": False},
        {"name": "الحالة", "value": status, "inline": False},
    ]
    if item.get("code_warned_at"):
        fields.append({"name": "⚠️ تنبيه", "inline": False,
                       "value": "ضُغط الزر بس ما شفت رسالة الرمز في المحادثة — تأكد إنها انرسلت."})
    return {"title": "🔑 %s — %s" % (item.get("unit") or "", item.get("guest") or ""),
            "description": "الرمز يُرسل بعد ما يكتب الضيف «أوافق» في المحادثة — "
                           "استخدم الرد الجاهز «🔑 كود الدخول» في Hostaway.",
            "color": color, "fields": fields,
            "footer": {"text": "تسليم الرموز · البوت ما يقرّر الموافقة ولا يرسل الرمز"}}


def header_text(mention, name, n):
    who = mention or name or "فريق العمليات"
    return "🔑 %s — عندك %s وصول اليوم يحتاج «أوافق» قبل الرمز." % (who, ar_num(n))


def alert_text(kind, item, mention):
    base = "**%s** — %s · الدخول %s" % (item.get("unit") or "", item.get("guest") or "",
                                        _hhmm(item.get("checkin_at")))
    if kind == "2h":
        head = "⏰ باقي ساعتين على الدخول وما أُرسل الرمز."
    else:
        head = "🚨 حلّ موعد الدخول وما أُرسل الرمز."
    tail = "اقرأ رد الضيف؛ لو ما رد اتصل فيه واطلب منه يكتب «أوافق» في المحادثة، ثم أرسل الرمز."
    return " ".join(x for x in (mention, head) if x) + "\n" + base + "\n" + tail


def content_hash(embed):
    return hashlib.sha1(json.dumps(embed, ensure_ascii=False, sort_keys=True)
                        .encode("utf-8")).hexdigest()
