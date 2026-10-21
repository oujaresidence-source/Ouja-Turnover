# codegate/db.py
# -*- coding: utf-8 -*-
"""
codegate.db — «تسليم الرموز» storage inside the SAME brain.db (brain/db.py rules: no WAL,
journal_mode=DELETE, one short-lived connection per call, always closed).

WHAT THE SCHEMA ENFORCES
  * One booking = one row (res_id PRIMARY KEY): a double tick or a redeploy never posts a
    second card.
  * First press wins: release() only updates a row whose released_at IS NULL.
  * One header per person per day (codegate_headers PRIMARY KEY (day, key)).
"""

import datetime
import json
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS codegate_items (
    res_id           TEXT PRIMARY KEY,
    lid              INTEGER,
    day              TEXT,
    unit             TEXT,
    guest            TEXT,
    conversation_id  TEXT,
    checkin_at       TEXT,
    cover_name       TEXT,
    cover_did        TEXT,
    cover_role_id    TEXT,
    owner_did        TEXT,
    channel_id       TEXT,
    card_message_id  TEXT,
    card_hash        TEXT,
    rules_at         TEXT,
    replies_json     TEXT,
    released_by      TEXT,
    released_by_did  TEXT,
    released_at      TEXT,
    code_seen        INTEGER,
    code_check_at    TEXT,
    code_warned_at   TEXT,
    prelive_checked_at TEXT,
    alert_2h_at      TEXT,
    alert_late_at    TEXT,
    cancelled        INTEGER NOT NULL DEFAULT 0,
    undone_by        TEXT,
    undone_at        TEXT,
    created_at       TEXT,
    updated_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_codegate_day  ON codegate_items(day);
CREATE INDEX IF NOT EXISTS idx_codegate_card ON codegate_items(card_message_id);
CREATE TABLE IF NOT EXISTS codegate_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    res_id  TEXT NOT NULL,
    at      TEXT NOT NULL,
    kind    TEXT NOT NULL,
    actor   TEXT,
    detail  TEXT
);
CREATE TABLE IF NOT EXISTS codegate_headers (
    day         TEXT NOT NULL,
    key         TEXT NOT NULL,
    message_id  TEXT,
    PRIMARY KEY (day, key)
);
CREATE TABLE IF NOT EXISTS codegate_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT,
    by     TEXT,
    at     TEXT
);
"""

# Columns added after the first deploy: a table that already exists keeps its old shape (CREATE
# TABLE IF NOT EXISTS is a no-op on it), so each is added once, additively, in _ensure.
_LATE_COLUMNS = (("prelive_checked_at", "TEXT"),)

STAMP_COLUMNS = ("alert_2h_at", "alert_late_at", "code_check_at", "code_warned_at")
# A booking moved to another date: what belonged to the old date (its card in the old day's
# list, its alert stamps, the honesty check, a release for the old arrival) starts over.
_DAY_RESET = ("channel_id", "card_message_id", "card_hash", "alert_2h_at", "alert_late_at",
              "code_seen", "code_check_at", "code_warned_at", "released_by", "released_by_did",
              "released_at")
_SNAPSHOT = ("lid", "day", "unit", "guest", "conversation_id", "checkin_at", "cover_name",
             "cover_did", "cover_role_id", "owner_did")

_inited = set()
_init_lock = threading.Lock()
_write_lock = threading.Lock()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            have = {r[1] for r in cx.execute("PRAGMA table_info(codegate_items)").fetchall()}
            for col, decl in _LATE_COLUMNS:
                if col not in have:
                    cx.execute("ALTER TABLE codegate_items ADD COLUMN %s %s" % (col, decl))
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()


def _q(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cols = [d[0] for d in cur.description or []]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _x(sql, args=()):
    _ensure()
    with _write_lock, closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.rowcount


def _shape(r):
    if r is None:
        return None
    try:
        r["replies"] = json.loads(r.get("replies_json") or "[]")
    except Exception:
        r["replies"] = []
    return r


def upsert_arrival(row):
    now = _now()
    vals = [str(row["res_id"])] + [row.get(k) for k in _SNAPSHOT]
    sets = ", ".join("%s=excluded.%s" % (k, k) for k in _SNAPSHOT)
    # SQLite evaluates every SET expression against the OLD row, so `day` below is the stored one
    sets += ", " + ", ".join("%s=CASE WHEN codegate_items.day IS excluded.day THEN %s ELSE NULL "
                             "END" % (k, k) for k in _DAY_RESET)
    _x("INSERT INTO codegate_items(res_id, %s, cancelled, created_at, updated_at) "
       "VALUES (?, %s, 0, ?, ?) "
       "ON CONFLICT(res_id) DO UPDATE SET %s, cancelled=0, updated_at=excluded.updated_at"
       % (", ".join(_SNAPSHOT), ", ".join("?" * len(_SNAPSHOT)), sets),
       vals + [now, now])


def mark_cancelled(day, keep_res_ids):
    keep = {str(x) for x in keep_res_ids or ()}
    gone = [r["res_id"] for r in _q("SELECT res_id FROM codegate_items WHERE day=? "
                                    "AND cancelled=0", (day,)) if r["res_id"] not in keep]
    for rid in gone:
        _x("UPDATE codegate_items SET cancelled=1, updated_at=? WHERE res_id=?", (_now(), rid))
    return gone


def get(res_id):
    rows = _q("SELECT * FROM codegate_items WHERE res_id=?", (str(res_id),))
    return _shape(rows[0]) if rows else None


def item_by_message(message_id):
    rows = _q("SELECT * FROM codegate_items WHERE card_message_id=?", (str(message_id),))
    return _shape(rows[0]) if rows else None


def day_items(day):
    return [_shape(r) for r in _q("SELECT * FROM codegate_items WHERE day=? "
                                  "ORDER BY checkin_at, res_id", (day,))]


def set_card(res_id, channel_id, message_id, card_hash):
    _x("UPDATE codegate_items SET channel_id=?, card_message_id=?, card_hash=?, updated_at=? "
       "WHERE res_id=?", (str(channel_id), str(message_id), card_hash, _now(), str(res_id)))


def set_hash(res_id, card_hash):
    _x("UPDATE codegate_items SET card_hash=? WHERE res_id=?", (card_hash, str(res_id)))


def set_replies(res_id, rules_at_iso, replies):
    blob = json.dumps([{"at": r.get("at"), "text": r.get("text")} for r in replies or []],
                      ensure_ascii=False)
    _x("UPDATE codegate_items SET rules_at=?, replies_json=?, updated_at=? WHERE res_id=?",
       (rules_at_iso, blob, _now(), str(res_id)))


def release(res_id, by_name, by_did, at_iso):
    n = _x("UPDATE codegate_items SET released_by=?, released_by_did=?, released_at=?, "
           "code_seen=NULL, code_check_at=NULL, code_warned_at=NULL, updated_at=? "
           "WHERE res_id=? AND released_at IS NULL AND cancelled=0",
           (by_name, str(by_did or ""), at_iso, _now(), str(res_id)))
    return n == 1


def undo(res_id, by_name, at_iso):
    n = _x("UPDATE codegate_items SET released_by=NULL, released_by_did=NULL, released_at=NULL, "
           "code_seen=NULL, code_check_at=NULL, code_warned_at=NULL, undone_by=?, undone_at=?, "
           "updated_at=? WHERE res_id=? AND released_at IS NOT NULL",
           (by_name, at_iso, _now(), str(res_id)))
    return n == 1


def stamp(res_id, column, at_iso):
    if column not in STAMP_COLUMNS:
        raise ValueError("codegate.db.stamp: column not allowed: %r" % column)
    _x("UPDATE codegate_items SET %s=?, updated_at=? WHERE res_id=?" % column,
       (at_iso, _now(), str(res_id)))


def set_prelive_checked(res_id, at_iso):
    """Go-live look at the chat is done (code found or not). Never stamped on a lookup error."""
    _x("UPDATE codegate_items SET prelive_checked_at=?, updated_at=? WHERE res_id=?",
       (at_iso, _now(), str(res_id)))


def set_code_seen(res_id, seen):
    _x("UPDATE codegate_items SET code_seen=? WHERE res_id=?", (1 if seen else 0, str(res_id)))


def header_posted(day, key):
    return bool(_q("SELECT 1 FROM codegate_headers WHERE day=? AND key=?", (day, str(key))))


def mark_header(day, key, message_id):
    _x("INSERT OR IGNORE INTO codegate_headers(day, key, message_id) VALUES (?,?,?)",
       (day, str(key), str(message_id or "")))


def event(res_id, kind, actor="", detail=""):
    _x("INSERT INTO codegate_events(res_id, at, kind, actor, detail) VALUES (?,?,?,?,?)",
       (str(res_id), _now(), kind, actor or "", detail or ""))


def get_setting(key, default=None):
    rows = _q("SELECT value FROM codegate_settings WHERE key=?", (str(key),))
    if not rows or rows[0]["value"] is None:
        return default
    return rows[0]["value"]


def set_setting(key, value, by=""):
    _x("INSERT OR REPLACE INTO codegate_settings(key, value, by, at) VALUES (?,?,?,?)",
       (str(key), None if value is None else str(value), by or "", _now()))
