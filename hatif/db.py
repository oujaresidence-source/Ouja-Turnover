# -*- coding: utf-8 -*-
"""
hatif_* tables inside the SAME brain.db (journal DELETE, one short connection per call via
closing(connect()) — the proven rules, see CLAUDE.md and stayhub/db.py).

    hatif_events   one row per inbound delivery we looked at. The primary key is Hatif's
                   conversationEventId, so a retried delivery can never be answered twice.
    hatif_convs    per conversation: how many times in a row the dates could not be read.

PRIVACY: no phone number is ever stored. The guest's message is kept trimmed with long digit
runs hidden (engine.mask), only so the owner can see what the bot did. Rows older than 30
days are deleted.
"""
import datetime
import json
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS hatif_events (
    event_id        TEXT PRIMARY KEY,
    conversation_id TEXT,
    created_at      TEXT,
    outcome         TEXT,
    body            TEXT,
    parsed          TEXT,
    reply           TEXT,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS hatif_events_created ON hatif_events(created_at);
CREATE TABLE IF NOT EXISTS hatif_ai_events (
    event_id        TEXT PRIMARY KEY,
    created_at      TEXT,
    door            TEXT,
    body            TEXT,
    reply           TEXT,
    violations      TEXT
);
CREATE INDEX IF NOT EXISTS hatif_ai_created ON hatif_ai_events(created_at);
CREATE TABLE IF NOT EXISTS hatif_convs (
    conversation_id TEXT PRIMARY KEY,
    fails           INTEGER DEFAULT 0,
    updated_at      TEXT
);
"""

_init_lock = threading.Lock()
_inited = set()
_claims = {"n": 0}
KEEP_DAYS = 30


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
    _claims["n"] = 0


def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat()


def claim(event_id, conversation_id, body):
    """True exactly once per event id. A second delivery of the same message returns False."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT OR IGNORE INTO hatif_events(event_id, conversation_id, created_at, outcome, body) "
            "VALUES(?,?,?,?,?)", (str(event_id), str(conversation_id or ""), now_iso(), "claimed", body))
        won = cur.rowcount == 1
        _claims["n"] += 1
        if _claims["n"] % 200 == 1:
            cutoff = (datetime.datetime.utcnow() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
            cx.execute("DELETE FROM hatif_events WHERE created_at < ?", (cutoff,))
            cx.execute("DELETE FROM hatif_convs WHERE updated_at < ?", (cutoff,))
            cx.execute("DELETE FROM hatif_ai_events WHERE created_at < ?", (cutoff,))
        cx.commit()
    return won


def finish(event_id, outcome, parsed=None, reply=None, error=None):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("UPDATE hatif_events SET outcome=?, parsed=?, reply=?, error=? WHERE event_id=?",
                   (outcome, json.dumps(parsed, ensure_ascii=False) if parsed is not None else None,
                    reply, (str(error)[:300] if error else None), str(event_id)))
        cx.commit()


def recent(limit=30):
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT event_id, conversation_id, created_at, outcome, body, parsed, reply, error "
            "FROM hatif_events ORDER BY created_at DESC, rowid DESC LIMIT ?", (int(limit),)).fetchall()
    out = []
    for r in rows:
        try:
            parsed = json.loads(r[5]) if r[5] else None
        except Exception:
            parsed = None
        out.append({"event_id": r[0], "conversation_id": r[1], "created_at": r[2], "outcome": r[3],
                    "body": r[4], "parsed": parsed, "reply": r[6], "error": r[7]})
    return out


def bump_fail(conversation_id):
    """Count one more unreadable message for this conversation; returns the new count."""
    _ensure()
    cid = str(conversation_id or "")
    with closing(_bdb.connect()) as cx:
        cx.execute("INSERT OR IGNORE INTO hatif_convs(conversation_id, fails, updated_at) VALUES(?,0,?)",
                   (cid, now_iso()))
        cx.execute("UPDATE hatif_convs SET fails = fails + 1, updated_at = ? WHERE conversation_id = ?",
                   (now_iso(), cid))
        n = cx.execute("SELECT fails FROM hatif_convs WHERE conversation_id = ?", (cid,)).fetchone()
        cx.commit()
    return int(n[0]) if n else 1


def clear_fail(conversation_id):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("DELETE FROM hatif_convs WHERE conversation_id = ?", (str(conversation_id or ""),))
        cx.commit()


def ai_claim(event_id, body):
    """True exactly once per event id for the reader (separate from the date bot's claim)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute("INSERT OR IGNORE INTO hatif_ai_events(event_id, created_at, door, body) "
                         "VALUES(?,?,?,?)", (str(event_id), now_iso(), "claimed", body))
        cx.commit()
        return cur.rowcount == 1


def ai_finish(event_id, door, reply=None, violations=None):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("UPDATE hatif_ai_events SET door=?, reply=?, violations=? WHERE event_id=?",
                   (door, (reply or "")[:2000], ",".join(violations or []), str(event_id)))
        cx.commit()


def ai_recent(limit=30):
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute("SELECT created_at, door, body, reply, violations FROM hatif_ai_events "
                          "ORDER BY created_at DESC LIMIT ?", (int(limit),)).fetchall()
    return [{"at": r[0], "door": r[1], "body": r[2], "reply": r[3], "violations": r[4]} for r in rows]
