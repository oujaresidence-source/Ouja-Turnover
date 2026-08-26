"""Privacy-safe public review projections from already-cached review rows."""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple


_LISTING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_ARABIC = re.compile(r"[\u0600-\u06ff]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_UNSAFE_REVIEW_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CATEGORY_ORDER = (
    "cleanliness",
    "accuracy",
    "checkin",
    "communication",
    "location",
    "value",
)
_TOPICS = {
    "cleanliness": ("نظاف", "نظيف", "clean", "spotless"),
    "space": ("واسع", "مساح", "spacious", "roomy"),
    "service": ("استجاب", "متعاون", "مرن", "responsive", "support"),
    "location": ("موقع", "قريب", "قريبه", "location", "easy access"),
    "accuracy": ("مطابق", "الصور", "accurate", "photos"),
    "value": ("سعر", "قيمة", "price", "value"),
}


def _clean_text(value: Any, maximum: int) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(_CONTROL.sub(" ", value).split()).strip()
    return text[:maximum]


def _review_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    return _UNSAFE_REVIEW_CONTROL.sub("", text).strip()[:8_000]


def _iso_date(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    try:
        return dt.date.fromisoformat(text).isoformat()
    except (TypeError, ValueError):
        return None


def _rating(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    rating = float(value)
    if not math.isfinite(rating) or rating < 1 or rating > 5:
        return None
    return rating


def _short_name(value: Any) -> str:
    name = _clean_text(value, 80)
    if not name:
        return ""
    parts = name.split()
    if len(parts) == 1:
        return parts[0][:40]
    return "%s %s." % (parts[0][:40], parts[-1][0])


def _language(text: str) -> str:
    if _ARABIC.search(text):
        return "ar"
    if any(character.isalpha() for character in text):
        return "en"
    return "unknown"


def _eligible_review(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, Mapping) or value.get("is_public") is not True:
        return None
    listing_id = str(value.get("listing_id") or "").strip()
    review_id = _clean_text(str(value.get("id") or ""), 128)
    date = _iso_date(value.get("date"))
    rating = _rating(value.get("rating"))
    if not _LISTING_ID.fullmatch(listing_id) or not review_id or date is None or rating is None:
        return None
    text = _review_text(value.get("public_review"))
    channel = _clean_text(value.get("channel"), 40)
    row: Dict[str, Any] = {
        "id": review_id,
        "listing_id": listing_id,
        "rating": rating,
        "guest_name": _short_name(value.get("guest_name")),
        "text": text,
        "language": _language(text),
        "channel": channel,
        "date": date,
    }
    translations = {}
    for language in ("ar", "en"):
        translated = _review_text(value.get("translation_%s" % language))
        if translated and translated != text:
            translations[language] = translated
    if translations:
        row["translations"] = translations
    return row


def _insight_index(value: Any) -> Dict[str, Tuple[Mapping[str, Any], ...]]:
    if not isinstance(value, Mapping):
        return {}
    apartments = value.get("apartments")
    if not isinstance(apartments, Mapping):
        return {}
    grouped: Dict[str, list[Mapping[str, Any]]] = {}
    for row in apartments.values():
        if not isinstance(row, Mapping):
            continue
        listing_id = str(row.get("listing_id") or "").strip()
        if _LISTING_ID.fullmatch(listing_id):
            grouped.setdefault(listing_id, []).append(row)
    return {key: tuple(rows) for key, rows in grouped.items()}


def _category_scores(
    listing_id: str,
    rating_count: int,
    insights: Mapping[str, Tuple[Mapping[str, Any], ...]],
) -> Tuple[Dict[str, Any], ...]:
    candidates = insights.get(listing_id) or ()
    if len(candidates) != 1:
        return ()
    row = candidates[0]
    if row.get("count") != rating_count or not isinstance(row.get("cats"), Mapping):
        return ()
    scores = []
    for key in _CATEGORY_ORDER:
        value = row["cats"].get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < 0 or numeric > 10:
            continue
        scores.append({"key": key, "rating": round(numeric / 2.0, 2), "scale": 5})
    return tuple(scores)


def _topic_mentions(rows: Tuple[Mapping[str, Any], ...]) -> Tuple[Dict[str, int], ...]:
    total = len(rows)
    mentions = []
    for key, needles in _TOPICS.items():
        count = sum(
            any(needle in str(row.get("text") or "").casefold() for needle in needles)
            for row in rows
        )
        if count:
            mentions.append({"key": key, "count": count, "total": total})
    return tuple(mentions)


def _project(
    listing_id: str,
    rows: Iterable[Mapping[str, Any]],
    insights: Mapping[str, Tuple[Mapping[str, Any], ...]],
) -> Dict[str, Any]:
    items = tuple(rows)
    text_rows = tuple(row for row in items if row.get("text"))
    latest = tuple(
        sorted(
            text_rows,
            key=lambda row: (str(row["date"]), str(row["id"])),
            reverse=True,
        )[:10]
    )
    rating_value = round(
        sum(float(row["rating"]) for row in items) / len(items), 2
    )
    public_latest = tuple(
        {key: value for key, value in row.items() if key != "listing_id"}
        for row in latest
    )
    return {
        "rating_value": rating_value,
        "rating_scale": 5,
        "rating_count": len(items),
        "text_review_count": len(text_rows),
        "source_label": "approved_public_reviews",
        "topic_mentions": _topic_mentions(text_rows),
        "category_scores": _category_scores(listing_id, len(items), insights),
        "latest_reviews": public_latest,
        "empty_state_ar": "لا توجد مراجعات عامة نصية لهذه الشقة حاليًا.",
        "empty_state_en": "No public written reviews are available for this home yet.",
    }


def build_review_projections(
    rows: Optional[Iterable[Any]], insights: Any = None
) -> Dict[str, Dict[str, Any]]:
    """Build listing-specific projections without provider or storage access."""

    grouped: Dict[str, list[Mapping[str, Any]]] = {}
    for raw in rows or ():
        review = _eligible_review(raw)
        if review is None:
            continue
        grouped.setdefault(review["listing_id"], []).append(review)
    indexed_insights = _insight_index(insights)
    return {
        listing_id: _project(listing_id, items, indexed_insights)
        for listing_id, items in grouped.items()
    }
