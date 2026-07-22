# -*- coding: utf-8 -*-
"""studio.virality — score an idea card against RESEARCHED virality mechanics. PURE.

What this is: a structural audit of the card. It checks whether the idea is BUILT the
way the research says short-form video has to be built — hook in 3s, length in the
completion sweet spot, a loop-closing last line, something worth saving, a real number.

What this is NOT: a view predictor. Nobody can predict views from a script, and a
number that pretends to is worse than no number. Views are learned separately from
Faisal's own logged performance (studio.learn) and blended in studio.rank.

Provenance — every factor traces to the verified 2026-07-08 research pass recorded in
studio/playbook.py (docs/superpowers/specs/2026-07-08-studio-v2-research-brief.md,
20 sources, 25 claims adversarially verified). Factors are TIERED by how well-evidenced
the underlying claim is, and the tier sets the weight:

  VERIFIED (weight 1.0) — TikTok's own documentation / strongly corroborated:
    * completion is the top-weighted ranking signal; the system predicts finish-vs-skip
    * the first 3 seconds decide whether the video is finished
    * saves and shares outweigh likes
    * negative ("Not interested") feedback actively SUPPRESSES distribution
    * specificity outperforms generality
  DIRECTIONAL (weight 0.5) — secondary sources, plausible but not confirmed:
    * 21-34s carries the highest completion rate
    * a pattern interrupt roughly every 4s holds attention
    * Arabic-native delivery lifts engagement for Saudi audiences

REFUTED and deliberately NOT scored: "rage/outrage gets amplified regardless of
sentiment". The research killed it, and the owner's brand would pay for it anyway.
"""

import re

from . import engine

VERIFIED = 1.0
DIRECTIONAL = 0.5

# Sweet spot and outer bounds for total runtime, in seconds.
BEST_MIN, BEST_MAX = 21, 34
OK_MIN, OK_MAX = 15, 50
INTERRUPT_EVERY = 4.0

# Openers that waste the 3 seconds that decide the video.
COLD_OPEN_KILLERS = ("السلام عليكم", "هلا والله", "هلا وغلا", "اهلا", "أهلا", "مرحبا",
                     "مرحباً", "صباح الخير", "مساء الخير", "كيفكم", "شلونكم",
                     "انا فيصل", "أنا فيصل", "معكم", "اسمي", "قبل ما نبدأ",
                     "في هذا الفيديو", "بهذا الفيديو", "اليوم بنتكلم")

# Words that read as unresolved negativity — the one thing research says gets
# SUPPRESSED rather than boosted. Presence is a penalty, not a bonus.
NEGATIVITY = ("فضيحة", "كارثة", "مصيبة", "غشونا", "نصب", "احتيال", "حرامي",
              "أسوأ", "اسوأ", "فشل ذريع", "تحذير خطير", "لا تتعامل")

# Payload words that signal something worth SAVING or SENDING to a friend.
SAVEABLE = ("طريقة", "خطوات", "كيف", "درس", "قاعدة", "نصيحة", "تقدر", "احفظ",
            "جرّب", "جرب", "الفرق", "قارن", "الخطأ", "تجنّب", "تجنب")

_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"

# Spoken Arabic quantities. Faisal talks, he doesn't read digits aloud — «قبل يوم واحد»
# is exactly as specific as «قبل 1 يوم», and the research rewards the specificity, not
# the glyph. Missing these made spoken-number hooks look vague when they aren't.
NUMBER_WORDS = ("واحد", "وحدة", "اثنين", "ثنتين", "ثلاث", "أربع", "اربع", "خمس", "ست",
                "سبع", "ثمان", "تسع", "عشر", "عشرين", "ثلاثين", "أربعين", "اربعين",
                "خمسين", "ستين", "سبعين", "ثمانين", "تسعين", "مية", "مئة", "ألف", "الف",
                "نص", "ثلث", "ربع", "ضعف", "ضعفين", "أضعاف", "اضعاف")


def _norm_digits(text):
    t = str(text or "")
    for i, d in enumerate(_AR_DIGITS):
        t = t.replace(d, str(i))
    return t


