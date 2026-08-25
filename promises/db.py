# -*- coding: utf-8 -*-
"""promise_ledger inside the SAME brain.db SQLite file (NO WAL, journal DELETE,
busy_timeout — the proven rules; see CLAUDE.md brain-sqlite notes)."""

import datetime
import sqlite3
import threading
import uuid
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS promise_ledger (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'watchman',   -- watchman | assistant
    conversation_id TEXT,
    listing_id      TEXT,
    apartment       TEXT,
    guest_name      TEXT,
    promised_by     TEXT,                               -- human name («المساعد» never appears here)
    promised_by_id  TEXT,                               -- discord id when known
    promise_text    TEXT NOT NULL,
    quote           TEXT,
    category        TEXT,                               -- maintenance/delivery/info/refund/other|action/money/timing
    due_at          TEXT,
    status          TEXT NOT NULL DEFAULT 'open',       -- open | done | expired
    created_at      TEXT NOT NULL,
    done_by         TEXT,
    done_at         TEXT,
    nudges          INTEGER NOT NULL DEFAULT 0,
    last_nudge_at   TEXT,
    escalated       INTEGER NOT NULL DEFAULT 0,
    channel_id      TEXT,
    msg_id          TEXT
);
CREATE INDEX IF NOT EXISTS idx_promise_status  ON promise_ledger(status);
CREATE INDEX IF NOT EXISTS idx_promise_person  ON promise_ledger(promised_by);
CREATE INDEX IF NOT EXISTS idx_promise_created ON promise_ledger(created_at);
"""

_inited = set()
_init_lock = threading.Lock()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def q(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.row_factory = sqlite3.Row
        return [dict(r) for r in cx.execute(sql, args).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid


def upsert(rec):
    """Insert-or-update one promise. `rec` keys mirror the columns; missing
    keys keep their current value on update. Returns the id."""
    pid = rec.get("id") or ("pk-" + uuid.uuid4().hex[:12])
    cur = q1("SELECT * FROM promise_ledger WHERE id=?", (pid,))
    if cur is None:
        execute(
            "INSERT INTO promise_ledger(id,source,conversation_id,listing_id,apartment,guest_name,"
            "promised_by,promised_by_id,promise_text,quote,category,due_at,status,created_at,"
            "nudges,escalated,channel_id,msg_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, rec.get("source") or "watchman", rec.get("conversation_id"),
             str(rec.get("listing_id") or "") or None, rec.get("apartment"),
             rec.get("guest_name"), rec.get("promised_by"), rec.get("promised_by_id"),
             rec.get("promise_text") or "", rec.get("quote"), rec.get("category"),
             rec.get("due_at"), rec.get("status") or "open",
             rec.get("created_at") or now_iso(),
             int(rec.get("nudges") or 0), int(bool(rec.get("escalated"))),
             rec.get("channel_id"), rec.get("msg_id")))
    else:
        sets, args = [], []
        for k in ("source", "conversation_id", "listing_id", "apartment", "guest_name",
                  "promised_by", "promised_by_id", "promise_text", "quote", "category",
                  "due_at", "status", "done_by", "done_at", "nudges", "last_nudge_at",
                  "escalated", "channel_id", "msg_id"):
            if k in rec and rec[k] is not None:
                sets.append("%s=?" % k)
                args.append(rec[k])
        if sets:
            args.append(pid)
            execute("UPDATE promise_ledger SET " + ",".join(sets) + " WHERE id=?", tuple(args))
    return pid


def get(pid):
    return q1("SELECT * FROM promise_ledger WHERE id=?", (pid,))


def get_by_msg(msg_id):
    return q1("SELECT * FROM promise_ledger WHERE msg_id=?", (str(msg_id),))


def mark_done(pid, by=""):
    execute("UPDATE promise_ledger SET status='done', done_by=?, done_at=? WHERE id=? AND status!='done'",
            (by or "", now_iso(), pid))
    return get(pid)


def mark_expired(pid):
    execute("UPDATE promise_ledger SET status='expired' WHERE id=? AND status='open'", (pid,))
    return get(pid)


def record_nudge(pid, at=None):
    execute("UPDATE promise_ledger SET nudges=nudges+1, last_nudge_at=? WHERE id=?",
            (at or now_iso(), pid))


def list_rows(status=None, limit=300):
    if status:
        return q("SELECT * FROM promise_ledger WHERE status=? ORDER BY created_at DESC LIMIT ?",
                 (status, int(limit)))
    return q("SELECT * FROM promise_ledger ORDER BY created_at DESC LIMIT ?", (int(limit),))


def open_rows():
    return q("SELECT * FROM promise_ledger WHERE status='open' ORDER BY created_at")
