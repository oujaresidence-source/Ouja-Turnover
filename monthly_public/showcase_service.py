"""Focused staff and public workflows for monthly showcase groups."""

from __future__ import annotations

import copy
import datetime as dt
import re
import secrets
from dataclasses import replace
from typing import Any, Callable, Dict, Mapping, Optional

from .presentation import present_listing
from .publication import PublicationResult
from .showcase_contracts import (
    ShowcaseContextError,
    issue_showcase_context,
    parse_showcase,
    verify_showcase_context,
)
from .showcase_store import ShowcaseStore


_LISTING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_GROUP_ID_RE = re.compile(r"^showcase_[A-Za-z0-9_-]{2,64}$")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ShowcaseNotFound(LookupError):
    """The requested group has no approved public version."""


def _listing_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _LISTING_ID_RE.fullmatch(text):
        raise ValueError("invalid listing ID")
    return text


def _group_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _GROUP_ID_RE.fullmatch(text):
        raise ValueError("invalid showcase group ID")
    return text


def _language(value: Any) -> str:
    if value not in ("ar", "en"):
        raise ValueError("language must be ar or en")
    return str(value)


class ShowcaseService:
    """Coordinate approved groups with the cached publication snapshot."""

    def __init__(
        self,
        store: ShowcaseStore,
        inventory_provider: Callable[[], Mapping[str, Any]],
        snapshot_provider: Callable[[], Any],
        session_secret: Any,
        clock: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        self.store = store
        self.inventory_provider = inventory_provider
        self.snapshot_provider = snapshot_provider
        self.session_secret = session_secret
        self.clock = clock

    def _now(self) -> dt.datetime:
        value = self.clock()
        if not isinstance(value, dt.datetime):
            raise TypeError("clock must return a datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value

    def _known_listing_ids(self) -> set[str]:
        source = self.inventory_provider()
        if not isinstance(source, Mapping) or not isinstance(
            source.get("listings"), (list, tuple)
        ):
            raise RuntimeError("monthly showcase inventory is unavailable")
        known = set()
        for row in source["listings"]:
            if not isinstance(row, Mapping):
                continue
            value = row.get("id")
            if value in (None, "") and isinstance(row.get("hostaway"), Mapping):
                value = row["hostaway"].get("id")
            listing_id = str(value or "").strip()
            if _LISTING_ID_RE.fullmatch(listing_id):
                known.add(listing_id)
        if not known:
            raise RuntimeError("monthly showcase inventory is empty")
        return known

    def _results_by_id(self) -> Dict[str, PublicationResult]:
        generation = self.snapshot_provider()
        values = getattr(generation, "results", None)
        if values is None:
            values = getattr(generation, "published", None)
        if not isinstance(values, (list, tuple)):
            raise RuntimeError("monthly publication snapshot is unavailable")
        result: Dict[str, PublicationResult] = {}
        for row in values:
            if not isinstance(row, PublicationResult):
                continue
            listing_id = str(row.listing.get("id") or "")
            if _LISTING_ID_RE.fullmatch(listing_id) and listing_id not in result:
                result[listing_id] = row
        return result

    @staticmethod
    def _price_can_complete(group: Mapping[str, Any], result: PublicationResult) -> bool:
        if group.get("fixed_price_enabled") is not True:
            return False
        rate = group.get("fixed_monthly_rate_sar")
        if isinstance(rate, bool) or not isinstance(rate, int) or rate < 1:
            return False
        return bool(result.blockers) and {
            issue.code for issue in result.blockers
        } == {"price_missing"}

    def _eligible_by_id(
        self,
        group: Mapping[str, Any],
    ) -> Dict[str, PublicationResult]:
        eligible = {}
        for listing_id, result in self._results_by_id().items():
            if result.publishable:
                eligible[listing_id] = result
            elif self._price_can_complete(group, result):
                eligible[listing_id] = replace(
                    result,
                    blockers=(),
                    publishable=True,
                    exact_match_eligible=result.availability_status == "confirmed",
                )
        return eligible

    def eligible_result(
        self,
        group: Mapping[str, Any],
        listing_id: Any,
    ) -> Optional[PublicationResult]:
        key = _listing_id(listing_id)
        members = {str(value) for value in group.get("listing_ids") or ()}
        if key not in members:
            return None
        return self._eligible_by_id(group).get(key)

    def create_draft(
        self,
        value: Mapping[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        parsed = parse_showcase(value, self._known_listing_ids())
        for _attempt in range(5):
            group_id = "showcase_%s" % secrets.token_urlsafe(12)
            if self.store.record(group_id)["draft"] is None:
                return self.store.save_draft(group_id, parsed, 0, actor)
        raise RuntimeError("could not allocate a showcase group ID")

    def save_draft(
        self,
        group_id: Any,
        value: Mapping[str, Any],
        revision: int,
        actor: str,
    ) -> Dict[str, Any]:
        key = _group_id(group_id)
        parsed = parse_showcase(value, self._known_listing_ids())
        return self.store.save_draft(key, parsed, revision, actor)

    def approve(
        self,
        group_id: Any,
        revision: int,
        actor: str,
    ) -> Dict[str, Any]:
        key = _group_id(group_id)
        record = self.store.record(key)
        if not isinstance(record.get("draft"), Mapping):
            raise ShowcaseNotFound(key)
        parse_showcase(record["draft"], self._known_listing_ids())
        return self.store.approve(key, revision, actor)

    def set_price_enabled(
        self,
        group_id: Any,
        enabled: bool,
        revision: int,
        actor: str,
    ) -> Dict[str, Any]:
        return self.store.set_price_enabled(
            _group_id(group_id),
            enabled,
            revision,
            actor,
        )

    def _staff_record(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        value = record.get("draft") or record.get("approved") or {}
        configured = [str(item) for item in value.get("listing_ids") or ()]
        eligible = self._eligible_by_id(value) if value else {}
        blocked = [listing_id for listing_id in configured if listing_id not in eligible]
        return {
            **copy.deepcopy(dict(record)),
            "configured_count": len(configured),
            "eligible_count": len(configured) - len(blocked),
            "blocked_listing_ids": blocked,
            "public_url": (
                "/monthly/showcase/%s" % record["approved"]["slug"]
                if isinstance(record.get("approved"), Mapping)
                else None
            ),
        }

    def group(self, group_id: Any) -> Dict[str, Any]:
        key = _group_id(group_id)
        record = self.store.record(key)
        if record.get("draft") is None and record.get("approved") is None:
            raise ShowcaseNotFound(key)
        return self._staff_record(record)

    def portfolio(self) -> list[Dict[str, Any]]:
        return [self._staff_record(record) for record in self.store.list_records()]

    def memberships(self) -> Dict[str, list[Dict[str, Any]]]:
        result: Dict[str, list[Dict[str, Any]]] = {}
        for record in self.store.list_records():
            value = record.get("draft") or record.get("approved") or {}
            for listing_id in value.get("listing_ids") or ():
                result.setdefault(str(listing_id), []).append(
                    {
                        "group_id": record["group_id"],
                        "name_ar": value.get("name_ar") or "",
                        "name_en": value.get("name_en") or "",
                        "approved": record.get("approved") is not None,
                    }
                )
        return result

    def public_by_slug(self, slug: str, lang: str = "ar") -> Dict[str, Any]:
        language = _language(lang)
        record = self.store.by_approved_slug(slug)
        if record is None or not isinstance(record.get("approved"), Mapping):
            raise ShowcaseNotFound(str(slug))
        group = copy.deepcopy(record["approved"])
        eligible = self._eligible_by_id(group)
        results = tuple(
            eligible[listing_id]
            for listing_id in group["listing_ids"]
            if listing_id in eligible
        )
        return {
            "group_id": record["group_id"],
            "revision": record["approved_revision"],
            "group": group,
            "results": results,
            "configured_count": len(group["listing_ids"]),
            "eligible_count": len(results),
            "lang": language,
            "context": issue_showcase_context(
                self.session_secret,
                record["group_id"],
                record["approved_revision"],
            ),
        }

    def context_for_slug(self, slug: str) -> Dict[str, Any]:
        public = self.public_by_slug(slug, "ar")
        return {
            "group_id": public["group_id"],
            "revision": public["revision"],
            "context": public["context"],
        }

    def resolve_context(self, token: Any) -> Dict[str, Any]:
        context = verify_showcase_context(token, self.session_secret)
        record = self.store.record(context["group_id"])
        if not isinstance(record.get("approved"), Mapping):
            raise ShowcaseContextError("showcase context has no approved group")
        return {
            "group_id": record["group_id"],
            "revision": record["approved_revision"],
            "token_revision": context["revision"],
            "group": copy.deepcopy(record["approved"]),
        }

    def health(self) -> Dict[str, Any]:
        records = self.store.list_records()
        approved = [row for row in records if isinstance(row.get("approved"), Mapping)]
        blocked_members = 0
        enabled = 0
        for row in approved:
            group = row["approved"]
            if group.get("fixed_price_enabled") is True:
                enabled += 1
            eligible = self._eligible_by_id(group)
            blocked_members += sum(
                1 for listing_id in group.get("listing_ids") or () if listing_id not in eligible
            )
        return {
            "configured": True,
            "write_probe": self.store.write_probe(),
            "received": len(records),
            "approved": len(approved),
            "fixed_price_enabled": enabled,
            "blocked_members": blocked_members,
        }


def present_showcase(public: Mapping[str, Any], lang: str) -> Dict[str, Any]:
    """Return only public, approved, localized group and listing fields."""

    language = _language(lang)
    suffix = "ar" if language == "ar" else "en"
    group = public["group"]
    enabled = group.get("fixed_price_enabled") is True
    return {
        "group_id": public["group_id"],
        "revision": public["revision"],
        "slug": group["slug"],
        "name": group["name_%s" % suffix],
        "description": group.get("description_%s" % suffix) or "",
        "image_url": group.get("image_url"),
        "price_mode": "fixed" if enabled else "listing",
        "fixed_price_enabled": enabled,
        "fixed_monthly_rate_sar": (
            group.get("fixed_monthly_rate_sar") if enabled else None
        ),
        "eligible_count": public["eligible_count"],
        "context": public["context"],
        "homes": tuple(
            present_listing(result, language) for result in public["results"]
        ),
    }
