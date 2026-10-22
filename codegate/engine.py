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
import re
import unicodedata
from datetime import timedelta
from zoneinfo import ZoneInfo

MARKERS = ("i agree to the house rules", "أوافق على قواعد الشقة")
ALERT_LEAD_MIN = 120
CODE_CHECK_MIN = 15
START_HOUR = 9
MAX_QUOTES = 3
QUOTE_CHARS = 300

LABEL_SEND = "✅ وافق — أرسل الرمز"
LABEL_MANUAL = "📝 أرسلته يدوياً"
LABEL_UNDO = "↩️ تراجع"
LABEL_RELEASE = "✅ وافق وأرسلت الرمز"   # deprecated, OLD text: bot.py hardcodes it; R3 removes
CONFIRM_SEND = "يرسل البوت الرمز للضيف الحين من Hostaway. متأكد إنه كتب «أوافق»؟"
CONFIRM_SEND_UNCLEAR = ("⚠️ ما لقيت «أوافق» واضحة في ردوده. لو قرأت ردّه وتأكدت إنه موافق، كمّل — "
                        "غير كذا اطلب منه يكتبها أول.")
CONFIRM_MANUAL = "سجّل إنك أرسلت الرمز بنفسك من Hostaway؟"
CONFIRM_TEXT = "الضيف كتب «أوافق» في المحادثة، وأرسلت له الرمز من Hostaway؟"  # deprecated, OLD text: R3 removes
VERDICT_LABEL = {"yes": "✅ كتب «أوافق»", "unclear": "⚠️ رد بس مو واضح", "none": "⏳ ما رد بعد"}

_AGREE_TOKENS = frozenset(("أوافق", "اوافق", "نوافق", "موافق", "موافقه", "موافقة", "موافقين",
                           "موافقون", "agree", "agreed"))
_NEGATIONS = frozenset(("ما", "لا", "مو", "مب", "مش", "غير", "no", "not", "never", "disagree",
                        "dont", "cant", "cannot", "wont", "wouldnt", "doesnt", "isnt"))
# "no problem, I agree" is agreement, so these idioms are removed before negations are looked for
_IDIOMS = ("ما عندنا اعتراض", "ما عندي مشكلة", "ما فيه مشكلة", "لا مشكلة", "لا بأس", "لا تقلق",
           "no problem", "no worries")
_QUESTION_WORDS = frozenset(("هل", "وش", "ايش", "إيش", "شنو", "ليش", "what", "do", "does", "how",
                             "why"))
_NEG_WINDOW = 2   # a negation only counts within this many words right before the agree word
_WORD = re.compile(r"[\w']+")
_MARKS = re.compile("[\u0640\u064B-\u065F\u0670\u06D6-\u06ED]")

HOSTAWAY_RES_URL = "https://dashboard.hostaway.com/reservations/%s"
SOAK_NAME = "🧪 وضع التجربة"
SOAK_TEXT = "الرمز يُرسل تلقائياً من Hostaway حالياً — لا تحتاج تضغط الزر."
TITLE_MAX = 256

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


_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
_REPEATS = re.compile(r"(\w)\1{2,}")
_ATTRIBUTION = re.compile(r"\bon\b[^\n]{0,120}?\bwrote\s*:|في[^\n]{0,120}?\d[^\n]{0,60}?كتب")
_QUOTE_MARK = re.compile(r"(?:^|\s)>")


def _own_text(text):
    """Only what the guest typed: no invisible characters, no marks, and none of the quoted
    copy of our own message that an email reply carries."""
    t = _MARKS.sub("", _INVISIBLE.sub("", _fold(text)))
    t = t.replace("_", " ").replace("\u2019", "'")
    t = "\n".join(ln for ln in t.split("\n") if not ln.lstrip().startswith(">"))
    m = _ATTRIBUTION.search(t)
    if m:
        t = t[:m.start()]
    return _QUOTE_MARK.split(t)[0]       # replies arrive flattened to one line


def _words(text):
    words = _WORD.findall(_REPEATS.sub(r"\1", text))
    flat = " " + " ".join(words) + " "
    for idiom in _IDIOMS:
        flat = flat.replace(" %s " % idiom, "  ")
    return flat.split()


def _squash(w):
    return re.sub(r"(.)\1+", r"\1", w)     # "agreeeee" and "agree" both become "agre"


