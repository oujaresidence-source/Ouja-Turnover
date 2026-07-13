# -*- coding: utf-8 -*-
"""
PROVENANCE — every figure in the report carries an H / O / M / C tag.

    H = Hostaway        (reservations, nights, revenue, channel, reviews, expenses)
    O = Operator input  (purchase price, Ejar value, furnished status, fee basis, blocks)
    M = Market estimate  (competitor ADR & occupancy, Riyadh yield benchmarks)
    C = Calculated       (RevPAR, MPI/ARI/RGI, yields, payback, projections)

The frozen renderer consumes a PLAIN `cfg` dict (numbers, strings, tuples) and computes
the C-metrics itself. Provenance therefore lives in a PARALLEL layer: the model is built
out of `Fig(value, tag, note)` wrappers, then:

    * ``assert_fully_tagged(model)`` proves NO raw number slipped in untagged
      (an untagged figure is a build failure, per the spec — not a warning),
    * ``unwrap(model)`` produces the plain dict the renderer consumes,
    * ``manifest(model)`` produces the per-figure source table for the audit log.

`M` figures must be visibly flagged as estimates in the report; the manifest preserves
their tag so the appendix source table and the audit snapshot can render them as such.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import BuildError

VALID_TAGS = ("H", "O", "M", "C")
_TAG_LABEL = {
    "H": ("Hostaway", "من نظام Hostaway"),
    "O": ("Operator-supplied", "مُدخَل من المشغّل"),
    "M": ("Market estimate", "تقدير سوقي"),
    "C": ("Calculated", "محسوب"),
}


class ProvenanceError(BuildError):
    """A figure is missing a valid H/O/M/C provenance tag."""


@dataclass(frozen=True)
class Fig:
    """A single tagged figure. ``value`` must be numeric; ``tag`` must be H/O/M/C.

    Booleans are NOT figures (they are structural facts, e.g. delivered_furnished);
    wrapping a bool raises, to catch accidental ``Fig(True, ...)``.
    """

    value: Any
    tag: str
    note: str = ""

    def __post_init__(self):
        if self.tag not in VALID_TAGS:
            raise ProvenanceError(
                f"invalid provenance tag {self.tag!r} (must be one of {VALID_TAGS}) "
                f"for value {self.value!r}"
            )
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ProvenanceError(
                f"a Fig value must be a real number, got {type(self.value).__name__} "
                f"({self.value!r}); labels/flags do not carry provenance tags"
            )

    @property
    def is_estimate(self) -> bool:
        return self.tag == "M"

    def label(self, lang: str = "en") -> str:
        return _TAG_LABEL[self.tag][0 if lang == "en" else 1]


def _walk(obj: Any, path: str):
    """Yield (path, node) for every node, descending dict/list/tuple containers."""
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk(v, f"{path}[{i}]")


def assert_fully_tagged(model: Any) -> None:
    """Raise ProvenanceError if any raw number appears where a Fig was required.

    This is the enforcement behind "an untagged figure is a build failure, not a
    warning." The model must be assembled entirely from Fig-wrapped numbers; any bare
    int/float (that is not a bool) reaching this check means a figure was emitted
    without provenance.
    """
    offenders = []
    for pth, node in _walk(model, ""):
        if isinstance(node, Fig):
            continue
        if isinstance(node, bool):
            continue  # structural flag, not a figure
        if isinstance(node, (int, float)):
            offenders.append(pth or "<root>")
    if offenders:
        raise ProvenanceError(
            "untagged figure(s) reached the model — every number must be a Fig with an "
            "H/O/M/C tag:\n  - " + "\n  - ".join(offenders)
        )


def unwrap(model: Any) -> Any:
    """Recursively replace every Fig with its raw value -> the plain cfg the renderer eats."""
    if isinstance(model, Fig):
        return model.value
    if isinstance(model, dict):
        return {k: unwrap(v) for k, v in model.items()}
    if isinstance(model, list):
        return [unwrap(v) for v in model]
    if isinstance(model, tuple):
        return tuple(unwrap(v) for v in model)
    return model


@dataclass
class ManifestEntry:
    path: str
    tag: str
    value: Any
    note: str


def manifest(model: Any) -> list[ManifestEntry]:
    """Flat list of every tagged figure, for the audit snapshot + appendix source table."""
    out: list[ManifestEntry] = []
    for pth, node in _walk(model, ""):
        if isinstance(node, Fig):
            out.append(ManifestEntry(pth, node.tag, node.value, node.note))
    return out


def tag_counts(model: Any) -> dict:
    counts = {t: 0 for t in VALID_TAGS}
    for e in manifest(model):
        counts[e.tag] += 1
    return counts
