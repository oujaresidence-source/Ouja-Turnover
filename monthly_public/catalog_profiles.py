"""Safe staff contracts and trusted-source prefills for monthly listings."""

from __future__ import annotations

import copy
import datetime as dt
import math
import re
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional
from urllib.parse import unquote, urlsplit

from .contracts import PURPOSES
from .settings import load_settings


_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_SAFE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_CLOCK_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_RIYADH_LAT = (24.0, 25.6)
_RIYADH_LNG = (46.0, 47.6)

PROFILE_FIELDS = frozenset(
    {
        "active",
        "name_ar",
        "name_en",
        "short_ar",
        "short_en",
        "structured",
        "content_verified",
        "neighborhood",
        "neighborhood_ar",
        "neighborhood_en",
        "neighborhood_verified",
        "bedrooms",
        "beds_count",
        "baths",
        "capacity",
        "floor_area_sqm",
        "images",
        "facts",
        "licence",
        "commercial_terms",
        "coordinates",
    }
)

FACT_FIELDS = frozenset(
    {
        "parking",
        "elevator",
        "workspace",
        "kitchen",
        "washer",
        "private_entrance",
        "compound",
        "accessibility",
        "balcony",
        "pool",
    }
)
_DAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


class CatalogContractError(ValueError):
    """A stable bilingual staff-contract error."""

    def __init__(
        self, field: str, code: str, message_ar: str, message_en: str
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


def _error(field: str, code: str, ar: str, en: str) -> CatalogContractError:
    return CatalogContractError(field, code, ar, en)


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(
            field,
            "invalid_type",
            "صيغة البيانات غير صحيحة.",
            "The data must be an object.",
        )
    return value


def _reject_unknown(value: Mapping[str, Any], allowed: Any, prefix: str = "") -> None:
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise _error(
            "%s%s" % (prefix, unknown[0]),
            "unknown_field",
            "الحقل غير معتمد ولا يمكن حفظه.",
            "This field is not approved for storage.",
        )


def _text(value: Any, field: str, maximum: int = 500, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise _error(field, "invalid_type", "قيمة الحقل غير صحيحة.", "This field has an invalid type.")
    text = re.sub(r"\s+", " ", value).strip()
    if required and not text:
        raise _error(field, "required", "هذا الحقل مطلوب.", "This field is required.")
    if len(text) > maximum:
        raise _error(field, "too_long", "النص أطول من الحد المسموح.", "The text exceeds the allowed length.")
    return text


def _language_text(value: Any, field: str, language: str, maximum: int) -> str:
    text = _text(value, field, maximum)
    pattern = _ARABIC_RE if language == "ar" else _LATIN_RE
    if not pattern.search(text):
        raise _error(
            field,
            "language_mismatch",
            "استخدم لغة الحقل المحددة.",
            "Use the language assigned to this field.",
        )
    return text


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise _error(field, "invalid_type", "اختر نعم أو لا.", "Choose yes or no.")
    return value


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise _error(field, "invalid_number", "الرقم غير صحيح.", "The number is invalid.")
    return value


def _number(value: Any, field: str, minimum: float, maximum: float) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise _error(field, "invalid_number", "المبلغ أو القياس غير صحيح.", "The amount or measurement is invalid.")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise _error(field, "invalid_number", "المبلغ أو القياس خارج الحد المسموح.", "The amount or measurement is outside the allowed range.")
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value)
    return value


def _structured(value: Any) -> Dict[str, Any]:
    raw = _mapping(value, "structured")
    _reject_unknown(
        raw,
        {"tagline_ar", "tagline_en", "neighborhood_ar", "neighborhood_en", "emblems", "sections"},
        "structured.",
    )
    out: Dict[str, Any] = {}
    for field in ("tagline_ar", "neighborhood_ar"):
        if field in raw:
            out[field] = _language_text(raw[field], "structured.%s" % field, "ar", 240)
    for field in ("tagline_en", "neighborhood_en"):
        if field in raw:
            out[field] = _language_text(raw[field], "structured.%s" % field, "en", 240)
    if "emblems" in raw:
        if not isinstance(raw["emblems"], (list, tuple)) or len(raw["emblems"]) > 6:
            raise _error("structured.emblems", "invalid_list", "قائمة السمات غير صحيحة.", "The emblems list is invalid.")
        emblems = []
        for index, item in enumerate(raw["emblems"]):
            entry = _mapping(item, "structured.emblems.%d" % index)
            _reject_unknown(entry, {"icon", "ar", "en"}, "structured.emblems.%d." % index)
            emblems.append(
                {
                    "icon": _text(entry.get("icon", "default"), "structured.emblems.%d.icon" % index, 40),
                    "ar": _language_text(entry.get("ar"), "structured.emblems.%d.ar" % index, "ar", 80),
                    "en": _language_text(entry.get("en"), "structured.emblems.%d.en" % index, "en", 80),
                }
            )
        out["emblems"] = emblems
    if "sections" in raw:
        if not isinstance(raw["sections"], (list, tuple)) or not 1 <= len(raw["sections"]) <= 4:
            raise _error("structured.sections", "invalid_list", "أضف من قسم إلى أربعة أقسام.", "Add between one and four sections.")
        sections = []
        signatures = set()
        for index, item in enumerate(raw["sections"]):
            entry = _mapping(item, "structured.sections.%d" % index)
            _reject_unknown(entry, {"title_ar", "title_en", "body_ar", "body_en"}, "structured.sections.%d." % index)
            section = {
                "title_ar": _language_text(entry.get("title_ar"), "structured.sections.%d.title_ar" % index, "ar", 120),
                "title_en": _language_text(entry.get("title_en"), "structured.sections.%d.title_en" % index, "en", 120),
                "body_ar": _language_text(entry.get("body_ar"), "structured.sections.%d.body_ar" % index, "ar", 900),
                "body_en": _language_text(entry.get("body_en"), "structured.sections.%d.body_en" % index, "en", 900),
            }
            signature = (
                re.sub(r"\W+", " ", section["body_ar"].casefold()).strip(),
                re.sub(r"\W+", " ", section["body_en"].casefold()).strip(),
            )
            if signature in signatures:
                raise _error("structured.sections.%d" % index, "duplicate_section", "يوجد قسم مكرر.", "A duplicate section was found.")
            signatures.add(signature)
            sections.append(section)
        out["sections"] = sections
    return out


def _coordinate_pair(value: str) -> Optional[tuple[float, float]]:
    text = unquote(value.strip())
    patterns = (
        r"^\s*(-?[0-9]{1,3}(?:\.[0-9]+)?)\s*,\s*(-?[0-9]{1,3}(?:\.[0-9]+)?)\s*$",
        r"@(-?[0-9]{1,3}(?:\.[0-9]+)?),(-?[0-9]{1,3}(?:\.[0-9]+)?)",
        r"[?&](?:q|query|destination)=(-?[0-9]{1,3}(?:\.[0-9]+)?),\s*(-?[0-9]{1,3}(?:\.[0-9]+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return float(match.group(1)), float(match.group(2))
            except (TypeError, ValueError):
                return None
    return None


def parse_coordinates(value: Any) -> Optional[Dict[str, Any]]:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        if "://" in value:
            try:
                parsed = urlsplit(value)
            except ValueError as error:
                raise _error("coordinates", "invalid_format", "رابط الخريطة غير صحيح.", "The map URL is invalid.") from error
            host = (parsed.hostname or "").casefold()
            if parsed.scheme != "https" or not (host == "google.com" or host.endswith(".google.com")):
                raise _error("coordinates", "invalid_map_url", "استخدم رابط خرائط Google آمن.", "Use a secure Google Maps URL.")
        pair = _coordinate_pair(value)
        if pair is None:
            raise _error("coordinates", "invalid_format", "أدخل الإحداثيات بصيغة صحيحة.", "Enter a valid coordinate pair.")
        lat, lng = pair
        source = "staff_maps_pin"
        verified = True
    else:
        raw = _mapping(value, "coordinates")
        _reject_unknown(raw, {"lat", "lng", "source", "verified"}, "coordinates.")
        lat = _number(raw.get("lat"), "coordinates.lat", -90, 90)
        lng = _number(raw.get("lng"), "coordinates.lng", -180, 180)
        source = _text(raw.get("source", "staff_maps_pin"), "coordinates.source", 80)
        verified = raw.get("verified", True)
        if not isinstance(verified, bool):
            raise _error("coordinates.verified", "invalid_type", "حالة التحقق غير صحيحة.", "The verification state is invalid.")
        if source == "guide_title_match":
            verified = False
    if not (_RIYADH_LAT[0] <= float(lat) <= _RIYADH_LAT[1] and _RIYADH_LNG[0] <= float(lng) <= _RIYADH_LNG[1]):
        raise _error("coordinates", "outside_riyadh", "الإحداثيات خارج نطاق الرياض المعتمد.", "The coordinates are outside the approved Riyadh bounds.")
    return {"lat": float(lat), "lng": float(lng), "source": source, "verified": verified}


def _images(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)) or len(value) > 40:
        raise _error("images", "invalid_list", "قائمة الصور غير صحيحة.", "The image list is invalid.")
    out = []
    for index, item in enumerate(value):
        url = _text(item, "images.%d" % index, 1200)
        try:
            parsed = urlsplit(url)
        except ValueError as error:
            raise _error("images.%d" % index, "invalid_url", "رابط الصورة غير صحيح.", "The image URL is invalid.") from error
        if parsed.scheme != "https" or not parsed.hostname:
            raise _error("images.%d" % index, "invalid_url", "رابط الصورة يجب أن يكون آمنًا.", "The image URL must be secure.")
        if url not in out:
            out.append(url)
    return out


def _facts(value: Any) -> Dict[str, Optional[bool]]:
    raw = _mapping(value, "facts")
    _reject_unknown(raw, FACT_FIELDS, "facts.")
    out = {}
    for field, state in raw.items():
        if state is not None and not isinstance(state, bool):
            raise _error("facts.%s" % field, "invalid_state", "اختر نعم أو لا أو غير مجاب.", "Choose yes, no, or unanswered.")
        out[str(field)] = state
    return out


def _licence(value: Any) -> Dict[str, str]:
    raw = _mapping(value, "licence")
    _reject_unknown(raw, {"licence_no", "expires"}, "licence.")
    number = _text(raw.get("licence_no"), "licence.licence_no", 120)
    expires = _text(raw.get("expires"), "licence.expires", 10)
    try:
        if not _DATE_RE.fullmatch(expires) or dt.date.fromisoformat(expires).isoformat() != expires:
            raise ValueError
    except ValueError as error:
        raise _error("licence.expires", "invalid_date", "تاريخ انتهاء الترخيص غير صحيح.", "The licence expiry date is invalid.") from error
    return {"licence_no": number, "expires": expires}


def _listing_terms(value: Any) -> Dict[str, Any]:
    raw = _mapping(value, "commercial_terms")
    _reject_unknown(raw, {"utilities", "cleaning"}, "commercial_terms.")
    utilities = _mapping(raw.get("utilities"), "commercial_terms.utilities")
    cleaning = _mapping(raw.get("cleaning"), "commercial_terms.cleaning")
    _reject_unknown(utilities, {"mode", "label_ar", "label_en"}, "commercial_terms.utilities.")
    _reject_unknown(cleaning, {"mode", "amount_sar", "label_ar", "label_en"}, "commercial_terms.cleaning.")
    utility_mode = _text(utilities.get("mode"), "commercial_terms.utilities.mode", 20)
    if utility_mode not in ("included", "variable", "excluded"):
        raise _error("commercial_terms.utilities.mode", "invalid_choice", "اختر طريقة احتساب الخدمات.", "Choose a utilities mode.")
    cleaning_mode = _text(cleaning.get("mode"), "commercial_terms.cleaning.mode", 20)
    if cleaning_mode not in ("included", "optional", "unavailable"):
        raise _error("commercial_terms.cleaning.mode", "invalid_choice", "اختر طريقة التنظيف.", "Choose a cleaning mode.")
    clean = {
        "utilities": {
            "mode": utility_mode,
            "label_ar": _language_text(utilities.get("label_ar"), "commercial_terms.utilities.label_ar", "ar", 300),
            "label_en": _language_text(utilities.get("label_en"), "commercial_terms.utilities.label_en", "en", 300),
        },
        "cleaning": {
            "mode": cleaning_mode,
            "amount_sar": None,
            "label_ar": _language_text(cleaning.get("label_ar"), "commercial_terms.cleaning.label_ar", "ar", 300),
            "label_en": _language_text(cleaning.get("label_en"), "commercial_terms.cleaning.label_en", "en", 300),
        },
    }
    if cleaning_mode == "optional":
        if "amount_sar" not in cleaning:
            raise _error("commercial_terms.cleaning.amount_sar", "required", "أدخل قيمة التنظيف الاختياري.", "Enter the optional cleaning amount.")
        clean["cleaning"]["amount_sar"] = _number(cleaning["amount_sar"], "commercial_terms.cleaning.amount_sar", 0, 1000000)
    elif "amount_sar" in cleaning and cleaning["amount_sar"] not in (None, 0):
        raise _error("commercial_terms.cleaning.amount_sar", "not_allowed", "المبلغ متاح للتنظيف الاختياري فقط.", "An amount is allowed only for optional cleaning.")
    return clean


def parse_profile(value: Any) -> Dict[str, Any]:
    raw = _mapping(value, "profile")
    _reject_unknown(raw, PROFILE_FIELDS)
    out: Dict[str, Any] = {}
    bool_fields = ("active", "content_verified", "neighborhood_verified")
    for field in bool_fields:
        if field in raw:
            out[field] = _bool(raw[field], field)
    language_fields = {
        "name_ar": ("ar", 180),
        "name_en": ("en", 180),
        "short_ar": ("ar", 500),
        "short_en": ("en", 500),
        "neighborhood_ar": ("ar", 120),
        "neighborhood_en": ("en", 120),
    }
    for field, (language, maximum) in language_fields.items():
        if field in raw:
            out[field] = _language_text(raw[field], field, language, maximum)
    if "neighborhood" in raw:
        key = _text(raw["neighborhood"], "neighborhood", 80)
        if not _SAFE_ID_RE.fullmatch(key):
            raise _error("neighborhood", "invalid_format", "معرّف الحي غير صحيح.", "The neighborhood ID is invalid.")
        out["neighborhood"] = key
    integer_fields = {
        "bedrooms": (0, 20),
        "beds_count": (0, 50),
        "baths": (1, 20),
        "capacity": (1, 50),
    }
    for field, bounds in integer_fields.items():
        if field in raw:
            out[field] = _integer(raw[field], field, *bounds)
    if "floor_area_sqm" in raw:
        out["floor_area_sqm"] = _number(raw["floor_area_sqm"], "floor_area_sqm", 1, 10000)
    if "structured" in raw:
        out["structured"] = _structured(raw["structured"])
    if "images" in raw:
        out["images"] = _images(raw["images"])
    if "facts" in raw:
        out["facts"] = _facts(raw["facts"])
    if "licence" in raw:
        out["licence"] = _licence(raw["licence"])
    if "commercial_terms" in raw:
        out["commercial_terms"] = _listing_terms(raw["commercial_terms"])
    if "coordinates" in raw:
        out["coordinates"] = parse_coordinates(raw["coordinates"])
    return out


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value)
    return value


