# -*- coding: utf-8 -*-
"""
monthly.ejar — the annual-rent reference and the data trust ladder.

PURE. Rows arrive as arguments; db.py does the reading. Same discipline as
engine.py, and the reason both can be argued with in a unit test.

WHY THIS MODULE IS SUSPICIOUS BY DEFAULT
AirDNA was checked against our own reality and found wrong — it scrapes calendars
and infers occupancy from them. So no external number is trusted because of who
published it. It is calibrated against ours first, and if it cannot prove it
describes a TRANSACTION rather than an advertisement, it is not evidence of a
price at all. A landlord's asking price is a hope; only a signed contract is a
market rate.

    gold    our own Hostaway history      may set a price shown to anyone
    silver  Ejar / Sakani / REGA index    annual-lease reference only
    bronze  AirDNA, Bayut, عقار           direction and trend, never a quote

EJAR IS CONTEXT, NOT A GATE (owner, 2026-08-19). Ouja's owners are on revenue
guarantees; they are not choosing between a yearly lease and us, so a gate built
on that comparison answered a question nobody asks. Nothing in this module may
bind a price. What it produces is a MULTIPLE — our monthly price against the
district's annual-equivalent month — shown so a 2.8x can be recognised as
plausible for furnished, serviced, utilities-included and flexible, and an 8x can
be caught before an owner sees it.

Which is also why `base` for the model price is drawn from OUR OWN realised
history and never from here. An annual-lease index feeding a variable named
base_rate would be this module binding the price under a different name, and
nobody reading that call site would see it happen.
"""

import datetime

# ─────────────────────────────── the tiers ───────────────────────────────

GOLD_SOURCES = ("ouja", "hostaway", "own")
# Matched by PREFIX after normalising, so the same publisher reached through a
# differently-named product — sakani, sakani_rei, «المؤشر الإيجاري» — lands in the
# same tier. An exact-match list silently demoted an entire real dataset to
# bronze once already, and a trust ladder that fails closed on a spelling is not
# measuring trust, it is measuring string equality.
SILVER_PREFIXES = ("sakani", "rega", "ejar", "manual")

_TIER_RANK = {"gold": 3, "silver": 2, "bronze": 1}

# The published rental index uses 200 registered transactions as its own
# threshold for reporting a district. Borrowing it means our thin-data warning
# fires at the same place the source's does.
MIN_EJAR_TXN = 200
MIN_CALIB_PAIRS = 3
EJAR_STALE_DAYS = 180

# Calibration bands. Between 10% and 25% we do not discard the source — we learn
# how wrong it is and correct for it, which is worth more than throwing it away.
MAPE_ALLOWED = 0.10
MAPE_CORRECTED = 0.25

# The owner's costs under a normal annual lease. Taken from the owner report's
# reference_data.EJAR so this codebase holds ONE set of lease terms rather than
# two that quietly disagree; a test asserts they stay equal.
DEFAULT_TERMS = {
    "broker_pct": 0.025,          # agency commission
    "vacancy_pct": 0.05,          # void between tenants, ~18 days
    "owner_maintenance": 4000.0,  # AC service and repairs the owner carries
    "admin_fees": 400.0,          # Ejar registration + municipal admin
}


def tier_for(source, obs_type="transacted"):
    """An ASKING price is bronze whatever published it. Source prestige does not
    turn an advertisement into a transaction."""
    if str(obs_type or "").strip().lower() != "transacted":
        return "bronze"
    s = "".join(ch for ch in str(source or "").strip().lower()
                if ch.isalnum() or ch == "_")
    if s in GOLD_SOURCES:
        return "gold"
    if any(s == p or s.startswith(p + "_") or s.startswith(p) for p in SILVER_PREFIXES):
        return "silver"
    return "bronze"


def may_set_price(tier):
    """Only our own transacted history may appear as a price to an owner or a
    guest."""
    return tier == "gold"


def may_reference_annual(tier):
    """Silver is good enough to say what a comparable annual lease fetches — that
    is exactly what the published index is for."""
    return _TIER_RANK.get(tier, 0) >= _TIER_RANK["silver"]


# ───────────────────────────── calibration ─────────────────────────────

