"""Verified-fit matching for the public monthly journey."""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .contracts import parse_match_request
from .presentation import present_card
from .pricing import add_months, quote_for
from .snapshot import SnapshotGeneration


_PURPOSE_FACTS = {
    "work": ("workspace",),
    "family": ("kids_ok", "full_kitchen", "washer"),
    "treatment": ("elderly_friendly", "elevator"),
    "visit": ("parking", "private_entrance"),
}

_FACT_LABELS = {
    "workspace": ("مساحة عمل موثقة", "Verified workspace"),
    "kids_ok": ("مناسب للعائلة بحسب المحتوى المعتمد", "Approved as family suitable"),
    "full_kitchen": ("مطبخ كامل موثق", "Verified full kitchen"),
    "washer": ("غسالة ملابس موثقة", "Verified washer"),
    "elderly_friendly": ("ملاءمة موثقة لكبار السن", "Verified elderly-friendly features"),
    "elevator": ("مصعد موثق", "Verified elevator"),
    "parking": ("موقف موثق", "Verified parking"),
    "private_entrance": ("مدخل خاص موثق", "Verified private entrance"),
}


def _date(value: Any) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _request_window(request: Mapping[str, Any]) -> Optional[Tuple[dt.date, dt.date]]:
    start = _date(request.get("move_in"))
    if start is None:
        return None
    if request.get("move_out"):
        end = _date(request.get("move_out"))
    else:
        end = _date(add_months(start.isoformat(), request.get("duration_months")))
    if end is None or end <= start:
        return None
    return start, end


def _pricing_request(request: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep the explicit departure route distinct from a duration request."""

    if request.get("move_out"):
        return {
            "move_in": request["move_in"],
            "move_out": request["move_out"],
            **(
                {"duration_days": request["duration_days"]}
                if request.get("duration_days") is not None
                else {}
            ),
        }
    return {
        "move_in": request["move_in"],
        "duration_months": request["duration_months"],
    }


def _shift_request(request: Mapping[str, Any], days: int) -> Dict[str, Any]:
    shifted = dict(request)
    shifted["move_in"] = (
        dt.date.fromisoformat(request["move_in"]) + dt.timedelta(days=days)
    ).isoformat()
    if request.get("move_out"):
        shifted["move_out"] = (
            dt.date.fromisoformat(request["move_out"]) + dt.timedelta(days=days)
        ).isoformat()
    return shifted


def _availability(result: Any, request: Mapping[str, Any]) -> str:
    if result.availability_status != "confirmed":
        return "pending"
    window = _request_window(request)
    calendar = result.listing.get("calendar") or {}
    coverage_start = _date(calendar.get("from"))
    coverage_end = _date(calendar.get("to"))
    if window is None or coverage_start is None or coverage_end is None:
        return "pending"
    start, end = window
    if start < coverage_start or end > coverage_end:
        return "pending"
    blocked = {
        value
        for value in (_date(item) for item in calendar.get("blocked_dates") or ())
        if value is not None
    }
    current = start
    while current < end:
        if current in blocked:
            return "unavailable"
        current += dt.timedelta(days=1)
    return "available"


def space_matches(listing: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    """Apply the matcher's hard capacity and sleeping-configuration gates."""

    capacity = listing.get("capacity")
    bedrooms = listing.get("bedrooms")
    if not isinstance(capacity, int) or capacity < request["residents"]:
        return False
    if not isinstance(bedrooms, int):
        return False
    sleeping = request["sleeping"]
    if sleeping == "studio":
        return bedrooms == 0
    minimums = {
        "one_bedroom": 1,
        "two_bedrooms": 2,
        "three_bedrooms": 3,
        "four_plus_bedrooms": 4,
    }
    if sleeping in minimums:
        return bedrooms >= minimums[sleeping]
    if sleeping == "separate_beds":
        beds = listing.get("beds_count")
        return isinstance(beds, int) and beds >= request["residents"]
    return sleeping == "flexible"


def _haversine_km(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    lat1, lng1 = math.radians(first["lat"]), math.radians(first["lng"])
    lat2, lng2 = math.radians(second["lat"]), math.radians(second["lng"])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    value = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(value)))


