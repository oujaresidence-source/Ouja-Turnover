# -*- coding: utf-8 -*-
"""
targets.pay — the month's payout sheet, by APARTMENT TARGET (owner-approved 2026-11-15).

THE RULE. Every apartment has a monthly revenue target, frozen for the quarter when the owner
approves it. What the apartment makes ABOVE the target, its employee gets engine.TARGET_SHARE of
Ouja's fee on. Under the target = zero, never a deduction. This replaced the commission on
10/10 reviews; the client book is now a tool to reach the target, not a second commission
(targets.money still measures what the messages add, for the owner's eyes only).

    this month's target = the quarter target x open nights / nights x the season
        open nights : a night the owner or maintenance blocked is not the employee's to sell
        the season  : if the whole company made less than its own base, every target falls by
                      the same share. It never rises — that would cancel the team's own gain.
                      Judged only after the month has ended.
    the rating      : an apartment rated under engine.RATING_MIN that month pays nothing —
                      unless the supervisor accepted the employee's note that the cause was
                      not theirs (a developer's defect, the building).
    warnings        : the ops multiplier cuts the employee's total, as before.
    the manager     : engine.MANAGER_OVERRIDE of what the team earned, ON TOP.

Nothing here writes to payroll or the ERP. An approval is one row in tg_approvals plus the
frozen sheet in tg_results: an approved month never moves again.
"""

import datetime as dt
import math

from . import db, engine, history, score
from .host import HOST

_cache = {"v": None, "sheets": {}}
RECORD_MONTHS = 6
WIN_DAYS = 10


def _now():
    return HOST.require("now")().isoformat(timespec="seconds")


def _rating(unit, month_key):
    """(average out of 5, how many reviews) for the month, or (None, 0)."""
    if unit.startswith("n:"):
        return None, 0
    r = HOST.call("unit_rating", None, unit, month_key)
    if not r or not r.get("n"):
        return None, 0
    return round(float(r["avg"]), 2), int(r["n"])


