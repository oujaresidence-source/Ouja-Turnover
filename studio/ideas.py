# -*- coding: utf-8 -*-
"""studio.ideas — turns a story card into ready-to-shoot TikTok idea cards.

Premium-model call, playbook-grounded. Each card carries everything the owner
needs at the moment of filming: the spoken hook (the literal first words on
camera), the visual hook (on-screen title + subtitle), the beat script, CTA,
and the audience tag (niche = ملاك/مشغّلين, escape = جمهور عام)."""

import json

from . import db, engine, hooks, learn
from .host import HOST
from .playbook import PLAYBOOK, WHY_MECHANICS

IDEAS_SYSTEM = """أنت مخرج محتوى قصير لفيصل — صاحب عوجا (شقق مفروشة راقية، الرياض).
تستلم «بطاقة قصة» حقيقية وإيجابية من محادثات الضيوف، وتحوّلها لأفكار فيديو تيك توك جاهزة للتصوير
تُثبت إن عوجا تشتغل شغل استثنائي.

""" + PLAYBOOK + "\n\n" + WHY_MECHANICS + """

أرجع JSON فقط بهذا الشكل (٢-٣ أفكار، كل فكرة زاوية مختلفة فعلاً — مو نفس الفكرة بصياغتين):
{"ideas": [
  {"hook_spoken": "الكلمات الحرفية اللي يقولها فيصل أول ٣ ثواني (٥-١٠ كلمات نجدي، cold open)",
   "visual_title": "العنوان الكبير على الشاشة (قصير وقوي بصدق، بدون كليشيهات محروقة)",
   "visual_sub": "السطر الثاني تحت العنوان (يرفع الرهان أو يحدد الجمهور)",
   "angle": "وش الزاوية وليش الناس بتوقف تشاهد — سطر أو سطرين",
   "why_it_works": "ليش بتشتغل هالفكرة — اربطها بآلية مثبتة بجملة قصيرة (إجباري)",
   "script": ["نقاط السيناريو بالترتيب: كل نقطة = مشهد/جملة، مع توقيت تقريبي مثل (٠-٣ث)"],
   "video_type": "talking|tour|before_after|story_voiceover|onsite",
   "cta": "الدعوة الختامية بكلمات فيصل (أو فاضية إذا الأفضل بدون)",
   "audience": "niche|escape",
   "trigger": "curiosity|loss|identity|provocation|emotion"}
]}
ملاحظة: أي فكرة بدون why_it_works أو فيها هوك كليشيه محروق بتُرفض تلقائياً — فاحرص عليها."""


# v3 — ideas from ANY signal, not just a guest story. This is the path that finally
# uses Ouja's own numbers and today's news (spec Sections C + D).
SIGNAL_IDEAS_SYSTEM_HEAD = """أنت مخرج محتوى قصير لفيصل — صاحب عوجا (شقق مفروشة راقية، الرياض)
وأكبر صانع محتوى سعودي في مجال الإيجار قصير المدى.

تستلم «إشارة» حقيقية وحدة — إما رقم من بيانات عوجا الفعلية، أو خبر/نظام خارجي موثّق بمصدره،
أو موقف كتبه فيصل بنفسه — وتحوّلها لأفكار فيديو تيك توك جاهزة للتصوير.

"""

