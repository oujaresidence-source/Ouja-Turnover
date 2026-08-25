"""Operational launch-health summary for the public monthly product."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .settings import MonthlySettings
from .snapshot import SnapshotGeneration, revalidate_generation


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
_CALENDAR_READINESS_CODES = frozenset(
    {"calendar_missing", "calendar_stale", "calendar_future", "calendar_invalid"}
)


def _action_section(code: str) -> str:
    if code in _CONTENT_CODES:
        return "content"
    if code in _LICENCE_CODES:
        return "identity"
    if code in _CALENDAR_READINESS_CODES or code.startswith(("price_", "rating_")):
        return "sources"
    if code in ("title_bedroom_conflict", "bedrooms_missing", "bathrooms_missing", "capacity_missing"):
        return "space"
    return "approval"


def _issue(issue: Any, *, listing_id: Optional[str] = None, source: str = "publication") -> Dict[str, Any]:
    value = issue.as_dict()
    value["source"] = source
    if listing_id is not None:
        value["listing_id"] = listing_id
        value["action_url"] = "/monthly/ops/listings?id=%s&section=%s" % (
            listing_id,
            _action_section(str(value.get("code") or "")),
        )
    return value


def build_health(
    generation: Optional[SnapshotGeneration],
    settings: MonthlySettings,
    *,
    analytics: Any = None,
    lead_store: Any = None,
    catalog: Any = None,
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
        if now is not None:
            generation = revalidate_generation(generation, now)
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
            red.extend(
                _issue(item, listing_id=listing_id)
                for item in result.warnings
                if item.code in _CALENDAR_READINESS_CODES
            )

    for blocker in settings.blockers:
        red.append(_issue(blocker, source="settings"))

    catalog_health = {
        "configured": False,
        "approved_profiles": 0,
        "drafts_waiting": 0,
        "published_profiles": 0,
        "profile_completion_average": 0,
        "settings_source": None,
        "settings_ready": False,
        "active_destinations": 0,
        "destination_categories": {},
        "priority_place_migration": {"applied": False},
        "verified_apartment_coordinates": 0,
        "missing_apartment_coordinates": 0,
        "write_probe": False,
        "journal_mode": None,
    }
    if isinstance(catalog, Mapping):
        catalog_health["configured"] = catalog.get("configured", True) is True
        for key in (
            "approved_profiles",
            "drafts_waiting",
            "published_profiles",
            "profile_completion_average",
            "active_destinations",
            "verified_apartment_coordinates",
            "missing_apartment_coordinates",
        ):
            value = catalog.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                catalog_health[key] = value
        for key in ("destination_categories", "priority_place_migration"):
            value = catalog.get(key)
            if isinstance(value, Mapping):
                catalog_health[key] = dict(value)
        catalog_health["settings_source"] = catalog.get("settings_source")
        catalog_health["settings_ready"] = catalog.get("settings_ready") is True
        catalog_health["write_probe"] = catalog.get("write_probe") is True
        catalog_health["journal_mode"] = catalog.get("journal_mode")
        if not catalog_health["configured"] or not catalog_health["write_probe"]:
            red.append(
                {
                    "source": "catalog",
                    "code": "catalog_store_unhealthy",
                    "field": "catalog",
                    "message_ar": "تخزين بيانات تجهيز الشقق غير سليم.",
                    "message_en": "The listing-readiness store is unhealthy.",
                    "action_url": "/monthly/ops/listings",
                }
            )

    if analytics is None:
        analytics_health = {
            "healthy": False,
            "write_probe": False,
            "event_count": None,
            "error": "analytics store is not configured",
            "configured": False,
        }
        red.append(
            {
                "source": "analytics",
                "code": "analytics_missing",
                "field": "analytics",
                "message_ar": "تخزين التحليلات غير مهيأ.",
                "message_en": "Analytics storage is not configured.",
            }
        )
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
        if not analytics_health.get("healthy") or not analytics_health.get("write_probe"):
            red.append(
                {
                    "source": "analytics",
                    "code": "analytics_unhealthy",
                    "field": "analytics",
                    "message_ar": "تخزين التحليلات غير سليم.",
                    "message_en": "Analytics storage is unhealthy.",
                }
            )

    if lead_store is None:
        lead_health = {
            "healthy": False,
            "write_probe": False,
            "lead_count": None,
            "error": "lead store is not configured",
            "configured": False,
        }
        red.append(
            {
                "source": "leads",
                "code": "lead_store_missing",
                "field": "leads",
                "message_ar": "تخزين الطلبات غير مهيأ.",
                "message_en": "Lead storage is not configured.",
            }
        )
    else:
        try:
            lead_health = dict(lead_store.health())
        except Exception as error:
            lead_health = {
                "healthy": False,
                "write_probe": False,
                "lead_count": None,
                "error": str(error),
            }
        lead_health["configured"] = True
        if not lead_health.get("healthy") or not lead_health.get("write_probe"):
            red.append(
                {
                    "source": "leads",
                    "code": "lead_store_unhealthy",
                    "field": "leads",
                    "message_ar": "تخزين الطلبات غير قابل للكتابة.",
                    "message_en": "Lead storage is not writable.",
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
        "leads": lead_health,
        "catalog": catalog_health,
        "red_blockers": red,
    }
    report["ready"] = not red
    return report
