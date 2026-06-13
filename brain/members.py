"""
brain.members — the member list and tiers.

Phase-1 seed source (Faisal's choice): the existing phone-keyed guest CRM in bot.py
(_guest_profiles), so we have real members immediately. A cleaned member file can be
merged later via seed_from_file() — file rows win on phone/tier.

Tiers (section 5): Turaif 4+ stays · Gold 2–3 · Silver 1 · Quarantine >20 (internal/
corporate — flagged & excluded from sends). All cutoffs are editable settings.

has_upcoming_booking / in_house are refreshed from a forward reservation window so we
never message someone who is arriving or in-house. NOTE: this matches reservations to
members BY PHONE; whether Hostaway's /reservations rows expose a phone on this account
is the one thing to confirm live (we try several field names and log coverage).
"""

from . import db, settings
from .host import HOST
from .util import now_iso, today_iso, days_from_now, parse_date, first_name_of

_RES_PHONE_FIELDS = ("phone", "guestPhone", "phoneNumber", "guestPhoneNumber",
                     "guestMobile", "mobile")
_CONFIRMED = {"new", "modified"}


def valid_phone(p):
    return bool(p) and p.startswith("+") and len(p) >= 9


def tier_for(stays):
    q = settings.get_int("quarantine_min_stays")
    tur = settings.get_int("tier_turaif_min_stays")
    gold = settings.get_int("tier_gold_min_stays")
    s = int(stays or 0)
    if s > q:
        return "Quarantine"
    if s >= tur:
        return "Turaif"
    if s >= gold:
        return "Gold"
    return "Silver"


def _last_stay(profile):
    last = None
    for r in profile.get("reservations", []):
        d = parse_date(r.get("checkout"))
        if d and (last is None or d > last):
            last = d
    return last.isoformat() if last else None


