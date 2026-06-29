"""
brain.playbook — the campaign catalogue for the Weekday-Gap Engine (build spec §4).

The original super-prompt shipped the message copy in a separate file that never reached the
repo, so this module is the first-draft AR (Najdi) + EN copy + the per-campaign targeting filter
+ the why-line template. Owner edits land here (or, later, in the Settings tab). Tokens merged at
card-build time: {name} {unit} {wd} {dates} {nights}. All offers are time-boxed, unit-specific and
anti-wait ("a night opened / held for you") — never "sale", never recurring (§HARD RULES 7).

Targeting filter keys (interpreted by brain.cards; absent signals degrade gracefully to no-op):
  tier_min          minimum tier (Turaif>Gold>Silver>Prospect)
  tier_only         exact tier required (e.g. Turaif-only)
  weekday_pattern   require the Sun–Wed regular flag
  days_since_max/min recency band
  score_min         minimum RFM score
  stays_min         minimum realized stays
  nights_min        long-stay history (max single-stay nights)
  preferred_match   member.preferred_unit == the gap's unit
  prospect_ok       allow single-stay Prospects (win-back / welcome-back pools)

offer_mode: relationship (no discount) | value_add (≤ceiling% direct) | deeper (deeper % only on
a P1 dead night, vetted score≥min, never below floor) | upgrade (protected units: access/upgrade,
never a price cut). A protected unit ALWAYS forces upgrade, overriding offer_mode (§HARD RULES 2/3).
"""