def _compute(month_key, today):
    start, end = engine.month_bounds(month_key)
    days = (end - start).days
    closed = today >= end
    quarter = score.quarter_of(month_key)
    rows = [r for r in db.targets(quarter) if r["status"] == "approved"]
    notes = {n["unit"]: n for n in db.notes(month_key)}

    pre = []
    for r in rows:
        blocked = score.blocked_count(r["unit"], month_key)
        pre.append((r, blocked, score.unit_revenue(r["unit"], month_key),
                    float(r.get("rev_base") or 0) * max(0, days - blocked) / days,
                    float(r.get("rev_target") or 0)))
    season = engine.season_factor(sum(p[2] for p in pre), sum(p[3] for p in pre)) if closed else 1.0

    units, raw, no_fee = [], {}, set()
    for r, blocked, revenue, _base, rev_target in pre:
        unit, emp = r["unit"], r["employee"] or ""
        target = engine.month_target(rev_target, days, blocked, season)
        fee_pct = HOST.call("fee_pct", None, unit, r["name"], end.isoformat())
        over, amount = engine.target_commission(revenue, target, fee_pct)
        rating, n_reviews = _rating(unit, month_key)
        note = notes.get(unit)
        waived = bool(note and note["status"] == "approved")
        blocked_by_rating = engine.rating_blocks(rating, waived)
        if over > 0 and fee_pct is None:
            no_fee.add(r["name"] or unit)
        if blocked_by_rating:
            amount = 0.0
        raw[emp] = raw.get(emp, 0.0) + amount
        units.append({"unit": unit, "name": r["name"], "employee": emp,
                      "revenue": round(revenue, 2), "target": round(target, 2),
                      "quarter_target": round(rev_target, 2), "blocked": blocked,
                      "over": round(over, 2), "raw": round(amount, 2),
                      "rating": rating, "reviews": n_reviews,
                      "rating_blocked": blocked_by_rating,
                      "note": ({"id": note["id"], "status": note["status"], "reason": note["reason"]}
                               if note else None),
                      "no_fee": fee_pct is None,
                      # riyals the employee earns per riyal above the target (admin sheet and
                      # the employee's OWN «يومي» only)
                      "rate": round((fee_pct or 0.0) * engine.TARGET_SHARE, 6)})

    # THE RACE: each employee's apartments, together, against their targets together. First
    # place takes the month's prize once the month has ended — if they earned any commission
    # at all (no prize for the best of a month where nobody passed a target, or for a place won
    # on apartments whose rating stopped them).
    pct = {}
    for emp in {u["employee"] for u in units if u["employee"]}:
        mine = [u for u in units if u["employee"] == emp and u["target"] > 0]
        t = sum(u["target"] for u in mine)
        pct[emp] = (sum(u["revenue"] for u in mine) / t) if t > 0 else 0.0
    order = sorted(pct, key=lambda e: (-pct[e], e))
    rank = {e: i + 1 for i, e in enumerate(order)}
    winners = []
    if closed and order:
        top = pct[order[0]]
        winners = [e for e in order if abs(pct[e] - top) < 1e-9 and raw.get(e, 0.0) > 0]
    each = round(engine.MONTH_PRIZE / len(winners), 2) if winners else 0.0

    employees, team, prizes = [], 0.0, 0.0
    for emp in sorted(e for e in raw if e):
        mult = float(HOST.call("ops_multiplier", 1.0, emp, month_key) or 1.0)
        commission = round(raw[emp] * mult, 2)
        prize = each if emp in winners else 0.0
        team += commission
        prizes += prize
        mine = [u for u in units if u["employee"] == emp]
        employees.append({"employee": emp, "units": len(mine),
                          "above": sum(1 for u in mine if u["over"] > 0),
                          "over": round(sum(u["over"] for u in mine), 2),
                          "raw": round(raw[emp], 2), "multiplier": round(mult, 4),
                          "commission": commission, "prize": prize,
                          "pct": round(pct.get(emp, 0.0), 4), "rank": rank.get(emp, 0),
                          "paid": round(commission + prize, 2)})
    manager = None
    mgr = db.setting("manager")
    if mgr:
        manager = {"name": mgr, "amount": round(team * engine.MANAGER_OVERRIDE, 2)}
    waiting = sum(1 for n in notes.values() if n["status"] == "pending")
    return {"month": month_key, "quarter": quarter, "approved_quarter": bool(rows),
            "season": round(season, 4), "closed": closed,
            "revenue": round(sum(u["revenue"] for u in units), 2),
            "over": round(sum(u["over"] for u in units), 2),
            "units": units, "employees": employees, "manager": manager,
            "team_paid": round(team, 2), "prize_paid": round(prizes, 2),
            "prize": {"amount": engine.MONTH_PRIZE, "winners": winners},
            "total_paid": round(team + prizes + (manager["amount"] if manager else 0.0), 2),
            "notes_waiting": waiting, "no_fee_units": sorted(no_fee),
            "ready": bool(rows) and closed and not waiting}


def month_sheet(month_key, today=None):
    """The full sheet — ADMIN ONLY. Employees get my_money(). An approved month is served
    from its frozen copy."""
    today = today or HOST.require("now")().date()
    v = db.version()
    if _cache["v"] != v:
        _cache.update(v=v, sheets={})
    ck = (month_key, today.isoformat())
    if ck in _cache["sheets"]:
        return _cache["sheets"][ck]
    approval = db.approval(month_key)
    frozen = db.result(month_key) if approval else None
    if frozen and "units" in frozen:
        sheet = dict(frozen, approval=approval, ready=False)
    else:
        sheet = dict(_compute(month_key, today), approval=approval)
    _cache["sheets"][ck] = sheet
    return sheet