def parse_global_settings(value: Any) -> Dict[str, Any]:
    raw = _mapping(value, "settings")
    _reject_unknown(raw, {"whatsapp_number", "working_hours", "commercial_terms", "long_stay_route"})

    hours = _mapping(raw.get("working_hours"), "working_hours")
    _reject_unknown(hours, {"timezone", "schedule"}, "working_hours.")
    schedule = _mapping(hours.get("schedule"), "working_hours.schedule")
    normalized_schedule: Dict[str, list[list[str]]] = {}
    for day, periods in schedule.items():
        if day not in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday") or not isinstance(periods, (list, tuple)):
            raise _error("working_hours.schedule.%s" % day, "invalid_schedule", "جدول ساعات العمل غير صحيح.", "The working-hours schedule is invalid.")
        normalized_schedule[str(day)] = []
        for index, period in enumerate(periods):
            if isinstance(period, Mapping):
                _reject_unknown(period, {"start", "end"}, "working_hours.schedule.%s.%d." % (day, index))
                pair = (period.get("start"), period.get("end"))
            elif isinstance(period, (list, tuple)) and len(period) == 2:
                pair = period
            else:
                raise _error("working_hours.schedule.%s.%d" % (day, index), "invalid_schedule", "فترة العمل غير صحيحة.", "The work interval is invalid.")
            if not all(isinstance(item, str) and _CLOCK_RE.fullmatch(item) for item in pair):
                raise _error("working_hours.schedule.%s.%d" % (day, index), "invalid_schedule", "وقت العمل غير صحيح.", "The work time is invalid.")
            normalized_schedule[str(day)].append([pair[0], pair[1]])

    commercial = _mapping(raw.get("commercial_terms"), "commercial_terms")
    _reject_unknown(commercial, {"included", "deposit", "payment_methods"}, "commercial_terms.")
    deposit = _mapping(commercial.get("deposit"), "commercial_terms.deposit")
    _reject_unknown(deposit, {"amount_sar", "refund_ar", "refund_en"}, "commercial_terms.deposit.")
    payments = commercial.get("payment_methods")
    if not isinstance(payments, (list, tuple)):
        raise _error("commercial_terms.payment_methods", "invalid_list", "طرق الدفع غير صحيحة.", "Payment methods are invalid.")
    for index, payment in enumerate(payments):
        entry = _mapping(payment, "commercial_terms.payment_methods.%d" % index)
        _reject_unknown(entry, {"ar", "en"}, "commercial_terms.payment_methods.%d." % index)

    candidate = {
        "whatsapp_number": _text(raw.get("whatsapp_number"), "whatsapp_number", 15),
        "working_hours": {
            "timezone": _text(hours.get("timezone"), "working_hours.timezone", 80),
            "schedule": normalized_schedule,
        },
        "commercial_terms": {
            "included": list(commercial.get("included") or ()),
            "deposit": {
                "amount_sar": deposit.get("amount_sar"),
                "refund_ar": deposit.get("refund_ar"),
                "refund_en": deposit.get("refund_en"),
            },
            "payment_methods": [dict(item) for item in payments],
        },
        "long_stay_route": _text(raw.get("long_stay_route"), "long_stay_route", 80),
    }
    settings = load_settings(candidate)
    if settings.blockers:
        issue = settings.blockers[0]
        raise _error(issue.field, issue.code, issue.message_ar, issue.message_en)
    return {
        "whatsapp_number": settings.whatsapp_number,
        "working_hours": candidate["working_hours"],
        "commercial_terms": _plain(settings.commercial_terms),
        "long_stay_route": settings.long_stay_route,
    }