# Order matters only for display; selection is by gap class (see CLASS_PRIMARY).
CAMPAIGNS = {
    "TONIGHT": {
        "name_ar": "الليلة", "name_en": "Tonight",
        "fires_on": ["TONIGHT"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver", "days_since_max": 120},
        "why_ar": "فاضية الليلة في {unit}؛ {n} ضيوف منتظمين يحجزون بسرعة وما تواصلنا معهم من {d} يوم.",
        "why_en": "Empty tonight on {unit}; {n} last-minute midweek regulars, not contacted in {d}d.",
        "msg_ar": "مساك الله بالخير {name} 👋 فتحت لك ليلة الليلة في {unit} ({dates}). لو يناسبك نثبتها باسمك الحين — قول لي وأرتّبها.",
        "msg_en": "Hi {name} 👋 a night just opened tonight at {unit} ({dates}). If it suits you I'll hold it in your name now — just say the word.",
    },
    "TOMORROW": {
        "name_ar": "بكرة", "name_en": "Tomorrow",
        "fires_on": ["TOMORROW"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver", "days_since_max": 150},
        "why_ar": "فاضية بكرة في {unit}؛ نعرضها أول على {n} من أسرع الضيوف ردًّا.",
        "why_en": "Free tomorrow on {unit}; offering first to {n} fast-responders.",
        "msg_ar": "هلا {name} 🌟 {unit} فاضية بكرة ({dates}) وحبيت أعطيك الأولوية قبل ما أنزلها. تبيها باسمك؟",
        "msg_en": "Hey {name} 🌟 {unit} is open tomorrow ({dates}) and I wanted to give you first pick before it goes out. Want it held for you?",
    },
    "ORPHAN-NIGHT": {
        "name_ar": "ليلة يتيمة", "name_en": "Orphan night",
        "fires_on": ["ORPHAN-NIGHT"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver", "preferred_boost": True, "days_since_max": 150},
        "why_ar": "ليلة {wd} وحيدة بين حجزين في {unit}؛ {n} منتظمين غالبًا ياخذونها.",
        "why_en": "Single {wd} night between two bookings on {unit}; {n} regulars likely to grab it.",
        "msg_ar": "{name} عندي ليلة {wd} وحدة فاضية في {unit} ({dates}) بين حجزين — مناسبة لو تبي سهرة قصيرة. أحجزها لك؟",
        "msg_en": "{name} I've got one open {wd} night at {unit} ({dates}) wedged between two stays — perfect for a quick getaway. Shall I book it for you?",
    },
    "MIDWEEK-2": {
        "name_ar": "ليلتين منتصف الأسبوع", "name_en": "Midweek two-night",
        "fires_on": ["MIDWEEK-2"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver"},
        "why_ar": "فجوة ليلتين منتصف الأسبوع في {unit}؛ {n} ضيوف ذهبيين منتظمين بالأيام العادية.",
        "why_en": "Two-night midweek gap on {unit}; {n} Gold weekday regulars.",
        "msg_ar": "هلا {name} 👋 {unit} فاضية ليلتين ({dates}) — هدوء منتصف الأسبوع اللي تحبه. أرتّبها لك؟",
        "msg_en": "Hi {name} 👋 {unit} is open for two nights ({dates}) — the quiet midweek stay you like. Want me to set it up?",
    },
    "LONG-GAP": {
        "name_ar": "فجوة طويلة", "name_en": "Long gap",
        "fires_on": ["LONG-GAP"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver", "nights_min": 3},
        "why_ar": "فترة {nights} ليالٍ منتصف الأسبوع في {unit}؛ {n} ضيوف إقامات طويلة.",
        "why_en": "{nights}-night midweek stretch on {unit}; {n} long-stay guests.",
        "msg_ar": "{name} عندنا فترة مفتوحة في {unit} ({dates}) تكفي إقامة مريحة. لك ترتيب خاص لو حابب — أقولك التفاصيل؟",
        "msg_en": "{name} we've a longer open stretch at {unit} ({dates}) — room for a proper stay. Happy to arrange something special; want the details?",
    },
    "THIS-WEEK": {
        "name_ar": "هالأسبوع", "name_en": "This week",
        "fires_on": ["THIS-WEEK"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver"},
        "why_ar": "ليالي منتصف الأسبوع مفتوحة في {unit}؛ {n} منتظمين موثوقين.",
        "why_en": "Open midweek nights on {unit}; {n} trusted regulars.",
        "msg_ar": "هلا {name} 🌟 فيه ليالي منتصف الأسبوع فاضية في {unit} ({dates}). تبي أحجز لك وحدة منها؟",
        "msg_en": "Hi {name} 🌟 a few midweek nights are open at {unit} ({dates}). Want me to grab one for you?",
    },
    "LAST-CHANCE": {
        "name_ar": "آخر فرصة", "name_en": "Last chance",
        "fires_on": ["LAST-CHANCE"], "offer_mode": "value_add",
        "filter": {"tier_min": "Silver"},
        "why_ar": "نداء أخير على {unit} {wd}؛ {n} ما ردّوا بعد.",
        "why_en": "Final call on {unit} {wd}; {n} who didn't reply yet.",
        "msg_ar": "{name} آخر تذكير — {unit} لسّا فاضية {wd} ({dates}) وراح تنحجز قريب. تبيها باسمك قبل لا تروح؟",
        "msg_en": "{name} last nudge — {unit} is still open {wd} ({dates}) and likely to go soon. Want it held before it does?",
    },
    "YOUR-UNIT-FREE": {
        "name_ar": "شقتك المفضلة فاضية", "name_en": "Your unit is free",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"preferred_match": True},
        "why_ar": "شقتهم المفضّلة {unit} فاضية يوم {wd} المعتاد؛ {n} أوفياء — علاقة بدون خصم.",
        "why_en": "Their favourite {unit} is open on their usual {wd}; {n} loyalists — relationship, no discount.",
        "msg_ar": "{name} 🤍 {unit} المفضّلة عندك فاضية {wd} ({dates}). حبيت أخبرك أول بأول — تبيها؟",
        "msg_en": "{name} 🤍 your favourite {unit} is open {wd} ({dates}). Wanted you to know first — want it?",
    },
    "SIMILAR-UNIT": {
        "name_ar": "شقة مشابهة", "name_en": "Similar unit",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"tier_min": "Silver"},
        "why_ar": "شقتهم المعتادة محجوزة؛ {unit} قريبة منها بنفس المنطقة وفاضية منتصف الأسبوع.",
        "why_en": "Their usual is taken; {unit} is a close match and open midweek.",
        "msg_ar": "{name} شقتك المعتادة محجوزة هاليومين، بس {unit} قريبة منها ونفس الأجواء وفاضية ({dates}). أرشّحها لك — تبيها؟",
        "msg_en": "{name} your usual place is taken those days, but {unit} is a close match with the same vibe and open ({dates}). I'd recommend it — interested?",
    },
    "WELCOME-BACK": {
        "name_ar": "وحشتنا", "name_en": "Welcome back",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"days_since_min": 60, "days_since_max": 120, "score_min": 50, "prospect_ok": True},
        "why_ar": "{n} ضيوف طيبين هدّوا من شهرين لأربعة؛ دعوة لطيفة منتصف الأسبوع.",
        "why_en": "{n} good guests quiet 2–4 months; gentle midweek invite.",
        "msg_ar": "{name} وحشتنا والله 🤍 صار لك فترة. {unit} فاضية منتصف الأسبوع ({dates}) لو تبي ترجع تستجمّ. نرتّبها لك؟",
        "msg_en": "{name} we've missed you 🤍 it's been a while. {unit} is open midweek ({dates}) if you'd like to come unwind. Shall we arrange it?",
    },
    "WIN-BACK": {
        "name_ar": "نرجّعك", "name_en": "Win back",
        "fires_on": ["ANY"], "offer_mode": "value_add",
        "filter": {"days_since_min": 120, "days_since_max": 365, "score_min": 50, "prospect_ok": True},
        "why_ar": "{n} ضيوف طيبين غابوا من ٤ شهور لسنة؛ دعوة أقوى لمرة وحدة منتصف الأسبوع.",
        "why_en": "{n} lapsed good guests; stronger one-time midweek invite.",
        "msg_ar": "{name} صار لك زمان عنّا 🤍 جهّزنا لك ليلة منتصف الأسبوع في {unit} ({dates}) بترتيب خاص لمرة وحدة. ترجع لنا؟",
        "msg_en": "{name} it's been too long 🤍 we've set aside a midweek night at {unit} ({dates}) with a one-time special just for you. Come back to us?",
    },
    "WEEKDAY-REGULAR": {
        "name_ar": "منتظم منتصف الأسبوع", "name_en": "Weekday regular",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"weekday_pattern": True, "stays_min": 3},
        "why_ar": "{n} يحجزون دائمًا منتصف الأسبوع؛ {unit} فاضية {wd}.",
        "why_en": "{n} who always book midweek; {unit} open {wd}.",
        "msg_ar": "{name} 👋 عارفين إنك تفضّل منتصف الأسبوع — {unit} فاضية {wd} ({dates}). أثبّتها باسمك؟",
        "msg_en": "{name} 👋 we know midweek is your thing — {unit} is open {wd} ({dates}). Hold it in your name?",
    },
    "POST-CHECKOUT": {
        "name_ar": "بعد المغادرة", "name_en": "Post-checkout",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"days_since_max": 2, "score_min": 50},
        "why_ar": "ضيوف غادروا للتو ومبسوطين؛ دعوة لطيفة «ارجع منتصف الأسبوع».",
        "why_en": "Just-departed happy guests; soft 'come back midweek'.",
        "msg_ar": "{name} عسى إقامتك عجبتك 🤍 إذا حاب ترجع، {unit} فاضية منتصف الأسبوع ({dates}). بابنا مفتوح لك.",
        "msg_en": "{name} hope you enjoyed your stay 🤍 whenever you'd like to return, {unit} is open midweek ({dates}). Our door's always open.",
    },
    "UPGRADE-MIDWEEK": {
        "name_ar": "ترقية منتصف الأسبوع", "name_en": "Midweek upgrade",
        "fires_on": ["PROTECTED"], "offer_mode": "upgrade",
        "filter": {"tier_min": "Gold"},
        "why_ar": "{unit} (محميّة) فاضية {wd}؛ نعرض ترقية، بدون أي تخفيض سعر.",
        "why_en": "{unit} (protected) empty {wd}; offer upgrade, never a price cut.",
        "msg_ar": "{name} 🌟 عندنا {unit} المميّزة فاضية {wd} ({dates}) ونحب نرقّيك لها كلفتة خاصة لضيوفنا. تشرّفنا؟",
        "msg_en": "{name} 🌟 our premium {unit} is open {wd} ({dates}) and we'd love to upgrade you to it as a gesture for our guests. Honour us?",
    },
    "TURAIF-MIDWEEK": {
        "name_ar": "تُرَيف منتصف الأسبوع", "name_en": "Turaif midweek",
        "fires_on": ["PROTECTED", "PREMIUM"], "offer_mode": "upgrade",
        "filter": {"tier_only": "Turaif"},
        "why_ar": "فجوة {wd} مميّزة في {unit}؛ ترتيب هادئ خاص لـ {n} من ضيوف تُرَيف.",
        "why_en": "Premium {wd} gap on {unit}; private quiet rate for {n} Turaif.",
        "msg_ar": "{name} 🤍 خصّيناك بليلة {wd} في {unit} المميّزة ({dates}) بترتيب هادئ خاص لضيوف تُرَيف. أحجزها لك؟",
        "msg_en": "{name} 🤍 we've set aside a {wd} night at the premium {unit} ({dates}) with a quiet private arrangement for our Turaif guests. Reserve it for you?",
    },
    "OCCASION-MIDWEEK": {
        "name_ar": "مناسبة منتصف الأسبوع", "name_en": "Occasion midweek",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"tier_min": "Silver"},
        "why_ar": "مناسبة تصادف منتصف الأسبوع؛ دعوة مخصّصة لـ {n} منتظمين.",
        "why_en": "An occasion falls midweek; themed invite to {n} regulars.",
        "msg_ar": "{name} 🎉 المناسبة تجي منتصف الأسبوع وعندنا {unit} فاضية ({dates}) لو تبي تحتفل بهدوء. نجهّزها لك؟",
        "msg_en": "{name} 🎉 the occasion lands midweek and {unit} is open ({dates}) if you'd like to celebrate quietly. Want us to prepare it?",
    },
    "LONG-STAY-MIDWEEK": {
        "name_ar": "إقامة طويلة منتصف الأسبوع", "name_en": "Long-stay midweek",
        "fires_on": ["LONG-GAP"], "offer_mode": "value_add",
        "filter": {"nights_min": 3, "stays_min": 2},
        "why_ar": "فجوة طويلة منتصف الأسبوع في {unit}؛ ترتيب إقامة طويلة لـ {n} ضيوف.",
        "why_en": "Long midweek gap on {unit}; long-stay rate to {n}.",
        "msg_ar": "{name} عندنا فترة طويلة مفتوحة في {unit} ({dates}) — مناسبة لإقامة مطوّلة بترتيب مريح. أقولك التفاصيل؟",
        "msg_en": "{name} we've a longer open stretch at {unit} ({dates}) — ideal for an extended stay with a comfortable arrangement. Want the details?",
    },
    "CORPORATE-WEEKDAY": {
        "name_ar": "شركات منتصف الأسبوع", "name_en": "Corporate weekday",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"corporate": True, "stays_min": 3},
        "why_ar": "{n} ضيوف بنمط أعمال؛ ترتيب أيام أسبوع ثابت.",
        "why_en": "{n} business-pattern guests; fixed weekday arrangement.",
        "msg_ar": "{name} 👋 لو تحتاج {unit} لأيام العمل منتصف الأسبوع ({dates})، نقدر نرتّب لك ترتيب ثابت يناسب جدولك. نتكلّم؟",
        "msg_en": "{name} 👋 if you need {unit} for midweek workdays ({dates}), we can set up a steady arrangement that fits your schedule. Shall we talk?",
    },
    "ELITE-NUDGE": {
        "name_ar": "ترحيب إيليت", "name_en": "Elite nudge",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"tier_only": "Silver", "stays_min": 2},
        "why_ar": "{n} منتظمين جدد نرحّب فيهم بنادي إيليت (مكانة، بدون خصم).",
        "why_en": "{n} new-ish regulars to welcome into Elite (status, no discount).",
        "msg_ar": "{name} 🌟 صرت من ضيوفنا المنتظمين ونحب نرحّب فيك بمزايا إيليت. وبالمناسبة {unit} فاضية منتصف الأسبوع ({dates}).",
        "msg_en": "{name} 🌟 you're one of our regulars now and we'd love to welcome you with Elite perks. And by the way, {unit} is open midweek ({dates}).",
    },
    "REVIEW-TO-REBOOK": {
        "name_ar": "تقييم ثم حجز", "name_en": "Review to rebook",
        "fires_on": ["ANY"], "offer_mode": "relationship",
        "filter": {"days_since_max": 3, "score_min": 50},
        "why_ar": "ضيوف غادروا للتو ومبسوطين؛ طلب تقييم + إعادة حجز منتصف الأسبوع بسهولة.",
        "why_en": "Recent happy guests; review request + easy midweek rebook.",
        "msg_ar": "{name} يسعدنا لو تشاركنا تقييمك عن إقامتك 🤍 وإذا حبيت ترجع، {unit} فاضية منتصف الأسبوع ({dates}) ونثبتها لك بسهولة.",
        "msg_en": "{name} we'd love your review of your stay 🤍 and if you'd like to return, {unit} is open midweek ({dates}) — easy to hold for you.",
    },
}

