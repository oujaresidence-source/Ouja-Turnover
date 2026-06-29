"""
brain.retier — nightly re-tiering of the member base from realized Hostaway stays (build
spec §1). This keeps the base current so the Weekday-Gap Engine always targets real behaviour.

Two layers, deliberately split so the math is unit-testable offline:

  • PURE CORE  `retier(rows, today, ...)` — takes already-aggregated per-phone rows
    {phone,name,stays,spend,last_stay,weekday_share,preferred_unit,cancels,nights,median_adr}
    and returns each row enriched with days_since + score + tier, using the exact §1 formula
    (percentile-ranked RFM score, sp75/sp90 spend cuts, the tier ladder incl. Prospect). No DB,
    no network — the synthetic tests drive it directly.

  • LIVE LAYER `load_aggregates()` + `recompute_tiers()` — pulls realized reservations through
    the host (HOST.ha_reservations_window), groups them by phone, runs the pure core, and writes
    the result onto the members table (additive columns). Reservation phone coverage is the one
    live unknown (some Hostaway accounts don't expose a phone on /reservations rows), so the
    loader logs matched-vs-missing exactly like brain.members.sync_upcoming_and_inhouse.

Quarantine (internal/corporate, >quarantine_min stays) is preserved on top of the §1 ladder so
the anti-spam exclusion never regresses; the §1 spec itself only goes up to Turaif.
"""

import bisect
from collections import Counter
from . import db, settings
from .host import HOST
from .util import now_iso, today_iso, parse_date, first_name_of

_CONFIRMED = {"new", "modified"}
_CANCELLED = {"cancelled", "canceled"}
_RES_PHONE_FIELDS = ("phone", "guestPhone", "phoneNumber", "guestPhoneNumber",
                     "guestMobile", "mobile")
# Sun–Wed in Python weekday() terms (Mon=0..Sun=6): the "weekday-regular" signal.
_WEEKDAY_ARRIVAL = frozenset({6, 0, 1, 2})

# §1 score weights (frequency / spend / recency). Exposed so a test can pin them.
DEFAULT_WEIGHTS = (0.40, 0.35, 0.25)


# --------------------------------------------------------------------------
# statistics helpers
# --------------------------------------------------------------------------

def pct_rank(value, sorted_vals):
    """Percentile rank of `value` within sorted_vals, in (0,1]: fraction of the population
    that is <= value. Empty population -> 0.5 (neutral)."""
    n = len(sorted_vals)
    if n == 0:
        return 0.5
    return bisect.bisect_right(sorted_vals, value) / n


