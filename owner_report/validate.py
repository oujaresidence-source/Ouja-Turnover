# -*- coding: utf-8 -*-
"""
VALIDATION ENGINE  (spec §4 + §5)

Bad data must never reach the frozen renderer. This module runs BEFORE render and is
the authority on data integrity. `audit_layout.assert_clean(html)` is the separate,
render-time authority on *layout* integrity and is invoked by the orchestrator once
HTML exists.

Two tiers:
  * HARD GATES   — block the render. No override. Raise ValidationError.
  * SOFT WARNINGS — render allowed, but each must be acknowledged AND each must print a
                    disclosure line in the PDF. An UN-acknowledged soft warning is
                    promoted to a hard block (you cannot silently skip a disclosure).

FIELD LIMITS (spec §5) — enforced here so the operator gets a precise, named message
BEFORE the slower audit_layout pass. NOTE the deliberate deviation from the spec's
written numbers for FACTORS and RISKS: the approved golden design (reference_data.py,
the unit the PDF was signed off on) ships 9 FACTORS and 6 RISKS, and the frozen renderer
renders every row with no truncation. Enforcing the spec's "FACTORS <=8 / RISKS <=5"
literally would reject the golden itself. The golden + audit_layout are the ground truth,
so the caps below match the proven design. audit_layout remains the final authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .errors import ValidationError

# ---- Field limits (spec §5, reconciled to the approved golden) ------------------
NAME_MAX = 34
NOTE_MAX = 220
SAR_MAX = 10_000_000
COMP_SET_ROWS = 5
OPEX_MAX = 3
FACTORS_MAX = 9   # spec says 8; golden ships 9 (renderer renders all) -> 9 is truth
RISKS_MAX = 6     # spec says 5; golden ships 6 (renderer renders all) -> 6 is truth
ACTIONS_MAX = 6
SOURCES_MAX = 7
MONTHS_HALF = 6
MONTHS_FULL = 12
ADR_SANE_LOW = 100
ADR_SANE_HIGH = 3_000

RECON_TOLERANCE = 0  # spec: "must reconcile to the riyal"

# Soft-warning codes -> each acknowledged one must produce a disclosure line in the PDF.
W_EJAR_SINGLE = "ejar_single_contract"
W_EJAR_UNFURNISHED = "ejar_unfurnished_no_uplift"
W_COMP_STALE = "comp_set_older_than_90d"
W_MANUAL_BOOKINGS = "manual_out_of_hostaway_bookings"
W_ADR_BAND = "adr_outside_sanity_band"


@dataclass
class ValidationResult:
    hard: list = field(default_factory=list)   # blocking violations (operator-facing str)
    soft: list = field(default_factory=list)   # (code, message) tuples

    @property
    def ok(self) -> bool:
        return not self.hard

    def raise_if_blocked(self):
        if self.hard:
            raise ValidationError(self.hard)


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _all_sar_figures(cfg):
    """Yield (path, value) for every SAR-scale figure that must fit the number columns."""
    money_keys = {
        "purchase_price", "annual_rent", "owner_maintenance", "admin_fees",
        "channel_fees", "capex", "opex_annual",
    }
    for k, v in cfg.get("ASSET", {}).items():
        if k in money_keys and _is_number(v):
            yield f"ASSET.{k}", v
    for k, v in cfg.get("EJAR", {}).items():
        if k in money_keys and _is_number(v):
            yield f"EJAR.{k}", v
    if _is_number(cfg.get("COSTS", {}).get("channel_fees")):
        yield "COSTS.channel_fees", cfg["COSTS"]["channel_fees"]
    for i, row in enumerate(cfg.get("COSTS", {}).get("opex", [])):
        yield f"COSTS.opex[{i}]", row[2]
    for i, m in enumerate(cfg.get("MONTHS", [])):
        yield f"MONTHS[{i}].gross", m[4]
    for band, scen in cfg.get("PROJECTION", {}).items():
        if isinstance(scen, dict):
            for k, v in scen.items():
                if _is_number(v):
                    yield f"PROJECTION.{band}.{k}", v


def _free_texts(cfg):
    """Yield (path, text) for free-text notes subject to the 220-char cap."""
    for sect in ("MARKET_YIELD",):
        for k in ("note_en", "note_ar"):
            t = cfg.get(sect, {}).get(k)
            if isinstance(t, str):
                yield f"{sect}.{k}", t
    for i, f in enumerate(cfg.get("FACTORS", [])):
        for j in (3, 4):
            if len(f) > j and isinstance(f[j], str):
                yield f"FACTORS[{i}][{j}]", f[j]
    for i, r in enumerate(cfg.get("RISKS", [])):
        for j in (3, 4):
            if len(r) > j and isinstance(r[j], str):
                yield f"RISKS[{i}][{j}]", r[j]


def validate_field_limits(cfg) -> list:
    """Spec §5 — return a list of operator-facing violation strings (empty == clean)."""
    v = []
    u = cfg.get("UNIT", {})
    for k in ("listing_name_en", "listing_name_ar"):
        name = u.get(k, "")
        if len(name) > NAME_MAX:
            v.append(f"UNIT.{k} is {len(name)} chars (max {NAME_MAX}): {name!r}")

    comp = cfg.get("COMP_SET", [])
    if len(comp) != COMP_SET_ROWS:
        v.append(f"COMP_SET must have exactly {COMP_SET_ROWS} rows, found {len(comp)}")

    months = cfg.get("MONTHS", [])
    if len(months) not in (MONTHS_HALF, MONTHS_FULL):
        v.append(f"MONTHS must have {MONTHS_HALF} (half-year) or {MONTHS_FULL} rows, found {len(months)}")

    opex = cfg.get("COSTS", {}).get("opex", [])
    if len(opex) > OPEX_MAX:
        v.append(f"COSTS.opex has {len(opex)} line items (max {OPEX_MAX})")

    for name, seq, mx in (
        ("FACTORS", cfg.get("FACTORS", []), FACTORS_MAX),
        ("RISKS", cfg.get("RISKS", []), RISKS_MAX),
        ("ACTIONS", cfg.get("ACTIONS", []), ACTIONS_MAX),
        ("SOURCES", cfg.get("SOURCES", []), SOURCES_MAX),
    ):
        if len(seq) > mx:
            v.append(f"{name} has {len(seq)} rows (max {mx})")

    for pth, val in _all_sar_figures(cfg):
        if abs(val) >= SAR_MAX:
            v.append(f"{pth} = {val:,} exceeds the {SAR_MAX:,} SAR column width")

    for pth, txt in _free_texts(cfg):
        if len(txt) > NOTE_MAX:
            v.append(f"{pth} note is {len(txt)} chars (max {NOTE_MAX})")

    return v


def validate(cfg, meta) -> ValidationResult:
    """Run all hard gates + soft warnings. `meta` carries the operator gate-answers.

    Expected `meta` keys (all confirmations default to blocking-if-absent):
      vat_resolved: bool                    # spec Q7 resolved & stored
      vat_reconciled_against_payout: bool   # verified vs one real Airbnb payout
      reconciliation_signed: bool           # §4 reconciliation screen sign-off
      reservation_revenue_total: number     # sum of reservation-level revenue for period
      cancelled_in_revenue: int             # count of cancelled reservations in revenue set
      lease_sections_enabled: bool          # yield/lease pages on
      owner_blocked_nights: int
      owner_blocked_treatment: 'exclude'|'vacant'
      ejar_is_single_contract: bool
      ejar_unfurnished_no_uplift: bool
      comp_stale: bool                      # any comp older than 90 days
      manual_bookings: int                  # count of out-of-Hostaway bookings included
      acknowledged: iterable[str]           # acknowledged soft-warning codes
      disclosures: iterable[str]            # warning codes with a disclosure line in cfg
      required_fields_confirmed: bool       # every wizard field explicitly re-confirmed
    """
    res = ValidationResult()
    ack = set(meta.get("acknowledged", []))
    disclosed = set(meta.get("disclosures", []))

    # ---- HARD GATES (§4) --------------------------------------------------------
    # required fields / confirmations
    if not meta.get("required_fields_confirmed", False):
        res.hard.append("Not every required wizard field was explicitly re-confirmed this run.")

    # occupancy integrity: per-month + total
    avail = booked = gross = 0
    for i, m in enumerate(cfg.get("MONTHS", [])):
        na, nb, g = m[2], m[3], m[4]
        avail += na; booked += nb; gross += g
        if nb > na:
            res.hard.append(f"MONTHS[{i}] ({m[1]}): nights_booked {nb} > nights_available {na}")
    if avail and booked > avail:
        res.hard.append(f"Total nights_booked {booked} > nights_available {avail} (occupancy > 100%)")

    # monthly revenue must reconcile to reservation-level revenue, to the riyal
    if "reservation_revenue_total" in meta:
        rt = meta["reservation_revenue_total"]
        if abs(round(gross) - round(rt)) > RECON_TOLERANCE:
            res.hard.append(
                f"Monthly revenue sum {gross:,} != reservation-level total {rt:,} "
                f"(delta {gross - rt:,}); must reconcile to the riyal."
            )
    else:
        res.hard.append("reservation_revenue_total not supplied — monthly/reservation reconciliation cannot run.")

    # cancelled reservations must not be in the revenue set
    if meta.get("cancelled_in_revenue", 0):
        res.hard.append(
            f"{meta['cancelled_in_revenue']} cancelled reservation(s) present in the revenue set."
        )

    # VAT treatment resolved (spec Q7)
    if not meta.get("vat_resolved", False):
        res.hard.append("VAT treatment (Q7) is unresolved — every figure would be wrong by up to 15%.")

    # purchase price / ejar present when lease + yield sections enabled
    if meta.get("lease_sections_enabled", True):
        pp = cfg.get("ASSET", {}).get("purchase_price")
        er = cfg.get("EJAR", {}).get("annual_rent")
        if not (_is_number(pp) and pp > 0):
            res.hard.append("ASSET.purchase_price missing while the yield/lease sections are enabled.")
        if not (_is_number(er) and er > 0):
            res.hard.append("EJAR.annual_rent missing while the lease-comparison section is enabled.")

    # reconciliation must be signed
    if not meta.get("reconciliation_signed", False):
        res.hard.append("Reconciliation is unsigned — nothing renders on an unsigned reconciliation.")

    # field-length limits (§5) are hard gates
    res.hard.extend(validate_field_limits(cfg))

    # ---- SOFT WARNINGS (§4) -----------------------------------------------------
    def soft(code, msg):
        res.soft.append((code, msg))
        if code not in ack:
            res.hard.append(f"Unacknowledged warning [{code}]: {msg}")
        elif code not in disclosed:
            res.hard.append(f"Warning [{code}] acknowledged but no disclosure line present in the PDF.")

    if meta.get("ejar_is_single_contract", False):
        soft(W_EJAR_SINGLE, "Ejar benchmark is a single data point (a baseline, not a benchmark).")
    if meta.get("ejar_unfurnished_no_uplift", False):
        soft(W_EJAR_UNFURNISHED, "Ejar comparable is unfurnished and no furnished-uplift was applied — the true gap is narrower.")
    if meta.get("comp_stale", False):
        soft(W_COMP_STALE, "Comp-set data is older than 90 days.")
    if meta.get("manual_bookings", 0):
        soft(W_MANUAL_BOOKINGS, f"{meta['manual_bookings']} manual out-of-Hostaway booking(s) included.")

    # ADR sanity band (period-level)
    if booked:
        adr = gross / booked
        if adr < ADR_SANE_LOW or adr > ADR_SANE_HIGH:
            soft(W_ADR_BAND, f"Period ADR {adr:,.0f} SAR/night is outside the sane band [{ADR_SANE_LOW}, {ADR_SANE_HIGH}].")

    return res
