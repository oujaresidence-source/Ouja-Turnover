"""Stable, privacy-minimising contracts for the public monthly product."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, Mapping, Optional


PURPOSES = ("work", "family", "treatment", "visit")
FLEXIBILITY_OPTIONS = ("fixed", "plus_minus_7")
SLEEPING_OPTIONS = (
    "studio",
    "one_bedroom",
    "two_bedrooms",
    "three_bedrooms",
    "four_plus_bedrooms",
    "separate_beds",
    "flexible",
)
PLACE_KINDS = ("destination", "neighborhood")
LANGUAGES = ("ar", "en")
ENTRY_ROUTES = ("guided", "browse")
DEVICE_CLASSES = ("mobile", "tablet", "desktop", "unknown")
EVENT_NAMES = (
    "landing_view",
    "entry_route_choice",
    "matcher_start",
    "matcher_answer",
    "matcher_completion",
    "results_view",
    "result_impression",
    "listing_view",
    "whatsapp_click",
    "lead_created",
    "team_response",
)
LOST_REASONS = (
    "price",
    "unavailable_dates",
    "location",
    "space",
    "contract_terms",
    "no_response",
    "booked_elsewhere",
    "other",
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_LEAD_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{5,63}$")


class ContractError(ValueError):
    """One customer-safe validation error, in both supported languages."""

    def __init__(
        self,
        field: str,
        code: str,
        message_ar: str,
        message_en: str,
    ) -> None:
        super().__init__(message_en)
        self.field = field
        self.code = code
        self.message_ar = message_ar
        self.message_en = message_en

    def as_dict(self) -> Dict[str, str]:
        return {
            "field": self.field,
            "code": self.code,
            "message_ar": self.message_ar,
            "message_en": self.message_en,
        }


def _error(
    field: str,
    code: str,
    message_ar: str,
    message_en: str,
) -> ContractError:
    return ContractError(field, code, message_ar, message_en)


def _mapping(value: Any, field: str = "request") -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(
            field,
            "invalid_type",
            "صيغة الطلب غير صحيحة.",
            "The request format is invalid.",
        )
    return value


def _reject_unknown(
    data: Mapping[str, Any], allowed: set[str], prefix: str = ""
) -> None:
    unknown = sorted(str(key) for key in data if key not in allowed)
    if not unknown:
        return
    field = "%s%s" % (prefix, unknown[0])
    raise _error(
        field,
        "unknown_field",
        "يحتوي الطلب على حقل غير معتمد.",
        "The request contains an unsupported field.",
    )


def _required_text(
    value: Any,
    field: str,
    *,
    max_length: int = 160,
    safe_id: bool = False,
) -> str:
    if value is None or not isinstance(value, (str, int)):
        raise _error(field, "required", "هذا الحقل مطلوب.", "This field is required.")
    text = str(value).strip()
    if not text:
        raise _error(field, "required", "هذا الحقل مطلوب.", "This field is required.")
    if len(text) > max_length or (safe_id and not _SAFE_ID_RE.fullmatch(text)):
        raise _error(
            field,
            "invalid_format",
            "قيمة الحقل غير صحيحة.",
            "This field has an invalid format.",
        )
    return text


def _choice(value: Any, field: str, choices: tuple[str, ...]) -> str:
    text = _required_text(value, field, max_length=40)
    if text not in choices:
        raise _error(
            field,
            "unsupported",
            "الخيار المحدد غير معتمد.",
            "The selected option is unsupported.",
        )
    return text


def _integer(
    value: Any,
    field: str,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    if isinstance(value, bool):
        parsed = None
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        parsed = int(value.strip())
    else:
        parsed = None
    if parsed is None:
        raise _error(
            field,
            "invalid_type",
            "أدخل رقمًا صحيحًا.",
            "Enter a whole number.",
        )
    if (minimum is not None and parsed < minimum) or (
        maximum is not None and parsed > maximum
    ):
        raise _error(
            field,
            "out_of_range",
            "القيمة خارج النطاق المعتمد.",
            "The value is outside the supported range.",
        )
    return parsed


def _date(value: Any, field: str) -> str:
    text = _required_text(value, field, max_length=10)
    if not _DATE_RE.fullmatch(text):
        raise _error(
            field,
            "invalid_date",
            "أدخل تاريخًا صحيحًا.",
            "Enter a valid date.",
        )
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        raise _error(
            field,
            "invalid_date",
            "أدخل تاريخًا صحيحًا.",
            "Enter a valid date.",
        )
    return text


def _place(value: Any, field: str = "place") -> Dict[str, str]:
    place = _mapping(value, field)
    _reject_unknown(place, {"kind", "id", "label"}, "%s." % field)
    return {
        "kind": _choice(place.get("kind"), "%s.kind" % field, PLACE_KINDS),
        "id": _required_text(
            place.get("id"), "%s.id" % field, max_length=80, safe_id=True
        ),
        "label": _required_text(
            place.get("label"), "%s.label" % field, max_length=120
        ),
    }


def _date_selection(data: Mapping[str, Any], *, required: bool) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    move_in_value = data.get("move_in")
    duration_value = data.get("duration_months")
    move_out_value = data.get("move_out")

    if required and move_in_value in (None, ""):
        raise _error("move_in", "required", "تاريخ الدخول مطلوب.", "Move-in date is required.")
    if move_in_value not in (None, ""):
        result["move_in"] = _date(move_in_value, "move_in")

    if required and duration_value in (None, "") and move_out_value in (None, ""):
        raise _error(
            "duration_months",
            "required",
            "حدد مدة الإقامة أو تاريخ الخروج.",
            "Choose a stay duration or move-out date.",
        )
    if duration_value not in (None, ""):
        result["duration_months"] = _integer(
            duration_value, "duration_months", minimum=1, maximum=6
        )
    if move_out_value not in (None, ""):
        result["move_out"] = _date(move_out_value, "move_out")
        if "move_in" not in result:
            raise _error(
                "move_in",
                "required",
                "تاريخ الدخول مطلوب عند تحديد تاريخ الخروج.",
                "Move-in date is required when move-out is provided.",
            )
        if result["move_out"] <= result["move_in"]:
            raise _error(
                "move_out",
                "invalid_range",
                "تاريخ الخروج يجب أن يكون بعد تاريخ الدخول.",
                "Move-out date must be after move-in date.",
            )
    return result


def parse_match_request(value: Any) -> Dict[str, Any]:
    """Validate and normalise the adaptive matcher's complete answer set."""

    data = _mapping(value)
    _reject_unknown(
        data,
        {
            "purpose",
            "place",
            "residents",
            "sleeping",
            "move_in",
            "move_out",
            "duration_months",
            "flexibility",
        },
    )
    purpose = _choice(data.get("purpose"), "purpose", PURPOSES)
    result: Dict[str, Any] = {
        "purpose": purpose,
        "residents": _integer(data.get("residents"), "residents", minimum=1),
        "sleeping": _choice(data.get("sleeping"), "sleeping", SLEEPING_OPTIONS),
        "flexibility": _choice(
            data.get("flexibility"), "flexibility", FLEXIBILITY_OPTIONS
        ),
    }
    if data.get("place") is not None:
        result["place"] = _place(data["place"])
    elif purpose in ("work", "treatment", "visit"):
        raise _error(
            "place",
            "required",
            "حدد المكان المهم لإقامتك.",
            "Choose the important place for your stay.",
        )
    result.update(_date_selection(data, required=True))
    return result


