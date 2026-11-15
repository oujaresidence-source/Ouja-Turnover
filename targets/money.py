# -*- coding: utf-8 -*-
"""
targets.money — the month's payout sheet.

THE RULE: Ouja pays only from money that would not have come without the employee.
A month here is a COHORT: the contacts logged in that month and the bookings they earned.

  raw commission = engine.booking_commission on each attributed booking, AFTER the guest has
                   checked out, with the unit's real contract fee (no fee on record -> 0).
  the cap        = 50% x (bookings the calls ADDED) x (average Ouja fee per booking).

LIKE WITH LIKE (owner-approved 2026-11-15). The hidden group is a random 20% of all callable
guests, but a team can choose to log contacts only with guests who rebook anyway: repeat
guests return at more than twice the average rate, and the call list ranks them first. On the
real history that "picky lazy team" drew 2,659 SAR through a single-rate cap. So the expected
natural bookings are computed per bucket of past stays (1, 2, 3+): each contacted guest is
compared with hidden guests of the same bucket, the buckets are summed, and ONE clamp is
applied to the total. engine.uplift_pool still does the capping arithmetic.

A hidden guest has no contact date, so each gets a pretend one drawn (deterministically) from
the team's real contact dates that month: both groups are measured over the same 14 days.

Nothing here writes to payroll or the ERP. An approval is one row in tg_approvals.
"""

import datetime as dt
import hashlib

from . import book, db, engine, history, score
from . import host as _host
from .host import HOST

BUCKETS = (1, 2, 3)
POOL_MIN_FOR_OWN_RATE = 200
_rates_cache = {}
_sheet_cache = {}


def _booked_within(g, day_iso, days=engine.ATTRIBUTION_DAYS):
    end = (dt.date.fromisoformat(day_iso) + dt.timedelta(days=days)).isoformat()
    return any(day_iso <= s["created"] <= end for s in g["stays"])


def natural_rates(month_key):
    """{bucket: rate or None}: how often a callable guest of that bucket booked within 14 days
    with NO call, over the 12 months before `month_key`. The higher of the whole guest base
    and (when large enough) the callable pool — the conservative side for Ouja."""
    ck = (db.version(), month_key, _host.pool_channels())
    if ck in _rates_cache:
        return _rates_cache[ck]
    consents = db.consents()
    channels = _host.pool_channels()
    n_all = {b: 0 for b in BUCKETS}
    h_all = dict(n_all)
    n_pool = dict(n_all)
    h_pool = dict(n_all)
    for mk in history.month_keys(history.shift_month(month_key, -12), 12):
        day1 = engine.month_bounds(mk)[0]
        for g in book.guests().values():
            ok, _why, past = book.as_callable(dict(g, channels={"direct"}), day1, set(), set(), {},
                                              ("direct",))
            if not ok:
                continue
            b = book.bucket_of(len(past))
            hit = 1 if _booked_within(g, day1.isoformat()) else 0
            n_all[b] += 1
            h_all[b] += hit
            if book.consent_ok(g, consents, channels):
                n_pool[b] += 1
                h_pool[b] += hit
    out = {}
    for b in BUCKETS:
        r = (h_all[b] / n_all[b]) if n_all[b] else None
        if n_pool[b] >= POOL_MIN_FOR_OWN_RATE:
            r = max(r or 0.0, h_pool[b] / n_pool[b])
        out[b] = r
    _rates_cache.clear()
    _rates_cache[ck] = out
    return out


def _pretend_date(key, month_key, dates):
    h = hashlib.sha256((month_key + ":" + key).encode("utf-8")).hexdigest()
    return dates[int(h[:8], 16) % len(dates)]


