# -*- coding: utf-8 -*-
"""studio.notify — pure text builder for the daily morning digest.

bot.py's studio_digest_loop runs the daily scan, generates ideas for the single best
fresh story, then hands (stories, top_ideas) here for the message body. Delivery +
DRY-RUN gating live in bot.py (same pattern as schedule.notify). No network here."""

TYPE_AR = {
    "hero_save": "إنقاذ الموقف", "transformation": "تحوّل", "transparency_numbers": "أرقام وشفافية",
    "day_in_life": "كواليس اليوم", "hospitality_wow": "لمسة ضيافة", "weird_delight": "طلب طريف",
    "heartwarming": "موقف إنساني", "loyal_return": "ضيف رجع", "operational_craft": "سر الصنعة",
    "other": "موقف",
}


def build_digest(stories, top_ideas=None):
    """Return the digest text, or '' when there's nothing worth posting today.
    stories: db rows (best first). top_ideas: parsed idea cards for stories[0]."""
    stories = [s for s in (stories or []) if s]
    if not stories:
        return ""
    nl = chr(10)
    best = stories[0]
    L = ["🎬 قصة اليوم من عوجا ستوديو",
         "",
         "📖 %s" % (best.get("title") or "")]
    if best.get("angle"):
        L.append("الزاوية: %s" % best["angle"])
    L.append("النوع: %s · قوة %s/10" % (TYPE_AR.get(best.get("story_type"), "موقف"),
                                        best.get("score", 0)))
    idea = (top_ideas or [None])[0]
    if idea:
        L += ["", "🎤 ابدأ الفيديو بـ: «%s»" % idea.get("hook_spoken", "")]
        if idea.get("visual_title"):
            L.append("🖥 على الشاشة: %s" % idea["visual_title"])
        if idea.get("why_it_works"):
            L.append("💡 ليش بيشتغل: %s" % idea["why_it_works"])
    extra = stories[1:3]
    if extra:
        L += ["", "➕ كمان اليوم:"]
        L += ["• %s" % (s.get("title") or "") for s in extra]
    L += ["", "افتح الاستوديو لكل الأفكار 👉 /studio"]
    return nl.join(L)