def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def calibrate(ours, theirs):
    """Compare a source against our own numbers for the same cells.

    Returns mape, a bias_factor that maps their scale onto ours, and a verdict.
    Fewer than MIN_CALIB_PAIRS pairs is 'uncalibrated' rather than 'allowed':
    two numbers agreeing is a coincidence, not evidence.
    """
    pairs = []
    for a, b in zip(list(ours or []), list(theirs or [])):
        o, t = _num(a), _num(b)
        if o is None or t is None or o <= 0:
            continue
        pairs.append((o, t))

    n = len(pairs)
    if n == 0:
        return {"mape": None, "bias_factor": 1.0, "n_obs": 0,
                "trust_tier": "uncalibrated"}

    mape = sum(abs(t - o) / o for (o, t) in pairs) / n
    ratio = sum(t for (_o, t) in pairs) / sum(o for (o, _t) in pairs)

    if n < MIN_CALIB_PAIRS:
        tier, bias = "uncalibrated", 1.0
    elif mape <= MAPE_ALLOWED:
        tier, bias = "allowed", 1.0
    elif mape <= MAPE_CORRECTED:
        tier, bias = "corrected", (1.0 / ratio if ratio else 1.0)
    else:
        tier, bias = "blocked", 1.0

    return {"mape": mape, "bias_factor": bias, "n_obs": n, "trust_tier": tier}


def usable(calibration):
    """A blocked or uncalibrated cell contributes nothing to a price. Ever."""
    return (calibration or {}).get("trust_tier") in ("allowed", "corrected")


# ─────────────────────────── the reference row ───────────────────────────

def _days_between(a, b):
    try:
        d1 = datetime.date(*[int(x) for x in str(a)[:10].split("-")])
        d2 = datetime.date(*[int(x) for x in str(b)[:10].split("-")])
        return (d2 - d1).days
    except (ValueError, TypeError):
        return None


def reference(row, today=None):
    """One stored reference row -> what we may do with it, and what to warn about.

    `usable` False with `annual_rent` None is the honest shape of "we do not
    know". The caller renders the market context as UNAVAILABLE — it never
    substitutes a zero, and it never lets the absence pass unremarked.
    """
    today = today or datetime.date.today().isoformat()

    if not row:
        return {"usable": False, "annual_rent": None, "tier": None,
                "warnings": ["ejar_missing"], "context_confidence_penalty": True,
                "as_of": None, "txn_count": None,
                "message_ar": "ما عندنا مرجع إيجار سنوي لهذا الحي — "
                              "مقارنة السوق غير متاحة (ما تأثّر السعر)",
                "message_en": "No annual-lease reference for this district — "
                              "market context unavailable (the price is unaffected)"}

    warnings = []
    rent = _num(row.get("annual_rent"))
    tier = tier_for(row.get("source"), row.get("obs_type"))

    if rent is None or rent <= 0:
        warnings.append("ejar_invalid")
    if str(row.get("obs_type") or "").strip().lower() != "transacted":
        warnings.append("asking_not_transacted")
    if not may_reference_annual(tier):
        if "asking_not_transacted" not in warnings:
            warnings.append("source_not_trusted")

    txn = _num(row.get("txn_count"))
    if txn is None or txn < MIN_EJAR_TXN:
        warnings.append("thin_district")

    age = _days_between(row.get("as_of"), today)
    if age is None:
        warnings.append("ejar_undated")
    elif age > EJAR_STALE_DAYS:
        warnings.append("ejar_stale")

    # thin_district BLOCKS. Owner's rule, 2026-08-19, and it matches §4: below the
    # sample gate we show a RANGE, never a number. With «النطاق السعري» not yet
    # captured a thin cell has no range either, so it is simply unusable — and the
    # honest answer is to say which districts still have no reference rather than
    # to lower the threshold until they all pass.
    blocking = {"ejar_invalid", "asking_not_transacted",
                "source_not_trusted", "ejar_undated", "thin_district"}
    usable_now = not (blocking & set(warnings))

    return {
        "usable": usable_now,
        "annual_rent": rent if usable_now else None,
        "tier": tier,
        "warnings": warnings,
        # Costs a level of confidence IN THE MARKET CONTEXT ONLY. It must never
        # reach the price's own confidence: Ejar no longer feeds the price, and a
        # number that does not feed a price has no business degrading how
        # confidently that price is stated.
        "context_confidence_penalty": bool({"ejar_stale", "thin_district"} & set(warnings)),
        "as_of": row.get("as_of"),
        "txn_count": None if txn is None else int(txn),
    }


# ───────────────────── the owner's annual-lease position ─────────────────────

def terms(**overrides):
    t = dict(DEFAULT_TERMS)
    for k, v in (overrides or {}).items():
        if k in t:
            f = _num(v)
            if f is not None and f >= 0:
                t[k] = f
    return t


