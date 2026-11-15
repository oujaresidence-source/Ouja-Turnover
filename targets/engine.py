# -*- coding: utf-8 -*-
"""
targets.engine — PURE rules for «الأهداف والعمولة». No DB, no clock, no network.

THE MONEY PRINCIPLE THIS FILE EXISTS TO PROTECT
    Ouja pays only out of money that would not have come without the employee.
    A 14-month backtest on real bookings (docs: backtest in the design spec) showed that
    occupancy-vs-own-baseline pays ~25,000 SAR for pure chance, even at portfolio level
    (chance swing: 9-10 occupancy points). So occupancy NEVER pays cash here. Cash comes from
    bookings that follow a logged guest contact, and the whole payout is capped by the uplift
    measured against a HOLDOUT group the team never sees. No uplift -> pool is zero.

Occupancy targets still exist: they are the scoreboard, they steer the call list, and they
move the employee's share between SHARE_BASE and SHARE_MAX. They cannot create cash alone.

Every function takes plain dicts/lists and returns plain values, so tests need no fixtures.
"""

import calendar
import datetime as _dt
import hashlib

# ---------------------------------------------------------------- tunables (owner-approved)
TIER_STEPS = (("bronze", 0.05), ("silver", 0.08), ("gold", 0.12))   # points above baseline
BRONZE_FLOOR, GOLD_CEIL = 0.60, 0.92
MIN_AVAILABLE_NIGHTS = 15          # a unit open fewer nights is left out, never scored zero
HALF_WEIGHT = 0.5                  # night priced between the floor and the unit's typical price

GATE_ZERO, GATE_FULL = 0.40, 0.60  # share of the employee's units at bronze or better
SHARE_BASE, SHARE_MAX = 0.30, 0.40 # employee's share of Ouja's fee on an attributed booking
CEILING_MULT = 2.0                 # share multiplier on the part of a night above the ceiling

LAPSED_DAYS = 45                   # a guest becomes callable this long after checkout
CONTACT_COOLDOWN_DAYS = 45         # one logged contact per guest per this many days
ATTRIBUTION_DAYS = 14              # booking must be CREATED within this window after contact
HOLDOUT_PCT = 20                   # percent of callable guests hidden from every call list

POOL_SHARE_OF_UPLIFT = 0.50        # hard cap: total payout <= this share of measured uplift fee
MIN_HOLDOUT_EVENTS = 20            # below this the holdout rate is too noisy; use the fallback
MANAGER_OVERRIDE, MANAGER_OVERRIDE_FULL = 0.15, 0.20

CONFIRMED = ("new", "modified")


# ---------------------------------------------------------------- dates
def _d(x):
    if isinstance(x, _dt.datetime):
        return x.date()
    if isinstance(x, _dt.date):
        return x
    return _dt.date.fromisoformat(str(x)[:10])


def month_bounds(month_key):
    """'2026-11' -> (first day, first day of next month)."""
    y, m = int(month_key[:4]), int(month_key[5:7])
    start = _dt.date(y, m, 1)
    return start, start + _dt.timedelta(days=calendar.monthrange(y, m)[1])


def nights_in_month(arrival, departure, month_key):
    """Nights of a stay that fall inside the month (a night belongs to its check-in date)."""
    a, b = _d(arrival), _d(departure)
    s, e = month_bounds(month_key)
    return max(0, (min(b, e) - max(a, s)).days)


# ---------------------------------------------------------------- occupancy (scoreboard only)
def night_weight(price, floor, typical):
    """0 below the floor, half up to the unit's typical price, full at or above it.
    `floor` or `typical` of 0/None means "not set": the night counts in full."""
    if floor and price < floor:
        return 0.0
    if typical and price < typical:
        return HALF_WEIGHT
    return 1.0


def unit_month(reservations, blocked_nights, month_key, floor=0, typical=0):
    """Scoreboard for one unit and one month.

    reservations: [{arrival, departure, total, status}] for this unit (any dates).
    blocked_nights: owner/maintenance nights inside the month.
    Returns None when the unit was open fewer than MIN_AVAILABLE_NIGHTS (left out, not zero).
    """
    s, e = month_bounds(month_key)
    available = (e - s).days - int(blocked_nights or 0)
    if available < MIN_AVAILABLE_NIGHTS:
        return None
    raw = weighted = below = 0.0
    for r in reservations:
        if r.get("status") not in CONFIRMED:
            continue
        stay = (_d(r["departure"]) - _d(r["arrival"])).days
        n = nights_in_month(r["arrival"], r["departure"], month_key)
        if stay <= 0 or n <= 0:
            continue
        w = night_weight(float(r.get("total") or 0) / stay, floor, typical)
        raw += n
        weighted += n * w
        if w == 0:
            below += n
    return {"available": available, "nights": raw, "weighted": weighted, "below_floor": below,
            "occupancy": weighted / available}


