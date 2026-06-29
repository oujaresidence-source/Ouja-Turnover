# -*- coding: utf-8 -*-
# brain/playbook.py — Ouja Elite (Saudi-premium, v5)
# 20 trigger-based, LINK-DRIVEN campaigns. NEVER name a unit or a date.
# Elevated Saudi hospitality register + light Najdi warmth. Button -> oujares.com/elite
# The ONLY variable is {{1}} = first name.
#
# This file is the single source of truth for the message TEXT. The decision layer
# (brain.triggers + brain.cards) reads CAMPAIGNS[code] for the copy and the small set of
# structural fields (template_name / category / trigger / audience / button). It does NOT
# merge a unit or a date into anything — every CTA is the same URL to /elite.

ELITE_URL = "https://oujares.com/elite"
OPT_OUT_AR = "للإيقاف أرسل: إيقاف"
OPT_OUT_EN = "Reply STOP to opt out"
BTN_AR = "افتح قائمتي"
BTN_EN = "Open my list"

CAMPAIGNS = {

"HEATWAVE": {
  "template_name": "elite_heatwave", "category": "MARKETING",
  "trigger": "Months Jun–Sep (peak heat)", "audience": "all 761",
  "ar": {"header": "من الحرّ إلى أجواء تريّح", "body": "حياك {{1}}، والجو برّا نار. خصّصنا لك أجواء هادئة وباردة تنفض بها عن نفسك زحمة اليوم. قائمتك بأسعار الأعضاء بين يديك — اختر متنفّسك."},
  "en": {"header": "From the heat to somewhere calm", "body": "Hi {{1}}, it's blazing outside. We've set aside a cool, calm space to take the day off your shoulders. Your members' list is at your fingertips — choose your escape."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "نورة"}, "sample_en": {"1": "Noura"},
},
"PERFECT-WEATHER": {
  "template_name": "elite_perfect_weather", "category": "MARKETING",
  "trigger": "Months Dec–Feb (mild season)", "audience": "all 761",
  "ar": {"header": "الجو يستاهل تطلّع له", "body": "حياك {{1}}، أخيراً الأجواء صفت وما تتعوّض. اطلع وغيّر جوّك بمكان يليق باللحظة. قائمتك بأسعار الأعضاء بانتظارك."},
  "en": {"header": "Weather worth stepping out for", "body": "Hi {{1}}, the weather's finally perfect and it won't last. Step out and change your scene somewhere that fits the moment. Your members' list is waiting."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "فهد"}, "sample_en": {"1": "Fahad"},
},
"MIDWEEK-RESET": {
  "template_name": "elite_midweek_reset", "category": "MARKETING",
  "trigger": "Any midweek (Sun–Wed)", "audience": "all 761",
  "ar": {"header": "ليلة تخصّك أنت", "body": "حياك {{1}}، أحياناً وسط الأسبوع يطوّل، وتستاهل ليلة هدوء تخصّك أنت بس. دلّل نفسك بأجواء تريّح بالك — قائمتك جاهزة على ذوقك."},
  "en": {"header": "A night that's just yours", "body": "Hi {{1}}, sometimes midweek drags, and you deserve one quiet night that's just yours. Treat yourself to some calm — your list is ready, made to your taste."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "سارة"}, "sample_en": {"1": "Sara"},
},
"WORK-FROM-ELSEWHERE": {
  "template_name": "elite_work_elsewhere", "category": "MARKETING",
  "trigger": "Any midweek; corporate/remote", "audience": "all 761",
  "ar": {"header": "بدّل زاويتك ليوم", "body": "حياك {{1}}، مو شرط تنجز من نفس المكان كل يوم. أجواء هادئة تشتغل فيها وترتاح، وسط الأسبوع وبأسعار الأعضاء. قائمتك بين يديك."},
  "en": {"header": "Switch your view for a day", "body": "Hi {{1}}, you don't have to get things done from the same place every day. A calm space to work and unwind, midweek, at members' rates. Your list is at your fingertips."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "عبدالله"}, "sample_en": {"1": "Abdullah"},
},
"LONG-WEEKEND": {
  "template_name": "elite_long_weekend", "category": "MARKETING",
  "trigger": "3–7 days before a public-holiday long weekend", "audience": "all 761",
  "ar": {"header": "الإجازة قرّبت، خلّك جاهز", "body": "حياك {{1}}، الإجازة على الأبواب والكل بيتحرك، واللي يسبق ياخذ راحته. طل على قائمتك بأسعار الأعضاء قبل لا تمتلئ."},
  "en": {"header": "A break's near — be ready", "body": "Hi {{1}}, the holiday's almost here and everyone's about to move; the early ones get the calm. Check your members' list before it fills."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "ريم"}, "sample_en": {"1": "Reem"},
},
"NATIONAL-DAY": {
  "template_name": "elite_national_day", "category": "MARKETING",
  "trigger": "~Sep 23 (National Day)", "audience": "all 761",
  "ar": {"header": "كل عام والوطن بخير", "body": "حياك {{1}}، اليوم الوطني قرّب، وأحلى احتفال هدوء بين أهلك بمكان يخصّك. قائمتك بأسعار الأعضاء بانتظارك — احتفل على طريقتك."},
  "en": {"header": "Happy National Day", "body": "Hi {{1}}, National Day's around the corner, and the best celebration is a calm one with your people, somewhere that's yours. Your members' list is waiting — celebrate your way."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "ماجد"}, "sample_en": {"1": "Majed"},
},
"FOUNDING-DAY": {
  "template_name": "elite_founding_day", "category": "MARKETING",
  "trigger": "~Feb 22 (Founding Day)", "audience": "all 761",
  "ar": {"header": "يوم التأسيس", "body": "حياك {{1}}، بمناسبة يوم التأسيس عسى أيامك كلها عز. ولو ودّك تقضيها بهدوء، قائمتك بأسعار الأعضاء بين يديك. اختر اللي يناسبك."},
  "en": {"header": "Founding Day", "body": "Hi {{1}}, with Founding Day here, may your days be proud ones. And if you'd like to spend it quietly, your members' list is at your fingertips. Pick what suits you."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "خالد"}, "sample_en": {"1": "Khalid"},
},
"EID": {
  "template_name": "elite_eid", "category": "MARKETING",
  "trigger": "Eid al-Fitr (~Mar) & Eid al-Adha (~May)", "audience": "all 761",
  "ar": {"header": "عيدك مبارك", "body": "حياك {{1}}، عيدك مبارك وعساك من عوّاده. ولو بغيت تاخذ نفس بعيد عن الزحمة بين الزيارات، قائمتك جاهزة ومكانك بانتظارك."},
  "en": {"header": "Eid Mubarak", "body": "Hi {{1}}, Eid Mubarak — may you see many more. And if you'd like a breather away from the crowd between visits, your list is ready and your place is waiting."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "أحمد"}, "sample_en": {"1": "Ahmed"},
},
"RAMADAN": {
  "template_name": "elite_ramadan", "category": "MARKETING",
  "trigger": "During Ramadan (~Feb 18 onward)", "audience": "all 761",
  "ar": {"header": "لياليك في رمضان", "body": "حياك {{1}}، لرمضان جوّه الخاص، ولياليه تستاهل مكان هادي قريب منك. لو ودّك سهرة أهدى، قائمتك بأسعار الأعضاء بانتظارك."},
  "en": {"header": "Your Ramadan nights", "body": "Hi {{1}}, Ramadan has its own spirit, and its nights deserve a calm place close by. If you'd like a quieter evening, your members' list is waiting."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "لمى"}, "sample_en": {"1": "Lama"},
},
"SCHOOL-BREAK": {
  "template_name": "elite_school_break", "category": "MARKETING",
  "trigger": "School holidays / exam season", "audience": "all 761 (families)",
  "ar": {"header": "الإجازة المدرسية", "body": "حياك {{1}}، العيال بإجازة والبيت صار زحمة. وش رايك بمتنفّس هادي وسط الأسبوع لك أو للعائلة؟ قائمتك جاهزة، اختر مهربك."},
  "en": {"header": "School's out", "body": "Hi {{1}}, the kids are off and the house is lively. How about a calm escape midweek, for you or the whole family? Your list is ready — pick your getaway."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "طلال"}, "sample_en": {"1": "Talal"},
},
"NEW-YEAR": {
  "template_name": "elite_new_year", "category": "MARKETING",
  "trigger": "Hijri New Year (~Jun 16) / Jan 1", "audience": "all 761",
  "ar": {"header": "سنة جديدة، بداية أهدى", "body": "حياك {{1}}، كل سنة وإنت طيّب. خلّ بداية سنتك راحة وهدوء تكافئ بها نفسك. قائمتك بأسعار الأعضاء بين يديك — ابدأها صح."},
  "en": {"header": "New year, calmer start", "body": "Hi {{1}}, happy new year. Begin it with some calm and a little reward to yourself. Your members' list is at your fingertips — start it right."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "هند"}, "sample_en": {"1": "Hind"},
},
"PAYDAY-DROPPED": {
  "template_name": "elite_payday", "category": "MARKETING",
  "trigger": "Days 27–1 (salary landed)", "audience": "all 761",
  "ar": {"header": "الراتب نزل، دلّل نفسك", "body": "حياك {{1}}، الراتب نزل وتعبت عليه، فتستاهل تدلّل نفسك ليلة. قائمتك بأسعار الأعضاء جاهزة — اختر اللي على كيفك وإنت مرتاح."},
  "en": {"header": "Payday's in — treat yourself", "body": "Hi {{1}}, payday's landed and you earned every riyal, so treat yourself to a night. Your members' list is ready — pick what you like, with an easy mind."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "بدر"}, "sample_en": {"1": "Badr"},
},
"END-OF-MONTH": {
  "template_name": "elite_end_of_month", "category": "MARKETING",
  "trigger": "Days 20–26 (pre-payday)", "audience": "all 761",
  "ar": {"header": "نعرف إن الشهر طوّل", "body": "حياك {{1}}، نعرف إن آخر الشهر دايم أثقل شوي، وما يصير نحرمك راحتك. خفّينا لك الأسعار خصيصاً لين ينزل الراتب. طل على قائمتك وبالك مرتاح."},
  "en": {"header": "We know the month's been long", "body": "Hi {{1}}, we know the end of the month is always a bit heavier, and we don't want that to keep you from a break. We've eased your rates specially until payday. Browse your list with an easy mind."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "نوف"}, "sample_en": {"1": "Nouf"},
},
"DORMANT-COMEBACK": {
  "template_name": "elite_comeback", "category": "MARKETING",
  "trigger": "Dormant 60–365 days", "audience": "448 dormant",
  "ar": {"header": "وحشتنا", "body": "حياك {{1}} 🤍 صار لنا زمن ما شفناك ووحشتنا. بابك ما تسكّر، وأسعار الأعضاء بانتظارك. ارجع لنا، تستاهل أحلى استقبال."},
  "en": {"header": "We've missed you", "body": "Hi {{1}} 🤍 it's been a while and we've missed you. Your door never closed, and your members' rates are waiting. Come back — you deserve the warmest welcome."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "ياسر"}, "sample_en": {"1": "Yasser"},
},
"FIRST-TIMER": {
  "template_name": "elite_first_timer", "category": "MARKETING",
  "trigger": "1–2 stays, recent", "audience": "new repeaters",
  "ar": {"header": "صرت من جماعتنا", "body": "حياك {{1}}، عجبتنا إقامتك وحبينا نضمّك لأعضائنا — قائمة بأسعار وخصوصية ما تلقاها برّا. هذي قائمتك، على راحتك."},
  "en": {"header": "You're one of us now", "body": "Hi {{1}}, we loved having you, and we'd like to bring you in as a member — a list with prices and privacy you won't find outside. This is your list now, at your ease."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "دانة"}, "sample_en": {"1": "Dana"},
},
"LOYAL-THANKS": {
  "template_name": "elite_loyal_thanks", "category": "MARKETING",
  "trigger": "Turaif + Gold", "audience": "317 top members",
  "ar": {"header": "إنت من أوفى ناسنا", "body": "حياك {{1}}، وفاك يفرق عندنا، وعشان كذا قائمتك دايم أهدى وأقرب. فتحناها لك تقديراً لك — تفضّل اختر اللي يعجبك."},
  "en": {"header": "One of our most loyal", "body": "Hi {{1}}, your loyalty means a lot to us, so your list is always the quietest and the closest. We've opened it as a thank-you — go ahead and choose."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "سعود"}, "sample_en": {"1": "Saud"},
},
"LAST-MINUTE": {
  "template_name": "elite_last_minute", "category": "MARKETING",
  "trigger": "Any; last-minute bookers (lead ≤2d)", "audience": "last-minute segment",
  "ar": {"header": "قرّرت الحين؟ تمام", "body": "حياك {{1}}، لو جاك على بالك تغيّر جوّك الحين، ما يحتاج تخطيط. قائمتك مفتوحة وجاهزة — اختر وتعال، بهالبساطة."},
  "en": {"header": "Decided just now? Perfect", "body": "Hi {{1}}, if the mood strikes for a change of scene right now, no planning needed. Your list is open and ready — pick one and come, simple as that."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "مشعل"}, "sample_en": {"1": "Mishal"},
},
"BIRTHDAY": {
  "template_name": "elite_birthday", "category": "MARKETING",
  "trigger": "Known DOB / first-stay anniversary", "audience": "guests with date on file",
  "ar": {"header": "يومك يستاهل", "body": "حياك {{1}}، مناسبتك قرّبت وتستاهل تحتفي بنفسك بهدوء بعيد عن الزحمة. جهّزنا لك قائمتك وفيها لمسة على ذوقك. خلّك مميّز."},
  "en": {"header": "Your day deserves it", "body": "Hi {{1}}, your day's coming up and you deserve to mark it quietly, away from the noise. Your list is ready with a little touch for you. Make it special."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "جواهر"}, "sample_en": {"1": "Jawaher"},
},
"POST-STAY": {
  "template_name": "elite_post_stay", "category": "MARKETING",
  "trigger": "Checked out ≤2–3 days ago", "audience": "recent guests",
  "ar": {"header": "نوّرتنا، وبابك مفتوح", "body": "حياك {{1}}، نوّرتنا بإقامتك وعسى عجبتك. متى ما ودّك ترجع، قائمتك بانتظارك على طول. لا تطوّل علينا."},
  "en": {"header": "It was a pleasure", "body": "Hi {{1}}, it was a pleasure having you, and we hope you enjoyed it. Whenever you fancy coming back, your list is right there. Don't be a stranger."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "يوسف"}, "sample_en": {"1": "Yousef"},
},
"GIFT-SOMEONE": {
  "template_name": "elite_gift", "category": "MARKETING",
  "trigger": "Any (gifting angle)", "audience": "all 761",
  "ar": {"header": "فاجئ أحد يستاهل", "body": "حياك {{1}}، أحياناً أحلى هدية ليلة هدوء لأحد تحبّه. اختر من قائمتك وأهدِها باسمك. خلّك سبب لابتسامة أحد."},
  "en": {"header": "Surprise someone special", "body": "Hi {{1}}, sometimes the best gift is a calm night for someone you love. Choose from your list and gift it in your name. Be the reason behind someone's smile."},
  "footer_ar": OPT_OUT_AR, "footer_en": OPT_OUT_EN,
  "button": {"type": "URL", "text_ar": BTN_AR, "text_en": BTN_EN, "url": ELITE_URL},
  "sample_ar": {"1": "ريماس"}, "sample_en": {"1": "Rimas"},
},
}


