"""Stable, privacy-minimising contracts for the public monthly product."""

from __future__ import annotations

import base64
import calendar
import datetime as dt
import hashlib
import hmac
import re
import secrets
from typing import Any, Collection, Dict, Mapping, Optional


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
PUBLIC_EVENT_NAMES = (
    "landing_view",
    "entry_route_choice",
    "matcher_start",
    "matcher_answer",
    "matcher_completion",
    "results_view",
    "result_impression",
    "listing_view",
    "whatsapp_click",
)
TRUSTED_LIFECYCLE_EVENT_NAMES = (
    "lead_created",
    "team_response",
    "booked",
    "lost",
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
MATCHER_QUESTIONS = (
    "purpose",
    "place",
    "residents",
    "sleeping",
    "move_in",
    "move_out",
    "duration_months",
    "flexibility",
)

_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_PLACE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
_LEAD_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{5,63}$")
_JOURNEY_RE = re.compile(r"^journey_[A-Za-z0-9_-]{22,64}$")
_ANON_SESSION_RE = re.compile(
    r"^anon_([A-Za-z0-9_-]{32})\.([A-Za-z0-9_-]{43})$"
)
_SESSION_HMAC_CONTEXT = b"ouja-monthly-anonymous-session:v1:"
MIN_SESSION_SECRET_BYTES = 32

# Abuse ceilings protect request parsing only. They do not describe Ouja's
# inventory; capacity and bedroom facts always come from the published snapshot.
MAX_PUBLIC_RESIDENTS = 50
MAX_PUBLIC_BEDROOMS = 20
MAX_PUBLIC_RESULT_RANK = 1_000
MAX_INTEGER_DIGITS = 9


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
    if value is None:
        raise _error(field, "required", "هذا الحقل مطلوب.", "This field is required.")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise _error(
            field,
            "invalid_type",
            "قيمة الحقل من نوع غير صحيح.",
            "This field has an invalid type.",
        )
    text = str(value).strip()
    if not text:
        raise _error(field, "required", "هذا الحقل مطلوب.", "This field is required.")
    if len(text) > max_length:
        raise _error(
            field,
            "too_long",
            "قيمة الحقل أطول من الحد المسموح.",
            "This field exceeds the allowed length.",
        )
    if safe_id and not _SAFE_ID_RE.fullmatch(text):
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
        if abs(value) > (10 ** MAX_INTEGER_DIGITS - 1):
            raise _error(
                field,
                "too_long",
                "الرقم أطول من الحد المسموح.",
                "The number exceeds the allowed length.",
            )
        parsed = value
    elif isinstance(value, str):
        stripped = value.strip()
        digits = stripped[1:] if stripped.startswith("-") else stripped
        if len(digits) > MAX_INTEGER_DIGITS:
            raise _error(
                field,
                "too_long",
                "الرقم أطول من الحد المسموح.",
                "The number exceeds the allowed length.",
            )
        parsed = int(stripped) if re.fullmatch(r"-?[0-9]+", stripped) else None
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


def _session_secret(value: Any) -> Optional[bytes]:
    if isinstance(value, bytearray):
        value = bytes(value)
    if not isinstance(value, bytes) or len(value) < MIN_SESSION_SECRET_BYTES:
        return None
    return value


def _session_signature(secret: bytes, nonce: str) -> str:
    digest = hmac.new(
        secret,
        _SESSION_HMAC_CONTEXT + nonce.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def issue_anonymous_session(secret: Any) -> str:
    """Issue one process-verifiable anonymous browser session token."""

    secret_bytes = _session_secret(secret)
    if secret_bytes is None:
        raise ValueError("session secret must contain at least 32 bytes")
    nonce = secrets.token_urlsafe(24)
    return "anon_%s.%s" % (nonce, _session_signature(secret_bytes, nonce))


def _anonymous_session(
    value: Any, secret: Any, field: str = "session_id"
) -> str:
    session_id = _required_text(value, field, max_length=128)
    match = _ANON_SESSION_RE.fullmatch(session_id)
    if match is None:
        raise _error(
            field,
            "invalid_format",
            "معرّف الجلسة المجهول غير صحيح.",
            "The anonymous session identifier is invalid.",
        )
    secret_bytes = _session_secret(secret)
    if secret_bytes is None:
        raise _error(
            field,
            "server_configuration",
            "تعذر التحقق من الجلسة بسبب إعداد الخادم.",
            "The session cannot be verified because server configuration is missing.",
        )
    nonce, supplied_signature = match.groups()
    expected_signature = _session_signature(secret_bytes, nonce)
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise _error(
            field,
            "invalid_signature",
            "تعذر التحقق من الجلسة المجهولة.",
            "The anonymous session signature is invalid.",
        )
    return session_id


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


def _add_calendar_months(value: dt.date, months: int) -> dt.date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def _calendar_span(
    move_in: str, move_out: str, field: str
) -> tuple[int, Optional[int]]:
    start = dt.date.fromisoformat(move_in)
    end = dt.date.fromisoformat(move_out)
    if end <= start:
        raise _error(
            field,
            "invalid_range",
            "تاريخ الخروج يجب أن يكون بعد تاريخ الدخول.",
            "Move-out date must be after move-in date.",
        )
    try:
        minimum = _add_calendar_months(start, 1)
        maximum = _add_calendar_months(start, 6)
    except (OverflowError, ValueError):
        raise _error(
            field,
            "unsupported_date",
            "التاريخ خارج النطاق المدعوم.",
            "The date is outside the supported range.",
        )
    if end < minimum or end > maximum:
        raise _error(
            field,
            "out_of_range",
            "مدة الإقامة يجب أن تكون من شهر إلى ستة أشهر.",
            "The stay must be between one and six months.",
        )
    try:
        exact_months = next(
            (
                months
                for months in range(1, 7)
                if _add_calendar_months(start, months) == end
            ),
            None,
        )
    except (OverflowError, ValueError):
        raise _error(
            field,
            "unsupported_date",
            "التاريخ خارج النطاق المدعوم.",
            "The date is outside the supported range.",
        )
    return (end - start).days, exact_months


def _duration_band_from_dates(move_in: str, move_out: str) -> str:
    start = dt.date.fromisoformat(move_in)
    end = dt.date.fromisoformat(move_out)
    if end <= _add_calendar_months(start, 1):
        return "1_month"
    if end <= _add_calendar_months(start, 3):
        return "2_3_months"
    return "4_6_months"


def _duration_band_from_months(months: int) -> str:
    if months == 1:
        return "1_month"
    if months <= 3:
        return "2_3_months"
    return "4_6_months"


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
    if duration_value not in (None, "") and move_out_value not in (None, ""):
        raise _error(
            "move_out",
            "mutually_exclusive",
            "اختر مدة الإقامة أو تاريخ الخروج، وليس الاثنين معًا.",
            "Choose either a stay duration or move-out date, not both.",
        )
    if duration_value not in (None, ""):
        duration_months = _integer(
            duration_value, "duration_months", minimum=1, maximum=6
        )
        if "move_in" in result:
            try:
                _add_calendar_months(
                    dt.date.fromisoformat(result["move_in"]), duration_months
                )
            except (OverflowError, ValueError):
                raise _error(
                    "move_in",
                    "unsupported_date",
                    "التاريخ خارج النطاق المدعوم.",
                    "The date is outside the supported range.",
                )
        result["duration_months"] = duration_months
    if move_out_value not in (None, ""):
        result["move_out"] = _date(move_out_value, "move_out")
        if "move_in" not in result:
            raise _error(
                "move_in",
                "required",
                "تاريخ الدخول مطلوب عند تحديد تاريخ الخروج.",
                "Move-in date is required when move-out is provided.",
            )
        duration_days, exact_months = _calendar_span(
            result["move_in"], result["move_out"], "move_out"
        )
        result["duration_days"] = duration_days
        if exact_months is not None:
            result["duration_months"] = exact_months
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
        "residents": _integer(
            data.get("residents"),
            "residents",
            minimum=1,
            maximum=MAX_PUBLIC_RESIDENTS,
        ),
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
        result["bedrooms"] = _integer(
            data["bedrooms"],
            "bedrooms",
            minimum=0,
            maximum=MAX_PUBLIC_BEDROOMS,
        )
    if data.get("residents") not in (None, ""):
        result["residents"] = _integer(
            data["residents"],
            "residents",
            minimum=1,
            maximum=MAX_PUBLIC_RESIDENTS,
        )
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
        result["residents"] = _integer(
            data["residents"],
            "residents",
            minimum=1,
            maximum=MAX_PUBLIC_RESIDENTS,
        )
    if data.get("purpose") not in (None, ""):
        result["purpose"] = _choice(data["purpose"], "purpose", PURPOSES)
    if data.get("place") is not None:
        result["place"] = _place(data["place"])
    if data.get("lang") not in (None, ""):
        result["lang"] = _choice(data["lang"], "lang", LANGUAGES)
    return result


def _place_allowlist(values: Optional[Collection[str]]) -> frozenset[str]:
    if values is None or isinstance(values, (str, bytes)):
        return frozenset()
    return frozenset(
        value
        for value in values
        if isinstance(value, str) and _PLACE_ID_RE.fullmatch(value)
    )


def _allowlisted_place_id(
    value: Any, field: str, allowed_place_ids: frozenset[str]
) -> str:
    place_id = _required_text(value, field, max_length=80)
    if not _PLACE_ID_RE.fullmatch(place_id) or place_id not in allowed_place_ids:
        raise _error(
            field,
            "not_allowed",
            "المكان غير موجود ضمن الخيارات المعتمدة.",
            "The place is not in the approved options.",
        )
    return place_id


def _event_context(
    value: Any, allowed_place_ids: frozenset[str]
) -> Dict[str, Any]:
    if value in (None, ""):
        return {}
    data = _mapping(value, "context")
    # Unknown context is dropped rather than stored.  This intentionally removes
    # UTM values, names, phone numbers, message bodies, and arbitrary free text.
    safe: Dict[str, Any] = {}
    if data.get("journey_id") not in (None, ""):
        journey_id = _required_text(
            data["journey_id"], "context.journey_id", max_length=72
        )
        if not _JOURNEY_RE.fullmatch(journey_id):
            raise _error(
                "context.journey_id",
                "invalid_format",
                "معرّف الرحلة غير صحيح.",
                "The journey correlation ID is invalid.",
            )
        safe["journey_id"] = journey_id
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
    derived_band: Optional[str] = None
    span_exact_months: Optional[int] = None
    if data.get("move_out") not in (None, ""):
        safe["move_out"] = _date(data["move_out"], "context.move_out")
        if "move_in" not in safe:
            raise _error(
                "context.move_in",
                "required",
                "تاريخ الدخول مطلوب عند حفظ تاريخ الخروج.",
                "Move-in date is required when move-out is recorded.",
            )
        duration_days, exact_months = _calendar_span(
            safe["move_in"], safe["move_out"], "context.move_out"
        )
        safe["duration_days"] = duration_days
        span_exact_months = exact_months
        if exact_months is not None:
            safe["duration_months"] = exact_months
        derived_band = _duration_band_from_dates(safe["move_in"], safe["move_out"])
    if data.get("duration_months") not in (None, ""):
        supplied_months = _integer(
            data["duration_months"],
            "context.duration_months",
            minimum=1,
            maximum=6,
        )
        if (
            data.get("move_out") not in (None, "")
            and supplied_months != span_exact_months
        ):
            raise _error(
                "context.duration_months",
                "mismatch",
                "مدة الأشهر لا تطابق التواريخ المحددة.",
                "The month duration does not match the selected dates.",
            )
        safe["duration_months"] = supplied_months
        if derived_band is None:
            derived_band = _duration_band_from_months(supplied_months)
    if data.get("duration_band") not in (None, ""):
        supplied_band = _choice(
            data["duration_band"],
            "context.duration_band",
            ("1_month", "2_3_months", "4_6_months"),
        )
        if derived_band is None:
            raise _error(
                "context.duration_band",
                "unverified",
                "لا يمكن حفظ نطاق المدة بدون مدة أو تواريخ متحققة.",
                "A duration band requires validated dates or duration.",
            )
        if supplied_band != derived_band:
            raise _error(
                "context.duration_band",
                "mismatch",
                "نطاق المدة لا يطابق التواريخ المحددة.",
                "The duration band does not match the selected dates.",
            )
    if derived_band is not None:
        safe["duration_band"] = derived_band
    if data.get("purpose") not in (None, ""):
        safe["purpose"] = _choice(data["purpose"], "context.purpose", PURPOSES)
    if data.get("place_id") not in (None, ""):
        safe["place_id"] = _allowlisted_place_id(
            data["place_id"], "context.place_id", allowed_place_ids
        )
    if data.get("entry_route") not in (None, ""):
        safe["entry_route"] = _choice(
            data["entry_route"], "context.entry_route", ENTRY_ROUTES
        )
    if data.get("question") not in (None, "") or data.get("answer") not in (None, ""):
        question = _choice(
            data.get("question"), "context.question", MATCHER_QUESTIONS
        )
        answer = data.get("answer")
        if question == "purpose":
            parsed_answer: Any = _choice(answer, "context.answer", PURPOSES)
        elif question == "sleeping":
            parsed_answer = _choice(answer, "context.answer", SLEEPING_OPTIONS)
        elif question == "flexibility":
            parsed_answer = _choice(answer, "context.answer", FLEXIBILITY_OPTIONS)
        elif question == "residents":
            parsed_answer = _integer(
                answer,
                "context.answer",
                minimum=1,
                maximum=MAX_PUBLIC_RESIDENTS,
            )
        elif question == "duration_months":
            parsed_answer = _integer(answer, "context.answer", minimum=1, maximum=6)
        elif question in ("move_in", "move_out"):
            parsed_answer = _date(answer, "context.answer")
        else:
            parsed_answer = _allowlisted_place_id(
                answer, "context.answer", allowed_place_ids
            )
        safe["question"] = question
        safe["answer"] = parsed_answer
    if "lead_reference" in data:
        raise _error(
            "context.lead_reference",
            "not_allowed",
            "مرجع الطلب يُنشأ من الخادم ولا يقبله هذا المسار.",
            "Lead references are server-created and cannot be accepted here.",
        )
    if data.get("rank") not in (None, ""):
        safe["rank"] = _integer(
            data["rank"],
            "context.rank",
            minimum=1,
            maximum=MAX_PUBLIC_RESULT_RANK,
        )
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


def parse_event(
    value: Any,
    *,
    session_secret: Any = None,
    allowed_place_ids: Optional[Collection[str]] = None,
) -> Dict[str, Any]:
    """Validate an anonymous funnel event and discard nonessential context."""

    data = _mapping(value)
    _reject_unknown(data, {"event", "session_id", "context"})
    return {
        "event": _choice(data.get("event"), "event", PUBLIC_EVENT_NAMES),
        "session_id": _anonymous_session(
            data.get("session_id"), session_secret
        ),
        "context": _event_context(
            data.get("context"), _place_allowlist(allowed_place_ids)
        ),
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