_AGREE_SQUASHED = frozenset(_squash(t) for t in _AGREE_TOKENS)


def _is_agree(w):
    w = _squash(w)
    return w in _AGREE_SQUASHED or (w[:1] in ("و", "ف") and w[1:] in _AGREE_SQUASHED)


def _is_negation(w):
    return w in _NEGATIONS or w.endswith("n't")


def _is_question(text, words):
    return "?" in text or "؟" in text or bool(words) and words[0] in _QUESTION_WORDS


def _reply_state(text):
    """None (no agree word) | "yes" | "no" (negated, or asked as a question)."""
    t = _own_text(text)
    words = _words(t)
    hits = [i for i, w in enumerate(words) if _is_agree(w)]
    if not hits:
        return None
    i = hits[-1]
    if _is_question(t, words) or any(_is_negation(w) for w in words[max(0, i - _NEG_WINDOW):i]):
        return "no"
    return "yes"


def agree_verdict(replies):
    """"yes" | "unclear" | "none". Only a HINT for the staff member who reads the replies and
    presses the button, so a false "yes" must be rare. The LATEST reply that mentions agreeing
    decides; it is "yes" only when it is not negated, not a question, and not just our own
    message quoted back."""
    if not replies:
        return "none"
    for r in reversed(replies):
        state = _reply_state(r.get("text"))
        if state:
            return "yes" if state == "yes" else "unclear"
    return "unclear"


def code_message(code):
    """The '#' stays glued to the digits: the watchdog and the honesty check both look for
    'digits#' to recognise a sent code."""
    c = re.sub(r"\s+", "", str(code if code is not None else "")).rstrip("#")
    if not c:
        raise ValueError("code_message needs a door code")
    return ("🔑 كود الدخول: %s#\n"
            "(اكتب الرقم ثم اضغط #) — يشتغل من وقت الدخول، ولو احتجت أي شي حنا هنا 🤍\n\n"
            "🔑 Door code: %s#\n"
            "(enter the digits, then press #) — works from check-in time; "
            "anything you need, we're right here 🤍") % (c, c)


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


def card(item, now, soak=False):
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
    elif item.get("alert_late_at"):
        status, color = "🚨 متأخر — حلّ الدخول وما أُرسل الرمز", COLOR_ALERT
    elif item.get("alert_2h_at"):
        status, color = "⏰ قرب الدخول — ما أُرسل الرمز بعد", COLOR_ALERT
    else:
        status, color = "⏳ بانتظار «أوافق» ثم إرسال الرمز", COLOR_WAIT
    fields = [
        {"name": "الدخول", "value": _hhmm(item.get("checkin_at")) or "—", "inline": True},
        {"name": "المسؤول اليوم", "value": item.get("cover_name") or "— (فريق العمليات)",
         "inline": True},
        {"name": "رسالة القواعد", "value": rules, "inline": False},
        {"name": "ما كتبه الضيف", "value": VERDICT_LABEL[agree_verdict(replies)], "inline": False},
        {"name": "ردود الضيف (حرفياً)", "value": quoted[:1024], "inline": False},
        {"name": "الحالة", "value": status, "inline": False},
    ]
    if item.get("res_id"):
        fields.append({"name": "المحادثة", "inline": False,
                       "value": "[افتح الحجز في Hostaway](%s)"
                                % (HOSTAWAY_RES_URL % item["res_id"])})
    if item.get("code_warned_at"):
        fields.append({"name": "⚠️ تنبيه", "inline": False,
                       "value": "ضُغط الزر بس ما شفت رسالة الرمز في المحادثة — تأكد إنها انرسلت."})
    if soak:
        fields.append({"name": SOAK_NAME, "value": SOAK_TEXT, "inline": False})
    title = "🔑 %s — %s" % (item.get("unit") or "", item.get("guest") or "")
    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX - 1] + "…"
    return {"title": title,
            "description": "اقرأ رد الضيف، ثم اضغط «%s». لو Hostaway ما عنده رمز للحجز، "
                           "أرسله يدوياً واضغط «%s»." % (LABEL_SEND, LABEL_MANUAL),
            "color": color, "fields": fields,
            "footer": {"text": "«تسليم الرموز» · البوت يقرأ الرد ويرسل الرمز فقط لما تضغط الزر"}}


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
