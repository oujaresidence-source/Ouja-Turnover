# -*- coding: utf-8 -*-
"""digest.voice — how the digest talks (brief §3.4).

Two halves. The PURE half (denylist, numerals, word limits) has no host and is what the
guard calls. The MODEL half (`polish`) asks Claude for a Najdi rewrite of one card's
copy with the facts pinned, then re-checks the answer with the pure half and keeps the
original if the model slipped. Rules live as code and tests, not prose."""

import json
import re

# Marketing slop, banned outright. Prefixes/plurals are covered by not anchoring on
# the word end («اكتشفوا» hits «اكتشف»). Patterns are matched against text with tashkeel (diacritics) and tatweel stripped,
# so «لا تفوّت» / «لا تفوت» / «لا يُفوَّت» all reduce to their bare letters.
_BANNED_SRC = (
    ("اكتشف", "اكتشف"),
    ("لا تفوت", "لا تفوّت"),
    ("تجربة استثنائية", "تجربة استثنائية"),
    ("لا مثيل ل", "لا مثيل لها"),
    ("وجهتك المثالية", "وجهتك المثالية"),
    ("أجواء ساحرة", "أجواء ساحرة"),
    ("على بعد خطوات", "على بُعد خطوات"),
    ("انغمس", "انغمس"),
    ("استمتع ب", "استمتع بـ"),
    ("نقلة نوعية", "نقلة نوعية"),
    ("لا يفوت", "لا يُفوَّت"),
    ("سحر ", "سحر"),
)
BANNED = [(re.compile(p), label) for p, label in _BANNED_SRC]
_TASHKEEL = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")


def normalize(text):
    """Strip tashkeel + tatweel so one pattern covers the vowelled and bare spellings."""
    return _TASHKEEL.sub("", text or "")

_AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_WESTERN = re.compile(r"[0-9]+")   # NOT \d — that matches Arabic-Indic too
_WS = re.compile(r"\s+")

MAX_TITLE_WORDS = 4
MAX_SUB_WORDS = 10


def slop_hits(text):
    """Every banned phrase found in `text`, as its canonical label."""
    t = normalize(text)
    return [label for rx, label in BANNED if rx.search(t)]


def is_clean(text):
    return not slop_hits(text)


_ARABIC_LETTER = re.compile("[؀-ۿ]")


def to_arabic_indic(text):
    return (text or "").translate(_AR)


def prose_digits(text):
    """The prose rule, applied honestly: Arabic text gets Arabic-Indic digits; a
    Latin-only run (a film title like «Fall 2») keeps its Western digits — the
    renderer sets it inside <span dir=ltr>, which the guard exempts."""
    t = text or ""
    return to_arabic_indic(t) if _ARABIC_LETTER.search(t) else t


def western_digits_in_prose(text):
    return _WESTERN.findall(text or "")


def word_count(s):
    """Words = whitespace tokens that are not bare separators («·», «–», «-»)."""
    return len([w for w in _WS.split((s or "").strip()) if w and w not in ("·", "–", "-", "—", "×")])


def title_ok(t):
    return 0 < word_count(t) <= MAX_TITLE_WORDS


def sub_ok(s):
    return word_count(s) <= MAX_SUB_WORDS


# ---------------- the model half ----------------

PROMPT_SYSTEM = (
    "أنت تكتب نشرة «وش صاير بالرياض» لضيوف عوجا. اللهجة نجدية، جمل قصيرة، شخص يتكلم مو إعلان. "
    "ممنوع الصفات التسويقية نهائياً: اكتشف · لا تفوّت · تجربة استثنائية · لا مثيل لها · "
    "وجهتك المثالية · أجواء ساحرة · على بُعد خطوات · انغمس · استمتع بـ · نقلة نوعية · سحر. "
    "الحقائق (الاسم، المكان، اليوم، الوقت، السعر) مثبّتة كما هي في JSON ولا تغيّرها ولا تضيف عليها. "
    "الأرقام في النص بالأرقام العربية (٣ سبتمبر). العنوان ٤ كلمات أو أقل، السطر الثاني ١٠ كلمات أو أقل. "
    "رجّع JSON فقط بالشكل {\"ttl\": \"...\", \"sub\": \"...\"}."
)


