# -*- coding: utf-8 -*-
"""
brain.cards — the Elite v5 decision engine.

Two jobs, both PURE at the core (so the synthetic tests need no DB or network):

  1. recommend_today(date, availability, guests, assumptions) -> the ranked 1–3 "Today's Push"
     recommendations. For each: WHICH campaign (highest-priority trigger live today with an
     available segment), the SEGMENT + N (contactable, opted-in, fatigue-clear), the open
     apartments X (from the live grid), and the assumed conversion -> expected fill Y, capped at X.

  2. build_campaign_catalogue / send-list — the 20 link-driven campaigns as cards with the raw
     Karzoun template + the ready send message, and the per-segment send list (today-first,
     deduped, opt-out + fatigue filtered) for the manual Karzoun push.

NOTHING here sends a message or names a unit or a date — every CTA is the same /elite URL. The
guardrails (opt-out, ≤1 msg/guest/7d, never the same campaign within 14d, kill-on-book) are all
applied in _contactable, so they hold identically for the recommendation N, the catalogue N and
the exported CSV.
"""

from . import playbook, triggers
from .playbook import TIER_RANK, ELITE_URL

ALL_TIERS = ("Silver", "Gold", "Turaif")

# Default conversion assumptions (clearly labelled "assumption, replace with real data" in the UI).
ASSUMPTION_DEFAULTS = {"click_through": 0.12, "click_to_book": 0.08}

# ---------------------------------------------------------------------------
# Segment definitions: audience -> filter. Campaigns not listed default to "all members".
# Behavioral flags read off the member row: tier, stays_count, days_since, lastmin, occasion_soon.
# ---------------------------------------------------------------------------
_ALL = {"tiers": ALL_TIERS, "label_ar": "كل الأعضاء", "label_en": "All members"}
SEGMENTS = {
    "DORMANT-COMEBACK": {"tiers": ALL_TIERS, "days_since_min": 60, "days_since_max": 365,
                         "label_ar": "الأعضاء النائمون (٦٠–٣٦٥ يوم)", "label_en": "Dormant 60–365 days"},
    "FIRST-TIMER": {"tiers": ALL_TIERS, "stays_min": 1, "stays_max": 2, "days_since_max": 150,
                    "label_ar": "ضيوف جدد (١–٢ إقامة)", "label_en": "New repeaters (1–2 stays)"},
    "LOYAL-THANKS": {"tiers": ("Gold", "Turaif"),
                     "label_ar": "كبار الأعضاء (ذهبي + تُرَيف)", "label_en": "Top members (Gold + Turaif)"},
    "LAST-MINUTE": {"tiers": ALL_TIERS, "lastmin": True,
                    "label_ar": "يحجزون باللحظة الأخيرة", "label_en": "Last-minute bookers"},
    "POST-STAY": {"tiers": ALL_TIERS, "days_since_max": 3,
                  "label_ar": "غادروا حديثاً (≤٣ أيام)", "label_en": "Just checked out (≤3 days)"},
    "BIRTHDAY": {"tiers": ALL_TIERS, "occasion": True,
                 "label_ar": "عندهم مناسبة على الملف", "label_en": "Occasion on file"},
    "SCHOOL-BREAK": {"tiers": ALL_TIERS, "label_ar": "كل الأعضاء (العوائل)", "label_en": "All members (families)"},
}


def segment_def(code):
    return SEGMENTS.get(code, _ALL)


def segment_label(code, lang):
    s = segment_def(code)
    return s.get("label_%s" % lang) or _ALL["label_%s" % lang]


# ---------------------------------------------------------------------------
# Membership + guardrails (PURE on the member dict — the live wrapper fills the annotations).
# A member dict carries: tier, stays_count, days_since, lastmin, occasion_soon, opted_out,
# in_house, has_upcoming_booking, recent_contact (bool: messaged in the last 7d),
# recent_campaigns (iterable of campaign codes sent to them in the last 14d).
# ---------------------------------------------------------------------------