def parse_browse_query(value: Any) -> Dict[str, Any]:
    """Validate optional full-catalog filters without accepting sort overrides."""

    data = _mapping(value, "query")
    _reject_unknown(
        data,
        {
            "move_in",
            "move_out",
            "duration_months",
            "bedrooms",
            "residents",
            "neighborhood",
            "place",
            "flexibility",
            "lang",
        },
    )
    result = _date_selection(data, required=False)
    if data.get("bedrooms") not in (None, ""):
        result["bedrooms"] = _integer(data["bedrooms"], "bedrooms", minimum=0)
    if data.get("residents") not in (None, ""):
        result["residents"] = _integer(data["residents"], "residents", minimum=1)
    if data.get("neighborhood") not in (None, ""):
        result["neighborhood"] = _required_text(
            data["neighborhood"], "neighborhood", max_length=120
        )
    if data.get("place") is not None:
        result["place"] = _place(data["place"])
    if data.get("flexibility") not in (None, ""):
        result["flexibility"] = _choice(
            data["flexibility"], "flexibility", FLEXIBILITY_OPTIONS
        )
    if data.get("lang") not in (None, ""):
        result["lang"] = _choice(data["lang"], "lang", LANGUAGES)
    return result


def parse_listing_request(value: Any) -> Dict[str, Any]:
    """Validate listing detail/quote context supplied to a public route."""

    data = _mapping(value)
    _reject_unknown(
        data,
        {
            "listing_id",
            "slug",
            "move_in",
            "move_out",
            "duration_months",
            "residents",
            "purpose",
            "place",
            "lang",
            "session_id",
        },
    )
    result: Dict[str, Any] = {}
    if data.get("listing_id") not in (None, ""):
        result["listing_id"] = _required_text(
            data["listing_id"], "listing_id", max_length=80, safe_id=True
        )
    elif data.get("slug") not in (None, ""):
        result["slug"] = _required_text(
            data["slug"], "slug", max_length=128, safe_id=True
        )
    else:
        raise _error(
            "listing_id",
            "required",
            "معرّف الشقة مطلوب.",
            "Listing ID is required.",
        )
    result.update(_date_selection(data, required=False))
    if data.get("residents") not in (None, ""):
        result["residents"] = _integer(data["residents"], "residents", minimum=1)
    if data.get("purpose") not in (None, ""):
        result["purpose"] = _choice(data["purpose"], "purpose", PURPOSES)
    if data.get("place") is not None:
        result["place"] = _place(data["place"])
    if data.get("lang") not in (None, ""):
        result["lang"] = _choice(data["lang"], "lang", LANGUAGES)
    if data.get("session_id") not in (None, ""):
        result["session_id"] = _required_text(
            data["session_id"], "session_id", max_length=128, safe_id=True
        )
    return result