CLAIM_SYSTEM = (
    "أنت تكتب عنوان صفحة واحد لنشرة «وش صاير بالرياض» لضيوف عوجا. نجدي، جملة فيها فعل أو ادّعاء، "
    "٦ كلمات أو أقل. محدّد لا عام: اسم، مكان، يوم، سعر — حقيقة من اللي أعطيك، لا تخترع ولا تضيف. "
    "ممنوع الصفات التسويقية: اكتشف · لا تفوّت · تجربة استثنائية · لا مثيل لها · وجهتك المثالية · "
    "أجواء ساحرة · على بُعد خطوات · انغمس · استمتع بـ · نقلة نوعية · سحر. الأرقام بالعربية. "
    "الفترة اسمها «هالويكند» دايم — لا تقول «هذا الأسبوع» ولا «هالأسبوع» ولا «الخميس الجاي». "
    "رجّع JSON فقط: {\"claim\": \"...\"}."
)
MAX_CLAIM_WORDS = 6


_WEEK_WORDS = ("هذا الأسبوع", "هالأسبوع", "هذا الاسبوع", "هالاسبوع", "الأسبوع الجاي", "الخميس الجاي", "الأسبوع القادم")


def weekend_wording(t):
    """The owner's word for the period is «هالويكند» (2026-09-03)."""
    for w in _WEEK_WORDS:
        t = (t or "").replace(w, "هالويكند")
    return t


def claim_ok(t):
    return 0 < word_count(t) <= MAX_CLAIM_WORDS and is_clean(t)


def polish_claim(section_key, items, model_call=None, model=None, seed=0):
    """The ONE thing the model writes: the page headline, from the facts. Returns ''
    when there is no model or its answer breaks a rule (the renderer then uses its
    deterministic fallback)."""
    if model_call is None or not items:
        return ""
    facts = [{k: it.get(k) for k in ("ttl", "sub", "chip", "hook", "home", "away", "when") if it.get(k)} for it in items[:4]]
    user = "القسم: %s · محاولة %d · الحقائق: %s" % (section_key, int(seed) + 1, json.dumps(facts, ensure_ascii=False))
    try:
        got = model_call(CLAIM_SYSTEM, user, max_tokens=200, model=model)
    except Exception:
        return ""
    if not isinstance(got, dict):
        return ""
    t = weekend_wording(prose_digits((got.get("claim") or "").strip()))
    return t if claim_ok(t) else ""


def polish(item, kind="card", seed=0, model_call=None, model=None):
    """Return a copy of `item` with ttl/sub rewritten by the model, or the same copy
    untouched when the model is absent, fails, or breaks a rule. `model_call` is
    HOST.claude_json (injected so this stays testable offline)."""
    out = dict(item)
    if model_call is None:
        return out
    facts = {k: item.get(k) for k in ("ttl", "sub", "chip", "day", "when", "home", "away") if item.get(k)}
    user = "النوع: %s · محاولة رقم %d · الحقائق: %s" % (kind, int(seed) + 1, json.dumps(facts, ensure_ascii=False))
    try:
        got = model_call(PROMPT_SYSTEM, user, max_tokens=300, model=model)
    except Exception:
        return out
    if not isinstance(got, dict):
        return out
    ttl = prose_digits((got.get("ttl") or "").strip())
    sub = prose_digits((got.get("sub") or "").strip())
    if kind == "card":
        if not (title_ok(ttl) and sub_ok(sub) and is_clean(ttl) and is_clean(sub)):
            return out
        out["ttl"], out["sub"] = ttl, sub
    return out