# Tier ordering (Quarantine excluded everywhere; kept for the tie-breaker / segment weighting).
TIER_RANK = {"Prospect": 0, "Silver": 1, "Gold": 2, "Turaif": 3, "Quarantine": -1}

# Stable display / iteration order = catalogue insertion order.
CODES = list(CAMPAIGNS.keys())


def get(code):
    return CAMPAIGNS.get(code)


def body(code, lang):
    """The send body for a campaign in 'ar'/'en' (the {{1}} name variable stays intact)."""
    c = CAMPAIGNS.get(code) or {}
    return ((c.get(lang) or {}).get("body")) or ""


def button_url(code):
    return ((CAMPAIGNS.get(code) or {}).get("button") or {}).get("url") or ELITE_URL


def assembled_message(code, lang):
    """The full human-readable message an agent loads into Karzoun: header, body ({{1}} kept for
    Karzoun's per-recipient merge), footer, and the elite button URL. Never names a unit or date."""
    c = CAMPAIGNS.get(code) or {}
    block = c.get(lang) or {}
    btn = c.get("button") or {}
    nl = "\n"
    parts = []
    if block.get("header"):
        parts.append(block["header"])
    if block.get("body"):
        parts.append(block["body"])
    foot = c.get("footer_%s" % lang)
    if foot:
        parts.append(foot)
    btn_text = btn.get("text_%s" % lang) or (BTN_AR if lang == "ar" else BTN_EN)
    parts.append("%s: %s" % (btn_text, btn.get("url") or ELITE_URL))
    return (nl + nl).join(parts)


