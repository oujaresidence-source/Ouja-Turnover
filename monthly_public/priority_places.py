"""Vetted monthly destinations and verified straight-line proximity."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .catalog_profiles import parse_place


PRIORITY_PLACE_MIGRATION_ID = "priority_places_2026_08_25_v1"
_DATA_PATH = Path(__file__).with_name("data") / "priority_places_2026_08_25.json"
_CATEGORY_PURPOSES = {
    "business_hubs": ["work"],
    "hospitals": ["treatment", "family"],
    "family_retail": ["family", "visit"],
    "riyadh_season": ["visit", "family"],
    "events": ["work", "visit"],
}
_PROJECTION_FIELDS = (
    "label_ar",
    "label_en",
    "category_id",
    "category_ar",
    "category_en",
    "priority",
    "map_url",
    "official_source_url",
    "coordinate_source_url",
    "verified_at",
    "review_interval_ar",
    "review_interval_en",
)


def load_priority_places() -> list[Dict[str, Any]]:
    """Return fresh validated canonical records from the approved workbook extract."""

    with _DATA_PATH.open("r", encoding="utf-8") as source:
        raw = json.load(source)
    if not isinstance(raw, list) or len(raw) != 25:
        raise ValueError("priority-place dataset must contain exactly 25 rows")
    rows: list[Dict[str, Any]] = []
    seen = set()
    for value in raw:
        if not isinstance(value, Mapping):
            raise ValueError("priority-place row must be an object")
        place_id = str(value.get("id") or "").strip()
        category_id = str(value.get("category_id") or "").strip()
        if not place_id or place_id in seen or place_id.startswith("edu_"):
            raise ValueError("priority-place IDs must be unique and exclude universities")
        if category_id not in _CATEGORY_PURPOSES:
            raise ValueError("priority-place category is not approved")
        if value.get("purposes") != _CATEGORY_PURPOSES[category_id]:
            raise ValueError("priority-place purposes do not match the approved category")
        payload = {key: copy.deepcopy(item) for key, item in value.items() if key not in ("id", "lat", "lng")}
        payload["coordinates"] = {
            "lat": value.get("lat"),
            "lng": value.get("lng"),
            "source": "priority_places_2026_08_25",
            "verified": True,
        }
        parsed = parse_place(payload)
        rows.append({"id": place_id, **parsed})
        seen.add(place_id)
    return rows


def _verified_coordinates(value: Any) -> Optional[tuple[float, float]]:
    if not isinstance(value, Mapping):
        return None
    if value.get("verified") is not True or not value.get("source"):
        return None
    lat = value.get("lat")
    lng = value.get("lng")
    if isinstance(lat, bool) or isinstance(lng, bool):
        return None
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return None
    if not (-90 <= float(lat) <= 90 and -180 <= float(lng) <= 180):
        return None
    return float(lat), float(lng)


def distance_km(origin: Mapping[str, Any], destination: Mapping[str, Any]) -> Optional[float]:
    """Return Haversine distance only for two verified coordinate pairs."""

    first = _verified_coordinates(origin)
    second = _verified_coordinates(destination)
    if first is None or second is None:
        return None
    lat1, lng1 = (math.radians(number) for number in first)
    lat2, lng2 = (math.radians(number) for number in second)
    delta_lat = lat2 - lat1
    delta_lng = lng2 - lng1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(value)))


def nearest_places(
    coordinates: Any, places: Mapping[str, Any], limit: int = 5
) -> list[Dict[str, Any]]:
    """Return stable staff-safe nearest destinations ordered by verified distance."""

    if _verified_coordinates(coordinates) is None:
        return []
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    candidates = []
    for raw_id, raw in places.items() if isinstance(places, Mapping) else ():
        place_id = str(raw_id or "").strip()
        if not place_id or not isinstance(raw, Mapping) or raw.get("kind") != "destination":
            continue
        distance = distance_km(coordinates, raw)
        if distance is None:
            continue
        priority = raw.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            priority = 100
        result = {"id": place_id}
        for field in _PROJECTION_FIELDS:
            result[field] = copy.deepcopy(raw.get(field))
        result["distance_km"] = round(distance, 1)
        candidates.append((distance, priority, place_id, result))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in candidates[:limit]]


__all__ = [
    "PRIORITY_PLACE_MIGRATION_ID",
    "distance_km",
    "load_priority_places",
    "nearest_places",
]
