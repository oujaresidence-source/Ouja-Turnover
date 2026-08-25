"""Official monthly quote presentation from prepared, verified rates only."""

from __future__ import annotations

import calendar
import datetime as dt
import math
from typing import Any, Dict, Mapping, Optional


PRICE_STALE_HOURS = 6
VERIFIED_PRICE_SOURCES = frozenset(
    {"engine_verified", "official_override", "official_rate", "contract_verified"}
)

PRELIMINARY_AR = "سعر مبدئي. يؤكد فريق عوجا نوع العقد والشروط قبل الالتزام."
PRELIMINARY_EN = (
    "Preliminary price. Ouja will confirm the contract route and terms before commitment."
)


def _date(value: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _add(value: dt.date, months: int) -> dt.date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return dt.date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def add_months(value: Any, months: Any) -> Optional[str]:
    start = _date(value)
    if start is None or isinstance(months, bool):
        return None
    try:
        count = int(months)
        if count != months and str(count) != str(months):
            return None
        return _add(start, count).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _number(value: Any, *, minimum: float = 0.01) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= minimum else None


def price_timestamp_is_fresh(value: Any, now: dt.datetime) -> bool:
    """Accept at most two missed three-hour engine refresh cycles and five minutes of clock skew."""
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo or dt.timezone.utc)
    current = now.astimezone(parsed.tzinfo)
    age = current - parsed
    return dt.timedelta(minutes=-5) <= age <= dt.timedelta(hours=PRICE_STALE_HOURS)


def _entry(value: Any, now: dt.datetime, *, require_total: bool) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return None
    monthly = _number(value.get("monthly_rate_sar"))
    total = _number(value.get("stay_total_sar")) if require_total else None
    if (
        monthly is None
        or (require_total and total is None)
        or value.get("currency") != "SAR"
        or value.get("source") not in VERIFIED_PRICE_SOURCES
        or not price_timestamp_is_fresh(value.get("verified_at"), now)
    ):
        return None
    return {
        "monthly_rate_sar": int(monthly) if monthly.is_integer() else monthly,
        "stay_total_sar": (
            int(total) if total is not None and total.is_integer() else total
        ),
    }


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return tuple(_plain(item) for item in value)
    return value


def _preliminary(start: dt.date, end: dt.date, months: Optional[int]) -> bool:
    if months is not None:
        return months >= 4
    try:
        return end > _add(start, 3)
    except (ValueError, OverflowError):
        return True


def quote_for(
    listing: Mapping[str, Any], request: Mapping[str, Any], now: dt.datetime
) -> Optional[Dict[str, Any]]:
    """Return a complete public quote or ``None`` when cached coverage is incomplete."""

    if not isinstance(listing, Mapping) or not isinstance(request, Mapping):
        return None
    start = _date(request.get("move_in"))
    if start is None:
        return None
    supplied_months = request.get("duration_months")
    supplied_move_out = request.get("move_out")
    if supplied_months not in (None, "") and supplied_move_out not in (None, ""):
        return None

    months: Optional[int] = None
    duration_days: Optional[int] = None
    price = None
    if supplied_months not in (None, ""):
        if isinstance(supplied_months, bool):
            return None
        try:
            months = int(supplied_months)
        except (TypeError, ValueError, OverflowError):
            return None
        if months < 1 or months > 6 or months != supplied_months:
            return None
        try:
            end = _add(start, months)
        except (ValueError, OverflowError):
            return None
        prices = listing.get("official_prices")
        price = _entry(
            prices.get(start.strftime("%Y-%m")) if isinstance(prices, Mapping) else None,
            now,
            require_total=False,
        )
        if price is None:
            return None
        price["stay_total_sar"] = price["monthly_rate_sar"] * months
    elif supplied_move_out not in (None, ""):
        end = _date(supplied_move_out)
        if end is None or end <= start:
            return None
        try:
            if end < _add(start, 1) or end > _add(start, 6):
                return None
        except (ValueError, OverflowError):
            return None
        duration_days = (end - start).days
        key = "%s|%s" % (start.isoformat(), end.isoformat())
        quotes = listing.get("official_request_quotes")
        price = _entry(
            quotes.get(key) if isinstance(quotes, Mapping) else None,
            now,
            require_total=True,
        )
        if price is None:
            return None
    else:
        return None

    terms = listing.get("commercial_terms")
    if not isinstance(terms, Mapping) or not all(
        key in terms
        for key in ("included", "utilities", "cleaning", "deposit", "payment_methods")
    ):
        return None
    is_preliminary = _preliminary(start, end, months)
    out: Dict[str, Any] = {
        "monthly_rate_sar": price["monthly_rate_sar"],
        "stay_total_sar": price["stay_total_sar"],
        "move_in": start.isoformat(),
        "move_out": end.isoformat(),
        "currency": "SAR",
        "included": tuple(terms["included"]),
        "utilities": _plain(terms["utilities"]),
        "cleaning": _plain(terms["cleaning"]),
        "deposit": _plain(terms["deposit"]),
        "payment_methods": tuple(_plain(item) for item in terms["payment_methods"]),
        "preliminary_contract": is_preliminary,
        "preliminary_label_ar": PRELIMINARY_AR if is_preliminary else "",
        "preliminary_label_en": PRELIMINARY_EN if is_preliminary else "",
    }
    if months is not None:
        out["months"] = months
    if duration_days is not None:
        out["duration_days"] = duration_days
    return out
