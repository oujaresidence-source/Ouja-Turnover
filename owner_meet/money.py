# -*- coding: utf-8 -*-
"""
owner_meet.money — PURE arithmetic over statement dicts the HOST already computed.

M1: there is ONE money truth — `_owner_month_report` (owner level) and `unit_slice` of it (one
apartment). This module only SUMS and ARRANGES their fields; it never derives income, fees,
cleaning or expenses itself. Every sum is Decimal, quantized to the halala.

M3: the waterfall starts at the statement's own «صافي الحجوزات» (`total_income`). There is no
guest-paid / VAT / channel-fee row in this version (Faisal 2026-10-06) and no back-calculation.
If the rows do not reconcile to `owner_net` within a halala, the waterfall is NOT drawn.
"""

from decimal import ROUND_HALF_UP, Decimal

HALALA = Decimal("0.01")
FIELDS = ("total_income", "ouja_fee", "cleaning", "expenses", "adjustments", "owner_net")


def D(x):
    if x is None or x == "":
        return Decimal(0)
    return Decimal(str(x)).quantize(HALALA, rounding=ROUND_HALF_UP)


def month_row(mk, rep, partial=False):
    """One statement dict -> the fields the meeting shows, as Decimal. None rep -> missing month."""
    if rep is None:
        return {"m": mk, "missing": True, "partial": partial, "degraded": False,
                **{f: Decimal(0) for f in FIELDS}}
    cl = rep.get("cleaning")
    cleaning = cl.get("total") if isinstance(cl, dict) else cl
    return {"m": mk, "missing": False, "partial": partial,
            "degraded": bool(rep.get("degraded")), "stale": bool(rep.get("stale")),
            "computed_at": rep.get("computed_at"),
            "cleaning_type": (cl.get("type") if isinstance(cl, dict) else None),
            "total_income": D(rep.get("total_income")), "ouja_fee": D(rep.get("ouja_fee")),
            "cleaning": D(cleaning), "expenses": D(rep.get("expenses")),
            "adjustments": D(rep.get("adjustments_total")), "owner_net": D(rep.get("owner_net"))}


def sum_rows(rows):
    tot = {f: sum((r[f] for r in rows), Decimal(0)) for f in FIELDS}
    tot["degraded_months"] = [r["m"] for r in rows if r.get("degraded")]
    tot["missing_months"] = [r["m"] for r in rows if r.get("missing")]
    return tot


def waterfall(tot):
    """-> {"rows": [{key, amount, sign}], "reconciled": bool, "residual": Decimal}.

    income - fee - cleaning - expenses + adjustments == owner_net (to the halala), else
    reconciled=False and the chapter shows the statement's own totals instead (spec §5.2).
    """
    rows = [{"key": "income", "amount": tot["total_income"], "sign": 1},
            {"key": "fee", "amount": tot["ouja_fee"], "sign": -1}]
    if tot["cleaning"] != 0:
        rows.append({"key": "cleaning", "amount": tot["cleaning"], "sign": -1})
    rows.append({"key": "expenses", "amount": tot["expenses"], "sign": -1})
    if tot["adjustments"] != 0:
        rows.append({"key": "adjustments", "amount": tot["adjustments"], "sign": 1})
    calc = (tot["total_income"] - tot["ouja_fee"] - tot["cleaning"] - tot["expenses"]
            + tot["adjustments"])
    residual = tot["owner_net"] - calc
    rows.append({"key": "net", "amount": tot["owner_net"], "sign": 0})
    return {"rows": rows, "reconciled": abs(residual) <= HALALA, "residual": residual}


def per_100(wf):
    """«من كل 100 ريال»: each deduction and the owner's share per 100 of income, as integers that
    sum to exactly 100 (largest remainder). None when income <= 0, the waterfall is unreconciled,
    a statement adjustment exists, or a part is negative — none of those has an honest per-100
    picture, and a wrong picture is worse than none."""
    rows = wf["rows"]
    income = rows[0]["amount"]
    if income <= 0 or not wf["reconciled"] or any(r["key"] == "adjustments" for r in rows):
        return None
    parts = [(r["key"], r["amount"]) for r in rows[1:-1]]
    parts.append(("owner", rows[-1]["amount"]))
    if any(a < 0 for _k, a in parts):
        return None
    raw = [(k, a * 100 / income) for k, a in parts]
    floors = [(k, int(v)) for k, v in raw]
    left = 100 - sum(v for _k, v in floors)
    order = sorted(range(len(raw)), key=lambda i: -(raw[i][1] - int(raw[i][1])))
    out = dict(floors)
    for i in order[:max(0, left)]:
        out[raw[i][0]] += 1
    return out


def can_send(snap):
    """M4 + readiness, read from a snapshot: -> (ok, reason_ar)."""
    meta = snap.get("meta") or {}
    if meta.get("degraded"):
        return False, "بيانات الحجوزات لهذه الفترة ناقصة (سحب جزئي من Hostaway) — أعد التجهيز لاحقاً"
    reds = [c for c in ((snap.get("presenter") or {}).get("readiness") or []) if c.get("level") == "red"]
    if reds:
        return False, reds[0].get("text_ar") or "فيه فحص أحمر مفتوح"
    return True, None


def as_float(x):
    return float(x) if isinstance(x, Decimal) else x