SIGNAL_IDEAS_RULES = """القاعدة الحاكمة (فوق كل شي): كل فكرة لازم تكون مبنية على الإشارة نفسها
وتذكر الحقيقة/الرقم اللي فيها بشكل صريح. ممنوع منعاً باتاً:
- تخترع رقم أو نسبة أو تاريخ مو موجود بالإشارة.
- تعمّم («٥ نصائح لأصحاب الشقق») بدون ما تستند للإشارة — هذا محتوى بلا قيمة ويُرفض.
- تبالغ أو تحوّل الرقم لادعاء أكبر منه.
إذا الإشارة ما تكفي لفكرة قوية، أرجع أفكار أقل — عدد أقل أفضل من فكرة فاضية.

الجمهور: صنّف كل فكرة إما niche (ملّاك ومشغّلين → عملاء محتملين) أو escape (جمهور عام سعودي → نمو الحساب).
حاول تعطي الاثنين إذا الإشارة تسمح.

أرجع JSON فقط بهذا الشكل (٢-٣ أفكار، كل وحدة زاوية مختلفة فعلاً):
{"ideas": [
  {"hook_spoken": "الكلمات الحرفية أول ٣ ثواني (٥-١٠ كلمات نجدي، cold open، والرقم يُنطق)",
   "visual_title": "العنوان الكبير على الشاشة",
   "visual_sub": "السطر الثاني: يرفع الرهان أو يحدد لمن هذا",
   "angle": "وش الزاوية وليش يوقف يشاهد — سطر أو سطرين",
   "why_it_works": "ليش بتشتغل — اربطها بآلية مثبتة بجملة قصيرة (إجباري)",
   "script": ["نقاط السيناريو بالترتيب مع توقيت تقريبي مثل (٠-٣ث)"],
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


def _stamp(cards, signal=None, story=None, stats=None, guard_novelty=True):
    """Attach the grounding + scoring every v3 card must carry, and drop repeats.

    signal: a validated signal dict (v3 path). story: a studio_stories row (v2 path).
    Returns the cards worth keeping."""
    stats = stats if stats is not None else _learn_stats()
    try:
        recent = db.recent_nkeys() if guard_novelty else []
    except Exception:
        recent = []
    out = []
    for c in cards:
        if signal:
            c["signal_sid"] = signal.get("sid", "")
            c["signal_family"] = signal.get("family", "")
            c["signal_source"] = signal.get("source", "")
            c["signal_text"] = signal.get("fact", "")
            c["signal_url"] = signal.get("url", "")
            c["signal_date"] = signal.get("as_of", "")
        elif story:
            c["signal_sid"] = ""
            c["signal_family"] = "internal"
            c["signal_source"] = "guest_story"
            c["signal_text"] = story.get("angle") or story.get("title") or ""
            c["signal_url"] = ""
            c["signal_date"] = str(story.get("created_at") or "")[:10]
        # F9: predicted strength from what already earns views on this account.
        c["strength"] = learn.strength_of(
            {"trigger_kind": c.get("trigger"), "audience": c.get("audience"),
             "video_type": c.get("video_type"),
             "signal_family": c.get("signal_family"),
             "story_type": (story or {}).get("story_type", "")}, stats)
        # H4: never hand the owner the same angle twice.
        key = engine.novelty_key("%s %s" % (c.get("visual_title", ""), c.get("angle", "")))
        if guard_novelty and not engine.is_novel(key, recent):
            continue
        c["nkey"] = key
        recent.append(key)
        out.append(c)
    return out


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


def generate_for_signal(sid, n_hint=3):
    """Turn ONE stored signal into idea cards. The v3 main path."""
    sig = db.signal(sid)
    if not sig:
        return []
    stats = _learn_stats()
    system = (SIGNAL_IDEAS_SYSTEM_HEAD + PLAYBOOK + "\n\n" + WHY_MECHANICS + "\n\n" +
              hooks.prompt_block(sig.get("source", "")) + "\n\n" + SIGNAL_IDEAS_RULES)
    body = {"نوع الإشارة": sig.get("family"), "المصدر": sig.get("source"),
            "العنوان": sig.get("title"), "الحقيقة": sig.get("fact"),
            "تفاصيل": sig.get("detail")}
    if sig.get("url"):
        body["رابط المصدر"] = sig["url"]
    if sig.get("as_of"):
        body["تاريخ المصدر"] = sig["as_of"]
    user = ("الإشارة:\n" + json.dumps(body, ensure_ascii=False, indent=1) +
            learn.bias_hint_ar(stats) +
            "\n\nحوّلها لأفكار فيديو حسب القواعد. JSON فقط.")
    raw = HOST.require("claude_json")(system, user, max_tokens=2400,
                                      model=getattr(HOST, "model_premium", None))
    cards = engine.parse_ideas(raw)[:max(1, int(n_hint))]
    cards = _stamp(cards, signal=sig, stats=stats)
    if cards:
        try:
            db.set_signal_status(sig["sid"], "used")
        except Exception:
            pass
    return _persist(cards, story_id=0)


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


def _learn_hint():
    """One-line hint of the archetypes that already earned views for this account, so
    the generator leans into what's proven. Empty until posted+views data exists."""
    try:
        top = db.top_posted_archetypes(3)
    except Exception:
        top = []
    if not top:
        return ""
    parts = ", ".join("%s (%s مشاهدة)" % (t, v) for t, v in top if v)
    if not parts:
        return ""
    return ("\n\nإشارة تعلّم (أفضل أنواع أدّت لك سابقاً): %s — مل للأنواع اللي أثبتت نجاحها "
            "لحسابك إذا ناسبت القصة." % parts)


def generate_for_story(story_id):
    """Generate + persist idea cards for one story. Returns the new cards."""
    s = db.story(story_id)
    if not s:
        return []
    claude_json = HOST.require("claude_json")
    user = ("بطاقة القصة:\n" +
            json.dumps({"العنوان": s["title"], "الزاوية": s.get("angle", ""),
                        "القصة": s["summary"],
                        "التسلسل": s["beats"], "اقتباسات حرفية": s["quotes"],
                        "القوس العاطفي": s["emotion"], "الدرس": s["lesson"],
                        "نوع القصة": s["story_type"]}, ensure_ascii=False, indent=1) +
            _learn_hint() +
            "\n\nحوّلها لأفكار فيديو حسب القواعد. JSON فقط.")
    raw = claude_json(IDEAS_SYSTEM, user, max_tokens=2200,
                      model=getattr(HOST, "model_premium", None))
    cards = _stamp(engine.parse_ideas(raw), story=s)
    return _persist(cards, story_id=story_id)