def baseline(same_quarter_last_year, trailing):
    """Occupancy baseline for a unit. Each argument is a list of monthly occupancies (None =
    missing). Last year's same quarter and the trailing months weigh 50/50; with no last year
    the trailing months stand alone; with neither, None (the caller uses the peer average)."""
    a = [x for x in (same_quarter_last_year or []) if x is not None]
    b = [x for x in (trailing or []) if x is not None]
    if a and b:
        return 0.5 * sum(a) / len(a) + 0.5 * sum(b) / len(b)
    if b:
        return sum(b) / len(b)
    if a:
        return sum(a) / len(a)
    return None


def tiers(base):
    """{bronze, silver, gold} occupancy targets, monotone and inside the allowed band."""
    out, prev = {}, 0.0
    for name, step in TIER_STEPS:
        t = base + step
        if name == "bronze":
            t = max(t, BRONZE_FLOOR)
        t = min(max(t, prev), GOLD_CEIL)
        out[name] = prev = t
    return out


def tier_reached(occupancy, targets):
    best = None
    for name, _ in TIER_STEPS:
        if occupancy >= targets[name]:
            best = name
    return best


def gate_factor(units_hit, units_scored):
    """0 below GATE_ZERO, 1 at GATE_FULL and above, straight line between. No cliff."""
    if units_scored <= 0:
        return 0.0
    share = units_hit / units_scored
    if share >= GATE_FULL:
        return 1.0
    if share <= GATE_ZERO:
        return 0.0
    return (share - GATE_ZERO) / (GATE_FULL - GATE_ZERO)


def employee_share(units_hit, units_scored):
    """Share of Ouja's fee the employee earns on attributed bookings this month."""
    return SHARE_BASE + (SHARE_MAX - SHARE_BASE) * gate_factor(units_hit, units_scored)


# ---------------------------------------------------------------- client book
def phone_key(phone):
    """Last 9 digits: one key for 05xxxxxxxx, +9665xxxxxxxx and 9665xxxxxxxx."""
    digits = "".join(c for c in str(phone or "") if c.isdigit())
    return digits[-9:] if len(digits) >= 9 else ""


