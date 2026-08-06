# -*- coding: utf-8 -*-
"""الملاك v2.1 — owner-workspace server logic.

Slice 0b: the statement DIAGNOSIS — a line-by-line reconciliation of one
owner-month built from a TARGETED Hostaway window pull, classifying every
candidate reservation as included/excluded-with-reason, probing the raw
payout/payment fields, and quantifying the two silent-exclusion bugs
(history-cache truncation + units missing from the registry).

Slice 1: OWNER & APARTMENT MANAGER — owner profile fields (phone/notes/active),
add/remove apartments with EFFECTIVE DATES, per-apartment effective-dated
management % / cleaning policy / contract window, versioned changes, and the
v2.1 statement compute (compute_owner_statement) that reads those windows:
a unit added mid-month contributes only its in-contract days (footnoted), a
removed unit counts until its end date. With NO overlay data the compute
reproduces the legacy aggregate exactly (bit-for-bit fallback safety).

Money classification is NEVER duplicated here: rows are bucketed by running
bot.py's own compute_owner_report on the same normalized rows and correlating
ids — the table can't drift from the real statement math.
"""

import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from . import api

TWO = Decimal("0.01")

_TERMS_FILE = "owner_terms.json"
_terms_cache = {"v": None}


def _terms_store():
    if _terms_cache["v"] is None:
        v = _B()._load_json(_TERMS_FILE, {}) or {}
        v.setdefault("owners", {})
        v.setdefault("units", {})
        v.setdefault("versions", [])
        _terms_cache["v"] = v
    return _terms_cache["v"]


def _terms_save():
    _B()._save_json(_TERMS_FILE, _terms_cache["v"])


def terms_version_add(actor, what, target, before, after, reason=""):
    st = _terms_store()
    st["versions"].append({
        "at": datetime.now(_B().TZ).isoformat(timespec="seconds"),
        "by": (actor or "")[:60], "what": what, "target": target,
        "before": before, "after": after, "reason": (reason or "")[:300]})
    if len(st["versions"]) > 800:
        del st["versions"][:len(st["versions"]) - 800]
    _terms_save()


