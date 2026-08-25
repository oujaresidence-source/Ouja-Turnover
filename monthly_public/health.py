"""Operational launch-health summary for the public monthly product."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .settings import MonthlySettings
from .snapshot import SnapshotGeneration


_CONTENT_CODES = frozenset(
    {
        "content_unverified",
        "arabic_title_missing",
        "english_title_missing",
        "arabic_content_missing",
        "english_content_missing",
        "title_bedroom_conflict",
        "untranslated_amenity",
    }
)
_LICENCE_CODES = frozenset(
    {"licence_missing", "licence_expiry_missing", "licence_expiry_invalid", "licence_expired", "licence_expiring"}
)


def _issue(issue: Any, *, listing_id: Optional[str] = None, source: str = "publication") -> Dict[str, Any]:
    value = issue.as_dict()
    value["source"] = source
    if listing_id is not None:
        value["listing_id"] = listing_id
    return value


def build_health(
    generation: Optional[SnapshotGeneration],
    settings: MonthlySettings,
    *,
    analytics: Any = None,
    now: Any = None,
) -> Dict[str, Any]:
    """Build one evidence-based status payload; readiness means no red blockers."""

    red = []
    publication_blockers: Dict[str, list[Dict[str, Any]]] = {}
    content: Dict[str, list[Dict[str, Any]]] = {}
    licences: Dict[str, list[Dict[str, Any]]] = {}
    if generation is None:
        red.append(
            {
                "source": "snapshot",
                "code": "snapshot_missing",
                "field": "snapshot",
                "message_ar": "لا توجد لقطة نشر صالحة.",
                "message_en": "No valid publication snapshot is available.",
            }
        )
        raw_counts: Mapping[str, int] = {}
        refresh_time = None
        generation_id = None
        source_timestamps: Dict[str, str] = {}
        coverage_details = {
            "calendar": {"covered": 0, "missing_ids": [], "stale_ids": []},
            "price": {"covered": 0, "missing_ids": []},
        }
    else:
        raw_counts = generation.counts
        refresh_time = generation.generated_at
        generation_id = generation.generation_id
        source_timestamps = dict(generation.source_timestamps)
        coverage_details = {
            "calendar": {
                "covered": int(raw_counts.get("calendar_covered", 0)),
                "missing_ids": list(generation.missing_calendar_ids),
                "stale_ids": list(generation.stale_calendar_ids),
            },
            "price": {
                "covered": int(raw_counts.get("price_covered", 0)),
                "missing_ids": list(generation.missing_price_ids),
            },
        }
        for result in generation.results:
            listing_id = result.listing["id"]
            if result.blockers:
                publication_blockers[listing_id] = [_issue(item, listing_id=listing_id) for item in result.blockers]
                red.extend(publication_blockers[listing_id])
            content_items = [_issue(item, listing_id=listing_id) for item in result.blockers + result.warnings if item.code in _CONTENT_CODES]
            if content_items:
                content[listing_id] = content_items
            licence_items = [_issue(item, listing_id=listing_id) for item in result.blockers + result.warnings if item.code in _LICENCE_CODES]
            if licence_items:
                licences[listing_id] = licence_items

    for blocker in settings.blockers:
        red.append(_issue(blocker, source="settings"))

    if analytics is None:
        analytics_health = {"healthy": True, "event_count": None, "error": None, "configured": False}
    else:
        try:
            analytics_health = dict(analytics.health())
        except Exception as error:
            analytics_health = {
                "healthy": False,
                "event_count": None,
                "error": str(error),
            }
        analytics_health["configured"] = True
        if not analytics_health.get("healthy"):
            red.append(
                {
                    "source": "analytics",
                    "code": "analytics_unhealthy",
                    "field": "analytics",
                    "message_ar": "تخزين التحليلات غير سليم.",
                    "message_en": "Analytics storage is unhealthy.",
                }
            )

    counts = {
        "received": int(raw_counts.get("received", 0)),
        "valid": int(raw_counts.get("validated", raw_counts.get("valid", 0))),
        "blocked": int(raw_counts.get("blocked", 0)),
        "published": int(raw_counts.get("published", 0)),
    }
    coverage = {
        "calendar": int(raw_counts.get("calendar_covered", 0)),
        "price": int(raw_counts.get("price_covered", 0)),
    }
    report = {
        "checked_at": now.isoformat() if hasattr(now, "isoformat") else None,
        "refresh_time": refresh_time,
        "generation_id": generation_id,
        "source_timestamps": source_timestamps,
        "counts": counts,
        "coverage": coverage,
        "coverage_details": coverage_details,
        "configuration": {
            "whatsapp": bool(settings.whatsapp_number),
            "working_hours": settings.working_hours is not None,
        },
        "contract_4_6_months": {
            "ready": bool(settings.long_stay_route),
            "route": settings.long_stay_route,
        },
        "publication_blockers": publication_blockers,
        "content_conflicts": content,
        "licence_expiry": licences,
        "analytics": analytics_health,
        "red_blockers": red,
    }
    report["ready"] = not red
    return report
