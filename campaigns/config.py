# -*- coding: utf-8 -*-
"""
campaigns.config — every CAMPAIGN_* env var (read at call time, never cached) and the two
owner-editable dicts: the code words and the WhatsApp button labels.

SAFE BY CONSTRUCTION
    * Nothing in this package ever writes to Hostaway (no special-offer API exists).
    * The code-word watcher and the weekly report only ever post to Discord.
    * CAMPAIGN_BUTTONS_DRYRUN defaults to 1: a prepared WhatsApp reply (the apartments list,
      the Elite explanation) is SHOWN on Discord, never sent. Live sends also need the Hatif
      API keys and still obey HATIF_TEST_NUMBERS and the opt-out list.
"""
import os

_TRUE = ("1", "true", "True", "yes")


def _env(name, default=""):
    v = os.environ.get(name)
    return default if v is None else v


def _flag(name, default):
    return _env(name, default).strip() in _TRUE


def _int(name, default):
    try:
        return int(str(_env(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return int(default)


# ---------------------------------------------------------------- switches
def enabled():
    """Master switch. 0 = the whole package is silent."""
    return _flag("CAMPAIGNS_ENABLED", "1")


def watch_enabled():
    """(1) Code-word watcher on Hostaway guest messages → Discord alert."""
    return enabled() and _flag("CAMPAIGN_WATCH", "1")


def buttons_enabled():
    """(2) Hatif template button taps → Discord alerts + opt-out list."""
    return enabled() and _flag("CAMPAIGN_BUTTONS", "1")


def buttons_dryrun():
    """(2) 1 (default) = prepared WhatsApp replies are shown on Discord, never sent."""
    return _flag("CAMPAIGN_BUTTONS_DRYRUN", "1")


def report_enabled():
    """(3) Weekly report, Sunday 09:00 Riyadh, Discord only."""
    return enabled() and _flag("CAMPAIGN_REPORT", "1")


def report_day():
    """Python weekday: 6 = Sunday."""
    return min(6, max(0, _int("CAMPAIGN_REPORT_DAY", 6)))


def report_hour():
    return min(23, max(0, _int("CAMPAIGN_REPORT_HOUR", 9)))


def offers_channel():
    return _env("CAMPAIGN_OFFERS_CHANNEL", "عروض-خاصة").strip() or "عروض-خاصة"


def owners_channel():
    return _env("CAMPAIGN_OWNERS_CHANNEL", "طلبات-الملاك").strip() or "طلبات-الملاك"


def offer_role_id():
    """Discord role pinged on a code-word hit (empty = no ping, the responsible name only)."""
    v = _env("CAMPAIGN_OFFER_ROLE_ID").strip()
    return v if v.isdigit() else ""


def owners_role_id():
    v = _env("CAMPAIGN_OWNERS_ROLE_ID").strip()
    return v if v.isdigit() else ""


def act_within_min():
    return max(1, _int("CAMPAIGN_ACT_MIN", 15))


def owner_call_within_h():
    return max(1, _int("CAMPAIGN_OWNER_CALL_H", 2))


def match_days():
    """A hit / tap counts as «led to a booking» when a booking is CREATED within this many days."""
    return max(1, _int("CAMPAIGN_MATCH_DAYS", 7))


# ---------------------------------------------------------------- code words
# Owner-editable. Add a campaign by adding an entry: phrases are matched as whole words after
# Arabic normalisation (أ/إ/آ → ا, ة → ه, ى → ي, no tashkeel, no tatweel), and a space between
# the words is optional. `not_before` blocks a hit when one of those words follows the phrase
# («عرض نص ساعة» is not the campaign).
CODEWORDS = {
    "B1": {
        "title": "الليلة الثانية بنص",
        "phrases": ["عرض نص", "عرض النص", "عرض نصف", "عرض النصف", "عرض بالنص"],
        "not_before": ["ساعه", "ساعات", "دقيقه", "يوم", "الليل"],
        "kind": "second_night",     # → the special-offer price is computed
        "discount_pct": 50,
        "nights": (6, 0, 1, 2),     # Python weekdays of night 1: Sun, Mon, Tue, Wed
    },
    # Example for later (kept off until the owner names the offer):
    # "C1": {"title": "جاي الرياض", "phrases": ["جاي الرياض"], "kind": "alert_only"},
}


# ---------------------------------------------------------------- Hatif template buttons
# The exact button labels the templates carry in Hatif (2026-11-23). A tap is matched on the
# label after normalisation; the punctuation and an optional «،» / «؟» do not matter.
TEMPLATES = {
    "ouja_owner_recontact": ["إيه، كلموني", "مو الحين"],
    "ouja_elite_member": ["وريني الشقق", "وش إيليت؟"],
    "ouja_elite_invite": ["وريني الشقق", "وش إيليت؟"],
    "ouja_midweek_half": ["وريني الشقق"],
    "ouja_winback": ["وريني الشقق"],
    "ouja_moments_midweek": ["وريني الباقات"],
}

BUTTONS = {
    "إيه، كلموني": "owner_call",
    "مو الحين": "owner_later",
    "وريني الشقق": "show_units",
    "وش إيليت؟": "elite_info",
    "وريني الباقات": "show_packages",
    # Meta's own marketing opt-out button (every template) + what a guest may type instead
    "إيقاف العروض": "opt_out",
    "ايقاف العروض": "opt_out",
    "Stop promotions": "opt_out",
}

# Typed messages (not taps) that also mean «stop». Whole message only — «وقف» inside a
# sentence is not an opt-out.
STOP_WORDS = ["ايقاف", "إيقاف", "إيقاف العروض", "ايقاف العروض", "stop", "unsubscribe",
              "الغاء الاشتراك", "إلغاء الاشتراك", "لا ترسلون", "لا ترسل"]

# The canned «وش إيليت؟» answer. Only what the live /elite site already says (three levels,
# a members' price, booking straight with our team on WhatsApp) — no new promise, no number.
# CAMPAIGN_ELITE_TEXT replaces it without a code change.
ELITE_TEXT_DEFAULT = (
    "«عوجا إيليت» عضوية ضيوفنا اللي يرجعون لنا 🤍\n"
    "ثلاث درجات: فضة، ذهب، وطُريف.\n"
    "الأعضاء يحجزون معنا مباشرة على الواتساب بسعر الأعضاء، وتوصلهم عروضنا الخاصة أول.\n"
    "تفاصيل العضوية: https://oujares.com/elite\n"
    "تبي نوريك الشقق المتاحة؟ اكتب لنا تاريخ الدخول وكم ليلة."
)


def elite_text():
    return _env("CAMPAIGN_ELITE_TEXT").strip() or ELITE_TEXT_DEFAULT
