# -*- coding: utf-8 -*-
"""
monthly.settings — monthly_settings.json, and the one switch that can change what
a guest sees.

THE SWITCH. price_source is "discount" or "engine". It SHIPS AS "discount", which
means the live site at /monthly behaves exactly as it did before this package
existed: calendar total less the configured discount. Flipping it to "engine"
puts this engine's number in front of guests.

THE REFUSAL IS IN CODE, NOT IN A WARNING. Below MIN_OWN_HISTORY the switch cannot
be set to "engine" at all — set_price_source returns a refusal naming the current
coverage. Today coverage is 26-53%: flipping now would publish pool averages, the
same 12,050 repeated across fifteen units, as if they were per-unit prices. A
warning beside a working button is a button that gets pressed.

The override exists because the owner must be able to overrule his own rule — but
it takes a typed reason, recorded with the actor, exactly like a price override.
A rule with no way through gets deleted; a rule with an audited way through gets
respected.
"""

import datetime

from .host import HOST

FILE = "monthly_settings.json"

# THREE MODES, not two. "engine" was all-or-nothing and that was the defect: it
# forced a choice between publishing pooled averages for the whole portfolio or
# publishing nothing at all, when a third of the units already have real,
# measured, per-unit numbers.
#
#   discount         the old flat percentage. Nothing from this package.
#   engine_verified  the engine speaks ONLY for units priced from their OWN
#                    booking history. Every other unit keeps the discount path.
#                    Structurally cannot publish a pooled average, so it needs no
#                    coverage gate — the guarantee is in the code, not in a rule.
#   engine           the engine speaks for everything. Still gated at 60%.
PRICE_SOURCES = ("discount", "engine_verified", "engine")

# Only this one can publish a number that was not measured on the unit itself.
NEEDS_COVERAGE_GATE = ("engine",)

# The flip criterion, written where the switch lives so it is read by whoever is
# about to flip it rather than remembered by whoever wrote it.
MIN_OWN_HISTORY = 0.60

FLIP_CRITERION_AR = (
    "لا تحوّل إلى «المحرّك» ما دامت تغطية السجل الذاتي أقل من 60%. "
    "الأسعار حينها متوسطات أحياء مكررة على عدة شقق، مو أسعار لكل شقة."
)
FLIP_CRITERION_EN = (
    "Do not flip to `engine` while own-history coverage is below 60%. "
    "Below that the prices are repeated district averages, not per-unit numbers."
)

# S15. The filter ships OFF and turns on by decision, not by drift.
LICENCE_FILTER_ON_DATE = "2026-09-30"
LICENCE_EXPIRY_WARN_DAYS = 14

# REVERTED to "discount", 2026-08-19. engine_verified was shipped on at the
# owner's instruction and the guest site became unreachable. The mode itself is
# still correct and still available, but nothing in this package touches the
# guest price path any more (see bot.py, monthly_quote), so this default now only
# affects /monthly-lab.
DEFAULTS = {
    "_comment_flip": FLIP_CRITERION_AR,
    "_comment_flip_en": FLIP_CRITERION_EN,
    "price_source": "discount",
    "price_source_reason": "",
    "price_source_actor": "",
    "price_source_at": "",
    "turnover_cost_sar": None,
    "licence_filter_on": False,
    "licence_filter_due": LICENCE_FILTER_ON_DATE,
}


def load():
    cur = dict(DEFAULTS)
    try:
        saved = HOST.load_json(FILE, None) if HOST.load_json else None
    except Exception:
        saved = None
    if isinstance(saved, dict):
        for k, v in saved.items():
            cur[k] = v
    if cur.get("price_source") not in PRICE_SOURCES:
        cur["price_source"] = "discount"
    return cur


def save(cur):
    if HOST.save_json:
        HOST.save_json(FILE, cur)
    return cur