def has_number(text):
    """A real quantity in the text — the specificity the research rewards.
    A bare year or a beat timestamp is not a claim, so those don't count."""
    t = _norm_digits(text)
    t = re.sub(r"[(（][^)）]*[)）]", " ", t)          # strip beat timings like (0-3s)
    for m in re.finditer(r"[0-9]+([.,][0-9]+)?", t):
        v = m.group(0)
        if len(v) == 4 and v.startswith(("19", "20")):   # a year, not a stat
            continue
        return True
    if "%" in t or "٪" in t:
        return True
    return any(w in t for w in NUMBER_WORDS)


def beat_timing(script):
    """(total_seconds|None, beat_count) read off the script's own timings.
    None means the card never declared a length — which is itself a finding."""
    beats = [str(b) for b in (script or []) if str(b).strip()]
    last = None
    for b in beats:
        for m in re.finditer(r"([0-9]+)\s*(?:-|–|إلى|الى)?\s*([0-9]+)?\s*(?:ث|ثانية|s\b)",
                             _norm_digits(b)):
            end = m.group(2) or m.group(1)
            try:
                last = max(last or 0, int(end))
            except ValueError:
                pass
    return last, len(beats)


def _words(text):
    return [w for w in str(text or "").split() if w.strip()]


# ---------------- individual factors (each returns 0.0 .. 1.0) ----------------

def f_hook_speed(card):
    """VERIFIED — the first 3 seconds decide completion."""
    hook = str(card.get("hook_spoken") or "").strip()
    if not hook:
        return 0.0
    if not engine.hook_is_clean(hook):
        return 0.0
    low = hook.lower()
    if any(low.startswith(k) or low[:24].find(k) >= 0 for k in COLD_OPEN_KILLERS):
        return 0.2                                    # warm-up burns the 3s
    n = len(_words(hook))
    if n <= 10:
        return 1.0
    if n <= 14:
        return 0.7
    return 0.35


def f_length(card):
    """DIRECTIONAL — 21-34s is reported as the completion sweet spot."""
    secs, _n = beat_timing(card.get("script"))
    if secs is None:
        return 0.5                                    # unknown, not wrong
    if BEST_MIN <= secs <= BEST_MAX:
        return 1.0
    if OK_MIN <= secs <= OK_MAX:
        return 0.7
    if secs < OK_MIN:
        return 0.45
    return 0.25


def f_loop_close(card):
    """VERIFIED — an ending that returns to the hook drives rewatch, and rewatch is
    completion. Measured as real token overlap between the last beat and the hook."""
    script = [str(b) for b in (card.get("script") or []) if str(b).strip()]
    hook = str(card.get("hook_spoken") or "")
    if not script or not hook:
        return 0.0
    tail = set(engine.novelty_key(script[-1]).split())
    head = set(engine.novelty_key(hook).split())
    if not tail or not head:
        return 0.0
    overlap = len(tail & head)
    if overlap >= 2:
        return 1.0
    if overlap == 1:
        return 0.6
    return 0.2


def f_saveable(card):
    """VERIFIED — saves and shares outweigh likes, so the card needs a payload."""
    blob = " ".join([str(card.get("angle") or ""), str(card.get("cta") or ""),
                     " ".join(str(b) for b in (card.get("script") or []))])
    hits = sum(1 for w in SAVEABLE if w in blob)
    has_num = has_number(blob) or has_number(card.get("signal_text"))
    if hits >= 2 and has_num:
        return 1.0
    if hits >= 1 or has_num:
        return 0.7
    return 0.3


def f_specificity(card):
    """VERIFIED — a concrete number in the opening buys instant credibility."""
    if has_number(card.get("hook_spoken")) or has_number(card.get("visual_title")):
        return 1.0
    if has_number(card.get("signal_text")):
        return 0.65                                   # the number exists but isn't up front
    return 0.25


def f_onscreen(card):
    """VERIFIED — 30%+ watch muted, and the on-screen line must ADD, not echo."""
    title = str(card.get("visual_title") or "").strip()
    sub = str(card.get("visual_sub") or "").strip()
    hook = str(card.get("hook_spoken") or "")
    if not title:
        return 0.0
    if engine.novelty_key(title) and not engine.is_novel(engine.novelty_key(title), [engine.novelty_key(hook)]):
        return 0.5                                    # on-screen text just repeats the spoken hook
    return 1.0 if sub else 0.8