def settings_form_values(settings: Any) -> Dict[str, Any]:
    """Expose a parsed setting object as safe, editable form values."""

    schedule: Dict[str, list[list[str]]] = {}
    hours = getattr(settings, "working_hours", None)
    if hours is not None:
        for day_index, periods in hours.schedule.items():
            if not isinstance(day_index, int) or not 0 <= day_index < len(_DAY_NAMES):
                continue
            schedule[_DAY_NAMES[day_index]] = [
                [period.start.strftime("%H:%M"), period.end.strftime("%H:%M")]
                for period in periods
            ]
    return {
        "whatsapp_number": getattr(settings, "whatsapp_number", None),
        "working_hours": {
            "timezone": getattr(hours, "timezone", None),
            "schedule": schedule,
        },
        "commercial_terms": _plain(
            getattr(settings, "commercial_terms", {}) or {}
        ),
        "long_stay_route": getattr(settings, "long_stay_route", None),
    }


def parse_place(value: Any) -> Dict[str, Any]:
    raw = _mapping(value, "place")
    _reject_unknown(raw, {"label_ar", "label_en", "purposes", "coordinates", "source_note"})
    purposes = raw.get("purposes")
    if not isinstance(purposes, (list, tuple)) or not purposes:
        raise _error("purposes", "required", "اختر غرضًا واحدًا على الأقل.", "Choose at least one purpose.")
    normalized = []
    for purpose in purposes:
        if purpose not in PURPOSES:
            raise _error("purposes", "invalid_choice", "غرض الإقامة غير معتمد.", "The stay purpose is not approved.")
        if purpose not in normalized:
            normalized.append(purpose)
    coordinates = parse_coordinates(raw.get("coordinates"))
    if not coordinates or coordinates.get("verified") is not True:
        raise _error("coordinates", "verification_required", "اعتمد إحداثيات المكان أولًا.", "Verify the place coordinates first.")
    return {
        "kind": "destination",
        "label_ar": _language_text(raw.get("label_ar"), "label_ar", "ar", 160),
        "label_en": _language_text(raw.get("label_en"), "label_en", "en", 160),
        "purposes": normalized,
        "lat": coordinates["lat"],
        "lng": coordinates["lng"],
        "source": coordinates["source"],
        "verified": True,
        "source_note": _text(raw.get("source_note"), "source_note", 300),
    }