def _place_fit(
    listing: Mapping[str, Any],
    request: Mapping[str, Any],
    places: Mapping[str, Mapping[str, Any]],
) -> Tuple[float, Optional[float]]:
    place = request.get("place")
    if not isinstance(place, Mapping):
        return 20.0, None
    if place.get("kind") == "neighborhood":
        return (20.0 if listing.get("neighborhood") == place.get("id") else 0.0), None
    destination = places.get(str(place.get("id")))
    coordinates = listing.get("coordinates")
    if (
        not isinstance(destination, Mapping)
        or destination.get("verified") is not True
        or not destination.get("source")
        or not destination.get("label_ar")
        or not destination.get("label_en")
        or not isinstance(coordinates, Mapping)
        or coordinates.get("verified") is not True
        or not coordinates.get("source")
    ):
        return 0.0, None
    try:
        distance = _haversine_km(coordinates, destination)
    except (KeyError, TypeError, ValueError):
        return 0.0, None
    if not math.isfinite(distance):
        return 0.0, None
    if distance <= 2:
        score = 20.0
    elif distance <= 5:
        score = 16.0
    elif distance <= 10:
        score = 10.0
    elif distance <= 20:
        score = 4.0
    else:
        score = 0.0
    return score, round(distance, 1)


def _quality_score(listing: Mapping[str, Any]) -> float:
    if listing.get("rating_verified") is not True:
        return 0.0
    rating = listing.get("rating")
    reviews = listing.get("reviews_count")
    if not isinstance(rating, (int, float)) or not isinstance(reviews, int):
        return 0.0
    rating_points = max(0.0, min(7.0, (float(rating) - 3.5) / 1.5 * 7.0))
    review_points = min(3.0, math.log10(max(1, reviews) + 1))
    return rating_points + review_points


def _purpose_score(listing: Mapping[str, Any], purpose: str) -> Tuple[float, Tuple[str, ...]]:
    facts = listing.get("facts") or {}
    expected = _PURPOSE_FACTS[purpose]
    verified = tuple(key for key in expected if facts.get(key) is True)
    return 20.0 * len(verified) / len(expected), verified


def _localized_reason(key: str, language: str) -> str:
    return _FACT_LABELS[key][0 if language == "ar" else 1]


def _score(
    result: Any,
    request: Mapping[str, Any],
    language: str,
    places: Mapping[str, Mapping[str, Any]],
    *,
    adjusted_dates: bool = False,
) -> Tuple[float, Tuple[str, ...], Tuple[str, ...], Optional[float]]:
    listing = result.listing
    place_score, distance = _place_fit(listing, request, places)
    purpose_score, purpose_facts = _purpose_score(listing, request["purpose"])
    score = 25.0 + 25.0 + place_score + purpose_score + _quality_score(listing)
    reasons = [
        (
            (
                "التوفر مؤكد للتواريخ المعدلة"
                if adjusted_dates
                else "التوفر مؤكد للتواريخ المطلوبة"
            )
            if language == "ar"
            else (
                "Availability is confirmed for the adjusted dates"
                if adjusted_dates
                else "Availability is confirmed for your requested dates"
            )
        ),
        (
            "السعة الموثقة %d وتناسب %d مقيمين"
            if language == "ar"
            else "Verified capacity of %d fits %d residents"
        )
        % (listing["capacity"], request["residents"]),
    ]
    reason_codes = [
        "date_adjusted_available" if adjusted_dates else "date_available",
        "capacity_match",
    ]
    if request.get("place", {}).get("kind") == "neighborhood" and place_score:
        reasons.append(
            "في الحي اللي اخترته" if language == "ar" else "In your selected neighborhood"
        )
        reason_codes.append("place_neighborhood")
    elif distance is not None and place_score:
        destination = places[str(request["place"].get("id"))]
        label = destination["label_ar" if language == "ar" else "label_en"]
        reasons.append(
            (
                "يبعد %.1f كم بخط مستقيم عن %s بحسب إحداثيات معتمدة"
                if language == "ar"
                else "%.1f km straight-line distance from %s using verified coordinates"
            )
            % (distance, label)
        )
        reason_codes.append("place_verified_distance")
    for key in purpose_facts:
        reasons.append(_localized_reason(key, language))
        reason_codes.append("purpose_%s" % key)
    return round(score, 3), tuple(reasons[:4]), tuple(reason_codes[:4]), distance


