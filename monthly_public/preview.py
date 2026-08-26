"""Read-only internal preview contracts for incomplete monthly inventory."""

from __future__ import annotations

import copy
import uuid
from types import MappingProxyType
from typing import Any, Dict, Mapping

from .publication import PublicationResult, validate_listing
from .snapshot import SnapshotGeneration


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _codes(result: PublicationResult, collection: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(item.code for item in getattr(result, collection))
    )


def build_preview_generation(
    source: Mapping[str, Any], settings: Any, now: Any
) -> SnapshotGeneration:
    """Build an in-memory preview containing all real, deduplicated source rows."""

    if not isinstance(source, Mapping):
        raise ValueError("preview source must be a mapping")
    listings = source.get("listings")
    if not isinstance(listings, (list, tuple)) or not listings:
        raise ValueError("preview source has no listings")
    raw_ids = [str(row.get("id") or "") for row in listings if isinstance(row, Mapping)]
    if len(raw_ids) != len(listings) or not all(raw_ids) or len(raw_ids) != len(set(raw_ids)):
        raise ValueError("preview source contains malformed or duplicate listings")

    results = []
    missing_calendar_ids = []
    stale_calendar_ids = []
    missing_price_ids = []
    calendar_codes = {"calendar_missing", "calendar_stale", "calendar_future", "calendar_invalid"}
    for raw in listings:
        validated = validate_listing(copy.deepcopy(dict(raw)), settings, now)
        listing = _plain(validated.listing)
        listing_id = str(listing.get("id") or raw.get("id"))
        if not listing.get("name_ar"):
            listing["name_ar"] = "شقة %s · بيانات قيد الإكمال" % listing_id
        if not listing.get("name_en"):
            listing["name_en"] = "Ouja | Apartment %s" % listing_id
        blocker_codes = _codes(validated, "blockers")
        warning_codes = _codes(validated, "warnings")
        missing = tuple(dict.fromkeys(blocker_codes + warning_codes))
        listing["preview"] = True
        listing["preview_missing"] = missing
        listing["preview_complete"] = not blocker_codes
        results.append(
            PublicationResult(
                listing=_freeze(listing),
                blockers=validated.blockers,
                warnings=validated.warnings,
                availability_status=validated.availability_status,
                publishable=True,
                exact_match_eligible=validated.exact_match_eligible,
            )
        )
        if "calendar_missing" in warning_codes:
            missing_calendar_ids.append(listing_id)
        if calendar_codes.intersection(warning_codes):
            stale_calendar_ids.append(listing_id)
        if "price_missing" in blocker_codes:
            missing_price_ids.append(listing_id)

    result_tuple = tuple(results)
    identifiers = tuple(result.listing["id"] for result in result_tuple)
    counts = {
        "received": len(result_tuple),
        "validated": len(result_tuple),
        "blocked": 0,
        "published": len(result_tuple),
        "calendar_covered": sum(
            result.availability_status == "confirmed" for result in result_tuple
        ),
        "price_covered": len(result_tuple) - len(missing_price_ids),
    }
    timestamps = source.get("source_timestamps")
    if not isinstance(timestamps, Mapping):
        timestamps = {}
    return SnapshotGeneration(
        generation_id="preview_%s" % uuid.uuid4().hex,
        generated_at=now.isoformat(),
        source_timestamps=_freeze(
            {str(key): str(value) for key, value in timestamps.items() if value}
        ),
        results=result_tuple,
        counts=_freeze(counts),
        published_ids=identifiers,
        blocked_ids=(),
        missing_calendar_ids=tuple(missing_calendar_ids),
        stale_calendar_ids=tuple(stale_calendar_ids),
        missing_price_ids=tuple(missing_price_ids),
    )


__all__ = ["build_preview_generation"]
