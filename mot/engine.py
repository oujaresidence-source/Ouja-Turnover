# -*- coding: utf-8 -*-
"""
mot.engine — PURE. No DB, no HTTP, no clock it wasn't handed.

Everything the pages and the close-the-round transaction need to compute lives here so it
can be driven with plain dicts in tests:

    components_for(has_pool)                       -> [component dict]
    score(results, has_pool)                       -> the TWO percentages + counts + denominator
    blockers(results, has_pool)                    -> structural failures
    can_export_evidence(round, results, has_pool)  -> (bool, reason_ar)
    default_qty(component, unit_meta)              -> int
    quote_lines(results, prices, unit_meta, has_pool, today=None)
                                                   -> owner / ouja_products / ouja_works /
                                                      documents / blocked / unpriced / stale
    quote_items(owner_lines)                       -> items[] for /api/quotes/save

`results` is {comp_key: {"state": unchecked|available|missing, "qty":?, "billed_to":?}}.
`prices` is {comp_key: float} or {comp_key: {"price_sar":, "set_at":}}.
"""
from datetime import date, datetime

from . import catalogue as C

STATES = ("unchecked", "available", "missing")
STALE_DAYS = 90
RECHECK_DAYS = 14
WORKS_SEPARATOR = "— أعمال وتركيبات (تحتاج فنّي) —"


def components_for(has_pool):
    return C.components(bool(has_pool))


def _state(results, key):
    r = (results or {}).get(key) or {}
    s = r.get("state") or "unchecked"
    return s if s in STATES else "unchecked"


def score(results, has_pool):
    comps = components_for(has_pool)
    avail = missing = unchecked = 0
    for c in comps:
        s = _state(results, c["key"])
        if s == "available":
            avail += 1
        elif s == "missing":
            missing += 1
        else:
            unchecked += 1
    seen = avail + missing
    denom = len(comps)
    return {
        "available": avail, "missing": missing, "not_inspected": unchecked,
        "denominator": denom,
        "compliance_pct": (round(avail / seen * 100, 1) if seen else None),
        "inspected_pct": (round(seen / denom * 100, 1) if denom else 0.0),
    }


def blockers(results, has_pool):
    return [c for c in components_for(has_pool)
            if c["kind"] == "structural" and _state(results, c["key"]) == "missing"]


def can_export_evidence(rnd, results, has_pool):
    """A round is evidence only when it is closed, not abandoned, and fully inspected.
    Enforced HERE, not in UI copy."""
    if not rnd or not rnd.get("closed_at"):
        return False, "الجولة ما زالت مفتوحة — أغلقها أولًا"
    if (rnd.get("note") or "") == "abandoned":
        return False, "جولة متروكة — ما تصلح دليلًا"
    s = score(results, has_pool)
    if s["not_inspected"]:
        return False, "فيه %d مكوّن ما انفحص — نسبة الفحص لازم تكون ١٠٠٪" % s["not_inspected"]
    return True, ""


def default_qty(component, unit_meta):
    m = unit_meta or {}

    def n(k):
        try:
            v = int(m.get(k) or 0)
        except (TypeError, ValueError):
            v = 0
        return v

    hint = component.get("unit_hint") or "per_unit"
    if hint == "per_bedroom":
        q = n("bedrooms")
    elif hint == "per_bathroom":
        q = n("bathrooms")
    elif hint == "per_bed":
        q = n("beds") or n("bedrooms")
    else:
        q = 1
    return max(1, q)


def _price_of(prices, key):
    p = (prices or {}).get(key)
    if isinstance(p, dict):
        try:
            return float(p.get("price_sar") or 0), p.get("set_at")
        except (TypeError, ValueError):
            return 0.0, p.get("set_at")
    try:
        return float(p or 0), None
    except (TypeError, ValueError):
        return 0.0, None


def _is_stale(set_at, today):
    if not set_at:
        return False
    try:
        d = datetime.fromisoformat(str(set_at)[:19]).date()
    except ValueError:
        return False
    t = today if isinstance(today, date) else (date.fromisoformat(str(today)[:10]) if today else date.today())
    return (t - d).days > STALE_DAYS


def quote_lines(results, prices, unit_meta, has_pool, today=None):
    """Split every failed component into where it goes. Products before works inside the
    owner list so the quote reads shopping-list first, then a visibly separate works group."""
    owner_p, owner_w = [], []
    ouja_p, ouja_w, docs, blocked = [], [], [], []
    unpriced, stale = [], []
    for c in components_for(has_pool):
        if _state(results, c["key"]) != "missing":
            continue
        r = (results or {}).get(c["key"]) or {}
        if c["kind"] == "structural":
            blocked.append(c)
            continue
        if c["kind"] == "document":
            docs.append(dict(c, task_key=C.DOCUMENT_TASK_KEY.get(c["key"], "")))
            continue
        billed = r.get("billed_to") if r.get("billed_to") in C.BILLED else c["billed_to"]
        try:
            qty = int(r.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0
        qty = qty if qty > 0 else default_qty(c, unit_meta)
        price, set_at = _price_of(prices, c["key"])
        if price <= 0:
            unpriced.append(c["key"])
        if _is_stale(set_at, today):
            stale.append(c["key"])
        line = dict(c, billed_to=billed, qty=qty, price=price,
                    total=round(qty * price, 2), group=c["kind"], note=r.get("note") or "")
        if billed == "owner":
            (owner_w if c["kind"] == "works" else owner_p).append(line)
        else:
            (ouja_w if c["kind"] == "works" else ouja_p).append(line)
    owner = owner_p + owner_w
    return {
        "owner": owner,
        "owner_total": round(sum(l["total"] for l in owner), 2),
        "ouja_products": ouja_p,
        "ouja_products_total": round(sum(l["total"] for l in ouja_p), 2),
        "ouja_works": ouja_w,
        "documents": docs,
        "blocked": blocked,
        "unpriced": unpriced,
        "stale": stale,
    }


def quote_items(owner_lines):
    """items[] exactly as /api/quotes/save cleans them. The works group is introduced by a
    visible zero-priced separator line, so the owner is never reading a shopping list that
    quietly contains a plumber."""
    items, sep_done = [], False
    for l in owner_lines:
        if l["group"] == "works" and not sep_done:
            items.append({"description": WORKS_SEPARATOR, "note": "", "qty": 0, "price": 0})
            sep_done = True
        items.append({
            "description": "%s — %s" % (l["criterion_ar"], l["label_ar"]),
            "note": ("معيار %d" % l["criterion_no"]) + ((" · " + l["note"]) if l.get("note") else ""),
            "qty": l["qty"], "price": l["price"],
        })
    return items


def outstanding_sar(results, prices, unit_meta, has_pool):
    """What it costs to reach compliance on this round: owner + Ouja product lines."""
    q = quote_lines(results, prices, unit_meta, has_pool)
    return round(q["owner_total"] + q["ouja_products_total"], 2)
