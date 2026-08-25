"""Bilingual, structured, claim-safe listing presentation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Mapping, Tuple


_GROUPS = (
    ("essentials", "الأساسيات", "Essentials"),
    ("kitchen", "المطبخ", "Kitchen"),
    ("comfort", "الراحة", "Comfort"),
    ("safety", "السلامة", "Safety"),
    ("access", "المواقف والدخول", "Parking & access"),
)

_AMENITIES = {
    "internet": ("essentials", "إنترنت", "Internet", ("wireless", "wifi", "wi fi", "internet")),
    "television": ("essentials", "تلفزيون", "Television", ("television", "tv")),
    "air_conditioning": ("essentials", "تكييف", "Air conditioning", ("air conditioning", "air conditioner", "ac")),
    "heating": ("essentials", "تدفئة", "Heating", ("heating",)),
    "hot_water": ("essentials", "ماء حار", "Hot water", ("hot water",)),
    "iron": ("essentials", "مكواة", "Iron", ("iron",)),
    "hair_dryer": ("essentials", "مجفف شعر", "Hair dryer", ("hair dryer", "hairdryer")),
    "towels": ("essentials", "مناشف", "Towels", ("towels",)),
    "linens": ("essentials", "بياضات", "Bed linens", ("bed linens", "linens")),
    "workspace": ("essentials", "مساحة عمل", "Workspace", ("workspace", "dedicated workspace", "desk")),
    "kitchen": ("kitchen", "مطبخ", "Kitchen", ("kitchen", "full kitchen")),
    "refrigerator": ("kitchen", "ثلاجة", "Refrigerator", ("refrigerator", "fridge")),
    "freezer": ("kitchen", "فريزر", "Freezer", ("freezer",)),
    "microwave": ("kitchen", "ميكروويف", "Microwave", ("microwave",)),
    "oven": ("kitchen", "فرن", "Oven", ("oven",)),
    "stove": ("kitchen", "موقد", "Stove", ("stove", "cooktop")),
    "dishwasher": ("kitchen", "غسالة صحون", "Dishwasher", ("dishwasher",)),
    "coffee_maker": ("kitchen", "آلة قهوة", "Coffee maker", ("coffee maker", "coffee machine")),
    "washer": ("comfort", "غسالة ملابس", "Washer", ("washer", "washing machine")),
    "dryer": ("comfort", "نشافة", "Dryer", ("dryer", "tumble dryer")),
    "elevator": ("comfort", "مصعد", "Elevator", ("elevator", "lift")),
    "balcony": ("comfort", "شرفة", "Balcony", ("balcony",)),
    "terrace": ("comfort", "تراس", "Terrace", ("terrace",)),
    "gym": ("comfort", "نادي رياضي", "Gym", ("gym", "fitness center")),
    "pool": ("comfort", "مسبح", "Pool", ("pool", "swimming pool")),
    "first_aid": ("safety", "حقيبة إسعافات أولية", "First-aid kit", ("first aid kit", "first aid")),
    "smoke_detector": ("safety", "كاشف دخان", "Smoke detector", ("smoke detector", "smoke alarm")),
    "carbon_monoxide": ("safety", "كاشف أول أكسيد الكربون", "Carbon-monoxide detector", ("carbon monoxide detector", "carbon monoxide alarm")),
    "fire_extinguisher": ("safety", "طفاية حريق", "Fire extinguisher", ("fire extinguisher",)),
    "safe": ("safety", "خزنة", "Safe", ("safe",)),
    "free_parking": ("access", "موقف مجاني", "Free parking", ("free parking", "free parking on premises")),
    "parking": ("access", "موقف", "Parking", ("parking", "parking on premises")),
    "self_check_in": ("access", "دخول ذاتي", "Self check-in", ("self check in", "self check-in")),
}


def _normal(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[_/\-]+", " ", text)
    text = re.sub(r"[^\w\u0600-\u06ff ]+", "", text)
    return re.sub(r"\s+", " ", text).strip()


_ALIASES = {
    _normal(alias): key
    for key, (_group, _ar, _en, aliases) in _AMENITIES.items()
    for alias in aliases
}


def map_amenities(values: Any) -> Tuple[Tuple[Mapping[str, Any], ...], Tuple[str, ...]]:
    """Map exact provider labels to approved bilingual facts; omit every unknown."""

    buckets = {key: [] for key, _ar, _en in _GROUPS}
    unknown, seen = [], set()
    for value in values if isinstance(values, (list, tuple)) else ():
        raw = str(value).strip() if isinstance(value, str) else ""
        key = _ALIASES.get(_normal(raw))
        if not key:
            if raw and raw not in unknown:
                unknown.append(raw)
            continue
        if key in seen:
            continue
        seen.add(key)
        group, ar, en, _aliases = _AMENITIES[key]
        buckets[group].append({"key": key, "ar": ar, "en": en})
    groups = []
    for key, ar, en in _GROUPS:
        if buckets[key]:
            groups.append({"key": key, "ar": ar, "en": en, "items": tuple(buckets[key])})
    return tuple(groups), tuple(unknown)


def _lang(lang: Any) -> str:
    if lang not in ("ar", "en"):
        raise ValueError("language must be ar or en")
    return str(lang)


def _localized_groups(listing: Mapping[str, Any], lang: str) -> Tuple[Mapping[str, Any], ...]:
    groups, _unknown = map_amenities(listing.get("amenities") or ())
    return tuple(
        {
            "key": group["key"],
            "label": group[lang],
            "items": tuple({"key": item["key"], "label": item[lang]} for item in group["items"]),
        }
        for group in groups
    )


def _rating(listing: Mapping[str, Any]) -> Dict[str, Any]:
    if listing.get("rating_verified") is True and listing.get("rating") is not None and listing.get("reviews_count"):
        return {"rating": listing["rating"], "reviews_count": listing["reviews_count"]}
    return {}


def present_card(result: Any, lang: str) -> Dict[str, Any]:
    """Produce the compact public card without raw provider fields."""

    language = _lang(lang)
    listing = result.listing
    suffix = "ar" if language == "ar" else "en"
    title = listing["name_%s" % suffix]
    facts = {
        "bedrooms": listing.get("bedrooms"),
        "bathrooms": listing.get("baths"),
        "capacity": listing.get("capacity"),
    }
    if listing.get("beds_count") is not None:
        facts["beds_count"] = listing["beds_count"]
    if listing.get("floor_area_sqm") is not None:
        facts["floor_area_sqm"] = listing["floor_area_sqm"]
    out = {
        "id": listing["id"],
        "slug": listing.get("slug") or listing["id"],
        "title": title,
        "summary": listing.get("short_%s" % suffix) or "",
        "neighborhood": listing.get("neighborhood_%s" % suffix) or "",
        "facts": facts,
        "availability_status": result.availability_status,
        "cover": {
            "url": listing["images"][0] if listing.get("images") else "",
            "alt": ("صورة %s" if language == "ar" else "%s photo") % title,
        },
    }
    out.update(_rating(listing))
    return out


def present_listing(result: Any, lang: str) -> Dict[str, Any]:
    """Produce the detail page contract from approved structured fields only."""

    language = _lang(lang)
    listing = result.listing
    suffix = "ar" if language == "ar" else "en"
    card = present_card(result, language)
    title = card["title"]
    structured = listing.get("structured") or {}
    story = []
    seen = set()
    for section in structured.get("sections") or ():
        heading = section.get("title_%s" % suffix) or ""
        body = section.get("body_%s" % suffix) or ""
        signature = _normal(body)
        if not heading or not body or not signature or signature in seen:
            continue
        seen.add(signature)
        story.append({"title": heading, "body": body})
    images = tuple(
        {
            "url": url,
            "alt": (
                "صورة %d من %s" % (index, title)
                if language == "ar"
                else "Photo %d of %s" % (index, title)
            ),
        }
        for index, url in enumerate(listing.get("images") or (), start=1)
    )
    highlights = tuple(
        {"icon": item.get("icon") or "default", "label": item.get(suffix) or ""}
        for item in structured.get("emblems") or ()
        if item.get(suffix)
    )
    return {
        **card,
        "tagline": structured.get("tagline_%s" % suffix) or card["summary"],
        "images": images,
        "highlights": highlights,
        "story": tuple(story),
        "amenity_groups": _localized_groups(listing, language),
        "location": {
            "neighborhood": listing.get("neighborhood_%s" % suffix) or "",
            "description": structured.get("neighborhood_%s" % suffix) or "",
        },
        "licence": dict(listing.get("licence") or {}),
    }
