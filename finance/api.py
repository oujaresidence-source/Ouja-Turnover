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
