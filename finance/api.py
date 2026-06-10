# -*- coding: utf-8 -*-
"""Thin bridge between the ERP package and the live bot.py module.

`B` is bot.py's module object (set once by finance.mount). Everything the ERP
reuses from the monolith — auth, STATE_DIR stores, Daftra import, dup shield,
custody math, expenses V4, owner-report math — is reached as `B.<name>` so the
data layer stays single-sourced and untouched.
"""

import json
from datetime import datetime

from aiohttp import web

B = None  # bot.py module object — set by finance.mount()


def attach(botmod):
    global B
    B = botmod


def jres(data, status=200):
    """JSON response that keeps Arabic readable (no \\uXXXX escapes)."""
    return web.json_response(
        data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


# ---------------- auth / roles (server-side, reusing bot.py's system) ----------------

def authed(request):
    """Same login the dashboard uses (DASHBOARD_TOKEN or session token)."""
    try:
        return bool(B and B._dash_auth(request))
    except Exception:
        return False


def can(request, tab, action="read"):
    """Role check via bot.py's _user_can (legacy token = super-admin)."""
    try:
        return bool(B and B._user_can(request, tab, action))
    except Exception:
        return False


def role(request):
    return B._req_role(request)


def actor(request):
    return B._req_actor(request)


def can_finance(request):
    """admin or accountant — the two roles allowed inside the ERP."""
    return bool(B and B._fb_can_finance(request))


def can_high(request):
    """May approve >= 3000 SAR (Faisal tier: admin/owner; legacy token = admin)."""
    return bool(B and B.can_finance_approve_high_value(request))


def is_admin(request):
    return B._req_role(request) == "admin"


# ---------------- helpers ----------------

def _days_since(iso):
    try:
        d = datetime.fromisoformat(str(iso)[:19]).date()
        return max(0, (datetime.now(B.TZ).date() - d).days)
    except Exception:
        return None


def _amt(x):
    """Bank txn signed view: debit = money out, credit = money in."""
    deb = B._fb_money(x.get("debit"))
    cred = B._fb_money(x.get("credit"))
    if deb > 0:
        return B._fb_money_str(deb), "out"
    return B._fb_money_str(cred), "in"


_DUP_SUGGESTED = ("possible_duplicate", "strong_possible_duplicate", "needs_manual_review")


# ---------------- Today: the one prioritized work queue ----------------

async def work_queue(request):
    """Aggregate of everything that needs a human, in priority order.
    Reads existing state only — no live external calls (fast + honest)."""
    ov_resp = await B._api_fb_overview(request)
    ov = json.loads(ov_resp.body)
    if not ov.get("ok"):
        return {"error": ov.get("error") or "overview_failed"}

    ib = B._fb_inbox({})

    # 1) >= 3000 awaiting Faisal (largest first — that's where the risk is)
    approvals = [i for i in ib["items"] if i.get("lane") == "needs_faisal_approval"]
    approvals.sort(key=lambda i: float(B._fb_money(i.get("amount"))), reverse=True)
    g_approvals = [{
        "id": i["id"], "kind": i.get("kind"), "date": i.get("date"),
        "desc": (i.get("description") or "")[:140], "amount": i.get("amount"),
        "direction": i.get("direction"), "apartment": i.get("apartment") or "",
        "category": i.get("category") or "", "chip_ar": i.get("reason_chip_ar") or "",
        "chip_en": i.get("reason_chip_en") or "",
    } for i in approvals[:50]]

    # 2) unclassified bank txns (same definition as the bank summary: status=needs_review)
    uncls = [x for x in B._fb_bank.values() if x.get("status") == "needs_review"]
    uncls.sort(key=lambda x: x.get("date") or "", reverse=True)
    g_uncls = []
    for x in uncls[:25]:
        amount, dirn = _amt(x)
        g_uncls.append({"id": x["id"], "date": x.get("date"),
                        "desc": (x.get("description") or "")[:140],
                        "amount": amount, "dir": dirn,
                        "card": x.get("card_last4") or "",
                        "category": x.get("category") or "unknown"})

    # 3) suggested matches from the dup shield, awaiting a human verdict
    sugg = [x for x in B._fb_bank.values()
            if x.get("daftra_duplicate_status") in _DUP_SUGGESTED
            and x.get("match_status") != "matched"]
    sugg.sort(key=lambda x: int(x.get("daftra_duplicate_confidence") or 0), reverse=True)
    g_sugg = []
    for x in sugg[:25]:
        amount, dirn = _amt(x)
        g_sugg.append({"id": x["id"], "date": x.get("date"),
                       "desc": (x.get("description") or "")[:140],
                       "amount": amount, "dir": dirn,
                       "conf": int(x.get("daftra_duplicate_confidence") or 0),
                       "reason_ar": x.get("daftra_duplicate_reason_ar") or "",
                       "reason_en": x.get("daftra_duplicate_reason_en") or "",
                       "journal_no": x.get("matched_daftra_number")})

    # 4) contracts with no Daftra cost-center link (breaks unit profitability)
    g_contracts = [{"key": p.get("id") or k, "name": p.get("apartment_name") or k,
                    "owner": p.get("owner_name") or ""}
                   for k, p in B._fb_contracts.items() if not p.get("daftra_cost_center_id")]

    # 5) stale / failed imports
    g_imports = []
    for r in list(B._fb_runs)[-60:]:
        if r.get("status") == "failed":
            age = _days_since(r.get("finished_at") or r.get("started_at"))
            if age is not None and age <= 14:
                g_imports.append({"id": r.get("id"), "source": r.get("source"),
                                  "status": "failed", "when": r.get("finished_at") or r.get("started_at"),
                                  "file": r.get("filename") or "", "error": (r.get("error_summary") or "")[:200]})
    bank_run = (ov.get("bank") or {}).get("last_run") or {}
    bank_age = _days_since(bank_run.get("finished_at")) if bank_run else None
    if bank_age is not None and bank_age >= 3:
        g_imports.append({"id": "stale-bank", "source": "bank", "status": "stale",
                          "when": bank_run.get("finished_at"), "file": bank_run.get("filename") or "",
                          "error": ""})

    steps = ov.get("steps") or []
    done = sum(1 for s in steps if s.get("done"))
    health = int(round(100.0 * done / len(steps))) if steps else 0

    groups = [
        {"key": "approvals", "count": len(approvals), "items": g_approvals},
        {"key": "unclassified", "count": len(uncls), "items": g_uncls},
        {"key": "suggested", "count": len(sugg), "items": g_sugg},
        {"key": "contracts", "count": len(g_contracts), "items": g_contracts[:25]},
        {"key": "imports", "count": len(g_imports), "items": g_imports[:10]},
    ]
    next_key = next((g["key"] for g in groups if g["count"]), None)

    return {
        "ok": True,
        "role": ov.get("role"),
        "can_high": can_high(request),
        "health": {"pct": health, "done": done, "total": len(steps), "steps": steps},
        "bank_age_days": bank_age,
        "bank_last_run": {"when": bank_run.get("finished_at"), "file": bank_run.get("filename")} if bank_run else None,
        "next_best": next_key,
        "groups": groups,
        "counters": counters_snapshot(),
    }


def counters_snapshot():
    """Light recount used by mutation responses so the UI patches counters
    without re-rendering (R1/R1b): queue membership derives from store state."""
    ib = B._fb_inbox({})
    uncls = sum(1 for x in B._fb_bank.values() if x.get("status") == "needs_review")
    sugg = sum(1 for x in B._fb_bank.values()
               if x.get("daftra_duplicate_status") in _DUP_SUGGESTED
               and x.get("match_status") != "matched")
    contracts = sum(1 for p in B._fb_contracts.values() if not p.get("daftra_cost_center_id"))
    return {"approvals": ib["counts"].get("needs_faisal", 0),
            "unclassified": uncls, "suggested": sugg, "contracts": contracts}


def approve(request, body):
    """Faisal decision on one item. Server-side permission split:
    >= 3000 needs the admin tier; accountant may decide below it."""
    item_id = (body.get("id") or "").strip()
    decision = (body.get("decision") or "").strip()
    reason = (body.get("reason") or "").strip()
    res = B._fb_do_approval(item_id, decision, actor(request), reason,
                            can_high(request), can_finance(request))
    if res.get("error"):
        return res, int(res.get("code") or 400)
    res["counters"] = counters_snapshot()
    return res, 200


# ====================== البنك Bank workspace ======================

def _acct_records():
    return [r for r in B._fb_external.values() if r.get("source_type") == "accounts"]


def _cc_records():
    return [r for r in B._fb_external.values() if r.get("source_type") == "cost_centers"]


def _acct_by_id():
    return {str(r.get("source_id")): r for r in _acct_records()}


def accounts_payload():
    """The REAL Daftra chart (دليل الحسابات) as imported — classification options.
    Free text is rejected at classify time; this list is the whole universe."""
    accs = sorted(_acct_records(), key=lambda r: ((r.get("code") or ""), (r.get("display_name") or "")))
    ccs = sorted(_cc_records(), key=lambda r: (r.get("display_name") or ""))
    units = sorted({(p.get("apartment_name") or "").strip()
                    for p in B._fb_contracts.values() if (p.get("apartment_name") or "").strip()})
    return {"ok": True,
            "accounts": [{"id": str(r.get("source_id")), "code": r.get("code") or "",
                          "name": r.get("display_name") or ""} for r in accs],
            "cost_centers": [{"id": str(r.get("source_id")), "code": r.get("code") or "",
                              "name": r.get("display_name") or ""} for r in ccs],
            "units": units,
            "counts": {"accounts": len(accs), "cost_centers": len(ccs)}}


def _bank_row(x):
    """Compact row view + the pipeline chip states (مُصنّف → مُتحقق → مُرحّل)."""
    amount, dirn = _amt(x)
    ec = x.get("erp_class") or {}
    dq = x.get("daftra_duplicate_status") or "not_checked"
    migrated = bool(x.get("matched_daftra_id")) and dq in ("already_in_daftra_verified", "linked_existing")
    verified = dq in ("already_in_daftra_verified", "linked_existing", "not_found_after_full_check")
    return {"id": x["id"], "date": x.get("date") or "", "desc": x.get("description") or "",
            "amount": amount, "dir": dirn, "ref": x.get("ref") or "", "card": x.get("card_last4") or "",
            "category": x.get("category") or "unknown", "status": x.get("status") or "needs_review",
            "match_status": x.get("match_status") or "unmatched",
            "dup": dq, "dup_conf": x.get("daftra_duplicate_confidence"),
            "journal_no": x.get("matched_daftra_number"),
            "cls": {"account_id": str(ec.get("daftra_account_id") or ""),
                    "code": ec.get("account_code") or "", "name": ec.get("account_name") or "",
                    "cost_center_id": str(ec.get("cost_center_id") or ""),
                    "cost_center": ec.get("cost_center_name") or "",
                    "counterparty": ec.get("counterparty") or "", "unit": ec.get("unit") or ""},
            "classified": bool(ec.get("daftra_account_id")) or (x.get("status") == "reviewed"),
            "verified": verified, "migrated": migrated}


def _sim_index():
    """description-key -> [(account_id, uses)] built from already erp-classified txns."""
    idx = {}
    for x in B._fb_bank.values():
        ec = x.get("erp_class") or {}
        aid = str(ec.get("daftra_account_id") or "")
        if not aid:
            continue
        key = B._fb_similar_key(x.get("description") or "")
        if not key:
            continue
        idx.setdefault(key, {})
        idx[key][aid] = idx[key].get(aid, 0) + 1
    return {k: sorted(v.items(), key=lambda kv: kv[1], reverse=True) for k, v in idx.items()}


def _bank_suggestions(x, acct_idx, sim_idx):
    """Top-3 account suggestions: category mapping first, then same-description history."""
    out, seen = [], set()
    m = B._fb_mappings.get(x.get("category") or "")
    if m and m.get("daftra_account_id"):
        aid = str(m["daftra_account_id"])
        acc = acct_idx.get(aid)
        if acc:
            out.append({"account_id": aid, "code": acc.get("code") or "",
                        "name": acc.get("display_name") or "",
                        "why_ar": "ربط فئة «" + (x.get("category") or "") + "»",
                        "why_en": "category mapping"})
            seen.add(aid)
    key = B._fb_similar_key(x.get("description") or "")
    for aid, n in (sim_idx.get(key) or []):
        if len(out) >= 3:
            break
        if aid in seen:
            continue
        acc = acct_idx.get(aid)
        if not acc:
            continue
        out.append({"account_id": aid, "code": acc.get("code") or "",
                    "name": acc.get("display_name") or "",
                    "why_ar": "استُخدم " + str(n) + "× لوصف مشابه",
                    "why_en": "used " + str(n) + "x for similar"})
        seen.add(aid)
    return out


def bank_register(params):
    """Server-side pagination over the FULL register (no 400-row cap) + filter counts."""
    f = (params.get("f") or "all").strip()
    q = (params.get("q") or "").strip().lower()
    dfrom = (params.get("from") or "").strip()
    dto = (params.get("to") or "").strip()
    try:
        page = max(1, int(params.get("p") or 1))
    except Exception:
        page = 1
    try:
        ps = min(200, max(10, int(params.get("ps") or 50)))
    except Exception:
        ps = 50

    def in_range(x):
        d = (x.get("date") or "")[:10]
        if dfrom and d and d < dfrom:
            return False
        if dto and d and d > dto:
            return False
        if q:
            hay = ((x.get("description") or "") + " " + (x.get("ref") or "") + " " +
                   (x.get("debit") or "") + " " + (x.get("credit") or "")).lower()
            if q not in hay:
                return False
        return True

    base = [x for x in B._fb_bank.values() if in_range(x)]

    def is_done(x):
        return x.get("status") == "reviewed"

    def ge3000(x):
        return float(B._fb_money(x.get("debit"))) >= 3000.0

    counts = {"all": len(base),
              "needs_review": sum(1 for x in base if x.get("status") == "needs_review"),
              "done": sum(1 for x in base if is_done(x)),
              "unmatched": sum(1 for x in base if (x.get("match_status") or "unmatched") == "unmatched"),
              "ge3000": sum(1 for x in base if ge3000(x))}

    if f == "needs_review":
        sel = [x for x in base if x.get("status") == "needs_review"]
    elif f == "done":
        sel = [x for x in base if is_done(x)]
    elif f == "unmatched":
        sel = [x for x in base if (x.get("match_status") or "unmatched") == "unmatched"]
    elif f == "ge3000":
        sel = [x for x in base if ge3000(x)]
    else:
        sel = base

    sel.sort(key=lambda x: ((x.get("date") or ""), str(x.get("row") or "")), reverse=True)
    total = len(sel)
    pages = max(1, (total + ps - 1) // ps)
    page = min(page, pages)
    chunk = sel[(page - 1) * ps: (page - 1) * ps + ps]

    acct_idx = _acct_by_id()
    sim_idx = _sim_index()
    rows = []
    for x in chunk:
        r = _bank_row(x)
        if x.get("status") == "needs_review":
            r["suggestions"] = _bank_suggestions(x, acct_idx, sim_idx)
        rows.append(r)
    return {"ok": True, "rows": rows, "total": total, "page": page, "pages": pages,
            "page_size": ps, "counts": counts}


def bank_classify(request, body):
    """v2 classification: ONLY a real imported Daftra account is accepted.
    Stores {daftra_account_id, account_code, cost_center, counterparty, unit} on the
    txn (erp_class), flips status to reviewed, audits, saves. Bulk via ids[]."""
    ids = body.get("ids") or ([body.get("id")] if body.get("id") else [])
    ids = [str(i) for i in ids if i]
    if not ids:
        return {"error": "no_ids"}, 400
    clear = bool(body.get("clear"))
    acct_idx = _acct_by_id()
    acc = cc = None
    aid = ccid = ""
    if not clear:
        aid = str(body.get("account_id") or "").strip()
        acc = acct_idx.get(aid)
        if not acc:
            return {"error": "account_not_in_chart",
                    "message_ar": "اختر حسابًا من دليل دافترة المستورد — النص الحر مرفوض.",
                    "message_en": "Pick an account from the imported Daftra chart — free text is rejected."}, 422
        ccid = str(body.get("cost_center_id") or "").strip()
        if ccid:
            cc = next((r for r in _cc_records() if str(r.get("source_id")) == ccid), None)
            if not cc:
                return {"error": "cost_center_unknown",
                        "message_ar": "مركز التكلفة غير موجود في المستورد من دافترة.",
                        "message_en": "Cost center not found in the imported Daftra data."}, 422
    now = datetime.now(B.TZ).isoformat(timespec="seconds")
    who = actor(request)
    rows, missing = [], []
    for i in ids:
        x = B._fb_bank.get(i)
        if not x:
            missing.append(i)
            continue
        before = {"status": x.get("status"), "erp_class": x.get("erp_class")}
        if clear:
            x.pop("erp_class", None)
            x["status"] = "needs_review"
        else:
            x["erp_class"] = {"daftra_account_id": aid, "account_code": acc.get("code") or "",
                              "account_name": acc.get("display_name") or "",
                              "cost_center_id": ccid,
                              "cost_center_name": (cc or {}).get("display_name") or "",
                              "counterparty": str(body.get("counterparty") or "").strip()[:120],
                              "unit": str(body.get("unit") or "").strip()[:80],
                              "by": who, "at": now}
            x["status"] = "reviewed"
            x["reviewed_by"] = who
            x["reviewed_at"] = now
            if (body.get("unit") or "").strip():
                x["apartment"] = str(body.get("unit")).strip()[:80]
        B._fb_audit_add(who, "erp_unclassify" if clear else "erp_classify", "bank", i,
                        before=before, after=x.get("erp_class"))
        rows.append(_bank_row(x))
    if rows:
        B._fb_save("finance_bank_transactions.json", B._fb_bank)
    return {"ok": True, "rows": rows, "missing": missing, "counters": counters_snapshot()}, 200
