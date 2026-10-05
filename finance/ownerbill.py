# -*- coding: utf-8 -*-
"""«حساب المالك» — owner-account billing.

Every other owner is paid a NET by Ouja: Airbnb pays Ouja, Ouja keeps its fee and
transfers the rest. A VAT-registered owner runs his units on HIS OWN Airbnb
account, so Airbnb pays HIM — and the money has to travel the other way: Ouja
BILLS him. The first building is Al-Nuzha (أبو فهد): its eight units were
duplicated under his account with an «-O» suffix (live 2026-09-13…19).

Owner's rules (brainstorm 2026-10-05, docs/superpowers/specs/2026-10-05-owner-account-billing-design.md):
  * Same deal as before: 18% of what Airbnb paid out, cleaning on Ouja, expenses
    at cost, + 15% VAT on Ouja's fee ONLY.
  * Two documents: the old statement keeps the OLD listings; this claim covers
    the «-O» listings. The listing decides whose money a booking was.
  * Expenses go by DATE: before a unit's switch date → the old statement; on or
    after → this claim. Switch date = first check-in on the unit's «-O» listing.
  * The tax invoice is issued in Daftra; its number is typed in and approval is
    impossible without it. Our PDF is «كشف حساب ومطالبة مالية» — never a tax invoice.

This module only READS Hostaway (through bot.py's proven statement engine). It
never writes to Hostaway, Airbnb or Daftra, and it never sends anything itself.
"""

import threading
import uuid
from calendar import monthrange
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from . import api

TWO = Decimal("0.01")
DUE_DAYS = 10                      # contract: the owner pays within 10 days of receipt
_FILE = "ownerbill.json"
_LOCK = threading.RLock()
_cache = {"v": None}
_month_cache = {}                  # (bid, mkey) -> (ts, payload)
_MONTH_TTL = 600                   # live months recompute at most every 10 min (writes bust it)

# ---------------------------------------------------------------------------
# Buildings. Listing ids read live from Hostaway on 2026-10-05.
# `owner` is the REGISTRY spelling (the key of the owner's profile / phone);
# `display_owner` is what the claim prints.
# ---------------------------------------------------------------------------
BUILDINGS = {
    "nuzha": {
        "id": "nuzha", "code": "NZH",
        "name_ar": "عمارة النزهة", "name_en": "Al-Nuzha building",
        "owner": "ابو فهد عبدالحمن الخطيب",
        "display_owner": "أبو فهد عبدالرحمن الخطيب",
        "mgmt_pct": 18.0, "vat_pct": 15.0,
        "since": "2026-09-01",
        "units": [
            {"code": "101A", "old_lid": 490890, "new_lid": 592595},
            {"code": "101B", "old_lid": 477748, "new_lid": 592593},
            {"code": "102A", "old_lid": 473467, "new_lid": 592597},
            {"code": "102B", "old_lid": 472286, "new_lid": 592599},
            {"code": "201A", "old_lid": 477749, "new_lid": 592594},
            {"code": "201B", "old_lid": 477747, "new_lid": 592596},
            {"code": "202A", "old_lid": 473607, "new_lid": 592592},
            {"code": "202B", "old_lid": 473608, "new_lid": 592598},
        ],
    },
}

KINDS = ("income", "expense", "credit")
LOCKED = ("approved", "sent", "paid")

_WA_DEFAULT = ("السلام عليكم {owner} 🌷\n"
               "مرفق كشف حساب {building} لشهر {month}.\n"
               "المبلغ المطلوب: {total} ريال، ويُستحق قبل {due}.\n"
               "الفاتورة الضريبية رقم {daftra} من دفترة.\n"
               "أي استفسار حنا حاضرين 🙏")


def _B():
    return api.B


# ------------------------------- small helpers -------------------------------

def _D(x):
    try:
        return Decimal(str(x if x not in (None, "") else 0))
    except Exception:
        return Decimal("0")


def _q(x):
    return _D(x).quantize(TWO, rounding=ROUND_HALF_UP)


def _f(x):
    return float(_q(x))


