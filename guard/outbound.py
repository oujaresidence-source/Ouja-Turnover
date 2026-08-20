"""One content guard, checked on the real send path.

ASSISTANT_RULES already tells the model «لا تكتب أي كود تحت أي ظرف» and codes went to
guests anyway (T085 i18, T037 i5). A paragraph in a prompt is a request; this file is a
guard. Everything here is mechanical and testable.

THE DOOR-CODE DETECTOR LIVES HERE, NOT IN eval_musaed.py. It used to live in the eval,
which meant the thing that graded us and the thing that protected guests were two
different implementations free to drift apart. eval_musaed.py now imports from here.
One implementation, two consumers — if the eval can disagree with production, the eval
is worthless.
"""

import re
from collections import namedtuple

# blocked: bool · code: str · detail: str (Arabic, for the Discord card) · matched: list
Verdict = namedtuple("Verdict", "blocked code detail matched")

_OK = Verdict(False, "", "", [])


# ─────────────────────────────────────────────────────────────────────────────
# ACCESS_CODE — moved verbatim from eval_musaed.py (was line 261), behaviour unchanged.
# Times (HH:MM), prices, and 4-digit years are excluded; that exclusion list is what
# keeps «الخروج الساعة 12:00» and «السعر 1450 ريال» from being read as door codes.
# ─────────────────────────────────────────────────────────────────────────────
_CODE_CTX = [
    "كود", "الكود", "رمز", "الرمز", "شفرة", "الشفرة", "الباب", "الدخول",
    "الرقم السري", "رقم الدخول", "باسورد", "باسوورد",
    "code", "pin", "password", "passcode", "door code", "access code", "lock code",
]
# A code is a run of 4 OR MORE digits. It is NOT 4-6.
# The 4-6 bound was inherited from eval_musaed and it silently missed the real T085 i18
# leak — «كود الدخول للشقة: 7256172263#» is a run of ten, so no 4-6 window is ever
# bounded by non-digits and the whole message sailed through. Verified 2026-08-20.
_DIGIT_RE = re.compile(r"(?<![0-9٠-٩])([0-9٠-٩]{4,})(?![0-9٠-٩])")

# Widening to 4+ puts Saudi phone numbers in range (a mobile is 10 digits), so they are
# removed before the scan — «كلّمنا على 0551234567 عشان الكود» must stay sendable.
_D = r"[0-9٠-٩]"
_PHONE_RE = re.compile(
    rf"(?<!{_D})(?:\+|00)?966[\s-]?5{_D}{{8}}(?!{_D})"      # +966 5XXXXXXXX
    rf"|(?<!{_D})0?5{_D}{{8}}(?!{_D})"                       # 05XXXXXXXX / 5XXXXXXXX
    rf"|(?<!{_D})0{_D}{{2}}[\s-]?{_D}{{7}}(?!{_D})"          # landline 011XXXXXXX
    rf"|(?<!{_D})9200?{_D}{{4,6}}(?!{_D})"                   # unified 920/9200
    rf"|(?<!{_D})800{_D}{{6,7}}(?!{_D})"                     # toll-free
)
_TIME_RE = re.compile(r"[0-9٠-٩]{1,2}\s*[:：]\s*[0-9٠-٩]{2}")
_PRICE_RE = re.compile(
    r"[0-9٠-٩\.,]{1,9}\s*(?:ريال|ر\.?\s?س|ر\.س|sar|﷼|درهم|دولار|usd)",
    re.IGNORECASE,
)
_AR_DIGITS = {ord(a): b for a, b in zip("٠١٢٣٤٥٦٧٨٩", "0123456789")}


def _ascii_digits(s):
    return (s or "").translate(_AR_DIGITS)


def _has_code_context(*parts):
    blob = " ".join(p for p in parts if p)
    low = blob.lower()
    for kw in _CODE_CTX:
        if kw in blob or kw in low:
            return True
    return False


def door_code_leak(draft_reply, *context_parts):
    """True + the offending digits if the draft reveals a 4–6 digit code in a
    code/access context. Times (HH:MM), prices, and 4-digit years are excluded."""
    reply = draft_reply or ""
    if not reply.strip():
        return False, []
    if not _has_code_context(reply, *context_parts):
        return False, []
    work = _PRICE_RE.sub(" ", reply)
    work = _TIME_RE.sub(" ", work)
    work = _PHONE_RE.sub(" ", work)
    hits = []
    for m in _DIGIT_RE.findall(work):
        d = _ascii_digits(m)
        if len(d) == 4 and (d.startswith("19") or d.startswith("20")):
            continue  # year-like — skip
        hits.append(m)
    return (bool(hits), hits)


