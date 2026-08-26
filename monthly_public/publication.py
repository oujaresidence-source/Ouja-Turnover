"""Fail-closed publication rules for Ouja's public monthly catalog."""

from __future__ import annotations

import copy
import datetime as dt
import math
import re
import unicodedata
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple
from urllib.parse import urlsplit

from .pricing import price_timestamp_is_fresh
from .settings import MonthlySettings


CALENDAR_STALE_MINUTES = 60
CALENDAR_FUTURE_SKEW_MINUTES = 5
LICENCE_EXPIRY_WARNING_DAYS = 14
MIN_PUBLIC_IMAGES = 3

_VERIFIED_PRICE_SOURCES = frozenset(
    {"engine_verified", "official_override", "official_rate", "contract_verified"}
)
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class PublicationIssue:
    code: str
    field: str
    message_ar: str
    message_en: str
    detail: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "message_ar": self.message_ar,
            "message_en": self.message_en,
            "detail": list(self.detail),
        }


@dataclass(frozen=True)
class PublicationResult:
    listing: Mapping[str, Any]
    blockers: Tuple[PublicationIssue, ...]
    warnings: Tuple[PublicationIssue, ...]
    availability_status: str
    publishable: bool
    exact_match_eligible: bool


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _issue(code: str, field: str, ar: str, en: str, *detail: str) -> PublicationIssue:
    return PublicationIssue(code, field, ar, en, tuple(str(item) for item in detail))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any, *, minimum: float = 0.0) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        return None
    return number


def _integer(value: Any, *, minimum: int = 0) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed < minimum or parsed != value:
        return None
    return parsed


def _normal_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", _text(value)).translate(_ARABIC_DIGITS)
    return re.sub(r"\s+", " ", text).strip()


