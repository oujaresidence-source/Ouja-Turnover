"""Strict contracts for staff-managed monthly showcase groups."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from typing import Any, Collection, Dict, Mapping, Optional
from urllib.parse import urlsplit


SHOWCASE_FIELDS = frozenset(
    {
        "name_ar",
        "name_en",
        "slug",
        "description_ar",
        "description_en",
        "image_url",
        "image_listing_id",
        "listing_ids",
        "listing_prices",
        "fixed_monthly_rate_sar",
        "fixed_price_enabled",
    }
)

_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_GROUP_ID_RE = re.compile(r"^showcase_[A-Za-z0-9_-]{2,64}$")
_TOKEN_RE = re.compile(
    r"^sc_(showcase_[A-Za-z0-9_-]{2,64})\.([1-9][0-9]{0,8})\.([A-Za-z0-9_-]{43})$"
)
_CONTEXT = b"ouja-monthly-showcase:v1:"
_MIN_SECRET_BYTES = 32
_MAX_MEMBERS = 250


class ShowcaseContractError(ValueError):
    """Stable bilingual validation failure for the staff editor."""

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


class ShowcaseContextError(ValueError):
    """A signed public showcase context could not be trusted."""


def _error(
    field: str,
    code: str,
    message_ar: str,
    message_en: str,
) -> ShowcaseContractError:
    return ShowcaseContractError(field, code, message_ar, message_en)


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(
            "showcase",
            "invalid_type",
            "صيغة المجموعة غير صحيحة.",
            "The showcase format is invalid.",
        )
    return value


def _text(
    value: Any,
    field: str,
    maximum: int,
    *,
    required: bool = True,
) -> str:
    if not isinstance(value, str):
        raise _error(
            field,
            "invalid_type",
            "قيمة الحقل غير صحيحة.",
            "This field has an invalid type.",
        )
    text = re.sub(r"\s+", " ", value).strip()
    if required and not text:
        raise _error(field, "required", "هذا الحقل مطلوب.", "This field is required.")
    if len(text) > maximum:
        raise _error(
            field,
            "too_long",
            "النص أطول من الحد المسموح.",
            "The text exceeds the allowed length.",
        )
    return text


def _language_text(
    value: Any,
    field: str,
    language: str,
    maximum: int,
    *,
    required: bool = True,
) -> str:
    text = _text(value, field, maximum, required=required)
    if not text:
        return ""
    pattern = _ARABIC_RE if language == "ar" else _LATIN_RE
    if not pattern.search(text):
        raise _error(
            field,
            "language_mismatch",
            "استخدم لغة الحقل المحددة.",
            "Use the language assigned to this field.",
        )
    return text


def _optional_https_url(value: Any, field: str) -> Optional[str]:
    if value in (None, ""):
        return None
    text = _text(value, field, 2_000)
    try:
        parsed = urlsplit(text)
    except ValueError as error:
        raise _error(
            field,
            "invalid_url",
            "رابط الصورة غير صحيح.",
            "The image URL is invalid.",
        ) from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise _error(
            field,
            "invalid_url",
            "استخدم رابط صورة آمنًا.",
            "Use a secure image URL.",
        )
    return text


def _listing_ids(
    value: Any,
    known_listing_ids: Collection[str],
) -> list[str]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= _MAX_MEMBERS:
        raise _error(
            "listing_ids",
            "invalid_list",
            "اختر شقة واحدة على الأقل للمجموعة.",
            "Choose at least one home for the showcase.",
        )
    known = {str(item) for item in known_listing_ids}
    result = []
    seen = set()
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise _error(
                "listing_ids.%d" % index,
                "invalid_type",
                "معرّف الشقة غير صحيح.",
                "The listing identifier is invalid.",
            )
        listing_id = str(item).strip()
        if not listing_id or len(listing_id) > 128 or listing_id not in known:
            raise _error(
                "listing_ids.%d" % index,
                "unknown_listing",
                "الشقة غير موجودة في البيانات الحالية.",
                "The listing is not in the current inventory.",
            )
        if listing_id in seen:
            raise _error(
                "listing_ids.%d" % index,
                "duplicate_listing",
                "لا يمكن إضافة الشقة نفسها مرتين.",
                "The same listing cannot be added twice.",
            )
        seen.add(listing_id)
        result.append(listing_id)
    return result


def _optional_rate(value: Any, field: str = "fixed_monthly_rate_sar") -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1_000_000:
        raise _error(
            field,
            "invalid_number",
            "السعر الشهري غير صحيح.",
            "The monthly price is invalid.",
        )
    return value


def _optional_listing_id(value: Any, members: Collection[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    listing_id = str(value).strip()
    if listing_id not in {str(item) for item in members}:
        raise _error(
            "image_listing_id",
            "cover_listing_not_selected",
            "اختر صورة من إحدى شقق المجموعة.",
            "Choose a cover from one of the collection homes.",
        )
    return listing_id


def _listing_prices(value: Any, members: Collection[str]) -> Dict[str, Dict[str, Any]]:
    if value in (None, {}):
        return {}
    if not isinstance(value, Mapping):
        raise _error(
            "listing_prices",
            "invalid_type",
            "صيغة أسعار الشقق غير صحيحة.",
            "The apartment-price format is invalid.",
        )
    member_ids = {str(item) for item in members}
    result: Dict[str, Dict[str, Any]] = {}
    for raw_listing_id, raw_price in value.items():
        listing_id = str(raw_listing_id).strip()
        field = "listing_prices.%s" % listing_id
        if listing_id not in member_ids:
            raise _error(
                field,
                "listing_not_selected",
                "لا يمكن تسعير شقة خارج المجموعة.",
                "A home outside the collection cannot be priced here.",
            )
        if not isinstance(raw_price, Mapping) or set(raw_price) - {
            "monthly_rate_sar",
            "enabled",
        }:
            raise _error(
                field,
                "invalid_type",
                "بيانات سعر الشقة غير صحيحة.",
                "The apartment-price values are invalid.",
            )
        enabled = raw_price.get("enabled")
        if not isinstance(enabled, bool):
            raise _error(
                field + ".enabled",
                "invalid_type",
                "اختر تشغيل السعر أو إيقافه.",
                "Choose whether this apartment price is enabled.",
            )
        rate_field = field + ".monthly_rate_sar"
        rate = _optional_rate(raw_price.get("monthly_rate_sar"), rate_field)
        if enabled and rate is None:
            raise _error(
                rate_field,
                "required",
                "أدخل السعر الشهري لهذه الشقة.",
                "Enter the monthly price for this apartment.",
            )
        result[listing_id] = {
            "monthly_rate_sar": rate,
            "enabled": enabled,
        }
    return result


def parse_showcase(
    value: Any,
    known_listing_ids: Collection[str],
) -> Dict[str, Any]:
    """Validate and normalize one complete showcase draft."""

    raw = _mapping(value)
    unknown = sorted(str(key) for key in raw if key not in SHOWCASE_FIELDS)
    if unknown:
        raise _error(
            unknown[0],
            "unknown_field",
            "الحقل غير معتمد ولا يمكن حفظه.",
            "This field is not approved for storage.",
        )
    enabled = raw.get("fixed_price_enabled")
    if not isinstance(enabled, bool):
        raise _error(
            "fixed_price_enabled",
            "invalid_type",
            "اختر تشغيل السعر أو إيقافه.",
            "Choose whether the fixed price is enabled.",
        )
    rate = _optional_rate(raw.get("fixed_monthly_rate_sar"))
    if enabled and rate is None:
        raise _error(
            "fixed_monthly_rate_sar",
            "required",
            "أدخل السعر الشهري الثابت.",
            "Enter the fixed monthly price.",
        )
    slug = _text(raw.get("slug"), "slug", 120)
    if not _SLUG_RE.fullmatch(slug):
        raise _error(
            "slug",
            "invalid_format",
            "استخدم حروفًا إنجليزية صغيرة وأرقامًا وشرطات فقط.",
            "Use lowercase letters, numbers, and single hyphens only.",
        )
    listing_ids = _listing_ids(raw.get("listing_ids"), known_listing_ids)
    image_url = _optional_https_url(raw.get("image_url"), "image_url")
    image_listing_id = _optional_listing_id(
        raw.get("image_listing_id"), listing_ids
    )
    if image_listing_id is not None and image_url is None:
        raise _error(
            "image_url",
            "required",
            "اختر صورة الغلاف.",
            "Choose the cover image.",
        )
    return {
        "name_ar": _language_text(raw.get("name_ar"), "name_ar", "ar", 180),
        "name_en": _language_text(raw.get("name_en"), "name_en", "en", 180),
        "slug": slug,
        "description_ar": _language_text(
            raw.get("description_ar", ""),
            "description_ar",
            "ar",
            500,
            required=False,
        ),
        "description_en": _language_text(
            raw.get("description_en", ""),
            "description_en",
            "en",
            500,
            required=False,
        ),
        "image_url": image_url,
        "image_listing_id": image_listing_id,
        "listing_ids": listing_ids,
        "listing_prices": _listing_prices(raw.get("listing_prices"), listing_ids),
        "fixed_monthly_rate_sar": rate,
        "fixed_price_enabled": enabled,
    }


def parse_showcase_request(value: Any) -> Dict[str, str]:
    """Validate the small public request for one permanent group URL."""

    raw = _mapping(value)
    unknown = sorted(str(key) for key in raw if key not in {"slug", "lang"})
    if unknown:
        raise _error(
            unknown[0],
            "unknown_field",
            "يحتوي الطلب على حقل غير معتمد.",
            "The request contains an unsupported field.",
        )
    slug = _text(raw.get("slug"), "slug", 120)
    if not _SLUG_RE.fullmatch(slug):
        raise _error(
            "slug",
            "invalid_format",
            "رابط المجموعة غير صحيح.",
            "The showcase URL is invalid.",
        )
    lang = raw.get("lang", "ar")
    if lang not in ("ar", "en"):
        raise _error(
            "lang",
            "unsupported",
            "اللغة المحددة غير معتمدة.",
            "The selected language is unsupported.",
        )
    return {"slug": slug, "lang": str(lang)}


def _secret(value: Any) -> bytes:
    if isinstance(value, bytearray):
        value = bytes(value)
    if not isinstance(value, bytes) or len(value) < _MIN_SECRET_BYTES:
        raise ShowcaseContextError("showcase secret must contain at least 32 bytes")
    return value


def _group_id(value: Any) -> str:
    group_id = str(value or "")
    if not _GROUP_ID_RE.fullmatch(group_id):
        raise ShowcaseContextError("invalid showcase group identifier")
    return group_id


def _revision(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 999_999_999:
        raise ShowcaseContextError("invalid showcase revision")
    return value


def issue_showcase_context(secret: Any, group_id: Any, revision: Any) -> str:
    """Issue a price-free signed reference to server-owned approved state."""

    body = "%s.%d" % (_group_id(group_id), _revision(revision))
    digest = hmac.new(
        _secret(secret),
        _CONTEXT + body.encode("ascii"),
        hashlib.sha256,
    ).digest()
    signature = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return "sc_%s.%s" % (body, signature)


def verify_showcase_context(token: Any, secret: Any) -> Dict[str, Any]:
    """Verify a context without trusting any customer-supplied business value."""

    match = _TOKEN_RE.fullmatch(str(token or ""))
    if match is None:
        raise ShowcaseContextError("invalid showcase context")
    group_id, revision_text, supplied_signature = match.groups()
    expected_signature = issue_showcase_context(
        secret,
        group_id,
        int(revision_text),
    ).rsplit(".", 1)[1]
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise ShowcaseContextError("invalid showcase signature")
    return {"group_id": group_id, "revision": int(revision_text)}