# ---------------------------------------------------------------------------
# Karzoun / Meta one-time template submission catalogue.
# Each of the 20 campaigns exports both languages — the RAW header/body/footer/button_url with the
# {{1}} variable INTACT (the text the owner pastes into Meta once). 40 rows total.
# ---------------------------------------------------------------------------
TEMPLATE_CSV_COLUMNS = ["template_name", "category", "language", "header", "body",
                        "footer", "button_text", "button_url", "trigger"]


def _tpl_rows(code, camp):
    rows = []
    btn = camp.get("button") or {}
    for lang in ("ar", "en"):
        block = camp.get(lang) or {}
        rows.append([
            camp.get("template_name", code),
            camp.get("category", "MARKETING"),
            lang,
            block.get("header") or "",
            block.get("body") or "",
            camp.get("footer_%s" % lang) or "",
            btn.get("text_%s" % lang) or "",
            btn.get("url") or ELITE_URL,
            camp.get("trigger") or "",
        ])
    return rows


def build_templates_csv():
    """All 20 campaigns × 2 languages (40 rows) as a Meta/Karzoun one-time submission CSV.
    Variables are left as {{1}} (never merged). Returns (filename, text). Read-only."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TEMPLATE_CSV_COLUMNS)
    for code, camp in CAMPAIGNS.items():
        for row in _tpl_rows(code, camp):
            w.writerow(row)
    return "ouja_elite_templates.csv", buf.getvalue()


def _selftest():
    """Sanity: 20 campaigns, link-driven, {{1}}-only, every CTA == /elite, no unit/date tokens."""
    assert len(CAMPAIGNS) == 20, "expected 20 campaigns, got %d" % len(CAMPAIGNS)
    import re
    bad_token = re.compile(r"\{\{[2-9]\}\}|\{unit\}|\{date|\{dates\}|\{wd\}")
    for code, c in CAMPAIGNS.items():
        for lang in ("ar", "en"):
            b = (c.get(lang) or {}).get("body") or ""
            assert b.strip(), "%s/%s empty body" % (code, lang)
            assert "{{1}}" in b, "%s/%s missing {{1}}" % (code, lang)
            assert not bad_token.search(b), "%s/%s names a unit/date/extra var" % (code, lang)
        assert button_url(code) == ELITE_URL, "%s CTA is not the elite URL" % code
    return True


if __name__ == "__main__":
    print("playbook v5 selftest:", _selftest())
