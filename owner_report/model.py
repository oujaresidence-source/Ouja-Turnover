# -*- coding: utf-8 -*-
"""
MODEL — assemble a provenance-tagged model, then emit the plain `cfg` the frozen
renderer consumes, plus a provenance manifest and the set of disclosure codes actually
woven into printed text.

Design facts that constrain this module:
  * The renderer computes derived C-metrics itself (RevPAR, MPI/ARI/RGI, yields,
    payback, projections). We supply only the H/O/M inputs; each is Fig-tagged.
  * The renderer prints a LIMITED set of free-text fields. Verified against the frozen
    source: it prints EJAR["ref"] (the lease "Source:" line) and the SOURCES rows in
    full; it does NOT read EJAR["source_*"] or MARKET_YIELD["note_*"]. So soft-warning
    disclosures are woven into EJAR["ref"] (lease caveats) and SOURCES descriptions
    (comp staleness, manual bookings). Adding SOURCES rows is impossible (>7 breaks the
    field limit), so disclosures append into existing row text.
  * The "not legal advice" rent-freeze caveat is hardcoded in the renderer — not injected.

Key operator-driven transforms handled here (spec §3):
  * VAT (Q7): if Hostaway financial fields INCLUDE 15% VAT, divide it out so revenue is
    net accommodation revenue. Never guess — the basis is an explicit operator input.
  * Owner-blocked nights (Q4): 'exclude' removes them from available nights; 'vacant'
    leaves them in (counting against occupancy). The choice is disclosed.
  * Furnished uplift (Q17): an UNFURNISHED Ejar comparable is uplifted by the supplied
    % to a furnished-equivalent, and the adjustment is printed in EJAR["ref"]. With no
    uplift, the raw rate is used and a caveat is printed (W_EJAR_UNFURNISHED).
  * Furnishing (Q18): delivered-furnished -> capex 0, owner_funded False (capital =
    purchase price). Owner-funded -> capex + amort years retained.
  * Single-contract Ejar (Q16): labelled a BASELINE, never a "benchmark", in EJAR["ref"].
"""
from __future__ import annotations

from .provenance import Fig, assert_fully_tagged, manifest, unwrap
from . import validate as V

VAT_RATE = 0.15


def _F(v, tag, note=""):
    return Fig(v, tag, note)


def _net_of_vat(amount, vat_included):
    """Divide out 15% VAT if the Hostaway figure includes it. Rounded to the riyal."""
    return round(amount / (1 + VAT_RATE)) if vat_included else amount