def _source_images(value: Any) -> list[str]:
    images = []
    for item in value if isinstance(value, (list, tuple)) else ():
        url = item.get("url") if isinstance(item, Mapping) else item
        if isinstance(url, str) and url.startswith("https://") and url not in images:
            images.append(url)
    return images[:40]


def _overlay(
    target: Dict[str, Any], sources: Dict[str, str], values: Mapping[str, Any], label: str
) -> None:
    for field, value in values.items():
        try:
            safe = parse_profile({field: value})
        except CatalogContractError:
            continue
        if field in safe:
            target[field] = copy.deepcopy(safe[field])
            sources[field] = label


def build_prefill(
    hostaway: Mapping[str, Any],
    stay: Mapping[str, Any],
    licence: Any,
    rating: Any,
    approved: Optional[Mapping[str, Any]] = None,
    draft: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one allowlisted review record without importing guide secrets."""

    host = hostaway if isinstance(hostaway, Mapping) else {}
    stay_values = stay if isinstance(stay, Mapping) else {}
    out: Dict[str, Any] = {}
    sources: Dict[str, str] = {}

    host_candidate: Dict[str, Any] = {}
    for field in ("active", "bedrooms", "beds_count", "baths", "capacity", "floor_area_sqm"):
        if field in host and host.get(field) is not None:
            host_candidate[field] = host[field]
    images = _source_images(host.get("images"))
    if images:
        host_candidate["images"] = images
    lat, lng = host.get("lat"), host.get("lng")
    if lat is None or lng is None:
        coords = host.get("coordinates")
        if isinstance(coords, Mapping):
            lat, lng = coords.get("lat"), coords.get("lng")
    if lat is not None and lng is not None:
        host_candidate["coordinates"] = {
            "lat": lat,
            "lng": lng,
            "source": "hostaway_listing",
            "verified": True,
        }
    _overlay(out, sources, host_candidate, "hostaway_listing")

    stay_candidate: Dict[str, Any] = {}
    aliases = {
        "title_ar": "name_ar",
        "title_en": "name_en",
        "visible": "active",
    }
    for source_field, target_field in aliases.items():
        if source_field in stay_values and stay_values.get(source_field) is not None:
            stay_candidate[target_field] = stay_values[source_field]
    for field in PROFILE_FIELDS:
        if field in stay_values and stay_values.get(field) is not None:
            stay_candidate[field] = stay_values[field]
    if "coordinates" not in out and isinstance(stay_values.get("guide_coordinates"), Mapping):
        guide = stay_values["guide_coordinates"]
        stay_candidate["coordinates"] = {
            "lat": guide.get("lat"),
            "lng": guide.get("lng"),
            "source": "guide_title_match",
            "verified": False,
        }
    _overlay(out, sources, stay_candidate, "stay_approved")

    if isinstance(licence, Mapping):
        licence_candidate = {
            "licence_no": licence.get("licence_no") or licence.get("license_no"),
            "expires": licence.get("expires") or licence.get("expiry_date"),
        }
        try:
            out["licence"] = _licence(licence_candidate)
            sources["licence"] = "monthly_licence_store"
        except CatalogContractError:
            pass

    if approved:
        _overlay(out, sources, approved, "monthly_approved")
    if draft:
        _overlay(out, sources, draft, "monthly_draft")

    readiness: Dict[str, Any] = {}
    if isinstance(rating, Mapping):
        number = rating.get("rating")
        count = rating.get("count") if rating.get("count") is not None else rating.get("reviews_count")
        if (
            isinstance(number, (int, float))
            and not isinstance(number, bool)
            and 1 <= float(number) <= 5
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
        ):
            readiness["rating"] = float(number)
            readiness["reviews_count"] = count
            readiness["rating_source"] = "approved_public_reviews"
    out["sources"] = sources
    out["source_readiness"] = readiness
    return out


def apply_approved_profile(
    base: Mapping[str, Any], approved: Optional[Mapping[str, Any]]
) -> Dict[str, Any]:
    out = copy.deepcopy(dict(base)) if isinstance(base, Mapping) else {}
    if not approved:
        return out
    safe = parse_profile(approved)
    for field, value in safe.items():
        out[field] = copy.deepcopy(value)
    return out


def completion(profile: Mapping[str, Any]) -> Dict[str, Any]:
    value = dict(profile) if isinstance(profile, Mapping) else {}
    if value.get("active") is False:
        return {
            "percent": 100,
            "ready_for_approval": True,
            "staff_blockers": [],
            "warnings": ["monthly_visibility_disabled"],
        }

    checks = (
        ("active_missing", value.get("active") is True),
        ("arabic_title_missing", bool(value.get("name_ar"))),
        ("english_title_missing", bool(value.get("name_en"))),
        ("arabic_content_missing", bool(value.get("short_ar"))),
        ("english_content_missing", bool(value.get("short_en"))),
        ("content_unverified", value.get("content_verified") is True),
        ("bedrooms_missing", isinstance(value.get("bedrooms"), int)),
        ("bathrooms_missing", isinstance(value.get("baths"), int)),
        ("capacity_missing", isinstance(value.get("capacity"), int)),
        (
            "neighbourhood_missing",
            bool(value.get("neighborhood"))
            and bool(value.get("neighborhood_ar"))
            and bool(value.get("neighborhood_en"))
            and value.get("neighborhood_verified") is True,
        ),
        ("images_missing", len(value.get("images") or ()) >= 3),
        (
            "licence_missing",
            isinstance(value.get("licence"), Mapping)
            and bool(value["licence"].get("licence_no"))
            and bool(value["licence"].get("expires")),
        ),
        (
            "commercial_terms_missing",
            isinstance(value.get("commercial_terms"), Mapping)
            and isinstance(value["commercial_terms"].get("utilities"), Mapping)
            and isinstance(value["commercial_terms"].get("cleaning"), Mapping),
        ),
    )
    blockers = [code for code, passed in checks if not passed]
    completed = len(checks) - len(blockers)
    warnings = []
    coordinates = value.get("coordinates")
    if not isinstance(coordinates, Mapping) or coordinates.get("verified") is not True:
        warnings.append("coordinates_unverified")
    if any(state is None for state in (value.get("facts") or {}).values()):
        warnings.append("facts_unanswered")
    return {
        "percent": int(round(100 * completed / len(checks))),
        "ready_for_approval": not blockers,
        "staff_blockers": blockers,
        "warnings": warnings,
    }


__all__ = [
    "CatalogContractError",
    "FACT_FIELDS",
    "PROFILE_FIELDS",
    "apply_approved_profile",
    "build_prefill",
    "completion",
    "parse_coordinates",
    "parse_global_settings",
    "parse_place",
    "parse_profile",
    "settings_form_values",
]
