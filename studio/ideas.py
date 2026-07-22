# -*- coding: utf-8 -*-
"""studio.ideas — turns a story card into ready-to-shoot TikTok idea cards.

Premium-model call, playbook-grounded. Each card carries everything the owner
needs at the moment of filming: the spoken hook (the literal first words on
camera), the visual hook (on-screen title + subtitle), the beat script, CTA,
and the audience tag (niche = ملاك/مشغّلين, escape = جمهور عام)."""

import json

from . import db, engine, hooks, learn, shapes, virality
from .host import HOST
from .playbook import PLAYBOOK, WHY_MECHANICS

# v3 — ideas from ANY signal, not just a guest story. This is the path that finally
# uses Ouja's own numbers and today's news (spec Sections C + D).
SIGNAL_IDEAS_SYSTEM_HEAD = """أنت مخرج محتوى قصير لفيصل — صاحب عوجا (شقق مفروشة راقية، الرياض)
وأكبر صانع محتوى سعودي في مجال الإيجار قصير المدى.

تستلم «إشارة» حقيقية وحدة — إما رقم من بيانات عوجا الفعلية، أو خبر/نظام خارجي موثّق بمصدره،
أو موقف كتبه فيصل بنفسه — وتحوّلها لأفكار فيديو تيك توك جاهزة للتصوير.

"""

# The voice + the hard constraints. These are GENERATION rules, not a printed scaffold:
# the discipline (hook-first, number-first, loop-close) shapes what the model writes, but
# the card must read like Faisal talking, never like a timed storyboard (owner verdict
# 2026-07-24: "the ideas are dumb / same shape / not my voice").
VOICE_SPEC = """صوت فيصل (إلزامي):
- نجدي، بضمير المتكلم، كأنك واقف قدام الكاميرا تتكلم — مو نص مكتوب يُقرأ.
- ودّي وطبيعي، بدون حماس مصطنع ولا مبالغة، بدون أي كلمة إنجليزية، وبدون إيموجي.
- جُمل قصيرة، وروابط طبيعية مثل «طيب»، «المهم»، «شوف»، «خلني أقول لك».
- العمود الفقري للفيديو رقم حقيقي أو اقتباس حقيقي — مو كلام إنشائي."""

SIGNAL_IDEAS_RULES = """القاعدة الحاكمة (فوق كل شي): الفكرة مبنية على «الإشارة» المعطاة فقط.
- ممنوع تخترع رقم أو نسبة أو تاريخ أو تفصيلة مو موجودة بالإشارة. لا تضيف «حقائق» ربط من عندك.
- ممنوع تعمّم («٥ نصائح لأصحاب الشقق») بدون ما تستند للإشارة — هذا يُرفض.
- إذا الإشارة فيها رقم: أول جملة تُنطق تبدأ بالرقم نفسه (أول كلمة أو كلمتين)، مو بعد سؤال ولا مقدمة.

قواعد البناء (طبّقها وانت تكتب — لا تطبعها كخطوات ولا تحط توقيتات مثل «(٠-٣ث)» أبداً):
- أول سطر = الهوك، يمسك خلال أول ٣ ثواني.
- كل جملة تعطي التفاتة أو معلومة جديدة، ما فيه حشو ولا فقرة شرح ميتة.
- آخر سطر يرجع لفكرة الهوك (يصنع إعادة مشاهدة).
- «script» = جُمل طبيعية متتابعة كأنك تحكي، بدون أرقام توقيت وبدون ترقيم مشاهد.

الجمهور: صنّف كل فكرة niche (ملّاك ومشغّلين) أو escape (جمهور عام سعودي). إذا الإشارة تصلح للجمهور
العام، فضّل escape — احنا نبي ننمّي الحساب مو بس نخاطب الملّاك.

كل فكرة تاخذ «شكل» مختلف من الأشكال المعطاة تحت (ما تكرر نفس الشكل مرتين).

أرجع JSON فقط بهذا الشكل (٢-٣ أفكار، كل وحدة شكل مختلف وزاوية مختلفة فعلاً):
{"ideas": [
  {"hook_spoken": "الكلمات الحرفية أول ٣ ثواني (٥-١٠ كلمات نجدي، والرقم أول شي إذا فيه رقم)",
   "visual_title": "العنوان الكبير على الشاشة",
   "visual_sub": "السطر الثاني: يرفع الرهان أو يحدد لمن هذا",
   "angle": "وش الزاوية وليش يوقف يشاهد — سطر",
   "why_it_works": "ليش بتشتغل — آلية مثبتة بجملة قصيرة (إجباري)",
   "script": ["جُمل السكربت طبيعية متتابعة بصوت فيصل — بدون أي توقيت أو ترقيم"],
   "shape": "cold_number|myth_bust|quote_reaction|before_after|half_of_us|owner_question|list_of_three|news_react",
   "video_type": "talking|tour|before_after|story_voiceover|onsite|data_reveal|news_reaction",
   "cta": "الدعوة الختامية بكلمات فيصل (أو فاضية إذا الأفضل بدونها)",
   "audience": "niche|escape",
   "trigger": "curiosity|loss|identity|provocation|authority|social_proof|news"}
]}"""