def _id_sort(value: Any) -> Tuple[int, Any]:
    text = str(value)
    return (0, int(text)) if text.isdigit() else (1, text)


def _ranked_item(
    result: Any,
    request: Mapping[str, Any],
    language: str,
    now: dt.datetime,
    places: Mapping[str, Mapping[str, Any]],
    *,
    availability_status: str,
    adjusted_dates: bool = False,
) -> Optional[Dict[str, Any]]:
    if not space_matches(result.listing, request):
        return None
    quote = quote_for(result.listing, _pricing_request(request), now)
    if quote is None:
        return None
    score, reasons, reason_codes, distance = _score(
        result,
        request,
        language,
        places,
        adjusted_dates=adjusted_dates,
    )
    item = present_card(result, language)
    item.update(
        {
            "availability_status": availability_status,
            "quote": quote,
            "fit_score": score,
            "reasons": reasons,
            "reason_codes": reason_codes,
            "tradeoff": "",
        }
    )
    if distance is not None:
        item["straight_line_distance_km"] = distance
    return item


def _sort(
    items: Sequence[Dict[str, Any]], price_priority: str
) -> Tuple[Dict[str, Any], ...]:
    if not items:
        return ()
    if price_priority == "lowest_suitable":
        key = lambda item: (
            item["quote"]["stay_total_sar"],
            -item["fit_score"],
            _id_sort(item["id"]),
        )
    elif price_priority == "value":
        totals = [item["quote"]["stay_total_sar"] for item in items]
        lowest, highest = min(totals), max(totals)
        span = max(1, highest - lowest)

        def key(item: Mapping[str, Any]) -> Tuple[Any, ...]:
            fit = max(0.0, min(1.0, float(item["fit_score"]) / 100.0))
            affordability = 1.0 - (
                (item["quote"]["stay_total_sar"] - lowest) / span
            )
            value_score = 0.7 * fit + 0.3 * affordability
            return (
                -value_score,
                -item["fit_score"],
                item["quote"]["stay_total_sar"],
                _id_sort(item["id"]),
            )
    else:
        key = lambda item: (
            -item["fit_score"],
            item["quote"]["stay_total_sar"],
            _id_sort(item["id"]),
        )
    return tuple(sorted(items, key=key))


def _with_tradeoffs(
    items: Sequence[Dict[str, Any]], language: str
) -> Tuple[Dict[str, Any], ...]:
    if not items:
        return ()
    cheapest = min(item["quote"]["stay_total_sar"] for item in items)
    out = []
    for source in items:
        item = dict(source)
        premium = item["quote"]["stay_total_sar"] - cheapest
        if premium > 0:
            item["tradeoff"] = (
                "إجماليها أعلى بـ %s ر.س عن أقل خيار مطابق."
                % format(premium, ",")
                if language == "ar"
                else "SAR %s above the lowest-priced exact match."
                % format(premium, ",")
            )
        out.append(item)
    return tuple(out)


