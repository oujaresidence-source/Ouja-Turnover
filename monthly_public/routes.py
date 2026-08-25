"""Framework-neutral request services for the public monthly product.

Customer methods deliberately own no refresh or provider capability. They read
one immutable ``SnapshotStore.current`` generation and use local stores only.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any, Dict, Mapping, Optional

from .analytics import funnel_summary
from .contracts import (
    ContractError,
    issue_anonymous_session,
    parse_browse_query,
    parse_event,
    parse_listing_request,
    parse_match_request,
    parse_outcome,
)
from .health import build_health
from .leads import (
    ALTERNATIVE_REASONS,
    HandoffValidationError,
    INFORMATION_REASONS,
    STAFF_ACTIONS,
    build_general_whatsapp_handoff,
    build_whatsapp_handoff,
)
from .matching import rank, space_matches
from .presentation import present_card, present_listing
from .pricing import add_months, quote_for
from .settings import MonthlySettings, response_window
from .snapshot import revalidate_generation


_LEAD_REFERENCE_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{5,63}$")


def _error(code: str, message_ar: str, message_en: str, *, field: str = "request") -> Dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "field": field,
            "code": code,
            "message_ar": message_ar,
            "message_en": message_en,
        },
    }


def _contract_error(error: ContractError) -> Dict[str, Any]:
    return {"ok": False, "error": error.as_dict()}


def _internal_error() -> Dict[str, Any]:
    return _error(
        "request_failed",
        "تعذر إكمال الطلب حاليًا. حاول مرة ثانية.",
        "The request could not be completed right now. Please try again.",
    )


def _language(value: Any) -> str:
    if value in (None, "", "ar"):
        return "ar"
    if value == "en":
        return "en"
    raise ContractError(
        "lang",
        "unsupported",
        "اللغة المحددة غير معتمدة.",
        "The selected language is unsupported.",
    )


def _window(request: Mapping[str, Any]) -> Optional[tuple[dt.date, dt.date]]:
    try:
        start = dt.date.fromisoformat(str(request.get("move_in")))
    except (TypeError, ValueError):
        return None
    if request.get("move_out"):
        try:
            end = dt.date.fromisoformat(str(request["move_out"]))
        except (TypeError, ValueError):
            return None
    else:
        value = add_months(start.isoformat(), request.get("duration_months"))
        try:
            end = dt.date.fromisoformat(str(value))
        except (TypeError, ValueError):
            return None
    return (start, end) if end > start else None


def _availability(result: Any, request: Mapping[str, Any]) -> str:
    if result.availability_status != "confirmed":
        return "pending"
    window = _window(request)
    calendar = result.listing.get("calendar") or {}
    try:
        coverage_start = dt.date.fromisoformat(str(calendar.get("from")))
        coverage_end = dt.date.fromisoformat(str(calendar.get("to")))
    except (TypeError, ValueError):
        return "pending"
    if window is None:
        return "pending"
    start, end = window
    if start < coverage_start or end > coverage_end:
        return "pending"
    blocked = set(calendar.get("blocked_dates") or ())
    current = start
    while current < end:
        if current.isoformat() in blocked:
            return "unavailable"
        current += dt.timedelta(days=1)
    return "available"


def _pricing_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    out = {"move_in": request.get("move_in")}
    if request.get("move_out"):
        out["move_out"] = request["move_out"]
    elif request.get("duration_months") is not None:
        out["duration_months"] = request["duration_months"]
    return out


def _distance_km(first: Mapping[str, Any], second: Mapping[str, Any]) -> Optional[float]:
    try:
        lat1 = math.radians(float(first["lat"]))
        lng1 = math.radians(float(first["lng"]))
        lat2 = math.radians(float(second["lat"]))
        lng2 = math.radians(float(second["lng"]))
    except (KeyError, TypeError, ValueError):
        return None
    dlat, dlng = lat2 - lat1, lng2 - lng1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    distance = 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(value)))
    return distance if math.isfinite(distance) else None


class MonthlyOpsApp:
    """Staff operations kept separate so the web host can apply its own auth."""

    def __init__(self, public: "MonthlyPublicApp") -> None:
        self._public = public

    def health(self) -> Dict[str, Any]:
        try:
            current = self._public._now()
            return build_health(
                self._public._generation(),
                self._public.settings,
                analytics=self._public.analytics_store,
                lead_store=self._public.lead_store,
                now=current,
            )
        except Exception:
            return {
                "ready": False,
                "red_blockers": [
                    {
                        "code": "health_failed",
                        "message_ar": "تعذر فحص جاهزية الخدمة.",
                        "message_en": "Service health could not be checked.",
                    }
                ],
            }

    def funnel(self) -> Dict[str, Any]:
        try:
            _current, generation = self._public._request_context()
            summary = funnel_summary(self._public.analytics_store, self._public.lead_store)
            registry = self._public._place_registry(generation)
            places = []
            for row in summary.get("requested_places") or ():
                value = {
                    "place_id": row.get("place_id"),
                    "count": row.get("count"),
                }
                registered = registry.get(row.get("place_id"))
                if isinstance(registered, Mapping):
                    value["label_ar"] = registered.get("label_ar")
                    value["label_en"] = registered.get("label_en")
                places.append(value)
            summary["requested_places"] = places
            return summary
        except Exception:
            return {
                "ok": False,
                "error": {
                    "code": "funnel_unavailable",
                    "message_ar": "تعذر تحميل مسار الطلبات.",
                    "message_en": "The lead funnel is unavailable.",
                },
            }

    @staticmethod
    def _reference(value: Any, *, allowed: set[str]) -> Optional[str]:
        if not isinstance(value, Mapping) or set(value) != allowed:
            return None
        reference = str(value.get("lead_reference") or "").strip().upper()
        return reference if _LEAD_REFERENCE_RE.fullmatch(reference) else None

    @staticmethod
    def _safe_request(lead: Mapping[str, Any]) -> Dict[str, Any]:
        request = lead.get("request")
        if not isinstance(request, Mapping):
            return {}
        out = {}
        for field in (
            "move_in", "move_out", "duration_months", "duration_days",
            "residents", "purpose",
        ):
            if field in request:
                out[field] = request[field]
        place = request.get("place")
        if isinstance(place, Mapping) and isinstance(place.get("id"), str):
            out["place_id"] = place["id"]
        return out

    @staticmethod
    def _safe_state(lead: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "reference": lead.get("reference"),
            "responded_at": lead.get("responded_at"),
            "discount_requested": lead.get("discount_requested"),
            "outcome": lead.get("outcome"),
            "outcome_at": lead.get("outcome_at"),
            "lost_reason": lead.get("lost_reason"),
        }

    def lead(self, value: Any) -> Dict[str, Any]:
        reference = self._reference(value, allowed={"lead_reference"})
        if reference is None:
            return _error(
                "invalid_request",
                "مرجع الطلب أو صيغة البحث غير صحيحة.",
                "The lead reference or lookup request is invalid.",
                field="lead_reference",
            )
        try:
            _current, generation = self._public._request_context()
            lead = self._public.lead_store.get(reference)
            if lead is None:
                return _error(
                    "lead_not_found",
                    "مرجع الطلب غير موجود.",
                    "The lead reference was not found.",
                    field="lead_reference",
                )
            listing_id = lead.get("listing_id") or None
            result = (
                self._public._find({"listing_id": listing_id}, generation)
                if listing_id is not None
                else None
            )
            title = None
            if result is not None:
                title = {
                    "ar": result.listing.get("name_ar"),
                    "en": result.listing.get("name_en"),
                }
            try:
                journey = self._public.analytics_store.lead_journey(
                    lead["session_id"], reference
                )
            except Exception:
                journey = []
            registry = self._public._place_registry(generation)
            safe_request = self._safe_request(lead)
            request_place_id = safe_request.get("place_id")
            request_place = registry.get(request_place_id)
            if isinstance(request_place, Mapping):
                safe_request["place"] = {
                    "id": request_place_id,
                    "label_ar": request_place.get("label_ar"),
                    "label_en": request_place.get("label_en"),
                }
            safe_journey = []
            for raw_item in journey:
                item = dict(raw_item)
                place_id = item.get("place_id")
                registered = registry.get(place_id)
                if isinstance(registered, Mapping):
                    item["place"] = {
                        "id": place_id,
                        "label_ar": registered.get("label_ar"),
                        "label_en": registered.get("label_en"),
                    }
                safe_journey.append(item)
            return {
                "ok": True,
                "lead": {
                    "reference": reference,
                    "listing_id": listing_id,
                    "title": title,
                    "request": safe_request,
                    "quote": dict(lead.get("quote") or {}),
                    "created_at": lead.get("created_at"),
                    "responded_at": lead.get("responded_at"),
                    "discount_requested": lead.get("discount_requested"),
                    "outcome": lead.get("outcome"),
                    "outcome_at": lead.get("outcome_at"),
                    "lost_reason": lead.get("lost_reason"),
                    "actions": [
                        {
                            "action": row.get("action"),
                            "reason": row.get("reason"),
                            "alternative_listing_id": row.get("alternative_listing_id"),
                            "quote": dict(row.get("quote") or {}),
                            "created_at": row.get("created_at"),
                        }
                        for row in self._public.lead_store.actions_for(reference)
                    ],
                    "journey": safe_journey,
                },
            }
        except Exception:
            return _internal_error()

    @staticmethod
    def _localized_amount(value: Any, language: str) -> str:
        try:
            formatted = format(float(value), ",.0f")
        except (TypeError, ValueError):
            return "—"
        if language == "ar":
            return formatted.translate(str.maketrans("0123456789,", "٠١٢٣٤٥٦٧٨٩٬"))
        return formatted

    def _prepared_alternative(
        self,
        reference: str,
        result: Any,
        reason: str,
        quote: Mapping[str, Any],
    ) -> Dict[str, Any]:
        reason_labels = {
            "lower_price": ("سعر أقل", "lower price"),
            "dates": ("التواريخ", "dates"),
            "location": ("الموقع", "location"),
            "space": ("المساحة", "space"),
            "contract_terms": ("شروط العقد", "contract terms"),
        }
        title_ar = result.listing["name_ar"]
        title_en = result.listing["name_en"]
        listing_id = result.listing["id"]
        reason_ar, reason_en = reason_labels[reason]
        monthly_ar = self._localized_amount(quote["monthly_rate_sar"], "ar")
        total_ar = self._localized_amount(quote["stay_total_sar"], "ar")
        monthly_en = self._localized_amount(quote["monthly_rate_sar"], "en")
        total_en = self._localized_amount(quote["stay_total_sar"], "en")
        return {
            "listing_id": listing_id,
            "title": {"ar": title_ar, "en": title_en},
            "reason": reason,
            "quote": dict(quote),
            "message_ar": (
                "بديل مجهز للطلب %s: %s (الوحدة %s). السعر الرسمي %s ر.س شهريًا، "
                "والإجمالي %s ر.س للتواريخ المحفوظة. سبب التجهيز: %s. يلزم تأكيد "
                "اختيار العميل قبل أي التزام."
            ) % (reference, title_ar, listing_id, monthly_ar, total_ar, reason_ar),
            "message_en": (
                "Prepared alternative for %s: %s (listing %s). The official monthly "
                "rate is SAR %s and the saved-date total is SAR %s. Preparation reason: "
                "%s. Confirm the customer's choice before any commitment."
            ) % (reference, title_en, listing_id, monthly_en, total_en, reason_en),
        }

    def action(self, value: Any) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            return _error("invalid_request", "صيغة الإجراء غير صحيحة.", "The staff action is invalid.")
        allowed = {"lead_reference", "action", "reason", "alternative_listing_id"}
        if not set(value).issubset(allowed) or set(value).difference(allowed):
            return _error("invalid_request", "صيغة الإجراء غير صحيحة.", "The staff action is invalid.")
        reference = str(value.get("lead_reference") or "").strip().upper()
        action = value.get("action")
        if not _LEAD_REFERENCE_RE.fullmatch(reference) or action not in STAFF_ACTIONS:
            return _error("invalid_request", "صيغة الإجراء غير صحيحة.", "The staff action is invalid.")
        expected = {
            "confirm_request": {"lead_reference", "action"},
            "request_information": {"lead_reference", "action", "reason"},
            "prepare_alternative": {"lead_reference", "action", "reason", "alternative_listing_id"},
        }[action]
        if set(value) != expected:
            return _error("invalid_request", "حقول الإجراء غير مكتملة أو غير معتمدة.", "The staff action fields are incomplete or unsupported.")
        reason = value.get("reason")
        if action == "request_information" and reason not in INFORMATION_REASONS:
            return _error("invalid_request", "سبب طلب المعلومات غير معتمد.", "The information reason is unsupported.", field="reason")
        if action == "prepare_alternative" and reason not in ALTERNATIVE_REASONS:
            return _error("invalid_request", "سبب تجهيز البديل غير معتمد.", "The alternative reason is unsupported.", field="reason")
        try:
            current, generation = self._public._request_context()
            lead = self._public.lead_store.get(reference)
            if lead is None:
                return _error("lead_not_found", "مرجع الطلب غير موجود.", "The lead reference was not found.", field="lead_reference")
            prepared = None
            values: Dict[str, Any] = {"reason": reason, "now": current}
            if action == "confirm_request":
                values = {"now": current}
            elif action == "prepare_alternative":
                listing_id = str(value.get("alternative_listing_id") or "").strip()
                if listing_id == (lead.get("listing_id") or None):
                    return _error("alternative_same_listing", "اختر بيتًا مختلفًا كبديل.", "Choose a different home as the alternative.", field="alternative_listing_id")
                result = self._public._find({"listing_id": listing_id}, generation)
                if result is None:
                    return _error("alternative_not_published", "البيت البديل غير منشور حاليًا.", "The alternative home is not currently published.", field="alternative_listing_id")
                request = lead.get("request")
                if not isinstance(request, Mapping) or not all(
                    key in request for key in ("residents", "sleeping", "move_in")
                ) or not any(key in request for key in ("duration_months", "move_out")):
                    return _error("lead_request_incomplete", "بيانات الطلب المحفوظة غير مكتملة لتجهيز بديل.", "The saved request is incomplete for preparing an alternative.")
                if not space_matches(result.listing, request):
                    return _error("alternative_space_mismatch", "البيت البديل لا يطابق السعة أو ترتيب النوم.", "The alternative home does not match capacity or sleeping needs.", field="alternative_listing_id")
                availability = _availability(result, request)
                if availability == "pending":
                    return _error("alternative_availability_pending", "توفر البيت البديل غير مؤكد حاليًا.", "The alternative home's availability is pending.", field="alternative_listing_id")
                if availability != "available":
                    return _error("alternative_unavailable", "البيت البديل غير متاح للتواريخ المحفوظة.", "The alternative home is unavailable for the saved dates.", field="alternative_listing_id")
                quote = quote_for(result.listing, _pricing_request(request), current)
                if quote is None:
                    return _error("alternative_price_missing", "السعر الرسمي للبديل غير متاح للتواريخ المحفوظة.", "The alternative's official price is unavailable for the saved dates.", field="alternative_listing_id")
                if reason == "lower_price":
                    original_rate = (lead.get("quote") or {}).get("monthly_rate_sar")
                    if (
                        isinstance(original_rate, bool)
                        or not isinstance(original_rate, (int, float))
                        or quote["monthly_rate_sar"] >= original_rate
                    ):
                        return _error(
                            "alternative_not_lower_price",
                            "السعر الرسمي للبديل ليس أقل من السعر المحفوظ للطلب.",
                            "The alternative's official rate is not lower than the saved lead rate.",
                            field="alternative_listing_id",
                        )
                prepared = self._prepared_alternative(reference, result, reason, quote)
                values.update({
                    "alternative_listing_id": listing_id,
                    "quote": quote,
                })
            stored = self._public.lead_store.add_action(reference, action, **values)
            recorded = self._record_lifecycle("team_response", stored["lead"])
            response = {
                "ok": True,
                "action": {
                    "action": stored["action"].get("action"),
                    "reason": stored["action"].get("reason"),
                    "alternative_listing_id": stored["action"].get("alternative_listing_id"),
                    "quote": dict(stored["action"].get("quote") or {}),
                    "created_at": stored["action"].get("created_at"),
                },
                "lead": self._safe_state(stored["lead"]),
                "analytics_recorded": recorded,
            }
            if prepared is not None:
                response["prepared_alternative"] = prepared
            return response
        except KeyError:
            return _error("lead_not_found", "مرجع الطلب غير موجود.", "The lead reference was not found.", field="lead_reference")
        except Exception:
            return _internal_error()

    def response(self, value: Any) -> Dict[str, Any]:
        if (
            not isinstance(value, Mapping)
            or "lead_reference" not in value
            or not set(value).issubset({"lead_reference", "discount_requested"})
            or (
                "discount_requested" in value
                and not isinstance(value["discount_requested"], bool)
            )
        ):
            return _error("invalid_request", "طلب تحديث الرد غير صحيح.", "The response update is invalid.")
        reference = str(value.get("lead_reference") or "").strip().upper()
        if not _LEAD_REFERENCE_RE.fullmatch(reference):
            return _error(
                "invalid_reference",
                "مرجع الطلب غير صحيح.",
                "The lead reference is invalid.",
                field="lead_reference",
            )
        try:
            lead = self._public.lead_store.mark_response(
                reference,
                discount_requested=value.get("discount_requested"),
                now=self._public._now(),
            )
        except KeyError:
            return _error(
                "lead_not_found",
                "مرجع الطلب غير موجود.",
                "The lead reference was not found.",
                field="lead_reference",
            )
        except Exception:
            return _internal_error()
        recorded = self._record_lifecycle("team_response", lead)
        return {"ok": True, "lead": self._safe_state(lead), "analytics_recorded": recorded}

    def outcome(self, value: Any) -> Dict[str, Any]:
        try:
            parsed = parse_outcome(value)
            lead = self._public.lead_store.set_outcome(parsed, now=self._public._now())
        except ContractError as error:
            return _contract_error(error)
        except KeyError:
            return _error(
                "lead_not_found",
                "مرجع الطلب غير موجود.",
                "The lead reference was not found.",
                field="lead_reference",
            )
        except Exception:
            return _internal_error()
        recorded = self._record_lifecycle(parsed["outcome"], lead, parsed)
        return {"ok": True, "lead": self._safe_state(lead), "analytics_recorded": recorded}

    def _record_lifecycle(
        self,
        event: str,
        lead: Mapping[str, Any],
        parsed: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        context = None
        if event == "lost" and parsed is not None:
            context = {"lost_reason": parsed["lost_reason"]}
        try:
            self._public.analytics_store.record_lifecycle(
                event,
                lead["session_id"],
                lead["reference"],
                context=context,
                now=self._public._now(),
            )
            return True
        except Exception:
            return False


class MonthlyPublicApp:
    """Pure request facade over one in-memory last-known-good generation."""

    def __init__(
        self,
        *,
        snapshot_store: Any,
        settings: MonthlySettings,
        lead_store: Any,
        analytics_store: Any,
        approved_places: Any,
        session_secret: Any,
        clock: Any,
    ) -> None:
        if not isinstance(settings, MonthlySettings):
            raise TypeError("settings must be MonthlySettings")
        self.snapshot_store = snapshot_store
        self.settings = settings
        self.lead_store = lead_store
        self.analytics_store = analytics_store
        self.approved_places = self._prepare_places(approved_places)
        self.session_secret = session_secret
        self.clock = clock
        self.ops = MonthlyOpsApp(self)

    @staticmethod
    def _prepare_places(values: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(values, Mapping):
            return {}
        out = {}
        for raw_id, raw in values.items():
            place_id = str(raw_id or "").strip()
            if not place_id or not isinstance(raw, Mapping):
                continue
            kind = raw.get("kind")
            label_ar = str(raw.get("label_ar") or "").strip()
            label_en = str(raw.get("label_en") or "").strip()
            if kind not in ("destination", "neighborhood") or not label_ar or not label_en:
                continue
            out[place_id] = dict(raw, kind=kind, label_ar=label_ar, label_en=label_en)
        return out

    def _now(self) -> dt.datetime:
        value = self.clock()
        if not isinstance(value, dt.datetime):
            raise TypeError("clock must return a datetime")
        return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)

    def _generation(self) -> Any:
        return self.snapshot_store.current

    def _request_context(self) -> tuple[dt.datetime, Any]:
        """Pin one base generation and one clock value for the whole request."""

        current = self._now()
        generation = self._generation()
        if generation is not None:
            generation = revalidate_generation(generation, current)
        return current, generation

    @staticmethod
    def _published(generation: Any) -> tuple[Any, ...]:
        return tuple(generation.published) if generation is not None else ()

    def _place_registry(self, generation: Any) -> Dict[str, Dict[str, Any]]:
        """Merge configured destinations with verified published neighborhoods."""
        registry = {key: dict(value) for key, value in self.approved_places.items()}
        for result in self._published(generation):
            listing = result.listing
            key = listing.get("neighborhood")
            if key and key not in registry:
                registry[key] = {
                    "kind": "neighborhood",
                    "label_ar": listing.get("neighborhood_ar"),
                    "label_en": listing.get("neighborhood_en"),
                }
        return registry

    def _find(self, request: Mapping[str, Any], generation: Any) -> Optional[Any]:
        listing_id = request.get("listing_id")
        slug = request.get("slug")
        for result in self._published(generation):
            if listing_id is not None and result.listing["id"] == listing_id:
                return result
            if slug is not None and result.listing.get("slug") == slug:
                return result
        return None

    def _canonical_place(
        self, place: Any, generation: Any
    ) -> Optional[Dict[str, str]]:
        if not isinstance(place, Mapping):
            return None
        place_id = str(place.get("id") or "")
        registered = self.approved_places.get(place_id)
        if registered is None and place.get("kind") == "neighborhood":
            for result in self._published(generation):
                listing = result.listing
                if listing.get("neighborhood") == place_id:
                    registered = {
                        "kind": "neighborhood",
                        "label_ar": listing.get("neighborhood_ar"),
                        "label_en": listing.get("neighborhood_en"),
                    }
                    break
        if not registered or registered.get("kind") != place.get("kind"):
            raise ContractError(
                "place.id",
                "not_allowed",
                "المكان غير موجود ضمن الخيارات المعتمدة.",
                "The place is not in the approved options.",
            )
        return {
            "kind": registered["kind"],
            "id": place_id,
            "label": registered["label_ar"],
        }

    def _canonical_request(
        self, request: Dict[str, Any], generation: Any
    ) -> Dict[str, Any]:
        result = dict(request)
        if "place" in result:
            result["place"] = self._canonical_place(result["place"], generation)
        return result

    def config(self, lang: Any = "ar") -> Dict[str, Any]:
        try:
            language = _language(lang)
            current, generation = self._request_context()
        except ContractError as error:
            return _contract_error(error)
        except Exception:
            return _internal_error()
        blockers = [item.as_dict() for item in self.settings.blockers]
        if generation is None:
            blockers.append(
                {
                    "field": "snapshot",
                    "code": "snapshot_missing",
                    "message_ar": "لا توجد لقطة نشر صالحة.",
                    "message_en": "No valid publication snapshot is available.",
                }
            )
        try:
            session_id = issue_anonymous_session(self.session_secret)
        except (TypeError, ValueError):
            session_id = None
            blockers.append(
                {
                    "field": "session_secret",
                    "code": "session_secret_missing",
                    "message_ar": "تسجيل الجلسة الآمن غير مهيأ.",
                    "message_en": "Secure anonymous sessions are not configured.",
                }
            )
        places = [
            {
                "id": place_id,
                "kind": row["kind"],
                "label_ar": row["label_ar"],
                "label_en": row["label_en"],
            }
            for place_id, row in sorted(self.approved_places.items())
        ]
        seen = {row["id"] for row in places if row["kind"] == "neighborhood"}
        neighborhoods = []
        for result in self._published(generation):
            listing = result.listing
            key = listing.get("neighborhood")
            if not key or key in seen:
                continue
            seen.add(key)
            neighborhoods.append(
                {
                    "id": key,
                    "kind": "neighborhood",
                    "label_ar": listing["neighborhood_ar"],
                    "label_en": listing["neighborhood_en"],
                }
            )
        return {
            "ok": True,
            "default_lang": "ar",
            "lang": language,
            "session_id": session_id,
            "eligible_count": len(self._published(generation)),
            "places": places,
            "neighborhoods": neighborhoods,
            "response_window": response_window(self.settings, current),
            "long_stay_route": self.settings.long_stay_route,
            "blockers": blockers,
        }

    def browse(self, value: Any) -> Dict[str, Any]:
        try:
            current, generation = self._request_context()
            request = self._canonical_request(parse_browse_query(value), generation)
            language = _language(request.get("lang"))
            has_dates = _window(request) is not None
            if request.get("move_in") and not has_dates:
                raise ContractError(
                    "duration_months",
                    "required",
                    "حدد مدة الإقامة أو تاريخ الخروج.",
                    "Choose a stay duration or move-out date.",
                )
            results = []
            pending = unavailable = missing_price = 0
            for result in self._published(generation):
                listing = result.listing
                if request.get("residents") is not None and listing.get("capacity", -1) < request["residents"]:
                    continue
                if request.get("bedrooms") is not None and listing.get("bedrooms") != request["bedrooms"]:
                    continue
                if request.get("neighborhood") and listing.get("neighborhood") != request["neighborhood"]:
                    continue
                if not self._browse_place_matches(listing, request.get("place")):
                    continue
                card = present_card(result, language)
                if not has_dates:
                    results.append(card)
                    continue
                availability = _availability(result, request)
                if availability == "pending":
                    pending += 1
                    continue
                if availability == "unavailable":
                    unavailable += 1
                    continue
                quote = quote_for(listing, _pricing_request(request), current)
                if quote is None:
                    missing_price += 1
                    continue
                card["availability_status"] = "available"
                card["quote"] = quote
                results.append(card)
            return {
                "ok": True,
                "browse": not has_dates,
                "results": results,
                "counts": {
                    "results": len(results),
                    "pending": pending,
                    "unavailable": unavailable,
                    "missing_price": missing_price,
                },
            }
        except ContractError as error:
            return _contract_error(error)
        except Exception:
            return _internal_error()

    def _browse_place_matches(self, listing: Mapping[str, Any], place: Any) -> bool:
        if not isinstance(place, Mapping):
            return True
        if place["kind"] == "neighborhood":
            return listing.get("neighborhood") == place["id"]
        destination = self.approved_places.get(place["id"])
        coordinates = listing.get("coordinates")
        if not destination or destination.get("verified") is not True or not destination.get("source"):
            return False
        if not isinstance(coordinates, Mapping) or coordinates.get("verified") is not True or not coordinates.get("source"):
            return False
        distance = _distance_km(coordinates, destination)
        return distance is not None and distance <= 20

    def search(self, value: Any) -> Dict[str, Any]:
        """Stable route-facing name for catalog browse/search."""
        return self.browse(value)

    def match(self, value: Any, lang: Any = "ar") -> Dict[str, Any]:
        try:
            current, generation = self._request_context()
            if generation is None:
                return _error(
                    "snapshot_missing",
                    "لا توجد خيارات منشورة حاليًا.",
                    "No published homes are currently available.",
                )
            request = self._canonical_request(parse_match_request(value), generation)
            language = _language(lang)
            result = rank(
                generation,
                request,
                language,
                now=current,
                places=self._place_registry(generation),
            )
            return {"ok": True, **result}
        except ContractError as error:
            return _contract_error(error)
        except Exception:
            return _internal_error()

    def listing(self, value: Any) -> Dict[str, Any]:
        try:
            current, generation = self._request_context()
            request = self._canonical_request(parse_listing_request(value), generation)
            language = _language(request.get("lang"))
            result = self._find(request, generation)
            if result is None:
                return _error(
                    "listing_not_found",
                    "الشقة غير موجودة ضمن الخيارات المنشورة.",
                    "The listing is not in the published catalog.",
                    field="listing_id",
                )
            detail = present_listing(result, language)
            quote = None
            status = "not_requested"
            if request.get("move_in"):
                if _window(request) is None:
                    raise ContractError(
                        "duration_months",
                        "required",
                        "حدد مدة الإقامة أو تاريخ الخروج.",
                        "Choose a stay duration or move-out date.",
                    )
                availability = _availability(result, request)
                status = availability
                if availability == "available":
                    quote = quote_for(result.listing, _pricing_request(request), current)
                    if quote is None:
                        status = "price_missing"
            return {"ok": True, "listing": detail, "quote": quote, "quote_status": status}
        except ContractError as error:
            return _contract_error(error)
        except Exception:
            return _internal_error()

    def quote(self, value: Any) -> Dict[str, Any]:
        result = self.listing(value)
        if not result.get("ok"):
            return result
        if result["quote_status"] == "not_requested":
            return _error(
                "dates_required",
                "حدد تواريخ الإقامة لعرض السعر.",
                "Select stay dates to view a quote.",
                field="move_in",
            )
        return {"ok": True, "quote": result["quote"], "quote_status": result["quote_status"]}

    def lead(self, value: Any) -> Dict[str, Any]:
        try:
            current, generation = self._request_context()
            if not isinstance(value, Mapping):
                raise ContractError(
                    "request",
                    "invalid_type",
                    "صيغة الطلب غير صحيحة.",
                    "The request format is invalid.",
                )
            unknown = sorted(set(value) - {"session_id", "listing_id", "general_help", "request", "lang"})
            if unknown:
                raise ContractError(
                    unknown[0],
                    "unknown_field",
                    "يحتوي الطلب على حقل غير معتمد.",
                    "The request contains an unsupported field.",
                )
            language = _language(value.get("lang"))
            session_id = parse_event(
                {"event": "whatsapp_click", "session_id": value.get("session_id")},
                session_secret=self.session_secret,
                allowed_place_ids=self._place_registry(generation),
            )["session_id"]
            request = self._canonical_request(
                parse_match_request(value.get("request")), generation
            )
            request["lang"] = language
            if value.get("general_help") is True:
                if value.get("listing_id") not in (None, ""):
                    return _error(
                        "general_help_listing_not_allowed",
                        "طلب المساعدة العام لا يقبل اختيار بيت.",
                        "A general-help request cannot include a selected home.",
                        field="listing_id",
                    )
                if generation is None:
                    return _error(
                        "snapshot_missing",
                        "لا توجد لقطة نشر صالحة لتأكيد عدم وجود خيار.",
                        "No valid publication snapshot can verify that no option exists.",
                    )
                match_request = dict(request)
                match_request.pop("lang", None)
                ranked = rank(
                    generation,
                    match_request,
                    language,
                    now=current,
                    places=self._place_registry(generation),
                )
                if ranked.get("pending_count"):
                    return _error(
                        "availability_pending",
                        "التوفر قيد التأكيد. لا يمكن إنشاء طلب عام قبل اكتمال التحقق.",
                        "Availability is pending. A general request cannot be created before verification completes.",
                    )
                if ranked.get("top") or ranked.get("near_matches"):
                    return _error(
                        "general_help_not_allowed",
                        "يوجد خيار موثّق يمكن اختياره لهذا الطلب.",
                        "A verified home can be selected for this request.",
                    )
                handoff = build_general_whatsapp_handoff(
                    self.lead_store,
                    self.settings,
                    session_id,
                    request,
                    analytics=self.analytics_store,
                    approved_places=self._place_registry(generation),
                    now=current,
                )
                if handoff.get("ok") is False:
                    blocked = _error(
                        str(handoff.get("code") or "handoff_blocked"),
                        str(handoff.get("message_ar") or "تعذر تجهيز طلب واتساب بشكل آمن."),
                        str(handoff.get("message_en") or "The WhatsApp handoff could not be prepared safely."),
                    )
                    if handoff.get("response_window") is not None:
                        blocked["response_window"] = handoff["response_window"]
                    return blocked
                return handoff
            if value.get("general_help") not in (None, False):
                raise ContractError(
                    "general_help",
                    "invalid_type",
                    "نوع طلب المساعدة غير صحيح.",
                    "The general-help flag is invalid.",
                )
            parsed_listing = parse_listing_request({"listing_id": value.get("listing_id")})
            result = self._find(parsed_listing, generation)
            if result is None:
                return _error(
                    "listing_not_found",
                    "الشقة غير موجودة ضمن الخيارات المنشورة.",
                    "The listing is not in the published catalog.",
                    field="listing_id",
                )
            if not space_matches(result.listing, request):
                return _error(
                    "listing_request_mismatch",
                    "الشقة المحددة لا تطابق السعة أو ترتيب النوم المطلوب.",
                    "The selected listing does not match the requested capacity or sleeping setup.",
                    field="listing_id",
                )
            availability = _availability(result, request)
            if availability != "available":
                return _error(
                    "availability_%s" % availability,
                    "التوفر غير مؤكد للتواريخ المحددة.",
                    "Availability is not confirmed for the selected dates.",
                )
            quote = quote_for(result.listing, _pricing_request(request), current)
            if quote is None:
                return _error(
                    "price_missing",
                    "السعر الرسمي غير متاح للتواريخ المحددة.",
                    "The official price is unavailable for the selected dates.",
                )
            handoff = build_whatsapp_handoff(
                self.lead_store,
                self.settings,
                session_id,
                result.listing,
                request,
                quote,
                analytics=self.analytics_store,
                approved_places=self._place_registry(generation),
                now=current,
            )
            if handoff.get("ok") is False:
                blocked = _error(
                    str(handoff.get("code") or "handoff_blocked"),
                    str(handoff.get("message_ar") or "تعذر تجهيز طلب واتساب بشكل آمن."),
                    str(handoff.get("message_en") or "The WhatsApp handoff could not be prepared safely."),
                )
                if handoff.get("response_window") is not None:
                    blocked["response_window"] = handoff["response_window"]
                return blocked
            return handoff
        except ContractError as error:
            return _contract_error(error)
        except HandoffValidationError:
            return _error(
                "handoff_blocked",
                "تعذر تجهيز طلب واتساب بشكل آمن.",
                "The WhatsApp handoff could not be prepared safely.",
            )
        except Exception:
            return _internal_error()

    def event(self, value: Any) -> Dict[str, Any]:
        try:
            current, generation = self._request_context()
            places = self._place_registry(generation)
            event = parse_event(
                value,
                session_secret=self.session_secret,
                allowed_place_ids=places,
            )
        except ContractError as error:
            return _contract_error(error)
        except Exception:
            return _internal_error()
        try:
            recorded = self.analytics_store.record(
                event,
                session_secret=self.session_secret,
                allowed_place_ids=places,
                now=current,
            )
            return {"ok": True, "event": recorded, "analytics_recorded": True}
        except Exception:
            return {"ok": True, "event": event, "analytics_recorded": False}
