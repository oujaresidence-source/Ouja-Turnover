# -*- coding: utf-8 -*-
"""Financial statements + budget math — PURE functions only.

No aiohttp, no bot.py access, no I/O: callers pass plain dicts/lists (imported
Daftra journals, chart of accounts, budgets) and get plain dicts back, so every
number here is unit-testable with synthetic data.

Conventions
-----------
- Journal line: {"account_id", "account_name", "account_code", "debit": "0.00",
  "credit": "0.00", "cost_center_id", "cost_center_name", "description"}
- Account record (the imported Daftra mirror): {"source_id", "display_name",
  "code", "source_payload": {raw Daftra object}}
- Account TYPE comes from Daftra's own payload when it carries one; an account
  without a recognizable type goes to the explicit «غير مصنّف النوع» bucket —
  NEVER guessed (the UI shows a completeness banner instead).
- Sign conventions: asset/expense are debit-positive; liability/equity/income
  are credit-positive.
"""

from decimal import Decimal, ROUND_HALF_UP

TWO = Decimal("0.01")


def D(x):
    try:
        return Decimal(str(x if x not in (None, "") else 0))
    except Exception:
        return Decimal(0)


def fnum(x):
    """JSON-safe 2dp float of a Decimal."""
    return float(D(x).quantize(TWO, rounding=ROUND_HALF_UP))


# ---------------- account typing (from Daftra's own fields) ----------------

_TYPE_KEYS = ("type", "account_type", "category", "account_category", "nature",
              "balance_type", "classification", "cat", "group", "account_group",
              "main_type", "acc_type")

_TYPE_TOKENS = (
    ("asset", ("asset", "اصول", "أصول", "اصل", "أصل", "موجودات")),
    ("liability", ("liabilit", "خصوم", "التزام", "إلتزام", "مطلوبات")),
    ("equity", ("equity", "حقوق", "راس المال", "رأس المال", "capital")),
    ("income", ("income", "revenue", "ايراد", "إيراد", "دخل", "مبيعات", "sales")),
    ("expense", ("expense", "مصروف", "مصاريف", "تكاليف", "تكلفة", "cost", "expenditure")),
)

_CASH_NAME_TOKENS = ("بنك", "نقد", "صندوق", "كاش", "bank", "cash", "راجحي", "rajhi")


def _norm_token(v):
    return str(v or "").strip().lower()


def detect_type(payload):
    """(normalized_type|None, found_key, raw_value) from a raw Daftra account payload."""
    if not isinstance(payload, dict):
        return None, "", ""
    candidates = []
    for k in _TYPE_KEYS:
        if k in payload and payload[k] not in (None, ""):
            candidates.append((k, payload[k]))
    # one level of nesting (Daftra wraps records under their model name sometimes)
    for v in payload.values():
        if isinstance(v, dict):
            for k in _TYPE_KEYS:
                if k in v and v[k] not in (None, ""):
                    candidates.append((k, v[k]))
    for k, raw in candidates:
        tok = _norm_token(raw)
        for norm, needles in _TYPE_TOKENS:
            if any(n in tok for n in needles):
                return norm, k, str(raw)
    if candidates:                      # a field exists but the value is opaque (e.g. numeric id)
        return None, candidates[0][0], str(candidates[0][1])
    return None, "", ""


def type_accounts(accounts):
    """account_id -> {"name","code","type","type_key","type_raw","is_cash"}"""
    out = {}
    for rec in accounts:
        aid = str(rec.get("source_id"))
        typ, key, raw = detect_type(rec.get("source_payload") or {})
        name = rec.get("display_name") or ""
        is_cash = any(tk in _norm_token(name) for tk in _CASH_NAME_TOKENS)
        if is_cash and typ is None:
            typ_eff = "asset"           # cash accounts are assets even when untyped …
            cash_inferred = True        # … but flagged so the coverage banner stays honest
        else:
            typ_eff, cash_inferred = typ, False
        out[aid] = {"name": name, "code": rec.get("code") or "", "type": typ_eff,
                    "typed_by_daftra": typ is not None, "cash_inferred": cash_inferred,
                    "type_key": key, "type_raw": raw, "is_cash": is_cash}
    return out


# ---------------- trial balance ----------------

def _line_net(ln):
    """debit − credit of one line (Decimal)."""
    return D(ln.get("debit")) - D(ln.get("credit"))