def my_money(employee, month_key, today=None):
    """What ONE employee may see: their own total, and each of their apartments against its
    target. No Ouja fee, no percentage, no per-apartment amount, nobody else's number."""
    sheet = month_sheet(month_key, today)
    row = next((r for r in sheet["employees"] if r["employee"] == employee), None)
    units = [{"unit": u["unit"], "name": u["name"], "revenue": u["revenue"], "target": u["target"],
              "over": u["over"], "rating": u["rating"], "reviews": u["reviews"],
              "rating_blocked": u["rating_blocked"], "note": u["note"]}
             for u in sheet["units"] if u["employee"] == employee]
    return {"month": month_key, "amount": (row or {}).get("paid", 0.0),
            "won_prize": (row or {}).get("prize", 0.0), "units": units,
            "above": sum(1 for u in units if u["over"] > 0),
            "has_targets": sheet["approved_quarter"], "closed": sheet["closed"],
            "final": bool(sheet["approval"])}


# ------------------------------------------------------------------ «يومي»: the employee's day
# The same numbers as the sheet, turned into "what do I do now and what is it worth to me".
# OWNER DECISION 2026-11-15: an employee sees their OWN riyals per booking and per night. That
# gives away roughly what Ouja keeps; he chose it knowingly, because the page cannot say
# «+85 ريال لك» without it. Still never shown: a percentage, a colleague, the manager's cut.

def _streak(employee, today):
    """(messages today, days in a row with at least one message — today does not break it)."""
    since = (today - dt.timedelta(days=60)).isoformat()
    days = {c["at"][:10] for c in db.contacts(employee, since=since)}
    n_today = sum(1 for c in db.contacts(employee, since=today.isoformat()))
    d, run = today, 0
    if d.isoformat() not in days:
        d -= dt.timedelta(days=1)
    while d.isoformat() in days:
        run += 1
        d -= dt.timedelta(days=1)
    return n_today, run


def my_day(employee, month_key, today=None):
    today = today or HOST.require("now")().date()
    sheet = month_sheet(month_key, today)
    start, end = engine.month_bounds(month_key)
    row = next((r for r in sheet["employees"] if r["employee"] == employee), None)
    mult = float((row or {}).get("multiplier", 1.0))
    live = start <= today < end and not sheet["approval"]
    units, potential = [], 0.0
    for u in sheet["units"]:
        if u["employee"] != employee:
            continue
        rate = 0.0 if u["rating_blocked"] else float(u.get("rate") or 0.0) * mult
        typical = score.price_stats(u["unit"], start)[0]
        empties = score.empty_nights(u["unit"], max(start, today), end) if live else []
        gap = max(0.0, u["target"] - u["revenue"]) if u["target"] > 0 else 0.0
        nights_to = int(math.ceil(gap / typical)) if (gap and typical) else 0
        half = (len(empties) + 1) // 2
        reach = max(0.0, u["revenue"] + half * typical - u["target"]) * rate if u["target"] > 0 else 0.0
        mine = u["over"] * rate
        potential += max(mine, reach)
        units.append({"unit": u["unit"], "name": u["name"], "revenue": u["revenue"],
                      "target": u["target"], "over": u["over"], "mine": round(mine, 2),
                      "gap": round(gap, 2), "nights_to_target": nights_to, "empty": len(empties),
                      "next_empty": empties[0] if empties else "",
                      "night_value": round(typical * rate, 2),
                      "reachable": bool(u["target"] > 0 and rate > 0 and empties
                                        and (u["over"] > 0 or nights_to <= len(empties)))})
    # «أقرب فلوس»: units already above their target first (every extra night pays today),
    # then the ones the fewest nights away.
    hot = sorted((u for u in units if u["reachable"]),
                 key=lambda u: (0, -u["night_value"]) if u["over"] > 0 else (1, u["nights_to_target"]))
    wins = _wins(employee, sheet, month_key, today, mult) if live else []
    n_today, run = _streak(employee, today) if live else (0, 0)
    record = my_record(employee, month_key, today)
    # The race, as an employee may see it: names, place and how far each is against their own
    # targets. Never anybody's riyals. (Owner decision 2026-11-15: «ابيهم يتذابحون».)
    rows = sorted(sheet["employees"], key=lambda r: r.get("rank") or 99)
    me = next((r for r in rows if r["employee"] == employee), None)
    lead = rows[0] if rows else None
    my_target = sum(u["target"] for u in sheet["units"] if u["employee"] == employee)
    race = {"prize": (sheet.get("prize") or {}).get("amount", 0.0),
            "place": (me or {}).get("rank", 0), "of": len(rows),
            "to_first": round(max(0.0, ((lead or {}).get("pct", 0) - (me or {}).get("pct", 0)) * my_target), 0)
            if me and lead and lead is not me else 0.0,
            "won": employee in ((sheet.get("prize") or {}).get("winners") or []),
            "board": [{"employee": r["employee"], "place": r.get("rank", 0), "pct": r.get("pct", 0.0),
                       "me": r["employee"] == employee} for r in rows]}
    return {"live": live, "amount": (row or {}).get("paid", 0.0),
            "potential": round(max(potential, (row or {}).get("paid", 0.0)), 2),
            "nearest": [u["unit"] for u in hot[:3]], "units": units,
            "mission": {"today": n_today, "streak": run},
            "race": race, "wins": wins, "record": record}