def percentile(sorted_vals, q):
    """Linear-interpolation percentile (q in 0..100). Empty -> 0."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return float(sorted_vals[0])
    pos = (q / 100.0) * (n - 1)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return float(sorted_vals[lo]) * (1 - frac) + float(sorted_vals[hi]) * frac


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# --------------------------------------------------------------------------
# PURE CORE
# --------------------------------------------------------------------------

def _tier(stays, spend, days_since, sp75, sp90, quarantine_min):
    """The §1 tier ladder. quarantine_min preserves the internal/corporate exclusion."""
    s = int(stays or 0)
    if quarantine_min and s > quarantine_min:
        return "Quarantine"
    recent = (days_since is not None and days_since <= 240)
    if s >= 5 or (s >= 3 and spend >= sp90):
        return "Turaif" if recent else "Gold"
    if s >= 3 or (s == 2 and spend >= sp75):
        return "Gold"
    if s == 2:
        return "Silver"
    return "Prospect"


def retier(rows, today=None, weights=DEFAULT_WEIGHTS, quarantine_min=None):
    """Enrich aggregated per-phone rows with days_since, score, tier (build spec §1).

    Returns a NEW list of dicts; never mutates the inputs in place beyond adding fields.
    """
    rows = [dict(r) for r in (rows or [])]
    today_d = parse_date(today) if today else parse_date(today_iso())
    if quarantine_min is None:
        try:
            quarantine_min = settings.get_int("quarantine_min_stays")
        except Exception:
            quarantine_min = 20
    w_stay, w_spend, w_rec = weights

    # days_since per row
    for r in rows:
        ls = parse_date(r.get("last_stay"))
        r["days_since"] = (today_d - ls).days if (ls and today_d) else None

    # population distributions
    stays_sorted = sorted(int(r.get("stays") or 0) for r in rows)
    spend_sorted = sorted(float(r.get("spend") or 0) for r in rows)
    days_known = sorted(r["days_since"] for r in rows if r["days_since"] is not None)
    repeater_spend = sorted(float(r.get("spend") or 0) for r in rows if int(r.get("stays") or 0) >= 2)
    sp75 = percentile(repeater_spend, 75)
    sp90 = percentile(repeater_spend, 90)

    for r in rows:
        stays = int(r.get("stays") or 0)
        spend = float(r.get("spend") or 0)
        ds = r["days_since"]
        pr_stays = pct_rank(stays, stays_sorted)
        pr_spend = pct_rank(spend, spend_sorted)
        pr_days = pct_rank(ds, days_known) if ds is not None else 1.0   # no last stay = worst recency
        raw = 100.0 * (w_stay * pr_stays + w_spend * pr_spend + w_rec * (1.0 - pr_days))
        raw -= 3 * min(int(r.get("cancels") or 0), 5)
        r["score"] = round(_clamp(raw, 0.0, 100.0), 1)
        r["tier"] = _tier(stays, spend, ds, sp75, sp90, quarantine_min)
        wshare = r.get("weekday_share")
        r["weekday_pattern"] = 1 if (wshare is not None and float(wshare) >= 0.5) else 0
        lshare = r.get("lastmin_share")
        r["lastmin"] = 1 if (lshare is not None and float(lshare) >= 0.5) else 0

    return {"rows": rows, "sp75": round(sp75), "sp90": round(sp90),
            "population": len(rows), "repeaters": len(repeater_spend)}


# --------------------------------------------------------------------------
# LIVE LAYER — pull realized stays, aggregate by phone, write the members table
# --------------------------------------------------------------------------

def _norm(p):
    p = (p or "").strip()
    if HOST.normalize_phone and p:
        p = HOST.normalize_phone(p)
    return p


def _res_phone(r):
    for fld in _RES_PHONE_FIELDS:
        if r.get(fld):
            return _norm(r.get(fld))
    return ""


def _windows(lookback_days, chunk_days=30):
    """Month-sized [start,end] ISO windows back over the lookback, to stay under the
    per-call reservation cap. Today is the end of the most recent window."""
    from datetime import timedelta
    end = parse_date(today_iso())
    out = []
    span = max(1, int(lookback_days))
    step = max(1, int(chunk_days))
    cur = 0
    while cur < span:
        w_end = end - timedelta(days=cur)
        w_start = end - timedelta(days=min(cur + step, span))
        out.append((w_start.isoformat(), w_end.isoformat()))
        cur += step
    return out


def load_aggregates(lookback_days=None):
    """Group realized stays by phone over the lookback window. Returns
    (aggregate_rows, coverage). Realized = status in {new,modified}; cancellations counted
    separately. preferred_unit = modal listing name; median_adr = median totalPrice/nights."""
    if lookback_days is None:
        lookback_days = settings.get_int("retier_lookback_days")
    fn = HOST.ha_reservations_window
    if not fn:
        return [], {"scanned": 0, "matched_phone": 0, "no_phone": 0, "note": "host not wired"}
    listings = {}
    try:
        listings = (HOST.get_listings_map() or {}) if HOST.get_listings_map else {}
    except Exception:
        listings = {}
    groups = {}            # lid -> area/compound (the listings store `group`)
    try:
        ls = HOST.ls_get() if HOST.ls_get else {}
        for lid, rec in ((ls or {}).get("listings") or {}).items():
            groups[str(lid)] = rec.get("group") or ""
    except Exception:
        groups = {}

    by_phone = {}                         # phone -> aggregate accumulator
    seen_res = set()                      # dedup by reservation id across overlapping windows
    scanned = matched = no_phone = cancelled_rows = 0
    for w_start, w_end in _windows(lookback_days):
        try:
            res = fn("arrivalStartDate", "arrivalEndDate", w_start, w_end) or []
        except Exception as e:
            print("[retier] window %s..%s error: %s" % (w_start, w_end, str(e)[:160]))
            continue
        for r in res:
            rid = r.get("id")
            if rid in seen_res:
                continue
            seen_res.add(rid)
            scanned += 1
            status = (r.get("status") or "").lower()
            phone = _res_phone(r)
            if not (phone and phone.startswith("+")):
                no_phone += 1
                continue
            acc = by_phone.get(phone)
            if acc is None:
                acc = by_phone[phone] = {"phone": phone, "full": "", "first": "", "stays": 0,
                                         "spend": 0.0, "nights": 0, "cancels": 0, "last_stay": None,
                                         "wd_hits": 0, "lastmin_hits": 0, "_adrs": [],
                                         "_unit_lids": Counter()}
            if not acc["full"]:
                gn = (r.get("guestName") or "").strip()
                acc["full"] = gn
                acc["first"] = first_name_of(gn)
            if status in _CANCELLED:
                acc["cancels"] += 1
                cancelled_rows += 1
                continue
            if status not in _CONFIRMED:
                continue
            matched += 1
            arr = parse_date(r.get("arrivalDate"))
            nights = int(r.get("nights") or 0) or 1
            price = float(r.get("totalPrice") or 0)
            acc["stays"] += 1
            acc["spend"] += price
            acc["nights"] += nights
            if arr and (acc["last_stay"] is None or arr.isoformat() > acc["last_stay"]):
                acc["last_stay"] = arr.isoformat()
            if arr and arr.weekday() in _WEEKDAY_ARRIVAL:
                acc["wd_hits"] += 1
            if price > 0 and nights > 0:
                acc["_adrs"].append(price / nights)
            bd = parse_date(r.get("reservationDate") or r.get("insertedOn"))
            if bd and arr:
                lead = (arr - bd).days
                if 0 <= lead <= 2:
                    acc["lastmin_hits"] += 1
            lid = str(r.get("listingMapId") or "")
            if lid:
                acc["_unit_lids"][lid] += 1

    rows = []
    for acc in by_phone.values():
        stays = acc["stays"]
        adrs = sorted(acc["_adrs"])
        pref_lid = acc["_unit_lids"].most_common(1)[0][0] if acc["_unit_lids"] else None
        rows.append({
            "phone": acc["phone"], "full_name": acc["full"], "first": acc["first"],
            "name": acc["full"], "stays": stays,
            "spend": round(acc["spend"], 2), "nights": acc["nights"], "cancels": acc["cancels"],
            "last_stay": acc["last_stay"],
            "weekday_share": (acc["wd_hits"] / stays) if stays else 0.0,
            "lastmin_share": (acc["lastmin_hits"] / stays) if stays else 0.0,
            "preferred_unit": (listings.get(pref_lid) or pref_lid) if pref_lid else None,
            "preferred_area": groups.get(pref_lid) if pref_lid else None,
            "median_adr": round(percentile(adrs, 50)) if adrs else 0,
        })
    coverage = {"scanned": scanned, "realized": matched, "cancelled": cancelled_rows,
                "no_phone": no_phone, "phones": len(by_phone)}
    return rows, coverage


def recompute_tiers(lookback_days=None):
    """Full nightly re-tier: load realized stays -> §1 score/tier -> write members. Preserves
    each member's Governor/engagement columns (opt-out, rest, ignores, last_contacted, trust_ok)
    and only refreshes the RFM profile. Inserts members seen in stays but not yet in the base."""
    db.init_db()
    rows, coverage = load_aggregates(lookback_days)
    if not rows:
        db.audit("system", "retier", {"written": 0, **coverage})
        return {"written": 0, "inserted": 0, "updated": 0, **coverage}

    res = retier(rows)
    enriched = res["rows"]
    existing = {r["phone"] for r in db.q("SELECT phone FROM members")}
    now = now_iso()
    inserts, updates = [], []
    for r in enriched:
        ph = r["phone"]
        first = r.get("first") or r.get("full_name") or r.get("name") or ""
        full = r.get("full_name") or r.get("name") or first
        common = (first, full, r["tier"], int(r["stays"]), float(r["spend"]),
                  r.get("last_stay"), r.get("score"), r.get("days_since"),
                  int(r.get("weekday_pattern") or 0), int(r.get("lastmin") or 0),
                  r.get("preferred_unit"), r.get("preferred_area"),
                  int(r.get("cancels") or 0), float(r.get("median_adr") or 0),
                  int(r.get("nights") or 0), now, now)
        if ph in existing:
            updates.append(common + (ph,))
        else:
            inserts.append((ph,) + common)

    if inserts:
        db.executemany(
            "INSERT INTO members(phone, first_name, full_name, tier, stays_count, total_spend, "
            "last_stay_date, score, days_since, weekday_pattern, lastmin, preferred_unit, "
            "preferred_area, cancellations, median_adr, nights_total, last_retier, updated_at, source) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'retier')", inserts)
    if updates:
        db.executemany(
            "UPDATE members SET first_name=?, full_name=?, tier=?, stays_count=?, total_spend=?, "
            "last_stay_date=?, score=?, days_since=?, weekday_pattern=?, lastmin=?, preferred_unit=?, "
            "preferred_area=?, cancellations=?, median_adr=?, nights_total=?, last_retier=?, "
            "updated_at=? WHERE phone=?", updates)

    out = {"written": len(enriched), "inserted": len(inserts), "updated": len(updates),
           "sp75": res["sp75"], "sp90": res["sp90"], **coverage}
    db.audit("system", "retier", out)
    return out
