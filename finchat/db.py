# -*- coding: utf-8 -*-
"""finchat.db — finchat_* tables inside the SAME brain.db file (reuses brain.db.connect:
NO WAL, journal_mode=DELETE, busy_timeout). Tables: finchat_kb, finchat_msgs, finchat_esc."""
import datetime
import json
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS finchat_kb (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    q_ar        TEXT NOT NULL,
    answer_ar   TEXT NOT NULL,
    links_json  TEXT DEFAULT '[]',
    tags        TEXT DEFAULT '',
    source      TEXT DEFAULT 'manual',      -- seed | learned | manual
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS finchat_msgs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL,
    role         TEXT NOT NULL,             -- user | bot | owner
    text         TEXT NOT NULL,
    links_json   TEXT DEFAULT '[]',
    kb_ids_json  TEXT DEFAULT '[]',
    model        TEXT,
    confidence   REAL,
    ts           TEXT
);
CREATE INDEX IF NOT EXISTS idx_finchat_msgs_user ON finchat_msgs(username, ts);
CREATE TABLE IF NOT EXISTS finchat_esc (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL,
    question       TEXT NOT NULL,
    context_json   TEXT DEFAULT '{}',
    status         TEXT DEFAULT 'open',     -- open | answered
    answer         TEXT,
    answered_at    TEXT,
    saved_as_kb    INTEGER DEFAULT 0,
    discord_msg_id TEXT,
    created_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_finchat_esc_status ON finchat_esc(status);
"""

_inited = False


def reset_init_cache():
    global _inited
    _inited = False


def _now():
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


def _ensure():
    global _inited
    if _inited:
        return
    with closing(_bdb.connect()) as cx:
        cx.executescript(SCHEMA)
        cx.commit()
    _inited = True


def _rows(cur):
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ---------------- KB ----------------

def kb_upsert(q_ar, answer_ar, links=None, tags="", source="manual", id=None):
    _ensure()
    lj = json.dumps(links or [], ensure_ascii=False)
    with closing(_bdb.connect()) as cx:
        if id:
            cx.execute("UPDATE finchat_kb SET q_ar=?, answer_ar=?, links_json=?, tags=?, updated_at=? WHERE id=?",
                       (q_ar, answer_ar, lj, tags, _now(), id))
            cx.commit()
            return int(id)
        cur = cx.execute(
            "INSERT INTO finchat_kb (q_ar, answer_ar, links_json, tags, source, enabled, created_at, updated_at)"
            " VALUES (?,?,?,?,?,1,?,?)",
            (q_ar, answer_ar, lj, tags, source, _now(), _now()))
        cx.commit()
        return int(cur.lastrowid)


def kb_all(enabled_only=True):
    _ensure()
    q = "SELECT * FROM finchat_kb" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY id"
    with closing(_bdb.connect()) as cx:
        rows = _rows(cx.execute(q))
    for r in rows:
        try:
            r["links"] = json.loads(r.pop("links_json") or "[]")
        except Exception:
            r["links"] = []
    return rows


def kb_count():
    _ensure()
    with closing(_bdb.connect()) as cx:
        return cx.execute("SELECT COUNT(*) FROM finchat_kb").fetchone()[0]


def kb_set_enabled(kb_id, enabled):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("UPDATE finchat_kb SET enabled=?, updated_at=? WHERE id=?",
                   (1 if enabled else 0, _now(), kb_id))
        cx.commit()


def kb_delete(kb_id):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("DELETE FROM finchat_kb WHERE id=?", (kb_id,))
        cx.commit()


# ---------------- chat log ----------------

def msg_add(username, role, text, kb_ids=None, model=None, confidence=None, links=None):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT INTO finchat_msgs (username, role, text, links_json, kb_ids_json, model, confidence, ts)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (username, role, text, json.dumps(links or [], ensure_ascii=False),
             json.dumps(kb_ids or []), model, confidence, _now()))
        cx.commit()
        return int(cur.lastrowid)


def msgs_for(username, limit=50):
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = _rows(cx.execute(
            "SELECT * FROM (SELECT * FROM finchat_msgs WHERE username=? ORDER BY id DESC LIMIT ?)"
            " ORDER BY id", (username, limit)))
    for r in rows:
        try:
            r["links"] = json.loads(r.pop("links_json") or "[]")
        except Exception:
            r["links"] = []
        r.pop("kb_ids_json", None)
    return rows


def msgs_today_count(username):
    """Daily cap counter — counts only the accountant's own questions (role=user), UTC day."""
    _ensure()
    today = datetime.datetime.utcnow().date().isoformat()
    with closing(_bdb.connect()) as cx:
        return cx.execute(
            "SELECT COUNT(*) FROM finchat_msgs WHERE username=? AND role='user' AND ts LIKE ?",
            (username, today + "%")).fetchone()[0]


# ---------------- escalations ----------------

def esc_create(username, question, context=None):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT INTO finchat_esc (username, question, context_json, status, created_at)"
            " VALUES (?,?,?,'open',?)",
            (username, question, json.dumps(context or {}, ensure_ascii=False), _now()))
        cx.commit()
        return int(cur.lastrowid)


def esc_get(esc_id):
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = _rows(cx.execute("SELECT * FROM finchat_esc WHERE id=?", (esc_id,)))
    return rows[0] if rows else None


def esc_open_list():
    _ensure()
    with closing(_bdb.connect()) as cx:
        return _rows(cx.execute("SELECT * FROM finchat_esc WHERE status='open' ORDER BY id DESC"))


def esc_answer(esc_id, answer, saved_as_kb=0):
    """Answer once — a second call is a no-op (returns False)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "UPDATE finchat_esc SET status='answered', answer=?, answered_at=?, saved_as_kb=?"
            " WHERE id=? AND status='open'",
            (answer, _now(), 1 if saved_as_kb else 0, esc_id))
        cx.commit()
        return cur.rowcount > 0