def measure(month_key, contacts, hit_contact_ids):
    """Contacted vs hidden group, bucket by bucket. Returns the numbers behind the cap."""
    quarter = score.quarter_of(month_key)
    c_n = {b: 0 for b in BUCKETS}
    c_hit = dict(c_n)
    for c in contacts:
        b = book.bucket_of(c["bucket"] or 1)
        c_n[b] += 1
        c_hit[b] += 1 if c["id"] in hit_contact_ids else 0
    h_n = {b: 0 for b in BUCKETS}
    h_hit = dict(h_n)
    dates = sorted(c["at"][:10] for c in contacts)
    if dates:
        consents, dnc, channels = db.consents(), db.dnc(), _host.pool_channels()
        for g in book.guests().values():
            if not book.is_holdout(g["key"], quarter):
                continue
            d = _pretend_date(g["key"], month_key, dates)
            ok, _why, past = book.as_callable(g, dt.date.fromisoformat(d), consents, dnc, {}, channels)
            if not ok:
                continue
            b = book.bucket_of(len(past))
            h_n[b] += 1
            h_hit[b] += 1 if _booked_within(g, d) else 0
    fallback = natural_rates(month_key)
    buckets, expected = [], 0.0
    for b in BUCKETS:
        measured = (h_hit[b] / h_n[b]) if h_n[b] else None
        if measured is None or h_hit[b] < engine.MIN_HOLDOUT_EVENTS:
            fb = fallback.get(b)
            rate = 1.0 if fb is None else max(fb, measured or 0.0)   # no evidence -> no uplift
            source = "history" if fb is not None else "none"
        else:
            rate, source = measured, "holdout"
        expected += c_n[b] * rate
        buckets.append({"bucket": b, "contacted": c_n[b], "contacted_bookings": c_hit[b],
                        "holdout": h_n[b], "holdout_bookings": h_hit[b],
                        "rate": round(rate, 5), "rate_source": source})
    return {"buckets": buckets, "contacted": sum(c_n.values()),
            "contacted_bookings": sum(c_hit.values()), "holdout": sum(h_n.values()),
            "holdout_bookings": sum(h_hit.values()), "expected_natural": expected}


def _bounds_for(unit, arrival):
    t = db.target(score.quarter_of(arrival), unit)
    if t and t["status"] == "approved":
        return float(t["floor"] or 0), float(t["ceiling"] or 0)
    lid = None if unit.startswith("n:") else unit
    return float(HOST.call("floor", 0, lid) or 0), 0.0


def month_sheet(month_key, today=None):
    """The full sheet for one cohort month — ADMIN ONLY. Employees get my_money()."""
    today = today or HOST.require("now")().date()
    ck = (db.version(), month_key, today.isoformat(), _host.pool_channels())
    if ck in _sheet_cache:
        return _sheet_cache[ck]
    start, end = engine.month_bounds(month_key)
    contacts = db.contacts(since=start.isoformat(), until=end.isoformat())
    by_id = {c["id"]: c for c in contacts}
    attr = [a for a in db.attrs() if a["contact_id"] in by_id]
    res = {r["res_id"]: r for r in db.res_by_ids([a["res_id"] for a in attr])}
    names = history.unit_names()
    today_iso = today.isoformat()

    people = sorted({c["employee"] for c in contacts})
    gates = {e: score.gate(e, month_key, today) for e in people}
    shares = {e: engine.employee_share(*gates[e]) for e in people}

    lines, raw, fees, no_fee, hit_ids = [], {e: 0.0 for e in people}, [], set(), set()
    for a in attr:
        r = res.get(a["res_id"])
        c = by_id[a["contact_id"]]
        if not r or r["status"] not in engine.CONFIRMED:
            continue
        hit_ids.add(c["id"])
        nights = (dt.date.fromisoformat(r["departure"]) - dt.date.fromisoformat(r["arrival"])).days
        lid = None if r["unit"].startswith("n:") else r["unit"]
        fee_pct = HOST.call("fee_pct", None, lid, r["listing_name"], r["departure"]) if lid else None
        state = "completed" if r["departure"] <= today_iso else "pending"
        commission = 0.0
        if fee_pct is None:
            no_fee.add(names.get(r["unit"]) or r["listing_name"] or r["unit"])
        else:
            fees.append(float(r["total"] or 0) * fee_pct)
            if state == "completed":
                floor, ceiling = _bounds_for(r["unit"], r["arrival"])
                commission = engine.booking_commission(r, shares[c["employee"]], fee_pct, floor, ceiling)
                raw[c["employee"]] += commission
        lines.append({"employee": c["employee"], "guest": book.first_name(r["guest_name"]),
                      "unit_name": names.get(r["unit"]) or r["listing_name"], "nights": nights,
                      "state": state, "departure": r["departure"], "res_id": r["res_id"],
                      "raw": commission, "no_fee": fee_pct is None})

    m = measure(month_key, contacts, hit_ids)
    avg_fee = (sum(fees) / len(fees)) if fees else 0.0
    n = m["contacted"]
    cap = engine.uplift_pool(n, m["contacted_bookings"], 0, 0, avg_fee,
                             fallback_rate=(m["expected_natural"] / n) if n else None)
    mults = {e: float(HOST.call("ops_multiplier", 1.0, e, month_key) or 1.0) for e in people}
    mgr_name = db.setting("manager")
    manager = None
    if mgr_name:
        scored = [gates[e] for e in people if gates[e][1] > 0]
        manager = {"name": mgr_name,
                   "all_passed_gate": bool(scored) and all(h / s >= engine.GATE_FULL for h, s in scored)}
    st = engine.settle(raw, cap["pool"], manager, mults)

    pending = sum(1 for ln in lines if ln["state"] == "pending")
    window_closed = today > end + dt.timedelta(days=engine.ATTRIBUTION_DAYS)
    emp_rows = []
    for e in people:
        mine = [ln for ln in lines if ln["employee"] == e]
        emp_rows.append({"employee": e, "contacts": sum(1 for c in contacts if c["employee"] == e),
                         "bookings": len(mine),
                         "completed": sum(1 for ln in mine if ln["state"] == "completed"),
                         "pending": sum(1 for ln in mine if ln["state"] == "pending"),
                         "hit": gates[e][0], "scored": gates[e][1], "share": round(shares[e], 4),
                         "raw": round(raw[e], 2), "multiplier": round(mults[e], 4),
                         "paid": st["employees"].get(e, 0.0)})
    sheet = {"month": month_key, "measure": m,
             "avg_fee": round(avg_fee, 2), "incremental": round(cap["incremental_bookings"], 2),
             "uplift_fee": round(cap["uplift_fee"], 2), "pool": cap["pool"],
             "raw_total": st["raw_total"], "total_paid": st["total_paid"],
             "scale": round(st["scale"], 4), "employees": emp_rows,
             "manager": st.get("manager"), "lines": lines, "pending": pending,
             "window_closed": window_closed, "ready": window_closed and pending == 0,
             "no_fee_units": sorted(no_fee), "approval": db.approval(month_key)}
    _sheet_cache.clear()
    _sheet_cache[ck] = sheet
    return sheet