def _bedroom_claims(title: Any) -> Tuple[int, ...]:
    text = _normal_text(title).casefold()
    if not text:
        return ()
    claims = []
    if re.search(r"(?:^|[\s|·,؛\-])(?:studio|استوديو|ستوديو)(?:$|[\s|·,؛\-])", text):
        claims.append(0)
    patterns = (
        r"(?<![a-z0-9])([0-9]{1,2})\s*#?\s*br\b",
        r"(?<![a-z0-9])([0-9]{1,2})\s*(?:bedroom|bedrooms)\b",
        r"(?<![0-9])([0-9]{1,2})\s*(?:غرف(?:ة|تين|تان)?(?:\s+نوم)?)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            claims.append(int(match.group(1)))
    word_claims = (
        (r"(?:^|\s)غرفة(?:\s+نوم)?(?:$|\s)", 1),
        (r"(?:^|\s)غرفتين(?:\s+نوم)?(?:$|\s)", 2),
        (r"(?:^|\s)غرفتان(?:\s+نوم)?(?:$|\s)", 2),
        (r"(?:^|\s)ثلاث\s+غرف(?:$|\s)", 3),
        (r"(?:^|\s)أربع\s+غرف(?:$|\s)", 4),
        (r"(?:^|\s)خمس\s+غرف(?:$|\s)", 5),
        (r"(?:^|\s)ست\s+غرف(?:$|\s)", 6),
    )
    for pattern, count in word_claims:
        if re.search(pattern, text):
            claims.append(count)
    return tuple(dict.fromkeys(claims))


def title_bedroom_conflict(title: Any, bedrooms: Any) -> bool:
    """Return true only when a title makes an explicit contradictory room claim."""

    count = _integer(bedrooms, minimum=0)
    if count is None:
        return False
    claims = _bedroom_claims(title)
    return bool(claims and any(claim != count for claim in claims))


def clean_images(values: Any) -> Tuple[str, ...]:
    seen = set()
    images = []
    if not isinstance(values, (list, tuple)):
        return ()
    for value in values:
        url = _text(value)
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme != "https" or not parsed.hostname or url in seen:
            continue
        seen.add(url)
        images.append(url)
    return tuple(images)


def _parse_date(value: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(_text(value))
    except ValueError:
        return None


def _parse_datetime(value: Any, timezone: dt.tzinfo) -> Optional[dt.datetime]:
    try:
        parsed = dt.datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed


def licence_timing_issue(licence: Any, now: dt.datetime) -> Optional[PublicationIssue]:
    """Re-evaluate the clock-bound part of an already validated licence."""

    if not isinstance(licence, Mapping):
        return None
    expires = _parse_date(licence.get("expires"))
    if expires is None:
        return None
    if expires < now.date():
        return _issue(
            "licence_expired", "licence.expires",
            "ترخيص الإعلان منتهي.", "The advertising licence has expired.",
        )
    if expires <= now.date() + dt.timedelta(days=LICENCE_EXPIRY_WARNING_DAYS):
        return _issue(
            "licence_expiring", "licence.expires",
            "ترخيص الإعلان قريب الانتهاء.", "The advertising licence expires soon.",
        )
    return None


def calendar_freshness_issue(
    calendar: Any,
    now: dt.datetime,
    *,
    calendar_stale_minutes: int = CALENDAR_STALE_MINUTES,
) -> Optional[PublicationIssue]:
    """Return the current clock-bound calendar issue without touching sources."""

    if not isinstance(calendar, Mapping):
        return None
    synced = _parse_datetime(calendar.get("synced_at"), now.tzinfo or dt.timezone.utc)
    if synced is None or now.astimezone(synced.tzinfo) - synced > dt.timedelta(
        minutes=max(1, calendar_stale_minutes)
    ):
        return _issue(
            "calendar_stale", "calendar.synced_at",
            "التوفر قيد التأكيد لأن التقويم قديم.",
            "Availability is pending because the calendar is stale.",
        )
    if synced - now.astimezone(synced.tzinfo) > dt.timedelta(
        minutes=CALENDAR_FUTURE_SKEW_MINUTES
    ):
        return _issue(
            "calendar_future", "calendar.synced_at",
            "التوفر قيد التأكيد لأن وقت التقويم غير صحيح.",
            "Availability is pending because the calendar timestamp is in the future.",
        )
    return None


def revalidate_clock_bound(
    result: PublicationResult,
    now: dt.datetime,
    *,
    calendar_stale_minutes: int = CALENDAR_STALE_MINUTES,
) -> PublicationResult:
    """Recheck time-sensitive claims in one immutable publication result."""

    if not isinstance(result, PublicationResult):
        raise TypeError("result must be a PublicationResult")
    licence_codes = {"licence_expired", "licence_expiring"}
    calendar_codes = {"calendar_stale", "calendar_future"}
    blockers = [item for item in result.blockers if item.code not in licence_codes]
    warnings = [
        item for item in result.warnings
        if item.code not in licence_codes | calendar_codes
    ]
    licence_issue = licence_timing_issue(result.listing.get("licence"), now)
    if licence_issue is not None:
        (blockers if licence_issue.code == "licence_expired" else warnings).append(
            licence_issue
        )
    calendar = result.listing.get("calendar")
    calendar_missing = any(item.code == "calendar_missing" for item in warnings)
    calendar_issue = None
    if calendar and not calendar_missing:
        calendar_issue = calendar_freshness_issue(
            calendar, now,
            calendar_stale_minutes=calendar_stale_minutes,
        )
    if calendar_issue is not None:
        warnings.append(calendar_issue)
    calendar_pending = calendar_issue is not None or any(
        item.code in {"calendar_missing", "calendar_invalid"} for item in warnings
    )
    availability_status = "pending" if calendar_pending else "confirmed"
    publishable = not blockers
    return replace(
        result,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        availability_status=availability_status,
        publishable=publishable,
        exact_match_eligible=publishable and availability_status == "confirmed",
    )


def _structured(raw: Any) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        return MappingProxyType({})
    out: Dict[str, Any] = {}
    for key in ("tagline_ar", "tagline_en", "neighborhood_ar", "neighborhood_en"):
        value = _text(raw.get(key))
        if value:
            out[key] = value
    emblems = []
    emblem_values = raw.get("emblems")
    if not isinstance(emblem_values, (list, tuple)):
        emblem_values = ()
    for item in emblem_values:
        if not isinstance(item, Mapping):
            continue
        ar, en = _text(item.get("ar")), _text(item.get("en"))
        if ar and en:
            emblems.append({"icon": _text(item.get("icon")) or "default", "ar": ar, "en": en})
    if emblems:
        out["emblems"] = tuple(emblems[:6])
    sections, seen = [], set()
    section_values = raw.get("sections")
    if not isinstance(section_values, (list, tuple)):
        section_values = ()
    for item in section_values:
        if not isinstance(item, Mapping):
            continue
        values = tuple(
            _text(item.get(key))
            for key in ("title_ar", "title_en", "body_ar", "body_en")
        )
        if not all(values):
            continue
        signature = tuple(re.sub(r"[^\w\u0600-\u06ff]+", " ", value.casefold()).strip() for value in values[2:])
        if signature in seen:
            continue
        seen.add(signature)
        sections.append(
            dict(zip(("title_ar", "title_en", "body_ar", "body_en"), values))
        )
    if sections:
        out["sections"] = tuple(sections[:4])
    return _freeze(out)


def _has_content(structured: Mapping[str, Any], raw: Mapping[str, Any], lang: str) -> bool:
    suffix = "ar" if lang == "ar" else "en"
    script = _ARABIC_RE if lang == "ar" else _LATIN_RE
    candidates = [
        _text(raw.get("short_%s" % suffix)),
        _text(structured.get("tagline_%s" % suffix)),
        _text(structured.get("neighborhood_%s" % suffix)),
    ]
    for section in structured.get("sections") or ():
        candidates.extend((_text(section.get("title_%s" % suffix)), _text(section.get("body_%s" % suffix))))
    return any(candidate and script.search(candidate) for candidate in candidates)


def _verified_prices(raw: Any, now: dt.datetime) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        return MappingProxyType({})
    prices = {}
    for month, item in raw.items():
        if not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", str(month)) or not isinstance(item, Mapping):
            continue
        rate = _number(item.get("monthly_rate_sar"), minimum=0.01)
        source = _text(item.get("source"))
        if (
            rate is None
            or item.get("currency") != "SAR"
            or source not in _VERIFIED_PRICE_SOURCES
            or not price_timestamp_is_fresh(item.get("verified_at"), now)
        ):
            continue
        prices[str(month)] = {
            "monthly_rate_sar": int(rate) if rate.is_integer() else rate,
            "currency": "SAR",
            "source": source,
            "verified_at": _text(item.get("verified_at")),
        }
    return _freeze(prices)


def _verified_request_quotes(raw: Any) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        return MappingProxyType({})
    quotes = {}
    for key, item in raw.items():
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\|[0-9]{4}-[0-9]{2}-[0-9]{2}", str(key)) or not isinstance(item, Mapping):
            continue
        monthly = _number(item.get("monthly_rate_sar"), minimum=0.01)
        total = _number(item.get("stay_total_sar"), minimum=0.01)
        source = _text(item.get("source"))
        if monthly is None or total is None or item.get("currency") != "SAR" or source not in _VERIFIED_PRICE_SOURCES:
            continue
        quotes[str(key)] = {
            "monthly_rate_sar": int(monthly) if monthly.is_integer() else monthly,
            "stay_total_sar": int(total) if total.is_integer() else total,
            "currency": "SAR",
            "source": source,
            "verified_at": _text(item.get("verified_at")),
        }
    return _freeze(quotes)


def _commercial_terms(raw: Any, settings: MonthlySettings) -> Optional[Mapping[str, Any]]:
    if not isinstance(raw, Mapping):
        return None
    global_terms = settings.commercial_terms
    if not all(key in global_terms for key in ("included", "deposit", "payment_methods")):
        return None
    utilities, cleaning = raw.get("utilities"), raw.get("cleaning")
    if not isinstance(utilities, Mapping) or not isinstance(cleaning, Mapping):
        return None
    utility_mode = _text(utilities.get("mode"))
    cleaning_mode = _text(cleaning.get("mode"))
    if utility_mode not in ("included", "variable", "excluded"):
        return None
    if cleaning_mode not in ("included", "optional", "unavailable"):
        return None
    utility_ar, utility_en = _text(utilities.get("label_ar")), _text(utilities.get("label_en"))
    cleaning_ar, cleaning_en = _text(cleaning.get("label_ar")), _text(cleaning.get("label_en"))
    if not all((utility_ar, utility_en, cleaning_ar, cleaning_en)):
        return None
    cleaning_amount = cleaning.get("amount_sar")
    if cleaning_mode == "optional" and _number(cleaning_amount, minimum=0.0) is None:
        return None
    return _freeze(
        {
            "included": tuple(global_terms["included"]),
            "deposit": global_terms["deposit"],
            "payment_methods": tuple(global_terms["payment_methods"]),
            "utilities": {"mode": utility_mode, "label_ar": utility_ar, "label_en": utility_en},
            "cleaning": {
                "mode": cleaning_mode,
                "amount_sar": cleaning_amount if cleaning_mode == "optional" else None,
                "label_ar": cleaning_ar,
                "label_en": cleaning_en,
            },
        }
    )


def validate_listing(
    raw: Mapping[str, Any],
    settings: MonthlySettings,
    now: dt.datetime,
    *,
    calendar_stale_minutes: int = CALENDAR_STALE_MINUTES,
) -> PublicationResult:
    """Validate and sanitize one prepared listing without changing the source."""

    source = copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}
    blockers = []
    warnings = []

    listing_id = source.get("id")
    if listing_id in (None, ""):
        blockers.append(_issue("listing_id_missing", "id", "معرّف الشقة مفقود.", "Listing ID is missing."))
    if source.get("active") is not True:
        blockers.append(_issue("inactive_listing", "active", "الشقة غير مفعلة للإقامة الشهرية.", "The listing is not active for monthly stays."))

    name_ar, name_en = _text(source.get("name_ar")), _text(source.get("name_en"))
    if not name_ar or not _ARABIC_RE.search(name_ar):
        blockers.append(_issue("arabic_title_missing", "name_ar", "العنوان العربي المعتمد مفقود.", "The approved Arabic title is missing."))
    if not name_en or not _LATIN_RE.search(name_en):
        blockers.append(_issue("english_title_missing", "name_en", "العنوان الإنجليزي المعتمد مفقود.", "The approved English title is missing."))
    structured = _structured(source.get("structured"))
    if source.get("content_verified") is not True:
        blockers.append(_issue("content_unverified", "content_verified", "محتوى الشقة لم يعتمد بعد.", "The listing content has not been approved."))
    if not _has_content(structured, source, "ar"):
        blockers.append(_issue("arabic_content_missing", "content", "المحتوى العربي المعتمد مفقود.", "Approved Arabic content is missing."))
    if not _has_content(structured, source, "en"):
        blockers.append(_issue("english_content_missing", "content", "المحتوى الإنجليزي المعتمد مفقود.", "Approved English content is missing."))

    bedrooms = _integer(source.get("bedrooms"), minimum=0)
    if bedrooms is None:
        bedrooms = _integer(source.get("beds"), minimum=0)
    baths = _integer(source.get("baths"), minimum=1)
    capacity = _integer(source.get("capacity"), minimum=1)
    if bedrooms is None:
        blockers.append(_issue("bedrooms_missing", "bedrooms", "عدد غرف النوم مفقود.", "Bedroom count is missing."))
    if baths is None:
        blockers.append(_issue("bathrooms_missing", "baths", "عدد دورات المياه مفقود.", "Bathroom count is missing."))
    if capacity is None:
        blockers.append(_issue("capacity_missing", "capacity", "سعة الشقة مفقودة.", "Listing capacity is missing."))
    if bedrooms is not None and (
        title_bedroom_conflict(name_ar, bedrooms) or title_bedroom_conflict(name_en, bedrooms)
    ):
        blockers.append(_issue("title_bedroom_conflict", "title", "العنوان يتعارض مع عدد غرف النوم.", "The title conflicts with the bedroom count.", name_ar, name_en, str(bedrooms)))

    neighborhood = _text(source.get("neighborhood"))
    neighborhood_ar = _text(source.get("neighborhood_ar"))
    neighborhood_en = _text(source.get("neighborhood_en"))
    generic = neighborhood_ar in ("الرياض",) or neighborhood_en.casefold() == "riyadh"
    if not neighborhood or not neighborhood_ar or not neighborhood_en or source.get("neighborhood_verified") is not True or generic:
        blockers.append(_issue("neighbourhood_missing", "neighborhood", "الحي المعتمد مفقود.", "The approved neighborhood is missing."))

    images = clean_images(source.get("images"))
    if len(images) < MIN_PUBLIC_IMAGES:
        blockers.append(_issue("images_missing", "images", "صور الشقة المعتمدة غير كافية.", "The listing does not have enough approved images."))
    elif len(images) < len(source.get("images") or ()):
        warnings.append(_issue("duplicate_image", "images", "حُذفت صور مكررة أو غير صالحة.", "Duplicate or invalid images were removed."))

    licence = source.get("licence")
    clean_licence = {}
    if not isinstance(licence, Mapping) or not _text(licence.get("licence_no")):
        blockers.append(_issue("licence_missing", "licence", "رقم ترخيص الإعلان مفقود.", "The advertising licence number is missing."))
    else:
        expires_text = _text(licence.get("expires"))
        if not expires_text:
            blockers.append(_issue("licence_expiry_missing", "licence.expires", "تاريخ انتهاء الترخيص مفقود.", "The licence expiry date is missing."))
        else:
            expires = _parse_date(expires_text)
            if expires is None:
                blockers.append(_issue("licence_expiry_invalid", "licence.expires", "تاريخ انتهاء الترخيص غير صحيح.", "The licence expiry date is invalid."))
            else:
                clean_licence = {"number": _text(licence.get("licence_no")), "expires": expires_text}
                timing_issue = licence_timing_issue(clean_licence, now)
                if timing_issue is not None:
                    (blockers if timing_issue.code == "licence_expired" else warnings).append(
                        timing_issue
                    )

    prices = _verified_prices(source.get("official_prices"), now)
    if not prices:
        blockers.append(_issue("price_missing", "official_prices", "السعر الشهري الرسمي مفقود.", "The official monthly price is missing."))

    terms = _commercial_terms(source.get("commercial_terms"), settings)
    if terms is None:
        blockers.append(_issue("commercial_terms_missing", "commercial_terms", "شروط الخدمات والتأمين والدفع غير مكتملة.", "Service, deposit, and payment terms are incomplete."))

    calendar = source.get("calendar")
    availability_status = "confirmed"
    clean_calendar = {}
    if not isinstance(calendar, Mapping):
        availability_status = "pending"
        warnings.append(_issue("calendar_missing", "calendar", "التوفر قيد التأكيد لغياب التقويم.", "Availability is pending because calendar data is missing."))
    else:
        freshness_issue = calendar_freshness_issue(
            calendar, now, calendar_stale_minutes=calendar_stale_minutes
        )
        if freshness_issue is not None:
            availability_status = "pending"
            warnings.append(freshness_issue)
        coverage_from = _parse_date(calendar.get("from"))
        coverage_to = _parse_date(calendar.get("to"))
        coverage_valid = (
            coverage_from is not None
            and coverage_to is not None
            and coverage_from < coverage_to
        )
        if not coverage_valid:
            availability_status = "pending"
            warnings.append(_issue("calendar_invalid", "calendar", "التوفر قيد التأكيد لأن نطاق التقويم غير صحيح.", "Availability is pending because calendar coverage is invalid."))
        blocked_dates = calendar.get("blocked_dates")
        blocked_dates_valid = isinstance(blocked_dates, (list, tuple))
        if not blocked_dates_valid:
            blocked_dates = ()
        elif any(
            not isinstance(value, str) or _parse_date(value) is None
            for value in blocked_dates
        ):
            blocked_dates_valid = False
        if not blocked_dates_valid:
            availability_status = "pending"
            warnings.append(_issue("calendar_invalid", "calendar.blocked_dates", "التوفر قيد التأكيد لأن أيام التقويم المحجوزة غير مكتملة.", "Availability is pending because blocked calendar dates are incomplete."))
        clean_calendar = {
            "synced_at": _text(calendar.get("synced_at")),
            "from": coverage_from.isoformat() if coverage_valid else "",
            "to": coverage_to.isoformat() if coverage_valid else "",
            "blocked_dates": tuple(
                sorted(
                    {
                        str(value)
                        for value in blocked_dates
                        if isinstance(value, str) and _parse_date(value) is not None
                    }
                )
            ),
        }

    rating = _number(source.get("rating"), minimum=1.0)
    reviews = _integer(source.get("reviews_count"), minimum=1)
    rating_ok = (
        source.get("rating_verified") is True
        and source.get("rating_source") == "approved_public_reviews"
        and rating is not None
        and rating <= 5.0
        and reviews is not None
    )
    if not rating_ok:
        warning_code = "rating_unverified" if source.get("rating_verified") is not True else "rating_invalid"
        warnings.append(_issue(warning_code, "rating", "التقييم غير متاح حتى يكتمل التحقق.", "The rating is unavailable until verification is complete."))

    coordinates = source.get("coordinates")
    clean_coordinates = None
    if isinstance(coordinates, Mapping) and coordinates.get("verified") is True:
        lat = _number(coordinates.get("lat"), minimum=-90.0)
        lng = _number(coordinates.get("lng"), minimum=-180.0)
        if lat is not None and lng is not None and lat <= 90 and lng <= 180 and _text(coordinates.get("source")):
            clean_coordinates = {"lat": lat, "lng": lng, "source": _text(coordinates.get("source")), "verified": True}
    if clean_coordinates is None:
        warnings.append(_issue("coordinates_unverified", "coordinates", "لن تظهر ادعاءات قرب حتى تعتمد الإحداثيات.", "Proximity claims stay hidden until coordinates are verified."))

    from .presentation import map_amenities
    from .reviews import sanitize_review_projection

    _groups, unknown_amenities = map_amenities(source.get("amenities") or ())
    if unknown_amenities:
        warnings.append(_issue("untranslated_amenity", "amenities", "حُذفت مرافق غير مترجمة أو غير معتمدة.", "Untranslated or unapproved amenities were omitted.", *unknown_amenities))

    amenity_values = source.get("amenities")
    if not isinstance(amenity_values, (list, tuple)):
        amenity_values = ()
    fact_values = source.get("facts")
    if not isinstance(fact_values, Mapping):
        fact_values = {}
    clean_listing = {
        "id": str(listing_id) if listing_id not in (None, "") else "",
        "slug": _text(source.get("slug")),
        "name_ar": name_ar,
        "name_en": name_en,
        "short_ar": _text(source.get("short_ar")),
        "short_en": _text(source.get("short_en")),
        "structured": structured,
        "neighborhood": neighborhood,
        "neighborhood_ar": neighborhood_ar,
        "neighborhood_en": neighborhood_en,
        "bedrooms": bedrooms,
        "beds_count": _integer(source.get("beds_count"), minimum=0),
        "baths": baths,
        "capacity": capacity,
        "floor_area_sqm": _number(source.get("floor_area_sqm"), minimum=1.0),
        "images": images,
        "amenities": tuple(_text(item) for item in amenity_values if _text(item)),
        "facts": {key: value for key, value in fact_values.items() if isinstance(key, str) and isinstance(value, bool)},
        "licence": clean_licence,
        "official_prices": prices,
        "official_request_quotes": _verified_request_quotes(source.get("official_request_quotes")),
        "calendar": clean_calendar,
        "commercial_terms": terms or {},
        "coordinates": clean_coordinates,
        "public_reviews": sanitize_review_projection(source.get("public_reviews")),
    }
    if rating_ok:
        clean_listing.update({"rating": rating, "reviews_count": reviews, "rating_verified": True})

    publishable = not blockers
    exact = publishable and availability_status == "confirmed"
    return PublicationResult(
        listing=_freeze(clean_listing),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        availability_status=availability_status,
        publishable=publishable,
        exact_match_eligible=exact,
    )
