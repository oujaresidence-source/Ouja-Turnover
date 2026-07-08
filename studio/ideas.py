# -*- coding: utf-8 -*-
"""studio.ideas — turns a story card into ready-to-shoot TikTok idea cards.

Premium-model call, playbook-grounded. Each card carries everything the owner
needs at the moment of filming: the spoken hook (the literal first words on
camera), the visual hook (on-screen title + subtitle), the beat script, CTA,
and the audience tag (niche = ملاك/مشغّلين, escape = جمهور عام)."""

import json

from . import db, engine
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
    cards = engine.parse_ideas(raw)
    ts = ""
    try:
        ts = HOST.require("now")().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    out = []
    for c in cards:
        iid = db.add_idea(story_id, c, ts)
        c["id"] = iid
        c["story_id"] = int(story_id)
        out.append(c)
    return out