# ---------------------------------------------------------------------------
# THE OWNER'S FLIP, 2026-08-25. Asked for in these words: «ابيك تاخذ التسعير من
# الـlab» — after being shown that the guest site was publishing the nightly rate
# times 31 nights, and after being told twice what turning the engine on means.
#
# Done here rather than by hand on the screen for one reason: set_price_source()
# refuses to move this switch without an actor and a reason, and a value typed
# into a settings file by a script has neither. This runs ONCE, records both, and
# then never touches the switch again — the marker below is what makes it once.
# The owner changing it afterwards on the screen wins permanently, because their
# value is saved and this has already marked itself done.
OWNER_FLIP_MARK = "owner_flip_2026_08_25"
OWNER_FLIP_TO = "engine_verified"
OWNER_FLIP_REASON = ("طلب المالك ٢٥-٠٨-٢٠٢٦: خذ التسعير من «التسعير الشهري» بدل "
                     "السعر اليومي × عدد الليالي.")


def apply_owner_flip():
    """Move the switch once, on the record. Returns what happened, never raises —
    a boot path that can throw is a boot path that can take the bot down."""
    try:
        cur = load()
        if cur.get(OWNER_FLIP_MARK):
            return "already-applied"
        if cur.get("price_source") == OWNER_FLIP_TO:
            cur[OWNER_FLIP_MARK] = True
            save(cur)
            return "already-set"
        cur["price_source"] = OWNER_FLIP_TO
        cur["price_source_reason"] = OWNER_FLIP_REASON
        cur["price_source_actor"] = "owner (via Claude)"
        cur["price_source_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        cur[OWNER_FLIP_MARK] = True
        save(cur)
        return "flipped"
    except Exception as e:                  # pragma: no cover
        print("[monthly] owner flip skipped:", e)
        return "error"


def price_source():
    """What the LIVE guest site should use. Any doubt resolves to discount."""
    try:
        return load().get("price_source") or "discount"
    except Exception:
        return "discount"


class FlipRefused(ValueError):
    """The switch refused. Carries the number that says why."""


def set_price_source(value, coverage, actor=None, reason="", override=False):
    """Set the switch, or refuse and say what would have to be true.

    coverage is the CURRENT own-history share, passed in rather than fetched, so
    this stays testable and so the caller must have actually looked at it.
    """
    if value not in PRICE_SOURCES:
        raise FlipRefused("قيمة غير معروفة: %s" % value)

    cur = load()
    if value in NEEDS_COVERAGE_GATE and (coverage is None or coverage < MIN_OWN_HISTORY):
        pctnow = 0 if coverage is None else int(round(coverage * 100))
        if not override:
            raise FlipRefused(
                "مرفوض: تغطية السجل الذاتي %d%% والحد الأدنى %d%%. %s "
                "جرّب «المحرّك للمقيسة فقط» — ينشر أسعار المحرّك للشقق اللي "
                "عندها سجل خاص فيها، والباقي يبقى على الخصم."
                % (pctnow, int(MIN_OWN_HISTORY * 100), FLIP_CRITERION_AR))
        if not (reason or "").strip():
            raise FlipRefused(
                "التجاوز يحتاج سبب مكتوب — التغطية %d%% وهي تحت الحد." % pctnow)

    cur["price_source"] = value
    cur["price_source_reason"] = (reason or "").strip()
    cur["price_source_actor"] = actor or ""
    cur["price_source_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    cur["price_source_coverage_at_flip"] = coverage
    cur["price_source_overridden"] = bool(
        override and value in NEEDS_COVERAGE_GATE
        and (coverage is None or coverage < MIN_OWN_HISTORY))
    save(cur)
    return cur


def flip_state(coverage):
    """Everything the admin screen needs to show BESIDE the switch — including
    the number that says not to flip it."""
    cur = load()
    ok = coverage is not None and coverage >= MIN_OWN_HISTORY
    return {
        "price_source": cur.get("price_source"),
        "verified_always_allowed": True,
        "coverage": coverage,
        "coverage_pct": None if coverage is None else int(round(coverage * 100)),
        "min_pct": int(MIN_OWN_HISTORY * 100),
        "may_flip": ok,
        "needs_override": not ok,
        "criterion_ar": FLIP_CRITERION_AR,
        "criterion_en": FLIP_CRITERION_EN,
        "last_change": {
            "actor": cur.get("price_source_actor"),
            "at": cur.get("price_source_at"),
            "reason": cur.get("price_source_reason"),
            "overridden": cur.get("price_source_overridden"),
        },
    }
