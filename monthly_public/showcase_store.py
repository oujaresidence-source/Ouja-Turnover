"""Revision-safe, non-destructive storage for monthly showcase groups."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional


_GROUP_ID_RE = re.compile(r"^showcase_[A-Za-z0-9_-]{2,64}$")
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ACTOR_MAX = 80


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class RevisionConflict(ValueError):
    """The staff screen tried to change a stale record."""

    def __init__(self, expected: int, current: int) -> None:
        super().__init__("stale revision: expected %d, current %d" % (expected, current))
        self.expected = expected
        self.current = current


class ImmutableShowcaseSlug(ValueError):
    """A permanent public URL cannot be renamed after approval."""


class DuplicateShowcaseSlug(ValueError):
    """Another approved group already owns the requested URL."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise ValueError("showcase value must be a mapping")
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("showcase value must be JSON serializable") from error


def _decoded(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("stored showcase must be an object")
    return decoded


def _group_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _GROUP_ID_RE.fullmatch(text):
        raise ValueError("invalid showcase group ID")
    return text


def _slug(value: Any) -> str:
    text = str(value or "").strip()
    if not _SLUG_RE.fullmatch(text):
        raise ValueError("invalid showcase slug")
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


class ShowcaseStore:
    """Short-connection SQLite store with separate draft and approved states."""

    def __init__(
        self,
        path: Any = "monthly_showcases.sqlite3",
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
                CREATE TABLE IF NOT EXISTS monthly_showcase_groups (
                    group_id TEXT PRIMARY KEY,
                    draft_slug TEXT,
                    approved_slug TEXT UNIQUE,
                    draft_json TEXT,
                    approved_json TEXT,
                    draft_revision INTEGER NOT NULL DEFAULT 0,
                    approved_revision INTEGER NOT NULL DEFAULT 0,
                    draft_updated_at TEXT,
                    draft_updated_by TEXT,
                    approved_at TEXT,
                    approved_by TEXT
                );

                CREATE TABLE IF NOT EXISTS monthly_showcase_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    changed_fields_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_monthly_showcase_audit
                ON monthly_showcase_audit(group_id, id DESC);
                """
            )
            connection.commit()

    @staticmethod
    def _result(group_id: str, row: Optional[sqlite3.Row]) -> Dict[str, Any]:
        if row is None:
            return {
                "group_id": group_id,
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
            "group_id": group_id,
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
    def _audit_insert(
        connection: sqlite3.Connection,
        group_id: str,
        action: str,
        revision: int,
        fields: list[str],
        actor: str,
        occurred_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO monthly_showcase_audit(
                group_id, action, revision, changed_fields_json, actor, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                group_id,
                action,
                revision,
                json.dumps(fields, ensure_ascii=True, separators=(",", ":")),
                actor,
                occurred_at,
            ),
        )

    def record(self, group_id: Any) -> Dict[str, Any]:
        key = _group_id(group_id)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_showcase_groups WHERE group_id = ?",
                (key,),
            ).fetchone()
        return self._result(key, row)

    def list_records(self) -> list[Dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM monthly_showcase_groups ORDER BY group_id"
            ).fetchall()
        return [self._result(row["group_id"], row) for row in rows]

    def by_approved_slug(self, slug: Any) -> Optional[Dict[str, Any]]:
        key = _slug(slug)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_showcase_groups WHERE approved_slug = ?",
                (key,),
            ).fetchone()
        return self._result(row["group_id"], row) if row is not None else None

    def save_draft(
        self,
        group_id: Any,
        value: Mapping[str, Any],
        expected_revision: Any,
        actor: Any,
    ) -> Dict[str, Any]:
        key = _group_id(group_id)
        expected = _revision(expected_revision)
        by = _actor(actor)
        payload = _canonical_json(value)
        slug = _slug(value.get("slug"))
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_showcase_groups WHERE group_id = ?",
                (key,),
            ).fetchone()
            current = row["draft_revision"] if row is not None else 0
            if current != expected:
                raise RevisionConflict(expected, current)
            if row is not None and row["approved_slug"] and row["approved_slug"] != slug:
                raise ImmutableShowcaseSlug("approved showcase URLs are permanent")
            next_revision = current + 1
            connection.execute(
                """
                INSERT INTO monthly_showcase_groups(
                    group_id, draft_slug, draft_json, draft_revision,
                    draft_updated_at, draft_updated_by
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(group_id) DO UPDATE SET
                    draft_slug=excluded.draft_slug,
                    draft_json=excluded.draft_json,
                    draft_revision=excluded.draft_revision,
                    draft_updated_at=excluded.draft_updated_at,
                    draft_updated_by=excluded.draft_updated_by
                """,
                (key, slug, payload, next_revision, occurred, by),
            )
            self._audit_insert(
                connection,
                key,
                "draft_saved",
                next_revision,
                sorted(str(field) for field in value),
                by,
                occurred,
            )
            saved = connection.execute(
                "SELECT * FROM monthly_showcase_groups WHERE group_id = ?",
                (key,),
            ).fetchone()
        return self._result(key, saved)

    def approve(
        self,
        group_id: Any,
        draft_revision: Any,
        actor: Any,
    ) -> Dict[str, Any]:
        key = _group_id(group_id)
        requested = _revision(draft_revision)
        by = _actor(actor)
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_showcase_groups WHERE group_id = ?",
                (key,),
            ).fetchone()
            current = row["draft_revision"] if row is not None else 0
            if row is None or row["draft_json"] is None or requested != current:
                raise RevisionConflict(requested, current)
            approved_slug = row["approved_slug"]
            if approved_slug and approved_slug != row["draft_slug"]:
                raise ImmutableShowcaseSlug("approved showcase URLs are permanent")
            owner = connection.execute(
                "SELECT group_id FROM monthly_showcase_groups WHERE approved_slug = ? AND group_id != ?",
                (row["draft_slug"], key),
            ).fetchone()
            if owner is not None:
                raise DuplicateShowcaseSlug("approved showcase URL is already in use")
            approved = _decoded(row["draft_json"]) or {}
            next_revision = row["approved_revision"] + 1
            try:
                connection.execute(
                    """
                    UPDATE monthly_showcase_groups
                    SET approved_slug=draft_slug,
                        approved_json=draft_json,
                        approved_revision=?,
                        approved_at=?,
                        approved_by=?
                    WHERE group_id=?
                    """,
                    (next_revision, occurred, by, key),
                )
            except sqlite3.IntegrityError as error:
                raise DuplicateShowcaseSlug(
                    "approved showcase URL is already in use"
                ) from error
            self._audit_insert(
                connection,
                key,
                "approved",
                next_revision,
                sorted(str(field) for field in approved),
                by,
                occurred,
            )
            saved = connection.execute(
                "SELECT * FROM monthly_showcase_groups WHERE group_id = ?",
                (key,),
            ).fetchone()
        return self._result(key, saved)

    def set_price_enabled(
        self,
        group_id: Any,
        enabled: Any,
        approved_revision: Any,
        actor: Any,
    ) -> Dict[str, Any]:
        key = _group_id(group_id)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        expected = _revision(approved_revision)
        by = _actor(actor)
        occurred = self._now()
        with self._write() as connection:
            row = connection.execute(
                "SELECT * FROM monthly_showcase_groups WHERE group_id = ?",
                (key,),
            ).fetchone()
            current = row["approved_revision"] if row is not None else 0
            if row is None or row["approved_json"] is None or expected != current:
                raise RevisionConflict(expected, current)
            approved = _decoded(row["approved_json"]) or {}
            if enabled and approved.get("fixed_monthly_rate_sar") is None:
                raise ValueError("fixed monthly price is required before enabling")
            approved["fixed_price_enabled"] = enabled
            next_revision = current + 1
            connection.execute(
                """
                UPDATE monthly_showcase_groups
                SET approved_json=?, approved_revision=?, approved_at=?, approved_by=?
                WHERE group_id=?
                """,
                (
                    _canonical_json(approved),
                    next_revision,
                    occurred,
                    by,
                    key,
                ),
            )
            self._audit_insert(
                connection,
                key,
                "price_enabled" if enabled else "price_disabled",
                next_revision,
                ["fixed_price_enabled"],
                by,
                occurred,
            )
            saved = connection.execute(
                "SELECT * FROM monthly_showcase_groups WHERE group_id = ?",
                (key,),
            ).fetchone()
        return self._result(key, saved)

    def audit(self, group_id: Any, limit: int = 100) -> list[Dict[str, Any]]:
        key = _group_id(group_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("audit limit is invalid")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, group_id, action, revision, changed_fields_json,
                       actor, occurred_at
                FROM monthly_showcase_audit
                WHERE group_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (key, limit),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "group_id": row["group_id"],
                "action": row["action"],
                "revision": row["revision"],
                "changed_fields": json.loads(row["changed_fields_json"]),
                "actor": row["actor"],
                "occurred_at": row["occurred_at"],
            }
            for row in rows
        ]

    def write_probe(self) -> bool:
        """Confirm the mounted database can begin a write without changing data."""

        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("SELECT 1").fetchone()
                connection.rollback()
            return True
        except sqlite3.Error:
            return False
