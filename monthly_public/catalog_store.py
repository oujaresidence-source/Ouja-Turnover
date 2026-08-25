"""Revision-safe persistence for monthly listing approvals.

The store keeps staff drafts separate from customer-approved records.  It uses
short SQLite connections and rollback journaling so it is safe on the mounted
application volume.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional


_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_ACTOR_MAX = 80


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class RevisionConflict(ValueError):
    """Raised when a draft or approval does not target the current revision."""

    def __init__(self, expected: int, current: int) -> None:
        super().__init__("stale revision: expected %d, current %d" % (expected, current))
        self.expected = expected
        self.current = current


def _canonical_json(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise ValueError("record value must be a mapping")
    try:
        return json.dumps(
            dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as error:
        raise ValueError("record value must be JSON serializable") from error


def _decoded(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("stored record must be an object")
    return decoded


def _record_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not _RECORD_ID.fullmatch(text):
        raise ValueError("invalid %s" % field)
    return text


def _revision(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("revision must be a non-negative integer")
    return value


def _actor(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("actor is required")
    text = value.strip()
    if not text or len(text) > _ACTOR_MAX or any(ord(char) < 32 for char in text):
        raise ValueError("actor is invalid")
    return text


class CatalogStore:
    """Short-connection SQLite store for monthly catalog review records."""

    def __init__(
        self,
        path: Any = "monthly_catalog.sqlite3",
        clock: Callable[[], dt.datetime] = _utc_now,
    ) -> None:
        self.path = Path(path)
        self.clock = clock
        self._initialize()

    def _now(self) -> str:
        value = self.clock()
        if not isinstance(value, dt.datetime):
            raise TypeError("clock must return a datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value.isoformat()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write(self):
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS monthly_catalog_profiles (
                    listing_id TEXT PRIMARY KEY,
                    draft_json TEXT,
                    approved_json TEXT,
                    draft_revision INTEGER NOT NULL DEFAULT 0,
                    approved_revision INTEGER NOT NULL DEFAULT 0,
                    draft_updated_at TEXT,
                    draft_updated_by TEXT,
                    approved_at TEXT,
                    approved_by TEXT
                );

                CREATE TABLE IF NOT EXISTS monthly_catalog_settings (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    draft_json TEXT,
                    approved_json TEXT,
                    draft_revision INTEGER NOT NULL DEFAULT 0,
                    approved_revision INTEGER NOT NULL DEFAULT 0,
                    draft_updated_at TEXT,
                    draft_updated_by TEXT,
                    approved_at TEXT,
                    approved_by TEXT
                );

                CREATE TABLE IF NOT EXISTS monthly_catalog_places (
                    place_id TEXT PRIMARY KEY,
                    draft_json TEXT,
                    approved_json TEXT,
                    draft_revision INTEGER NOT NULL DEFAULT 0,
                    approved_revision INTEGER NOT NULL DEFAULT 0,
                    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
                    draft_updated_at TEXT,
                    draft_updated_by TEXT,
                    approved_at TEXT,
                    approved_by TEXT
                );

                CREATE TABLE IF NOT EXISTS monthly_catalog_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    action TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    changed_fields_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_monthly_catalog_audit_target
                ON monthly_catalog_audit(target, id DESC);
                """
            )
            connection.commit()

    @staticmethod
    def _profile_result(listing_id: str, row: Optional[sqlite3.Row]) -> Dict[str, Any]:
        if row is None:
            return {
                "listing_id": listing_id,
                "draft": None,
                "approved": None,
                "draft_revision": 0,
                "approved_revision": 0,
                "draft_updated_at": None,
                "draft_updated_by": None,
                "approved_at": None,
                "approved_by": None,
            }
        return {
            "listing_id": listing_id,
            "draft": _decoded(row["draft_json"]),
            "approved": _decoded(row["approved_json"]),
            "draft_revision": row["draft_revision"],
            "approved_revision": row["approved_revision"],
            "draft_updated_at": row["draft_updated_at"],
            "draft_updated_by": row["draft_updated_by"],
            "approved_at": row["approved_at"],
            "approved_by": row["approved_by"],
        }

    @staticmethod
    def _settings_result(row: Optional[sqlite3.Row]) -> Dict[str, Any]:
        if row is None:
            return {
                "draft": None,
                "approved": None,
                "draft_revision": 0,
                "approved_revision": 0,
                "draft_updated_at": None,
                "draft_updated_by": None,
                "approved_at": None,
                "approved_by": None,
            }
        return {
            "draft": _decoded(row["draft_json"]),
            "approved": _decoded(row["approved_json"]),
            "draft_revision": row["draft_revision"],
            "approved_revision": row["approved_revision"],
            "draft_updated_at": row["draft_updated_at"],
            "draft_updated_by": row["draft_updated_by"],
            "approved_at": row["approved_at"],
            "approved_by": row["approved_by"],
        }

    @staticmethod
    def _place_result(place_id: str, row: Optional[sqlite3.Row]) -> Dict[str, Any]:
        result = CatalogStore._profile_result(place_id, row)
        result["place_id"] = result.pop("listing_id")
        result["active"] = bool(row["active"]) if row is not None else False
        return result

    @staticmethod
    def _fields(value: Mapping[str, Any]) -> list[str]:
        return sorted(str(field) for field in value)

    @staticmethod
    def _audit_insert(
        connection: sqlite3.Connection,
        target: str,
        action: str,
        revision: int,
        fields: list[str],
        actor: str,
        occurred_at: str,
    ) -> None:
        connection.execute(
            "INSERT INTO monthly_catalog_audit(target, action, revision, changed_fields_json, actor, occurred_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                target,
                action,
                revision,
                json.dumps(fields, ensure_ascii=True, separators=(",", ":")),
                actor,
                occurred_at,
            ),
        )

    def profile(self, listing_id: str) -> Dict[str, Any]:
        key = _record_id(listing_id, "listing ID")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_catalog_profiles WHERE listing_id = ?", (key,)
            ).fetchone()
        return self._profile_result(key, row)

    def save_profile_draft(
        self,
        listing_id: str,
        value: Mapping[str, Any],
        expected_revision: int,
        actor: str,
    ) -> Dict[str, Any]:
        key = _record_id(listing_id, "listing ID")
        expected = _revision(expected_revision)
        by = _actor(actor)
        payload = _canonical_json(value)
        fields = self._fields(value)
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_catalog_profiles WHERE listing_id = ?", (key,)
            ).fetchone()
            current = row["draft_revision"] if row is not None else 0
            if expected != current:
                raise RevisionConflict(expected, current)
            next_revision = current + 1
            connection.execute(
                """
                INSERT INTO monthly_catalog_profiles(
                    listing_id, draft_json, draft_revision, draft_updated_at, draft_updated_by
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(listing_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    draft_revision=excluded.draft_revision,
                    draft_updated_at=excluded.draft_updated_at,
                    draft_updated_by=excluded.draft_updated_by
                """,
                (key, payload, next_revision, occurred, by),
            )
            self._audit_insert(
                connection,
                "listing:%s" % key,
                "profile_draft_saved",
                next_revision,
                fields,
                by,
                occurred,
            )
            result_row = connection.execute(
                "SELECT * FROM monthly_catalog_profiles WHERE listing_id = ?", (key,)
            ).fetchone()
        return self._profile_result(key, result_row)

    def approve_profile(
        self, listing_id: str, revision: int, actor: str
    ) -> Dict[str, Any]:
        key = _record_id(listing_id, "listing ID")
        requested = _revision(revision)
        by = _actor(actor)
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_catalog_profiles WHERE listing_id = ?", (key,)
            ).fetchone()
            current = row["draft_revision"] if row is not None else 0
            if requested != current or row is None or row["draft_json"] is None:
                raise RevisionConflict(requested, current)
            approved = _decoded(row["draft_json"]) or {}
            connection.execute(
                """
                UPDATE monthly_catalog_profiles
                SET approved_json=draft_json, approved_revision=?, approved_at=?, approved_by=?
                WHERE listing_id=?
                """,
                (requested, occurred, by, key),
            )
            self._audit_insert(
                connection,
                "listing:%s" % key,
                "profile_approved",
                requested,
                self._fields(approved),
                by,
                occurred,
            )
            result_row = connection.execute(
                "SELECT * FROM monthly_catalog_profiles WHERE listing_id = ?", (key,)
            ).fetchone()
        return self._profile_result(key, result_row)

    def approved_profiles(self) -> Dict[str, Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT listing_id, approved_json FROM monthly_catalog_profiles WHERE approved_json IS NOT NULL ORDER BY listing_id"
            ).fetchall()
        return {row["listing_id"]: _decoded(row["approved_json"]) or {} for row in rows}

    def settings(self) -> Dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_catalog_settings WHERE singleton = 1"
            ).fetchone()
        return self._settings_result(row)

    def save_settings_draft(
        self,
        value: Mapping[str, Any],
        expected_revision: int,
        actor: str,
    ) -> Dict[str, Any]:
        expected = _revision(expected_revision)
        by = _actor(actor)
        payload = _canonical_json(value)
        fields = self._fields(value)
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_catalog_settings WHERE singleton = 1"
            ).fetchone()
            current = row["draft_revision"] if row is not None else 0
            if expected != current:
                raise RevisionConflict(expected, current)
            next_revision = current + 1
            connection.execute(
                """
                INSERT INTO monthly_catalog_settings(
                    singleton, draft_json, draft_revision, draft_updated_at, draft_updated_by
                ) VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    draft_revision=excluded.draft_revision,
                    draft_updated_at=excluded.draft_updated_at,
                    draft_updated_by=excluded.draft_updated_by
                """,
                (payload, next_revision, occurred, by),
            )
            self._audit_insert(
                connection,
                "settings",
                "settings_draft_saved",
                next_revision,
                fields,
                by,
                occurred,
            )
            result_row = connection.execute(
                "SELECT * FROM monthly_catalog_settings WHERE singleton = 1"
            ).fetchone()
        return self._settings_result(result_row)

    def approve_settings(self, revision: int, actor: str) -> Dict[str, Any]:
        requested = _revision(revision)
        by = _actor(actor)
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_catalog_settings WHERE singleton = 1"
            ).fetchone()
            current = row["draft_revision"] if row is not None else 0
            if requested != current or row is None or row["draft_json"] is None:
                raise RevisionConflict(requested, current)
            approved = _decoded(row["draft_json"]) or {}
            connection.execute(
                """
                UPDATE monthly_catalog_settings
                SET approved_json=draft_json, approved_revision=?, approved_at=?, approved_by=?
                WHERE singleton=1
                """,
                (requested, occurred, by),
            )
            self._audit_insert(
                connection,
                "settings",
                "settings_approved",
                requested,
                self._fields(approved),
                by,
                occurred,
            )
            result_row = connection.execute(
                "SELECT * FROM monthly_catalog_settings WHERE singleton = 1"
            ).fetchone()
        return self._settings_result(result_row)

    def places(self) -> Dict[str, Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM monthly_catalog_places ORDER BY place_id"
            ).fetchall()
        return {row["place_id"]: self._place_result(row["place_id"], row) for row in rows}

    def save_place_draft(
        self,
        place_id: str,
        value: Mapping[str, Any],
        expected_revision: int,
        actor: str,
    ) -> Dict[str, Any]:
        key = _record_id(place_id, "place ID")
        expected = _revision(expected_revision)
        by = _actor(actor)
        payload = _canonical_json(value)
        fields = self._fields(value)
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_catalog_places WHERE place_id = ?", (key,)
            ).fetchone()
            current = row["draft_revision"] if row is not None else 0
            if expected != current:
                raise RevisionConflict(expected, current)
            next_revision = current + 1
            connection.execute(
                """
                INSERT INTO monthly_catalog_places(
                    place_id, draft_json, draft_revision, draft_updated_at, draft_updated_by
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(place_id) DO UPDATE SET
                    draft_json=excluded.draft_json,
                    draft_revision=excluded.draft_revision,
                    draft_updated_at=excluded.draft_updated_at,
                    draft_updated_by=excluded.draft_updated_by
                """,
                (key, payload, next_revision, occurred, by),
            )
            self._audit_insert(
                connection,
                "place:%s" % key,
                "place_draft_saved",
                next_revision,
                fields,
                by,
                occurred,
            )
            result_row = connection.execute(
                "SELECT * FROM monthly_catalog_places WHERE place_id = ?", (key,)
            ).fetchone()
        return self._place_result(key, result_row)

    def approve_place(
        self, place_id: str, revision: int, active: bool, actor: str
    ) -> Dict[str, Any]:
        key = _record_id(place_id, "place ID")
        requested = _revision(revision)
        if not isinstance(active, bool):
            raise ValueError("active must be a boolean")
        by = _actor(actor)
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_catalog_places WHERE place_id = ?", (key,)
            ).fetchone()
            current = row["draft_revision"] if row is not None else 0
            if requested != current or row is None or row["draft_json"] is None:
                raise RevisionConflict(requested, current)
            approved = _decoded(row["draft_json"]) or {}
            connection.execute(
                """
                UPDATE monthly_catalog_places
                SET approved_json=draft_json, approved_revision=?, active=?, approved_at=?, approved_by=?
                WHERE place_id=?
                """,
                (requested, int(active), occurred, by, key),
            )
            self._audit_insert(
                connection,
                "place:%s" % key,
                "place_approved" if active else "place_deactivated",
                requested,
                self._fields(approved) + ["active"],
                by,
                occurred,
            )
            result_row = connection.execute(
                "SELECT * FROM monthly_catalog_places WHERE place_id = ?", (key,)
            ).fetchone()
        return self._place_result(key, result_row)

    def audit(self, target: Optional[str] = None, limit: int = 100) -> list[Dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("invalid audit limit")
        with self._connection() as connection:
            if target is None:
                rows = connection.execute(
                    "SELECT * FROM monthly_catalog_audit ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                if not isinstance(target, str) or not target.strip() or len(target) > 100:
                    raise ValueError("invalid audit target")
                rows = connection.execute(
                    "SELECT * FROM monthly_catalog_audit WHERE target = ? ORDER BY id DESC LIMIT ?",
                    (target.strip(), limit),
                ).fetchall()
        return [
            {
                "id": row["id"],
                "target": row["target"],
                "action": row["action"],
                "revision": row["revision"],
                "changed_fields": json.loads(row["changed_fields_json"]),
                "actor": row["actor"],
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def probe(self) -> Dict[str, Any]:
        connection = self._connect()
        try:
            journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO monthly_catalog_audit(target, action, revision, changed_fields_json, actor, occurred_at) VALUES ('probe', 'probe', 0, '[]', 'system', ?)",
                (self._now(),),
            )
            connection.rollback()
            return {"ok": True, "journal_mode": str(journal).lower()}
        except Exception as error:
            connection.rollback()
            return {"ok": False, "error": type(error).__name__}
        finally:
            connection.close()


__all__ = ["CatalogStore", "RevisionConflict"]