# ---------------------------------------------------------------------------
# v2 copy (build change 5): the owner-authored hooks + persuasion principle live verbatim in
# brain/playbook_v2.py (so that file stays the single source of truth for the message text).
# We swap ONLY the ar/en message body and add principle/tier_focus here, preserving every
# structural field above (filter / offer_mode / fires_on / why / names) that the engine reads.
# ---------------------------------------------------------------------------
try:
    from . import playbook_v2 as _v2
    for _code, _c in _v2.CAMPAIGNS.items():
        _dst = CAMPAIGNS.get(_code)
        if _dst is None:
            continue
        if _c.get("ar"):
            _dst["msg_ar"] = _c["ar"]
        if _c.get("en"):
            _dst["msg_en"] = _c["en"]
        _dst["principle"] = _c.get("principle")
        _dst["tier_focus"] = _c.get("tier_focus")
except Exception as _e:        # never let a copy-file issue break the engine
    print("[brain] playbook_v2 merge skipped:", _e)


# Tier ordering for tier_min comparisons.
TIER_RANK = {"Prospect": 0, "Silver": 1, "Gold": 2, "Turaif": 3, "Quarantine": -1}

# Gap class -> the campaign pushed by default (build spec §4 spine).
CLASS_PRIMARY = {
    "TONIGHT": "TONIGHT", "TOMORROW": "TOMORROW", "ORPHAN-NIGHT": "ORPHAN-NIGHT",
    "MIDWEEK-2": "MIDWEEK-2", "LONG-GAP": "LONG-GAP", "THIS-WEEK": "THIS-WEEK",
}


def get(code):
    return CAMPAIGNS.get(code)


def primary_code(gap, pace_mode="normal"):
    """Pick the campaign for a gap. Protected units are upgrade-only; a 'full' portfolio swaps a
    discount campaign for the no-discount relationship one (build spec §4 offer-by-calendar-state)."""
    if gap.get("protected"):
        return "UPGRADE-MIDWEEK"
    code = CLASS_PRIMARY.get(gap.get("gap_class"), "THIS-WEEK")
    if pace_mode == "full" and CAMPAIGNS.get(code, {}).get("offer_mode") in ("value_add", "deeper"):
        return "YOUR-UNIT-FREE"            # relationship-only when we're nearly sold out
    return code
