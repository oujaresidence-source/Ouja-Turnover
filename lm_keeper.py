# -*- coding: utf-8 -*-
"""Same-day price keeper «حارس سعر الليلة» — PURE rules (no bot import, no network).

bot.py wires the I/O (Hostaway reads/writes, Discord, state files); every decision lives here
so it can be tested on fake data. Spec: docs/superpowers/specs/2026-11-02-lm-price-keeper-design.md
"""
from datetime import date, datetime, timedelta, timezone

RIYADH = timezone(timedelta(hours=3))
CONFIRMED = ("new", "modified")
FEE_KEYS = ("cleaningFee", "totalTax", "cityTax", "securityDepositFee")


# ---- step / target / decide -------------------------------------------------------------

def step_pct(now, steps):
    """Discount % in force at `now`. steps = [(hour, pct), ...] ascending; 0 before the first."""
    pct = 0.0
    for hour, p in steps:
        if now.hour >= int(hour):
            pct = float(p)
    return pct


def step_started_at(now, steps):
    """When the step in force at `now` began (None before the first step)."""
    start = None
    for hour, _p in steps:
        if now.hour >= int(hour):
            start = now.replace(hour=int(hour), minute=0, second=0, microsecond=0)
    return start


def target_price(original, pct, minimum=0):
    """`pct`% off tonight's ORIGINAL price (never compounding), never below `minimum`."""
    raw = int(round(float(original) * (100.0 - float(pct)) / 100.0))
    return max(raw, int(minimum or 0))


def decide(day, original, pct, minimum, pending):
    """One unit, one tick. `day` is tonight's Hostaway calendar row."""
    available = int(day.get("isAvailable", 0) or 0) == 1
    current = day.get("price")
    if not available or day.get("reservationId") or not current:
        return {"action": "booked", "target": None, "current": None, "floor_blocked": False}
    current = int(round(float(current)))
    if float(pct) <= 0:
        return {"action": "hold", "target": current, "current": current, "floor_blocked": False}
    if pending:                                   # a guest mid-booking must not see the price move
        return {"action": "wait_pending", "target": None, "current": current, "floor_blocked": False}
    raw = int(round(float(original) * (100.0 - float(pct)) / 100.0))
    tgt = target_price(original, pct, minimum)
    blocked = bool(minimum) and raw < int(minimum)
    if current <= tgt:                            # already there, or someone set it lower: never raise
        return {"action": "hold", "target": tgt, "current": current, "floor_blocked": blocked}
    return {"action": "write", "target": tgt, "current": current, "floor_blocked": blocked}


# ---- "lowest that sold" minimum ---------------------------------------------------------

def booked_at_riyadh(res):
    """Hostaway reservationDate is UTC ("YYYY-MM-DD HH:MM:SS") — verified 2026-11-01 against
    the reservation page's charge times. Returns an aware Riyadh datetime, or None."""
    s = str(res.get("reservationDate") or "")[:19]
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(RIYADH)


def nightly_price(res):
    """Accommodation-only nightly rate (fees stripped when Hostaway gives them)."""
    tp = res.get("totalPrice")
    try:
        n = int(res.get("nights") or 0)
    except (TypeError, ValueError):
        n = 0
    if not isinstance(tp, (int, float)) or tp <= 0 or n <= 0:
        return None
    fees = sum(float(res[k]) for k in FEE_KEYS
               if isinstance(res.get(k), (int, float)) and res.get(k) > 0)
    acc = float(tp) - fees
    return (acc if acc > 0 else float(tp)) / n


def is_same_night(res):
    b = booked_at_riyadh(res)
    return bool(b) and b.date().isoformat() == str(res.get("arrivalDate") or "")[:10]


def _confirmed(res):
    return str(res.get("status") or "").lower() in CONFIRMED