def _pdate(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def unit_overlay(apt):
    return (_terms_store()["units"] or {}).get(_B()._owner_key(apt)) or {}


def contract_window(apt):
    """(from_date|None, to_date|None) — None = open-ended on that side."""
    ov = unit_overlay(apt)
    return _pdate(ov.get("contract_from")), _pdate(ov.get("contract_to"))


def terms_on(apt, d, registry_rec=None):
    """Effective {mgmt_pct, cleaning} for one unit on one date: the LAST overlay
    term whose `from` <= d, else the registry values."""
    rec = registry_rec or {}
    base = {"mgmt_pct": rec.get("mgmt_pct"),
            "cleaning": rec.get("cleaning") or {"type": "ours", "amount": 0}}
    ov = unit_overlay(apt)
    best = None
    for term in ov.get("terms") or []:
        f = _pdate(term.get("from"))
        if f is None or (d is not None and f <= d):
            if best is None or (_pdate(best.get("from")) or date.min) <= (f or date.min):
                best = term
    if best:
        if best.get("mgmt_pct") is not None:
            base["mgmt_pct"] = best["mgmt_pct"]
        if best.get("cleaning"):
            # per-month cleaning overrides live on the registry record (the single
            # source, written by «نظافة بالشهر»). An effective-dated term replaces
            # the base type/amount but must NOT wipe a month-specific override —
            # carry it across unless the term defines its own overrides.
            bc = dict(best["cleaning"])
            reg_ov = (rec.get("cleaning") or {}).get("overrides")
            if reg_ov and not bc.get("overrides"):
                bc["overrides"] = dict(reg_ov)
            base["cleaning"] = bc
    return base


def _B():
    return api.B


# Raw-field candidates worth probing on a live reservation (per owner-report-2:
# the exact live field names were never confirmed — the probe shows them).
_PROBE_KEYS = (
    "airbnbExpectedPayoutAmount", "expectedPayoutAmount", "ownerPayout", "hostPayout",
    "paymentStatus", "payment_status", "isPaid",
    "alreadyPaid", "totalPaid", "paidAmount", "already_paid", "total_paid",
    "remainingBalance", "remaining_balance", "balanceDue",
    "totalPrice", "refundAmount", "channelName", "status",
)


def _probe(raw):
    """The raw payout/payment-ish fields actually PRESENT on one reservation."""
    out = {}
    for k in _PROBE_KEYS:
        if k in raw and raw.get(k) not in (None, ""):
            out[k] = raw.get(k)
    # any other numeric key that smells like money data we didn't anticipate
    for k, v in raw.items():
        if k in out or not isinstance(v, (int, float)) or not v:
            continue
        kl = k.lower()
        if any(w in kl for w in ("payout", "paid", "payment")):
            out[k] = v
    return out


def _owner_units(owner):
    """Registry rows + resolved Hostaway listing ids for one owner."""
    B = _B()
    listings = B.get_listings_map() or {}
    units = []
    for rec in api._registry_rows():
        if (rec.get("owner") or "").strip() != (owner or "").strip():
            continue
        lid = B._owner_resolve_lid(rec, listings)
        units.append({"apartment": rec.get("apartment"), "lid": lid,
                      "listing": (listings.get(lid) or "") if lid is not None else "",
                      "mgmt_pct": rec.get("mgmt_pct"),
                      "cleaning": rec.get("cleaning") or {"type": "ours", "amount": 0}})
    return units, listings


# ====================== Slice 1: owner & unit management ======================

def owner_detail(owner):
    """Everything the إدارة editor shows for one owner."""
    B = _B()
    st = _terms_store()
    units, listings = _owner_units(owner)
    out_units = []
    for u in units:
        ov = unit_overlay(u["apartment"])
        now = terms_on(u["apartment"], datetime.now(B.TZ).date(),
                       next((r for r in api._registry_rows()
                             if (r.get("apartment") or "") == u["apartment"]), None))
        out_units.append({**u,
                          "contract_from": ov.get("contract_from"),
                          "contract_to": ov.get("contract_to"),
                          "terms": ov.get("terms") or [],
                          "mgmt_now": now.get("mgmt_pct"),
                          "cleaning_now": now.get("cleaning")})
    prof = (st["owners"] or {}).get(owner) or {}
    versions = [v for v in reversed(st["versions"]) if owner in str(v.get("target") or "")][:40]
    return {"ok": True, "owner": owner,
            "profile": {"phone": prof.get("phone") or "", "notes": prof.get("notes") or "",
                        "active": prof.get("active", True)},
            "units": out_units, "versions": versions}


def owner_save(request, body):
    owner = (body.get("owner") or "").strip()
    if not owner:
        return {"error": "owner_required"}, 400
    st = _terms_store()
    before = dict((st["owners"] or {}).get(owner) or {})
    phone = "".join(ch for ch in str(body.get("phone") or "") if ch.isdigit() or ch == "+")[:18]
    rec = {"phone": phone, "notes": (body.get("notes") or "")[:500],
           "active": bool(body.get("active", True))}
    st["owners"][owner] = rec
    terms_version_add(api.actor(request), "owner_profile", owner, before, rec)
    return {"ok": True, "profile": rec}, 200


def unit_add(request, body):
    """Attach an apartment to an owner: writes the REGISTRY (single source of
    unit→owner) + the overlay contract_from. Explicit lid (from the listings
    search) preferred — no fuzzy matching for new entries."""
    B = _B()
    owner = (body.get("owner") or "").strip()
    apt = (body.get("apartment") or "").strip()
    if not owner or not apt:
        return {"error": "owner_and_apartment_required"}, 400
    k = B._owner_key(apt)
    if k in B._owner_registry:
        existing = B._owner_registry[k]
        if (existing.get("owner") or "") != owner:
            return {"error": "apartment_taken",
                    "message_ar": "هالشقة مسجلة باسم «" + (existing.get("owner") or "?") + "» — شيلها من عنده أول.",
                    "message_en": "This apartment belongs to another owner — remove it there first."}, 409
    try:
        mgmt = round(float(body.get("mgmt_pct")), 2) if body.get("mgmt_pct") not in (None, "") else None
    except (TypeError, ValueError):
        mgmt = None
    cl = body.get("cleaning") or {}
    ctype = "owner" if cl.get("type") == "owner" else "ours"
    try:
        camt = round(float(cl.get("amount") or 0), 2)
    except (TypeError, ValueError):
        camt = 0.0
    lid = None
    if body.get("lid") not in (None, ""):
        try:
            lid = int(body.get("lid"))
        except (TypeError, ValueError):
            lid = None
    before = dict(B._owner_registry.get(k) or {})
    B._owner_registry[k] = {"apartment": apt, "owner": owner, "mgmt_pct": mgmt, "lid": lid,
                            "cleaning": {"type": ctype, "amount": camt if ctype == "owner" else 0}}
    B._save_json("owner_registry.json", B._owner_registry)
    st = _terms_store()
    u = st["units"].setdefault(k, {})
    cfrom = (body.get("from") or "").strip()[:10] or None
    u["contract_from"] = cfrom
    u.pop("contract_to", None)                      # re-adding re-opens the contract
    terms_version_add(api.actor(request), "unit_add", owner + " / " + apt, before,
                      {"registry": B._owner_registry[k], "contract_from": cfrom})
    _invalidate_owner_cache(owner)
    return {"ok": True, "unit": B._owner_registry[k], "contract_from": cfrom}, 200


def unit_remove(request, body):
    """SOFT remove: the registry row stays (history months keep computing);
    the overlay closes the contract at `to`. Months after `to` exclude it."""
    B = _B()
    apt = (body.get("apartment") or "").strip()
    k = B._owner_key(apt)
    rec = B._owner_registry.get(k)
    if not rec:
        return {"error": "apartment_not_found"}, 404
    to = (body.get("to") or "").strip()[:10]
    if not to or _pdate(to) is None:
        return {"error": "end_date_required",
                "message_ar": "حدد تاريخ نهاية العقد.", "message_en": "Set the contract end date."}, 400
    reason = (body.get("reason") or "").strip()
    if not reason:
        return {"error": "reason_required",
                "message_ar": "سبب الإزالة إلزامي.", "message_en": "A removal reason is required."}, 400
    st = _terms_store()
    u = st["units"].setdefault(k, {})
    before = {"contract_to": u.get("contract_to")}
    u["contract_to"] = to
    terms_version_add(api.actor(request), "unit_remove", (rec.get("owner") or "") + " / " + apt,
                      before, {"contract_to": to}, reason)
    _invalidate_owner_cache(rec.get("owner") or "")
    return {"ok": True, "apartment": apt, "contract_to": to}, 200


def unit_terms_set(request, body):
    """Append an EFFECTIVE-DATED terms change (mgmt % / cleaning) — never edits
    history in place; past months keep reading the terms active back then."""
    B = _B()
    apt = (body.get("apartment") or "").strip()
    k = B._owner_key(apt)
    rec = B._owner_registry.get(k)
    if not rec:
        return {"error": "apartment_not_found"}, 404
    frm = (body.get("from") or "").strip()[:10]
    if not frm or _pdate(frm) is None:
        return {"error": "from_required",
                "message_ar": "حدد تاريخ سريان التغيير.", "message_en": "Set the effective date."}, 400
    term = {"from": frm}
    if body.get("mgmt_pct") not in (None, ""):
        try:
            term["mgmt_pct"] = round(float(body.get("mgmt_pct")), 2)
        except (TypeError, ValueError):
            return {"error": "bad_mgmt_pct"}, 400
    cl = body.get("cleaning")
    if isinstance(cl, dict) and cl.get("type") in ("ours", "owner"):
        try:
            camt = round(float(cl.get("amount") or 0), 2)
        except (TypeError, ValueError):
            camt = 0.0
        term["cleaning"] = {"type": cl["type"], "amount": camt if cl["type"] == "owner" else 0}
    if len(term) == 1:
        return {"error": "nothing_to_change"}, 400
    st = _terms_store()
    u = st["units"].setdefault(k, {})
    terms = u.setdefault("terms", [])
    before = list(terms)
    terms[:] = [x for x in terms if (x.get("from") or "") != frm] + [term]
    terms.sort(key=lambda x: x.get("from") or "")
    terms_version_add(api.actor(request), "unit_terms", (rec.get("owner") or "") + " / " + apt,
                      before, list(terms), (body.get("reason") or ""))
    _invalidate_owner_cache(rec.get("owner") or "")
    return {"ok": True, "terms": terms}, 200


def unit_cleaning_month_set(request, body):
    """Set (or clear) the cleaning amount for ONE specific month on a unit — lets the
    owner give each month a different cleaning value instead of one fixed amount. Writes
    cleaning.overrides = {'YYYY-MM': amount} on the registry record. Pass clear:true (or
    an empty amount) to drop a month back to the unit's base amount."""
    B = _B()
    apt = (body.get("apartment") or "").strip()
    k = B._owner_key(apt)
    rec = B._owner_registry.get(k)
    if not rec:
        return {"error": "apartment_not_found"}, 404
    month = (body.get("month") or "").strip()[:7]
    if not (len(month) == 7 and month[4] == "-" and month[:4].isdigit() and month[5:].isdigit()
            and 1 <= int(month[5:]) <= 12):
        return {"error": "bad_month",
                "message_ar": "حدد الشهر بصيغة YYYY-MM.", "message_en": "Month must be YYYY-MM."}, 400
    cl = dict(rec.get("cleaning") or {"type": "ours", "amount": 0})
    if cl.get("type") != "owner":
        return {"error": "not_owner_paid",
                "message_ar": "النظافة على عوجا لهالوحدة — خلِّها «على المالك» أول.",
                "message_en": "Cleaning is on Ouja for this unit — set it to «owner-paid» first."}, 400
    overrides = dict(cl.get("overrides") or {})
    before = dict(overrides)
    clear = bool(body.get("clear")) or body.get("amount") in (None, "")
    if clear:
        overrides.pop(month, None)
    else:
        try:
            overrides[month] = round(float(body.get("amount")), 2)
        except (TypeError, ValueError):
            return {"error": "bad_amount"}, 400
    if overrides:
        cl["overrides"] = overrides
    else:
        cl.pop("overrides", None)
    rec = dict(rec); rec["cleaning"] = cl
    B._owner_registry[k] = rec
    B._save_json("owner_registry.json", B._owner_registry)
    terms_version_add(api.actor(request), "cleaning_month", (rec.get("owner") or "") + " / " + apt,
                      before, overrides, (body.get("reason") or month))
    _invalidate_owner_cache(rec.get("owner") or "")
    return {"ok": True, "apartment": apt, "cleaning": cl, "overrides": overrides}, 200


def listings_search(q):
    """Search the listings store for the add-apartment picker."""
    B = _B()
    listings = B.get_listings_map() or {}
    taken = {}
    for rec in api._registry_rows():
        lid = B._owner_resolve_lid(rec, listings)
        if lid is not None:
            taken[lid] = rec.get("owner") or ""
    ql = (q or "").strip().lower()
    rows = []
    for lid, name in sorted(listings.items(), key=lambda x: str(x[1] or "")):
        if ql and ql not in str(name or "").lower():
            continue
        rows.append({"lid": lid, "name": name or str(lid), "owner": taken.get(lid) or ""})
    return {"ok": True, "rows": rows[:30]}


def _invalidate_owner_cache(owner, mkey=None):
    """Terms changed → the memoized monthly reports for this owner are stale.
    v2.2: delegates to bot.py's _owner_cache_bust (the ONE implementation all
    writers share); falls back to the direct pop for older bot.py builds.
    v2.2.2: pass mkey when the change is month-scoped (statement edits) so the
    other 12 cached months survive — broad busts forced cold rebuilds."""
    try:
        bust = getattr(_B(), "_owner_cache_bust", None)
        if bust is not None:
            bust(owner=owner, mkey=mkey)
            return
        cache = _B()._owner_portal_cache
        for key in [k for k in cache if k[0] == owner and (not mkey or k[1] == mkey)]:
            cache.pop(key, None)
    except Exception:
        pass


# ====================== v2.1 statement compute (effective-dated) ======================

def _D(x):
    try:
        return Decimal(str(x if x not in (None, "") else 0))
    except Exception:
        return Decimal(0)


def _fnum(x):
    return float(_D(x).quantize(TWO, rounding=ROUND_HALF_UP))


def unit_statement(rec, mkey, force_rederive=False, settings=None):
    """One unit's month with effective dating applied ON TOP of bot.py's report.
    No overlay data → the legacy report passes through untouched (safety),
    unless force_rederive (the statement editor needs per-line mgmt % stamps).
    `settings` overrides bot.py's FINANCE_DEFAULTS for this compute only — the ONE
    way the «بدون خصم ٣٪» view asks for direct_fee_pct=0. Default None = today's
    numbers, bit-for-bit; nothing here is stored, so the override cannot leak.
    Returns (report_dict, footnotes[])."""
    B = _B()
    listings = B.get_listings_map() or {}
    apt = rec.get("apartment") or ""
    lid = B._owner_resolve_lid(rec, listings)
    start, end = B._month_bounds(mkey)
    rep = B.build_owner_report(lid, start, end, 0, dict(settings or {})) if lid is not None else None
    if rep is None:
        return None, []
    ov = unit_overlay(apt)
    cf, ct = contract_window(apt)
    has_terms = bool(ov.get("terms"))
    win_s = max(start, cf) if cf else start
    win_e = min(end, ct) if ct else end
    partial = (win_s > start) or (win_e < end)
    if not has_terms and not partial and not force_rederive:
        return rep, []                              # legacy bit-for-bit
    footnotes = []
    if win_e < win_s:
        # the whole month is outside the contract → nothing counts, all visible
        footnotes.append({"apartment": apt, "kind": "outside_contract",
                          "text_ar": apt + ": خارج فترة العقد هذا الشهر",
                          "text_en": apt + ": outside the contract this month"})
    elif partial:
        if win_s > start:
            footnotes.append({"apartment": apt, "kind": "starts_mid_month",
                              "text_ar": apt + ": من " + win_s.isoformat() + " حسب العقد",
                              "text_en": apt + ": from " + win_s.isoformat() + " per the contract"})
        if win_e < end:
            footnotes.append({"apartment": apt, "kind": "ends_mid_month",
                              "text_ar": apt + ": حتى " + win_e.isoformat() + " حسب العقد",
                              "text_en": apt + ": until " + win_e.isoformat() + " per the contract"})
    # ---- re-derive money from the report's DISPLAYED lines, window-filtered ----
    kept, excluded = [], []
    fee = Decimal(0)
    income = Decimal(0)
    for l in rep.get("resv_lines") or []:
        ci = _pdate(l.get("checkin"))
        in_win = (ci is not None) and (win_s <= ci <= win_e) and (win_e >= win_s)
        # EVERY line carries the % that applies on its check-in date — the
        # statement editor recomputes fees from these stamps after edits.
        tm = terms_on(apt, ci or start, rec)
        pct = _D(tm.get("mgmt_pct") or 0)
        l = dict(l)
        l["mgmt_pct_applied"] = float(pct)
        if not in_win:
            l["needs_review"] = False
            l["exclude_reason"] = "outside_contract"
            l["reference_total"] = l.get("income") if l.get("income") is not None else l.get("reference_total")
            l["income"] = None
            excluded.append(l)
            continue
        if l.get("income") is not None:
            line_money = _D(l["income"]) + _D(l.get("extras") or 0)
            fee += line_money * pct / Decimal(100)   # legacy applies the % to extras too
            income += line_money
        kept.append(l)
    exp_kept, exp_excluded = [], []
    exp_total = Decimal(0)
    for e in rep.get("exp_lines") or []:
        if e.get("manual"):
            # A hand-entered line is an explicit human decision, not a Hostaway
            # fact: the accountant attached it to THIS statement on purpose, so
            # its own date can never delete it. (Owner-reported 2026-08-02: an
            # invoice dated after the month vanished from the print and the
            # editor blamed «وحدة خارج فترة العقد» — a reason with nothing to do
            # with a manual entry.) A date that doesn't parse is blanked for
            # display only — it must never show text in a date column.
            if _pdate(e.get("date")) is None:
                e = {**e, "date": ""}
            exp_kept.append(e)
            exp_total += _D(e.get("amount"))
            continue
        d = _pdate(e.get("display_date") or e.get("date"))
        if d is not None and not (win_s <= d <= win_e and win_e >= win_s):
            exp_excluded.append({**e, "exclude_reason": "outside_contract"})
            continue
        exp_kept.append(e)
        exp_total += _D(e.get("amount"))
    # manual income lines (slice-2 edits) ride through untouched
    manual = _D(rep.get("manual_income") or 0)
    # cleaning: monthly amount pro-rated to the covered days (footnoted)
    days_in_month = (end - start).days + 1
    covered = max(0, (win_e - win_s).days + 1) if win_e >= win_s else 0
    cl_now = terms_on(apt, win_s if win_e >= win_s else start, rec).get("cleaning") or {}
    # per-month override: this exact month may carry its own cleaning amount
    _cl_ov = cl_now.get("overrides") or {}
    cl_month_amt = _cl_ov[mkey] if mkey in _cl_ov else cl_now.get("amount")
    cleaning_total = Decimal(0)
    if cl_now.get("type") == "owner" and covered:
        cleaning_total = (_D(cl_month_amt) * Decimal(covered) / Decimal(days_in_month)
                          ).quantize(TWO, rounding=ROUND_HALF_UP)
        if covered < days_in_month:
            footnotes.append({"apartment": apt, "kind": "cleaning_prorated",
                              "text_ar": apt + ": النظافة محسوبة نسبيًا (" + str(covered) + "/" + str(days_in_month) + " يوم)",
                              "text_en": apt + ": cleaning pro-rated (" + str(covered) + "/" + str(days_in_month) + " days)"})
    out = dict(rep)
    # stamp the applicable % on the footer lines too — force-including one from
    # the editor needs to know which management rate its money would carry
    for fk in ("refunded_lines", "unpaid_lines"):
        stamped = []
        for fl in rep.get(fk) or []:
            fl = dict(fl)
            fl["mgmt_pct_applied"] = float(_D(terms_on(apt, _pdate(fl.get("checkin")) or start, rec).get("mgmt_pct") or 0))
            stamped.append(fl)
        out[fk] = stamped
    out["resv_lines"] = kept
    out["contract_excluded_lines"] = excluded
    out["exp_lines"] = exp_kept
    out["contract_excluded_expenses"] = exp_excluded
    out["total_income"] = _fnum(income + manual)
    # The channel split has to follow the window filter too. It didn't, so a unit
    # that is OUTSIDE its contract for the month showed «إجمالي الدخل 0.00» beside
    # «دخل Airbnb 9,232.32» on the same page — found by the 2026-08-04 sweep on
    # عبدالمحسن (4 months), not by anyone reading the statement.
    _paid = [l for l in kept if l.get("income") is not None]
    out["income_airbnb"] = _fnum(sum((_D(l["income"]) for l in _paid
                                      if (l.get("channel") or "") == "airbnb"), Decimal(0)))
    out["income_direct"] = _fnum(sum((_D(l["income"]) for l in _paid
                                      if (l.get("channel") or "") != "airbnb"), Decimal(0)))
    out["extras"] = _fnum(sum((_D(l.get("extras") or 0) for l in _paid), Decimal(0)))
    out["ouja_fee"] = _fnum(fee)
    out["expenses"] = _fnum(exp_total)
    out["cleaning"] = {"type": cl_now.get("type", "ours"), "amount": _fnum(cl_month_amt or 0),
                       "base_amount": _fnum(cl_now.get("amount") or 0),
                       "overridden": mkey in _cl_ov,
                       "months": 1, "total": _fnum(cleaning_total),
                       "prorated_days": (covered if covered < days_in_month else None)}
    out["owner_net"] = _fnum(income + manual - fee - exp_total - cleaning_total)
    out["management_pct"] = (terms_on(apt, win_s if win_e >= win_s else start, rec).get("mgmt_pct"))
    out["contract_window"] = {"from": (cf.isoformat() if cf else None),
                              "to": (ct.isoformat() if ct else None)}
    # excluded-summary stays honest after the re-derivation
    es = dict(out.get("excluded_summary") or {})
    es["outside_contract"] = len(excluded)
    es["outside_contract_value"] = _fnum(sum((_D(x.get("reference_total") or 0) for x in excluded), Decimal(0)))
    out["excluded_summary"] = es
    return out, footnotes


# ====================== v2.2 slice 1: the month must never lie ======================

def _partial_net(owner, mkey, ndays):
    """Owner aggregate net for the FIRST `ndays` days of a month — the
    same-days-of-last-month comparison the editor header shows. Runs the real
    statement engine over the partial window (booking-driven; month-keyed
    manual adjusts don't apply to partial windows — it's a labeled pace
    indicator, not a statement).
    v2.2.2: memoized in bot.py's _owner_partial_cache (busted with the month) —
    uncached this was a fresh Hostaway window pull on EVERY editor load (~29s)."""
    B = _B()
    ck = (owner, mkey, int(ndays))
    pc = getattr(B, "_owner_partial_cache", None)
    if pc is not None:
        hit = pc.get(ck)
        if hit and (time.time() - hit[1] < 6 * 3600):
            return hit[0]
    start, end = B._month_bounds(mkey)
    pend = min(end, start + timedelta(days=max(1, int(ndays)) - 1))
    items = B._finance_collect_items("owner", [], [owner], start, pend)
    rep = items[0]["report"] if items else None
    val = _fnum(rep.get("owner_net") or 0) if rep is not None else None
    if pc is not None and val is not None:
        pc[ck] = (val, time.time())
        if len(pc) > 300:
            for k in sorted(pc, key=lambda k: pc[k][1])[:100]:
                pc.pop(k, None)
    return val


def month_meta(owner, mkey, rep=None, with_compare=False):
    """Honest month-state block rendered everywhere a month shows (v2.2 slice 1):
    state (running/closed/future), day counters, net-so-far, a LABELED linear
    pace projection, and (editor only) first-N-days vs last month."""
    B = _B()
    today = datetime.now(B.TZ).date()
    cur = today.isoformat()[:7]
    start, end = B._month_bounds(mkey)
    days_in_month = (end - start).days + 1
    state = "running" if mkey == cur else ("closed" if mkey < cur else "future")
    out = {"month": mkey, "state": state, "days_in_month": days_in_month,
           "day_of_month": today.day if state == "running" else None}
    if state != "running":
        return out
    elapsed = max(1, today.day)
    net = float((rep or {}).get("owner_net") or 0) if rep is not None else None
    if net is not None:
        out["net_so_far"] = _fnum(net)
        out["projection"] = int(round(net / elapsed * days_in_month))
        out["projection_basis"] = "linear"
    if with_compare and owner:
        try:
            pm = api._prior_month(mkey)
            prev_partial = _partial_net(owner, pm, elapsed)
            if prev_partial is not None:
                out["compare"] = {"prev_month": pm, "days": elapsed,
                                  "prev_net": prev_partial,
                                  "cur_net": (_fnum(net) if net is not None else None)}
        except Exception as e:
            print("month_meta compare error:", e)
    return out


# ---- v2.2 slice 2: تطابق الكشوف — per-unit subtotals vs the aggregate + hard fixtures ----

TIEOUT_FIXTURES = [
    {
        # أبو فهد الخطيب — May 2026: his 8 system-generated per-apartment PDFs
        # (01-05 → 31-05) sum to net 48,115.05 exactly. THE regression anchor
        # for the whole money engine — never force totals to match it; a diff
        # means a rule changed and must be explained per unit.
        "owner_keys": ["فهد", "خطيب"],
        "month": "2026-05",
        "totals": {"net": 48115.05, "income": 59016.76, "fees": 9962.90,
                   "expenses": 938.81, "manual_income": 3667.30},
        "units": {"101a": 7674.62, "101b": 6864.72, "102a": 6999.52, "102b": 6441.11,
                  "201b": 5272.71, "201a": 5302.78, "202a": 4894.07, "202b": 4665.52},
    },
]


def _tieout_fixture(owner, mkey):
    for f in TIEOUT_FIXTURES:
        if f["month"] == mkey and all(k in (owner or "") for k in f["owner_keys"]):
            return f
    return None


def statement_tieout(owner, mkey):
    """Per-apartment subtotals (the SAME per-unit engine the apartment PDFs
    render) vs the live aggregate statement, plus the hard-number PDF fixture
    when one exists for (owner, month). Read-only; mismatches are SHOWN per
    unit with their deltas — totals are never forced."""
    B = _B()
    recs = [r for r in api._registry_rows() if (r.get("owner") or "").strip() == (owner or "").strip()]
    if not recs:
        return {"error": "owner_not_in_registry", "owner": owner}
    fixture = _tieout_fixture(owner, mkey)
    fx_units = {B._owner_key(k): v for k, v in ((fixture or {}).get("units") or {}).items()}
    units = []
    sums = {"income": Decimal(0), "fees": Decimal(0), "expenses": Decimal(0),
            "cleaning": Decimal(0), "net": Decimal(0), "manual_income": Decimal(0)}
    for rec in recs:
        apt = rec.get("apartment") or ""
        rep, _fn = unit_statement(rec, mkey)
        if rep is None:
            units.append({"apartment": apt, "lid": None, "error": "no_report",
                          "fixture_net": fx_units.get(B._owner_key(apt)),
                          "delta_vs_fixture": None})
            continue
        row = {"apartment": apt, "lid": rep.get("lid"),
               "income": rep.get("total_income"), "fees": rep.get("ouja_fee"),
               "expenses": rep.get("expenses"),
               "cleaning": (rep.get("cleaning") or {}).get("total") or 0,
               "manual_income": rep.get("manual_income") or 0,
               "net": rep.get("owner_net")}
        for k in ("income", "fees", "expenses", "cleaning", "net", "manual_income"):
            sums[k] += _D(row[k])
        fxn = fx_units.get(B._owner_key(apt))
        row["fixture_net"] = fxn
        row["delta_vs_fixture"] = (_fnum(_D(row["net"]) - _D(fxn)) if fxn is not None else None)
        units.append(row)
    agg = compute_owner_statement(owner, mkey)             # WITH the editor's saved edits
    agg_t = {"income": (agg or {}).get("total_income"), "fees": (agg or {}).get("ouja_fee"),
             "expenses": (agg or {}).get("expenses"),
             "cleaning": ((agg or {}).get("cleaning") or {}).get("total") or 0,
             "net": (agg or {}).get("owner_net"),
             "adjustments": (agg or {}).get("adjustments_total") or 0,
             "has_manual_edits": bool((agg or {}).get("has_manual_edits"))}
    sums_f = {k: _fnum(v) for k, v in sums.items()}
    # aggregate − sum(units): nonzero ONLY when owner-level editor decisions
    # (excludes / includes / manual lines / adjustments) moved the totals.
    agg_minus_units = {k: (_fnum(_D(agg_t.get(k)) - _D(sums_f.get(k)))
                           if agg_t.get(k) is not None else None)
                       for k in ("income", "fees", "expenses", "cleaning", "net")}
    out = {"ok": True, "owner": owner, "month": mkey,
           "generated_at": datetime.now(B.TZ).isoformat(timespec="seconds"),
           "units": units, "units_sum": sums_f,
           "aggregate": agg_t, "agg_minus_units": agg_minus_units,
           "balanced": all((v is None or abs(v) < 0.02) for v in agg_minus_units.values()),
           "month_meta": month_meta(owner, mkey)}
    if fixture:
        mism = [u["apartment"] for u in units
                if u.get("delta_vs_fixture") is not None and abs(u["delta_vs_fixture"]) >= 0.02]
        missing = [k for k in ((fixture.get("units") or {}))
                   if B._owner_key(k) not in {B._owner_key(u["apartment"]) for u in units}]
        d_units = _fnum(_D(sums_f["net"]) - _D(fixture["totals"]["net"]))
        out["fixture"] = {
            "month": fixture["month"], "totals": fixture["totals"],
            "delta_net_units_sum": d_units,
            "delta_net_aggregate": (_fnum(_D(agg_t["net"]) - _D(fixture["totals"]["net"]))
                                    if agg_t.get("net") is not None else None),
            "unit_mismatches": mism, "fixture_units_missing": missing,
            "passed": (abs(d_units) < 0.02 and not mism and not missing),
        }
    return out


# ====================== Slice 2: statement store + editor engine ======================

_STMT_FILE = "owner_statements.json"
_stmt_cache = {"v": None}


def _stmt_store():
    if _stmt_cache["v"] is None:
        _stmt_cache["v"] = _B()._load_json(_STMT_FILE, {}) or {}
        # Decisions taken before the per-unit mirror existed reach their
        # apartment on the first read after boot — see backfill_expense_mirrors.
        backfill_expense_mirrors()
    return _stmt_cache["v"]


def _stmt_save():
    _B()._save_json(_STMT_FILE, _stmt_cache["v"])


def _stmt_key(owner, mkey):
    return (owner or "") + "|" + (mkey or "")


def stmt_rec(owner, mkey, create=False):
    st = _stmt_store()
    k = _stmt_key(owner, mkey)
    rec = st.get(k)
    if rec is None and create:
        rec = {"owner": owner, "month": mkey, "status": "draft",
               "edits": {"resv": {}, "exp_overrides": {}, "exp_manual": [], "adjustments": []},
               "audit": [], "published": None, "status_log": []}
        st[k] = rec
    return rec


def stmt_audit_add(rec, actor, action, target, before, after, reason=""):
    rec.setdefault("audit", []).append({
        "at": datetime.now(_B().TZ).isoformat(timespec="seconds"),
        "by": (actor or "")[:60], "action": action, "target": str(target)[:120],
        "before": before, "after": after, "reason": (reason or "")[:300]})
    if len(rec["audit"]) > 400:
        del rec["audit"][:len(rec["audit"]) - 400]


def _expense_lid(eid, body=None):
    """The listing an expense belongs to. The ledger is the authority; the
    editor's row may pass one as a hint for a line the ledger no longer holds."""
    try:
        rec = (getattr(_B(), "_expenses", None) or {}).get(str(eid)) or {}
        lid = rec.get("listing_id")
        if lid not in (None, ""):
            return int(lid)
    except (TypeError, ValueError):
        pass
    try:
        v = (body or {}).get("lid")
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _unit_adjust(lid, mkey):
    """This unit's per-month adjust record, created on demand. THE store every
    per-apartment surface reads (build_owner_report → _finance_apply_adjust)."""
    B = _B()
    start, end = B._month_bounds(mkey)
    ak = B._finance_adjust_key(lid, start.isoformat(), end.isoformat())
    adj = B._finance_adjust.get(ak) or {}
    for kdef, vdef in (("expense_overrides", {}), ("extra_lines", []),
                       ("line_overrides", {}), ("comment", "")):
        adj.setdefault(kdef, vdef)
    B._finance_adjust[ak] = adj
    return adj


def _mirror_expense_edit(mkey, eid, body, delete=False, fields=None):
    """Carry an editor decision about ONE expense down to its apartment.

    `_apply_stmt_edits` runs AFTER `_finance_aggregate`, so on its own it patches
    the owner TOTAL and nothing else: the per-apartment breakdown, the unit tab
    subtotal and the apartment PDF (build_owner_report) all kept showing the
    deleted line (owner-reported 2026-08-03). Manual ADDs were routed into the
    per-lid store in 2026-07-05 for exactly this reason — deletes and amount
    edits now take the same road, so every surface tells one story.

    Returns True when the decision reached a unit. An expense we cannot attribute
    (no listing on the ledger row) still applies at owner level — never a crash.
    """
    lid = _expense_lid(eid, body)
    if lid is None:
        return False
    try:
        adj = _unit_adjust(lid, mkey)
        if delete:
            adj["expense_overrides"][str(eid)] = None      # None = drop the line
        else:
            ov = dict(adj["line_overrides"].get("exp:" + str(eid)) or {})
            ov.update({k: v for k, v in (fields or {}).items() if v not in (None, "")})
            adj["line_overrides"]["exp:" + str(eid)] = ov
        _B().persist_state()
        return True
    except Exception as ex:
        print("expense edit mirror failed for %s: %s" % (eid, ex))
        return False


def backfill_expense_mirrors():
    """Give expense decisions taken BEFORE the mirror shipped the same road as new
    ones. Mirroring on WRITE only helps the next delete — every expense the
    accountant had already deleted still sat in the apartment report and the unit
    PDF (owner-reported «ما انحلت المشكلة», 2026-08-03). This walks the saved
    statements once per boot and mirrors each exp_override into the per-lid store.

    Idempotent by construction: writing the SAME key with the same value twice is
    a no-op, and money is never added — only a line is dropped or its amount
    restated. Rows the ledger can no longer attribute are skipped (they cannot
    reach a unit report anyway). Never raises: a statement store we cannot read
    must not take the whole finance page down.
    """
    done = 0
    try:
        # _stmt_store() loads on demand and re-enters here with the cache already
        # set, so this is safe from either direction (boot or first statement read)
        for key, rec in list((_stmt_store() or {}).items()):
            mkey = (rec or {}).get("month") or (key.split("|", 1)[-1] if "|" in key else "")
            if not mkey:
                continue
            for eid, ov in list((((rec or {}).get("edits") or {}).get("exp_overrides") or {}).items()):
                if not isinstance(ov, dict):
                    continue
                if ov.get("deleted"):
                    done += 1 if _mirror_expense_edit(mkey, eid, None, delete=True) else 0
                elif any(ov.get(f) not in (None, "") for f in ("amount", "date", "description")):
                    done += 1 if _mirror_expense_edit(
                        mkey, eid, None,
                        fields={"amount": ov.get("amount"), "date": ov.get("date"),
                                "description": ov.get("description"),
                                "edit_reason": ov.get("reason")}) else 0
    except Exception as ex:
        print("expense mirror backfill failed:", ex)
    if done:
        print("expense mirror backfill: %d decision(s) pushed down to their apartment" % done)
    return done


def _apply_stmt_edits(agg, edits):
    """Apply the editor's decisions to a computed statement. Pure recompute from
    the per-line mgmt stamps — totals always equal the visible rows."""
    resv_e = edits.get("resv") or {}
    kept, manual_excluded = [], []
    income = Decimal(0)
    fee = Decimal(0)
    for l in agg.get("resv_lines") or []:
        e = resv_e.get(str(l.get("id")))
        if e and e.get("action") == "exclude":
            x = dict(l)
            x["manual_excluded"] = True
            x["exclude_reason"] = "manual_exclude"
            x["edit_reason"] = e.get("reason") or ""
            x["reference_total"] = l.get("income") if l.get("income") is not None else l.get("reference_total")
            x["income"] = None
            x["needs_review"] = False
            manual_excluded.append(x)
            continue
        if e and e.get("action") == "include":
            l = dict(l)
            if l.get("income") is None and e.get("amount") not in (None, ""):
                l["income"] = round(float(e.get("amount") or 0), 2)
            l["manual_included"] = True
            l["edit_reason"] = e.get("reason") or ""
            l["needs_review"] = False
            l.pop("exclude_reason", None)
        if l.get("income") is not None:
            pct = _D(l.get("mgmt_pct_applied") or agg.get("management_pct") or 0)
            money = _D(l["income"]) + _D(l.get("extras") or 0)
            income += money
            fee += money * pct / Decimal(100)
        kept.append(l)
    # force-includes of footer lines (refunded / unpaid): an explicit amount +
    # reason promotes the row into income at its stamped rate
    new_footers = {}
    for fk in ("refunded_lines", "unpaid_lines"):
        remaining = []
        for l in agg.get(fk) or []:
            e = resv_e.get(str(l.get("id")))
            if e and e.get("action") == "include" and e.get("amount") not in (None, ""):
                nl = dict(l)
                nl["income"] = round(float(e["amount"]), 2)
                nl["manual_included"] = True
                nl["edit_reason"] = e.get("reason") or ""
                pct = _D(nl.get("mgmt_pct_applied") or agg.get("management_pct") or 0)
                income += _D(nl["income"])
                fee += _D(nl["income"]) * pct / Decimal(100)
                kept.append(nl)
                continue
            remaining.append(l)
        new_footers[fk] = remaining
    exp_e = edits.get("exp_overrides") or {}
    exps, deleted_exps = [], []
    exp_total = Decimal(0)
    for x in agg.get("exp_lines") or []:
        o = exp_e.get(str(x.get("id")))
        if o:
            if o.get("deleted"):
                deleted_exps.append({**x, "edit_reason": o.get("reason") or ""})
                continue
            x = dict(x)
            for f in ("amount", "date", "description"):
                if o.get(f) not in (None, ""):
                    x.setdefault("original_" + f, x.get(f))
                    x[f] = o[f]
            x["edited"] = True
            x["edit_reason"] = o.get("reason") or ""
        exps.append(x)
        exp_total += _D(x.get("amount"))
    for m in edits.get("exp_manual") or []:
        exps.append({"id": m.get("id"), "amount": m.get("amount"), "date": m.get("date"),
                     "description": m.get("description") or m.get("label") or "",
                     "category": "يدوي", "manual": True, "edit_reason": m.get("reason") or ""})
        exp_total += _D(m.get("amount"))
    adjustments = list(edits.get("adjustments") or [])
    adj_total = sum((_D(a.get("amount")) for a in adjustments), Decimal(0))
    manual_income = _D(agg.get("manual_income") or 0)
    cleaning = _D((agg.get("cleaning") or {}).get("total") or 0)
    agg = dict(agg)
    agg["resv_lines"] = kept
    agg["refunded_lines"] = new_footers.get("refunded_lines", agg.get("refunded_lines") or [])
    agg["unpaid_lines"] = new_footers.get("unpaid_lines", agg.get("unpaid_lines") or [])
    agg["manual_excluded_lines"] = manual_excluded
    agg["exp_lines"] = exps
    agg["deleted_expense_lines"] = deleted_exps
    agg["adjust_lines"] = adjustments
    agg["expenses"] = _fnum(exp_total)
    agg["total_income"] = _fnum(income + manual_income)
    # …and the CHANNEL SPLIT with it. It used to keep the pre-edit numbers, so a
    # force-included booking landed in the total while «تفصيل الدخل» still showed
    # the old figure — the same page contradicting itself by exactly the included
    # amount, which reads as «الحجز ما ظهر» (owner-reported 2026-08-04: ثامر ال
    # جربوع 2026-07, total 8,860.88 vs split 8,424.54, diff = 436.34).
    # Non-airbnb income folds into «مباشر»: a forced include must be visible
    # somewhere, and 'other' channels carry no confirmed payout rule of their own.
    paid_kept = [l for l in kept if l.get("income") is not None]
    agg["income_airbnb"] = _fnum(sum((_D(l["income"]) for l in paid_kept
                                      if (l.get("channel") or "") == "airbnb"), Decimal(0)))
    agg["income_direct"] = _fnum(sum((_D(l["income"]) for l in paid_kept
                                      if (l.get("channel") or "") != "airbnb"), Decimal(0)))
    agg["extras"] = _fnum(sum((_D(l.get("extras") or 0) for l in paid_kept), Decimal(0)))
    agg["ouja_fee"] = _fnum(fee)
    agg["adjustments_total"] = _fnum(adj_total)
    agg["owner_net"] = _fnum(income + manual_income - fee - exp_total - cleaning + adj_total)
    agg["has_manual_edits"] = bool(resv_e or exp_e or edits.get("exp_manual") or adjustments)
    es = dict(agg.get("excluded_summary") or {})
    es["manual_excluded"] = len(manual_excluded)
    es["manual_excluded_value"] = _fnum(sum((_D(x.get("reference_total") or 0) for x in manual_excluded), Decimal(0)))
    agg["excluded_summary"] = es
    return _rebuild_unit_parts(agg)


def _rebuild_unit_parts(agg):
    """Re-derive the per-apartment breakdown from the EDITED lines.

    `bot._finance_aggregate` builds `apartments[]` from the untouched per-unit
    reports, and `_apply_stmt_edits` runs after it — so a booking the accountant
    force-included (or excluded) moved the owner total but left the apartment
    exactly as the raw engine saw it. That stale row is what the apartment PDF
    prints (owner-reported 2026-08-04: 202A printed 5,839.38 while the owner
    total already carried 6,350.50).

    Every line knows its unit, so the breakdown is rebuilt from them. Lines with
    no lid (owner-level manual entries and adjustments) stay OUT of the units on
    purpose — they are unattributable and already footnoted; the unit subtotals
    then legitimately sum to less than the owner total.
    """
    parts = agg.get("apartments") or []
    if not parts:
        return agg
    out, idx = [], {}
    for p in parts:
        q = dict(p)
        q["total_income"] = Decimal(0)
        q["ouja_fee"] = Decimal(0)
        q["expenses"] = Decimal(0)
        out.append(q)
        idx[str(q.get("lid"))] = q
    default_pct = _D(agg.get("management_pct") or 0)
    for l in agg.get("resv_lines") or []:
        q = idx.get(str(l.get("lid")))
        if q is None or l.get("income") is None:
            continue
        money = _D(l["income"]) + _D(l.get("extras") or 0)
        pct = _D(l.get("mgmt_pct_applied")) if l.get("mgmt_pct_applied") is not None else default_pct
        q["total_income"] += money
        q["ouja_fee"] += money * pct / Decimal(100)
    for m in agg.get("manual_income_lines") or []:      # fee-exempt by design
        q = idx.get(str(m.get("lid")))
        if q is not None:
            q["total_income"] += _D(m.get("amount"))
    for x in agg.get("exp_lines") or []:
        q = idx.get(str(x.get("lid")))
        if q is not None:
            q["expenses"] += _D(x.get("amount"))
    for q in out:
        q["total_income"] = _fnum(q["total_income"])
        q["ouja_fee"] = _fnum(q["ouja_fee"])
        q["expenses"] = _fnum(q["expenses"])
        q["owner_net"] = _fnum(_D(q["total_income"]) - _D(q["ouja_fee"])
                               - _D(q["expenses"]) - _D(q.get("cleaning") or 0))
    agg["apartments"] = out
    return agg


def unit_slice(rep, lid):
    """One apartment's view of an EDITED monthly statement, shaped like a unit
    report so the range report / apartment PDF can sum it. Used when an apartment
    filter is applied to a multi-unit owner — re-running the raw engine there is
    what silently dropped every editor decision."""
    if rep is None or lid is None:
        return None
    part = next((p for p in (rep.get("apartments") or [])
                 if str(p.get("lid")) == str(lid)), None)
    if part is None:
        return None
    same = lambda l: str(l.get("lid") or "") == str(lid)
    resv = [l for l in (rep.get("resv_lines") or []) if same(l)]
    paid = [l for l in resv if l.get("income") is not None]
    mil = [m for m in (rep.get("manual_income_lines") or []) if same(m)]
    cl = rep.get("cleaning") or {}
    return {
        "currency": "SAR", "owner": rep.get("owner"),
        "apartment": part.get("apartment"), "lid": part.get("lid"),
        "management_pct": rep.get("management_pct"),
        "income_airbnb": _fnum(sum((_D(l["income"]) for l in paid
                                    if (l.get("channel") or "") == "airbnb"), Decimal(0))),
        "income_direct": _fnum(sum((_D(l["income"]) for l in paid
                                    if (l.get("channel") or "") != "airbnb"), Decimal(0))),
        "extras": _fnum(sum((_D(l.get("extras") or 0) for l in paid), Decimal(0))),
        "manual_income": _fnum(sum((_D(m.get("amount")) for m in mil), Decimal(0))),
        "manual_income_lines": mil,
        "total_income": part.get("total_income"), "ouja_fee": part.get("ouja_fee"),
        "expenses": part.get("expenses"), "owner_net": part.get("owner_net"),
        "cleaning": {"type": cl.get("type"), "amount": cl.get("amount"),
                     "total": part.get("cleaning") or 0, "cleans": None, "months": 1},
        "apartments": [part],
        "resv_lines": resv,
        "exp_lines": [x for x in (rep.get("exp_lines") or []) if same(x)],
        "unpaid_lines": [l for l in (rep.get("unpaid_lines") or []) if same(l)],
        "refunded_lines": [l for l in (rep.get("refunded_lines") or []) if same(l)],
        "manual_excluded_lines": [l for l in (rep.get("manual_excluded_lines") or []) if same(l)],
        "adjust_lines": [], "adjustments_total": 0.0,
        "excluded_summary": rep.get("excluded_summary") or {},
        "has_manual_edits": rep.get("has_manual_edits"),
        "reconciliation": rep.get("reconciliation") or {"balanced": True},
        "footnotes": rep.get("footnotes") or [],
    }


def statement_health(owner, mkey, rep=None):
    """Every way a statement can silently disagree with itself, checked in one
    place. Born 2026-08-04 after four separate «الرقم على الشاشة مو نفسه في
    التقرير» reports: each one was a surface reading a value the editor's
    decisions had never reached. Rather than wait for the fifth, assert the
    invariants and let anyone sweep every owner on demand.

    Returns {owner, month, ok, problems[]} — a problem names the surface that
    would lie, in Arabic, with the exact gap.
    """
    if rep is None:
        rep = compute_owner_statement(owner, mkey)
    if rep is None:
        return {"owner": owner, "month": mkey, "ok": True, "skipped": "not_in_registry",
                "problems": []}
    P = []
    add = lambda k, ar, gap=None: P.append(
        {"kind": k, "text_ar": ar, "gap": (_fnum(gap) if gap is not None else None)})
    T = lambda k: _D(rep.get(k) or 0)
    # Each unit is rounded to halalas before being summed, so a multi-unit owner
    # drifts a halala or two by arithmetic, not by losing money. Alarming on that
    # would bury the real findings — allow the drift, never more.
    tol = Decimal("0.05") + Decimal("0.01") * len(rep.get("apartments") or [])
    off = lambda a, b: abs(_D(a) - _D(b)) > tol

    # 1) «تفصيل الدخل» must add up to «إجمالي الدخل» — the PDF prints both.
    split = T("income_airbnb") + T("income_direct") + T("extras") + T("manual_income")
    if off(split, T("total_income")):
        add("income_split", "تفصيل الدخل ما يساوي إجمالي الدخل",
            T("total_income") - split)

    # 2) The bottom line must follow from the rows above it.
    net = (T("total_income") - T("ouja_fee") - T("expenses")
           - _D((rep.get("cleaning") or {}).get("total") or 0) + T("adjustments_total"))
    if off(net, T("owner_net")):
        add("net_math", "صافي المالك ما يطلع من الصفوف اللي فوقه", T("owner_net") - net)

    # 3) Unit subtotals may only fall short by lines that carry no apartment.
    parts = rep.get("apartments") or []
    if parts:
        unit_sum = sum((_D(p.get("total_income") or 0) for p in parts), Decimal(0))
        homeless = sum((_D(m.get("amount")) for m in (rep.get("manual_income_lines") or [])
                        if not m.get("lid")), Decimal(0))
        if off(unit_sum + homeless, T("total_income")):
            add("unit_rollup", "مجموع الشقق ما يساوي إجمالي المالك",
                T("total_income") - unit_sum - homeless)
        unit_exp = sum((_D(p.get("expenses") or 0) for p in parts), Decimal(0))
        homeless_exp = sum((_D(x.get("amount")) for x in (rep.get("exp_lines") or [])
                            if not x.get("lid")), Decimal(0))
        if off(unit_exp + homeless_exp, T("expenses")):
            add("unit_expenses", "مجموع مصاريف الشقق ما يساوي مصاريف المالك",
                T("expenses") - unit_exp - homeless_exp)

    # 4) A booking the accountant force-included must actually be in the money.
    for l in rep.get("resv_lines") or []:
        if l.get("manual_included") and l.get("income") is None:
            add("included_without_money",
                "حجز مُدرج يدويًا بدون مبلغ: " + str(l.get("guest") or l.get("id")))
    for fk in ("refunded_lines", "unpaid_lines"):
        for l in rep.get(fk) or []:
            if l.get("manual_included"):
                add("included_still_excluded",
                    "حجز مُدرج يدويًا لا يزال في «حركات بدون فلوس»: "
                    + str(l.get("guest") or l.get("id")))

    # 5) An expense must never be drawn as an excluded BOOKING row.
    for l in rep.get("contract_excluded_lines") or []:
        if l.get("kind") == "expense":
            add("expense_as_booking", "مصروف معروض كأنه حجز مستبعد: " + str(l.get("id")))

    # 6) A deleted expense must be gone from the apartment, not just the total.
    edits = ((stmt_rec(owner, mkey) or {}).get("edits") or {})
    live_ids = {str(x.get("id")) for x in (rep.get("exp_lines") or [])}
    for eid, ov in (edits.get("exp_overrides") or {}).items():
        if isinstance(ov, dict) and ov.get("deleted") and str(eid) in live_ids:
            add("deleted_expense_alive", "مصروف محذوف لا يزال محسوبًا: " + str(eid))

    # 7) The owner's «التقرير النهائي» is the published snapshot — say when it lags.
    pub = (stmt_rec(owner, mkey) or {}).get("published") or {}
    snap = pub.get("snapshot") or {}
    if snap and any(_fnum(snap.get(k)) != _fnum(rep.get(k))
                    for k in ("owner_net", "total_income", "expenses", "ouja_fee")):
        add("published_stale",
            "المنشور للمالك (نسخة %s) أقدم من الأرقام الحالية" % pub.get("version"),
            _D(rep.get("owner_net") or 0) - _D(snap.get("owner_net") or 0))

    return {"owner": owner, "month": mkey, "ok": not P, "problems": P,
            "owner_net": rep.get("owner_net"), "total_income": rep.get("total_income")}


def audit_all(months=None, owner=None):
    """Sweep every owner (or one) across the given months and report every
    statement that disagrees with itself. `months` defaults to the last 6."""
    B = _B()
    if not months:
        cur = datetime.now(B.TZ).date().isoformat()[:7]
        months = list(reversed(_prev_months(cur, 5) + [cur]))
    owners = [owner] if owner else sorted({(r.get("owner") or "").strip()
                                           for r in api._registry_rows()
                                           if (r.get("owner") or "").strip()})
    rows, bad = [], 0
    for own in owners:
        for mk in months:
            try:
                h = statement_health(own, mk)
            except Exception as ex:
                h = {"owner": own, "month": mk, "ok": False,
                     "problems": [{"kind": "crash", "text_ar": "تعذّر حساب الكشف: " + str(ex)[:120]}]}
            if not h.get("ok"):
                bad += 1
                rows.append(h)
    return {"ok": True, "checked_owners": len(owners), "months": months,
            "statements_with_problems": bad, "rows": rows}


def _build_explain(agg):
    """«ليش هالرقم؟» — the exact rows + rule behind every total. Server-built so
    the editor, the PDF and any future surface tell the SAME story."""
    inc_lines = [{"id": l.get("id"), "guest": l.get("guest"), "apartment": l.get("apartment"),
                  "checkin": l.get("checkin"), "amount": l.get("income"),
                  "pct": l.get("mgmt_pct_applied"),
                  "manual_included": bool(l.get("manual_included"))}
                 for l in (agg.get("resv_lines") or []) if l.get("income") is not None]
    fee_groups = {}
    for l in inc_lines:
        p = l.get("pct") if l.get("pct") is not None else agg.get("management_pct")
        g = fee_groups.setdefault(str(p), {"pct": p, "base": Decimal(0)})
        g["base"] += _D(l["amount"])
    fees = [{"pct": g["pct"], "base": _fnum(g["base"]),
             "fee": _fnum(g["base"] * _D(g["pct"] or 0) / Decimal(100))}
            for g in fee_groups.values()]
    cl = agg.get("cleaning") or {}
    return {
        "income": {"lines": inc_lines, "manual_income": agg.get("manual_income") or 0,
                   "total": agg.get("total_income"),
                   "rule_ar": "مجموع المبالغ المستلمة فعليًا للحجوزات المحسوبة (الأساس النقدي) + الإيراد اليدوي",
                   "rule_en": "Sum of money actually received for included bookings (paid basis) + manual income"},
        "fees": {"groups": fees, "total": agg.get("ouja_fee"),
                 "rule_ar": "لكل حجز: (الدخل + الإضافات) × نسبة الإدارة السارية بتاريخ دخوله",
                 "rule_en": "Per booking: (income + extras) × the management % effective on its check-in date"},
        "expenses": {"lines": [{"id": x.get("id"), "date": x.get("date"), "amount": x.get("amount"),
                                "description": x.get("description") or x.get("category") or "",
                                "manual": bool(x.get("manual")), "edited": bool(x.get("edited"))}
                               for x in (agg.get("exp_lines") or [])],
                     "total": agg.get("expenses"),
                     "rule_ar": "المصاريف المتحقّقة على وحدات المالك داخل الفترة (+ اليدوية)",
                     "rule_en": "Verified expenses on the owner's units inside the period (+ manual lines)"},
        "cleaning": {"type": cl.get("type"), "amount": cl.get("amount"), "total": cl.get("total"),
                     "prorated_days": cl.get("prorated_days"),
                     "rule_ar": "مبلغ شهري ثابت إذا كان على المالك — يُحسب نسبيًا لو العقد جزئي",
                     "rule_en": "Flat monthly amount when owner-paid — pro-rated for partial contracts"},
        "adjustments": {"lines": agg.get("adjust_lines") or [], "total": agg.get("adjustments_total") or 0,
                        "rule_ar": "تسويات يدوية صريحة (± مبلغ + سبب) خارج النموذج",
                        "rule_en": "Explicit manual adjustments (± amount + reason) outside the model"},
        "net": {"total": agg.get("owner_net"),
                "values": {"income": agg.get("total_income"), "fees": agg.get("ouja_fee"),
                           "expenses": agg.get("expenses"),
                           "cleaning": cl.get("total") or 0,
                           "adjustments": agg.get("adjustments_total") or 0},
                "rule_ar": "الصافي = الدخل − رسوم الإدارة − المصاريف − النظافة ± التسويات",
                "rule_en": "Net = income − management fee − expenses − cleaning ± adjustments"},
    }


def compute_owner_statement(owner, mkey, apply_edits=True, settings=None):
    """The v2.1 owner-month statement: per-unit effective-dated reports
    aggregated the same way bot.py aggregates (shape-compatible superset),
    then the editor's saved decisions applied on top.
    `settings` = a per-compute override of bot.py's FINANCE_DEFAULTS (see
    unit_statement). Defaults to off. It IS publishable, but only through
    statement_publish's explicit `basis` argument, which records what it froze —
    a screen previewing an alternate basis can never publish itself.
    Returns None when the owner has no registry units (caller falls back)."""
    B = _B()
    start, end = B._month_bounds(mkey)
    recs = [r for r in api._registry_rows() if (r.get("owner") or "").strip() == (owner or "").strip()]
    if not recs:
        return None
    srec = stmt_rec(owner, mkey)
    edits = (srec or {}).get("edits") or {}
    has_edits = bool(edits.get("resv") or edits.get("exp_overrides")
                     or edits.get("exp_manual") or edits.get("adjustments"))
    reps, foots = [], []
    for rec in recs:
        rep, fn = unit_statement(rec, mkey, force_rederive=has_edits, settings=settings)
        if rep is not None:
            reps.append(rep)
            foots.extend(fn)
    if not reps:
        return None
    agg = B._finance_aggregate(reps, owner, start, end)
    if any(r.get("degraded") for r in reps):
        # M3: a unit fell back to the truncated cache — the totals are NOT
        # trustworthy. Say so loudly; publish is refused while degraded.
        agg["degraded"] = True
        foots.append({"kind": "degraded",
                      "text_ar": "⚠️ بيانات غير متاحة مؤقتاً — ما قدرنا نسحب الحجوزات من Hostaway، الأرقام ناقصة",
                      "text_en": "⚠️ Data temporarily unavailable — Hostaway pull failed, numbers are incomplete"})
    # carry the v2.1 extras through the aggregate
    # Bookings and expenses keep SEPARATE buckets. Merging them made the editor
    # render an excluded expense with the reservation row renderer — a ghost row
    # with no guest, no dates and an «احسبه» button that could never work.
    contract_excluded, contract_excluded_exp = [], []
    for r in reps:
        contract_excluded.extend(r.get("contract_excluded_lines") or [])
        contract_excluded_exp.extend(r.get("contract_excluded_expenses") or [])
    if contract_excluded or contract_excluded_exp:
        es = dict(agg.get("excluded_summary") or {})
        es["outside_contract"] = len(contract_excluded) + len(contract_excluded_exp)
        es["outside_contract_value"] = _fnum(
            sum((_D(x.get("reference_total") or 0) for x in contract_excluded), Decimal(0))
            + sum((_D(x.get("amount") or 0) for x in contract_excluded_exp), Decimal(0)))
        agg["excluded_summary"] = es
        agg["contract_excluded_lines"] = contract_excluded
        agg["contract_excluded_expenses"] = contract_excluded_exp
    if foots:
        agg["footnotes"] = foots
    op = (_terms_store()["owners"] or {}).get(owner) or {}
    if op:
        agg["owner_profile"] = {"phone": op.get("phone") or "", "active": op.get("active", True)}
    if apply_edits and has_edits:
        agg = _apply_stmt_edits(agg, edits)
    # Stamp the alternate basis so EVERY surface that renders this object (screen
    # banner, PDF header, income label) says so. _finance_aggregate drops
    # direct_fee_pct, so an unstamped 0% report would print «−3٪» over full-value
    # numbers — the one way this feature could lie.
    if settings is not None and settings.get("direct_fee_pct") is not None:
        agg["direct_fee_pct"] = float(settings["direct_fee_pct"])
        agg["no_direct_fee"] = (float(settings["direct_fee_pct"]) == 0.0)
    if srec:
        agg["statement_status"] = srec.get("status") or "draft"
        pub = srec.get("published") or {}
        if pub.get("version"):
            agg["published_version"] = pub["version"]
            agg["published_at"] = pub.get("at")
    return agg


def _iter_months(start, end):
    """Every calendar month touched by [start,end] → (slice_start, slice_end,
    mkey, is_whole_month). A whole month means the range fully covers it."""
    B = _B()
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        mk = "%04d-%02d" % (y, m)
        ms, me = B._month_bounds(mk)
        s, e = max(ms, start), min(me, end)
        out.append((s, e, mk, s == ms and e == me))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _aggregate_period(reports, owner, start, end):
    """Sum several monthly/slice reports into ONE range report. Totals come from
    each report's TOP-LEVEL values (so manual expenses / edits / adjustments the
    editor added are already included); the per-apartment breakdown is merged by
    apartment (Hostaway-level — owner-scoped manual lines live only in the totals,
    exactly like the monthly statement). Shape mirrors B._finance_aggregate."""
    R = lambda x: round(float(x or 0), 2)
    tot = lambda k: R(sum(float(r.get(k) or 0) for r in reports))
    cleaning_total = R(sum(float((r.get("cleaning") or {}).get("total") or 0) for r in reports))
    parts_by = {}
    for r in reports:
        aps = r.get("apartments") or [{
            "apartment": r.get("apartment"), "lid": r.get("lid"),
            "total_income": r.get("total_income"), "ouja_fee": r.get("ouja_fee"),
            "expenses": r.get("expenses"), "cleaning": (r.get("cleaning") or {}).get("total", 0),
            "owner_net": r.get("owner_net")}]
        for p in aps:
            key = (p.get("apartment"), p.get("lid"))
            acc = parts_by.setdefault(key, {"apartment": p.get("apartment"), "lid": p.get("lid"),
                  "total_income": 0.0, "ouja_fee": 0.0, "expenses": 0.0, "cleaning": 0.0, "owner_net": 0.0})
            for k in ("total_income", "ouja_fee", "expenses", "cleaning", "owner_net"):
                acc[k] = R(acc[k] + float(p.get(k) or 0))
    concat = lambda k: [x for r in reports for x in (r.get(k) or [])]
    all_lines = concat("resv_lines"); all_lines.sort(key=lambda l: l.get("checkin") or "")
    all_exp = concat("exp_lines"); all_exp.sort(key=lambda e: e.get("date") or "")
    exsum = {"needs_review": 0, "needs_review_reference": 0.0, "unpaid": 0,
             "unpaid_expected": 0.0, "refunded": 0, "reasons": {}}
    for r in reports:
        es = r.get("excluded_summary") or {}
        for k in ("needs_review", "unpaid", "refunded"):
            exsum[k] += int(es.get(k) or 0)
        for k in ("needs_review_reference", "unpaid_expected"):
            exsum[k] = R(exsum[k] + float(es.get(k) or 0))
        for k, v in (es.get("reasons") or {}).items():
            exsum["reasons"][k] = exsum["reasons"].get(k, 0) + v
    ti, fee = tot("total_income"), tot("ouja_fee")
    # derive the cleaning type/amount honestly (uniform → keep it; else "mixed") —
    # the PDF header + editor labels read cleaning.type (نواف الوهيبي label bug)
    _cl_types = {((r.get("cleaning") or {}).get("type") or "ours") for r in reports}
    cl_type = _cl_types.pop() if len(_cl_types) == 1 else "mixed"
    _cl_amts = {round(float((r.get("cleaning") or {}).get("amount") or 0), 2) for r in reports}
    cl_amount = _cl_amts.pop() if len(_cl_amts) == 1 else None
    out = {"currency": "SAR", "owner": owner,
           "management_pct": (round(fee / ti * 100, 1) if ti else None),
           "period": {"start": start.isoformat(), "end": end.isoformat(), "basis": "checkin"},
           "income_airbnb": tot("income_airbnb"), "income_direct": tot("income_direct"),
           "extras": tot("extras"), "manual_income": tot("manual_income"),
           "manual_income_lines": concat("manual_income_lines"),
           "total_income": ti, "ouja_fee": fee, "expenses": tot("expenses"),
           "cleaning": {"type": cl_type, "total": cleaning_total, "cleans": None,
                        "amount": cl_amount, "months": len(reports)},
           "owner_net": tot("owner_net"), "apartments": list(parts_by.values()),
           "resv_lines": all_lines, "exp_lines": all_exp,
           "unpaid_lines": concat("unpaid_lines"), "refunded_lines": concat("refunded_lines"),
           "adjust_lines": concat("adjust_lines"), "adjustments_total": tot("adjustments_total"),
           "excluded_summary": exsum, "n_apartments": len(parts_by),
           "reconciliation": {"balanced": all((r.get("reconciliation") or {}).get("balanced", True) for r in reports),
                              "missing_payout_ids": [], "needs_channel_rule_ids": [], "needs_base_ids": []}}
    foots = concat("footnotes")
    if foots:
        out["footnotes"] = foots
    if any(r.get("has_manual_edits") for r in reports):
        out["has_manual_edits"] = True
    cx = concat("contract_excluded_lines")
    if cx:
        out["contract_excluded_lines"] = cx
    return out


def compute_owner_range(owner, start, end, apt=None, settings=None):
    """Custom-range owner report = the SUM of the monthly statements across the
    window, so manual expenses / edits / adjustments entered in the monthly editor
    all appear (parity with what the owner sees month by month). Whole months use
    compute_owner_statement (full editor overlay); a partial edge month falls back
    to the raw engine (month-scoped manual edits can't be pro-rated) and is
    footnoted. `apt` slices to one apartment. Returns (report, error_code)."""
    B = _B()
    units, _listings = _owner_units(owner)
    sel = [u for u in units if (u.get("apartment") or "").strip() == apt] if apt else units
    lids = [u["lid"] for u in sel if u.get("lid") is not None]
    if not lids:
        return None, "no_units"
    # owner-scoped manual lines are attributable only when the slice IS the whole
    # owner (or a single-unit owner). A multi-unit owner filtered to one apartment
    # can't carry owner-level manual entries → raw per-apartment, footnoted.
    owner_total_units = len([u for u in units if u.get("lid") is not None])
    owner_level = (not apt) or owner_total_units <= 1
    month_reports, footnotes = [], []
    for (m_start, m_end, mkey, whole) in _iter_months(start, end):
        rep = None
        if whole and owner_level:
            rep = compute_owner_statement(owner, mkey, settings=settings)
        elif whole and len(lids) == 1:
            # An apartment filter on a multi-unit owner used to re-run the RAW
            # engine, which knows nothing of the statement editor — every
            # include/exclude silently vanished from the apartment PDF. Slice the
            # EDITED statement instead (owner-reported 2026-08-04).
            rep = unit_slice(compute_owner_statement(owner, mkey, settings=settings), lids[0])
            if rep is not None:
                footnotes.append({"kind": "apt_filter_owner_manual_excluded", "month": mkey,
                                  "text_ar": mkey + ": التسويات اليدوية على مستوى المالك تظهر في تقرير المالك",
                                  "text_en": mkey + ": owner-level manual entries appear on the owner report"})
        if rep is None:
            reps = [B.build_owner_report(lid, m_start, m_end, 0, dict(settings or {})) for lid in lids]
            reps = [r for r in reps if r is not None]
            rep = B._finance_aggregate(reps, owner, m_start, m_end) if reps else None
            if rep is not None and not whole:
                footnotes.append({"kind": "partial_month_manual_excluded", "month": mkey,
                                  "text_ar": mkey + ": شهر جزئي — التسويات اليدوية ما تدخل بالتناسب",
                                  "text_en": mkey + ": partial month — manual edits not pro-rated"})
                try:
                    _cl = float((rep.get("cleaning") or {}).get("total") or 0)
                except (TypeError, ValueError):
                    _cl = 0
                if _cl:
                    # cleaning is a flat monthly fee — a partial month still carries it whole
                    footnotes.append({"kind": "partial_month_full_cleaning", "month": mkey,
                                      "text_ar": mkey + ": رسوم النظافة الشهرية محسوبة كاملة رغم إن الشهر جزئي",
                                      "text_en": mkey + ": monthly cleaning charged in full for the partial month"})
            elif rep is not None and not owner_level:
                footnotes.append({"kind": "apt_filter_owner_manual_excluded", "month": mkey,
                                  "text_ar": mkey + ": التسويات اليدوية على مستوى المالك تظهر في تقرير المالك",
                                  "text_en": mkey + ": owner-level manual entries appear on the owner report"})
        if rep is not None:
            month_reports.append(rep)
    if not month_reports:
        return None, "no_data"
    agg = _aggregate_period(month_reports, owner, start, end)
    # re-stamp the basis: neither _aggregate_period nor unit_slice carries it, and an
    # unstamped 0% report would print the «−٣٪» label over full-value numbers
    if settings is not None and settings.get("direct_fee_pct") is not None:
        agg["direct_fee_pct"] = float(settings["direct_fee_pct"])
        agg["no_direct_fee"] = (float(settings["direct_fee_pct"]) == 0.0)
    if apt:
        agg["apartment"] = apt
        if len(agg.get("apartments") or []) == 1:
            agg["lid"] = (agg["apartments"][0] or {}).get("lid")
    if footnotes:
        agg["footnotes"] = (agg.get("footnotes") or []) + footnotes
    return agg, None


def statement_for_portal(owner, mkey):
    """What the OWNER's live link + PDF render: the PUBLISHED snapshot when one
    exists (stable until an explicit republish), else the live compute. This is
    the hook bot.py's _owner_month_report consumes."""
    rec = stmt_rec(owner, mkey)
    pub = (rec or {}).get("published") or {}
    snap = pub.get("snapshot")
    if snap:
        out = json.loads(json.dumps(snap))           # never hand out the stored object
        out["statement_version"] = pub.get("version")
        out["published_at"] = pub.get("at")
        return out
    return compute_owner_statement(owner, mkey)


def _receipt_proxy_rewrite(rep, owner):
    """Expense receipt links open through the owner-scoped proxy (slice 4) so
    Drive sharing settings never break them — in the EDIT view too. The proxy
    token is the statement owner's own link token (scope = his apartments)."""
    try:
        lk = (getattr(_B(), "_owner_links", None) or {}).get(owner) or {}
        tok = lk.get("token") if lk.get("active") else None
        if not tok:
            return rep
        for x in rep.get("exp_lines") or []:
            if (x.get("receipt_url") or "").strip() and str(x.get("id")) in _B()._expenses:
                x["receipt_url"] = "/fin/receipt/" + str(x["id"]) + "?t=" + tok
    except Exception:
        pass
    return rep


# The only two bases a statement may be published on. `None` = bot.py's
# FINANCE_DEFAULTS (the 3% direct-booking deduction) — always the default.
PUBLISH_BASES = {"normal": None, "no_direct_fee": {"direct_fee_pct": 0.0}}


def statement_payload(owner, mkey, settings=None):
    """Everything the editor view needs. `settings` = the read-only alternate
    basis for the «بدون خصم ٣٪» toggle; it changes what this screen SHOWS and
    nothing else (publish recomputes on its own, without it)."""
    live = compute_owner_statement(owner, mkey, settings=settings)
    if live is None:
        return {"error": "owner_not_in_registry"}
    live = _receipt_proxy_rewrite(live, owner)
    rec = stmt_rec(owner, mkey)
    pub = (rec or {}).get("published") or {}
    # What the OWNER's link/PDF renders is the PUBLISHED snapshot, frozen until an
    # explicit republish. So an edit can be correct on this screen and absent from
    # «التقرير النهائي» — and nothing used to say so (owner-reported 2026-08-03,
    # deleted expenses "still in the final report"). Say it, loudly and cheaply.
    snap = pub.get("snapshot") or {}
    pub_basis = pub.get("basis") or "normal"
    # Staleness must compare LIKE WITH LIKE. Two ways it goes wrong:
    #  • previewing an alternate basis — the diff is by design, so don't warn at all;
    #  • the owner's published copy is on the no-fee basis while this screen shows the
    #    normal one — then every such owner would read as permanently "needs
    #    republishing". Re-derive on the PUBLISHED basis and compare against that.
    stale = False
    if settings is None and snap:
        ref = live
        if pub_basis != "normal":
            try:
                ref = compute_owner_statement(owner, mkey,
                                              settings=PUBLISH_BASES[pub_basis]) or live
            except Exception as e:                  # never let this break the screen
                print("stale-compare error:", e)
                ref = None
        stale = ref is not None and any(
            _fnum(snap.get(k)) != _fnum(ref.get(k))
            for k in ("owner_net", "total_income", "expenses", "ouja_fee"))
    return {"ok": True, "owner": owner, "month": mkey,
            "computed_at": datetime.now(_B().TZ).isoformat(timespec="seconds"),
            "month_meta": month_meta(owner, mkey, live, with_compare=True),
            "statement": live,
            "explain": _build_explain(live),
            "edits": (rec or {}).get("edits") or {},
            "audit": list(reversed(((rec or {}).get("audit") or [])))[:120],
            "status": (rec or {}).get("status") or "draft",
            "published_stale": stale,
            "published": ({"version": pub.get("version"), "at": pub.get("at"),
                           "by": pub.get("by"), "basis": pub_basis,
                           "net": ((pub.get("snapshot") or {}).get("owner_net"))}
                          if pub.get("version") else None)}


_EDIT_OPS = ("resv_exclude", "resv_include", "exp_override", "exp_delete",
             "exp_manual_add", "exp_manual_edit", "exp_manual_del", "adj_add", "adj_del",
             "inc_manual_add", "inc_manual_del")

# Ids minted by the editor itself — an expense, a manual income line or an
# adjustment. `resv_exclude`/`resv_include` used to accept ANY id and write it
# into `edits.resv`, where it matched no reservation: the accountant clicked,
# the server answered 200 with unchanged numbers, and nothing ever happened.
_NON_RESV_ID_PREFIXES = ("exp-", "man-", "inc-", "adj-")


def statement_edit(request, body):
    """ONE mutation endpoint for the editor. Every op requires a reason, lands
    in the per-statement audit + the global finance audit, and returns the
    freshly recomputed statement (totals live-update, R1-style)."""
    B = _B()
    owner = (body.get("owner") or "").strip()
    mkey = api._month_key_or_prev(body.get("m"))
    op = (body.get("op") or "").strip()
    reason = (body.get("reason") or "").strip()
    if op not in _EDIT_OPS:
        return {"error": "bad_op"}, 400
    if not owner:
        return {"error": "owner_required"}, 400
    if not reason and op not in ("exp_manual_del", "adj_del", "inc_manual_del"):
        return {"error": "reason_required",
                "message_ar": "السبب إلزامي — كل تعديل لازم يُفسَّر.",
                "message_en": "A reason is required — every edit must be explainable."}, 400
    target = str(body.get("id") or "")
    if op in ("resv_exclude", "resv_include") and (
            not target or target.startswith(_NON_RESV_ID_PREFIXES)):
        return {"error": "not_a_reservation",
                "message_ar": "هذا السطر مصروف أو تسوية يدوية، مو حجز — يتعدّل أو ينحذف من قائمة المصاريف.",
                "message_en": "That row is an expense or a manual line, not a booking — edit or "
                              "delete it in the expenses list."}, 400
    rec = stmt_rec(owner, mkey, create=True)
    e = rec["edits"]
    actor = api.actor(request)
    moved_to = None            # set when an edit relocates a line to another month
    before = None
    after = None
    if op == "resv_exclude":
        before = e["resv"].get(target)
        e["resv"][target] = {"action": "exclude", "reason": reason, "by": actor,
                             "at": datetime.now(B.TZ).isoformat(timespec="seconds")}
        after = e["resv"][target]
    elif op == "resv_include":
        before = e["resv"].get(target)
        entry = {"action": "include", "reason": reason, "by": actor,
                 "at": datetime.now(B.TZ).isoformat(timespec="seconds")}
        if body.get("amount") not in (None, ""):
            try:
                entry["amount"] = round(float(body.get("amount")), 2)
            except (TypeError, ValueError):
                return {"error": "bad_amount"}, 400
        if before and before.get("action") == "exclude":
            e["resv"].pop(target, None)              # undo an exclude = back to computed
            after = None
        else:
            e["resv"][target] = entry
            after = entry
    elif op == "exp_override":
        before = e["exp_overrides"].get(target)
        o = {"reason": reason, "by": actor,
             "at": datetime.now(B.TZ).isoformat(timespec="seconds")}
        for f in ("amount", "date", "description"):
            if body.get(f) not in (None, ""):
                o[f] = (round(float(body[f]), 2) if f == "amount" else str(body[f])[:200])
        e["exp_overrides"][target] = o
        after = o
        # …and down to the apartment, or the unit PDF keeps the old amount
        o["reached_unit"] = _mirror_expense_edit(
            mkey, target, body,
            fields={"amount": o.get("amount"), "date": o.get("date"),
                    "description": o.get("description"), "edit_reason": reason,
                    "edited_by": actor})
    elif op == "exp_delete":
        before = e["exp_overrides"].get(target)
        e["exp_overrides"][target] = {"deleted": True, "reason": reason, "by": actor,
                                      "at": datetime.now(B.TZ).isoformat(timespec="seconds")}
        after = e["exp_overrides"][target]
        # …and down to the apartment, or the deleted line survives on the unit
        # report, the unit tab subtotal and the apartment PDF
        after["reached_unit"] = _mirror_expense_edit(mkey, target, body, delete=True)
    elif op == "exp_manual_add":
        try:
            amt = round(float(body.get("amount")), 2)
        except (TypeError, ValueError):
            return {"error": "bad_amount"}, 400
        # An empty date used to leak the DESCRIPTION into the date field
        # downstream (a sentence printed where a date belongs). Fall back to the
        # last day of the statement month — the line belongs to this month by
        # the very act of typing it here.
        _d_in = str(body.get("date") or "")[:10]
        exp_date = _d_in if _pdate(_d_in) else B._month_bounds(mkey)[1].isoformat()
        if body.get("lid") not in (None, ""):
            # per-APARTMENT manual expense (owner-reported 2026-07: entered per unit
            # but invisible on the unit print). Same fix as inc_manual_add: land in
            # the per-lid adjust store so the unit statement/PDF, the apt-sliced
            # range report and the owner aggregate all read the SAME line.
            try:
                lid = int(body.get("lid"))
            except (TypeError, ValueError):
                return {"error": "bad_lid"}, 400
            start, end = B._month_bounds(mkey)
            ak = B._finance_adjust_key(lid, start.isoformat(), end.isoformat())
            adj = B._finance_adjust.get(ak) or {}
            for kdef, vdef in (("expense_overrides", {}), ("extra_lines", []),
                               ("line_overrides", {}), ("comment", "")):
                adj.setdefault(kdef, vdef)
            line = {"kind": "expense",
                    "label": (str(body.get("description") or "").strip() or "مصروف يدوي")[:200],
                    "amount": amt, "date": exp_date,
                    "reason": reason}
            adj["extra_lines"] = list(adj.get("extra_lines") or []) + [line]
            B._finance_adjust[ak] = adj
            B.persist_state()
            target = ak + " exp[" + str(len(adj["extra_lines"]) - 1) + "]"
            after = line
        else:
            row = {"id": "man-" + uuid.uuid4().hex[:8], "amount": amt,
                   "date": exp_date,
                   "description": str(body.get("description") or "")[:200],
                   "reason": reason, "by": actor,
                   "at": datetime.now(B.TZ).isoformat(timespec="seconds")}
            e["exp_manual"].append(row)
            target = row["id"]
            after = row
    elif op == "exp_manual_edit":
        # «تعديل» on a hand-entered expense — amount / date / description, and
        # above all the MONTH. Since 2.7.1 a manual line counts in the month whose
        # store holds it, whatever its date says, so moving it to another month
        # means physically relocating the row: out of July's store, into August's.
        # Anything less would print an August date on a line July still charges.
        new_amt = body.get("amount")
        if new_amt not in (None, ""):
            try:
                new_amt = round(float(new_amt), 2)
            except (TypeError, ValueError):
                return {"error": "bad_amount"}, 400
        else:
            new_amt = None
        d_in = str(body.get("date") or "")[:10]
        new_date = d_in if _pdate(d_in) else None
        dest = new_date[:7] if new_date else mkey
        new_desc = body.get("description")
        moved = dest != mkey

        if str(target).startswith("exp-adj-"):          # per-APARTMENT line
            try:
                lid = int(body.get("lid"))
                idx = int(str(target).replace("exp-adj-", ""))
            except (TypeError, ValueError):
                return {"error": "bad_target"}, 400
            adj = B._finance_adjust.get(
                B._finance_adjust_key(lid, *[d.isoformat() for d in B._month_bounds(mkey)]))
            lines = list((adj or {}).get("extra_lines") or [])
            if not (0 <= idx < len(lines)) or (lines[idx] or {}).get("kind") == "income":
                return {"error": "expense_line_not_found"}, 404
            before = dict(lines[idx])
            row = dict(lines[idx])
            if new_amt is not None:
                row["amount"] = new_amt
            if new_date:
                row["date"] = new_date
            if new_desc not in (None, ""):
                row["label"] = str(new_desc)[:200]
            row["reason"] = reason
            if not moved:
                lines[idx] = row
                adj["extra_lines"] = lines
                B._finance_adjust[B._finance_adjust_key(
                    lid, *[d.isoformat() for d in B._month_bounds(mkey)])] = adj
            else:
                del lines[idx]
                adj["extra_lines"] = lines
                src_key = B._finance_adjust_key(
                    lid, *[d.isoformat() for d in B._month_bounds(mkey)])
                if not (adj.get("expense_overrides") or adj.get("extra_lines")
                        or adj.get("line_overrides") or (adj.get("comment") or "").strip()):
                    B._finance_adjust.pop(src_key, None)
                else:
                    B._finance_adjust[src_key] = adj
                dst = _unit_adjust(lid, dest)
                dst["extra_lines"] = list(dst.get("extra_lines") or []) + [row]
            B.persist_state()
            after = row
        else:                                            # owner-level line
            rows = e.get("exp_manual") or []
            hit = next((x for x in rows if x.get("id") == target), None)
            if hit is None:
                return {"error": "expense_line_not_found"}, 404
            before = dict(hit)
            row = dict(hit)
            if new_amt is not None:
                row["amount"] = new_amt
            if new_date:
                row["date"] = new_date
            if new_desc not in (None, ""):
                row["description"] = str(new_desc)[:200]
            row["reason"] = reason
            row["by"] = actor
            row["at"] = datetime.now(B.TZ).isoformat(timespec="seconds")
            if not moved:
                e["exp_manual"] = [row if x.get("id") == target else x for x in rows]
            else:
                e["exp_manual"] = [x for x in rows if x.get("id") != target]
                drec = stmt_rec(owner, dest, create=True)
                drec["edits"].setdefault("exp_manual", []).append(row)
            after = row
        if moved:
            # The destination month must be able to explain the line too, and its
            # own cached numbers are now wrong.
            drec = stmt_rec(owner, dest, create=True)
            stmt_audit_add(drec, actor, op, target, before, after,
                           (reason + " — منقول من " + mkey))
            _invalidate_owner_cache(owner, dest)
            moved_to = dest
    elif op == "exp_manual_del" and str(target).startswith("exp-adj-"):
        # per-lid manual expense line (see exp_manual_add) — mirror inc_manual_del
        try:
            lid = int(body.get("lid"))
            idx = int(str(target).replace("exp-adj-", ""))
        except (TypeError, ValueError):
            return {"error": "bad_target"}, 400
        start, end = B._month_bounds(mkey)
        ak = B._finance_adjust_key(lid, start.isoformat(), end.isoformat())
        adj = B._finance_adjust.get(ak)
        lines = list((adj or {}).get("extra_lines") or [])
        if not (0 <= idx < len(lines)) or (lines[idx] or {}).get("kind") == "income":
            return {"error": "expense_line_not_found"}, 404
        before = lines[idx]
        del lines[idx]
        adj["extra_lines"] = lines
        if not (adj.get("expense_overrides") or adj.get("extra_lines")
                or adj.get("line_overrides") or (adj.get("comment") or "").strip()):
            B._finance_adjust.pop(ak, None)
        B.persist_state()
        target = ak + " exp[" + str(idx) + "]"
    elif op == "exp_manual_del":
        before = next((x for x in e["exp_manual"] if x.get("id") == target), None)
        e["exp_manual"] = [x for x in e["exp_manual"] if x.get("id") != target]
    elif op == "adj_add":
        try:
            amt = round(float(body.get("amount")), 2)
        except (TypeError, ValueError):
            return {"error": "bad_amount"}, 400
        row = {"id": "adj-" + uuid.uuid4().hex[:8], "amount": amt,
               "label": str(body.get("label") or "تسوية")[:120],
               "reason": reason, "by": actor,
               "at": datetime.now(B.TZ).isoformat(timespec="seconds")}
        e["adjustments"].append(row)
        target = row["id"]
        after = row
    elif op == "adj_del":
        before = next((x for x in e["adjustments"] if x.get("id") == target), None)
        e["adjustments"] = [x for x in e["adjustments"] if x.get("id") != target]
    elif op == "inc_manual_add":
        # v2.2 slice 3: per-apartment MANUAL INCOME — fee-exempt. Lands in the
        # legacy per-lid adjust store so the unit PDF and the owner aggregate
        # read the SAME line (exactly May's «سلطان عبدالله 2,844» pattern).
        try:
            amt = round(float(body.get("amount")), 2)
        except (TypeError, ValueError):
            return {"error": "bad_amount"}, 400
        try:
            lid = int(body.get("lid"))
        except (TypeError, ValueError):
            return {"error": "lid_required",
                    "message_ar": "حدد الشقة أول.", "message_en": "Pick the apartment first."}, 400
        start, end = B._month_bounds(mkey)
        ak = B._finance_adjust_key(lid, start.isoformat(), end.isoformat())
        adj = B._finance_adjust.get(ak) or {}
        for kdef, vdef in (("expense_overrides", {}), ("extra_lines", []),
                           ("line_overrides", {}), ("comment", "")):
            adj.setdefault(kdef, vdef)
        line = {"kind": "income",
                "label": (str(body.get("label") or "").strip() or "إيراد يدوي")[:120],
                "amount": amt}
        adj["extra_lines"] = list(adj.get("extra_lines") or []) + [line]
        B._finance_adjust[ak] = adj
        B.persist_state()
        target = ak + " inc[" + str(len(adj["extra_lines"]) - 1) + "]"
        after = line
    elif op == "inc_manual_del":
        try:
            lid = int(body.get("lid"))
            idx = int(str(body.get("id") or "").replace("inc-", ""))
        except (TypeError, ValueError):
            return {"error": "bad_target"}, 400
        start, end = B._month_bounds(mkey)
        ak = B._finance_adjust_key(lid, start.isoformat(), end.isoformat())
        adj = B._finance_adjust.get(ak)
        lines = list((adj or {}).get("extra_lines") or [])
        if not (0 <= idx < len(lines)) or (lines[idx] or {}).get("kind") != "income":
            return {"error": "income_line_not_found"}, 404
        before = lines[idx]
        del lines[idx]
        adj["extra_lines"] = lines
        if not (adj.get("expense_overrides") or adj.get("extra_lines")
                or adj.get("line_overrides") or (adj.get("comment") or "").strip()):
            B._finance_adjust.pop(ak, None)
        B.persist_state()
        target = ak + " inc[" + str(idx) + "]"
    stmt_audit_add(rec, actor, op, target, before, after, reason)
    _stmt_save()
    try:
        B._fb_audit_add(actor, "owner_stmt_" + op, "owner_statement",
                        _stmt_key(owner, mkey), before=before, after=after)
    except Exception:
        pass
    _invalidate_owner_cache(owner, mkey)
    payload = statement_payload(owner, mkey)
    if moved_to:
        payload["moved_to"] = moved_to
    return payload, 200


def statement_publish(request, body):
    """Freeze the CURRENT live compute as the published snapshot (version+1).
    The owner's live link + PDF flip to it together; the version marker shows
    on the page so a stale PDF is recognizable.

    `basis` (2026-08-06, owner's decision) picks WHICH statement gets frozen —
    'normal' (the 3% direct-booking deduction) or 'no_direct_fee' (full value).
    It must arrive EXPLICITLY in the request body: it is never inherited from
    whatever basis the screen happens to be previewing, so an alternate view
    cannot publish itself. Default is always 'normal', and the chosen basis is
    stored on the published record + the audit trail — six months from now the
    record is the only way to know which statement an owner was actually sent."""
    B = _B()
    owner = (body.get("owner") or "").strip()
    mkey = api._month_key_or_prev(body.get("m"))
    basis = (body.get("basis") or "normal").strip()
    if basis not in PUBLISH_BASES:
        return {"error": "bad_basis"}, 400
    fresh = compute_owner_statement(owner, mkey, settings=PUBLISH_BASES[basis])
    if fresh is None:
        return {"error": "owner_not_in_registry"}, 404
    if fresh.get("degraded"):
        # M3: never freeze a snapshot computed from the truncated fallback.
        return {"error": "degraded_data",
                "message_ar": "بيانات غير متاحة مؤقتاً — ما قدرنا نسحب الحجوزات من Hostaway. جرّب بعد شوي قبل النشر.",
                "message_en": "Data temporarily unavailable — the Hostaway pull failed. Retry before publishing."}, 503
    # The OWNER's copy must read as an ordinary statement (his call: «ولا شي —
    # كشف عادي تماماً»), so the internal display stamp is dropped — no red band,
    # no «تقرير بدون خصم ٣٪» title. direct_fee_pct=0 deliberately STAYS: it is what
    # makes the PDF print a bare «دخل مباشر» instead of a false «−٣٪» over
    # full-value numbers. Silence is fine; a wrong percentage is not.
    fresh.pop("no_direct_fee", None)
    rec = stmt_rec(owner, mkey, create=True)
    old = rec.get("published") or {}
    ver = int(old.get("version") or 0) + 1
    rec["published"] = {"version": ver, "at": datetime.now(B.TZ).isoformat(timespec="seconds"),
                        "by": api.actor(request), "basis": basis, "snapshot": fresh}
    if rec.get("status") in (None, "", "draft"):
        rec["status"] = "ready"
    stmt_audit_add(rec, api.actor(request), "publish", "v" + str(ver),
                   {"version": old.get("version"), "basis": old.get("basis") or "normal",
                    "net": (old.get("snapshot") or {}).get("owner_net")},
                   {"version": ver, "basis": basis, "net": fresh.get("owner_net")},
                   body.get("reason") or "")
    _stmt_save()
    _invalidate_owner_cache(owner, mkey)
    try:
        B.log_event("finance", "نُشر كشف %s — %s (نسخة %d)" % (owner, mkey, ver))
    except Exception:
        pass
    return {"ok": True, "version": ver, "net": fresh.get("owner_net"),
            "basis": basis, "at": rec["published"]["at"]}, 200


def statement_recompute_diff(owner, mkey):
    """«أعد الحساب» preview: published snapshot vs a FRESH compute — the diff
    the admin must see before republishing a past month."""
    rec = stmt_rec(owner, mkey)
    pub = (rec or {}).get("published") or {}
    snap = pub.get("snapshot")
    fresh = compute_owner_statement(owner, mkey)
    if fresh is None:
        return {"error": "owner_not_in_registry"}
    def tot(r):
        return {"total_income": (r or {}).get("total_income"),
                "ouja_fee": (r or {}).get("ouja_fee"),
                "expenses": (r or {}).get("expenses"),
                "cleaning": ((r or {}).get("cleaning") or {}).get("total"),
                "adjustments": (r or {}).get("adjustments_total") or 0,
                "owner_net": (r or {}).get("owner_net")}
    a, b = tot(snap), tot(fresh)
    delta = {k: (None if (a[k] is None or b[k] is None)
                 else round(float(b[k]) - float(a[k]), 2)) for k in a}
    return {"ok": True, "owner": owner, "month": mkey,
            "published": (a if snap else None), "fresh": b, "delta": delta,
            "published_version": pub.get("version"),
            "changed": any((delta[k] or 0) != 0 for k in delta) if snap else True}


# ====================== v2.2 slice 3: the owner profile ======================

def owner_profile(owner):
    """Everything the owner-profile page renders: header (profile + link),
    apartment chips (with live contract terms), and the 12-month grid with
    per-month net / status / anomaly flag / per-unit nets. Reads the memoized
    month reports — first load computes, then it's warm."""
    B = _B()
    det = owner_detail(owner)
    if not det.get("ok"):
        return det
    if not det.get("units"):
        return {"error": "owner_not_in_registry", "owner": owner}
    links = getattr(B, "_owner_links", None) or {}
    lk = links.get(owner) or {}
    today = datetime.now(B.TZ).date()
    cur = today.isoformat()[:7]
    months = []
    y, m = int(cur[:4]), int(cur[5:7])
    mkeys = []
    for i in range(12):
        ty, tm = y, m - i
        while tm <= 0:
            tm += 12
            ty -= 1
        mkeys.append("%04d-%02d" % (ty, tm))
    # v2.2.2 perf: warm missing months in parallel (cold grid was 12 serial pulls)
    try:
        pcache = getattr(B, "_owner_portal_cache", {}) or {}
        warm = [k for k in mkeys if (owner, k) not in pcache]
        if len(warm) > 1:
            with ThreadPoolExecutor(max_workers=4) as ex:
                list(ex.map(lambda k: B._owner_month_report(owner, k), warm))
    except Exception as e:
        print("owner_profile warmup error:", e)
    for k in mkeys:
        try:
            rep = B._owner_month_report(owner, k)
        except Exception as e:
            print("owner_profile month %s error: %s" % (k, e))
            rep = None
        srec = stmt_rec(owner, k) or {}
        pub = srec.get("published") or {}
        try:
            anomalies = owner_anomalies(owner, k, rep) if rep is not None else []
        except Exception:
            anomalies = []
        unit_nets = {}
        for p in (rep or {}).get("apartments") or []:
            unit_nets[str(p.get("apartment") or "")] = p.get("owner_net")
        months.append({"m": k,
                       "state": "running" if k == cur else "closed",
                       "net": (rep or {}).get("owner_net"),
                       "status": srec.get("status") or "draft",
                       "published_version": pub.get("version"),
                       "flagged": bool(anomalies), "anomalies": anomalies[:4],
                       "unit_nets": unit_nets})
    return {"ok": True, "owner": owner,
            "profile": det.get("profile") or {},
            "units": det.get("units") or [],
            "versions": (det.get("versions") or [])[:20],
            "months": months,
            "link": {"exists": bool(lk.get("token")), "active": bool(lk.get("active")),
                     "url": ("/fin/o/" + lk["token"]) if (lk.get("token") and lk.get("active")) else "",
                     "opened_at": lk.get("opened_at") or "", "opens": lk.get("opens") or 0},
            "wa_template": wa_template(),
            "default_month": api._month_key_or_prev(None),
            "month_meta": month_meta(owner, cur)}


# ====================== Slice 3: دورة الشهر — the monthly cycle board ======================

import os as _os

# Anomaly thresholds — env-configurable, sane defaults.
ANOM_NET_DEV_PCT = float(_os.environ.get("OWNER_ANOM_NET_DEV_PCT", "30"))      # vs 3-month avg
ANOM_EXCLUDED_SAR = float(_os.environ.get("OWNER_ANOM_EXCLUDED_SAR", "500"))   # excluded reference value
ANOM_RECEIPT_SAR = float(_os.environ.get("OWNER_ANOM_RECEIPT_SAR", "200"))     # expense without receipt (slice 4)

_STATUSES = ("draft", "ready", "reviewed", "sent", "opened")

_WA_DEFAULT = ("مساء الخير {owner} 🌙\n"
               "كشف حسابك لشهر {month} جاهز — صافيك {net} ريال.\n"
               "تقدر تفتحه من رابطك الخاص:\n{link}\n"
               "أي ملاحظة نسولف فيها على طول 🙏")


def wa_template():
    st = _terms_store()
    return (st.get("settings") or {}).get("wa_template") or _WA_DEFAULT


def wa_template_set(request, text):
    st = _terms_store()
    st.setdefault("settings", {})
    before = st["settings"].get("wa_template")
    st["settings"]["wa_template"] = str(text or "")[:1000] or _WA_DEFAULT
    terms_version_add(api.actor(request), "wa_template", "settings", before, st["settings"]["wa_template"])
    return st["settings"]["wa_template"]


def _prev_months(mkey, n=3):
    y, m = int(mkey[:4]), int(mkey[5:7])
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append("%04d-%02d" % (y, m))
    return out


def owner_anomalies(owner, mkey, rep):
    """Pre-send checks for one owner-month. `rep` = the month's report (memoized)."""
    B = _B()
    out = []
    if rep is None:
        return [{"key": "no_report", "sev": "bad",
                 "ar": "ما انحسب كشف", "en": "No statement computed"}]
    net = float(rep.get("owner_net") or 0)
    # 1) net deviation vs the owner's own 3-month average
    prior = []
    for pm in _prev_months(mkey, 3):
        try:
            pr = B._owner_month_report(owner, pm)
        except Exception:
            pr = None
        if pr is not None and pr.get("owner_net") is not None:
            prior.append(float(pr["owner_net"]))
    if prior:
        avg = sum(prior) / len(prior)
        if abs(avg) > 1 and abs(net - avg) / abs(avg) * 100.0 > ANOM_NET_DEV_PCT:
            dev = round((net - avg) / abs(avg) * 100.0)
            out.append({"key": "net_deviation", "sev": "warn",
                        "ar": "الصافي %+d%% عن متوسط ٣ أشهر (%s)" % (dev, "{:,.0f}".format(avg)),
                        "en": "Net %+d%% vs 3-month avg (%s)" % (dev, "{:,.0f}".format(avg))})
    es = rep.get("excluded_summary") or {}
    # 2) excluded-reservation value above threshold
    excl_val = float(es.get("needs_review_reference") or 0) + float(es.get("manual_excluded_value") or 0)
    if excl_val > ANOM_EXCLUDED_SAR:
        out.append({"key": "excluded_value", "sev": "warn",
                    "ar": "قيمة مستبعدة %s ريال" % "{:,.0f}".format(excl_val),
                    "en": "Excluded value SAR %s" % "{:,.0f}".format(excl_val)})
    # 3) missing payout count
    if int(es.get("needs_review") or 0) > 0:
        out.append({"key": "missing_payout", "sev": "bad",
                    "ar": "%d حجز بانتظار تأكيد المبلغ" % es["needs_review"],
                    "en": "%d bookings awaiting amount" % es["needs_review"]})
    # 4) zero-revenue unit (in-contract, whole month, no income)
    zero_units = [a.get("apartment") for a in (rep.get("apartments") or [])
                  if not float(a.get("total_income") or 0)]
    if zero_units:
        out.append({"key": "zero_revenue_unit", "sev": "warn",
                    "ar": "وحدة بدون دخل: " + "، ".join(str(u) for u in zero_units[:4]),
                    "en": "Zero-revenue unit: " + ", ".join(str(u) for u in zero_units[:4])})
    # 5) unverified expenses on his units (would be missing from the statement)
    try:
        listings = B.get_listings_map() or {}
        lids = set(B._owner_lids(owner, listings))
        start, end = B._month_bounds(mkey)
        pend = 0
        for e in B._expenses.values():
            if e.get("listing_id") not in lids:
                continue
            d = _pdate(e.get("expense_date"))
            if d is None or not (start <= d <= end):
                continue
            if B._exp_canonical_status(e) != "verified":
                pend += 1
        if pend:
            out.append({"key": "pending_expenses", "sev": "warn",
                        "ar": "%d مصروف غير متحقق على وحداته" % pend,
                        "en": "%d unverified expenses on his units" % pend})
    except Exception:
        pass
    # 6) big expense without a receipt (slice 4 ties the proxy in)
    noreceipt = [x for x in (rep.get("exp_lines") or [])
                 if float(x.get("amount") or 0) >= ANOM_RECEIPT_SAR
                 and not (x.get("receipt_url") or "").strip() and not x.get("manual")]
    if noreceipt:
        out.append({"key": "receipt_missing", "sev": "warn",
                    "ar": "%d مصروف ≥%d بدون فاتورة" % (len(noreceipt), int(ANOM_RECEIPT_SAR)),
                    "en": "%d expenses ≥%d without receipt" % (len(noreceipt), int(ANOM_RECEIPT_SAR))})
    # 7) v2.2.3: cancelled rows carrying a REAL payment signal — by policy they
    # never auto-count; this reminds Faisal to review and add manually if real.
    sig = [x for x in (rep.get("refunded_lines") or [])
           if x.get("kind") == "cancelled_money_signal"]
    if sig:
        out.append({"key": "cancelled_money_signal", "sev": "warn",
                    "ar": "%d إلغاء فيه إشارة دفع — يحتاج مراجعتك اليدوية" % len(sig),
                    "en": "%d cancellations with a payment signal — review manually" % len(sig)})
    return out


def cycle_board(mkey):
    """One row per owner for the month: status, net, anomalies, link state."""
    B = _B()
    owners = sorted({(r.get("owner") or "").strip() for r in api._registry_rows()
                     if (r.get("owner") or "").strip()})
    links = getattr(B, "_owner_links", None) or {}
    rows = []
    _dirty = False   # batch the sent→opened auto-flips into ONE save after the loop
    for o in owners:
        rec = stmt_rec(o, mkey)
        status = (rec or {}).get("status") or "draft"
        sent_at = ""
        for ev in reversed((rec or {}).get("status_log") or []):
            if ev.get("to") == "sent":
                sent_at = ev.get("at") or ""
                break
        lk = links.get(o) or {}
        # فتحها flips automatically off the existing opened_at touch
        if status == "sent" and lk.get("opened_at") and sent_at and lk["opened_at"] >= sent_at:
            rec = stmt_rec(o, mkey, create=True)
            rec["status"] = "opened"
            rec.setdefault("status_log", []).append(
                {"at": lk["opened_at"], "by": "owner-open", "to": "opened"})
            status = "opened"
            _dirty = True
        try:
            rep = B._owner_month_report(o, mkey)
        except Exception:
            rep = None
        anomalies = owner_anomalies(o, mkey, rep)
        prof = (_terms_store()["owners"] or {}).get(o) or {}
        pub = (rec or {}).get("published") or {}
        rows.append({
            "owner": o, "phone": prof.get("phone") or "",
            "active": prof.get("active", True),
            "units": len([r for r in api._registry_rows() if (r.get("owner") or "").strip() == o]),
            "net": (rep or {}).get("owner_net"),
            "status": status,
            "published_version": pub.get("version"),
            "anomalies": anomalies,
            "flagged": bool(anomalies),
            "link": {"exists": bool(lk.get("token")), "active": bool(lk.get("active")),
                     "url": ("/fin/o/" + lk["token"]) if (lk.get("token") and lk.get("active")) else "",
                     "opened_at": lk.get("opened_at") or ""},
        })
    if _dirty:
        _stmt_save()
    # flagged first («راجع هذي قبل الإرسال»), then by name
    rows.sort(key=lambda r: (not r["flagged"], r["owner"]))
    counts = {"total": len(rows),
              "ready": sum(1 for r in rows if r["status"] in ("ready", "reviewed", "sent", "opened")),
              "sent": sum(1 for r in rows if r["status"] in ("sent", "opened")),
              "opened": sum(1 for r in rows if r["status"] == "opened"),
              "flagged": sum(1 for r in rows if r["flagged"])}
    total_net = round(sum(float(r["net"]) for r in rows if r["net"] is not None), 2)
    return {"ok": True, "month": mkey, "rows": rows, "counts": counts,
            "month_meta": month_meta(None, mkey),
            "portfolio_net": total_net, "wa_template": wa_template(),
            "thresholds": {"net_dev_pct": ANOM_NET_DEV_PCT,
                           "excluded_sar": ANOM_EXCLUDED_SAR,
                           "receipt_sar": ANOM_RECEIPT_SAR},
            "done": counts["sent"] >= counts["total"] and counts["total"] > 0}


def cycle_status_set(request, body):
    """Status transition for one/many owners (bulk). Forward or back — every
    move is logged with who/when."""
    to = (body.get("to") or "").strip()
    if to not in _STATUSES:
        return {"error": "bad_status"}, 400
    mkey = api._month_key_or_prev(body.get("m"))
    owners = body.get("owners") or ([body.get("owner")] if body.get("owner") else [])
    owners = [str(o).strip() for o in owners if str(o or "").strip()]
    if not owners:
        return {"error": "owners_required"}, 400
    now = datetime.now(_B().TZ).isoformat(timespec="seconds")
    actor = api.actor(request)
    changed = []
    for o in owners:
        rec = stmt_rec(o, mkey, create=True)
        if rec.get("status") == to:
            continue
        rec.setdefault("status_log", []).append({"at": now, "by": actor,
                                                 "from": rec.get("status"), "to": to})
        rec["status"] = to
        stmt_audit_add(rec, actor, "status", to, None, None, body.get("reason") or "")
        changed.append(o)
    _stmt_save()
    return {"ok": True, "changed": changed, "to": to}, 200


def cycle_links(request, body):
    """Link hygiene: action=regen_all (old tokens die, logged) or copy_all
    (the owner+URL list for manual sending)."""
    B = _B()
    action = (body.get("action") or "").strip()
    owners = sorted({(r.get("owner") or "").strip() for r in api._registry_rows()
                     if (r.get("owner") or "").strip()})
    actor = api.actor(request)
    if action == "regen_all":
        out = []
        for o in owners:
            rec = B._owner_link_regenerate(o, actor)
            out.append({"owner": o, "url": "/fin/o/" + rec["token"]})
        try:
            B.log_event("finance", "جُدّدت روابط الملاك كلها (%d) — الروابط القديمة ماتت" % len(out))
        except Exception:
            pass
        return {"ok": True, "links": out, "regenerated": len(out)}, 200
    if action == "copy_all":
        links = getattr(B, "_owner_links", None) or {}
        out = []
        for o in owners:
            lk = links.get(o) or {}
            if lk.get("token") and lk.get("active"):
                out.append({"owner": o, "url": "/fin/o/" + lk["token"]})
        return {"ok": True, "links": out}, 200
    return {"error": "bad_action"}, 400


def diagnose(owner, mkey):
    """The 0b reconciliation table for (owner, month). Pure read — no writes."""
    B = _B()
    units, listings = _owner_units(owner)
    if not units:
        return {"error": "owner_not_in_registry", "owner": owner}
    start, end = B._month_bounds(mkey)
    window = B.fetch_reservations_window(start, end)
    big_ids = {str(r.get("id")) for r in (B.get_reservations_cached() or [])}
    migrated_apts = set()
    if "v21-102b" in (B._load_json("owner_registry_migrations.json", []) or []):
        migrated_apts.add("102b")

    rows = []
    unit_summaries = []
    total_included = 0.0
    pre_fix_net = 0.0
    fixed_net = 0.0
    lost_truncation_value = 0.0
    lost_registry_value = 0.0

    for u in units:
        lid = u["lid"]
        raw_rows = [r for r in window if r.get("listingMapId") == lid] if lid is not None else []
        norm = [B.normalize_reservation(r, listings) for r in raw_rows]
        raw_by_id = {str(n.get("id")): raw_rows[i] for i, n in enumerate(norm)}
        mgmt = float(u.get("mgmt_pct") or 0)
        # the REAL statement math for this unit (full rows + real expenses + adjust)
        rep_full = B.build_owner_report(lid, start, end, 0, {}) if lid is not None else None
        # the same math but ONLY rows the pre-fix pull could see, and only for
        # units that existed in the registry pre-migration → the old wrong number
        unit_is_migrated = B._owner_key(u["apartment"]) in {B._owner_key(a) for a in migrated_apts}
        if rep_full is not None:
            fixed_net += float(rep_full.get("owner_net") or 0)
            if not unit_is_migrated:
                # pre-fix world: only rows the truncated cache could see; a unit the
                # registry didn't know contributes NOTHING (not even its expenses).
                old_rows = [n for n in norm if str(n.get("id")) in big_ids]
                rep_old = B.compute_owner_report(
                    old_rows,
                    [{"id": e.get("id"), "amount": e.get("amount"), "date": e.get("date"),
                      "matched": True} for e in (rep_full.get("exp_lines_raw") or rep_full.get("exp_lines") or [])],
                    start, end, mgmt, None, cleaning=u.get("cleaning"))
                pre_fix_net += float(rep_old.get("owner_net") or 0)
        # ---- correlate every window row to its verdict in the real math ----
        verdicts = {}
        if rep_full is not None:
            for l in rep_full.get("resv_lines") or []:
                rid = str(l.get("id"))
                if l.get("needs_review"):
                    verdicts[rid] = {"verdict": "excluded", "reason": l.get("exclude_reason") or "needs_review",
                                     "amount": None, "reference": l.get("reference_total")}
                else:
                    verdicts[rid] = {"verdict": "included", "reason": "",
                                     "amount": l.get("income"), "reference": None}
            for l in rep_full.get("refunded_lines") or []:
                verdicts[str(l.get("id"))] = {"verdict": "excluded",
                                              "reason": l.get("kind") or "cancelled_refunded",
                                              "amount": 0.0,
                                              "reference": l.get("reference_total"),
                                              "evidence": l.get("evidence")}
            for l in rep_full.get("unpaid_lines") or []:
                verdicts[str(l.get("id"))] = {"verdict": "excluded", "reason": "unpaid_yet",
                                              "amount": None, "reference": l.get("expected")}
        for n in norm:
            rid = str(n.get("id"))
            v = verdicts.get(rid)
            if v is None:
                status = (n.get("status") or "")
                in_period = B._finance_in_period(n, start, end, "checkin")
                v = {"verdict": "excluded",
                     "reason": ("out_of_period" if not in_period else "status_" + (status or "unknown")),
                     "amount": None, "reference": n.get("total_price")}
            in_cache = rid in big_ids
            if v["verdict"] == "included":
                total_included += float(v.get("amount") or 0)
                if not in_cache:
                    lost_truncation_value += float(v.get("amount") or 0)
                if unit_is_migrated:
                    lost_registry_value += float(v.get("amount") or 0)
            rows.append({
                "id": rid, "apartment": u["apartment"], "listing": u["listing"],
                "guest": n.get("guest"), "channel": n.get("channel"),
                "checkin": n.get("checkin"), "checkout": n.get("checkout"),
                "nights": n.get("nights"), "status": n.get("status"),
                "total_price": n.get("total_price"),
                "verdict": v["verdict"], "reason": v.get("reason") or "",
                "amount": v.get("amount"), "reference": v.get("reference"),
                "evidence": v.get("evidence") or "",
                "in_history_cache": in_cache,
                "unit_added_by_fix": unit_is_migrated,
                "field_probe": _probe(raw_by_id.get(rid) or {}),
            })
        unit_summaries.append({
            "apartment": u["apartment"], "lid": lid, "listing": u["listing"],
            "mgmt_pct": u.get("mgmt_pct"), "cleaning": u.get("cleaning"),
            "rows": sum(1 for r in rows if r["apartment"] == u["apartment"]),
            "net": (rep_full or {}).get("owner_net"),
            "income": (rep_full or {}).get("total_income"),
            "expenses": (rep_full or {}).get("expenses"),
            "added_by_fix": unit_is_migrated,
            "lid_unresolved": lid is None,
        })

    rows.sort(key=lambda r: (r["apartment"], r.get("checkin") or ""))
    rep_now = B._owner_month_report(owner, mkey)
    # payout-field histogram across the owner's rows — THE live evidence for
    # which Hostaway field actually carries the Airbnb payout.
    field_hist = {}
    for r in rows:
        for k in r["field_probe"]:
            field_hist[k] = field_hist.get(k, 0) + 1
    return {
        "ok": True, "owner": owner, "month": mkey,
        "generated_at": datetime.now(_B().TZ).isoformat(timespec="seconds"),
        "units": unit_summaries,
        "rows": rows,
        "field_histogram": field_hist,
        "totals": {
            "statement_net_now": (rep_now or {}).get("owner_net"),
            "statement_income_now": (rep_now or {}).get("total_income"),
            "included_income_sum": round(total_included, 2),
            "pre_fix_net_estimate": round(pre_fix_net, 2),
            "fixed_net": round(fixed_net, 2),
            "lost_to_truncation_income": round(lost_truncation_value, 2),
            "lost_to_missing_unit_income": round(lost_registry_value, 2),
        },
        "excluded_summary": (rep_now or {}).get("excluded_summary") or {},
        "window_rows": len(window),
        "history_cache_rows": len(big_ids),
        "notes_ar": ("pre_fix_net_estimate = الرقم اللي كان يطلع قبل الإصلاح (بدون الحجوزات "
                     "المفقودة من الكاش المبتور وبدون الوحدات المضافة) — fixed_net = بعد الإصلاح."),
    }
