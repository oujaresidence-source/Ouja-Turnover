"""
brain.governor — the SACRED anti-nag chokepoint. Every outbound passes through screen().
It returns, per member, include OR exclude-with-a-reason, so the dashboard can show
exactly why anyone was held back. Nothing about volume or messaging bypasses this.

Rules (all from editable settings, build spec section 9):
  • max N msgs / member / rolling 7 days        (default 2)
  • min gap between messages                     (default 48h)
  • respect auto-rest                            (rested_until in the future)
  • suppress upcoming-booking / in-house         (never promo an arriving/in-house guest)
  • suppress recently-booked                     (default last 14 days)
  • permanent opt-out                            (flag OR opt_outs table)
  • quarantine (>20 stays internal/corporate)
Plus send-window + warm-up daily cap (applied as the final volume ceiling).
"""

from datetime import timedelta
from . import db, settings
from .util import now_dt, now_iso, today_iso, parse_date, clampi


def _reason(code_ar, code_en):
    return {"reason": code_ar, "reason_en": code_en}


def _opted_out_phones():
    return {r["phone"] for r in db.q("SELECT phone FROM opt_outs")}


def screen(members, campaign_code=None):
    """members = list of member dicts. Returns {included:[...], excluded:[{member_id,
    first_name, phone, **reason}]}. Pure read of contact_log; writes nothing."""
    db.init_db()
    included, excluded = [], []
    if not members:
        return {"included": [], "excluded": []}

    max_7d = settings.get_int("gov_max_msgs_per_7d")
    min_gap_h = settings.get_int("gov_min_gap_hours")
    suppress_booked = settings.get_int("gov_suppress_booked_days")
    now = now_dt()
    today = today_iso()
    week_ago = (now - timedelta(days=7)).isoformat(timespec="seconds")
    gap_cutoff = (now - timedelta(hours=min_gap_h)).isoformat(timespec="seconds")
    booked_cutoff = (now.date() - timedelta(days=suppress_booked)).isoformat()

    ids = [m["id"] for m in members if m.get("id") is not None]
    counts7d, last_sent = {}, {}
    if ids:
        marks = ",".join("?" for _ in ids)
        for r in db.q("SELECT member_id, COUNT(*) c FROM contact_log "
                      "WHERE sent_at > ? AND member_id IN (%s) GROUP BY member_id" % marks,
                      tuple([week_ago] + ids)):
            counts7d[r["member_id"]] = r["c"]
        for r in db.q("SELECT member_id, MAX(sent_at) last FROM contact_log "
                      "WHERE member_id IN (%s) GROUP BY member_id" % marks, tuple(ids)):
            last_sent[r["member_id"]] = r["last"]
    opted_phones = _opted_out_phones()

    for m in members:
        mid = m.get("id")
        base = {"member_id": mid, "first_name": m.get("first_name") or "", "phone": m.get("phone")}

        if m.get("opted_out") or (m.get("phone") in opted_phones):
            excluded.append({**base, **_reason("ألغى الاشتراك نهائياً", "permanently opted out")}); continue
        if (m.get("tier") or "") == "Quarantine":
            excluded.append({**base, **_reason("محجوز (داخلي/شركات >20 إقامة)", "quarantined (internal/corporate)")}); continue
        ru = m.get("rested_until")
        if ru and str(ru) > today:
            excluded.append({**base, **_reason("في فترة راحة حتى %s" % ru, "resting until %s" % ru)}); continue
        if m.get("has_upcoming_booking"):
            excluded.append({**base, **_reason("عنده حجز قادم", "has an upcoming booking")}); continue
        if m.get("in_house"):
            excluded.append({**base, **_reason("مقيم حالياً", "currently in-house")}); continue
        ls = m.get("last_stay_date")
        if ls and str(ls) >= booked_cutoff:
            excluded.append({**base, **_reason("حجز/أقام خلال %d يوم" % suppress_booked,
                                               "booked/stayed within %d days" % suppress_booked)}); continue
        c7 = counts7d.get(mid, 0)
        if c7 >= max_7d:
            excluded.append({**base, **_reason("وصل الحد %d رسائل/7 أيام" % max_7d,
                                               "hit %d msgs / 7 days" % max_7d)}); continue
        last = last_sent.get(mid)
        if last and last > gap_cutoff:
            excluded.append({**base, **_reason("آخر رسالة قبل أقل من %d ساعة" % min_gap_h,
                                               "messaged < %dh ago" % min_gap_h)}); continue
        included.append(m)

    return {"included": included, "excluded": excluded}


# ---------------- send window + volume ceiling ----------------

def send_window(now=None):
    """Compute the next allowed scheduled send time. Default 20:30 KSA; never before the
    earliest hour; Friday 00:00–HH:00 is quiet (the default 20:30 already clears it)."""
    now = now or now_dt()
    # Clamp to valid clock ranges — an out-of-range setting (e.g. hour 24 typed in the
    # Settings tab) must never crash datetime.replace() and 500 the whole "Today's Move".
    hour = clampi(settings.get_int("gov_send_hour"), 0, 23)
    minute = clampi(settings.get_int("gov_send_minute"), 0, 59)
    earliest = clampi(settings.get_int("gov_earliest_hour"), 0, 23)
    fri_until = clampi(settings.get_int("gov_no_friday_until_hour"), 0, 23)
    hour = max(hour, earliest)

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    # Friday quiet hours: if the target somehow lands in 00:00–fri_until on a Friday, bump it.
    if target.weekday() == 4 and target.hour < fri_until:
        target = target.replace(hour=max(hour, fri_until))
    allowed_now = not (now.weekday() == 4 and now.hour < fri_until) and now.hour >= earliest
    return {"allowed_now": allowed_now, "scheduled_time": target.isoformat(timespec="minutes"),
            "send_hour": hour, "send_minute": minute}


def effective_daily_cap():
    """Warm-up-aware daily ceiling. If the ramp hasn't started, use the most conservative
    (week-1) cap. Never exceeds the hard daily_send_cap."""
    hard = settings.get_int("daily_send_cap")
    w1 = settings.get_int("warmup_week1_cap")
    w2 = settings.get_int("warmup_week2_cap")
    w3 = settings.get_int("warmup_week3_cap")
    started = settings.get("warmup_started_on") or ""
    start_d = parse_date(started)
    if not start_d:
        return min(w1, hard)
    days = (now_dt().date() - start_d).days
    if days < 7:
        cap = w1
    elif days < 14:
        cap = w2
    elif days < 21:
        cap = w3
    else:
        cap = hard
    return min(cap, hard)


def sent_today():
    n = db.q1("SELECT COUNT(*) c FROM contact_log WHERE substr(sent_at,1,10)=?", (today_iso(),))
    return n["c"] if n else 0


def remaining_today():
    return max(0, effective_daily_cap() - sent_today())


def opt_out(phone, source="dashboard"):
    """Permanent opt-out: log it and flag the member."""
    db.execute("INSERT INTO opt_outs(phone, opted_out_at, source) VALUES(?,?,?) "
               "ON CONFLICT(phone) DO UPDATE SET opted_out_at=excluded.opted_out_at",
               (phone, now_iso(), source))
    db.execute("UPDATE members SET opted_out=1 WHERE phone=?", (phone,))
    db.audit(source, "opt_out", {"phone": phone})
