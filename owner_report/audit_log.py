# -*- coding: utf-8 -*-
"""
AUDIT LOG & IMMUTABILITY  (spec §7)

Every generated report writes an immutable record keyed by `doc_ref`:
  * doc_ref, unit, period, generated-by, timestamp
  * a FULL snapshot of every input (operator answers + provenance manifest) — enough to
    reproduce the exact cfg via model.build_cfg(record["inputs"])
  * the signed-off reconciliation totals
  * a reference + sha256 of the rendered PDF
  * a content hash over the canonical snapshot, for tamper-evidence

Rules enforced here:
  * A doc_ref is written ONCE. Re-issuing the same doc_ref raises — reports are never
    silently regenerated.
  * A correction issues a NEW doc_ref and marks the prior record ``superseded``.

Storage is dependency-injected (load/save callables), so this is unit-testable off-disk.
"""
from __future__ import annotations

import copy
import hashlib
import json

from .errors import BuildError

_STORE_NAME = "owner_report_audit.json"


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash(snapshot: dict) -> str:
    return hashlib.sha256(_canonical(snapshot).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, load, save, store_name: str = _STORE_NAME):
        self._load = load
        self._save = save
        self._name = store_name

    def _all(self) -> dict:
        return self._load(self._name, {}) or {}

    def get(self, doc_ref: str) -> dict:
        return copy.deepcopy(self._all().get(doc_ref))

    def exists(self, doc_ref: str) -> bool:
        return doc_ref in self._all()

    def issue(self, *, doc_ref, unit_ref, lid, period, generated_by, created_at,
              inputs, cfg, manifest, meta, disclosures, reconciliation,
              pdf_ref, pdf_sha256, supersedes=None) -> dict:
        """Write an immutable record. Raises if doc_ref already exists."""
        allr = self._all()
        if doc_ref in allr:
            raise BuildError(
                f"doc_ref {doc_ref!r} already issued — reports are never silently "
                f"regenerated. Issue a correction under a new doc_ref instead."
            )
        snapshot = {
            "doc_ref": doc_ref, "unit_ref": unit_ref, "lid": lid, "period": period,
            "generated_by": generated_by, "created_at": created_at,
            "inputs": copy.deepcopy(inputs),
            "cfg": copy.deepcopy(cfg),
            "manifest": [
                {"path": e.path, "tag": e.tag, "value": e.value, "note": e.note}
                if not isinstance(e, dict) else e
                for e in manifest
            ],
            "meta": copy.deepcopy(meta),
            "disclosures": list(disclosures),
            "reconciliation": copy.deepcopy(reconciliation),
            "pdf_ref": pdf_ref, "pdf_sha256": pdf_sha256,
            "status": "issued", "supersedes": supersedes, "superseded_by": None,
        }
        snapshot["content_hash"] = content_hash(
            {k: v for k, v in snapshot.items() if k != "content_hash"}
        )
        allr[doc_ref] = snapshot
        if supersedes and supersedes in allr:
            allr[supersedes]["status"] = "superseded"
            allr[supersedes]["superseded_by"] = doc_ref
        self._save(self._name, allr)
        return copy.deepcopy(snapshot)

    def reproduce_inputs(self, doc_ref: str) -> dict:
        """The stored inputs — feed to model.build_cfg to reconstruct the exact cfg."""
        rec = self.get(doc_ref)
        if not rec:
            raise BuildError(f"no audit record for doc_ref {doc_ref!r}")
        return rec["inputs"]

    def verify_integrity(self, doc_ref: str) -> bool:
        rec = self._all().get(doc_ref)
        if not rec:
            return False
        stored = rec.get("content_hash")
        recomputed = content_hash({k: v for k, v in rec.items() if k != "content_hash"})
        return stored == recomputed

    def history(self) -> list:
        return [
            {"doc_ref": r["doc_ref"], "status": r["status"],
             "created_at": r["created_at"], "superseded_by": r.get("superseded_by")}
            for r in self._all().values()
        ]