MANUAL_SYSTEM = """أنت محرر محتوى لفيصل — صاحب عوجا (شقق مفروشة راقية بالرياض) وصانع محتوى.
فيصل كتب لك موقف حقيقي صار معه اليوم بسطر أو سطرين. حوّله لـ«إشارة» صالحة للمحتوى.

- لا تخترع تفاصيل ما ذكرها. إذا الموقف ناقص، خذه كما هو.
- ممنوع اسم ضيف أو رقم شقة أو أي معلومة تعرّف على أحد.
- خلّ الزاوية إيجابية: تُظهر احتراف عوجا أو إنسانية الموقف أو طرافته.

أرجع JSON فقط:
{"signals": [{"source": "manual", "title": "عنوان قصير", "fact": "الموقف بجملة وحدة واضحة",
              "detail": "ليش هالموقف يستاهل فيديو — سطر", "strength": 0-100}]}"""


def _learn_stats():
    try:
        return learn.stats(db.learn_rows())
    except Exception:
        return {"n": 0, "mean": 0, "dims": {}}


def _ground(card, signal, shape, stats, story_type=""):
    """Stamp the grounding, shape, strength and novelty key onto one card.
    A card is ALWAYS tied to a signal here — the story path mints a signal first, so
    there is no ungrounded path left (spec S1)."""
    card["signal_sid"] = signal.get("sid", "")
    card["signal_family"] = signal.get("family", "")
    card["signal_source"] = signal.get("source", "")
    card["signal_text"] = signal.get("fact", "")
    card["signal_url"] = signal.get("url", "")
    card["signal_date"] = signal.get("as_of", "")
    # keep the model's shape if it's a real one, else the shape we asked it to use
    sh = card.get("shape")
    card["shape"] = sh if sh in shapes.SHAPE_KEYS else shape
    card["strength"] = learn.strength_of(
        {"trigger_kind": card.get("trigger"), "audience": card.get("audience"),
         "video_type": card.get("video_type"), "signal_family": card.get("signal_family"),
         "story_type": story_type}, stats)
    card["nkey"] = engine.novelty_key("%s %s" % (card.get("visual_title", ""),
                                                 card.get("angle", "")))
    return card


def card_grounded(card):
    """spec S1: a card renders only if its signal_sid resolves to a stored signal.
    ideas.py never emits a card without one; this is the belt-and-suspenders check
    used by the persist path and asserted in tests."""
    sid = (card or {}).get("signal_sid") if isinstance(card, dict) else None
    if not sid:
        return False
    try:
        return db.signal(sid) is not None
    except Exception:
        return False


def _pick_best(cards, fact):
    """From the model's candidates, keep the single strongest that is clean and —
    when the fact carries a number — leads with it (spec S2/S3). Returns one card
    or None."""
    scored = []
    for c in cards:
        hook = c.get("hook_spoken", "")
        if not engine.hook_is_clean(hook) or not engine.hook_is_clean(c.get("visual_title", "")):
            continue
        number_first = engine.leads_with_number(hook, fact)
        # virality score is the tie-breaker; a card that leads with the number wins a
        # decisive bonus so number-first is effectively enforced, not just preferred.
        s = virality.score(c) + (25 if number_first else 0)
        scored.append((number_first, s, c))
    if not scored:
        return None
    # prefer number-first candidates; among those, the strongest build
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]


def _persist(cards, story_id=0):
    ts = ""
    try:
        ts = HOST.require("now")().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    out = []
    for c in cards:
        c["id"] = db.add_idea(story_id, c, ts)
        c["story_id"] = int(story_id or 0)
        out.append(c)
    return out


