"""Privacy-minimising local analytics for the public monthly funnel."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Collection, Dict, Mapping, Optional

from .contracts import (
    LOST_REASONS,
    PRICE_PRIORITIES,
    PUBLIC_EVENT_NAMES,
    PURPOSES,
    TRUSTED_LIFECYCLE_EVENT_NAMES,
    parse_event,
)


_LEAD_REFERENCE = re.compile(r"^[A-Z0-9][A-Z0-9-]{5,63}$")
_LISTING_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_JOURNEY_ID = re.compile(r"^journey_[A-Za-z0-9_-]{22,64}$")
_SHOWCASE_ID = re.compile(r"^showcase_[A-Za-z0-9_-]{2,64}$")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _as_datetime(value: Any) -> dt.datetime:
    if not isinstance(value, dt.datetime):
        raise TypeError("clock must return a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.timezone.utc)
    return value


class AnalyticsStore:
    """A small SQLite event store that opens one connection per operation."""

    def __init__(self, path: Any = "monthly_public_analytics.sqlite3", *, clock=None) -> None:
        self.path = Path(path)
        self.clock = clock or _utc_now
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        # Analytics is best-effort on the conversion path; fail fast on a lock.
        connection = sqlite3.connect(str(self.path), timeout=0.05)
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
                CREATE TABLE IF NOT EXISTS monthly_public_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_name TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    lead_reference TEXT,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL,
                    trusted INTEGER NOT NULL CHECK (trusted IN (0, 1)),
                    UNIQUE(event_name, lead_reference)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_monthly_events_session ON monthly_public_events(session_id, occurred_at)"
            )

    def record(
        self,
        value: Any,
        *,
        session_secret: Any = None,
        allowed_place_ids: Optional[Collection[str]] = None,
        now: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        """Validate a browser-supplied event through the public contract and persist it."""

        event = parse_event(
            value,
            session_secret=session_secret,
            allowed_place_ids=allowed_place_ids,
        )
        occurred = _as_datetime(now if now is not None else self.clock())
        context_json = json.dumps(event["context"], ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT INTO monthly_public_events(event_name, session_id, context_json, occurred_at, trusted) VALUES (?, ?, ?, ?, 0)",
                (event["event"], event["session_id"], context_json, occurred.isoformat()),
            )
        return {
            "id": cursor.lastrowid,
            "event": event["event"],
            "session_id": event["session_id"],
            "context": event["context"],
            "occurred_at": occurred.isoformat(),
        }

    record_public = record

    def record_lead_creation(
        self,
        session_id: str,
        lead_reference: str,
        *,
        listing_id: Optional[str] = None,
        journey_id: Optional[str] = None,
        showcase_id: Optional[str] = None,
        now: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        """Atomically persist the contact click and created-lead lifecycle.

        Navigation to WhatsApp happens only after the server creates a lead, so
        this transaction is the durable conversion boundary.  Retries return
        the original persisted timestamps and reject conflicting identities.
        """

        reference = str(lead_reference or "").strip().upper()
        if not _LEAD_REFERENCE.fullmatch(reference):
            raise ValueError("invalid lead reference")
        if not isinstance(session_id, str) or not session_id.startswith("anon_"):
            raise ValueError("invalid anonymous session")
        normalized_listing: Optional[str] = None
        if listing_id is not None:
            normalized_listing = str(listing_id).strip()
            if not _LISTING_ID.fullmatch(normalized_listing):
                raise ValueError("invalid listing ID")
        normalized_journey: Optional[str] = None
        if journey_id not in (None, ""):
            normalized_journey = str(journey_id).strip()
            if not _JOURNEY_ID.fullmatch(normalized_journey):
                raise ValueError("invalid journey ID")
        normalized_showcase: Optional[str] = None
        if showcase_id not in (None, ""):
            normalized_showcase = str(showcase_id).strip()
            if not _SHOWCASE_ID.fullmatch(normalized_showcase):
                raise ValueError("invalid showcase ID")
        occurred = _as_datetime(now if now is not None else self.clock()).isoformat()
        journey_context = {
            **({"journey_id": normalized_journey} if normalized_journey else {}),
            **({"showcase_id": normalized_showcase} if normalized_showcase else {}),
        }
        expected = [
            (
                "whatsapp_click",
                {
                    **({"listing_id": normalized_listing} if normalized_listing else {}),
                    **journey_context,
                },
            ),
            ("lead_created", journey_context),
        ]
        if normalized_showcase:
            expected.extend(
                [
                    (
                        "showcase_whatsapp_click",
                        {
                            **(
                                {"listing_id": normalized_listing}
                                if normalized_listing
                                else {}
                            ),
                            **journey_context,
                        },
                    ),
                    ("showcase_lead_created", journey_context),
                ]
            )
        result_rows: Dict[str, sqlite3.Row] = {}
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT id, event_name, session_id, context_json, occurred_at FROM monthly_public_events WHERE lead_reference = ? AND trusted = 1 ORDER BY id",
                (reference,),
            ).fetchall()
            if rows and any(row["session_id"] != session_id for row in rows):
                raise ValueError("lead reference belongs to another anonymous session")
            names = {row["event_name"] for row in rows}
            if names and "lead_created" not in names:
                raise ValueError("lead reference has no created-lead lifecycle")
            by_name = {row["event_name"]: row for row in rows}
            for event, context in expected:
                payload = json.dumps(context, sort_keys=True, separators=(",", ":"))
                existing = by_name.get(event)
                if existing is not None:
                    if existing["context_json"] != payload:
                        raise ValueError("trusted lead creation retry conflicts with stored event")
                    result_rows[event] = existing
                    continue
                connection.execute(
                    "INSERT INTO monthly_public_events(event_name, session_id, lead_reference, context_json, occurred_at, trusted) VALUES (?, ?, ?, ?, ?, 1)",
                    (event, session_id, reference, payload, occurred),
                )
                result_rows[event] = connection.execute(
                    "SELECT id, event_name, session_id, context_json, occurred_at FROM monthly_public_events WHERE event_name = ? AND lead_reference = ?",
                    (event, reference),
                ).fetchone()
        return {
            "session_id": session_id,
            "lead_reference": reference,
            "events": [
                {
                    "event": event,
                    "context": json.loads(result_rows[event]["context_json"]),
                    "occurred_at": result_rows[event]["occurred_at"],
                }
                for event, _context in expected
            ],
        }

    def record_lifecycle(
        self,
        event: str,
        session_id: str,
        lead_reference: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
        now: Optional[dt.datetime] = None,
    ) -> Dict[str, Any]:
        """Record a server/staff lifecycle event; this is not a public parser."""

        if event not in TRUSTED_LIFECYCLE_EVENT_NAMES:
            raise ValueError("unsupported trusted lifecycle event")
        reference = str(lead_reference or "").strip().upper()
        if not _LEAD_REFERENCE.fullmatch(reference):
            raise ValueError("invalid lead reference")
        if not isinstance(session_id, str) or not session_id.startswith("anon_"):
            raise ValueError("invalid anonymous session")
        safe_context: Dict[str, Any] = {}
        if event == "lost":
            if (
                not isinstance(context, Mapping)
                or set(context) != {"lost_reason"}
                or context.get("lost_reason") not in LOST_REASONS
            ):
                raise ValueError("lost lifecycle event requires one controlled lost reason")
            safe_context["lost_reason"] = context["lost_reason"]
        elif isinstance(context, Mapping) and "lost_reason" in context:
            raise ValueError("lost reason is only valid for a lost lifecycle event")
        occurred = _as_datetime(now if now is not None else self.clock())
        payload = json.dumps(safe_context, sort_keys=True, separators=(",", ":"))
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT event_name, session_id, context_json, occurred_at FROM monthly_public_events WHERE lead_reference = ? AND trusted = 1 ORDER BY occurred_at, id",
                (reference,),
            ).fetchall()
            existing = next((row for row in rows if row["event_name"] == event), None)
            if existing is not None:
                if existing["session_id"] != session_id or existing["context_json"] != payload:
                    raise ValueError("trusted lifecycle retry conflicts with stored event")
                return {
                    "event": event,
                    "session_id": session_id,
                    "lead_reference": reference,
                    "context": json.loads(existing["context_json"]),
                    "occurred_at": existing["occurred_at"],
                }
            if rows and any(row["session_id"] != session_id for row in rows):
                raise ValueError("lead reference belongs to another anonymous session")
            names = {row["event_name"] for row in rows}
            if event == "lead_created":
                if rows:
                    raise ValueError("lead creation must be the first lifecycle event")
            elif event == "showcase_lead_created":
                if "lead_created" not in names or {"booked", "lost"}.intersection(names):
                    raise ValueError("showcase lead creation requires an open created lead")
            elif event == "team_response":
                if "lead_created" not in names or {"booked", "lost"}.intersection(names):
                    raise ValueError("team response requires an open created lead")
            else:
                if "team_response" not in names or {"booked", "lost"}.intersection(names):
                    raise ValueError("outcome requires one responded lead without a final outcome")
            if rows:
                previous = dt.datetime.fromisoformat(rows[-1]["occurred_at"])
                if occurred.astimezone(previous.tzinfo) < previous:
                    raise ValueError("lifecycle timestamps cannot move backwards")
            connection.execute(
                "INSERT INTO monthly_public_events(event_name, session_id, lead_reference, context_json, occurred_at, trusted) VALUES (?, ?, ?, ?, ?, 1)",
                (event, session_id, reference, payload, occurred.isoformat()),
            )
        return {
            "event": event,
            "session_id": session_id,
            "lead_reference": reference,
            "context": safe_context,
            "occurred_at": occurred.isoformat(),
        }

    def events(self) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT event_name, session_id, lead_reference, context_json, occurred_at, trusted FROM monthly_public_events ORDER BY id"
            ).fetchall()
        return [
            {
                "event": row["event_name"],
                "session_id": row["session_id"],
                "lead_reference": row["lead_reference"],
                "context": json.loads(row["context_json"]),
                "occurred_at": row["occurred_at"],
                "trusted": bool(row["trusted"]),
            }
            for row in rows
        ]

    def lead_journey(self, session_id: str, lead_reference: str) -> list[Dict[str, Any]]:
        """Return a narrow staff timeline without exposing its correlation key."""

        reference = str(lead_reference or "").strip().upper()
        if not _LEAD_REFERENCE.fullmatch(reference):
            raise ValueError("invalid lead reference")
        if not isinstance(session_id, str) or not session_id.startswith("anon_"):
            raise ValueError("invalid anonymous session")
        allowed = {
            "entry_route_choice",
            "price_priority_selected",
            "matcher_completion",
            "no_match",
            "result_impression",
            "listing_view",
            "review_section_view",
            "price_breakdown_open",
            "whatsapp_click",
        }
        with self._connection() as connection:
            target = connection.execute(
                """
                SELECT id, context_json FROM monthly_public_events
                WHERE session_id = ? AND lead_reference = ?
                  AND event_name = 'lead_created' AND trusted = 1
                ORDER BY id LIMIT 1
                """,
                (session_id, reference),
            ).fetchone()
            if target is None:
                return []
            try:
                target_context = json.loads(target["context_json"])
            except (TypeError, ValueError):
                target_context = {}
            journey_id = target_context.get("journey_id")
            if not isinstance(journey_id, str) or not _JOURNEY_ID.fullmatch(journey_id):
                journey_id = None
            rows = connection.execute(
                """
                SELECT event_name, lead_reference, context_json, occurred_at
                FROM monthly_public_events
                WHERE session_id = ?
                  AND id <= ?
                ORDER BY id
                """,
                (session_id, target["id"]),
            ).fetchall()
        journey = []
        for row in rows:
            event = row["event_name"]
            if event not in allowed:
                continue
            try:
                context = json.loads(row["context_json"])
            except (TypeError, ValueError):
                context = {}
            if row["lead_reference"] is not None and row["lead_reference"] != reference:
                continue
            if journey_id is not None:
                if context.get("journey_id") != journey_id:
                    continue
            elif row["lead_reference"] != reference:
                # Historical leads without a journey ID are deliberately kept
                # narrow rather than inferred from event insertion order.
                continue
            item: Dict[str, Any] = {
                "event": event,
                "occurred_at": row["occurred_at"],
            }
            if event == "entry_route_choice" and context.get("entry_route") in ("guided", "browse"):
                item["entry_route"] = context["entry_route"]
            elif event == "matcher_completion":
                if context.get("purpose") in PURPOSES:
                    item["purpose"] = context["purpose"]
                if isinstance(context.get("place_id"), str):
                    item["place_id"] = context["place_id"]
                if isinstance(context.get("duration_months"), int):
                    item["duration_months"] = context["duration_months"]
                if context.get("duration_band") in ("1_month", "2_3_months", "4_6_months"):
                    item["duration_band"] = context["duration_band"]
                if context.get("price_priority") in PRICE_PRIORITIES:
                    item["price_priority"] = context["price_priority"]
            elif event == "price_priority_selected":
                if context.get("price_priority") in PRICE_PRIORITIES:
                    item["price_priority"] = context["price_priority"]
            elif event == "result_impression":
                if isinstance(context.get("listing_id"), str):
                    item["listing_id"] = context["listing_id"]
                if isinstance(context.get("rank"), int):
                    item["rank"] = context["rank"]
            elif event in (
                "listing_view",
                "review_section_view",
                "price_breakdown_open",
                "whatsapp_click",
                "showcase_view",
                "showcase_listing_impression",
                "showcase_listing_view",
                "showcase_whatsapp_click",
                "showcase_lead_created",
            ):
                if isinstance(context.get("listing_id"), str):
                    item["listing_id"] = context["listing_id"]
                if isinstance(context.get("showcase_id"), str):
                    item["showcase_id"] = context["showcase_id"]
            journey.append(item)
        return journey

    def health(self) -> Dict[str, Any]:
        try:
            with self._connection() as connection:
                count = connection.execute("SELECT COUNT(*) FROM monthly_public_events").fetchone()[0]
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO monthly_public_events(event_name, session_id, context_json, occurred_at, trusted) VALUES (?, ?, '{}', ?, 0)",
                    ("landing_view", "anon_health_probe", _as_datetime(self.clock()).isoformat()),
                )
                connection.rollback()
            return {
                "healthy": True,
                "write_probe": True,
                "event_count": int(count),
                "error": None,
            }
        except Exception as error:
            return {
                "healthy": False,
                "write_probe": False,
                "event_count": None,
                "error": str(error),
            }


# ``EventStore`` is the product-facing name; retain ``AnalyticsStore`` as the
# descriptive compatibility name used by health/reporting callers.
EventStore = AnalyticsStore


def _duration_band(value: Mapping[str, Any]) -> Optional[str]:
    supplied = value.get("duration_band")
    if supplied in ("1_month", "2_3_months", "4_6_months"):
        return supplied
    months = value.get("duration_months")
    if isinstance(months, int) and not isinstance(months, bool) and 1 <= months <= 6:
        if months == 1:
            return "1_month"
        return "2_3_months" if months <= 3 else "4_6_months"
    days = value.get("duration_days")
    if isinstance(days, int) and not isinstance(days, bool) and days > 0:
        if days <= 31:
            return "1_month"
        return "2_3_months" if days <= 92 else "4_6_months"
    return None


def _conversion(numerator: int, denominator: int) -> Optional[float]:
    return round(float(numerator) / denominator, 4) if denominator else None


def funnel_summary(analytics: AnalyticsStore, leads: Any) -> Dict[str, Any]:
    """Summarise anonymous stages and linked operational outcomes without PII."""

    events = analytics.events()
    stage_names = PUBLIC_EVENT_NAMES + TRUSTED_LIFECYCLE_EVENT_NAMES
    stages = {name: 0 for name in stage_names}
    stage_keys = {name: set() for name in stage_names}
    sessions: Dict[str, Dict[str, Any]] = {}
    profiles: Dict[str, Dict[str, str]] = {}
    for event in events:
        name = event["event"]
        key = event["lead_reference"] or event["session_id"]
        if name in stage_keys:
            stage_keys[name].add(key)
        session = sessions.setdefault(event["session_id"], {"stages": [], "lead_references": []})
        if name not in session["stages"]:
            session["stages"].append(name)
        reference = event["lead_reference"]
        if reference and reference not in session["lead_references"]:
            session["lead_references"].append(reference)
        context = event.get("context")
        if isinstance(context, Mapping):
            profile = profiles.setdefault(event["session_id"], {})
            if context.get("purpose") in PURPOSES:
                profile["purpose"] = context["purpose"]
            if context.get("price_priority") in PRICE_PRIORITIES:
                profile["price_priority"] = context["price_priority"]
            if isinstance(context.get("place_id"), str) and context["place_id"]:
                profile["place_id"] = context["place_id"]
            band = _duration_band(context)
            if band is not None:
                profile["duration_band"] = band
            if context.get("question") == "purpose" and context.get("answer") in PURPOSES:
                profile["purpose"] = context["answer"]
            if context.get("question") == "price_priority" and context.get("answer") in PRICE_PRIORITIES:
                profile["price_priority"] = context["answer"]
            if context.get("question") == "place" and isinstance(context.get("answer"), str):
                profile["place_id"] = context["answer"]
    for name, keys in stage_keys.items():
        stages[name] = len(keys)

    lead_rows = leads.list_all()
    for row in lead_rows:
        session = sessions.setdefault(
            row["session_id"], {"stages": [], "lead_references": []}
        )
        if row["reference"] not in session["lead_references"]:
            session["lead_references"].append(row["reference"])
        request = row.get("request")
        if isinstance(request, Mapping):
            profile = profiles.setdefault(row["session_id"], {})
            if request.get("purpose") in PURPOSES:
                profile["purpose"] = request["purpose"]
            if request.get("price_priority") in PRICE_PRIORITIES:
                profile["price_priority"] = request["price_priority"]
            place = request.get("place")
            if isinstance(place, Mapping) and isinstance(place.get("id"), str):
                profile["place_id"] = place["id"]
            band = _duration_band(request)
            if band is not None:
                profile["duration_band"] = band
    responded = [row for row in lead_rows if row["responded_at"]]
    response_minutes = []
    for row in responded:
        created = dt.datetime.fromisoformat(row["created_at"])
        response = dt.datetime.fromisoformat(row["responded_at"])
        response_minutes.append((response - created).total_seconds() / 60.0)
    lost_reasons = {reason: 0 for reason in LOST_REASONS}
    for row in lead_rows:
        if row["outcome"] == "lost" and row["lost_reason"] in lost_reasons:
            lost_reasons[row["lost_reason"]] += 1
    purpose_counts = {purpose: 0 for purpose in PURPOSES}
    place_counts: Dict[str, int] = {}
    duration_bands = {band: 0 for band in ("1_month", "2_3_months", "4_6_months")}
    price_priorities = {priority: 0 for priority in PRICE_PRIORITIES}
    for profile in profiles.values():
        purpose = profile.get("purpose")
        if purpose in purpose_counts:
            purpose_counts[purpose] += 1
        place_id = profile.get("place_id")
        if place_id:
            place_counts[place_id] = place_counts.get(place_id, 0) + 1
        band = profile.get("duration_band")
        if band in duration_bands:
            duration_bands[band] += 1
        priority = profile.get("price_priority")
        if priority in price_priorities:
            price_priorities[priority] += 1
    common_purposes = [
        {"purpose": purpose, "count": count}
        for purpose, count in sorted(
            purpose_counts.items(), key=lambda item: (-item[1], item[0])
        )
        if count
    ]
    requested_places = [
        {"place_id": place_id, "count": count}
        for place_id, count in sorted(
            place_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    lead_sessions = {row["session_id"] for row in lead_rows}
    booked = sum(row["outcome"] == "booked" for row in lead_rows)
    discount_classified = [
        row
        for row in lead_rows
        if isinstance(row.get("discount_requested"), bool)
    ]
    discount_requested = sum(
        row["discount_requested"] is True for row in discount_classified
    )
    return {
        "stages": stages,
        "leads": {
            "created": len(lead_rows),
            "responded": len(responded),
            "booked": booked,
            "lost": sum(row["outcome"] == "lost" for row in lead_rows),
        },
        "response_time_minutes": {
            "average": round(sum(response_minutes) / len(response_minutes), 2) if response_minutes else None,
            "count": len(response_minutes),
        },
        "lost_reasons": lost_reasons,
        "common_purposes": common_purposes,
        "requested_places": requested_places,
        "duration_bands": duration_bands,
        "price_priorities": price_priorities,
        "conversion_rates": {
            "matcher_to_lead": _conversion(
                len(lead_sessions.intersection(stage_keys["matcher_completion"])),
                stages["matcher_completion"],
            ),
            "lead_to_response": _conversion(len(responded), len(lead_rows)),
            "lead_to_booking": _conversion(booked, len(lead_rows)),
            "response_to_booking": _conversion(booked, len(responded)),
        },
        "discount_request_rate": {
            "status": "tracked" if discount_classified else "not_tracked",
            "count": discount_requested,
            "numerator": discount_requested,
            "denominator": len(discount_classified),
            "rate": _conversion(discount_requested, len(discount_classified)),
        },
        "sessions": sessions,
    }