def trial(journals, start_iso, end_iso):
    """Per-account debit-net movements: opening (date < start) and period
    (start..end inclusive). Also period movements split by cost center."""
    acc = {}
    for ent in journals.values() if isinstance(journals, dict) else journals:
        d = str(ent.get("date") or "")[:10]
        if not d:
            continue
        bucket = "open" if d < start_iso else ("period" if d <= end_iso else None)
        if bucket is None:
            continue
        for ln in ent.get("lines") or []:
            aid = str(ln.get("account_id"))
            a = acc.setdefault(aid, {"name": ln.get("account_name") or "",
                                     "code": ln.get("account_code") or "",
                                     "open": Decimal(0), "period": Decimal(0),
                                     "by_cc": {}})
            net = _line_net(ln)
            a[bucket] += net
            if bucket == "period":
                cc = str(ln.get("cost_center_id") or "") or "—"
                ccd = a["by_cc"].setdefault(cc, {"name": ln.get("cost_center_name") or "", "net": Decimal(0)})
                ccd["net"] += net
    return acc


def _signed(net_debit, typ):
    """Natural-sign balance: assets/expenses debit-positive, the rest credit-positive."""
    return net_debit if typ in ("asset", "expense") else -net_debit


# ---------------- the four statements ----------------

def build_statements(journals, accounts, start_iso, end_iso,
                     prior_start_iso=None, prior_end_iso=None,
                     bank_account_ids=None, bank_register_delta=None):
    """All four statements + typed-coverage diagnostics. Pure."""
    bank_ids = {str(x) for x in (bank_account_ids or set())}
    types = type_accounts(accounts)
    for aid in bank_ids:                       # mapped bank accounts are cash by definition
        if aid in types:
            types[aid]["is_cash"] = True
            if types[aid]["type"] is None:
                types[aid]["type"] = "asset"
                types[aid]["cash_inferred"] = True

    cur = trial(journals, start_iso, end_iso)
    pri = trial(journals, prior_start_iso, prior_end_iso) if (prior_start_iso and prior_end_iso) else {}

    def tinfo(aid, row):
        ti = types.get(aid)
        if ti:
            return ti
        return {"name": row["name"], "code": row["code"], "type": None,
                "typed_by_daftra": False, "cash_inferred": False,
                "type_key": "", "type_raw": "", "is_cash": False}

    # ---- typed coverage (completeness banner) ----
    untyped = []
    n_typed = 0
    seen_accounts = set(cur.keys()) | set(types.keys())
    for aid in seen_accounts:
        row = cur.get(aid) or {"name": (types.get(aid) or {}).get("name", ""),
                               "code": (types.get(aid) or {}).get("code", ""),
                               "open": Decimal(0), "period": Decimal(0), "by_cc": {}}
        ti = tinfo(aid, row)
        if ti["type"] is not None and ti["typed_by_daftra"]:
            n_typed += 1
        elif ti["type"] is None:
            untyped.append({"account_id": aid, "name": ti["name"] or row["name"],
                            "code": ti["code"] or row["code"],
                            "probe_key": ti["type_key"], "probe_raw": ti["type_raw"]})
    coverage = {"accounts": len(seen_accounts), "typed_by_daftra": n_typed,
                "untyped": len(untyped),
                "pct": (round(100.0 * n_typed / len(seen_accounts)) if seen_accounts else 0),
                "untyped_accounts": sorted(untyped, key=lambda r: r["code"])[:80]}

    # ---- balance sheet (as of end) ----
    bs = {"asset": [], "liability": [], "equity": [], "untyped": []}
    totals = {"asset": Decimal(0), "liability": Decimal(0), "equity": Decimal(0), "untyped": Decimal(0)}
    earnings_cum = Decimal(0)        # income − expense from journal start through end
    pri_totals = {"asset": Decimal(0), "liability": Decimal(0), "equity": Decimal(0)}
    pri_earnings = Decimal(0)

    for aid in seen_accounts:
        row = cur.get(aid) or {"open": Decimal(0), "period": Decimal(0), "name": "", "code": "", "by_cc": {}}
        ti = tinfo(aid, row)
        cum = row["open"] + row["period"]                     # debit-net through end
        prow = pri.get(aid)
        pcum = (prow["open"] + prow["period"]) if prow else None
        if ti["type"] in ("income", "expense"):
            earnings_cum += -cum if ti["type"] == "income" else Decimal(0)
            earnings_cum -= cum if ti["type"] == "expense" else Decimal(0)
            if pcum is not None:
                pri_earnings += -pcum if ti["type"] == "income" else Decimal(0)
                pri_earnings -= pcum if ti["type"] == "expense" else Decimal(0)
            continue
        bal = _signed(cum, ti["type"] or "asset")
        entry = {"account_id": aid, "code": ti["code"] or row["code"],
                 "name": ti["name"] or row["name"], "amount": fnum(bal),
                 "prior": (None if pcum is None else fnum(_signed(pcum, ti["type"] or "asset")))}
        if ti["type"] in ("asset", "liability", "equity"):
            if bal != 0 or entry["prior"]:
                bs[ti["type"]].append(entry)
            totals[ti["type"]] += bal
            if pcum is not None:
                pri_totals[ti["type"]] += _signed(pcum, ti["type"])
        else:
            if cum != 0:
                bs["untyped"].append({**entry, "amount": fnum(cum)})   # raw debit-net, no pretend sign
            totals["untyped"] += cum

    gap = totals["asset"] - (totals["liability"] + totals["equity"] + earnings_cum + totals["untyped"])
    for k in bs:
        bs[k].sort(key=lambda r: r["code"])
    balance_sheet = {
        "as_of": end_iso, "rows": bs,
        "totals": {"assets": fnum(totals["asset"]), "liabilities": fnum(totals["liability"]),
                   "equity": fnum(totals["equity"]), "current_earnings": fnum(earnings_cum),
                   "untyped_net_debit": fnum(totals["untyped"]), "gap": fnum(gap)},
        "prior_totals": {"assets": fnum(pri_totals["asset"]), "liabilities": fnum(pri_totals["liability"]),
                         "equity": fnum(pri_totals["equity"]), "current_earnings": fnum(pri_earnings)},
        "balanced": abs(gap) < Decimal("0.005"),
    }

    # ---- income statement (period) + cost-center drill ----
    inc_rows, exp_rows = [], []
    inc_t = Decimal(0)
    exp_t = Decimal(0)
    pinc_t = Decimal(0)
    pexp_t = Decimal(0)
    cc_agg = {}
    for aid, row in cur.items():
        ti = tinfo(aid, row)
        if ti["type"] not in ("income", "expense"):
            continue
        amt = _signed(row["period"], ti["type"])
        prow = pri.get(aid)
        pamt = _signed(prow["period"], ti["type"]) if prow else None
        entry = {"account_id": aid, "code": ti["code"] or row["code"],
                 "name": ti["name"] or row["name"], "amount": fnum(amt),
                 "prior": (None if pamt is None else fnum(pamt))}
        if ti["type"] == "income":
            inc_rows.append(entry)
            inc_t += amt
            pinc_t += (pamt or Decimal(0)) if pamt is not None else Decimal(0)
        else:
            exp_rows.append(entry)
            exp_t += amt
            pexp_t += (pamt or Decimal(0)) if pamt is not None else Decimal(0)
        for cc, ccd in row["by_cc"].items():
            agg = cc_agg.setdefault(cc, {"name": ccd["name"], "income": Decimal(0), "expense": Decimal(0)})
            if ti["type"] == "income":
                agg["income"] += -ccd["net"]
            else:
                agg["expense"] += ccd["net"]
    inc_rows.sort(key=lambda r: -r["amount"])
    exp_rows.sort(key=lambda r: -r["amount"])
    income = {
        "period": {"start": start_iso, "end": end_iso},
        "income_rows": inc_rows, "expense_rows": exp_rows,
        "totals": {"income": fnum(inc_t), "expenses": fnum(exp_t), "net": fnum(inc_t - exp_t)},
        "prior_totals": {"income": fnum(pinc_t), "expenses": fnum(pexp_t), "net": fnum(pinc_t - pexp_t)},
        "by_cost_center": sorted(
            [{"cost_center_id": cc, "name": a["name"], "income": fnum(a["income"]),
              "expense": fnum(a["expense"]), "net": fnum(a["income"] - a["expense"])}
             for cc, a in cc_agg.items()],
            key=lambda r: -(r["net"])),
    }

    # ---- equity changes (period) ----
    eq_open = Decimal(0)
    contrib = Decimal(0)
    withdraw = Decimal(0)
    earn_open = Decimal(0)
    for aid in seen_accounts:
        row = cur.get(aid) or {"open": Decimal(0), "period": Decimal(0)}
        ti = tinfo(aid, row)
        if ti["type"] == "equity":
            eq_open += -row["open"]
            mv = -row["period"]                       # credit-positive
            if mv >= 0:
                contrib += mv
            else:
                withdraw += -mv
        elif ti["type"] == "income":
            earn_open += -row["open"]
        elif ti["type"] == "expense":
            earn_open -= row["open"]
    net_period = inc_t - exp_t
    opening_total = eq_open + earn_open
    closing_total = opening_total + net_period + contrib - withdraw
    bs_equity_side = totals["equity"] + earnings_cum
    equity = {
        "period": {"start": start_iso, "end": end_iso},
        "opening": fnum(opening_total), "net_income": fnum(net_period),
        "contributions": fnum(contrib), "withdrawals": fnum(withdraw),
        "closing": fnum(closing_total),
        "ties_to_balance_sheet": abs(closing_total - bs_equity_side) < Decimal("0.005"),
        "gap": fnum(closing_total - bs_equity_side),
    }

    # ---- cash flow (direct method, period) ----
    cash_ids = {aid for aid, ti in types.items() if ti.get("is_cash")} | bank_ids
    groups = {"income": Decimal(0), "expense": Decimal(0), "asset": Decimal(0),
              "liability": Decimal(0), "equity": Decimal(0), "untyped": Decimal(0)}
    for ent in (journals.values() if isinstance(journals, dict) else journals):
        d = str(ent.get("date") or "")[:10]
        if not (start_iso <= d <= end_iso):
            continue
        lines = ent.get("lines") or []
        cash_delta = sum((_line_net(ln) for ln in lines if str(ln.get("account_id")) in cash_ids), Decimal(0))
        if cash_delta == 0:
            continue
        # classify by the largest counterpart line
        cps = [ln for ln in lines if str(ln.get("account_id")) not in cash_ids]
        cps.sort(key=lambda ln: abs(_line_net(ln)), reverse=True)
        ti = tinfo(str(cps[0].get("account_id")), {"name": "", "code": ""}) if cps else None
        key = (ti["type"] if (ti and ti["type"]) else "untyped")
        groups[key] += cash_delta
    open_cash = Decimal(0)
    close_cash = Decimal(0)
    for aid in cash_ids:
        row = cur.get(aid)
        if not row:
            continue
        open_cash += row["open"]
        close_cash += row["open"] + row["period"]
    net_cash = sum(groups.values(), Decimal(0))
    reg_delta = None if bank_register_delta is None else D(bank_register_delta)
    cash_flow = {
        "period": {"start": start_iso, "end": end_iso},
        "groups": {k: fnum(v) for k, v in groups.items()},
        "net_cash": fnum(net_cash),
        "opening_cash": fnum(open_cash), "closing_cash": fnum(close_cash),
        "ties_internal": abs((close_cash - open_cash) - net_cash) < Decimal("0.005"),
        "cash_account_ids": sorted(cash_ids),
        "bank_register_delta": (None if reg_delta is None else fnum(reg_delta)),
        "ties_bank_register": (None if reg_delta is None else bool(abs(net_cash - reg_delta) < Decimal("0.005"))),
        "gap_vs_bank": (None if reg_delta is None else fnum(net_cash - reg_delta)),
    }

    return {"coverage": coverage, "balance_sheet": balance_sheet, "income": income,
            "equity": equity, "cash_flow": cash_flow}