def build_model(inp: dict) -> dict:
    """Return the fully Fig-tagged model. Raises ProvenanceError via assert_fully_tagged
    only when unwrapped downstream; call assert_fully_tagged(model) to enforce early."""
    vat_included = inp["vat_basis"] == "inclusive"

    # ---- MONTHS (H) : net-of-VAT revenue + owner-block adjustment --------------
    months = []
    blocked = inp.get("blocked_by_month") or [0] * len(inp["months"])
    treat = inp.get("owner_blocked_treatment", "exclude")
    for (m_ar, m_en, cal_avail, booked, gross_raw), blk in zip(inp["months"], blocked):
        avail = cal_avail - blk if treat == "exclude" else cal_avail
        net_gross = _net_of_vat(gross_raw, vat_included)
        months.append((m_ar, m_en, _F(avail, "H"), _F(booked, "H"), _F(net_gross, "H")))

    # ---- EJAR (O) : furnished uplift + single-contract baseline labelling -------
    ej = inp["ejar"]
    raw_rent = ej["annual_rent"]
    uplift = ej.get("furnished_uplift_pct") or 0.0
    unfurnished = not ej.get("comparable_furnished", True)
    applied_rent = round(raw_rent * (1 + uplift)) if (unfurnished and uplift) else raw_rent

    ref_bits = [ej.get("ref", "Ejar registered lease")]
    disclosures = set()
    if inp.get("ejar_is_single_contract", False):
        ref_bits.append("single registered contract — a baseline, not a benchmark")
        disclosures.add(V.W_EJAR_SINGLE)
    if unfurnished and uplift:
        ref_bits.append(f"unfurnished, uplifted +{uplift*100:.0f}% to a furnished-equivalent rate")
    elif unfurnished and not uplift:
        ref_bits.append("unfurnished comparable, no furnished uplift applied — true gap is narrower")
        disclosures.add(V.W_EJAR_UNFURNISHED)
    ejar = {
        "annual_rent": _F(applied_rent, "O"),
        "source_en": ej.get("source_en", "Ejar Platform"),
        "source_ar": ej.get("source_ar", "منصة إيجار"),
        "ref": " · ".join(ref_bits),
        "broker_pct": _F(ej["broker_pct"], "O"),
        "vacancy_pct": _F(ej["vacancy_pct"], "O"),
        "owner_maintenance": _F(ej["owner_maintenance"], "O"),
        "admin_fees": _F(ej["admin_fees"], "O"),
    }

    # ---- SOURCES (mixed) : weave remaining disclosures into printed rows --------
    sources = [list(r) for r in inp["sources"]]
    if inp.get("comp_stale", False):
        for r in sources:
            if "tracking" in r[1].lower() or "market" in r[1].lower() or "منافس" in r[2]:
                r[2] = (r[2] + " — بيانات أقدم من 90 يوم").strip()
                disclosures.add(V.W_COMP_STALE)
                break
    if inp.get("manual_bookings", 0):
        for r in sources:
            if "hostaway" in r[1].lower():
                r[2] = (r[2] + f" + {inp['manual_bookings']} حجز يدوي خارج Hostaway").strip()
                disclosures.add(V.W_MANUAL_BOOKINGS)
                break
    sources = [tuple(r) for r in sources]

    # ---- FURNISHING (O/flags) : per delivery status -----------------------------
    fu = inp["furnishing"]
    delivered = fu.get("delivered_furnished", True)
    owner_funded = (not delivered) and fu.get("owner_funded", False)
    furnishing = {
        "delivered_furnished": delivered,
        "capex": _F(0 if delivered else fu.get("capex", 0), "O"),
        "amort_years": _F(fu.get("amort_years", 5), "O"),
        "owner_funded": owner_funded,
    }

    # ---- COSTS (H channel fees / O mgmt + opex) --------------------------------
    costs = {
        "channel_fees": _F(inp["costs"]["channel_fees"], "H"),
        "mgmt_fee_pct": _F(inp["costs"]["mgmt_fee_pct"], "O"),
        "opex": [(a, e, _F(v, "O")) for (a, e, v) in inp["costs"]["opex"]],
    }

    # ---- ASSET / MARKET_YIELD ---------------------------------------------------
    asset = {
        "purchase_price": _F(inp["asset"]["purchase_price"], "O"),
        "purchase_note_en": inp["asset"].get("purchase_note_en", "Owner acquisition cost"),
        "purchase_note_ar": inp["asset"].get("purchase_note_ar", "تكلفة شراء الوحدة"),
    }
    my = inp["market_yield"]
    market_yield = {
        "riyadh_gross_low": _F(my["riyadh_gross_low"], "M"),
        "riyadh_gross_high": _F(my["riyadh_gross_high"], "M"),
        "riyadh_net_avg": _F(my["riyadh_net_avg"], "M"),
        "ksa_gross_avg": _F(my["ksa_gross_avg"], "M"),
        "note_en": my.get("note_en", ""), "note_ar": my.get("note_ar", ""),
    }

    # ---- CHANNELS (H) / BOOKING_BEHAVIOUR (H) / GUEST (H) -----------------------
    channels = [(a, e, _F(sh, "H")) for (a, e, sh) in inp["channels"]]
    bb = inp["booking_behaviour"]
    booking = {
        "alos": _F(bb["alos"], "H"), "lead_time": _F(bb["lead_time"], "H"),
        "repeat_guest_pct": _F(bb["repeat_guest_pct"], "H"),
        "cancellation_pct": _F(bb["cancellation_pct"], "H"),
        "reservations": _F(bb["reservations"], "H"),
    }
    g = inp["guest"]
    guest = {
        "overall": _F(g["overall"], "H"), "reviews": _F(g["reviews"], "H"),
        "response_rate": _F(g["response_rate"], "H"),
        "median_response_min": _F(g["median_response_min"], "H"),
        "superhost": g.get("superhost", False),
        "sub": [(a, e, _F(s, "H")) for (a, e, s) in g["sub"]],
    }

    # ---- COMP_SET (M) -----------------------------------------------------------
    comp = [(a, e, _F(adr, "M"), _F(occ, "M")) for (a, e, adr, occ) in inp["comp_set"]]

    # ---- PROJECTION (scenarios C, assumptions O) -------------------------------
    pj = inp["projection"]
    projection = {
        "h2_2026": {k: _F(v, "C") for k, v in pj["h2_2026"].items()},
        "fy_2027": {k: _F(v, "C") for k, v in pj["fy_2027"].items()},
        "channel_pct": _F(pj["channel_pct"], "C"),
        "opex_annual": _F(pj["opex_annual"], "C"),
        "assumptions_ar": list(pj["assumptions_ar"]),
        "assumptions_en": list(pj["assumptions_en"]),
    }

    # ---- RENT_FREEZE (O) --------------------------------------------------------
    rf = inp["rent_freeze"]
    rent_freeze = {
        "start": rf["start"], "years": _F(rf["years"], "O"), "ends": rf["ends"],
        "ends_ar": rf["ends_ar"], "start_ar": rf["start_ar"],
    }

    model = {
        "UNIT": {**inp["unit"],
                 "bedrooms": _F(inp["unit"]["bedrooms"], "O"),
                 "area_sqm": _F(inp["unit"]["area_sqm"], "O")},
        "OWNER": dict(inp["owner"]),
        "REPORT": dict(inp["report"]),
        "ASSET": asset,
        "MARKET_YIELD": market_yield,
        "RENT_FREEZE": rent_freeze,
        "EJAR": ejar,
        "MONTHS": months,
        "COSTS": costs,
        "FURNISHING": furnishing,
        "CHANNELS": channels,
        "BOOKING_BEHAVIOUR": booking,
        "COMP_SET": comp,
        "GUEST": guest,
        "FACTORS": [tuple(r) for r in inp["factors"]],
        "RISKS": [tuple(r) for r in inp["risks"]],
        "PROJECTION": projection,
        "ACTIONS": [tuple(r) for r in inp["actions"]],
        "SOURCES": sources,
    }
    model["_disclosures"] = sorted(disclosures)  # side-channel, stripped before cfg
    return model


def build_cfg(inp: dict):
    """Emit (cfg, manifest_entries, disclosures).

    cfg is the plain dict the renderer consumes. Provenance is enforced: any untagged
    figure raises ProvenanceError before cfg is produced.
    """
    model = build_model(inp)
    disclosures = model.pop("_disclosures")
    assert_fully_tagged(model)           # untagged figure => build failure
    cfg = unwrap(model)
    return cfg, manifest(model), disclosures
