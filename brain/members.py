"""
brain.members — the member list and tiers.

Seed sources (Faisal): the cleaned member file (authoritative on phone/tier) merged with the
existing guest CRM (_guest_profiles) for anyone the file doesn't have. The member file holds
4.5k real phone numbers, so it is NOT committed to git — it is uploaded once via the dashboard
and stored on the Railway volume (brain_members_seed.json), exactly like guest_profiles.json.

Tiers (section 5): Turaif 4+ stays · Gold 2–3 · Silver 1 · Quarantine >20 (internal/corporate,
flagged & excluded). The file's tier is honored; quarantine (>20 stays) is always enforced.

has_upcoming_booking / in_house come from a forward reservation window matched BY PHONE.
Whether Hostaway's /reservations rows expose a phone on this account is the one live thing to
confirm — we try several field names and log coverage.
"""

from . import db, settings
from .host import HOST
from .util import now_iso, today_iso, days_from_now, parse_date, first_name_of

_RES_PHONE_FIELDS = ("phone", "guestPhone", "phoneNumber", "guestPhoneNumber",
                     "guestMobile", "mobile")
_CONFIRMED = {"new", "modified"}
_KNOWN_TIERS = {"Silver", "Gold", "Turaif", "Quarantine"}
SEED_FILE_NAME = "brain_members_seed.json"


def valid_phone(p):
    return bool(p) and p.startswith("+") and len(p) >= 9


def _norm(p):
    p = (p or "").strip()
    if HOST.normalize_phone and p:
        p = HOST.normalize_phone(p)
    return p


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


def _resolve_tier(file_tier, stays):
    """File tier wins for the Silver/Gold/Turaif split; quarantine (>20) is always enforced."""
    q = settings.get_int("quarantine_min_stays")
    if stays and int(stays) > q:
        return "Quarantine"
    if file_tier in _KNOWN_TIERS:
        return file_tier
    return tier_for(stays)


def _last_stay(profile):
    last = None
    for r in profile.get("reservations", []):
        d = parse_date(r.get("checkout"))
        if d and (last is None or d > last):
            last = d
    return last.isoformat() if last else None


# --------------------------------------------------------------------------
# Bulk upsert — ONE connection, executemany. (Per-row execute on 4.5k rows would
# open thousands of connections and block the first dashboard hit.)
# --------------------------------------------------------------------------

def _bulk_upsert(rows, source, insert_only=False):
    """rows = [{first_name, phone, tier(opt), stays, spend, last}]. Preserves each member's
    governor/engagement columns on update (only refreshes the profile fields)."""
    db.init_db()
    # normalize + dedupe by phone (keep last), drop invalid
    norm = {}
    for r in rows or []:
        ph = _norm(r.get("phone"))
        if not valid_phone(ph):
            continue
        stays = int(r.get("stays") or 0)
        norm[ph] = (first_name_of(r.get("first_name") or r.get("name") or ""), ph,
                    _resolve_tier(r.get("tier"), stays), stays,
                    float(r.get("spend") or 0), r.get("last"), source, now_iso())
    if not norm:
        return {"inserted": 0, "updated": 0, "skipped": 0}
    existing = {r["phone"] for r in db.q("SELECT phone FROM members")}
    inserts, updates = [], []
    for ph, t in norm.items():
        if ph in existing:
            if not insert_only:
                # (first_name, tier, stays, spend, last, source, updated_at, phone)
                updates.append((t[0], t[2], t[3], t[4], t[5], t[6], t[7], ph))
        else:
            inserts.append(t)        # (first_name, phone, tier, stays, spend, last, source, updated_at)
    if inserts:
        db.executemany(
            "INSERT INTO members(first_name, phone, tier, stays_count, total_spend, "
            "last_stay_date, source, updated_at) VALUES(?,?,?,?,?,?,?,?)", inserts)
    if updates:
        db.executemany(
            "UPDATE members SET first_name=?, tier=?, stays_count=?, total_spend=?, "
            "last_stay_date=?, source=?, updated_at=? WHERE phone=?", updates)
    return {"inserted": len(inserts), "updated": len(updates),
            "skipped": len(rows or []) - len(norm)}


def _lc(r):
    """Lower-case a row's keys so we read it CASE-INSENSITIVELY (the shipped files use
    capitalized Karzoum keys Name/Phone/Tag; older exports use first_name/phone/tier)."""
    return {str(k).lower(): v for k, v in r.items()} if isinstance(r, dict) else {}


def seed_from_file(rows):
    """Seed/refresh from a member file (authoritative on phone/tier). Accepts BOTH the
    Karzoum-style Name/Phone/Tag and the richer first_name/phone/tier/stays_count keys,
    matched case-insensitively."""
    mapped = []
    for r in (rows or []):
        rr = _lc(r)
        mapped.append({
            "first_name": rr.get("first_name") or rr.get("name"),
            "phone": rr.get("phone"),
            "tier": rr.get("tier") or rr.get("tag"),
            "stays": rr.get("stays_count") or rr.get("stays"),
            "spend": rr.get("total_spend") or rr.get("spend"),
            "last": rr.get("last_stay_date") or rr.get("last_stay") or rr.get("last"),
        })
    out = _bulk_upsert(mapped, "file")
    db.audit("system", "seed_from_file", out)
    return out


