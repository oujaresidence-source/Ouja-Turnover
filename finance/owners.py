# -*- coding: utf-8 -*-
"""الملاك v2.1 — owner-workspace server logic.

Slice 0b: the statement DIAGNOSIS — a line-by-line reconciliation of one
owner-month built from a TARGETED Hostaway window pull, classifying every
candidate reservation as included/excluded-with-reason, probing the raw
payout/payment fields, and quantifying the two silent-exclusion bugs
(history-cache truncation + units missing from the registry).

Money classification is NEVER duplicated here: rows are bucketed by running
bot.py's own compute_owner_report on the same normalized rows and correlating
ids — the table can't drift from the real statement math.
"""

from datetime import datetime

from . import api


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
