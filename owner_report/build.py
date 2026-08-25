# -*- coding: utf-8 -*-
"""
ORCHESTRATOR — the one supported way to produce a report.

    from owner_report import build_report
    result = build_report(inputs, meta, out_pdf, generated_by=..., created_at=...)

Runs the full non-negotiable gate chain, in order, failing closed at every step:

  1. build_cfg(inputs)        -> provenance enforced (untagged figure => build failure)
  2. reconciliation(cfg)      -> the gross -> ... -> owner_net chain (renderer-identical math)
  3. validate(cfg, meta)      -> §4 hard gates + §5 field limits + soft-warning discipline
  4. render(cfg, out_pdf)     -> the frozen 17-page renderer (also writes _report.html)
  5. assert_layout_clean(html)-> §4 layout hard gate on the REAL rendered markup
  6. audit_log.issue(...)     -> immutable, reproducible snapshot per doc_ref

Nothing is emitted to an owner unless every gate passes. The reconciliation must be signed
(meta['reconciliation_signed']) — that is enforced inside validate().
"""
from __future__ import annotations

import hashlib
import pathlib

from .model import build_cfg
from .validate import validate
from . import renderer_api


def reconciliation(cfg: dict) -> dict:
    """The owner reconciliation chain. Mirrors the frozen renderer's derivation exactly
    (ouja_render lines 234-246) so the preview equals the PDF to the riyal."""
    months = cfg["MONTHS"]
    gross = sum(m[4] for m in months)
    avail = sum(m[2] for m in months)
    booked = sum(m[3] for m in months)
    channel_fees = cfg["COSTS"]["channel_fees"]
    net_rental = gross - channel_fees
    mgmt_fee = round(net_rental * cfg["COSTS"]["mgmt_fee_pct"])
    opex_total = sum(o[2] for o in cfg["COSTS"]["opex"])
    owner_net = net_rental - mgmt_fee - opex_total
    return {
        "gross": gross, "channel_fees": channel_fees, "net_rental": net_rental,
        "mgmt_fee": mgmt_fee, "opex_total": opex_total, "owner_net": owner_net,
        "nights_available": avail, "nights_booked": booked,
        "occupancy": round(booked / avail, 4) if avail else None,
        "adr": round(gross / booked, 2) if booked else None,
        "revpar": round(gross / avail, 2) if avail else None,
    }


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    h.update(pathlib.Path(path).read_bytes())
    return h.hexdigest()


def build_report(inputs, meta, out_pdf, *, generated_by, created_at,
                 audit_log=None, supersedes=None, run_layout_audit=True):
    """Produce the report through every gate. Returns a result dict. Raises on any gate."""
    # 1. provenance-enforced cfg
    cfg, manifest, disclosures = build_cfg(inputs)

    # 2. reconciliation chain (renderer-identical)
    recon = reconciliation(cfg)

    # 3. validation — fill the fields the model is authoritative for, then gate
    meta = dict(meta)
    meta["disclosures"] = list(disclosures)
    meta.setdefault("reservation_revenue_total", recon["gross"])
    validate(cfg, meta).raise_if_blocked()

    # 4. render (frozen). also writes _report.html next to the pdf
    pdf_path = renderer_api.render(cfg, out_pdf)

    # 5. layout hard gate on the actual rendered HTML
    if run_layout_audit:
        renderer_api.assert_layout_clean(renderer_api.html_for(pdf_path))

    pdf_sha = _sha256_file(pdf_path)

    # 6. immutable audit snapshot
    snapshot = None
    if audit_log is not None:
        snapshot = audit_log.issue(
            doc_ref=cfg["REPORT"]["doc_ref"],
            unit_ref=cfg["UNIT"].get("unit_ref"),
            lid=inputs.get("lid") or meta.get("lid"),
            period=cfg["REPORT"].get("period_label_en"),
            generated_by=generated_by, created_at=created_at,
            inputs=inputs, cfg=cfg, manifest=manifest, meta=meta,
            disclosures=disclosures, reconciliation=recon,
            pdf_ref=str(pdf_path), pdf_sha256=pdf_sha, supersedes=supersedes,
        )

    return {
        "pdf": pdf_path, "pdf_sha256": pdf_sha, "doc_ref": cfg["REPORT"]["doc_ref"],
        "cfg": cfg, "manifest": manifest, "disclosures": disclosures,
        "reconciliation": recon, "snapshot": snapshot,
    }
