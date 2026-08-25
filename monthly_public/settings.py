"""Required launch configuration and response-window calculation."""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_WHATSAPP_RE = re.compile(r"^[1-9][0-9]{7,14}$")
_ROUTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{1,79}$")
_CLOCK_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_SAR_CENT = Decimal("0.01")
# Parsing safety ceiling, not a commercial deposit recommendation.
MAX_DEPOSIT_SAR = Decimal("10000000")

_DAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_DAY_AR = (
    "الاثنين",
    "الثلاثاء",
    "الأربعاء",
    "الخميس",
    "الجمعة",
    "السبت",
    "الأحد",
)
_DAY_EN = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _deep_freeze(value: Any) -> Any:
    """Copy nested containers into immutable equivalents."""

    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class SettingsIssue:
    field: str
    code: str
    message_ar: str
    message_en: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "field": self.field,
            "code": self.code,
            "message_ar": self.message_ar,
            "message_en": self.message_en,
        }


@dataclass(frozen=True)
class WorkInterval:
    start: dt.time
    end: dt.time


@dataclass(frozen=True)
class WorkingHours:
    timezone: str
    schedule: Mapping[int, Tuple[WorkInterval, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "schedule", _deep_freeze(self.schedule))


@dataclass(frozen=True)
class MonthlySettings:
    whatsapp_number: Optional[str]
    working_hours: Optional[WorkingHours]
    commercial_terms: Mapping[str, Any]
    long_stay_route: Optional[str]
    blockers: Tuple[SettingsIssue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "commercial_terms", _deep_freeze(self.commercial_terms)
        )
        object.__setattr__(self, "blockers", tuple(self.blockers))

    @property
    def launch_ready(self) -> bool:
        return not self.blockers


def _issue(field: str, code: str, ar: str, en: str) -> SettingsIssue:
    return SettingsIssue(field, code, ar, en)


def _pick(values: Mapping[str, Any], simple: str, environment: str) -> Any:
    if simple in values:
        return values.get(simple)
    return values.get(environment)


def _decode_mapping(value: Any) -> Optional[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return None
        if isinstance(decoded, Mapping):
            return decoded
    return None


def _clock(value: Any) -> dt.time:
    if not isinstance(value, str) or not _CLOCK_RE.fullmatch(value):
        raise ValueError("invalid clock")
    return dt.time(int(value[:2]), int(value[3:]))


def _working_hours(value: Any) -> Optional[WorkingHours]:
    raw = _decode_mapping(value)
    if raw is None:
        return None
    timezone = raw.get("timezone")
    schedule_raw = raw.get("schedule")
    if not isinstance(timezone, str) or not isinstance(schedule_raw, Mapping):
        return None
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    schedule: Dict[int, Tuple[WorkInterval, ...]] = {}
    total = 0
    try:
        for day_name, periods in schedule_raw.items():
            if day_name not in _DAY_INDEX or not isinstance(periods, (list, tuple)):
                return None
            parsed = []
            for period in periods:
                if isinstance(period, Mapping):
                    start_value = period.get("start")
                    end_value = period.get("end")
                elif isinstance(period, (list, tuple)) and len(period) == 2:
                    start_value, end_value = period
                else:
                    return None
                start = _clock(start_value)
                end = _clock(end_value)
                if start >= end:
                    return None
                parsed.append(WorkInterval(start, end))
            parsed.sort(key=lambda interval: interval.start)
            for previous, current in zip(parsed, parsed[1:]):
                if previous.end > current.start:
                    return None
            schedule[_DAY_INDEX[day_name]] = tuple(parsed)
            total += len(parsed)
    except (TypeError, ValueError):
        return None
    if total == 0:
        return None
    return WorkingHours(timezone, MappingProxyType(schedule))


def _text(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _sar_amount(value: Any) -> Optional[Any]:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    try:
        amount = Decimal(str(value))
        if (
            not amount.is_finite()
            or amount < 0
            or amount > MAX_DEPOSIT_SAR
            or amount.quantize(_SAR_CENT) != amount
        ):
            return None
    except (InvalidOperation, ValueError):
        return None
    return value


def _commercial_terms(
    value: Any, blockers: list[SettingsIssue]
) -> Mapping[str, Any]:
    raw = _decode_mapping(value)
    if raw is None:
        blockers.append(
            _issue(
                "commercial_terms",
                "commercial_terms_missing",
                "الشروط التجارية الشهرية غير مهيأة.",
                "Monthly commercial terms are not configured.",
            )
        )
        return MappingProxyType({})

    normalized: Dict[str, Any] = {}
    included_value = raw.get("included")
    included = (
        tuple(item.strip() for item in included_value if isinstance(item, str) and item.strip())
        if isinstance(included_value, (list, tuple))
        else ()
    )
    normalized["included"] = included
    for required, code, ar, en in (
        (
            "internet",
            "internet_not_included",
            "يجب تأكيد شمول الإنترنت.",
            "Internet inclusion must be confirmed.",
        ),
        (
            "maintenance",
            "maintenance_not_included",
            "يجب تأكيد شمول الصيانة.",
            "Maintenance inclusion must be confirmed.",
        ),
    ):
        if required not in included:
            blockers.append(_issue("commercial_terms.included", code, ar, en))

    deposit = raw.get("deposit")
    if deposit is None:
        blockers.append(
            _issue(
                "commercial_terms.deposit",
                "deposit_missing",
                "مبلغ التأمين وشروط استرداده غير مهيأة.",
                "The deposit and refund terms are not configured.",
            )
        )
    elif not isinstance(deposit, Mapping):
        blockers.append(
            _issue(
                "commercial_terms.deposit",
                "deposit_invalid",
                "بيانات التأمين غير صحيحة.",
                "The deposit configuration is invalid.",
            )
        )
    else:
        amount = _sar_amount(deposit.get("amount_sar"))
        refund_ar = _text(deposit.get("refund_ar"))
        refund_en = _text(deposit.get("refund_en"))
        if (
            amount is None
            or refund_ar is None
            or refund_en is None
        ):
            blockers.append(
                _issue(
                    "commercial_terms.deposit",
                    "deposit_invalid",
                    "مبلغ التأمين وشروط استرداده غير مكتملة.",
                    "The deposit and refund terms are incomplete.",
                )
            )
        else:
            normalized["deposit"] = MappingProxyType(
                {
                    "amount_sar": amount,
                    "refund_ar": refund_ar,
                    "refund_en": refund_en,
                }
            )

    payment_value = raw.get("payment_methods")
    methods = []
    if isinstance(payment_value, (list, tuple)):
        for item in payment_value:
            if not isinstance(item, Mapping):
                methods = []
                break
            ar = _text(item.get("ar"))
            en = _text(item.get("en"))
            if ar is None or en is None:
                methods = []
                break
            methods.append(MappingProxyType({"ar": ar, "en": en}))
    if not methods:
        blockers.append(
            _issue(
                "commercial_terms.payment_methods",
                "payment_methods_missing",
                "طرق الدفع المعتمدة غير مهيأة.",
                "Approved payment methods are not configured.",
            )
        )
    else:
        normalized["payment_methods"] = tuple(methods)
    return MappingProxyType(normalized)


def load_settings(values: Mapping[str, Any]) -> MonthlySettings:
    """Load explicit config while retaining a safe, inspectable blocked state.

    Missing required values do not crash the process.  They become bilingual
    launch blockers, so staff can inspect health while customer conversion stays
    disabled.
    """

    values = values if isinstance(values, Mapping) else {}
    blockers: list[SettingsIssue] = []

    whatsapp_raw = _pick(values, "whatsapp_number", "MONTHLY_WHATSAPP")
    whatsapp = _text(whatsapp_raw)
    if whatsapp is None:
        blockers.append(
            _issue(
                "whatsapp_number",
                "whatsapp_missing",
                "رقم واتساب عوجا غير مهيأ.",
                "Ouja's WhatsApp number is not configured.",
            )
        )
    elif not _WHATSAPP_RE.fullmatch(whatsapp):
        blockers.append(
            _issue(
                "whatsapp_number",
                "whatsapp_invalid",
                "رقم واتساب يجب أن يكون بصيغة دولية من أرقام فقط.",
                "The WhatsApp number must contain international digits only.",
            )
        )
        whatsapp = None

    hours_raw = _pick(values, "working_hours", "MONTHLY_WORKING_HOURS")
    hours = _working_hours(hours_raw)
    if hours_raw in (None, ""):
        blockers.append(
            _issue(
                "working_hours",
                "working_hours_missing",
                "ساعات عمل فريق عوجا غير مهيأة.",
                "Ouja team working hours are not configured.",
            )
        )
    elif hours is None:
        blockers.append(
            _issue(
                "working_hours",
                "working_hours_invalid",
                "جدول ساعات العمل غير صحيح أو فارغ.",
                "The working-hours schedule is invalid or empty.",
            )
        )

    commercial = _commercial_terms(
        _pick(values, "commercial_terms", "MONTHLY_COMMERCIAL_TERMS"), blockers
    )

    route = _text(_pick(values, "long_stay_route", "MONTHLY_LONG_STAY_ROUTE"))
    if route is None:
        blockers.append(
            _issue(
                "long_stay_route",
                "long_stay_route_missing",
                "مسار مراجعة الإقامات من أربعة إلى ستة أشهر غير مهيأ.",
                "The four-to-six-month review route is not configured.",
            )
        )
    elif not _ROUTE_RE.fullmatch(route):
        blockers.append(
            _issue(
                "long_stay_route",
                "long_stay_route_invalid",
                "مسار مراجعة الإقامة الطويلة غير صحيح.",
                "The long-stay review route is invalid.",
            )
        )
        route = None

    return MonthlySettings(
        whatsapp_number=whatsapp,
        working_hours=hours,
        commercial_terms=commercial,
        long_stay_route=route,
        blockers=tuple(blockers),
    )


def _local_now(now: dt.datetime, timezone: ZoneInfo) -> dt.datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone)
    return now.astimezone(timezone)


def _format_ar(value: dt.datetime) -> str:
    return "%s %d:%02d" % (_DAY_AR[value.weekday()], value.hour, value.minute)


def _format_en(value: dt.datetime) -> str:
    return "%s %s" % (
        _DAY_EN[value.weekday()],
        value.strftime("%I:%M %p").lstrip("0"),
    )


def response_window(settings: MonthlySettings, now: dt.datetime) -> Dict[str, Any]:
    """Return approved in-hours copy or the next configured response period."""

    hours = settings.working_hours
    if hours is None:
        return {
            "is_open": False,
            "response_minutes": None,
            "next_opens_at": None,
            "message_ar": "وقت الرد غير متاح حتى يكتمل إعداد ساعات العمل.",
            "message_en": "Response timing is unavailable until working hours are configured.",
        }
    timezone = ZoneInfo(hours.timezone)
    current = _local_now(now, timezone)
    for interval in hours.schedule.get(current.weekday(), ()):
        if interval.start <= current.timetz().replace(tzinfo=None) < interval.end:
            return {
                "is_open": True,
                "response_minutes": 30,
                "next_opens_at": None,
                "message_ar": "عادة نرد خلال 30 دقيقة في أوقات العمل",
                "message_en": "We usually reply within 30 minutes during working hours.",
            }

    next_open: Optional[dt.datetime] = None
    for day_offset in range(8):
        day = current.date() + dt.timedelta(days=day_offset)
        for interval in hours.schedule.get(day.weekday(), ()):
            candidate = dt.datetime.combine(day, interval.start, timezone)
            if candidate > current and (next_open is None or candidate < next_open):
                next_open = candidate
    if next_open is None:
        return {
            "is_open": False,
            "response_minutes": None,
            "next_opens_at": None,
            "message_ar": "وقت الرد القادم غير متاح حتى يُراجع فريق عوجا الجدول.",
            "message_en": "The next response window is unavailable until Ouja reviews the schedule.",
        }
    return {
        "is_open": False,
        "response_minutes": None,
        "next_opens_at": next_open.isoformat(),
        "message_ar": "نرد عليك في فترة العمل القادمة: %s" % _format_ar(next_open),
        "message_en": "We will reply in the next working period: %s."
        % _format_en(next_open),
    }