def build_minimums(reservations, min_samples=5):
    """{lid: {"min", "n", "median"}} — the lowest price each unit actually sold at for the same
    night. Prices under half the unit's median are data errors / family stays and are dropped;
    a unit with fewer than `min_samples` real sales gets no entry (= no sold-minimum)."""
    by = {}
    for r in reservations:
        lid = r.get("listingMapId")
        if not lid or not _confirmed(r) or not is_same_night(r):
            continue
        p = nightly_price(r)
        if p:
            by.setdefault(str(lid), []).append(p)
    out = {}
    for lid, ps in by.items():
        ps.sort()
        med = ps[len(ps) // 2]
        kept = [p for p in ps if p >= 0.5 * med]
        if len(kept) < int(min_samples):
            continue
        out[lid] = {"min": int(round(kept[0])), "n": len(kept), "median": int(round(med))}
    return out


# ---- nightly report ---------------------------------------------------------------------

def night_bookings(reservations, night, units, steps):
    """Confirmed same-night bookings for `night`, each tagged `from_drop` only when it was made
    AFTER that unit's first drop write that day."""
    out = []
    for r in reservations:
        if not _confirmed(r) or str(r.get("arrivalDate") or "")[:10] != night or not is_same_night(r):
            continue
        lid = str(r.get("listingMapId"))
        u = units.get(lid) or {}
        at = booked_at_riyadh(r)
        p = nightly_price(r) or 0.0
        try:
            nights = int(r.get("nights") or 1)
        except (TypeError, ValueError):
            nights = 1
        fd = u.get("first_drop_at")
        from_drop = bool(fd) and at >= datetime.fromisoformat(fd)
        out.append({"lid": lid, "name": u.get("name") or r.get("listingName") or lid,
                    "booked_at": at, "price": int(round(p)), "total": int(round(p * nights)),
                    "orig": int(u.get("orig") or 0), "pct": int(step_pct(at, steps)),
                    "from_drop": from_drop})
    out.sort(key=lambda b: b["booked_at"])
    return out


def week_start(d):
    """Sunday on/before `d` (Saudi week)."""
    return d - timedelta(days=(d.weekday() + 1) % 7)


def week_count(reservations, start, end, after_hour=15):
    """Same-day bookings made at/after `after_hour` Riyadh, arrivals in [start, end] — the
    number the accounting report tracks (baseline 37/week, target 43)."""
    n = 0
    for r in reservations:
        arr = str(r.get("arrivalDate") or "")[:10]
        if not _confirmed(r) or not (start <= arr <= end) or not is_same_night(r):
            continue
        if booked_at_riyadh(r).hour >= int(after_hour):
            n += 1
    return n


_REASONS = {
    "minimum": "وقف عند الحد الأدنى",
    "pending_guest": "ضيف ينتظر تأكيد",
    "read_failed": "خطأ من هوستواي",
    "write_failed": "خطأ من هوستواي",
    "not_stuck": "هوستواي ما ثبّت السعر",
    "dry_run": "وضع التجربة — ما تغيّر شي",
}


def render_report(night, units, bookings, week, target=43, baseline=37):
    """The 12 AM Arabic report for `night` (plain text, chunked by the caller)."""
    empty = {lid: u for lid, u in units.items() if u.get("seen_empty")}
    dropped = [u for u in empty.values() if u.get("first_drop_at")]
    lines = ["🌙 **تقرير سعر الليلة — %s**" % night, "",
             "📉 فاضية الساعة ٣: %d · نزل سعرها: %d" % (len(empty), len(dropped))]

    ours = [b for b in bookings if b["from_drop"]]
    lines += ["", "✅ **انحجزت بعد النزول: %d**" % len(ours)]
    for b in ours:
        lines.append("• %s — %s — %s ر.س (كان %s) · خصم %d٪"
                     % (b["name"], b["booked_at"].strftime("%H:%M"), b["price"], b["orig"], b["pct"]))
    if ours:
        income = sum(b["total"] for b in ours)
        disc = sum(max(0, b["orig"] - b["price"]) for b in ours if b["orig"])
        lines.append("الدخل: %s ر.س · الخصم: %s ر.س" % ("{:,}".format(income), "{:,}".format(disc)))
    others = [b for b in bookings if not b["from_drop"]]
    if others:
        lines.append("(حجوزات نفس الليلة قبل النزول: %d — ما تنحسب)" % len(others))

    booked = {b["lid"] for b in bookings}
    still = [u for lid, u in empty.items() if lid not in booked]
    lines += ["", "🏠 **فاضية للحين: %d**" % len(still)]
    for u in still:
        lines.append("• %s — %s ر.س (الحد الأدنى %s)"
                     % (u.get("name"), u.get("final") or u.get("current") or "؟",
                        u.get("minimum") or "—"))

    nodrop = [u for lid, u in empty.items() if not u.get("first_drop_at") and lid not in booked]
    if nodrop:
        lines += ["", "⚠️ **ما نزل سعرها: %d**" % len(nodrop)]
        for u in nodrop:
            lines.append("• %s — %s" % (u.get("name"), _REASONS.get(u.get("reason"), u.get("reason") or "—")))

    skipped = [u.get("name") for u in units.values() if u.get("status") == "skipped"]
    if skipped:
        lines += ["", "⏸️ موقوفة (ما يلمسها الخصم): %s" % "، ".join(str(s) for s in skipped)]

    lines += ["", "📊 هالأسبوع: %d حجز بنفس اليوم بعد ٣ العصر · الهدف %d (قبل: %d)" % (week, target, baseline)]
    return "\n".join(lines)


def chunk(text, limit=1900):
    """Split on line breaks into pieces ≤ `limit` (Discord caps a message at 2,000)."""
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:                 # a single over-long line: hard cut
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:limit])
            line = line[limit:]
        cand = line if not cur else cur + "\n" + line
        if len(cand) > limit:
            parts.append(cur)
            cur = line
        else:
            cur = cand
    parts.append(cur)
    return parts