def _wins(employee, sheet, month_key, today, mult):
    """Bookings that landed on my apartments in the last days, and what each added to MY month.
    Bookings are taken in the order they were made: the one that crosses the target earns only
    on its part above it, so the amounts add up to exactly what the apartment pays."""
    mine = {u["unit"]: u for u in sheet["units"] if u["employee"] == employee}
    if not mine:
        return []
    start, end = engine.month_bounds(month_key)
    since = (today - dt.timedelta(days=WIN_DAYS)).isoformat()
    marks = ",".join("?" * len(mine))
    rows = db.q("SELECT unit, guest_name, arrival, departure, total, created, status FROM tg_res "
                "WHERE unit IN (%s) AND arrival<? AND departure>? AND status IN ('new','modified') "
                "ORDER BY created, arrival" % marks,
                tuple(mine) + (end.isoformat(), start.isoformat()))
    so_far, out = {}, []
    for r in rows:
        u = mine[r["unit"]]
        part = engine.revenue_in_month([r], month_key)
        before = so_far.get(r["unit"], 0.0)
        so_far[r["unit"]] = before + part
        if part <= 0 or str(r["created"] or "")[:10] < since:
            continue
        rate = 0.0 if u["rating_blocked"] else float(u.get("rate") or 0.0) * mult
        gain = 0.0
        if u["target"] > 0:
            gain = (max(0.0, before + part - u["target"]) - max(0.0, before - u["target"])) * rate
        nights = (dt.date.fromisoformat(r["departure"]) - dt.date.fromisoformat(r["arrival"])).days
        out.append({"unit_name": u["name"], "guest": (str(r["guest_name"] or "").split() or ["ضيف"])[0],
                    "nights": nights, "created": str(r["created"])[:10], "mine": round(gain, 2)})
    out.sort(key=lambda w: w["created"], reverse=True)
    return out[:5]


def my_record(employee, month_key, today):
    """My last months: what I earned in each. An approved month reads its frozen sheet."""
    out = []
    for mk in history.month_keys(history.shift_month(month_key, -(RECORD_MONTHS - 1)), RECORD_MONTHS):
        if mk > score.month_of(today):
            continue
        sh = month_sheet(mk, today)
        row = next((r for r in sh["employees"] if r["employee"] == employee), None)
        if not row and not sh["approved_quarter"]:
            continue
        out.append({"month": mk, "amount": (row or {}).get("paid", 0.0), "final": bool(sh["approval"])})
    best = max(out, key=lambda x: x["amount"]) if out else None
    return {"months": out, "earned": round(sum(x["amount"] for x in out), 2),
            "best": best if best and best["amount"] > 0 else None}