def seed_from_crm(insert_only=False):
    """Seed/enrich from the guest CRM. insert_only=True (used after the file seed) adds only
    members the file didn't have, never overwriting file tiers."""
    profiles = {}
    try:
        profiles = HOST.guest_profiles() if HOST.guest_profiles else {}
    except Exception:
        profiles = {}
    rows = []
    for p in (profiles or {}).values():
        names = p.get("names") or []
        rows.append({"first_name": names[0] if names else "", "phone": p.get("phone"),
                     "tier": None, "stays": len(p.get("reservations", [])),
                     "spend": p.get("total_revenue"), "last": _last_stay(p)})
    out = _bulk_upsert(rows, "crm", insert_only=insert_only)
    db.audit("system", "seed_from_crm", {**out, "insert_only": insert_only})
    return out


# ---- seed file on the volume (PII stays off git) ----

def load_seed_file():
    try:
        data = HOST.load_json(SEED_FILE_NAME, None) if HOST.load_json else None
    except Exception:
        data = None
    if isinstance(data, dict):
        data = data.get("members")
    return data if isinstance(data, list) and data else None


def save_seed_file(rows):
    if HOST.save_json:
        HOST.save_json(SEED_FILE_NAME, rows)


def import_member_file(rows):
    """Dashboard upload: MERGE rows into the volume seed file (union by phone, newest wins),
    then seed (file authoritative) + CRM fill. Merging means importing the Silver/Gold/Turaif
    files one by one ACCUMULATES instead of overwriting; importing ALL_members works too."""
    incoming = [r for r in (rows or []) if isinstance(r, dict)]
    merged = {}
    for r in (load_seed_file() or []) + incoming:
        ph = _norm(_lc(r).get("phone"))
        if ph:
            merged[ph] = r                      # later (incoming) overwrites earlier
    allrows = list(merged.values())
    save_seed_file(allrows)
    res = {"received": len(incoming), "stored_total": len(allrows),
           "file": seed_from_file(allrows), "crm_enrich": seed_from_crm(insert_only=True)}
    db.audit("dashboard", "import_member_file",
             {"received": len(incoming), "stored_total": len(allrows), **res["file"]})
    return res


def sync_upcoming_and_inhouse():
    """Refresh has_upcoming_booking + in_house from a forward reservation window, matched by
    phone. Resets the flags first so departures clear correctly."""
    db.init_db()
    db.execute("UPDATE members SET has_upcoming_booking=0, in_house=0")
    if not HOST.ha_reservations_window:
        return {"scanned": 0, "matched_phone": 0, "no_phone": 0, "note": "host not wired"}
    try:
        res = HOST.ha_reservations_window("arrivalStartDate", "arrivalEndDate",
                                          today_iso(), days_from_now(120)) or []
    except Exception as e:
        return {"scanned": 0, "matched_phone": 0, "no_phone": 0, "error": str(e)[:200]}
    today = today_iso()
    matched = no_phone = 0
    for r in res:
        if (r.get("status") or "").lower() not in _CONFIRMED:
            continue
        phone = ""
        for fld in _RES_PHONE_FIELDS:
            if r.get(fld):
                phone = _norm(r.get(fld))
                break
        if not valid_phone(phone):
            no_phone += 1
            continue
        arr = parse_date(r.get("arrivalDate"))
        dep = parse_date(r.get("departureDate"))
        in_house = 1 if (arr and dep and arr.isoformat() <= today < dep.isoformat()) else 0
        if db.execute("UPDATE members SET has_upcoming_booking=1, in_house=MAX(in_house,?) "
                      "WHERE phone=?", (in_house, phone)):
            matched += 1
    out = {"scanned": len(res), "matched_phone": matched, "no_phone": no_phone}
    db.audit("system", "sync_upcoming_and_inhouse", out)
    return out


def recompute(full=True):
    """Full refresh: file (if present, authoritative) + CRM enrichment, then upcoming/in-house."""
    rows = load_seed_file()
    if rows:
        out = {"file": seed_from_file(rows), "crm_enrich": seed_from_crm(insert_only=True)}
    else:
        out = {"crm": seed_from_crm()}
    if full:
        out["upcoming"] = sync_upcoming_and_inhouse()
    return out


def count():
    db.init_db()
    r = db.q1("SELECT COUNT(*) c FROM members")
    return r["c"] if r else 0


def ensure_seeded():
    """First-run: seed from the uploaded file if present, else the CRM, so the dashboard has
    real data on its first hit. No-op once seeded."""
    if count() == 0:
        rows = load_seed_file()
        if rows:
            seed_from_file(rows)
            seed_from_crm(insert_only=True)
        else:
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
    db.init_db()
    total = db.q1("SELECT COUNT(*) c FROM members")["c"]
    by_tier = {r["tier"]: r["c"] for r in db.q("SELECT tier, COUNT(*) c FROM members GROUP BY tier")}
    opted = db.q1("SELECT COUNT(*) c FROM members WHERE opted_out=1")["c"]
    rested = db.q1("SELECT COUNT(*) c FROM members WHERE rested_until IS NOT NULL AND rested_until > ?",
                   (today_iso(),))["c"]
    upcoming = db.q1("SELECT COUNT(*) c FROM members WHERE has_upcoming_booking=1")["c"]
    inhouse = db.q1("SELECT COUNT(*) c FROM members WHERE in_house=1")["c"]
    opt30 = db.q1("SELECT COUNT(*) c FROM opt_outs WHERE opted_out_at > ?", (days_from_now(-30),))["c"]
    have_file = bool(load_seed_file())
    return {"total": total, "by_tier": by_tier, "opted_out": opted, "rested": rested,
            "upcoming": upcoming, "in_house": inhouse, "opt_out_30d": opt30, "have_seed_file": have_file}