def _upsert(phone, first_name, stays, spend, last_stay, source):
    """Insert or update a member by phone, preserving governor/engagement state."""
    tier = tier_for(stays)
    existing = db.q1("SELECT id FROM members WHERE phone=?", (phone,))
    if existing:
        db.execute(
            "UPDATE members SET first_name=COALESCE(NULLIF(?,''), first_name), tier=?, "
            "stays_count=?, total_spend=?, last_stay_date=?, source=?, updated_at=? "
            "WHERE phone=?",
            (first_name, tier, stays, spend, last_stay, source, now_iso(), phone))
        return existing["id"], False
    mid = db.execute(
        "INSERT INTO members(first_name, phone, tier, stays_count, total_spend, "
        "last_stay_date, source, updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (first_name, phone, tier, stays, spend, last_stay, source, now_iso()))
    return mid, True


def seed_from_crm():
    """Build/refresh members from _guest_profiles. Returns a summary dict."""
    db.init_db()
    profiles = {}
    try:
        profiles = HOST.guest_profiles() if HOST.guest_profiles else {}
    except Exception:
        profiles = {}
    seen = inserted = updated = skipped_no_phone = 0
    for p in (profiles or {}).values():
        phone = (p.get("phone") or "").strip()
        if HOST.normalize_phone and phone:
            phone = HOST.normalize_phone(phone)
        if not valid_phone(phone):
            skipped_no_phone += 1
            continue
        seen += 1
        names = p.get("names") or []
        first = first_name_of(names[0] if names else "")
        stays = len(p.get("reservations", []))
        spend = float(p.get("total_revenue") or 0)
        _id, is_new = _upsert(phone, first, stays, spend, _last_stay(p), "crm")
        inserted += 1 if is_new else 0
        updated += 0 if is_new else 1
    db.audit("system", "seed_from_crm",
             {"seen": seen, "inserted": inserted, "updated": updated,
              "skipped_no_phone": skipped_no_phone})
    return {"seen": seen, "inserted": inserted, "updated": updated,
            "skipped_no_phone": skipped_no_phone}


def seed_from_file(rows):
    """Merge a cleaned member file: rows = [{name, phone, tag}]. File wins on phone/tier.
    `tag` (if a known tier) overrides the derived tier; otherwise tier is derived later."""
    db.init_db()
    inserted = updated = skipped = 0
    tier_tags = {"silver": "Silver", "gold": "Gold", "turaif": "Turaif",
                 "تريف": "Turaif", "تُرَيف": "Turaif", "ذهبي": "Gold", "فضي": "Silver"}
    for r in rows or []:
        phone = (r.get("phone") or "").strip()
        if HOST.normalize_phone and phone:
            phone = HOST.normalize_phone(phone)
        if not valid_phone(phone):
            skipped += 1
            continue
        first = first_name_of(r.get("name") or "")
        existing = db.q1("SELECT id, stays_count, total_spend, last_stay_date FROM members WHERE phone=?", (phone,))
        stays = existing["stays_count"] if existing else 0
        spend = existing["total_spend"] if existing else 0
        last = existing["last_stay_date"] if existing else None
        _id, is_new = _upsert(phone, first, stays, spend, last, "file")
        tag = tier_tags.get((r.get("tag") or "").strip().lower())
        if tag:
            db.execute("UPDATE members SET tier=? WHERE phone=?", (tag, phone))
        inserted += 1 if is_new else 0
        updated += 0 if is_new else 1
    db.audit("system", "seed_from_file", {"inserted": inserted, "updated": updated, "skipped": skipped})
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def sync_upcoming_and_inhouse():
    """Refresh has_upcoming_booking + in_house from a forward reservation window, matched
    by phone. Resets the flags first so departures clear correctly."""
    db.init_db()
    db.execute("UPDATE members SET has_upcoming_booking=0, in_house=0")
    if not HOST.ha_reservations_window:
        return {"scanned": 0, "matched_phone": 0, "no_phone": 0, "note": "host not wired"}
    start = today_iso()
    end = days_from_now(120)
    try:
        res = HOST.ha_reservations_window("arrivalStartDate", "arrivalEndDate", start, end) or []
    except Exception as e:
        return {"scanned": 0, "matched_phone": 0, "no_phone": 0, "error": str(e)[:200]}
    today = today_iso()
    matched = no_phone = 0
    for r in res:
        if (r.get("status") or "").lower() not in _CONFIRMED:
            continue
        phone = ""
        for fld in _RES_PHONE_FIELDS:
            v = r.get(fld)
            if v:
                phone = str(v)
                break
        if not phone:
            no_phone += 1
            continue
        if HOST.normalize_phone:
            phone = HOST.normalize_phone(phone)
        if not valid_phone(phone):
            no_phone += 1
            continue
        arr = parse_date(r.get("arrivalDate"))
        dep = parse_date(r.get("departureDate"))
        in_house = 1 if (arr and dep and arr.isoformat() <= today < dep.isoformat()) else 0
        upd = db.execute(
            "UPDATE members SET has_upcoming_booking=1, in_house=MAX(in_house,?) WHERE phone=?",
            (in_house, phone))
        if upd:
            matched += 1
    db.audit("system", "sync_upcoming_and_inhouse",
             {"scanned": len(res), "matched_phone": matched, "no_phone": no_phone})
    return {"scanned": len(res), "matched_phone": matched, "no_phone": no_phone}


def recompute(full=True):
    """Full refresh: re-seed from CRM (re-derives tiers) + sync upcoming/in-house."""
    out = {"crm": seed_from_crm()}
    if full:
        out["upcoming"] = sync_upcoming_and_inhouse()
    return out


def count():
    db.init_db()
    r = db.q1("SELECT COUNT(*) c FROM members")
    return r["c"] if r else 0


def ensure_seeded():
    """First-run convenience: if there are no members yet, seed from the CRM so the
    dashboard has real data on its very first hit. No-op once seeded."""
    if count() == 0:
        seed_from_crm()
    return count()


# ---- read helpers ----

def get_by_ids(ids):
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    return [dict(r) for r in db.q("SELECT * FROM members WHERE id IN (%s)" % marks, tuple(ids))]


def eligible_pool(tier_targets):
    """Members in the target tiers who aren't structurally excluded (opt-out/quarantine/
    upcoming/in-house). The Governor still applies its time-based rules on top of this."""
    if not tier_targets:
        return []
    marks = ",".join("?" for _ in tier_targets)
    sql = ("SELECT * FROM members WHERE tier IN (%s) AND opted_out=0 AND tier!='Quarantine' "
           "AND has_upcoming_booking=0 AND in_house=0" % marks)
    return [dict(r) for r in db.q(sql, tuple(tier_targets))]


def health_counts():
    """Live List-Health numbers for the dashboard gauge."""
    db.init_db()
    total = db.q1("SELECT COUNT(*) c FROM members")["c"]
    by_tier = {r["tier"]: r["c"] for r in db.q("SELECT tier, COUNT(*) c FROM members GROUP BY tier")}
    opted = db.q1("SELECT COUNT(*) c FROM members WHERE opted_out=1")["c"]
    rested = db.q1("SELECT COUNT(*) c FROM members WHERE rested_until IS NOT NULL AND rested_until > ?",
                   (today_iso(),))["c"]
    upcoming = db.q1("SELECT COUNT(*) c FROM members WHERE has_upcoming_booking=1")["c"]
    inhouse = db.q1("SELECT COUNT(*) c FROM members WHERE in_house=1")["c"]
    # rolling opt-out rate over last 30 days
    opt30 = db.q1("SELECT COUNT(*) c FROM opt_outs WHERE opted_out_at > ?",
                  (days_from_now(-30),))["c"]
    return {"total": total, "by_tier": by_tier, "opted_out": opted, "rested": rested,
            "upcoming": upcoming, "in_house": inhouse, "opt_out_30d": opt30}