def _event_context(value: Any) -> Dict[str, Any]:
    if value in (None, ""):
        return {}
    data = _mapping(value, "context")
    # Unknown context is dropped rather than stored.  This intentionally removes
    # UTM values, names, phone numbers, message bodies, and arbitrary free text.
    safe: Dict[str, Any] = {}
    if data.get("language") not in (None, ""):
        safe["language"] = _choice(data["language"], "context.language", LANGUAGES)
    if data.get("device_class") not in (None, ""):
        safe["device_class"] = _choice(
            data["device_class"], "context.device_class", DEVICE_CLASSES
        )
    if data.get("listing_id") not in (None, ""):
        safe["listing_id"] = _required_text(
            data["listing_id"], "context.listing_id", max_length=80, safe_id=True
        )
    if data.get("move_in") not in (None, ""):
        safe["move_in"] = _date(data["move_in"], "context.move_in")
    if data.get("duration_band") not in (None, ""):
        safe["duration_band"] = _choice(
            data["duration_band"],
            "context.duration_band",
            ("1_month", "2_3_months", "4_6_months"),
        )
    if data.get("purpose") not in (None, ""):
        safe["purpose"] = _choice(data["purpose"], "context.purpose", PURPOSES)
    if data.get("place_id") not in (None, ""):
        safe["place_id"] = _required_text(
            data["place_id"], "context.place_id", max_length=80, safe_id=True
        )
    if data.get("entry_route") not in (None, ""):
        safe["entry_route"] = _choice(
            data["entry_route"], "context.entry_route", ENTRY_ROUTES
        )
    if data.get("question") not in (None, ""):
        safe["question"] = _required_text(
            data["question"], "context.question", max_length=80, safe_id=True
        )
    if data.get("answer") not in (None, ""):
        safe["answer"] = _required_text(
            data["answer"], "context.answer", max_length=80, safe_id=True
        )
    if data.get("lead_reference") not in (None, ""):
        lead = _required_text(
            data["lead_reference"], "context.lead_reference", max_length=64
        ).upper()
        if not _LEAD_RE.fullmatch(lead):
            raise _error(
                "context.lead_reference",
                "invalid_format",
                "مرجع الطلب غير صحيح.",
                "The lead reference is invalid.",
            )
        safe["lead_reference"] = lead
    if data.get("rank") not in (None, ""):
        safe["rank"] = _integer(data["rank"], "context.rank", minimum=1)
    if data.get("listing_ids") not in (None, ""):
        values = data["listing_ids"]
        if not isinstance(values, (list, tuple)) or len(values) > 100:
            raise _error(
                "context.listing_ids",
                "invalid_type",
                "قائمة الشقق غير صحيحة.",
                "The listing ID collection is invalid.",
            )
        safe["listing_ids"] = [
            _required_text(item, "context.listing_ids", max_length=80, safe_id=True)
            for item in values
        ]
    return safe


def parse_event(value: Any) -> Dict[str, Any]:
    """Validate an anonymous funnel event and discard nonessential context."""

    data = _mapping(value)
    _reject_unknown(data, {"event", "session_id", "context"})
    return {
        "event": _choice(data.get("event"), "event", EVENT_NAMES),
        "session_id": _required_text(
            data.get("session_id"), "session_id", max_length=128, safe_id=True
        ),
        "context": _event_context(data.get("context")),
    }


def parse_outcome(value: Any) -> Dict[str, str]:
    """Validate the controlled booked/lost result recorded by staff."""

    data = _mapping(value)
    _reject_unknown(data, {"lead_reference", "outcome", "lost_reason"})
    lead = _required_text(
        data.get("lead_reference"), "lead_reference", max_length=64
    ).upper()
    if not _LEAD_RE.fullmatch(lead):
        raise _error(
            "lead_reference",
            "invalid_format",
            "مرجع الطلب غير صحيح.",
            "The lead reference is invalid.",
        )
    outcome = _choice(data.get("outcome"), "outcome", ("booked", "lost"))
    result = {"lead_reference": lead, "outcome": outcome}
    reason = data.get("lost_reason")
    if outcome == "lost":
        result["lost_reason"] = _choice(reason, "lost_reason", LOST_REASONS)
    elif reason not in (None, ""):
        raise _error(
            "lost_reason",
            "not_allowed",
            "سبب الخسارة لا يُسجل للطلب المحجوز.",
            "A lost reason cannot be recorded for a booked lead.",
        )
    return result