# ── NOT IN THE PRICING PATH ──────────────────────────────────────────────────
# Kept, not deleted: written and tested, and wanted for owner acquisition later.
# But it must not find a quiet way back into a price, so engine.py never imports
# it and a test asserts the pricing path cannot reach it.

def owner_annual_net(ejar_annual, term_overrides=None):
    """What the owner ACTUALLY keeps from a normal annual lease.

    OUT OF THE PRICING PATH (owner, 2026-08-19). For owner-acquisition material,
    never for setting a price.

    An owner weighing two paths compares what reaches their pocket, not the
    headline rent. Quoting them the gross would flatter our own side of the
    comparison, which is the one dishonesty this whole feature exists to avoid.
    """
    rent = _num(ejar_annual)
    if rent is None or rent <= 0:
        return None
    t = terms(**(term_overrides or {}))
    return (rent * (1.0 - t["broker_pct"] - t["vacancy_pct"])
            - t["owner_maintenance"] - t["admin_fees"])


def gate_report(rows, today=None):
    """Every stored cell, sorted into what may be used and what the sample gate
    turned away — and WHY. The blocked list is the useful half: it names the
    districts that still have no usable annual-lease reference."""
    usable_rows, blocked = [], []
    for row in (rows or []):
        r = reference(row, today=today)
        entry = {
            "district": row.get("district"), "unit_type": row.get("unit_type"),
            "bedrooms": row.get("bedrooms"), "annual_rent": row.get("annual_rent"),
            "txn_count": row.get("txn_count"), "warnings": r["warnings"],
            "tier": r["tier"],
        }
        (usable_rows if r["usable"] else blocked).append(entry)
    return {"usable": usable_rows, "blocked": blocked,
            "n_usable": len(usable_rows), "n_blocked": len(blocked)}


def inversions(rows):
    """Cells where MORE bedrooms fetch LESS rent than fewer bedrooms elsewhere.
    Surfaced, never smoothed: it may be perfectly real — different district,
    different stock — but a pricing model that quietly averages it away is a
    model nobody can interrogate."""
    apts = [r for r in (rows or [])
            if r.get("unit_type") == "شقة" and r.get("bedrooms")]
    out = []
    for a in apts:
        for b in apts:
            if a is b:
                continue
            if (a.get("bedrooms") or 0) > (b.get("bedrooms") or 0) and \
                    _num(a.get("annual_rent")) is not None and \
                    _num(b.get("annual_rent")) is not None and \
                    _num(a["annual_rent"]) < _num(b["annual_rent"]):
                out.append({
                    "more_bedrooms": {"district": a.get("district"),
                                      "bedrooms": a.get("bedrooms"),
                                      "annual_rent": a.get("annual_rent")},
                    "fewer_bedrooms": {"district": b.get("district"),
                                       "bedrooms": b.get("bedrooms"),
                                       "annual_rent": b.get("annual_rent")},
                })
    return out


def market_context(monthly_price, row, today=None):
    """Our monthly price as a multiple of the district's annual-equivalent month.

    INFORMATIONAL. Nothing here may bind, adjust or veto a price — it is a number
    to look at before an owner does. A 2.8x is plausible for furnished, serviced,
    utilities-included and flexible-term. An 8x is a question, and the point of
    computing it is to be asked that question early.
    """
    r = reference(row, today=today)
    price = _num(monthly_price)
    if not r["usable"] or price is None or price <= 0:
        return {"available": False, "multiple": None, "annual_equivalent_month": None,
                "annual_rent": None, "warnings": r["warnings"], "tier": r["tier"],
                "as_of": r.get("as_of"), "txn_count": r.get("txn_count"),
                "binding": False,
                "message_ar": r.get("message_ar") or "مرجع السوق غير متاح لهذا الحي",
                "message_en": r.get("message_en") or "No market reference for this district"}
    aem = r["annual_rent"] / 12.0
    return {
        "available": True,
        "annual_rent": r["annual_rent"],
        "annual_equivalent_month": aem,
        "multiple": price / aem,
        "warnings": r["warnings"],
        "tier": r["tier"],
        "as_of": r.get("as_of"),
        "txn_count": r.get("txn_count"),
        # Stated on the object itself so no caller has to remember it.
        "binding": False,
        "message_ar": "للسياق فقط — ما يدخل في حساب السعر",
        "message_en": "Context only — does not enter the price calculation",
    }
