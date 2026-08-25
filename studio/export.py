# -*- coding: utf-8 -*-
"""studio.export — the whole studio as ONE ready file.

The owner asked for a single document he can open on his phone, read top to bottom,
and film from — no tabs, no filters, no thinking. So this renders everything the
studio currently knows into one Markdown file: today's set, every ready idea with its
full script, what to fix before shooting, the live signal feed with sources, and what
his own numbers have taught the system.

Markdown on purpose: it opens in anything, it reads fine as plain text if a viewer
can't render it, and every script is copy-pasteable straight out of it. An HTML file
looks nicer and is useless the moment Discord hands it to a phone as a download.

`render()` is PURE — it takes already-fetched rows and returns text — so the exact
document can be asserted in tests. `document()` is the thin gathering wrapper.
"""

from . import db, engine, learn, mobile, rank

TRG = {"curiosity": "فضول", "loss": "خسارة", "identity": "هوية", "provocation": "رأي مخالف",
       "authority": "خبرة داخلية", "social_proof": "أرقام ونتائج", "news": "خبر وتوقيت",
       "emotion": "مشاعر"}
AUD = {"niche": "ملّاك ومشغّلين", "escape": "جمهور عام"}
VT = {"talking": "كلام للكاميرا", "tour": "جولة", "before_after": "قبل/بعد",
      "story_voiceover": "سرد بصوت", "onsite": "ميداني", "data_reveal": "كشف أرقام",
      "news_reaction": "رد على خبر"}
SRC = {"occupancy": "الإشغال", "pricing": "التسعير", "reviews": "التقييمات",
       "ops": "العمليات", "season": "الموسم", "insider": "من الداخل",
       "guest_story": "قصة ضيف", "regulation": "أنظمة وتراخيص", "market": "سوق السعودية",
       "global_trend": "اتجاه عالمي", "trend": "خبر/ترند", "manual": "كتبته بنفسك"}

NL = chr(10)


def _card_block(c, n=None):
    """One idea, complete enough to film from without opening anything else."""
    L = []
    head = "### %s%s" % (("%s. " % n) if n else "", c.get("visual_title") or "بدون عنوان")
    L.append(head)
    meta = ["ترتيب **%s٪**" % c.get("rank_score", 0)]
    if c.get("virality") is not None:
        meta.append("بناء **%s٪**" % c["virality"])
    if c.get("id"):
        meta.append("رقم `%s`" % c["id"])
    L.append(" · ".join(meta))
    L.append("")
    if c.get("visual_sub"):
        L.append("**على الشاشة:** %s" % c["visual_sub"])
    L.append("**🎤 أول ما تقول:** «%s»" % (c.get("hook_spoken") or ""))
    if c.get("signal_text"):
        s = "**📌 الإشارة:** %s" % c["signal_text"]
        bits = []
        if c.get("signal_source"):
            bits.append(SRC.get(c["signal_source"], c["signal_source"]))
        if c.get("signal_date"):
            bits.append(c["signal_date"])
        if bits:
            s += "  _(%s)_" % " · ".join(bits)
        L.append(s)
        if c.get("signal_url"):
            L.append("  المصدر: %s" % c["signal_url"])
    if c.get("angle"):
        L.append("**الزاوية:** %s" % c["angle"])
    script = [b for b in (c.get("script") or []) if str(b).strip()]
    if script:
        L.append("")
        L.append("**السكربت:**")
        for i, b in enumerate(script, 1):
            L.append("%s. %s" % (i, b))
    if c.get("cta"):
        L.append("")
        L.append("**🎯 الختام:** %s" % c["cta"])
    if c.get("why_it_works"):
        L.append("**💡 ليش بيشتغل:** %s" % c["why_it_works"])
    fixes = c.get("fixes") or []
    if fixes:
        L.append("")
        L.append("**⚠️ عدّل قبل ما تصوّر:**")
        for f in fixes:
            L.append("- %s" % f)
    tags = [AUD.get(c.get("audience"), c.get("audience") or ""),
            TRG.get(c.get("trigger_kind") or c.get("trigger"), ""),
            VT.get(c.get("video_type"), c.get("video_type") or "")]
    tags = [t for t in tags if t]
    if tags:
        L.append("")
        L.append("`%s`" % "` · `".join(tags))
    if c.get("status") == "posted":
        L.append("_✅ منشور · %s مشاهدة_" % f"{int(c.get('views') or 0):,}")
    elif c.get("status") == "filmed":
        L.append("_🎥 مصوّر، ما نُشر بعد_")
    L.append("")
    return NL.join(L)


def _signal_block(s):
    bits = [SRC.get(s.get("source"), s.get("source") or "")]
    if s.get("as_of"):
        bits.append(s["as_of"])
    line = "- **%s**  _(%s)_" % (s.get("fact") or "", " · ".join([b for b in bits if b]))
    if s.get("detail"):
        line += NL + "  %s" % s["detail"]
    if s.get("url"):
        line += NL + "  المصدر: %s" % s["url"]
    return line


