"""
brain.settings — every Brain threshold lives here, persisted in the `settings` table,
editable from the /brain dashboard. Defaults are exactly the numbers from the build spec
(sections 5, 9 and Appendix B). Change them in the UI; nothing here is hard-coded elsewhere.
"""

import json
from . import db

# key -> (default_value, type, group, label_ar, label_en, help)
DEFAULTS = {
    # ---- tiers (section 5) ----
    "tier_turaif_min_stays": (4, "int", "tiers", "حد ضيف تُرَيف (إقامات)", "Turaif min stays", "4+ stays = Turaif"),
    "tier_gold_min_stays":   (2, "int", "tiers", "حد ضيف ذهبي (إقامات)", "Gold min stays", "2–3 stays = Gold"),
    "quarantine_min_stays":  (20, "int", "tiers", "حجر داخلي/شركات (إقامات)", "Quarantine over", ">20 stays = internal/corporate, excluded"),

    # ---- governor (section 9) — the sacred anti-nag rules ----
    "gov_max_msgs_per_7d":   (2, "int", "governor", "أقصى رسائل / 7 أيام", "Max msgs / 7 days", "Rolling 7-day cap per member"),
    "gov_min_gap_hours":     (48, "int", "governor", "أقل فجوة بين الرسائل (ساعة)", "Min gap (hours)", "Minimum hours between two messages"),
    "gov_rest_days":         (30, "int", "governor", "راحة بعد التجاهل (يوم)", "Rest days", "Auto-rest length after too many ignores"),
    "gov_ignores_to_rest":   (3, "int", "governor", "تجاهلات متتالية للراحة", "Ignores to rest", "Consecutive ignores that trigger a rest"),
    "gov_suppress_booked_days": (14, "int", "governor", "كتم بعد حجز (يوم)", "Suppress after booking (days)", "Don't promo someone who just booked"),
    "gov_no_friday_until_hour": (17, "int", "governor", "لا إرسال جمعة قبل الساعة", "No Friday before hour", "Friday quiet hours end (00:00–HH:00)"),
    "gov_send_hour":         (20, "int", "governor", "ساعة الإرسال الافتراضية", "Default send hour", "Default scheduled send hour (KSA)"),
    "gov_send_minute":       (30, "int", "governor", "دقيقة الإرسال", "Send minute", "Default scheduled send minute"),
    "gov_earliest_hour":     (13, "int", "governor", "أبكر ساعة إرسال", "Earliest send hour", "Never send before this hour"),

    # ---- warm-up daily caps (section 6/9, week 1/2/3) ----
    "daily_send_cap":        (300, "int", "volume", "السقف اليومي للإرسال", "Daily send cap", "Hard ceiling per day after warm-up"),
    "warmup_week1_cap":      (50, "int", "volume", "سقف الأسبوع الأول", "Warm-up wk1 cap", "Daily cap during week 1"),
    "warmup_week2_cap":      (120, "int", "volume", "سقف الأسبوع الثاني", "Warm-up wk2 cap", "Daily cap during week 2"),
    "warmup_week3_cap":      (200, "int", "volume", "سقف الأسبوع الثالث", "Warm-up wk3 cap", "Daily cap during week 3"),
    "warmup_started_on":     ("", "str", "volume", "تاريخ بدء الإحماء", "Warm-up start date", "ISO date the ramp started ('' = not started)"),

    # ---- demand-matched volume (Appendix B) ----
    "expected_bookings_per_message": (0.04, "float", "demand", "حجوزات متوقعة لكل رسالة", "Bookings / message", "Conversion estimate (auto-learned later)"),
    "avg_nights_per_booking": (2, "float", "demand", "متوسط الليالي للحجز", "Avg nights / booking", "Average nights a booking fills"),
    "audience_buffer":        (1.3, "float", "demand", "هامش الجمهور", "Audience buffer", "Over-target multiplier so enough convert"),

    # ---- signal engine ----
    "signal_horizon_days":   (14, "int", "signals", "أفق الإشارات (يوم)", "Signal horizon (days)", "How far ahead to read inventory softness"),
    "imminent_hours":        (72, "int", "signals", "وشيك (ساعة)", "Imminent (hours)", "Open nights within this window are 'imminent'"),
    "gap_long_nights":       (3, "int", "signals", "فجوة طويلة (ليالي)", "Long gap (nights)", "Consecutive empty nights that count as a long gap"),
    "healthy_pace_pct":      (90, "int", "signals", "إشغال صحي %", "Healthy occupancy %", "At/above this and nothing soft => stay SILENT"),

    # ---- approval ----
    "human_approval_required": (1, "int", "approval", "موافقة بشرية إلزامية", "Human approval required", "Phase 1: always 1 (nothing auto-sends)"),
    "active_sender_adapter":   ("csv", "str", "approval", "قناة التسليم", "Sender adapter", "csv (export) | karzoum (Phase 2)"),
    "karzoum_name_token":      ("{name}", "str", "approval", "رمز الاسم في كرزوم", "Karzoum name token", "What Karzoum substitutes the Name into, e.g. {name} / {{name}} / [Name]"),
}

_CAST = {"int": int, "float": float, "str": str}


def seed_defaults():
    """Insert any missing setting with its default. Never overwrites a value already set."""
    db.init_db()
    existing = {r["key"] for r in db.q("SELECT key FROM settings")}
    rows = []
    for key, (val, typ, *_rest) in DEFAULTS.items():
        if key not in existing:
            rows.append((key, json.dumps(val)))
    if rows:
        db.executemany("INSERT OR IGNORE INTO settings(key, value) VALUES(?,?)", rows)


def get(key, default=None):
    seed_defaults()
    r = db.q1("SELECT value FROM settings WHERE key=?", (key,))
    if r is None:
        if key in DEFAULTS:
            return DEFAULTS[key][0]
        return default
    try:
        return json.loads(r["value"])
    except (ValueError, TypeError):
        return r["value"]


def get_int(key):
    try:
        return int(get(key))
    except (ValueError, TypeError):
        return int(DEFAULTS.get(key, (0,))[0] or 0)


def get_float(key):
    try:
        return float(get(key))
    except (ValueError, TypeError):
        return float(DEFAULTS.get(key, (0.0,))[0] or 0.0)


def set_value(key, value):
    """Set one setting, casting to the declared type so the UI can post strings."""
    typ = DEFAULTS.get(key, (None, "str"))[1]
    caster = _CAST.get(typ, str)
    try:
        if typ == "int":
            value = int(float(value))
        elif typ == "float":
            value = float(value)
        else:
            value = caster(value)
    except (ValueError, TypeError):
        pass
    db.execute("INSERT INTO settings(key, value) VALUES(?,?) "
               "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, json.dumps(value)))
    return value


def all_grouped():
    """Settings for the dashboard, grouped, with current values + metadata."""
    seed_defaults()
    cur = {r["key"]: r["value"] for r in db.q("SELECT key, value FROM settings")}
    groups = {}
    for key, (val, typ, group, lab_ar, lab_en, helptext) in DEFAULTS.items():
        try:
            v = json.loads(cur.get(key, json.dumps(val)))
        except (ValueError, TypeError):
            v = val
        groups.setdefault(group, []).append({
            "key": key, "value": v, "type": typ,
            "label_ar": lab_ar, "label_en": lab_en, "help": helptext,
        })
    return groups