def my_money(employee, month_key, today=None):
    """What ONE employee may see: their own amount and which of their bookings counted.
    No Ouja fee, no contract percentage, no pool, no hidden-group figure, no colleague —
    and no per-booking amount, because amount / share would reveal the fee."""
    sheet = month_sheet(month_key, today)
    row = next((r for r in sheet["employees"] if r["employee"] == employee), None)
    mine = [{"guest": ln["guest"], "unit_name": ln["unit_name"], "nights": ln["nights"],
             "state": ln["state"]} for ln in sheet["lines"] if ln["employee"] == employee]
    return {"month": month_key,
            "amount": (row or {}).get("paid", 0.0), "contacts": (row or {}).get("contacts", 0),
            "bookings": mine, "pending": sum(1 for b in mine if b["state"] == "pending"),
            "final": bool(sheet["approval"])}


def team_activity(month_key, today=None):
    """For the operations manager: counts and gate only — no money, no pool, no hidden group."""
    sheet = month_sheet(month_key, today)
    return [{k: r[k] for k in ("employee", "contacts", "bookings", "hit", "scored")}
            for r in sheet["employees"]]


def approve_month(month_key, by):
    """Owner approves a month: one row, nothing else. Refused before the
    14-day window has closed, and while a counted guest has not checked out yet."""
    sheet = month_sheet(month_key)
    if not sheet["window_closed"]:
        return False, "الشهر ما قفل: لازم يمر 14 يوم بعد نهايته."
    if sheet["pending"]:
        return False, "باقي %d حجز ما خرج ضيفه. العمولة تنحسب بعد الخروج." % sheet["pending"]
    now = HOST.require("now")().isoformat(timespec="seconds")
    snap = {k: v for k, v in sheet.items() if k != "approval"}
    if not db.approve_month(month_key, by, now, sheet["total_paid"], snap):
        return False, "هالشهر معتمد من قبل."
    db.save_result(month_key, snap, now)
    db.log("approve_month", now, by, {"month": month_key, "total_paid": sheet["total_paid"]})
    return True, ""