def f_interrupts(card):
    """DIRECTIONAL — roughly a beat every 4s keeps attention from drifting."""
    secs, n = beat_timing(card.get("script"))
    if not n:
        return 0.0
    if secs is None:
        return 0.6 if n >= 4 else 0.4
    need = max(2.0, secs / INTERRUPT_EVERY)
    ratio = n / need
    if ratio >= 0.9:
        return 1.0
    if ratio >= 0.6:
        return 0.7
    return 0.35


def f_no_suppression(card):
    """VERIFIED — negative feedback suppresses distribution. Inverted: clean = 1.0."""
    blob = " ".join([str(card.get("hook_spoken") or ""), str(card.get("visual_title") or ""),
                     str(card.get("visual_sub") or ""), str(card.get("angle") or "")])
    hits = sum(1 for w in NEGATIVITY if w in blob)
    if hits >= 2:
        return 0.0
    if hits == 1:
        return 0.45
    return 1.0


FACTORS = (
    ("hook_speed", f_hook_speed, VERIFIED, "الهوك يخطف أول ٣ ثواني"),
    ("specificity", f_specificity, VERIFIED, "رقم حقيقي في المقدمة"),
    ("loop_close", f_loop_close, VERIFIED, "النهاية ترجع للهوك (إعادة مشاهدة)"),
    ("saveable", f_saveable, VERIFIED, "فيه شي يستاهل الحفظ أو الإرسال"),
    ("onscreen", f_onscreen, VERIFIED, "نص على الشاشة يضيف مو يكرّر"),
    ("no_suppression", f_no_suppression, VERIFIED, "خالي من السلبية اللي تُكبت"),
    ("length", f_length, DIRECTIONAL, "الطول في نطاق الإكمال الأعلى"),
    ("interrupts", f_interrupts, DIRECTIONAL, "إيقاع مشاهد يمسك الانتباه"),
)

# What to tell him when a factor is weak. This is the part that actually improves the
# next video — a score without a fix is just a grade.
FIXES = {
    "hook_speed": "اختصر الهوك لأقل من ١٠ كلمات وابدأ وسط الحدث — بدون سلام ولا تعريف بالنفس",
    "specificity": "حط الرقم الحقيقي في أول جملة تُنطق، مو في وسط الفيديو",
    "loop_close": "خلّ آخر جملة ترجع لنفس فكرة الهوك — هذي اللي تصنع إعادة المشاهدة",
    "saveable": "ضيف درس عملي أو رقم مفيد يخلي الواحد يحفظه أو يرسله لصاحبه",
    "onscreen": "النص على الشاشة يقول شي مختلف عن المنطوق — يرفع الرهان أو يحدد لمن هذا",
    "no_suppression": "خفّف اللهجة السلبية — التغذية الراجعة السلبية تكبت التوزيع فعلياً",
    "length": "خلّ الطول بين ٢١ و٣٤ ثانية — أعلى نسبة إكمال",
    "interrupts": "زد الانعطافات: مشهد أو رقم جديد كل ٤ ثواني تقريباً",
}

WEAK = 0.6          # below this a factor is worth naming as a fix


def audit(card):
    """{'score':0-100, 'factors':{name:{value,tier,label}}, 'fixes':[…], 'wins':[…]}."""
    if not isinstance(card, dict):
        return {"score": 0, "factors": {}, "fixes": [], "wins": []}
    factors, total_w, got = {}, 0.0, 0.0
    for name, fn, weight, label in FACTORS:
        try:
            v = float(fn(card))
        except Exception:
            v = 0.0
        v = max(0.0, min(1.0, v))
        factors[name] = {"value": round(v, 2), "tier": weight, "label": label}
        total_w += weight
        got += weight * v
    score = int(round(100.0 * got / total_w)) if total_w else 0
    fixes, wins = [], []
    for name, _fn, weight, label in FACTORS:
        v = factors[name]["value"]
        if v < WEAK:
            fixes.append({"key": name, "text": FIXES.get(name, label),
                          "weight": weight})
        elif v >= 0.9:
            wins.append(label)
    # verified-tier problems come first: they matter more and are better evidenced
    fixes.sort(key=lambda f: -f["weight"])
    return {"score": score, "factors": factors,
            "fixes": [f["text"] for f in fixes], "wins": wins}


def score(card):
    return audit(card)["score"]