def in_holdout(phone, salt):
    """Stable, unguessable split. The same guest stays on the same side for a whole `salt`
    (the quarter key), so nobody can re-roll a guest into the call list."""
    key = phone_key(phone)
    if not key:
        return False
    h = hashlib.sha256((str(salt) + ":" + key).encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100 < HOLDOUT_PCT


def callable_guest(guest, today):
    """guest: {phone, last_checkout, has_future_booking, do_not_contact, consent, last_contact}.
    Returns (ok, reason). Consent is required: no consent, no call."""
    today = _d(today)
    if not phone_key(guest.get("phone")):
        return False, "no_phone"
    if guest.get("do_not_contact"):
        return False, "do_not_contact"
    if not guest.get("consent"):
        return False, "no_consent"
    if guest.get("has_future_booking"):
        return False, "already_booked"
    if not guest.get("last_checkout") or (today - _d(guest["last_checkout"])).days < LAPSED_DAYS:
        return False, "too_recent"
    if guest.get("last_contact") and (today - _d(guest["last_contact"])).days < CONTACT_COOLDOWN_DAYS:
        return False, "cooldown"
    return True, ""


def attribute(contacts, bookings):
    """Match bookings to the logged contact that earned them.

    contacts: [{id, employee, phone, at}]   bookings: [{id, phone, created, ...}]
    A booking belongs to the EARLIEST contact of that phone whose window covers the booking's
    creation date (first logger wins; a later colleague cannot take it). One booking, one
    contact. Returns {booking_id: contact}.
    """
    by_phone = {}
    for c in sorted(contacts, key=lambda c: (_d(c["at"]), str(c.get("id")))):
        by_phone.setdefault(phone_key(c["phone"]), []).append(c)
    out = {}
    for b in bookings:
        made = _d(b["created"])
        for c in by_phone.get(phone_key(b.get("phone")), []):
            gap = (made - _d(c["at"])).days
            if 0 <= gap <= ATTRIBUTION_DAYS:
                out[b["id"]] = c
                break
    return out


def booking_commission(booking, share, fee_pct, floor=0, ceiling=0):
    """Employee's commission on one attributed, COMPLETED booking.

    Pays `share` of Ouja's fee. A booking under the unit's floor pays nothing. The part of the
    nightly price above the ceiling pays CEILING_MULT x share. Never more than Ouja's fee.
    """
    if booking.get("status") not in CONFIRMED:
        return 0.0
    nights = (_d(booking["departure"]) - _d(booking["arrival"])).days
    if nights <= 0:
        return 0.0
    ppn = float(booking.get("total") or 0) / nights
    if floor and ppn < floor:
        return 0.0
    normal = min(ppn, ceiling) if ceiling else ppn
    above = max(0.0, ppn - ceiling) if ceiling else 0.0
    fee_night = fee_pct * ppn
    pay_night = fee_pct * (normal * share + above * share * CEILING_MULT)
    return round(nights * min(pay_night, fee_night), 2)


# ---------------------------------------------------------------- the safety valve
def uplift_pool(contacted, contacted_bookings, holdout, holdout_bookings, avg_fee,
                fallback_rate=None):
    """Hard cap on the month's total payout, from the measured uplift.

    contacted / holdout: guests in each group over the measuring window.
    *_bookings: how many of them booked inside the attribution window.
    The holdout shows what happens with no call. Uplift = bookings the calls ADDED. With too
    few holdout events the measured rate is noise, so the historical `fallback_rate` is used
    when it is HIGHER (the conservative side for Ouja). Thin holdout and no history: pool is 0.
    Returns {natural_rate, expected_natural, incremental_bookings, uplift_fee, pool}.
    """
    measured = (holdout_bookings / holdout) if holdout else None
    rate = measured
    if measured is None or holdout_bookings < MIN_HOLDOUT_EVENTS:
        # thin holdout AND no history to lean on -> no evidence -> assume no uplift
        rate = 1.0 if fallback_rate is None else max(fallback_rate, measured or 0.0)
    expected = contacted * rate
    incremental = max(0.0, contacted_bookings - expected)
    uplift_fee = incremental * float(avg_fee or 0)
    return {"natural_rate": rate, "expected_natural": expected,
            "incremental_bookings": incremental, "uplift_fee": uplift_fee,
            "pool": round(POOL_SHARE_OF_UPLIFT * uplift_fee, 2)}


def settle(employee_commissions, pool, manager=None, ops_multipliers=None):
    """Turn raw commissions into the month's payout sheet.

    employee_commissions: {employee: raw SAR}.  pool: cap from uplift_pool().
    manager: {"name": str, "all_passed_gate": bool} or None.
    ops_multipliers: {employee: multiplier from ops warnings x scorecard}; applied BEFORE the
    cap so a bonus multiplier can never push the total past the pool.
    The manager's override comes out of the same pool. If the total exceeds the pool, everyone
    is scaled by the same factor. Total paid never exceeds the pool.
    """
    ops_multipliers = ops_multipliers or {}
    lines = {e: max(0.0, float(v)) * float(ops_multipliers.get(e, 1.0))
             for e, v in employee_commissions.items()}
    team = sum(lines.values())
    override = 0.0
    if manager:
        rate = MANAGER_OVERRIDE_FULL if manager.get("all_passed_gate") else MANAGER_OVERRIDE
        override = team * rate
    total = team + override
    scale = 1.0 if total <= pool or total == 0 else max(0.0, pool) / total
    paid = {e: round(v * scale, 2) for e, v in lines.items()}
    out = {"employees": paid, "scale": scale, "pool": pool, "raw_total": round(total, 2)}
    if manager:
        out["manager"] = {"name": manager["name"], "amount": round(override * scale, 2)}
    out["total_paid"] = round(sum(paid.values()) + (out.get("manager", {}).get("amount", 0.0)), 2)
    return out


# ====================================================================== the apartment target
# OWNER-APPROVED 2026-11-15 — this is what PAYS. It replaced the commission on 10/10 reviews.
#
#   Every apartment has a monthly revenue target: its own average month before the quarter,
#   plus TARGET_STEP. Whatever it makes ABOVE the target, the employee gets TARGET_SHARE of
#   Ouja's fee on that part. At or under the target the apartment pays nothing; it never costs
#   the employee anything.
#
#   A HIGHER BAR, A BIGGER SLICE (owner decision, 2026-11-15 evening). At +20% / 20% an extra
#   night was worth ~26 SAR to the employee and one WhatsApp message one or two riyals: nobody
#   runs for that. So the target is the unit's own average + 30% and the employee keeps 30% of
#   Ouja's fee above it (about 6 riyals in every 100), plus a monthly prize for whoever is first.
#   Measured on Apr-Oct 2026 with the rule exactly as built
#   (outputs/targets-audit-2026-11-15/scripts/a13.py): a team that changes nothing draws ~2,310
#   in commission, ~2,660 with the manager, +500 prize = ~3,160 a month against the 1,887 the
#   review commission cost. That gap is repaid once revenue grows ~1.7%; every riyal of growth
#   after it leaves Ouja ~65% of its fee. Re-measure before changing any of these.
TARGET_BASE_MONTHS = 3
TARGET_STEP = 0.30
TARGET_SHARE = 0.30
LEGACY_STEPS = (0.20,)       # earlier automatic steps: a stored target equal to one is not "typed by the owner"
MONTH_PRIZE = 500.0          # SAR, to the employee whose apartments did best against their targets
# THE OPERATIONS MANAGER (owner decision 2026-11-15 night). She sells no apartment; she moves
# the team. At 15% of the team's commission her month was ~350 SAR while the team's offer had
# been raised twice, so: 25% of the team's commission, on top, plus a team bonus of her own on
# HOW MANY apartments passed their target that month. On Apr-Oct 2026 the share was
# 31/23/27/40/21/18/20% — 30% reached twice in seven months, 40% once: it has to be worked for.
TARGET_MANAGER_SHARE = 0.25
MANAGER_TEAM_BONUS = ((0.40, 700.0), (0.30, 300.0))   # (share of apartments above target, SAR), best first


def manager_bonus(above, units):
    """(bonus in SAR, share of apartments above target)."""
    rate = (float(above) / units) if units else 0.0
    for need, sar in MANAGER_TEAM_BONUS:
        if rate >= need - 1e-9:
            return sar, rate
    return 0.0, rate
RATING_MIN = 4.75            # out of 5: under it, the apartment pays nothing that month


def revenue_in_month(reservations, month_key):
    """Revenue of the confirmed stays that falls inside the month, night by night."""
    start, end = month_bounds(month_key)
    total = 0.0
    for r in reservations or ():
        if r.get("status") not in CONFIRMED:
            continue
        a, b = _d(r.get("arrival")), _d(r.get("departure"))
        nights = (b - a).days
        if nights <= 0:
            continue
        inside = (min(b, end) - max(a, start)).days
        if inside > 0:
            total += float(r.get("total") or 0) * inside / nights
    return total


def season_factor(revenue_total, base_total):
    """How the whole company moved against its own base — DOWNWARD ONLY. A slow month lowers
    every target; a strong month never raises one (it would cancel the team's own gain)."""
    if not base_total or base_total <= 0:
        return 1.0
    return max(0.0, min(1.0, float(revenue_total) / float(base_total)))


def month_target(rev_target, days, blocked=0, season=1.0):
    """The quarter's monthly target, for THIS month: a night the owner or maintenance blocked
    is not the employee's to sell, and a slow season lowers it."""
    if not rev_target or rev_target <= 0 or days <= 0:
        return 0.0
    open_share = max(0, days - max(0, blocked)) / float(days)
    return float(rev_target) * open_share * max(0.0, min(1.0, season))


def rating_blocks(rating, waived=False):
    """True when the month's guest rating stops the apartment from paying. No rating that
    month = nothing to judge. `waived` = the supervisor accepted that the cause was not the
    employee's (a developer's defect, the building)."""
    return rating is not None and float(rating) < RATING_MIN and not waived


def target_commission(revenue, target, fee_pct, share=TARGET_SHARE):
    """(riyals above the target, the employee's commission on them)."""
    if not target or target <= 0:
        return 0.0, 0.0
    over = max(0.0, float(revenue) - float(target))
    if fee_pct is None or fee_pct <= 0:
        return over, 0.0
    return over, over * float(fee_pct) * float(share)