def generate_for_signal(sid, force=False, story_type=""):
    """Turn ONE stored signal into exactly ONE idea card (spec S2: one grounding fact
    = one card). Generates a few candidate shapes in a single call and keeps the
    strongest number-first build. Returns [] if the signal already has a card
    (unless force) or nothing usable came back."""
    sig = db.signal(sid)
    if not sig:
        return []
    if not force and db.sid_has_live_card(sig["sid"]):
        return []                       # one fact already produced a card this cycle
    stats = _learn_stats()
    src = sig.get("source", "")
    shape_keys = shapes.candidate_shapes(src, n=3)
    system = (SIGNAL_IDEAS_SYSTEM_HEAD + VOICE_SPEC + "\n\n" + PLAYBOOK + "\n\n" +
              WHY_MECHANICS + "\n\n" + hooks.prompt_block(src) + "\n\n" +
              shapes.guide_block(shape_keys) + "\n\n" + SIGNAL_IDEAS_RULES)
    body = {"نوع الإشارة": sig.get("family"), "المصدر": sig.get("source"),
            "العنوان": sig.get("title"), "الحقيقة": sig.get("fact"),
            "تفاصيل": sig.get("detail")}
    if sig.get("url"):
        body["رابط المصدر"] = sig["url"]
    if sig.get("as_of"):
        body["تاريخ المصدر"] = sig["as_of"]
    user = ("الإشارة:\n" + json.dumps(body, ensure_ascii=False, indent=1) +
            learn.bias_hint_ar(stats) +
            "\n\nحوّلها لأفكار فيديو (كل وحدة بشكل مختلف) حسب القواعد. JSON فقط.")
    raw = HOST.require("claude_json")(system, user, max_tokens=2400,
                                      model=getattr(HOST, "model_premium", None))
    best = _pick_best(engine.parse_ideas(raw), sig.get("fact", ""))
    if not best:
        return []
    best = _ground(best, sig, shape_keys[0], stats, story_type=story_type)
    if not card_grounded(best):
        return []                       # never render an ungrounded card (spec S1)
    try:
        db.set_signal_status(sig["sid"], "used")
    except Exception:
        pass
    return _persist([best], story_id=0)


def generate_manual(text):
    """Spec Section E: Faisal types one line about his day -> a grounded signal ->
    idea cards. Returns (signal|None, cards)."""
    txt = str(text or "").strip()
    if len(txt) < 8:
        return None, []
    ts = ""
    try:
        ts = HOST.require("now")().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    raw = HOST.require("claude_json")(MANUAL_SYSTEM, "الموقف:\n" + txt[:1500],
                                      max_tokens=700,
                                      model=getattr(HOST, "model_premium", None))
    sigs = engine.parse_signals(raw, "manual", default_source="manual")
    if not sigs:
        # The model failed but the owner's own words are already a real signal —
        # never lose them. Store the raw line verbatim.
        s = engine.make_signal("manual", "manual", "موقف من فيصل", txt[:700],
                               as_of=ts[:10], strength=60)
        if not s:
            return None, []
        sigs = [s]
    sig = sigs[0]
    db.add_signal(sig, nkey=engine.novelty_key(sig["fact"]), ts=ts)
    return sig, generate_for_signal(sig["sid"])


def generate_for_story(story_id):
    """A guest story becomes ONE card — by first minting a `guest_story` SIGNAL from
    it (spec S1) so the card is grounded on a real, feed-visible `sid`, then running
    the one unified grounded generator. This closes the old fabrication path where
    story cards had signal_sid="" and invented connective framing, and it caps a story
    at one card (spec S2). The anecdote now shows up in v=signals like any other fact."""
    s = db.story(story_id)
    if not s:
        return []
    # a real guest quote is the strongest, most honest fact; fall back to the angle.
    fact = ""
    for qraw in (s.get("quotes") or []):
        if str(qraw or "").strip():
            fact = str(qraw).strip()[:200]
            break
    if not fact:
        fact = str(s.get("angle") or s.get("title") or "").strip()[:200]
    detail = " — ".join([x for x in (s.get("summary"), s.get("lesson")) if x])[:900]
    try:
        strength = max(0, min(100, int(s.get("score") or 0) * 10))
    except (TypeError, ValueError):
        strength = 50
    sig = engine.make_signal("internal", "guest_story", s.get("title") or "قصة ضيف",
                             fact, detail=detail,
                             as_of=str(s.get("created_at") or "")[:10], strength=strength)
    if not sig:
        return []                       # empty fact -> cannot ground -> don't render
    db.add_signal(sig, nkey=engine.novelty_key(fact), ts=_now_ts())
    return generate_for_signal(sig["sid"], story_type=s.get("story_type", ""))


def _now_ts():
    try:
        return HOST.require("now")().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""