def render(today_cards, other_cards, signals, stats, generated_at="",
           link="", day=""):
    """The whole document. Pure: same inputs, same bytes."""
    today_cards = today_cards or []
    other_cards = other_cards or []
    signals = signals or []
    stats = stats or {"n": 0, "mean": 0, "dims": {}}

    L = ["# 🎬 استوديو عوجا — كل الأفكار", ""]
    L.append("**آخر تحديث:** %s  (بتوقيت الرياض)" % (generated_at or "—"))
    if link:
        L.append("**الصفحة الحيّة (دايماً أحدث من هالملف):** %s" % link)
    L.append("")
    posted = [c for c in other_cards if c.get("status") == "posted"]
    L.append("**الملخص:** %s فكرة جاهزة · %s إشارة حيّة · %s فيديو مسجّل"
             % (len(today_cards) + len([c for c in other_cards
                                        if c.get("status") in ("new", "shortlisted")]),
                len(signals), stats.get("n", 0)))
    L.append("")
    L.append("> الترتيب من أدائك أنت أولاً، بعدها بناء الفكرة، بعدها قوة الإشارة وطزاجتها.")
    L.append("> أي فكرة بدون «الإشارة» تحتها = ما نبنيها، وهذا مقصود.")
    L.append("")
    L.append("---")
    L.append("")

    L.append("## 📅 صوّر هذي اليوم%s" % ((" — %s" % day) if day else ""))
    L.append("")
    if today_cards:
        for i, c in enumerate(today_cards, 1):
            L.append(_card_block(c, i))
    else:
        L.append("_ما فيه خطة لليوم بعد — شغّل الأمر مرة ثانية بعد ما تتجمع إشارات._")
        L.append("")

    fresh = [c for c in other_cards if c.get("status") in ("new", "shortlisted")]
    L.append("---")
    L.append("")
    L.append("## 💡 باقي الأفكار الجاهزة (%s)" % len(fresh))
    L.append("")
    if fresh:
        for c in fresh:
            L.append(_card_block(c))
    else:
        L.append("_الرف فاضي._")
        L.append("")

    ext = [s for s in signals if s.get("family") == "external"]
    other = [s for s in signals if s.get("family") != "external"]
    L.append("---")
    L.append("")
    L.append("## 📡 الإشارات الحيّة")
    L.append("")
    if ext:
        L.append("### 🌍 من برّا — أخبار وأنظمة وسوق")
        L.append("")
        for s in ext:
            L.append(_signal_block(s))
        L.append("")
    if other:
        L.append("### 🏠 من بيانات عوجا")
        L.append("")
        for s in other:
            L.append(_signal_block(s))
        L.append("")
    if not signals:
        L.append("_ما فيه إشارات._")
        L.append("")

    L.append("---")
    L.append("")
    L.append("## 📈 وش يشتغل لحسابك")
    L.append("")
    if not stats.get("n"):
        L.append("_ما فيه بيانات كافية. كل ما تسجّل فيديو نشرته بمشاهداته، الترتيب يصير أدق._")
    else:
        L.append("**%s** فيديو مسجّل · متوسط **%s** مشاهدة"
                 % (stats["n"], f"{int(stats.get('mean') or 0):,}"))
        L.append("")
        ins = learn.insights_ar(stats)
        if ins:
            for t in ins:
                L.append("- %s" % t)
        else:
            L.append("_لسا ما فيه فرق واضح — نحتاج %s فيديوهات على الأقل بكل نوع._"
                     % learn.MIN_SAMPLE)
    L.append("")
    if posted:
        L.append("### 🚀 اللي نشرته")
        L.append("")
        for c in sorted(posted, key=lambda x: -(int(x.get("views") or 0)))[:20]:
            L.append("- **%s** — %s مشاهدة"
                     % (c.get("visual_title") or "", f"{int(c.get('views') or 0):,}"))
        L.append("")
    L.append("---")
    L.append("")
    L.append("_وُلّد آلياً من استوديو عوجا. الأفكار من محادثات وبيانات حقيقية — بدون أسماء ضيوف._")
    return NL.join(L)


def document():
    """Gather + render the current state. Returns (text, filename)."""
    try:
        now = mobile._now_iso()
    except Exception:
        now = ""
    day = now[:10]
    stats = learn.stats(db.learn_rows())
    today_cards = rank.rank(db.plan_for(day), stats, day)
    today_ids = {c.get("id") for c in today_cards}
    rest = [c for c in db.ideas(limit=400) if c.get("id") not in today_ids]
    for c in rest:
        c.setdefault("signal_strength", 50)
    other_cards = rank.rank(rest, stats, day)
    signals = [s for s in db.signals(limit=200) if s.get("status") != "hidden"]
    for s in signals:
        s["age_days"] = engine.freshness_days(s.get("as_of"), day)
    link = ""
    try:
        link = mobile.share_url("today", _base())
    except Exception:
        pass
    text = render(today_cards, other_cards, signals, stats,
                  generated_at=now, link=link, day=day)
    return text, "ouja-studio-%s.md" % (day or "latest")


def _base():
    """Public site base for the live link. Wired as a CALLABLE by bot.py because the
    URL is auto-captured from a real request and isn't known at wire time."""
    from .host import HOST
    v = getattr(HOST, "public_base", "")
    try:
        return (v() if callable(v) else v) or ""
    except Exception:
        return ""