def match_segment(m, code):
    s = segment_def(code)
    tier = m.get("tier")
    if tier == "Quarantine" or tier not in (s.get("tiers") or ALL_TIERS):
        return False
    ds = m.get("days_since")
    if s.get("days_since_min") is not None and (ds is None or ds < s["days_since_min"]):
        return False
    if s.get("days_since_max") is not None and (ds is None or ds > s["days_since_max"]):
        return False
    st = int(m.get("stays_count") or 0)
    if s.get("stays_min") is not None and st < s["stays_min"]:
        return False
    if s.get("stays_max") is not None and st > s["stays_max"]:
        return False
    if s.get("lastmin") and not m.get("lastmin"):
        return False
    if s.get("occasion") and not m.get("occasion_soon"):
        return False
    return True


def _contactable(m, code):
    """The guardrail gate, identical for the recommendation N, the catalogue N and the CSV."""
    if m.get("opted_out"):
        return False
    if m.get("in_house") or m.get("has_upcoming_booking"):     # kill-on-book
        return False
    if m.get("recent_contact"):                                # ≤1 message / guest / 7 days
        return False
    if code in set(m.get("recent_campaigns") or ()):           # never the same campaign within 14d
        return False
    return True


def segment_audience(code, guests):
    """Contactable members in `code`'s segment, deduped by phone (today-first ordering is applied
    at export). Returns the member dicts."""
    seen, out = set(), []
    for m in guests or []:
        if not match_segment(m, code) or not _contactable(m, code):
            continue
        ph = (m.get("phone") or "").strip()
        key = ph or ("id:%s" % m.get("id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def _tier_weight(audience):
    if not audience:
        return 0.0
    return sum(TIER_RANK.get(m.get("tier"), 0) for m in audience) / float(len(audience))


# ---------------------------------------------------------------------------
# THE BRAIN — recommend_today (PURE).
# ---------------------------------------------------------------------------

def _name(code, lang):
    return ((playbook.get(code) or {}).get(lang) or {}).get("header") or code


def recommend_today(d, availability, guests, assumptions=None, overrides=None, limit=3):
    """Ranked 1–3 recommendations for date `d`.

    availability: {open_units (X), open_unit_nights, ...} from gaps.open_midweek_inventory.
    guests: annotated member dicts. assumptions: {click_through, click_to_book} as fractions.

    Each recommendation states, in structured fields + a plain bilingual sentence:
      Push CODE today at TIME -> to SEGMENT (N people) -> because X apartments are open Sun–Wed
      -> at an assumed C% conversion this should fill ~Y apartments (Y capped at X).
    Ranking: trigger priority (relevance) first, tier weight as the tie-breaker only, then N.
    """
    a = {**ASSUMPTION_DEFAULTS, **(assumptions or {})}
    cc = float(a.get("click_through") or 0.0)
    cb = float(a.get("click_to_book") or 0.0)
    X = int((availability or {}).get("open_units") or 0)
    unit_nights = int((availability or {}).get("open_unit_nights") or 0)
    if X <= 0:
        return []                                              # portfolio full this week — push nothing
    elig = triggers.eligible_campaigns(d, overrides)
    cands = []
    for e in elig:
        code = e["code"]
        aud = segment_audience(code, guests)
        N = len(aud)
        if N == 0:
            continue                                           # trigger live but no audience -> skip
        raw_y = N * cc * cb
        Y = min(int(round(raw_y)), X)
        tl = e["time_label"]
        seg_ar, seg_en = segment_label(code, "ar"), segment_label(code, "en")
        why_ar = ("%s، وفيه %d شقة فاضية وسط الأسبوع. أنسب حملة اليوم هي «%s» لشريحة %s (%d عضو)."
                  % (e["reason_ar"], X, _name(code, "ar"), seg_ar, N))
        why_en = ("%s, and %d apartments are open midweek. Today's best fit is \"%s\" to %s (%d people)."
                  % (e["reason_en"], X, _name(code, "en"), seg_en, N))
        statement_ar = ("ادفع «%s» اليوم %s ← لشريحة %s (%d عضو) ← لأن %d شقة فاضية أحد–أربعاء هذا الأسبوع "
                        "← باحتمال تحويل %.0f%% المفترض تعمّر ~%d شقة."
                        % (_name(code, "ar"), tl["ar"], seg_ar, N, X, cc * cb * 100, Y))
        statement_en = ("Push \"%s\" today at %s → to %s (%d people) → because %d apartments are open "
                        "Sun–Wed this week → at an assumed %.1f%% conversion this should fill ~%d apartments."
                        % (_name(code, "en"), tl["en"], seg_en, N, X, cc * cb * 100, Y))
        cands.append({
            "campaign": code, "name_ar": _name(code, "ar"), "name_en": _name(code, "en"),
            "priority": e["priority"], "time": e["time"],
            "time_label_ar": tl["ar"], "time_label_en": tl["en"], "send_hour": tl["hour"],
            "segment_label_ar": seg_ar, "segment_label_en": seg_en,
            "N": N, "X": X, "open_unit_nights": unit_nights,
            "click_pct": round(cc * 100, 1), "book_pct": round(cb * 100, 1),
            "combined_pct": round(cc * cb * 100, 2),
            "Y": Y, "capped": int(round(raw_y)) > X,
            "trigger_ar": e["reason_ar"], "trigger_en": e["reason_en"],
            "why_ar": why_ar, "why_en": why_en,
            "statement_ar": statement_ar, "statement_en": statement_en,
            "math": {"N": N, "click_pct": round(cc * 100, 1), "book_pct": round(cb * 100, 1),
                     "raw_fill": round(raw_y, 2), "X": X, "Y": Y},
            "url": playbook.button_url(code),
            "_tier_weight": _tier_weight(aud),
        })
    # relevance (priority) first; tier weight breaks ties only; then audience size.
    cands.sort(key=lambda c: (c["priority"], c["_tier_weight"], c["N"]), reverse=True)
    for c in cands:
        c.pop("_tier_weight", None)
    return cands[:max(1, int(limit))]


# ---------------------------------------------------------------------------
# Campaign catalogue (the 20 cards) + Karzoun handoff payloads.
# ---------------------------------------------------------------------------

def _raw_template(code):
    """The RAW Meta/Karzoun template block (both languages) with {{1}} INTACT — what «Copy Karzoun
    template» / «Export templates» use. Never merges a name, unit or date."""
    c = playbook.get(code) or {}
    btn = c.get("button") or {}
    out = {"template_name": c.get("template_name"), "category": c.get("category"),
           "trigger": c.get("trigger"), "button_url": btn.get("url") or ELITE_URL}
    for lang in ("ar", "en"):
        block = c.get(lang) or {}
        out[lang] = {"header": block.get("header") or "", "body": block.get("body") or "",
                     "footer": c.get("footer_%s" % lang) or "",
                     "button": btn.get("text_%s" % lang) or "",
                     "sample": c.get("sample_%s" % lang) or {}}
    return out


def build_campaign_catalogue(d, guests, assumptions=None, overrides=None):
    """All 20 link-driven campaigns as cards: name, trigger, segment + N, eligible-today flag, the
    raw Karzoun template and the ready send message (both languages). Read-only."""
    elig = {e["code"]: e for e in triggers.eligible_campaigns(d, overrides)}
    out = []
    for code in playbook.CODES:
        aud = segment_audience(code, guests)
        e = elig.get(code)
        tl = triggers.time_label(code)
        out.append({
            "campaign": code, "name_ar": _name(code, "ar"), "name_en": _name(code, "en"),
            "trigger_text": (playbook.get(code) or {}).get("trigger") or "",
            "segment_label_ar": segment_label(code, "ar"), "segment_label_en": segment_label(code, "en"),
            "N": len(aud), "eligible_today": bool(e),
            "priority": (e or {}).get("priority", triggers.CAMPAIGN_TRIGGERS.get(code, {}).get("priority", 0)),
            "trigger_ar": (e or {}).get("reason_ar", ""), "trigger_en": (e or {}).get("reason_en", ""),
            "time_label_ar": tl["ar"], "time_label_en": tl["en"],
            "template": _raw_template(code),
            "message_ar": playbook.assembled_message(code, "ar"),
            "message_en": playbook.assembled_message(code, "en"),
            "url": playbook.button_url(code),
        })
    out.sort(key=lambda c: (c["eligible_today"], c["priority"]), reverse=True)
    return out


# ---------------------------------------------------------------------------
# Send-list CSV (per campaign) — the manual Karzoun push vehicle. Columns are a contract.
# ---------------------------------------------------------------------------
SEND_CSV_COLUMNS = ["first_name", "phone", "tier", "campaign", "language"]


def send_list_rows(code, guests, lang="ar"):
    """Deduped, opt-out + fatigue + kill-on-book filtered rows for one campaign's segment."""
    rows = []
    for m in segment_audience(code, guests):
        rows.append([(m.get("first_name") or "").strip(),
                     (m.get("phone") or "").lstrip("+"),
                     m.get("tier") or "", code, lang])
    return rows


def build_send_list_csv(code, guests, lang="ar"):
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(SEND_CSV_COLUMNS)
    for r in send_list_rows(code, guests, lang):
        w.writerow(r)
    safe = str(code or "campaign").lower().replace("-", "_")
    return "ouja_send_%s.csv" % safe, buf.getvalue()


# ============================ LIVE WRAPPER ============================

def _assumptions_from_settings():
    from . import settings
    try:
        cc = settings.get_int("assume_click_through_pct") / 100.0
        cb = settings.get_int("assume_click_to_book_pct") / 100.0
    except Exception:
        cc, cb = ASSUMPTION_DEFAULTS["click_through"], ASSUMPTION_DEFAULTS["click_to_book"]
    return {"click_through": cc, "click_to_book": cb,
            "click_through_pct": round(cc * 100, 1), "click_to_book_pct": round(cb * 100, 1)}


def _holiday_overrides():
    from . import settings
    import json
    raw = settings.get("gap_holidays")
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except (ValueError, TypeError):
        return {}


def load_guests():
    """Members eligible to consider (not quarantined), annotated with the live guardrail signals:
    days_since (from last_stay_date), recent_contact (messaged ≤7d) and recent_campaigns (≤14d)."""
    from . import db, members as members_mod
    from .util import now_dt, parse_date, today_iso
    from datetime import timedelta
    members_mod.ensure_seeded()
    rows = [dict(r) for r in db.q("SELECT * FROM members WHERE tier!='Quarantine'")]
    now = now_dt()
    today = parse_date(today_iso())
    week_ago = (now - timedelta(days=7)).isoformat(timespec="seconds")
    fortnight_ago = (now - timedelta(days=14)).isoformat(timespec="seconds")
    recent7 = {r["member_id"] for r in db.q(
        "SELECT DISTINCT member_id FROM contact_log WHERE sent_at > ?", (week_ago,))}
    recent14 = {}
    for r in db.q("SELECT DISTINCT member_id, campaign_code FROM contact_log WHERE sent_at > ?",
                  (fortnight_ago,)):
        recent14.setdefault(r["member_id"], set()).add(r["campaign_code"])
    for m in rows:
        ds = m.get("days_since")
        if ds is None and m.get("last_stay_date") and today:
            ls = parse_date(m.get("last_stay_date"))
            if ls:
                ds = (today - ls).days
        m["days_since"] = ds
        m["recent_contact"] = m["id"] in recent7
        m["recent_campaigns"] = recent14.get(m["id"], set())
        m["occasion_soon"] = False                            # no DOB/anniversary source yet
    return rows


def build_cards():
    """Production entry point for /api/brain/gaps. Pulls the live grid + member base, computes the
    open-apartment count, today's ranked pushes and the 20-campaign catalogue. Read-only; sends
    nothing. (Name kept as build_cards for the route, though it now returns recommendations.)"""
    from . import gaps as gaps_mod, settings
    from .util import now_iso, today_iso, parse_date
    horizon = settings.get_int("gap_horizon_days")
    grid = gaps_mod.pull_grid(days=max(8, horizon + 1))
    avail = gaps_mod.open_midweek_inventory(grid, horizon_days=horizon)
    guests = load_guests()
    assumptions = _assumptions_from_settings()
    overrides = _holiday_overrides()
    d = parse_date(today_iso())
    recs = recommend_today(d, avail, guests, assumptions, overrides)
    catalogue = build_campaign_catalogue(d, guests, assumptions, overrides)
    by_tier = {}
    for m in guests:
        by_tier[m.get("tier")] = by_tier.get(m.get("tier"), 0) + 1
    return {"date": today_iso(), "availability": avail, "recommendations": recs,
            "campaigns": catalogue, "assumptions": assumptions,
            "members_total": len(guests), "members_by_tier": by_tier,
            "generated_at": now_iso()}