def account_lines(journals, account_id, start_iso, end_iso, limit=400):
    """Drill-down (R7): the journal lines behind one account in a period."""
    aid = str(account_id)
    out = []
    for ent in (journals.values() if isinstance(journals, dict) else journals):
        d = str(ent.get("date") or "")[:10]
        if not (start_iso <= d <= end_iso):
            continue
        for ln in ent.get("lines") or []:
            if str(ln.get("account_id")) != aid:
                continue
            out.append({"date": d, "entry_id": ent.get("entry_id"), "number": ent.get("number"),
                        "description": (ln.get("description") or ent.get("description") or "")[:140],
                        "debit": fnum(ln.get("debit")), "credit": fnum(ln.get("credit")),
                        "cost_center": ln.get("cost_center_name") or ""})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out[:limit]


# ---------------- budget math ----------------

def budget_row(budget_amount, actual_amount):
    """Variance + alert per the acceptance spec: 10,000 budget / 9,200 actual →
    remaining 800, 92% used, alert at >=90% (warn) and >=100% (over)."""
    b = D(budget_amount)
    a = D(actual_amount)
    pct = (int((a / b * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if b > 0 else None)
    alert = None
    if pct is not None:
        if pct >= 100:
            alert = "over"
        elif pct >= 90:
            alert = "warn"
    return {"budget": fnum(b), "actual": fnum(a), "remaining": fnum(b - a),
            "pct": pct, "alert": alert}


def split_weekly(month_total, weights=None, weeks=None):
    """Split a month budget into N weekly buckets that ALWAYS sum back exactly.
    weights: optional list of Decimals; default equal split. Remainder goes to
    the last week so the halalas never leak."""
    total = D(month_total)
    n = int(weeks or (len(weights) if weights else 4))
    if n <= 0:
        return []
    if weights:
        wsum = sum((D(w) for w in weights), Decimal(0))
        parts = [(total * D(w) / wsum).quantize(TWO, rounding=ROUND_HALF_UP) if wsum else Decimal(0)
                 for w in weights]
    else:
        base = (total / n).quantize(TWO, rounding=ROUND_HALF_UP)
        parts = [base] * n
    drift = total - sum(parts, Decimal(0))
    if parts:
        parts[-1] += drift
    return [fnum(p) for p in parts]


def weekly_sums_ok(parts, month_total):
    return abs(sum((D(p) for p in parts), Decimal(0)) - D(month_total)) < Decimal("0.005")
