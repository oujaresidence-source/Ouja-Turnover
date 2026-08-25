"""Operations workflow for monthly listing drafts, approvals, and readiness."""

from __future__ import annotations

import copy
import datetime as dt
import re
from typing import Any, Callable, Dict, Mapping, Optional

from .catalog_profiles import (
    CatalogContractError,
    apply_approved_profile,
    build_prefill,
    completion,
    parse_global_settings,
    parse_place,
    parse_profile,
    settings_form_values,
)
from .catalog_store import CatalogStore
from .publication import validate_listing
from .priority_places import (
    PRIORITY_PLACE_MIGRATION_ID,
    load_priority_places,
    nearest_places,
)
from .settings import MonthlySettings, load_settings
from .snapshot import SnapshotGeneration, revalidate_generation


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_BACKGROUND_BLOCKERS = frozenset(
    {
        "price_missing",
        "calendar_missing",
        "calendar_stale",
        "calendar_future",
        "calendar_invalid",
        "rating_unverified",
        "rating_invalid",
        "source_refresh_failed",
        "catalog_incomplete",
    }
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _listing_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _ID_RE.fullmatch(text):
        raise CatalogContractError(
            "listing_id",
            "invalid_listing_id",
            "معرّف الشقة غير صحيح.",
            "The listing ID is invalid.",
        )
    return text


def _source_id(row: Mapping[str, Any]) -> str:
    value = row.get("id")
    if value in (None, "") and isinstance(row.get("hostaway"), Mapping):
        value = row["hostaway"].get("id")
    return str(value or "").strip()


class CatalogService:
    """Coordinate trusted cached sources with revisioned staff approvals."""

    def __init__(
        self,
        store: CatalogStore,
        source_provider: Callable[[], Mapping[str, Any]],
        settings_fallback: Callable[[], Mapping[str, Any]],
        snapshot_refresh: Callable[[], Mapping[str, Any]],
        clock: Callable[[], dt.datetime] = _utc_now,
        active_snapshot_provider: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.store = store
        self.source_provider = source_provider
        self.settings_fallback = settings_fallback
        self.snapshot_refresh = snapshot_refresh
        self.clock = clock
        self.active_snapshot_provider = active_snapshot_provider
        self._priority_place_migration = {
            "applied": False,
            "migration_id": PRIORITY_PLACE_MIGRATION_ID,
        }

    def _now(self) -> dt.datetime:
        value = self.clock()
        if not isinstance(value, dt.datetime):
            raise TypeError("clock must return a datetime")
        return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)

    def _source(self) -> Dict[str, Any]:
        source = self.source_provider()
        if not isinstance(source, Mapping) or not isinstance(source.get("listings"), list):
            raise RuntimeError("monthly catalog source is unavailable")
        rows: Dict[str, Mapping[str, Any]] = {}
        duplicates = 0
        malformed = 0
        for raw in source["listings"]:
            if not isinstance(raw, Mapping):
                malformed += 1
                continue
            listing_id = _source_id(raw)
            if not _ID_RE.fullmatch(listing_id):
                malformed += 1
                continue
            if listing_id in rows:
                duplicates += 1
                continue
            rows[listing_id] = raw
        return {
            "rows": rows,
            "duplicates": duplicates,
            "malformed": malformed,
            "refresh_ok": source.get("refresh_ok") is True,
            "catalog_complete": source.get("catalog_complete") is True,
            "source_timestamps": copy.deepcopy(source.get("source_timestamps") or {}),
        }

    def _row(self, listing_id: str, source: Optional[Dict[str, Any]] = None) -> Mapping[str, Any]:
        key = _listing_id(listing_id)
        prepared = source or self._source()
        row = prepared["rows"].get(key)
        if row is None:
            raise CatalogContractError(
                "listing_id",
                "listing_not_found",
                "الشقة غير موجودة ضمن المخزون الحالي.",
                "The listing is not in the current inventory.",
            )
        return row

    def _fallback_values(self) -> Mapping[str, Any]:
        value = self.settings_fallback()
        return value if isinstance(value, Mapping) else {}

    def approved_settings_values(self) -> Mapping[str, Any]:
        record = self.store.settings()
        if isinstance(record.get("approved"), Mapping):
            return copy.deepcopy(record["approved"])
        return copy.deepcopy(dict(self._fallback_values()))

    def _effective_settings(self) -> MonthlySettings:
        return load_settings(self.approved_settings_values())

    def _active_publication(self, listing_id: str) -> Optional[tuple[bool, bool]]:
        """Return customer-visible publication state when a snapshot is connected."""

        if self.active_snapshot_provider is None:
            return None
        snapshot = self.active_snapshot_provider()
        if snapshot is None:
            return False, False
        if isinstance(snapshot, SnapshotGeneration):
            snapshot = revalidate_generation(snapshot, self._now())
        by_id = getattr(snapshot, "by_id", {})
        result = by_id.get(listing_id) if isinstance(by_id, Mapping) else None
        if result is None:
            return False, False
        return bool(result.publishable), bool(result.exact_match_eligible)

    @staticmethod
    def _parts(row: Mapping[str, Any]) -> tuple[Mapping[str, Any], Mapping[str, Any], Any, Any, Mapping[str, Any]]:
        hostaway = row.get("hostaway") if isinstance(row.get("hostaway"), Mapping) else row
        stay = row.get("stay") if isinstance(row.get("stay"), Mapping) else {}
        licence = row.get("licence")
        rating = row.get("rating")
        publication = row.get("publication")
        if not isinstance(publication, Mapping):
            publication = row.get("public") if isinstance(row.get("public"), Mapping) else row
        return hostaway, stay, licence, rating, publication

    def _prepared_listing(
        self, listing_id: str, source: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        key = _listing_id(listing_id)
        source_value = source or self._source()
        row = self._row(key, source_value)
        hostaway, stay, licence, rating, publication = self._parts(row)
        record = self.store.profile(key)
        prefill = build_prefill(
            hostaway,
            stay,
            licence,
            rating,
            approved=record.get("approved"),
            draft=record.get("draft"),
        )
        status = completion(
            {field: value for field, value in prefill.items() if field not in ("sources", "source_readiness")}
        )
        approved = record.get("approved")
        merged = apply_approved_profile(publication, approved)
        validation = validate_listing(merged, self._effective_settings(), self._now())
        publication_codes = [issue.code for issue in validation.blockers]
        warning_codes = [issue.code for issue in validation.warnings]
        background = [
            code for code in publication_codes + warning_codes if code in _BACKGROUND_BLOCKERS
        ]
        staff_publication = [
            code for code in publication_codes if code not in _BACKGROUND_BLOCKERS
        ]
        active_publication = self._active_publication(key)
        if active_publication is None:
            published = approved is not None and validation.publishable
            exact = published and validation.exact_match_eligible
        else:
            published, exact = active_publication
        source_title = str(
            hostaway.get("name")
            or hostaway.get("internal")
            or publication.get("name_en")
            or publication.get("name_ar")
            or key
        ).strip()
        images = prefill.get("images") or ()
        return {
            "id": key,
            "source_title": source_title,
            "first_image": images[0] if images else None,
            "prefill": prefill,
            "record": record,
            "completion": status,
            "staff_blockers": list(status["staff_blockers"]),
            "staff_publication_blockers": staff_publication,
            "background_blockers": list(dict.fromkeys(background)),
            "publication_warnings": warning_codes,
            "published": published,
            "exact_match_eligible": exact,
            "availability_status": validation.availability_status,
            "publication_result": validation,
            "source_timestamps": copy.deepcopy(source_value["source_timestamps"]),
        }

    @staticmethod
    def _row_status(prepared: Mapping[str, Any]) -> str:
        record = prepared["record"]
        if prepared["published"]:
            return "published"
        if record.get("approved") is not None and prepared["background_blockers"]:
            return "source_blocked"
        if prepared["completion"]["ready_for_approval"] and (
            record.get("approved") is None
            or record.get("draft_revision", 0) > record.get("approved_revision", 0)
        ):
            return "ready_for_approval"
        return "needs_review"

    def portfolio(self) -> Dict[str, Any]:
        source = self._source()
        listings = []
        for listing_id in sorted(
            source["rows"], key=lambda item: (0, int(item)) if item.isdigit() else (1, item)
        ):
            prepared = self._prepared_listing(listing_id, source)
            prefill = prepared["prefill"]
            record = prepared["record"]
            listings.append(
                {
                    "id": listing_id,
                    "source_title": prepared["source_title"],
                    "public_title_ar": prefill.get("name_ar"),
                    "public_title_en": prefill.get("name_en"),
                    "first_image": prepared["first_image"],
                    "neighborhood": prefill.get("neighborhood"),
                    "neighborhood_ar": prefill.get("neighborhood_ar"),
                    "neighborhood_en": prefill.get("neighborhood_en"),
                    "coordinates_verified": (
                        isinstance(prefill.get("coordinates"), Mapping)
                        and prefill["coordinates"].get("verified") is True
                        and bool(prefill["coordinates"].get("source"))
                    ),
                    "bedrooms": prefill.get("bedrooms"),
                    "completion_percent": prepared["completion"]["percent"],
                    "status": self._row_status(prepared),
                    "staff_blockers": prepared["staff_blockers"],
                    "background_blockers": prepared["background_blockers"],
                    "draft_revision": record["draft_revision"],
                    "approved_revision": record["approved_revision"],
                    "draft_updated_at": record["draft_updated_at"],
                    "approved_at": record["approved_at"],
                    "published": prepared["published"],
                    "exact_match_eligible": prepared["exact_match_eligible"],
                }
            )
        counts = {
            "received": len(listings),
            "needs_review": sum(row["status"] == "needs_review" for row in listings),
            "ready_for_approval": sum(row["status"] == "ready_for_approval" for row in listings),
            "approved": sum(row["approved_revision"] > 0 for row in listings),
            "published": sum(row["published"] for row in listings),
            "source_blocked": sum(row["status"] == "source_blocked" for row in listings),
            "duplicate_source_rows": source["duplicates"],
            "malformed_source_rows": source["malformed"],
        }
        launch_blockers = []
        if source["duplicates"]:
            launch_blockers.append("duplicate_listing_source")
        if source["malformed"]:
            launch_blockers.append("malformed_listing_source")
        if not source["refresh_ok"]:
            launch_blockers.append("source_refresh_failed")
        if not source["catalog_complete"]:
            launch_blockers.append("catalog_incomplete")
        return {
            "listings": listings,
            "counts": counts,
            "launch_blockers": launch_blockers,
            "source_timestamps": source["source_timestamps"],
        }

    def listing(self, listing_id: str) -> Dict[str, Any]:
        prepared = self._prepared_listing(listing_id)
        record = prepared["record"]
        result = prepared["publication_result"]
        public_listing = result.listing
        return {
            "id": prepared["id"],
            "source_title": prepared["source_title"],
            "prefill": prepared["prefill"],
            "draft": copy.deepcopy(record["draft"]),
            "approved_profile": copy.deepcopy(record["approved"]),
            "draft_revision": record["draft_revision"],
            "approved_revision": record["approved_revision"],
            "draft_updated_at": record["draft_updated_at"],
            "draft_updated_by": record["draft_updated_by"],
            "approved_at": record["approved_at"],
            "approved_by": record["approved_by"],
            "completion": prepared["completion"],
            "staff_blockers": prepared["staff_blockers"],
            "staff_publication_blockers": prepared["staff_publication_blockers"],
            "background_blockers": prepared["background_blockers"],
            "warnings": prepared["publication_warnings"],
            "published": prepared["published"],
            "exact_match_eligible": prepared["exact_match_eligible"],
            "availability_status": prepared["availability_status"],
            "source_readiness": {
                "price_months": sorted(public_listing.get("official_prices") or {}),
                "calendar": copy.deepcopy(dict(public_listing.get("calendar") or {})),
                "rating": prepared["prefill"].get("source_readiness", {}),
                "image_count": len(public_listing.get("images") or ()),
                "licence_present": bool((public_listing.get("licence") or {}).get("licence_no")),
            },
            "source_timestamps": prepared["source_timestamps"],
            "nearest_places": nearest_places(
                prepared["prefill"].get("coordinates"),
                self.approved_places(),
                limit=5,
            ),
            "audit": self.store.audit("listing:%s" % prepared["id"], limit=30),
        }

    def save_profile_draft(
        self, listing_id: str, value: Any, revision: int, actor: str
    ) -> Dict[str, Any]:
        key = _listing_id(listing_id)
        self._row(key)
        parsed = parse_profile(value)
        return self.store.save_profile_draft(key, parsed, revision, actor)

    def approve_profile(
        self, listing_id: str, revision: int, actor: str
    ) -> Dict[str, Any]:
        key = _listing_id(listing_id)
        self._row(key)
        record = self.store.profile(key)
        status = completion(record.get("draft") or {})
        if not status["ready_for_approval"]:
            raise CatalogContractError(
                "profile",
                "profile_incomplete",
                "أكمل حقول الشقة المطلوبة قبل الاعتماد.",
                "Complete the required listing fields before approval.",
            )
        approved_record = self.store.approve_profile(key, revision, actor)
        refresh = self.refresh()
        prepared = self._prepared_listing(key)
        return {
            "approved": approved_record.get("approved") is not None,
            "record": approved_record,
            "published": prepared["published"],
            "exact_match_eligible": prepared["exact_match_eligible"],
            "background_blockers": prepared["background_blockers"],
            "refresh": refresh,
        }

    def settings(self) -> Dict[str, Any]:
        record = self.store.settings()
        approved = record.get("approved")
        effective = self.approved_settings_values()
        parsed = load_settings(effective)
        return {
            **record,
            "effective": settings_form_values(parsed),
            "effective_source": "catalog_approved" if approved is not None else "environment_fallback",
            "blockers": [issue.as_dict() for issue in parsed.blockers],
        }

    def save_settings_draft(
        self, value: Any, revision: int, actor: str
    ) -> Dict[str, Any]:
        return self.store.save_settings_draft(
            parse_global_settings(value), revision, actor
        )

    def approve_settings(self, revision: int, actor: str) -> Dict[str, Any]:
        record = self.store.approve_settings(revision, actor)
        return {"approved": True, "record": record, "refresh": self.refresh()}

    def places(self) -> Dict[str, Any]:
        rows = self.store.places()
        active = sorted(
            place_id
            for place_id, row in rows.items()
            if row.get("active") and row.get("approved") is not None
        )
        category_counts: Dict[str, int] = {}
        for place_id in active:
            category_id = str(rows[place_id]["approved"].get("category_id") or "")
            if category_id:
                category_counts[category_id] = category_counts.get(category_id, 0) + 1
        return {
            "places": rows,
            "active": active,
            "category_counts": dict(sorted(category_counts.items())),
        }

    def seed_priority_places(self) -> Dict[str, Any]:
        """Apply the approved workbook extract once without replacing staff edits."""

        try:
            result = self.store.seed_approved_places_once(
                PRIORITY_PLACE_MIGRATION_ID,
                load_priority_places(),
                "system:priority_places",
            )
        except Exception as error:
            self._priority_place_migration = {
                "applied": False,
                "migration_id": PRIORITY_PLACE_MIGRATION_ID,
                "error": type(error).__name__,
            }
            raise
        self._priority_place_migration = {
            **copy.deepcopy(result),
            "applied": True,
        }
        return copy.deepcopy(result)

    def save_place_draft(
        self, place_id: str, value: Any, revision: int, actor: str
    ) -> Dict[str, Any]:
        key = str(place_id or "").strip()
        parsed = parse_place(value)
        return self.store.save_place_draft(key, parsed, revision, actor)

    def approve_place(
        self, place_id: str, revision: int, active: bool, actor: str
    ) -> Dict[str, Any]:
        record = self.store.approve_place(place_id, revision, active, actor)
        return {"approved": True, "record": record, "refresh": self.refresh()}

    def approved_profiles(self) -> Dict[str, Dict[str, Any]]:
        return self.store.approved_profiles()

    def approved_places(self) -> Dict[str, Dict[str, Any]]:
        return {
            place_id: copy.deepcopy(row["approved"])
            for place_id, row in self.store.places().items()
            if row.get("active") and isinstance(row.get("approved"), Mapping)
        }

    def approved_place_history(self) -> Dict[str, Dict[str, Any]]:
        """Keep approved labels available for historical leads after deactivation."""

        return {
            place_id: copy.deepcopy(row["approved"])
            for place_id, row in self.store.places().items()
            if isinstance(row.get("approved"), Mapping)
        }

    def refresh(self) -> Dict[str, Any]:
        try:
            result = self.snapshot_refresh()
            if not isinstance(result, Mapping):
                return {"accepted": False, "error": "refresh_unavailable"}
            return copy.deepcopy(dict(result))
        except Exception:
            return {"accepted": False, "error": "source_unavailable"}

    def health(self) -> Dict[str, Any]:
        portfolio = self.portfolio()
        settings = self.settings()
        places = self.places()
        probe = self.store.probe()
        return {
            "approved_profiles": portfolio["counts"]["approved"],
            "drafts_waiting": sum(
                row["draft_revision"] > row["approved_revision"]
                for row in portfolio["listings"]
            ),
            "published_profiles": portfolio["counts"]["published"],
            "profile_completion_average": (
                round(
                    sum(row["completion_percent"] for row in portfolio["listings"])
                    / len(portfolio["listings"]),
                    1,
                )
                if portfolio["listings"]
                else 0
            ),
            "settings_source": settings["effective_source"],
            "settings_ready": not settings["blockers"],
            "active_destinations": len(places["active"]),
            "destination_categories": copy.deepcopy(places["category_counts"]),
            "priority_place_migration": copy.deepcopy(
                self._priority_place_migration
            ),
            "verified_apartment_coordinates": sum(
                row["coordinates_verified"] for row in portfolio["listings"]
            ),
            "missing_apartment_coordinates": sum(
                not row["coordinates_verified"] for row in portfolio["listings"]
            ),
            "write_probe": probe.get("ok") is True,
            "journal_mode": probe.get("journal_mode"),
        }


__all__ = ["CatalogService"]
