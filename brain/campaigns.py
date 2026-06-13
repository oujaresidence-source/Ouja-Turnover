"""
brain.campaigns — load the campaign catalog (campaigns.json) into SQLite, and pick
today's single best campaign from the live signals (build-spec section 7 priority).

Seeding rule: a NEW code is inserted whole (draft copy from the file). For an EXISTING
code we refresh only the *wiring* fields (trigger_type, tier_targets, cooldown_class,
name, offer, lever, active) and DON'T touch message_template / image_prompt — so the
real Arabic copy you paste (or edit in the dashboard) survives every redeploy.
"""

import os
import json
from . import db

_WIRING_FIELDS = ("name", "tier_targets", "trigger_type", "offer", "lever",
                  "cooldown_class", "active")


def _catalog_path():
    return os.path.join(os.path.dirname(__file__), "campaigns.json")


def seed_campaigns():
    db.init_db()
    try:
        with open(_catalog_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0
    rows = data.get("campaigns", [])
    existing = {r["code"] for r in db.q("SELECT code FROM campaigns")}
    n = 0
    for c in rows:
        code = c.get("code")
        if not code:
            continue
        tier_json = json.dumps(c.get("tier_targets", []), ensure_ascii=False)
        if code in existing:
            db.execute(
                "UPDATE campaigns SET name=?, tier_targets=?, trigger_type=?, offer=?, "
                "lever=?, cooldown_class=?, active=? WHERE code=?",
                (c.get("name", ""), tier_json, c.get("trigger_type", ""), c.get("offer", ""),
                 c.get("lever", ""), c.get("cooldown_class", "soft"), int(c.get("active", 1)), code))
        else:
            db.execute(
                "INSERT INTO campaigns(code, name, tier_targets, trigger_type, offer, lever, "
                "message_template, image_prompt, cooldown_class, active) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (code, c.get("name", ""), tier_json, c.get("trigger_type", ""), c.get("offer", ""),
                 c.get("lever", ""), c.get("message_template", ""), c.get("image_prompt", ""),
                 c.get("cooldown_class", "soft"), int(c.get("active", 1))))
            n += 1
    return n


def _row_to_campaign(r):
    if r is None:
        return None
    d = dict(r)
    try:
        d["tier_targets"] = json.loads(d.get("tier_targets") or "[]")
    except (ValueError, TypeError):
        d["tier_targets"] = []
    return d


def get_campaign(code):
    seed_campaigns()
    return _row_to_campaign(db.q1("SELECT * FROM campaigns WHERE code=?", (code,)))


def list_campaigns():
    seed_campaigns()
    return [_row_to_campaign(r) for r in db.q("SELECT * FROM campaigns ORDER BY code")]


# --------------------------------------------------------------------------
# Selection — signals -> one campaign (or SILENT). Returns a decision dict the
# recommender consumes. `nights_to_fill` is the campaign-scoped soft-night count
# that drives the demand-matched audience size (Appendix B).
# --------------------------------------------------------------------------

