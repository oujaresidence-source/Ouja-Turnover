"""Read-only internal preview contracts for incomplete monthly inventory."""

from __future__ import annotations

import copy
import uuid
from dataclasses import replace
from types import MappingProxyType
from typing import Any, Dict, Mapping

from .contracts import ContractError, parse_match_request
from .matching import catalog_claim, rank, space_matches
from .presentation import present_card
from .publication import PublicationResult, validate_listing
from .routes import MonthlyPublicApp, _contract_error, _internal_error, _language
from .settings import load_settings
from .snapshot import SnapshotGeneration, SnapshotStore


_PREVIEW_DEPOSIT_RANGE_SAR = MappingProxyType(
    {"minimum": 500, "maximum": 2500}
)
_PREVIEW_WORKING_HOURS = {
    "timezone": "Asia/Riyadh",
    "schedule": {
        day: [["10:00", "22:00"]]
        for day in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    },
}


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
        listing["preview_complete"] = not missing
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


def _preview_settings() -> Any:
    """Use approved temporary hours while retaining every unresolved launch block."""

    return load_settings(
        {
            "whatsapp_number": None,
            "working_hours": _PREVIEW_WORKING_HOURS,
            "commercial_terms": None,
            "long_stay_route": None,
        }
    )


def _preview_card(result: PublicationResult, language: str) -> Dict[str, Any]:
    card = present_card(result, language)
    card.update(
        {
            "preview": True,
            "preview_complete": bool(result.listing.get("preview_complete")),
            "preview_missing": list(result.listing.get("preview_missing") or ()),
        }
    )
    return card


def _exact_generation(generation: SnapshotGeneration) -> SnapshotGeneration:
    results = tuple(row for row in generation.results if row.exact_match_eligible)
    identifiers = tuple(row.listing["id"] for row in results)
    return replace(
        generation,
        results=results,
        published_ids=identifiers,
        blocked_ids=(),
    )


class MonthlyPreviewApp(MonthlyPublicApp):
    """Read-only customer facade for authenticated staff preview routes."""

    def _request_context(self) -> tuple[Any, Any]:
        # Public request-time revalidation intentionally restores publication
        # gates. Preview keeps the immutable, explicitly labelled staff view.
        return self._now(), self._generation()

    def config(self, lang: Any = "ar") -> Dict[str, Any]:
        result = super().config(lang)
        if result.get("ok"):
            result.update(
                {
                    "preview": True,
                    "contact_enabled": False,
                    "deposit_range_sar": dict(_PREVIEW_DEPOSIT_RANGE_SAR),
                }
            )
        return result

    def browse(self, value: Any) -> Dict[str, Any]:
        response = super().browse(value)
        if response.get("ok"):
            generation = self._generation()
            by_id = generation.by_id if generation is not None else {}
            language = "en" if isinstance(value, Mapping) and value.get("lang") == "en" else "ar"
            response["preview"] = True
            response["results"] = [
                {
                    **row,
                    **(
                        {
                            "preview": True,
                            "preview_complete": bool(by_id[str(row["id"])].listing.get("preview_complete")),
                            "preview_missing": list(by_id[str(row["id"])].listing.get("preview_missing") or ()),
                        }
                        if str(row["id"]) in by_id
                        else {}
                    ),
                }
                for row in response.get("results") or ()
            ]
            response["catalog_claim"] = catalog_claim(len(response["results"]), language)
        return response

    def match(self, value: Any, lang: Any = "ar") -> Dict[str, Any]:
        try:
            current, generation = self._request_context()
            _settings, approved_places = self._configuration()
            if generation is None:
                return {
                    "ok": False,
                    "error": {
                        "field": "snapshot",
                        "code": "snapshot_missing",
                        "message_ar": "لا توجد بيانات للمعاينة حاليًا.",
                        "message_en": "No preview inventory is available.",
                    },
                }
            request = self._canonical_request(
                parse_match_request(value), generation, approved_places
            )
            language = _language(lang)
            ranked = rank(
                _exact_generation(generation),
                request,
                language,
                now=current,
                places=self._place_registry(generation, approved_places),
            )
            all_cards = []
            incomplete_alternatives = []
            ranked_ids = {
                str(row["id"])
                for section in ("top", "alternatives", "near_matches")
                for row in ranked.get(section) or ()
            }
            for publication in self._published(generation):
                card = _preview_card(publication, language)
                all_cards.append(card)
                if (
                    str(card["id"]) not in ranked_ids
                    and space_matches(publication.listing, request)
                ):
                    alternative = dict(card)
                    alternative.update(
                        {
                            "reasons": (
                                "السعة الموثقة تناسب عدد المقيمين.",
                            )
                            if language == "ar"
                            else ("Verified capacity fits the resident count.",),
                            "reason_codes": ("capacity_match",),
                            "tradeoff": (
                                "السعر أو التوفر أو بيانات النشر تحتاج تأكيد قبل الحجز."
                                if language == "ar"
                                else "Price, availability, or publication details need confirmation before booking."
                            ),
                            "fit_score": None,
                        }
                    )
                    incomplete_alternatives.append(alternative)
            by_id = {str(row.listing["id"]): row for row in generation.results}
            for section in ("top", "alternatives", "near_matches"):
                decorated = []
                for row in ranked.get(section) or ():
                    publication = by_id.get(str(row["id"]))
                    decorated.append(
                        {
                            **(
                                _preview_card(publication, language)
                                if publication
                                else {}
                            ),
                            **row,
                        }
                    )
                ranked[section] = tuple(decorated)
            ranked["alternatives"] = tuple(ranked["alternatives"]) + tuple(
                incomplete_alternatives
            )
            ranked["catalog"] = tuple(all_cards)
            ranked["catalog_count"] = len(all_cards)
            ranked["catalog_claim"] = catalog_claim(len(all_cards), language)
            return {"ok": True, "preview": True, **ranked}
        except ContractError as error:
            return _contract_error(error)
        except Exception:
            return _internal_error()

    def listing(self, value: Any) -> Dict[str, Any]:
        response = super().listing(value)
        if not response.get("ok"):
            return response
        generation = self._generation()
        listing_id = str(response["listing"]["id"])
        publication = generation.by_id.get(listing_id) if generation is not None else None
        if publication is not None:
            language = "en" if isinstance(value, Mapping) and value.get("lang") == "en" else "ar"
            response["listing"].update(_preview_card(publication, language))
        response["preview"] = True
        return response

    @staticmethod
    def lead(_value: Any) -> Dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "field": "whatsapp_number",
                "code": "preview_contact_disabled",
                "message_ar": "التواصل مقفول في المعاينة حتى يُضاف رقم واتساب عوجا.",
                "message_en": "Contact is disabled in preview until Ouja's WhatsApp number is configured.",
            },
        }

    event = lead


def build_preview_app(service: Any, *, clock: Any) -> MonthlyPreviewApp:
    """Build one isolated preview app without replacing the public snapshot."""

    current = clock()
    validation_settings = load_settings(service.approved_settings_values())
    generation = build_preview_generation(
        service.preview_inventory(), validation_settings, current
    )
    snapshot = SnapshotStore()
    snapshot.current = generation
    return MonthlyPreviewApp(
        snapshot_store=snapshot,
        settings=_preview_settings(),
        lead_store=None,
        analytics_store=None,
        approved_places=service.approved_places(),
        session_secret=None,
        clock=clock,
    )


__all__ = ["MonthlyPreviewApp", "build_preview_app", "build_preview_generation"]
