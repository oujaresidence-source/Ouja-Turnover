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


SRC_AR = {
    "occupancy": "الإشغال", "pricing": "التسعير", "reviews": "التقييمات", "ops": "العمليات",
    "season": "الموسم", "insider": "من الداخل", "guest_story": "قصة ضيف",
    "regulation": "أنظمة وتراخيص", "market": "سوق السعودية", "global_trend": "اتجاه عالمي",
    "trend": "خبر/ترند", "manual": "موقف مكتوب",
}


def build_digest(stories, top_ideas=None, signals=None, day_cards=None):
    """The morning message, or '' when there's genuinely nothing to say.

    v3 leads with the DAY'S PLAN (what to film today) because that's the question
    Faisal actually wakes up with; the story and the new signals follow as context."""
    stories = [s for s in (stories or []) if s]
    day_cards = [c for c in (day_cards or []) if c]
    signals = [s for s in (signals or []) if s]
    if not (stories or day_cards or signals):
        return ""
    nl = chr(10)
    L = ["🎬 عوجا ستوديو — صباح الخير"]

    if day_cards:
        L += ["", "📅 اللي تصوّره اليوم:"]
        for i, c in enumerate(day_cards[:3], 1):
            L.append("%s. %s" % (i, c.get("visual_title") or ""))
            if c.get("hook_spoken"):
                L.append("   🎤 «%s»" % c["hook_spoken"])
            if c.get("signal_text"):
                L.append("   📌 مبنية على: %s" % c["signal_text"][:140])

    hot = [s for s in signals if s.get("family") == "external"][:3]
    if hot:
        L += ["", "🌍 إشارات جديدة من برّا:"]
        for s in hot:
            L.append("• [%s] %s" % (SRC_AR.get(s.get("source"), "خبر"), s.get("fact") or ""))
            if s.get("url"):
                L.append("   %s" % s["url"])

    if stories:
        best = stories[0]
        L += ["", "📖 قصة اليوم: %s" % (best.get("title") or "")]
        if best.get("angle"):
            L.append("الزاوية: %s" % best["angle"])
        L.append("النوع: %s · قوة %s/10" % (TYPE_AR.get(best.get("story_type"), "موقف"),
                                            best.get("score", 0)))
        idea = (top_ideas or [None])[0]
        if idea:
            L.append("🎤 ابدأ بـ: «%s»" % idea.get("hook_spoken", ""))
            if idea.get("why_it_works"):
                L.append("💡 ليش بيشتغل: %s" % idea["why_it_works"])

    L += ["", "افتح الاستوديو لكل الأفكار 👉 /studio"]
    return nl.join(L)
