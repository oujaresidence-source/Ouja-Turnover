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
            base["cleaning"] = best["cleaning"]
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


def _invalidate_owner_cache(owner):
    """Terms changed → the memoized monthly reports for this owner are stale."""
    try:
        cache = _B()._owner_portal_cache
        for key in [k for k in cache if k[0] == owner]:
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


def unit_statement(rec, mkey):
    """One unit's month with effective dating applied ON TOP of bot.py's report.
    No overlay data → the legacy report passes through untouched (safety).
    Returns (report_dict, footnotes[])."""
    B = _B()
    listings = B.get_listings_map() or {}
    apt = rec.get("apartment") or ""
    lid = B._owner_resolve_lid(rec, listings)
    start, end = B._month_bounds(mkey)
    rep = B.build_owner_report(lid, start, end, 0, {}) if lid is not None else None
    if rep is None:
        return None, []
    ov = unit_overlay(apt)
    cf, ct = contract_window(apt)
    has_terms = bool(ov.get("terms"))
    win_s = max(start, cf) if cf else start
    win_e = min(end, ct) if ct else end
    partial = (win_s > start) or (win_e < end)
    if not has_terms and not partial:
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
        if not in_win:
            x = dict(l)
            x["needs_review"] = False
            x["exclude_reason"] = "outside_contract"
            x["reference_total"] = l.get("income") if l.get("income") is not None else l.get("reference_total")
            x["income"] = None
            excluded.append(x)
            continue
        if l.get("income") is not None:
            tm = terms_on(apt, ci, rec)
            pct = _D(tm.get("mgmt_pct") or 0)
            l = dict(l)
            l["mgmt_pct_applied"] = float(pct)
            line_money = _D(l["income"]) + _D(l.get("extras") or 0)
            fee += line_money * pct / Decimal(100)   # legacy applies the % to extras too
            income += line_money
        kept.append(l)
    exp_kept, exp_excluded = [], []
    exp_total = Decimal(0)
    for e in rep.get("exp_lines") or []:
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
    cleaning_total = Decimal(0)
    if cl_now.get("type") == "owner" and covered:
        cleaning_total = (_D(cl_now.get("amount")) * Decimal(covered) / Decimal(days_in_month)
                          ).quantize(TWO, rounding=ROUND_HALF_UP)
        if covered < days_in_month:
            footnotes.append({"apartment": apt, "kind": "cleaning_prorated",
                              "text_ar": apt + ": النظافة محسوبة نسبيًا (" + str(covered) + "/" + str(days_in_month) + " يوم)",
                              "text_en": apt + ": cleaning pro-rated (" + str(covered) + "/" + str(days_in_month) + " days)"})
    out = dict(rep)
    out["resv_lines"] = kept
    out["contract_excluded_lines"] = excluded
    out["exp_lines"] = exp_kept
    out["contract_excluded_expenses"] = exp_excluded
    out["total_income"] = _fnum(income + manual)
    out["ouja_fee"] = _fnum(fee)
    out["expenses"] = _fnum(exp_total)
    out["cleaning"] = {"type": cl_now.get("type", "ours"), "amount": _fnum(cl_now.get("amount") or 0),
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


def compute_owner_statement(owner, mkey):
    """The v2.1 owner-month statement: per-unit effective-dated reports
    aggregated the same way bot.py aggregates (shape-compatible superset).
    Returns None when the owner has no registry units (caller falls back)."""
    B = _B()
    start, end = B._month_bounds(mkey)
    recs = [r for r in api._registry_rows() if (r.get("owner") or "").strip() == (owner or "").strip()]
    if not recs:
        return None
    reps, foots = [], []
    for rec in recs:
        rep, fn = unit_statement(rec, mkey)
        if rep is not None:
            reps.append(rep)
            foots.extend(fn)
    if not reps:
        return None
    agg = B._finance_aggregate(reps, owner, start, end)
    # carry the v2.1 extras through the aggregate
    contract_excluded = []
    for r in reps:
        contract_excluded.extend(r.get("contract_excluded_lines") or [])
        contract_excluded.extend(r.get("contract_excluded_expenses") or [])
    if contract_excluded:
        es = dict(agg.get("excluded_summary") or {})
        es["outside_contract"] = sum(1 for x in contract_excluded if x.get("checkin"))
        es["outside_contract_value"] = _fnum(sum((_D(x.get("reference_total") or x.get("amount") or 0)
                                                  for x in contract_excluded), Decimal(0)))
        agg["excluded_summary"] = es
        agg["contract_excluded_lines"] = contract_excluded
    if foots:
        agg["footnotes"] = foots
    op = (_terms_store()["owners"] or {}).get(owner) or {}
    if op:
        agg["owner_profile"] = {"phone": op.get("phone") or "", "active": op.get("active", True)}
    return agg


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
                verdicts[str(l.get("id"))] = {"verdict": "excluded", "reason": "cancelled_refunded",
                                              "amount": 0.0, "reference": None,
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