def _pdate(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _now():
    return datetime.now(_B().TZ)


def _today():
    return _now().date()


def _month_bounds(mkey):
    y, m = int(mkey[:4]), int(mkey[5:7])
    return date(y, m, 1), date(y, m, monthrange(y, m)[1])


def valid_month(mkey):
    s = str(mkey or "")
    if len(s) != 7 or s[4] != "-" or not (s[:4].isdigit() and s[5:].isdigit()):
        return False
    return 1 <= int(s[5:]) <= 12


def months_since(since, upto):
    """'YYYY-MM' keys from `since` (a date) through `upto` (a date), oldest first."""
    out = []
    y, m = since.year, since.month
    while (y, m) <= (upto.year, upto.month):
        out.append("%04d-%02d" % (y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def building(bid):
    return BUILDINGS.get(str(bid or "").strip())


def _unit(cfg, code):
    for u in cfg["units"]:
        if u["code"] == code:
            return u
    return None


# ---------------------------------- storage ----------------------------------

def _store():
    if _cache["v"] is None:
        v = _B()._load_json(_FILE, {}) or {}
        for k in ("settings", "switch", "months", "audit"):
            v.setdefault(k, {} if k != "audit" else [])
        _cache["v"] = v
    return _cache["v"]


def _save():
    _B()._save_json(_FILE, _cache["v"])


def _audit_building(actor, action, target, before, after, reason=""):
    st = _store()
    st["audit"].append({"at": _now().isoformat(timespec="seconds"), "by": (actor or "")[:60],
                        "action": action, "target": str(target)[:120],
                        "before": before, "after": after, "reason": (reason or "")[:300]})
    if len(st["audit"]) > 600:
        del st["audit"][:len(st["audit"]) - 600]


def _audit_month(rec, actor, action, detail="", reason=""):
    rec.setdefault("audit", []).append({"at": _now().isoformat(timespec="seconds"),
                                        "by": (actor or "")[:60], "action": action,
                                        "detail": str(detail)[:300], "reason": (reason or "")[:300]})
    if len(rec["audit"]) > 300:
        del rec["audit"][:len(rec["audit"]) - 300]


def month_rec(bid, mkey, create=False):
    st = _store()
    k = bid + "|" + mkey
    rec = st["months"].get(k)
    if rec is None and create:
        rec = {"building": bid, "month": mkey, "lines": [], "daftra_no": "", "status": None,
               "versions": [], "audit": []}
        st["months"][k] = rec
    return rec


def settings(bid):
    cfg = building(bid) or {}
    s = dict((_store()["settings"].get(bid) or {}))
    s.setdefault("display_owner", cfg.get("display_owner") or cfg.get("owner") or "")
    s.setdefault("bank_text", "")
    s.setdefault("wa_template", _WA_DEFAULT)
    if not s.get("phone"):
        try:
            from . import owners as OW
            s["phone"] = ((OW._terms_store().get("owners") or {}).get(cfg.get("owner")) or {}).get("phone") or ""
        except Exception:
            s["phone"] = ""
    return s


def _bust(bid=None):
    for k in list(_month_cache):
        if bid is None or k[0] == bid:
            _month_cache.pop(k, None)


# ------------------------------- switch dates -------------------------------

def switch_dates(bid):
    """{unit code: date|None} — the STORED dates only (never touches Hostaway).
    The old-statement hook reads this, so it must stay cheap and offline."""
    sw = (_store()["switch"].get(bid) or {})
    return {u["code"]: _pdate((sw.get(u["code"]) or {}).get("date")) for u in building(bid)["units"]}


def detect_switch_dates(bid):
    """Fill every unit that has no switch date yet with the first check-in on its
    «-O» listing (owner's rule). A found date is STORED, so a later cancellation
    of that first booking can't silently move expenses between documents."""
    cfg = building(bid)
    B = _B()
    with _LOCK:
        sw = _store()["switch"].setdefault(bid, {})
        missing = [u for u in cfg["units"] if not (sw.get(u["code"]) or {}).get("date")]
    if not missing:
        return 0
    since = _pdate(cfg["since"])
    rows = B.fetch_reservations_window(since, _today() + timedelta(days=60)) or []
    confirmed = getattr(B, "CONFIRMED_STATUSES", ("new", "modified"))
    found = {}
    for u in missing:
        days = sorted(str(r.get("arrivalDate"))[:10] for r in rows
                      if r.get("listingMapId") == u["new_lid"] and r.get("arrivalDate")
                      and (r.get("status") or "").lower() in confirmed
                      and str(r.get("arrivalDate"))[:10] >= cfg["since"])
        if days:
            found[u["code"]] = days[0]
    if not found:
        return 0
    with _LOCK:
        sw = _store()["switch"].setdefault(bid, {})
        n = 0
        for code, d in found.items():
            if (sw.get(code) or {}).get("date"):
                continue                       # someone set it meanwhile — theirs wins
            sw[code] = {"date": d, "source": "auto", "at": _now().isoformat(timespec="seconds")}
            _audit_building("system", "switch_auto", bid + "/" + code, None, d,
                            "أول دخول على الإعلان الجديد")
            n += 1
        if n:
            _save()
    if n:
        _bust(bid)
        _owner_cache_bust(cfg)
    return n


def _owner_cache_bust(cfg):
    """The OLD statement's expense set depends on the switch dates — drop its cache."""
    try:
        from . import owners as OW
        OW._invalidate_owner_cache(cfg["owner"])
    except Exception as e:
        print("ownerbill: owner cache bust skipped:", e)


def expense_moved(lid, d):
    """bot.build_owner_report hook: True when a ledger expense on an OLD listing of a
    switched unit is dated on/after that unit's switch date — it belongs to the
    claim now, so the old statement must not deduct it too. Offline + cheap."""
    dd = _pdate(d)
    try:
        lid = int(lid)
    except (TypeError, ValueError):
        return False
    if dd is None:
        return False
    for bid, cfg in BUILDINGS.items():
        for u in cfg["units"]:
            if u["old_lid"] == lid:
                s = switch_dates(bid).get(u["code"])
                return bool(s and dd >= s)
    return False


# --------------------------- registry safety (step 0) ---------------------------

def pin_old_lids(registry, key_fn):
    """Pin each old unit's registry row to its OLD listing id. Before this, 7 of the 8
    rows resolved by NAME, and «101b» also matches «101B-O» — the old statement could
    have silently switched to the owner's own listing. Returns rows changed. Pure."""
    n = 0
    for cfg in BUILDINGS.values():
        for u in cfg["units"]:
            rec = registry.get(key_fn(u["code"]))
            if not rec or (rec.get("owner") or "").strip() != cfg["owner"]:
                continue
            if rec.get("lid") in (None, "", 0):
                rec["lid"] = u["old_lid"]
                n += 1
    return n


def ensure_pinned():
    """One-time, marked (like bot's v21-102b): a deliberate later change stays."""
    B = _B()
    reg = getattr(B, "_owner_registry", None)
    if not reg:
        return False                       # registry not loaded yet — try again later
    with _LOCK:
        st = _store()
        done = st.setdefault("migrations", [])
        if "pin-old-lids-v1" in done:
            return False
        n = pin_old_lids(reg, B._owner_key)
        if n:
            B._save_json("owner_registry.json", reg)
        done.append("pin-old-lids-v1")
        _audit_building("system", "pin_old_lids", "registry", None, n, "تثبيت الإعلانات القديمة")
        _save()
    if n:
        for cfg in BUILDINGS.values():
            _owner_cache_bust(cfg)
    return bool(n)


def guards(bid):
    """What the accountant must see before trusting either document."""
    cfg = building(bid)
    B = _B()
    out = []
    listings = B.get_listings_map() or {}
    new_lids = {u["new_lid"]: u["code"] for u in cfg["units"]}
    rows = api._registry_rows()
    for u in cfg["units"]:
        rec = None
        for r in rows:
            if B._owner_key(r.get("apartment") or "") == B._owner_key(u["code"]):
                rec = r
                break
        if rec is None:
            out.append({"level": "warn", "code": "old_unit_missing", "unit": u["code"]})
            continue
        try:
            pinned = int(rec.get("lid")) if rec.get("lid") not in (None, "") else None
        except (TypeError, ValueError):
            pinned = None
        if pinned != u["old_lid"]:
            out.append({"level": "warn", "code": "old_unit_not_pinned", "unit": u["code"],
                        "detail": pinned})
    for r in rows:
        try:
            lid = B._owner_resolve_lid(r, listings)
        except Exception:
            lid = None
        if lid in new_lids:
            out.append({"level": "bad", "code": "new_listing_in_statement",
                        "unit": new_lids[lid], "detail": r.get("apartment")})
    for u in cfg["units"]:
        if u["new_lid"] not in listings:
            out.append({"level": "warn", "code": "new_listing_missing", "unit": u["code"]})
    return out


# --------------------------------- the math ---------------------------------

def _ledger_expenses(cfg, start, end, sw):
    """Posted ledger expenses of each unit for the claim: tagged to the NEW listing
    (any date in the month), or to the OLD listing on/after the switch date."""
    B = _B()
    by_lid = {}                                      # ids may arrive as text — compare as int
    for u in cfg["units"]:
        by_lid[u["old_lid"]] = (u, "old")
        by_lid[u["new_lid"]] = (u, "new")
    out = {u["code"]: [] for u in cfg["units"]}
    for e in list((getattr(B, "_expenses", None) or {}).values()):
        try:
            hit = by_lid.get(int(e.get("listing_id")))
        except (TypeError, ValueError):
            hit = None
        if not hit:
            continue
        try:
            if not B._exp_posted_to_hostaway(e):
                continue
        except Exception:
            continue
        d = _pdate(e.get("expense_date"))
        if d is None or d < start or d > end:
            continue
        u, side = hit
        s = sw.get(u["code"])
        if side == "old" and (s is None or d < s):
            continue                                   # still the old statement's
        out[u["code"]].append({
            "id": e.get("id"), "date": d.isoformat(), "amount": _f(e.get("amount")),
            "category": e.get("category") or "",
            "description": (e.get("note") or e.get("maintenance_type") or "")[:200],
            "receipt_url": (e.get("receipt_link") or "").strip() or None,
            "listing": side, "unit": u["code"]})
    for v in out.values():
        v.sort(key=lambda x: (x["date"], str(x["id"])))
    return out


def _initial(name):
    n = (name or "").strip()
    return (n[0] + ".") if n else "—"


def compute_month(bid, mkey):
    """The live claim for one month. Pure READ. Totals are sums of per-unit values
    rounded to the halala, so the PDF table adds up exactly."""
    cfg = building(bid)
    B = _B()
    start, end = _month_bounds(mkey)
    pct, vat_pct = _D(cfg["mgmt_pct"]), _D(cfg["vat_pct"])
    # Expenses depend on the switch dates — never compute (or approve!) on dates that
    # haven't been detected yet just because nobody opened the board first.
    try:
        detect_switch_dates(bid)
    except Exception as e:
        print("ownerbill: switch detection skipped:", e)
    listings = B.get_listings_map() or {}
    sw = switch_dates(bid)
    exp_by_unit = _ledger_expenses(cfg, start, end, sw)
    units, blockers, warnings = [], [], []
    degraded = False
    T = {"income": Decimal(0), "fee": Decimal(0), "vat": Decimal(0), "expenses": Decimal(0),
         "bookings": 0, "nights": 0}
    for u in cfg["units"]:
        rep = B.build_owner_report(u["new_lid"], start, end, cfg["mgmt_pct"], None,
                                   expenses=[], cleaning={"type": "ours", "amount": 0}, adjust={})
        if rep.get("degraded"):
            degraded = True
        bookings, excluded = [], []
        for l in rep.get("resv_lines") or []:
            if l.get("needs_review") or (l.get("channel") or "") != "airbnb" or l.get("income") is None:
                why = l.get("exclude_reason") or ("non_airbnb" if (l.get("channel") or "") != "airbnb"
                                                  else "needs_review")
                excluded.append({"id": l.get("id"), "checkin": l.get("checkin"), "checkout": l.get("checkout"),
                                 "guest": _initial(l.get("guest")), "channel": l.get("channel"),
                                 "reason": why, "reference": l.get("reference_total")})
                blockers.append({"code": why, "unit": u["code"], "id": l.get("id")})
                continue
            amt = _q(_D(l.get("income")) + _D(l.get("extras")))
            bookings.append({"id": l.get("id"), "checkin": l.get("checkin"), "checkout": l.get("checkout"),
                             "nights": int(l.get("nights") or 0), "guest": _initial(l.get("guest")),
                             "amount": float(amt), "refund": l.get("refund") or 0})
        for l in rep.get("refunded_lines") or []:
            excluded.append({"id": l.get("id"), "checkin": l.get("checkin"), "checkout": l.get("checkout"),
                             "guest": _initial(l.get("guest")), "channel": l.get("channel"),
                             "reason": l.get("kind") or "cancelled", "reference": l.get("reference_total")})
            if l.get("kind") == "cancelled_money_signal":
                warnings.append({"code": "cancelled_money_signal", "unit": u["code"], "id": l.get("id")})
        bookings.sort(key=lambda b: (str(b["checkin"]), str(b["id"])))
        income = sum((_D(b["amount"]) for b in bookings), Decimal(0))
        fee = _q(income * pct / 100)
        vat = _q(fee * vat_pct / 100)
        exps = exp_by_unit.get(u["code"]) or []
        exp_total = sum((_D(e["amount"]) for e in exps), Decimal(0))
        nights = sum(b["nights"] for b in bookings)
        s = sw.get(u["code"])
        units.append({"code": u["code"], "old_lid": u["old_lid"], "new_lid": u["new_lid"],
                      "listing": listings.get(u["new_lid"]) or "",
                      "switch_date": s.isoformat() if s else None,
                      "bookings": bookings, "excluded": excluded, "expenses": exps,
                      "n_bookings": len(bookings), "nights": nights,
                      "income": _f(income), "fee": float(fee), "vat": float(vat),
                      "expenses_total": _f(exp_total), "due": _f(fee + vat + exp_total)})
        T["income"] += income; T["fee"] += fee; T["vat"] += vat; T["expenses"] += exp_total
        T["bookings"] += len(bookings); T["nights"] += nights
    if degraded:
        blockers.append({"code": "degraded", "unit": "", "id": None})
    return {"building": bid, "month": mkey,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "mgmt_pct": cfg["mgmt_pct"], "vat_pct": cfg["vat_pct"],
            "units": units, "blockers": blockers, "warnings": warnings, "degraded": degraded,
            "base": {k: (_f(v) if isinstance(v, Decimal) else v) for k, v in T.items()},
            "computed_at": _now().isoformat(timespec="seconds")}


def apply_lines(comp, lines, cfg):
    """Fold the human lines into the computed month → final totals. Pure."""
    pct, vat_pct = _D(cfg["mgmt_pct"]), _D(cfg["vat_pct"])
    base = comp["base"]
    m_inc = sum((_D(l["amount"]) for l in lines if l["kind"] == "income"), Decimal(0))
    m_exp = sum((_D(l["amount"]) for l in lines if l["kind"] == "expense"), Decimal(0))
    m_crd = sum((_D(l["amount"]) for l in lines if l["kind"] == "credit"), Decimal(0))
    inc_fee = _q(m_inc * pct / 100)
    inc_vat = _q(inc_fee * vat_pct / 100)
    fee = _D(base["fee"]) + inc_fee
    vat = _D(base["vat"]) + inc_vat
    expenses = _D(base["expenses"]) + m_exp
    due = fee + vat + expenses - m_crd
    return {"income": _f(_D(base["income"]) + m_inc), "airbnb_income": _f(base["income"]),
            "manual_income": _f(m_inc), "fee": _f(fee), "vat": _f(vat),
            "manual_income_fee": float(inc_fee), "manual_income_vat": float(inc_vat),
            "ledger_expenses": _f(base["expenses"]), "manual_expenses": _f(m_exp),
            "expenses": _f(expenses), "credits": _f(m_crd), "due": _f(due),
            "bookings": base["bookings"], "nights": base["nights"]}


def _month_over(mkey):
    return _month_bounds(mkey)[1] < _today()


def effective_status(rec, comp, mkey):
    st = (rec or {}).get("status")
    if st == "paid":
        return "paid"
    if st == "sent":
        due = _pdate((rec or {}).get("due"))
        return "overdue" if (due and _today() > due) else "sent"
    if st == "approved":
        return "approved"
    if not _month_over(mkey):
        return "running"
    if comp and comp.get("blockers"):
        return "needs_review"
    return "ready"


def approve_problems(rec, comp, mkey):
    probs = []
    if (rec or {}).get("status") in LOCKED:
        probs.append("already_locked")
    if not _month_over(mkey):
        probs.append("month_not_over")
    if comp.get("blockers"):
        probs.append("blockers")
    if not str((rec or {}).get("daftra_no") or "").strip():
        probs.append("daftra_missing")
    return probs


def claim_no(cfg, mkey):
    return "OJ-%s-%s" % (cfg["code"], mkey)


def _live(bid, mkey, fresh=False):
    k = (bid, mkey)
    hit = _month_cache.get(k)
    now = datetime.now().timestamp()
    if hit and not fresh and now - hit[0] < _MONTH_TTL:
        return hit[1]
    comp = compute_month(bid, mkey)
    _month_cache[k] = (now, comp)
    return comp


def month_view(bid, mkey, fresh=False):
    """What the screen and the PDF render: the FROZEN version when approved, else live."""
    cfg = building(bid)
    rec = month_rec(bid, mkey) or {"lines": [], "daftra_no": "", "status": None, "versions": [], "audit": []}
    frozen = None
    if rec.get("status") in LOCKED and rec.get("versions"):
        frozen = rec["versions"][-1]
    if frozen:
        snap = frozen["snapshot"]
        comp, lines, totals = snap["comp"], snap["lines"], snap["totals"]
        daftra = snap.get("daftra_no") or rec.get("daftra_no") or ""
        sett = snap.get("settings") or settings(bid)
    else:
        comp = _live(bid, mkey, fresh=fresh)
        lines = list(rec.get("lines") or [])
        totals = apply_lines(comp, lines, cfg)
        daftra = rec.get("daftra_no") or ""
        sett = settings(bid)
    status = effective_status(rec, comp, mkey)
    return {"building": public_building(bid), "month": mkey, "claim_no": claim_no(cfg, mkey),
            "status": status, "frozen": bool(frozen),
            "version": frozen["v"] if frozen else None,
            "approved_at": frozen["at"] if frozen else None,
            "approved_by": frozen["by"] if frozen else None,
            "comp": comp, "lines": lines, "totals": totals, "daftra_no": daftra,
            "settings": {"display_owner": sett.get("display_owner"), "bank_text": sett.get("bank_text"),
                         "phone": settings(bid).get("phone"), "wa_template": settings(bid).get("wa_template")},
            "sent_at": rec.get("sent_at"), "due": rec.get("due"), "paid_at": rec.get("paid_at"),
            "paid_ref": rec.get("paid_ref"),
            "versions": [{"v": v["v"], "at": v["at"], "by": v["by"]} for v in rec.get("versions") or []],
            "audit": list(rec.get("audit") or [])[-60:],
            "approve_problems": ([] if frozen else approve_problems(rec, comp, mkey))}


def public_building(bid):
    cfg = building(bid)
    sw = (_store()["switch"].get(bid) or {})
    return {"id": cfg["id"], "code": cfg["code"], "name_ar": cfg["name_ar"], "name_en": cfg["name_en"],
            "owner": cfg["owner"], "mgmt_pct": cfg["mgmt_pct"], "vat_pct": cfg["vat_pct"],
            "since": cfg["since"],
            "units": [{"code": u["code"], "old_lid": u["old_lid"], "new_lid": u["new_lid"],
                       "switch_date": (sw.get(u["code"]) or {}).get("date"),
                       "switch_source": (sw.get(u["code"]) or {}).get("source"),
                       "switch_by": (sw.get(u["code"]) or {}).get("by"),
                       "switch_reason": (sw.get(u["code"]) or {}).get("reason")}
                      for u in cfg["units"]]}


def board(bid):
    """The month board: one row per month since the building switched."""
    cfg = building(bid)
    ensure_pinned()
    try:
        detect_switch_dates(bid)
    except Exception as e:
        print("ownerbill: switch detection skipped:", e)
    months = months_since(_pdate(cfg["since"]), _today())
    rows = []
    outstanding = Decimal(0)
    for m in reversed(months):
        v = month_view(bid, m)
        rows.append({"month": m, "status": v["status"], "income": v["totals"]["income"],
                     "due": v["totals"]["due"], "due_date": v["due"], "daftra_no": v["daftra_no"],
                     "version": v["version"], "blockers": len(v["comp"].get("blockers") or []),
                     "bookings": v["totals"]["bookings"]})
        if v["status"] in ("sent", "overdue"):
            outstanding += _D(v["totals"]["due"])
    return {"ok": True, "building": public_building(bid), "settings": settings(bid),
            "guards": guards(bid), "months": rows, "outstanding": _f(outstanding),
            "audit": list(_store()["audit"])[-40:]}


def buildings_list():
    return [{"id": b["id"], "name_ar": b["name_ar"], "name_en": b["name_en"],
             "owner": b["owner"], "units": len(b["units"])} for b in BUILDINGS.values()]


# ---------------------------------- writes ----------------------------------

def _req(body, bid_key="b"):
    bid = str(body.get(bid_key) or "").strip()
    if not building(bid):
        return None, None, ({"error": "unknown_building"}, 400)
    mkey = str(body.get("m") or "").strip()
    if mkey and not valid_month(mkey):
        return None, None, ({"error": "bad_month"}, 400)
    return bid, mkey, None


def _locked_err():
    return {"error": "locked", "message_ar": "الشهر معتمد ومقفل — افتحه من جديد أول (مدير)",
            "message_en": "This month is approved and locked — reopen it first (admin)."}, 409


def line_add(request, body):
    bid, mkey, err = _req(body)
    if err:
        return err
    if not mkey:
        return {"error": "bad_month"}, 400
    cfg = building(bid)
    kind = str(body.get("kind") or "")
    if kind not in KINDS:
        return {"error": "bad_kind"}, 400
    label = str(body.get("label") or "").strip()[:160]
    reason = str(body.get("reason") or "").strip()[:300]
    unit = str(body.get("unit") or "").strip()
    try:
        amount = _q(body.get("amount"))
    except Exception:
        amount = Decimal(0)
    if not label:
        return {"error": "label_required", "message_ar": "اكتب وصف البند", "message_en": "Describe the line"}, 400
    if amount <= 0:
        return {"error": "bad_amount", "message_ar": "المبلغ لازم يكون أكبر من صفر",
                "message_en": "Amount must be above zero"}, 400
    if len(reason) < 3:
        return {"error": "reason_required", "message_ar": "السبب إلزامي", "message_en": "A reason is required"}, 400
    if unit and not _unit(cfg, unit):
        return {"error": "bad_unit"}, 400
    with _LOCK:
        rec = month_rec(bid, mkey, create=True)
        if rec.get("status") in LOCKED:
            return _locked_err()
        line = {"id": "ln-" + uuid.uuid4().hex[:10], "kind": kind, "unit": unit, "label": label,
                "amount": float(amount), "reason": reason, "by": api.actor(request),
                "at": _now().isoformat(timespec="seconds")}
        rec["lines"].append(line)
        _audit_month(rec, api.actor(request), "line_add",
                     "%s %s %s %s" % (kind, unit or "-", label, line["amount"]), reason)
        _save()
    return {"ok": True, "line": line, "view": month_view(bid, mkey)}, 200


def line_del(request, body):
    bid, mkey, err = _req(body)
    if err:
        return err
    reason = str(body.get("reason") or "").strip()[:300]
    if len(reason) < 3:
        return {"error": "reason_required", "message_ar": "السبب إلزامي", "message_en": "A reason is required"}, 400
    with _LOCK:
        rec = month_rec(bid, mkey)
        if not rec:
            return {"error": "not_found"}, 404
        if rec.get("status") in LOCKED:
            return _locked_err()
        lid = str(body.get("id") or "")
        keep = [l for l in rec["lines"] if l["id"] != lid]
        if len(keep) == len(rec["lines"]):
            return {"error": "not_found"}, 404
        gone = [l for l in rec["lines"] if l["id"] == lid][0]
        rec["lines"] = keep
        _audit_month(rec, api.actor(request), "line_del",
                     "%s %s %s" % (gone["kind"], gone["label"], gone["amount"]), reason)
        _save()
    return {"ok": True, "view": month_view(bid, mkey)}, 200


def daftra_set(request, body):
    bid, mkey, err = _req(body)
    if err:
        return err
    if not mkey:
        return {"error": "bad_month"}, 400
    no = str(body.get("number") or "").strip()[:40]
    with _LOCK:
        rec = month_rec(bid, mkey, create=True)
        if rec.get("status") in LOCKED:
            return _locked_err()
        before = rec.get("daftra_no") or ""
        rec["daftra_no"] = no
        _audit_month(rec, api.actor(request), "daftra_no", "%s → %s" % (before or "—", no or "—"))
        _save()
    return {"ok": True, "view": month_view(bid, mkey)}, 200


def approve(request, body):
    bid, mkey, err = _req(body)
    if err:
        return err
    if not mkey:
        return {"error": "bad_month"}, 400
    cfg = building(bid)
    comp = compute_month(bid, mkey)           # never approve a 10-minute-old number
    with _LOCK:
        rec = month_rec(bid, mkey, create=True)
        probs = approve_problems(rec, comp, mkey)
        if probs:
            return {"error": "cannot_approve", "problems": probs,
                    "message_ar": "ما ينفع الاعتماد: " + "، ".join(_PROB_AR.get(p, p) for p in probs),
                    "message_en": "Cannot approve: " + ", ".join(probs)}, 409
        lines = [dict(l) for l in rec.get("lines") or []]
        totals = apply_lines(comp, lines, cfg)
        s = settings(bid)
        v = len(rec.get("versions") or []) + 1
        rec.setdefault("versions", []).append({
            "v": v, "at": _now().isoformat(timespec="seconds"), "by": api.actor(request),
            "snapshot": {"comp": comp, "lines": lines, "totals": totals,
                         "daftra_no": rec.get("daftra_no") or "",
                         "settings": {"display_owner": s.get("display_owner"), "bank_text": s.get("bank_text")}}})
        rec["status"] = "approved"
        _audit_month(rec, api.actor(request), "approve", "نسخة %d — المطلوب %s" % (v, totals["due"]))
        _save()
    _month_cache[(bid, mkey)] = (datetime.now().timestamp(), comp)
    return {"ok": True, "view": month_view(bid, mkey)}, 200


_PROB_AR = {"already_locked": "الشهر معتمد من قبل", "month_not_over": "الشهر ما خلص",
            "blockers": "فيه حجوزات تحتاج مراجعة", "daftra_missing": "رقم فاتورة دفترة ناقص"}


def status_set(request, body):
    """sent | paid | unpaid | reopen. unpaid + reopen are admin-only and need a reason."""
    bid, mkey, err = _req(body)
    if err:
        return err
    if not mkey:
        return {"error": "bad_month"}, 400
    action = str(body.get("action") or "")
    reason = str(body.get("reason") or "").strip()[:300]
    who = api.actor(request)
    with _LOCK:
        rec = month_rec(bid, mkey)
        st = (rec or {}).get("status")
        if action == "sent":
            if st != "approved":
                return {"error": "not_approved", "message_ar": "اعتمد الشهر أول",
                        "message_en": "Approve the month first"}, 409
            rec["status"] = "sent"
            rec["sent_at"] = _today().isoformat()
            rec["sent_by"] = who
            rec["due"] = (_today() + timedelta(days=DUE_DAYS)).isoformat()
            _audit_month(rec, who, "sent", "يستحق " + rec["due"])
        elif action == "paid":
            if st not in ("approved", "sent"):
                return {"error": "not_billable", "message_ar": "الشهر لازم يكون معتمد أو مرسل",
                        "message_en": "The month must be approved or sent"}, 409
            pd = _pdate(body.get("paid_date")) or _today()
            if pd > _today():
                return {"error": "future_date"}, 400
            rec["status"] = "paid"
            rec["paid_at"] = pd.isoformat()
            rec["paid_by"] = who
            rec["paid_ref"] = str(body.get("ref") or "").strip()[:120]
            _audit_month(rec, who, "paid", "%s %s" % (rec["paid_at"], rec["paid_ref"]))
        elif action in ("unpaid", "reopen"):
            if not api.is_admin(request):
                return {"error": "admin_only", "message_ar": "هذي للمدير فقط", "message_en": "Admin only"}, 403
            if len(reason) < 3:
                return {"error": "reason_required", "message_ar": "السبب إلزامي",
                        "message_en": "A reason is required"}, 400
            if action == "unpaid":
                if st != "paid":
                    return {"error": "not_paid"}, 409
                rec["status"] = "sent" if rec.get("sent_at") else "approved"
                rec["paid_at"] = rec["paid_by"] = rec["paid_ref"] = None
                _audit_month(rec, who, "unpaid", "", reason)
            else:
                if st not in LOCKED:
                    return {"error": "not_locked"}, 409
                rec["status"] = None
                rec["sent_at"] = rec["due"] = rec["paid_at"] = rec["paid_ref"] = None
                _audit_month(rec, who, "reopen", "النسخ السابقة محفوظة", reason)
        else:
            return {"error": "bad_action"}, 400
        _save()
    return {"ok": True, "view": month_view(bid, mkey)}, 200


def switch_set(request, body):
    bid, _m, err = _req(body)
    if err:
        return err
    cfg = building(bid)
    code = str(body.get("unit") or "").strip()
    if not _unit(cfg, code):
        return {"error": "bad_unit"}, 400
    d = _pdate(body.get("date"))
    if d is None:
        return {"error": "bad_date"}, 400
    reason = str(body.get("reason") or "").strip()[:300]
    if len(reason) < 3:
        return {"error": "reason_required", "message_ar": "السبب إلزامي", "message_en": "A reason is required"}, 400
    with _LOCK:
        sw = _store()["switch"].setdefault(bid, {})
        before = (sw.get(code) or {}).get("date")
        sw[code] = {"date": d.isoformat(), "source": "manual", "by": api.actor(request),
                    "reason": reason, "at": _now().isoformat(timespec="seconds")}
        _audit_building(api.actor(request), "switch_set", bid + "/" + code, before, d.isoformat(), reason)
        _save()
    _bust(bid)
    _owner_cache_bust(cfg)
    return {"ok": True, "building": public_building(bid)}, 200


def settings_set(request, body):
    bid, _m, err = _req(body)
    if err:
        return err
    with _LOCK:
        cur = _store()["settings"].setdefault(bid, {})
        before = dict(cur)
        for k, lim in (("bank_text", 400), ("display_owner", 120), ("wa_template", 1000)):
            if k in body:
                cur[k] = str(body.get(k) or "").strip()[:lim]
        if "phone" in body:
            cur["phone"] = "".join(ch for ch in str(body.get("phone") or "") if ch.isdigit() or ch == "+")[:18]
        _audit_building(api.actor(request), "settings", bid, before, dict(cur))
        _save()
    return {"ok": True, "settings": settings(bid)}, 200