def select_campaign(sig):
    """sig = the dict from signals.compute_signals(). Returns a decision dict:
       {silent: bool, code, reason, nights_to_fill, scope_lids:set|None}."""
    imminent_soft = sig.get("imminent_discounted_nights", 0)
    imminent_open = sig.get("imminent_open_nights", 0)
    long_gap_units = sig.get("long_gap_units", [])
    checkouts_today = sig.get("checkouts_today", 0)
    new_premium = sig.get("new_premium_units", [])
    large_empty = sig.get("large_units_empty", [])
    far_out = sig.get("far_out_at_risk_dates", [])
    open_weekday = sig.get("open_weekday_nights", 0)
    occ = sig.get("occupancy_pct", 0)

    def lids_of(units):
        return {u["lid"] for u in units} or None

    # 1) Imminent empties (<=72h) — strongest. Already-discounted nights make it a flash.
    if imminent_open > 0:
        if imminent_soft > 0:
            return {"silent": False, "code": "C12",
                    "reason": "ليالٍ قريبة (≤72 ساعة) فاضية ومخفّضة أصلاً من محرّك التسعير — أفضل وقت لعرض اللحظة الأخيرة.",
                    "reason_en": "%d open night(s) within 72h, %d already price-softened — last-minute push." % (imminent_open, imminent_soft),
                    "nights_to_fill": max(imminent_soft, imminent_open), "scope_lids": None}
        # imminent but not yet discounted, and a few of them -> flash to top tiers
        if imminent_open >= 3:
            return {"silent": False, "code": "C10",
                    "reason": "عدة ليالٍ قريبة فاضية تحتاج دفعة — عرض فلاش ٤٨ ساعة لكبار الأعضاء.",
                    "reason_en": "%d imminent open nights need a push — 48h flash to top tiers." % imminent_open,
                    "nights_to_fill": imminent_open, "scope_lids": None}
        return {"silent": False, "code": "C12",
                "reason": "ليالٍ قريبة فاضية — عرض اللحظة الأخيرة.",
                "reason_en": "%d imminent open night(s) — last-minute." % imminent_open,
                "nights_to_fill": imminent_open, "scope_lids": None}

    # 2) Long consecutive weekday gaps -> 3rd-night-free (top tiers) / stay-more ladder.
    if long_gap_units:
        gap_weekday = sum(u.get("weekday_nights", 0) for u in long_gap_units) or len(long_gap_units)
        if len(long_gap_units) >= 2:
            return {"silent": False, "code": "C02",
                    "reason": "فجوات أيام أسبوع طويلة في %d وحدة — الليلة الثالثة هدية يطوّل الإقامات." % len(long_gap_units),
                    "reason_en": "Long weekday gaps in %d units — 3rd-night-free lengthens stays." % len(long_gap_units),
                    "nights_to_fill": gap_weekday, "scope_lids": lids_of(long_gap_units)}
        return {"silent": False, "code": "C03",
                "reason": "أسبوع هادئ مع فجوات — سلّم «طوّل وفّر» يملأ الليالي.",
                "reason_en": "Soft week with gaps — stay-more ladder fills nights.",
                "nights_to_fill": gap_weekday, "scope_lids": lids_of(long_gap_units)}

    # 3) Checkouts today/tomorrow -> book-direct + review.
    if checkouts_today > 0:
        return {"silent": False, "code": "C06",
                "reason": "%d مغادرة اليوم/بكرة — لحظة مثالية لدعوتهم يحجزون مباشرة المرة الجاية." % checkouts_today,
                "reason_en": "%d checkouts today/tomorrow — perfect moment for a book-direct nudge." % checkouts_today,
                "nights_to_fill": max(open_weekday, checkouts_today), "scope_lids": None}

    # 4) New premium unit / weekend freed -> Turaif early access.
    if new_premium:
        return {"silent": False, "code": "C19",
                "reason": "وحدة مميّزة جديدة/متاحة — وصول مبكر حصري لضيوف تُرَيف.",
                "reason_en": "New/freed premium unit — exclusive early access for Turaif.",
                "nights_to_fill": max(open_weekday, len(new_premium) * 2), "scope_lids": lids_of(new_premium)}

    # 4b) Large/family units empty -> family package (school break / large empties).
    if len(large_empty) >= 2:
        return {"silent": False, "code": "C14",
                "reason": "%d وحدة عائلية كبيرة فاضية — باقة العائلة." % len(large_empty),
                "reason_en": "%d large family units empty — family package." % len(large_empty),
                "nights_to_fill": open_weekday, "scope_lids": lids_of(large_empty)}

    # 5) Far-out at-risk dates pacing low -> advance purchase.
    if len(far_out) >= 3 and open_weekday > 0:
        return {"silent": False, "code": "C11",
                "reason": "تواريخ بعيدة إشغالها منخفض — احجز بدري لتثبيت الإيراد.",
                "reason_en": "Far-out dates pacing low — advance-purchase to lock revenue.",
                "nights_to_fill": open_weekday, "scope_lids": None}

    # 5b) Month close, and a little softness -> gratitude touch.
    if sig.get("is_month_close") and open_weekday > 0:
        return {"silent": False, "code": "C18",
                "reason": "نهاية الشهر — لمسة امتنان خفيفة تبني الولاء وتملأ ليالي خفيفة.",
                "reason_en": "Month close — light gratitude touch builds loyalty and fills soft nights.",
                "nights_to_fill": open_weekday, "scope_lids": None}

    # 6) Healthy and nothing soft -> SILENT (the proud default).
    return {"silent": True, "code": None,
            "reason": "الإشغال صحّي (%d%%) ولا توجد ليالٍ ضعيفة تحتاج دفعة — اليوم الأفضل ألا نرسل شيء." % occ,
            "reason_en": "Occupancy is healthy (%d%%) and nothing is soft — the best move today is to send nothing." % occ,
            "nights_to_fill": 0, "scope_lids": None}
