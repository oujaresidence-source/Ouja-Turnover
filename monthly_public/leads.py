"""Anonymous lead persistence and prepared WhatsApp handoff."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Mapping, Optional
from urllib.parse import quote as url_quote

from .contracts import (
    FLEXIBILITY_OPTIONS,
    LANGUAGES,
    PLACE_KINDS,
    PURPOSES,
    SLEEPING_OPTIONS,
    parse_outcome,
)
from .settings import MonthlySettings, response_window


DEDUPE_MINUTES = 30
_SESSION_RE = re.compile(r"^anon_[A-Za-z0-9_-]{32}\.[A-Za-z0-9_-]{43}$")
_REFERENCE_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{5,63}$")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _time(value: Any) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise TypeError("clock must return a datetime")
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)


def _choice(value: Any, choices: Any, field: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError("invalid %s" % field)
    return value


def _integer(value: Any, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError("invalid %s" % field)
    return value


def _text(value: Any, field: str, maximum: int = 300) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError("invalid %s" % field)
    return value.strip()


def _date(value: Any, field: str) -> str:
    text = _text(value, field, 10)
    try:
        if dt.date.fromisoformat(text).isoformat() != text:
            raise ValueError
    except ValueError:
        raise ValueError("invalid %s" % field)
    return text


def _number(value: Any, field: str, *, allow_zero: bool = False) -> Any:
    minimum = 0 if allow_zero else 0.01
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid %s" % field)
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError("invalid %s" % field)
    return value


def _approved_request(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("request must be a mapping")
    safe: Dict[str, Any] = {}
    choice_fields = {
        "purpose": PURPOSES,
        "sleeping": SLEEPING_OPTIONS,
        "flexibility": FLEXIBILITY_OPTIONS,
        "lang": LANGUAGES,
    }
    for field, choices in choice_fields.items():
        if field in value:
            safe[field] = _choice(value[field], choices, field)
    if "residents" in value:
        safe["residents"] = _integer(value["residents"], 1, 50, "residents")
    for field in ("move_in", "move_out"):
        if field in value:
            safe[field] = _date(value[field], field)
    if "duration_months" in value:
        safe["duration_months"] = _integer(value["duration_months"], 1, 6, "duration_months")
    if "duration_days" in value:
        safe["duration_days"] = _integer(value["duration_days"], 1, 366, "duration_days")
    if "place" in value:
        place = value["place"]
        if not isinstance(place, Mapping):
            raise ValueError("invalid place")
        safe["place"] = {
            "kind": _choice(place.get("kind"), PLACE_KINDS, "place.kind"),
            "id": _text(place.get("id"), "place.id", 80),
            "label": _text(place.get("label"), "place.label", 120),
        }
    return safe


def _approved_quote(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("quote must be a mapping")
    safe: Dict[str, Any] = {}
    for field in ("monthly_rate_sar", "stay_total_sar"):
        if field in value:
            safe[field] = _number(value[field], field)
    if "currency" in value:
        safe["currency"] = _choice(value["currency"], ("SAR",), "currency")
    for field in ("move_in", "move_out"):
        if field in value:
            safe[field] = _date(value[field], field)
    if "months" in value:
        safe["months"] = _integer(value["months"], 1, 6, "months")
    if "duration_days" in value:
        safe["duration_days"] = _integer(value["duration_days"], 1, 366, "duration_days")
    if "included" in value:
        included = value["included"]
        if not isinstance(included, (list, tuple)):
            raise ValueError("invalid included")
        safe["included"] = [_text(item, "included", 80) for item in included]
    if "preliminary_contract" in value:
        if not isinstance(value["preliminary_contract"], bool):
            raise ValueError("invalid preliminary_contract")
        safe["preliminary_contract"] = value["preliminary_contract"]
    preliminary = safe.get("preliminary_contract")
    for field in ("preliminary_label_ar", "preliminary_label_en"):
        if field in value:
            if value[field] == "" and preliminary is False:
                safe[field] = ""
            else:
                safe[field] = _text(value[field], field)
    if preliminary is True and not all(safe.get(field) for field in ("preliminary_label_ar", "preliminary_label_en")):
        raise ValueError("preliminary contract labels are required")
    nested_fields = {
        "utilities": ("mode", "label_ar", "label_en"),
        "cleaning": ("mode", "amount_sar", "label_ar", "label_en"),
        "deposit": ("amount_sar", "refund_ar", "refund_en"),
    }
    for key, allowed in nested_fields.items():
        item = value.get(key)
        if isinstance(item, Mapping):
            clean = {}
            for field in allowed:
                if field not in item:
                    continue
                if field == "amount_sar":
                    clean[field] = _number(item[field], "%s.%s" % (key, field), allow_zero=True)
                elif field == "mode":
                    modes = ("included", "variable", "excluded") if key == "utilities" else ("included", "optional", "unavailable")
                    clean[field] = _choice(item[field], modes, "%s.mode" % key)
                else:
                    clean[field] = _text(item[field], "%s.%s" % (key, field))
            safe[key] = clean
        elif key in value:
            raise ValueError("invalid %s" % key)
    methods = value.get("payment_methods")
    if isinstance(methods, (list, tuple)):
        safe["payment_methods"] = [
            {field: _text(item[field], "payment_methods.%s" % field) for field in ("ar", "en") if field in item}
            for item in methods
            if isinstance(item, Mapping)
        ]
    return safe


def _reference(now: dt.datetime) -> str:
    return "OJM-%s-%s" % (now.strftime("%Y%m%d"), secrets.token_hex(4).upper())


class LeadStore:
    """A short-connection SQLite store containing structured, anonymous leads only."""

    def __init__(self, path: Any = "monthly_public_leads.sqlite3", *, clock=None, reference_factory=None) -> None:
        self.path = Path(path)
        self.clock = clock or _utc_now
        self.reference_factory = reference_factory or _reference
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS monthly_public_leads (
                    reference TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    request_key TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    quote_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    responded_at TEXT,
                    outcome TEXT CHECK (outcome IS NULL OR outcome IN ('booked', 'lost')),
                    outcome_at TEXT,
                    lost_reason TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_monthly_lead_dedupe ON monthly_public_leads(session_id, listing_id, request_key, created_at)"
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "reference": row["reference"],
            "session_id": row["session_id"],
            "listing_id": row["listing_id"],
            "request": json.loads(row["request_json"]),
            "quote": json.loads(row["quote_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "responded_at": row["responded_at"],
            "outcome": row["outcome"],
            "outcome_at": row["outcome_at"],
            "lost_reason": row["lost_reason"],
        }

    def create(self, session_id: str, listing_id: Any, request: Any, quote: Any, *, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
        if not isinstance(session_id, str) or not _SESSION_RE.fullmatch(session_id):
            raise ValueError("invalid anonymous session")
        listing = str(listing_id or "").strip()
        if not listing or len(listing) > 80:
            raise ValueError("invalid listing ID")
        safe_request = _approved_request(request)
        safe_quote = _approved_quote(quote)
        request_json = json.dumps(safe_request, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        quote_json = json.dumps(safe_quote, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        request_key = hashlib.sha256(request_json.encode("utf-8")).hexdigest()
        current = _time(now if now is not None else self.clock())

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            candidates = connection.execute(
                "SELECT * FROM monthly_public_leads WHERE session_id = ? AND listing_id = ? AND request_key = ? ORDER BY created_at DESC LIMIT 8",
                (session_id, listing, request_key),
            ).fetchall()
            for candidate in candidates:
                created = dt.datetime.fromisoformat(candidate["created_at"])
                if dt.timedelta(0) <= current.astimezone(created.tzinfo) - created <= dt.timedelta(minutes=DEDUPE_MINUTES):
                    return self._row(candidate)
            base_reference = str(self.reference_factory(current)).strip().upper()
            if not _REFERENCE_RE.fullmatch(base_reference):
                raise ValueError("reference factory returned an invalid reference")
            for attempt in range(10):
                suffix = "" if attempt == 0 else "-%d" % (attempt + 1)
                reference = base_reference[: 64 - len(suffix)] + suffix
                if not _REFERENCE_RE.fullmatch(reference):
                    raise ValueError("reference factory returned an invalid reference")
                try:
                    connection.execute(
                        "INSERT INTO monthly_public_leads(reference, session_id, listing_id, request_key, request_json, quote_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (reference, session_id, listing, request_key, request_json, quote_json, current.isoformat(), current.isoformat()),
                    )
                    row = connection.execute("SELECT * FROM monthly_public_leads WHERE reference = ?", (reference,)).fetchone()
                    return self._row(row)
                except sqlite3.IntegrityError:
                    continue
        raise RuntimeError("could not create a unique lead reference")

    def get(self, reference: str) -> Optional[Dict[str, Any]]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM monthly_public_leads WHERE reference = ?", (str(reference).upper(),)).fetchone()
        return self._row(row) if row is not None else None

    def list_all(self) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM monthly_public_leads ORDER BY created_at, reference").fetchall()
        return [self._row(row) for row in rows]

    def count(self) -> int:
        with self._connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM monthly_public_leads").fetchone()[0])

    def mark_response(self, reference: str, *, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
        current_time = _time(now if now is not None else self.clock())
        current = current_time.isoformat()
        reference = str(reference or "").strip().upper()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM monthly_public_leads WHERE reference = ?", (reference,)).fetchone()
            if row is None:
                raise KeyError("unknown lead reference")
            if row["responded_at"] is None:
                created = dt.datetime.fromisoformat(row["created_at"])
                if current_time.astimezone(created.tzinfo) < created:
                    raise ValueError("team response cannot precede lead creation")
                connection.execute(
                    "UPDATE monthly_public_leads SET responded_at = ?, updated_at = ? WHERE reference = ? AND responded_at IS NULL",
                    (current, current, reference),
                )
            row = connection.execute("SELECT * FROM monthly_public_leads WHERE reference = ?", (reference,)).fetchone()
        return self._row(row)

    def set_outcome(self, value: Any, outcome: Optional[str] = None, lost_reason: Optional[str] = None, *, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
        if not isinstance(value, Mapping):
            value = {"lead_reference": value, "outcome": outcome, "lost_reason": lost_reason}
        parsed = parse_outcome(value)
        current_time = _time(now if now is not None else self.clock())
        current = current_time.isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM monthly_public_leads WHERE reference = ?", (parsed["lead_reference"],)).fetchone()
            if row is None:
                raise KeyError("unknown lead reference")
            if row["responded_at"] is None:
                raise ValueError("a lead cannot receive an outcome before a team response")
            wanted_reason = parsed.get("lost_reason")
            if row["outcome"] is not None:
                if row["outcome"] != parsed["outcome"] or row["lost_reason"] != wanted_reason:
                    raise ValueError("lead outcome is already final")
                return self._row(row)
            responded = dt.datetime.fromisoformat(row["responded_at"])
            if current_time.astimezone(responded.tzinfo) < responded:
                raise ValueError("lead outcome cannot precede team response")
            connection.execute(
                "UPDATE monthly_public_leads SET outcome = ?, lost_reason = ?, outcome_at = ?, updated_at = ? WHERE reference = ?",
                (parsed["outcome"], wanted_reason, current, current, parsed["lead_reference"]),
            )
            row = connection.execute("SELECT * FROM monthly_public_leads WHERE reference = ?", (parsed["lead_reference"],)).fetchone()
        return self._row(row)


def _amount(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return format(value, ",")


def _term_labels(quote: Mapping[str, Any], key: str) -> str:
    item = quote.get(key)
    if not isinstance(item, Mapping):
        return "—"
    ar = str(item.get("label_ar") or "").strip()
    en = str(item.get("label_en") or "").strip()
    return " / ".join(value for value in (ar, en) if value) or "—"


def _deposit_label(quote: Mapping[str, Any]) -> str:
    deposit = quote.get("deposit")
    if not isinstance(deposit, Mapping):
        return "—"
    amount = deposit.get("amount_sar")
    return "SAR %s — %s / %s" % (
        _amount(amount) if amount is not None else "—",
        deposit.get("refund_ar") or "—",
        deposit.get("refund_en") or "—",
    )


def _payment_labels(quote: Mapping[str, Any]) -> str:
    methods = quote.get("payment_methods")
    if not isinstance(methods, (list, tuple)):
        return "—"
    labels = []
    for item in methods:
        if isinstance(item, Mapping):
            labels.append(" / ".join(str(item.get(key) or "").strip() for key in ("ar", "en") if item.get(key)))
    return ", ".join(value for value in labels if value) or "—"


def build_whatsapp_handoff(
    store: LeadStore,
    settings: MonthlySettings,
    session_id: str,
    listing: Mapping[str, Any],
    request: Mapping[str, Any],
    quote: Mapping[str, Any],
    *,
    analytics: Any = None,
    now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    """Create an anonymous lead and a bilingual pre-filled WhatsApp URL."""

    current = _time(now if now is not None else store.clock())
    window = response_window(settings, current)
    if not settings.whatsapp_number:
        return {
            "ok": False,
            "blocked": True,
            "code": "whatsapp_not_configured",
            "message_ar": "تعذر تجهيز واتساب حتى يكتمل إعداد رقم عوجا.",
            "message_en": "WhatsApp handoff is blocked until Ouja's number is configured.",
            "response_window": window,
        }
    listing_id = str(listing.get("id") or "").strip()
    lead = store.create(session_id, listing_id, request, quote, now=current)
    request = lead["request"]
    quote = lead["quote"]
    place = request.get("place") if isinstance(request.get("place"), Mapping) else {}
    place_label = str(place.get("label") or listing.get("neighborhood_ar") or listing.get("neighborhood_en") or "—")
    neighborhood = " / ".join(
        value for value in (str(listing.get("neighborhood_ar") or "").strip(), str(listing.get("neighborhood_en") or "").strip()) if value
    ) or "—"
    included = ", ".join(str(item) for item in quote.get("included") or ()) or "—"
    duration = quote.get("months") or request.get("duration_months") or quote.get("duration_days") or request.get("duration_days") or "—"
    duration_unit = "months / أشهر" if quote.get("months") or request.get("duration_months") else "days / أيام"
    move_in = quote.get("move_in") or request.get("move_in") or "—"
    move_out = quote.get("move_out") or request.get("move_out") or "—"
    lines = (
        "طلب سكن شهري جديد / New monthly-stay request",
        "الشقة / Listing: %s | %s | ID %s" % (listing.get("name_ar") or "—", listing.get("name_en") or "—", listing_id),
        "التواريخ / Dates: %s → %s (%s %s)" % (move_in, move_out, duration, duration_unit),
        "المقيمون / Residents: %s" % (request.get("residents") or "—"),
        "الغرض / Purpose: %s" % (request.get("purpose") or "—"),
        "ترتيب النوم / Sleeping: %s" % (request.get("sleeping") or "—"),
        "مرونة التواريخ / Date flexibility: %s" % (request.get("flexibility") or "—"),
        "الوجهة أو الحي المعتمد / Approved destination or neighborhood: %s | %s" % (place_label, neighborhood),
        "السعر الشهري المعروض / Displayed monthly price: SAR %s" % _amount(quote.get("monthly_rate_sar", "—")),
        "الإجمالي المعروض / Displayed total price: SAR %s" % _amount(quote.get("stay_total_sar", "—")),
        "المشمول / Included: %s" % included,
        "المتغيرات / Variable items — utilities: %s; cleaning: %s" % (_term_labels(quote, "utilities"), _term_labels(quote, "cleaning")),
        "التأمين المعروض / Displayed deposit terms: %s" % _deposit_label(quote),
        "طرق الدفع المعروضة / Displayed payment methods: %s" % _payment_labels(quote),
        "نوع العقد / Contract status: %s" % (
            (quote.get("preliminary_label_ar") or "") + " / " + (quote.get("preliminary_label_en") or "")
            if quote.get("preliminary_contract")
            else "standard / قياسي"
        ),
        "مرجع الطلب / Lead reference: %s" % lead["reference"],
        "فضلاً أكدوا التوفر والإجمالي والتأمين وشروط العقد. / Please confirm availability, total, deposit, and contract terms.",
        "%s / %s" % (window["message_ar"], window["message_en"]),
    )
    message = "\n".join(lines)
    recorded = None
    if analytics is not None:
        try:
            analytics.record_lifecycle("lead_created", session_id, lead["reference"], now=current)
            recorded = True
        except Exception:
            recorded = False
    return {
        "ok": True,
        "blocked": False,
        "lead_reference": lead["reference"],
        "message": message,
        "url": "https://wa.me/%s?text=%s" % (settings.whatsapp_number, url_quote(message, safe="")),
        "response_window": window,
        "analytics_recorded": recorded,
    }