def _near_match(
    result: Any,
    request: Mapping[str, Any],
    language: str,
    now: dt.datetime,
    places: Mapping[str, Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    if request.get("flexibility") != "plus_minus_7":
        return None
    for offset in (1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6, -6, 7, -7):
        shifted = _shift_request(request, offset)
        if _availability(result, shifted) != "available":
            continue
        item = _ranked_item(
            result,
            shifted,
            language,
            now,
            places,
            availability_status="available",
            adjusted_dates=True,
        )
        if item is None:
            continue
        item["changed_condition"] = "dates"
        item["adjusted_move_in"] = shifted["move_in"]
        item["adjusted_move_out"] = _request_window(shifted)[1].isoformat()
        return item
    return None


def _empty_state(
    exact: Sequence[Mapping[str, Any]],
    near: Sequence[Mapping[str, Any]],
    pending: bool,
    language: str,
) -> Optional[Dict[str, str]]:
    if exact:
        return None
    if near:
        code = "near_matches"
        ar = "ما لقينا تطابق كامل، لكن هذي أقرب خيارات بتواريخ معدلة."
        en = "No exact match was found, but these are the closest options with adjusted dates."
    elif pending:
        code = "availability_pending"
        ar = "التوفر قيد التأكيد. ما راح نعرض وعد غير موثق."
        en = "Availability is being confirmed. We will not show an unverified promise."
    else:
        code = "no_exact_match"
        ar = "ما لقينا خيارًا يطابق الشروط المحددة حاليًا."
        en = "No home currently matches all selected conditions."
    return {"code": code, "message": ar if language == "ar" else en}


def rank(
    generation: SnapshotGeneration,
    request: Mapping[str, Any],
    lang: str,
    *,
    now: dt.datetime,
    places: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return three best verified matches, alternatives, and the full published catalog."""

    if not isinstance(generation, SnapshotGeneration):
        raise TypeError("generation must be a SnapshotGeneration")
    if lang not in ("ar", "en"):
        raise ValueError("language must be ar or en")
    parsed = parse_match_request(request)
    approved_places = places if isinstance(places, Mapping) else {}
    exact_items = []
    near_items = []
    catalog = []
    pending = False
    pending_count = 0
    unavailable_count = 0
    for result in generation.published:
        availability = _availability(result, parsed)
        quote = quote_for(result.listing, _pricing_request(parsed), now)
        passes_request_gates = quote is not None and space_matches(
            result.listing, parsed
        )
        if (
            availability == "pending"
            and passes_request_gates
        ):
            pending = True
            pending_count += 1
        if availability == "available" and passes_request_gates:
            item = _ranked_item(
                result,
                parsed,
                lang,
                now,
                approved_places,
                availability_status=availability,
            )
            if item is not None:
                exact_items.append(item)
                card = present_card(result, lang)
                card["availability_status"] = availability
                card["quote"] = quote
                catalog.append(card)
        elif availability in ("unavailable", "pending") and passes_request_gates:
            if availability == "unavailable":
                unavailable_count += 1
            near = _near_match(result, parsed, lang, now, approved_places)
            if near is not None:
                near_items.append(near)

    price_priority = parsed["price_priority"]
    exact = _with_tradeoffs(_sort(exact_items, price_priority), lang)
    near = _sort(near_items, price_priority)
    catalog_sorted = tuple(sorted(catalog, key=lambda item: _id_sort(item["id"])))
    return {
        "top": exact[:3],
        "alternatives": exact[3:],
        "near_matches": near[:3],
        "catalog": catalog_sorted,
        "exact_count": len(exact),
        "catalog_count": len(catalog_sorted),
        "pending_count": pending_count,
        "unavailable_count": unavailable_count,
        "catalog_claim": catalog_claim(len(catalog_sorted), lang),
        "empty_state": _empty_state(exact, near, pending, lang),
        "price_priority": price_priority,
    }


def catalog_claim(count: int, lang: str) -> str:
    """Generate a truthful public catalog statement from the eligible count."""

    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("count must be a non-negative integer")
    if lang == "ar":
        return (
            "أكثر من 50 بيتًا مفروشًا"
            if count > 50
            else "%d بيتًا مفروشًا" % count
        )
    if lang == "en":
        return "50+ furnished homes" if count >= 50 else "%d furnished homes" % count
    raise ValueError("language must be ar or en")
