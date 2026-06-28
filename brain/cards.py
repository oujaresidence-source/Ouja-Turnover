"""
brain.cards — the decision engine: turn each weekday gap into a push card with WHY, the ranked
targets (each with a per-guest reason), the offer/floor, and the ready AR/EN message (build spec
§4/§5/§6). One card = one campaign on one gap.

The CORE (build_card / select + filter + rank + offer + assemble) is a pure function of its
inputs — gaps, member rows, config, a floor lookup — so the synthetic tests prove the hard rules
without a DB or network: weekends already excluded upstream, F1/F2 never discounted, audience
ranked tier→fit→recency, frequency cap + flag exclusion applied, every card carries a why and
per-guest reasons.

The LIVE wrapper (build_cards) wires the core to the host: live gaps, the members table, the
Governor (in-house/upcoming/recently-booked/freq screen), the per-unit floor, and a portfolio
pace read that can swap a discount for a relationship message when we're nearly sold out.
"""

from . import playbook
from .playbook import TIER_RANK

_WD_AR = {6: "الأحد", 0: "الاثنين", 1: "الثلاثاء", 2: "الأربعاء", 3: "الخميس", 4: "الجمعة", 5: "السبت"}
_WD_EN = {6: "Sunday", 0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
_P1_DEAD = frozenset({"TONIGHT", "TOMORROW", "ORPHAN-NIGHT"})

DEFAULT_CFG = {
    "targets_per_card": 25,
    "ceiling_pct": 13,
    "deep_min_score": 75,
    "deep_floor_pct": 55,      # fallback floor = p5(or min night price) × this %
}


# -------------------------- audience filter + rank --------------------------

def _tier_ok(m, filt):
    tier = m.get("tier")
    if tier == "Quarantine":
        return False
    if filt.get("tier_only"):
        return tier == filt["tier_only"]
    if not filt.get("prospect_ok") and tier == "Prospect":
        return False
    if filt.get("tier_min") and TIER_RANK.get(tier, -1) < TIER_RANK.get(filt["tier_min"], 0):
        return False
    return True


def _match(m, gap, filt):
    """True iff member m passes the campaign filter for this gap. Signals absent from the data
    (corporate pattern, explicit last-minute history) are treated as no-op, never as a reject —
    so the campaign still produces an audience instead of silently emptying."""
    if not _tier_ok(m, filt):
        return False
    if filt.get("weekday_pattern") and not m.get("weekday_pattern"):
        return False
    ds = m.get("days_since")
    if filt.get("days_since_max") is not None and (ds is None or ds > filt["days_since_max"]):
        return False
    if filt.get("days_since_min") is not None and (ds is None or ds < filt["days_since_min"]):
        return False
    if filt.get("score_min") is not None and float(m.get("score") or 0) < filt["score_min"]:
        return False
    if filt.get("stays_min") is not None and int(m.get("stays_count") or 0) < filt["stays_min"]:
        return False
    if filt.get("nights_min") is not None and int(m.get("nights_total") or 0) < filt["nights_min"]:
        return False
    if filt.get("preferred_match") and (m.get("preferred_unit") != gap.get("unit")):
        return False
    return True


def _rank_key(m, gap):
    """Audience ranking (build spec §4): tier -> fit (preferred unit, weekday regular) ->
    recency (lower days_since first) -> score. Sorted descending on this tuple."""
    pref = 1 if m.get("preferred_unit") == gap.get("unit") else 0
    wd = 1 if m.get("weekday_pattern") else 0
    ds = m.get("days_since")
    rec = -int(ds) if ds is not None else -99999      # nearer last stay ranks first
    return (TIER_RANK.get(m.get("tier"), 0), pref, wd, rec, float(m.get("score") or 0))


# -------------------------- per-guest reason --------------------------

def _reason(m, gap):
    stays = int(m.get("stays_count") or 0)
    ds = m.get("days_since")
    pref = m.get("preferred_unit") == gap.get("unit")
    en, ar = [], []
    if pref and stays:
        en.append("favourite unit, %d stays" % stays)
        ar.append("شقته المفضّلة، %d إقامات" % stays)
    else:
        en.append("%d stays" % stays)
        ar.append("%d إقامات" % stays)
    if ds is not None:
        en.append("last %dd ago" % ds)
        ar.append("آخر إقامة قبل %d يوم" % ds)
    if m.get("weekday_pattern"):
        en.append("books Sun–Wed")
        ar.append("يحجز منتصف الأسبوع")
    return ", ".join(en), "، ".join(ar)


def _target_view(m, gap):
    reason_en, reason_ar = _reason(m, gap)
    return {"name": m.get("first_name") or "", "phone": m.get("phone"),
            "tier": m.get("tier"), "score": m.get("score"),
            "reason_en": reason_en, "reason_ar": reason_ar}


# -------------------------- offer / floor --------------------------

def _offer(gap, camp, cfg, floor_fn):
    ceiling = int(cfg.get("ceiling_pct", 13))
    protected = bool(gap.get("protected"))
    mode = camp.get("offer_mode", "relationship")
    if protected or mode == "upgrade":
        return {"mode": "upgrade", "max_pct": 0, "floor": None, "deep_allowed": False,
                "text_ar": "ترقية أو وصول فقط — بدون أي تخفيض سعر.",
                "text_en": "Upgrade / access only — never a price cut."}
    if mode == "relationship":
        return {"mode": "relationship", "max_pct": 0, "floor": None, "deep_allowed": False,
                "text_ar": "علاقة فقط — بدون خصم.",
                "text_en": "Relationship only — no discount."}
    # value_add / deeper -> capped at the direct-booking ceiling, never below floor
    floor = None
    if floor_fn:
        try:
            floor = floor_fn(gap.get("lid"))
        except Exception:
            floor = None
    if not floor:
        prices = [p for p in (gap.get("prices") or []) if isinstance(p, (int, float)) and p > 0]
        if prices:
            floor = int(round(min(prices) * int(cfg.get("deep_floor_pct", 55)) / 100.0))
    deep_allowed = gap.get("gap_class") in _P1_DEAD     # deeper only on a P1 dead night, vetted
    fl = ("؛ الأرضية %d ر.س" % floor) if floor else ""
    fl_en = ("; floor SAR %d" % floor) if floor else ""
    return {"mode": "value_add", "max_pct": ceiling, "floor": floor, "deep_allowed": deep_allowed,
            "deep_min_score": int(cfg.get("deep_min_score", 75)),
            "text_ar": "قيمة مضافة أولًا؛ حتى %d%% على الحجز المباشر%s." % (ceiling, fl),
            "text_en": "Value-add first; up to %d%% on a direct booking%s." % (ceiling, fl_en)}


# -------------------------- message + why merge --------------------------

def _merge(text, gap):
    wd0 = gap.get("weekdays", [None])[0]
    dates = " – ".join(gap.get("gap_labels") or [])
    return (str(text or "")
            .replace("{unit}", gap.get("unit", ""))
            .replace("{dates}", dates)
            .replace("{wd}", _WD_EN.get(wd0, ""))
            .replace("{nights}", str(gap.get("nights", 1))))


def _merge_ar(text, gap):
    wd0 = gap.get("weekdays", [None])[0]
    dates = " – ".join(gap.get("gap_labels") or [])
    return (str(text or "")
            .replace("{unit}", gap.get("unit", ""))
            .replace("{dates}", dates)
            .replace("{wd}", _WD_AR.get(wd0, ""))
            .replace("{nights}", str(gap.get("nights", 1))))


def _why(camp, gap, n, d_default=14):
    wd0 = gap.get("weekdays", [None])[0]
    def fill(t, wd):
        return (str(t or "").replace("{unit}", gap.get("unit", "")).replace("{n}", str(n))
                .replace("{d}", str(d_default)).replace("{wd}", wd)
                .replace("{nights}", str(gap.get("nights", 1))).replace("{k}", str(gap.get("nights", 1))))
    return fill(camp.get("why_ar"), _WD_AR.get(wd0, "")), fill(camp.get("why_en"), _WD_EN.get(wd0, ""))


# -------------------------- card assembly (PURE) --------------------------

def build_card(gap, members, cfg=None, floor_fn=None, pace_mode="normal",
               contacted_7d=None, risk_ids=None):
    """Build one §5 push card for `gap` from the candidate `members` (list of member dicts).
    contacted_7d / risk_ids are id sets to exclude (≤1 Elite msg/7d, risky guests). Returns the
    card dict (target_count may be 0 — the caller decides whether to surface an empty card)."""
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    contacted_7d = contacted_7d or set()
    risk_ids = risk_ids or set()
    code = playbook.primary_code(gap, pace_mode)
    camp = playbook.get(code)

    filt = camp.get("filter", {})
    elig = []
    for m in members:
        mid = m.get("id")
        if mid in contacted_7d or mid in risk_ids:
            continue
        if m.get("opted_out"):
            continue
        if _match(m, gap, filt):
            elig.append(m)
    elig.sort(key=lambda m: _rank_key(m, gap), reverse=True)
    chosen = elig[: int(cfg.get("targets_per_card", 25))]

    why_ar, why_en = _why(camp, gap, len(chosen))
    gd = gap.get("gap_dates") or []
    return {
        "card_key": "%s:%s:%s" % (gap.get("lid"), gd[0] if gd else "", code),
        "campaign": code,
        "campaign_name_ar": camp.get("name_ar"), "campaign_name_en": camp.get("name_en"),
        "priority": gap.get("priority_label"), "priority_num": gap.get("priority"),
        "unit": gap.get("unit"), "lid": gap.get("lid"),
        "protected": bool(gap.get("protected")),
        "gap_class": gap.get("gap_class"),
        "gap_dates": gap.get("gap_labels"), "gap_dates_iso": gap.get("gap_dates"),
        "nights": gap.get("nights"), "at_risk": gap.get("at_risk"),
        "why_ar": why_ar, "why_en": why_en,
        "offer": _offer(gap, camp, cfg, floor_fn),
        "target_count": len(chosen),
        "pool_eligible": len(elig),
        "targets": [_target_view(m, gap) for m in chosen],
        "message_ar": _merge_ar(camp.get("msg_ar"), gap),
        "message_en": _merge(camp.get("msg_en"), gap),
    }


def _week_strip(grid, gaps, horizon):
    """The §6 7-day strip: each day in the horizon with its weekday, whether it's a weekend
    (greyed/leave-alone), and how many gap-nights fall on it."""
    from .gaps import _label, WEEKDAY_NIGHTS
    counts = {}
    for g in gaps:
        for d in (g.get("gap_dates") or []):
            counts[d] = counts.get(d, 0) + 1
    out = []
    for day in (grid or {}).get("days", [])[:horizon]:
        wd = day.get("weekday")
        out.append({"date": day.get("date"), "weekday": wd,
                    "weekend": wd not in WEEKDAY_NIGHTS,        # Thu/Fri/Sat = leave alone
                    "label": _label(day.get("date"), wd),
                    "gaps": counts.get(day.get("date"), 0)})
    return out


def daily_summary(gaps, cards):
    """The §6 top narrative: how many weekday gaps across how many units, and the biggest
    opportunity (most revenue-at-risk among P1)."""
    units = {g.get("lid") for g in gaps}
    p1 = [c for c in cards if c.get("priority_num") == 1 and c.get("target_count")]
    biggest = max(cards, key=lambda c: (c.get("at_risk") or 0), default=None) if cards else None
    return {
        "gap_count": len(gaps),
        "unit_count": len(units),
        "p1_count": len(p1),
        "card_count": len([c for c in cards if c.get("target_count")]),
        "biggest_unit": (biggest or {}).get("unit"),
        "biggest_class": (biggest or {}).get("gap_class"),
        "biggest_at_risk": (biggest or {}).get("at_risk"),
    }


# ============================ LIVE WRAPPER ============================

def _protected_lids(ls, names_csv):
    """Map the configured protected unit NAMES to listing ids, plus honour a per-listing
    `protected` flag if the dashboard ever sets one."""
    want = {n.strip().lower() for n in (names_csv or "").split(",") if n.strip()}
    out = set()
    for lid, rec in ((ls or {}).get("listings") or {}).items():
        nm = (rec.get("internal_name") or rec.get("public_name") or "").strip().lower()
        if rec.get("protected") or (nm and nm in want):
            out.add(str(lid))
    return out


def _floor_lookup(ls):
    """Per-unit hard floor from the listings store (the pricing-engine `floor` field). Returns a
    function lid -> floor or None (None lets _offer fall back to p5×55%)."""
    listings = (ls or {}).get("listings") or {}
    def fn(lid):
        rec = listings.get(str(lid)) or {}
        f = rec.get("floor")
        return int(f) if isinstance(f, (int, float)) and f > 0 else None
    return fn


def _pace_mode():
    """'full' when the portfolio is nearly sold out (relationship-only), 'soft' when it's wide
    open (room to lead with the ceiling), else 'normal'."""
    from .host import HOST
    try:
        cal = HOST.get_forward_calendar(7, 1200) if HOST.get_forward_calendar else []
        pcts = [d.get("pace_pct") for d in (cal or []) if d.get("pace_pct") is not None]
        if not pcts:
            return "normal"
        avg = sum(pcts) / len(pcts)
        return "full" if avg >= 90 else ("soft" if avg <= 55 else "normal")
    except Exception:
        return "normal"


def build_cards():
    """Production entry point. Pulls live gaps + members + Governor screen + floors and returns
    {summary, cards, generated_at}. Read-only; sends nothing."""
    from . import db, settings, members as members_mod, governor
    from . import gaps as gaps_mod
    from .util import now_iso, now_dt
    from datetime import timedelta
    from .host import HOST

    members_mod.ensure_seeded()
    ls = HOST.ls_get() if HOST.ls_get else {}
    protected = _protected_lids(ls, settings.get("gap_protected_units"))
    horizon = settings.get_int("gap_horizon_days")
    grid = gaps_mod.pull_grid(days=max(8, horizon + 1))
    live_gaps = gaps_mod.detect_gaps(grid, protected_lids=protected, horizon_days=horizon)
    strip = _week_strip(grid, live_gaps, horizon)

    # candidate members: everyone not structurally excluded; the Governor refines per send.
    rows = [dict(r) for r in db.q(
        "SELECT * FROM members WHERE opted_out=0 AND tier!='Quarantine' "
        "AND has_upcoming_booking=0 AND in_house=0")]
    screened = governor.screen(rows)
    included = screened["included"]

    # ≤1 Elite message / guest / 7 days (build spec §HARD RULES 4)
    week_ago = (now_dt() - timedelta(days=7)).isoformat(timespec="seconds")
    contacted_7d = {r["member_id"] for r in db.q(
        "SELECT DISTINCT member_id FROM contact_log WHERE sent_at > ?", (week_ago,))}

    cfg = {"targets_per_card": settings.get_int("gap_targets_per_card"),
           "ceiling_pct": settings.get_int("discount_ceiling_pct"),
           "deep_min_score": settings.get_int("deep_discount_min_score"),
           "deep_floor_pct": settings.get_int("deep_discount_floor_pct")}
    floor_fn = _floor_lookup(ls)
    pace = _pace_mode()

    cards = [build_card(g, included, cfg=cfg, floor_fn=floor_fn, pace_mode=pace,
                        contacted_7d=contacted_7d) for g in live_gaps]
    cards = [c for c in cards if c.get("target_count")]            # drop empty-audience cards
    return {"summary": daily_summary(live_gaps, cards), "cards": cards, "strip": strip,
            "pace_mode": pace, "protected_units": sorted(protected), "generated_at": now_iso()}
