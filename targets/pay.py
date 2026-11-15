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

from . import db, engine, score
from .host import HOST

_cache = {}


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
                      "no_fee": fee_pct is None})

    employees, team = [], 0.0
    for emp in sorted(e for e in raw if e):
        mult = float(HOST.call("ops_multiplier", 1.0, emp, month_key) or 1.0)
        paid = round(raw[emp] * mult, 2)
        team += paid
        mine = [u for u in units if u["employee"] == emp]
        employees.append({"employee": emp, "units": len(mine),
                          "above": sum(1 for u in mine if u["over"] > 0),
                          "over": round(sum(u["over"] for u in mine), 2),
                          "raw": round(raw[emp], 2), "multiplier": round(mult, 4), "paid": paid})
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
            "team_paid": round(team, 2),
            "total_paid": round(team + (manager["amount"] if manager else 0.0), 2),
            "notes_waiting": waiting, "no_fee_units": sorted(no_fee),
            "ready": bool(rows) and closed and not waiting}


def month_sheet(month_key, today=None):
    """The full sheet — ADMIN ONLY. Employees get my_money(). An approved month is served
    from its frozen copy."""
    today = today or HOST.require("now")().date()
    ck = (db.version(), month_key, today.isoformat())
    if ck in _cache:
        return _cache[ck]
    approval = db.approval(month_key)
    frozen = db.result(month_key) if approval else None
    if frozen and "units" in frozen:
        sheet = dict(frozen, approval=approval, ready=False)
    else:
        sheet = dict(_compute(month_key, today), approval=approval)
    _cache.clear()
    _cache[ck] = sheet
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
    return {"month": month_key, "amount": (row or {}).get("paid", 0.0), "units": units,
            "above": sum(1 for u in units if u["over"] > 0),
            "has_targets": sheet["approved_quarter"], "closed": sheet["closed"],
            "final": bool(sheet["approval"])}


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
