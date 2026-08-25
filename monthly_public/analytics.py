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
    PUBLIC_EVENT_NAMES,
    TRUSTED_LIFECYCLE_EVENT_NAMES,
    parse_event,
)


_LEAD_REFERENCE = re.compile(r"^[A-Z0-9][A-Z0-9-]{5,63}$")


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

    def health(self) -> Dict[str, Any]:
        try:
            with self._connection() as connection:
                count = connection.execute("SELECT COUNT(*) FROM monthly_public_events").fetchone()[0]
            return {"healthy": True, "event_count": int(count), "error": None}
        except sqlite3.Error as error:
            return {"healthy": False, "event_count": None, "error": str(error)}


# ``EventStore`` is the product-facing name; retain ``AnalyticsStore`` as the
# descriptive compatibility name used by health/reporting callers.
EventStore = AnalyticsStore


def funnel_summary(analytics: AnalyticsStore, leads: Any) -> Dict[str, Any]:
    """Summarise anonymous stages and linked operational outcomes without PII."""

    events = analytics.events()
    stage_names = PUBLIC_EVENT_NAMES + TRUSTED_LIFECYCLE_EVENT_NAMES
    stages = {name: 0 for name in stage_names}
    stage_keys = {name: set() for name in stage_names}
    sessions: Dict[str, Dict[str, Any]] = {}
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
    for name, keys in stage_keys.items():
        stages[name] = len(keys)

    lead_rows = leads.list_all()
    for row in lead_rows:
        session = sessions.setdefault(
            row["session_id"], {"stages": [], "lead_references": []}
        )
        if row["reference"] not in session["lead_references"]:
            session["lead_references"].append(row["reference"])
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
    return {
        "stages": stages,
        "leads": {
            "created": len(lead_rows),
            "responded": len(responded),
            "booked": sum(row["outcome"] == "booked" for row in lead_rows),
            "lost": sum(row["outcome"] == "lost" for row in lead_rows),
        },
        "response_time_minutes": {
            "average": round(sum(response_minutes) / len(response_minutes), 2) if response_minutes else None,
            "count": len(response_minutes),
        },
        "lost_reasons": lost_reasons,
        "sessions": sessions,
    }