def team_activity(month_key, today=None):
    """For the operations manager: counts only — no money."""
    sheet = month_sheet(month_key, today)
    start, end = engine.month_bounds(month_key)
    contacts = {}
    for c in db.contacts(since=start.isoformat(), until=end.isoformat()):
        contacts[c["employee"]] = contacts.get(c["employee"], 0) + 1
    return [{"employee": r["employee"], "contacts": contacts.get(r["employee"], 0),
             "above": r["above"], "units": r["units"]} for r in sheet["employees"]]


def team_notes(month_key, today=None):
    """Rating notes of the month for the supervisor: who, which apartment, why, the rating."""
    sheet = month_sheet(month_key, today)
    by_unit = {u["unit"]: u for u in sheet["units"]}
    out = []
    for n in db.notes(month_key):
        u = by_unit.get(n["unit"], {})
        out.append({"id": n["id"], "unit_name": u.get("name") or n["unit"], "employee": n["employee"],
                    "reason": n["reason"], "status": n["status"], "rating": u.get("rating"),
                    "reviews": u.get("reviews", 0), "decided_by": n.get("decided_by") or ""})
    return out


def raise_note(employee, unit, month_key, reason, today=None):
    """The apartment's own employee says the low rating was not theirs to prevent.
    Returns (ok, error, note id)."""
    reason = " ".join(str(reason or "").split())[:400]
    if len(reason) < 3:
        return False, "اكتب السبب.", None
    sheet = month_sheet(month_key, today)
    if sheet["approval"]:
        return False, "الشهر معتمد وما يتغير.", None
    line = next((u for u in sheet["units"] if u["unit"] == str(unit)), None)
    if not line or line["employee"] != employee:
        return False, "هالشقة مو من شققك.", None
    if line["rating"] is None or line["rating"] >= engine.RATING_MIN:
        return False, "تقييم الشقة هالشهر ما هو نازل، ما تحتاج ملاحظة.", None
    nid = db.add_note(str(unit), month_key, employee, reason, _now())
    if not nid:
        return False, "فيه ملاحظة مرفوعة لهالشقة هالشهر.", None
    db.log("note_raise", _now(), employee, {"unit": str(unit), "month": month_key})
    return True, "", nid


def decide_note(note_id, accept, by):
    """The supervisor's decision — once. Returns (ok, error)."""
    try:
        note_id = int(note_id)
    except (TypeError, ValueError):
        return False, "ملاحظة غير موجودة."
    note = next((n for n in db.notes() if n["id"] == note_id), None)
    if not note:
        return False, "ملاحظة غير موجودة."
    if db.approval(note["month_key"]):
        return False, "الشهر معتمد وما يتغير."
    if not db.decide_note(note_id, "approved" if accept else "rejected", by, _now()):
        return False, "الملاحظة انبتّ فيها من قبل."
    db.log("note_decide", _now(), by, {"id": note_id, "accept": bool(accept)})
    return True, ""


def approve_month(month_key, by):
    """Owner approves a month: one row and the frozen sheet, nothing else."""
    sheet = month_sheet(month_key)
    if sheet["approval"]:
        return False, "هالشهر معتمد من قبل."
    if not sheet["approved_quarter"]:
        return False, "أهداف الربع ما اعتمدت، فما فيه شي ينصرف."
    if not sheet["closed"]:
        return False, "الشهر ما خلص."
    if sheet["notes_waiting"]:
        return False, "باقي %d ملاحظة تقييم ما انبتّ فيها." % sheet["notes_waiting"]
    now = _now()
    snap = {k: v for k, v in sheet.items() if k != "approval"}
    if not db.approve_month(month_key, by, now, sheet["total_paid"], snap):
        return False, "هالشهر معتمد من قبل."
    db.save_result(month_key, snap, now)
    db.log("approve_month", now, by, {"month": month_key, "total_paid": sheet["total_paid"]})
    return True, ""