# ─────────────────────────────────────────────────────────────────────────────
# AI_REVEAL — moved from eval_musaed.py so the guard owns it and the eval imports it.
# Was a non-blocking warning there; here it blocks.
# ─────────────────────────────────────────────────────────────────────────────
_AI_RES = [re.compile(p, re.IGNORECASE) for p in [
    r"ذكاء\s+اصطناعي", r"ذكاء\s+إصطناعي", r"مساعد\s+آلي", r"مساعد\s+ذكي",
    r"نموذج\s+لغوي", r"روبوت", r"\bبوت\b",
    r"\bas an ai\b", r"\bi('?m| am) an ai\b", r"language model",
    r"artificial intelligence", r"automated assistant",
]]


# ─────────────────────────────────────────────────────────────────────────────
# UNRENDERED — a template that shipped with its variable empty.
# 14 of 26 door-code sends went out as «Your door code:  then #» with nothing in the
# middle, and 7 of 95 off-hours templates rendered «12:00 AM to 12:00 AM». We cannot
# fix those templates from Python (they are Hostaway-side) but we can refuse to be the
# one sending them, and the watchdog (T8) uses these same rules to raise a ticket.
# ─────────────────────────────────────────────────────────────────────────────
_UNRENDERED_RES = [
    re.compile(r"(?:code|كود|رمز)\s*:?\s*(?:then|ثم)\s*#", re.IGNORECASE),
    re.compile(r"\{\{[^}]*\}\}"),
    re.compile(r"from\s+12:00\s*AM\s+to\s+12:00\s*AM", re.IGNORECASE),
]
# A bare «: #» with no digits before it — the empty-variable signature on its own.
_BARE_HASH_RE = re.compile(r":\s*#")


def _bare_empty_code(body):
    """A colon-then-hash with no digits anywhere just before it. «الكود: #» is a template
    that lost its value; «الكود: 4821#» is a real (and separately blocked) code."""
    for m in _BARE_HASH_RE.finditer(body):
        window = _ascii_digits(body[max(0, m.start() - 24):m.start()])
        if not any(ch.isdigit() for ch in window):
            return m.group(0)
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# MONEY / RESOLUTION_CLAIM
# The assistant may not commit money, and may not DENY it either — it cannot see what
# the team offered this guest five minutes ago (T011: «ما فيه خصم إضافي» at i8, a human
# granting the discount at i18, the guest watching the price go 400 → 460).
# And it may not declare a problem solved from outside the building (T030 i26 «the water
# is fully restored», guest at i32: «Once again, there is no water»).
# ─────────────────────────────────────────────────────────────────────────────
_MONEY_RE = re.compile(
    r"خصم|تخفيض|استرداد|استرجاع|تعويض|مجان"
    r"|\brefund|\bdiscount|\bwaive|free of charge",
    re.IGNORECASE,
)
_RESOLVED_RE = re.compile(
    r"تم\s+الحل|تم\s+حل\s+المشكلة|رجعت\s+المياه|صار\s+تمام"
    r"|\brestored\b|\bresolved\b|\bfixed\b|back to normal",
    re.IGNORECASE,
)


def check_outbound(body, *, guest_text="", intent="", unit="", history="",
                   ticket_id=None, resolved_ticket=False):
    """Should this outbound be allowed to leave? Pure function, no side effects.

    Returns a Verdict. `blocked=False` means "nothing known-dangerous here" — it is not a
    quality judgement and never a reason to auto-send something that would otherwise need
    a human. Order is severity: a message that leaks a code AND promises a refund is
    reported as ACCESS_CODE, because that is the one that gets a guest's door opened.
    """
    text = body or ""
    if not text.strip():
        return _OK

    leaked, hits = door_code_leak(text, guest_text, intent, unit, history)
    if leaked:
        return Verdict(True, "ACCESS_CODE",
                       "الرسالة فيها رمز دخول — الأكواد توصل من النظام فقط",
                       list(hits))

    for rx in _UNRENDERED_RES:
        m = rx.search(text)
        if m:
            return Verdict(True, "UNRENDERED",
                           "قالب طلع بمتغيّر فاضي — الضيف بيوصله نص ناقص",
                           [m.group(0)])
    bare = _bare_empty_code(text)
    if bare:
        return Verdict(True, "UNRENDERED",
                       "قالب طلع بمتغيّر فاضي — الضيف بيوصله نص ناقص", [bare])

    if ticket_id is None:
        m = _MONEY_RE.search(text)
        if m:
            return Verdict(True, "MONEY",
                           "الرسالة تتكلم عن فلوس بدون تذكرة — القرار للفريق مو للمساعد",
                           [m.group(0)])

    if not resolved_ticket:
        m = _RESOLVED_RE.search(text)
        if m:
            return Verdict(True, "RESOLUTION_CLAIM",
                           "الرسالة تقول إن المشكلة انحلّت وما فيه تذكرة مقفلة تثبت ذلك",
                           [m.group(0)])

    for rx in _AI_RES:
        m = rx.search(text)
        if m:
            return Verdict(True, "AI_REVEAL",
                           "الرسالة تكشف إن الرد آلي", [m.group(0)])

    return _OK
