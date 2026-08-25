"""Atomic, persistent last-known-good publication snapshots."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple

from .publication import PublicationIssue, PublicationResult, validate_listing
from .settings import MonthlySettings


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class SnapshotGeneration:
    generation_id: str
    generated_at: str
    source_timestamps: Mapping[str, str]
    results: Tuple[PublicationResult, ...]
    counts: Mapping[str, int]
    published_ids: Tuple[str, ...]
    blocked_ids: Tuple[str, ...]
    missing_calendar_ids: Tuple[str, ...]
    stale_calendar_ids: Tuple[str, ...]
    missing_price_ids: Tuple[str, ...]

    @property
    def published(self) -> Tuple[PublicationResult, ...]:
        return tuple(result for result in self.results if result.publishable)

    @property
    def blocked(self) -> Tuple[PublicationResult, ...]:
        return tuple(result for result in self.results if not result.publishable)

    @property
    def by_id(self) -> Mapping[str, PublicationResult]:
        return MappingProxyType({result.listing["id"]: result for result in self.results})

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": 1,
            "generation_id": self.generation_id,
            "generated_at": self.generated_at,
            "source_timestamps": _plain(self.source_timestamps),
            "counts": _plain(self.counts),
            "published_ids": list(self.published_ids),
            "blocked_ids": list(self.blocked_ids),
            "missing_calendar_ids": list(self.missing_calendar_ids),
            "stale_calendar_ids": list(self.stale_calendar_ids),
            "missing_price_ids": list(self.missing_price_ids),
            "results": [
                {
                    "listing": _plain(result.listing),
                    "blockers": [issue.as_dict() for issue in result.blockers],
                    "warnings": [issue.as_dict() for issue in result.warnings],
                    "availability_status": result.availability_status,
                    "publishable": result.publishable,
                    "exact_match_eligible": result.exact_match_eligible,
                }
                for result in self.results
            ],
        }


@dataclass(frozen=True)
class RefreshOutcome:
    accepted: bool
    generation: Optional[SnapshotGeneration]
    error: Optional[str] = None


def _codes(result: PublicationResult, collection: str) -> set[str]:
    return {issue.code for issue in getattr(result, collection)}


def build_generation(
    source: Mapping[str, Any], settings: MonthlySettings, now: Any
) -> SnapshotGeneration:
    """Build one complete generation; malformed or duplicate catalogs fail as a unit."""

    if not isinstance(source, Mapping):
        raise ValueError("monthly source must be a mapping")
    if source.get("refresh_ok") is not True or source.get("catalog_complete") is not True:
        raise ValueError("monthly source refresh is incomplete")
    listings = source.get("listings")
    if not isinstance(listings, (list, tuple)) or not listings:
        raise ValueError("monthly catalog is empty")
    raw_ids = []
    for listing in listings:
        if not isinstance(listing, Mapping):
            raise ValueError("monthly catalog contains a malformed listing")
        raw_ids.append(str(listing.get("id")))
    if len(raw_ids) != len(set(raw_ids)):
        raise ValueError("monthly catalog contains duplicate listing IDs")

    results = tuple(validate_listing(listing, settings, now) for listing in listings)
    published_ids = tuple(result.listing["id"] for result in results if result.publishable)
    blocked_ids = tuple(result.listing["id"] for result in results if not result.publishable)
    missing_calendar_ids = tuple(
        result.listing["id"] for result in results if "calendar_missing" in _codes(result, "warnings")
    )
    stale_calendar_ids = tuple(
        result.listing["id"] for result in results if "calendar_stale" in _codes(result, "warnings")
    )
    missing_price_ids = tuple(
        result.listing["id"] for result in results if "price_missing" in _codes(result, "blockers")
    )
    counts = {
        "received": len(results),
        "validated": len(results),
        "blocked": len(blocked_ids),
        "published": len(published_ids),
        "calendar_covered": len(results) - len(missing_calendar_ids) - len(stale_calendar_ids),
        "price_covered": len(results) - len(missing_price_ids),
    }
    timestamps = source.get("source_timestamps")
    if not isinstance(timestamps, Mapping):
        timestamps = {}
    return SnapshotGeneration(
        generation_id=uuid.uuid4().hex,
        generated_at=now.isoformat(),
        source_timestamps=_freeze(
            {str(key): str(value) for key, value in timestamps.items() if value}
        ),
        results=results,
        counts=_freeze(counts),
        published_ids=published_ids,
        blocked_ids=blocked_ids,
        missing_calendar_ids=missing_calendar_ids,
        stale_calendar_ids=stale_calendar_ids,
        missing_price_ids=missing_price_ids,
    )


def _issue_from_dict(value: Any) -> PublicationIssue:
    if not isinstance(value, Mapping):
        raise ValueError("invalid persisted issue")
    return PublicationIssue(
        code=str(value.get("code") or ""),
        field=str(value.get("field") or ""),
        message_ar=str(value.get("message_ar") or ""),
        message_en=str(value.get("message_en") or ""),
        detail=tuple(str(item) for item in value.get("detail") or ()),
    )


def _generation_from_dict(value: Any) -> SnapshotGeneration:
    if not isinstance(value, Mapping) or value.get("schema") != 1:
        raise ValueError("unsupported persisted monthly snapshot")
    rows = value.get("results")
    if not isinstance(rows, list) or not rows:
        raise ValueError("persisted monthly snapshot has no rows")
    results = []
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("listing"), Mapping):
            raise ValueError("persisted monthly snapshot row is malformed")
        status = row.get("availability_status")
        if status not in ("confirmed", "pending"):
            raise ValueError("persisted availability status is invalid")
        results.append(
            PublicationResult(
                listing=_freeze(row["listing"]),
                blockers=tuple(_issue_from_dict(item) for item in row.get("blockers") or ()),
                warnings=tuple(_issue_from_dict(item) for item in row.get("warnings") or ()),
                availability_status=status,
                publishable=bool(row.get("publishable")),
                exact_match_eligible=bool(row.get("exact_match_eligible")),
            )
        )
    generation = SnapshotGeneration(
        generation_id=str(value.get("generation_id") or ""),
        generated_at=str(value.get("generated_at") or ""),
        source_timestamps=_freeze(value.get("source_timestamps") or {}),
        results=tuple(results),
        counts=_freeze(value.get("counts") or {}),
        published_ids=tuple(str(item) for item in value.get("published_ids") or ()),
        blocked_ids=tuple(str(item) for item in value.get("blocked_ids") or ()),
        missing_calendar_ids=tuple(str(item) for item in value.get("missing_calendar_ids") or ()),
        stale_calendar_ids=tuple(str(item) for item in value.get("stale_calendar_ids") or ()),
        missing_price_ids=tuple(str(item) for item in value.get("missing_price_ids") or ()),
    )
    actual_published = tuple(result.listing["id"] for result in generation.results if result.publishable)
    actual_blocked = tuple(result.listing["id"] for result in generation.results if not result.publishable)
    actual_counts = {
        "received": len(generation.results),
        "validated": len(generation.results),
        "blocked": len(actual_blocked),
        "published": len(actual_published),
        "calendar_covered": len(generation.results) - len(generation.missing_calendar_ids) - len(generation.stale_calendar_ids),
        "price_covered": len(generation.results) - len(generation.missing_price_ids),
    }
    if (
        not generation.generation_id
        or generation.published_ids != actual_published
        or generation.blocked_ids != actual_blocked
        or dict(generation.counts) != actual_counts
    ):
        raise ValueError("persisted monthly snapshot integrity check failed")
    return generation


class SnapshotStore:
    """Own the current immutable generation and swap it only after validation and disk save."""

    def __init__(self, persist_path: Optional[Any] = None) -> None:
        self.persist_path = Path(persist_path) if persist_path else None
        self.current: Optional[SnapshotGeneration] = None
        self.last_attempt: Optional[SnapshotGeneration] = None
        self.last_error: Optional[str] = None
        if self.persist_path and self.persist_path.exists():
            self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.persist_path.read_text(encoding="utf-8"))
            self.current = _generation_from_dict(payload)
            self.last_error = None
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self.current = None
            self.last_error = str(exc)

    def _persist(self, generation: SnapshotGeneration) -> None:
        if self.persist_path is None:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.persist_path.parent),
                prefix=self.persist_path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(generation.as_dict(), handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temporary), str(self.persist_path))
        finally:
            if temporary and temporary.exists():
                temporary.unlink()

    def refresh(
        self, source: Mapping[str, Any], settings: MonthlySettings, now: Any
    ) -> RefreshOutcome:
        try:
            generation = build_generation(source, settings, now)
            self.last_attempt = generation
            self._persist(generation)
        except (OSError, ValueError, TypeError) as exc:
            self.last_error = str(exc)
            return RefreshOutcome(False, self.current, self.last_error)
        self.current = generation
        self.last_error = None
        return RefreshOutcome(True, generation, None)
