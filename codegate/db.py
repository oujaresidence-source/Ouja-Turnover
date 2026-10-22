# codegate/db.py
# -*- coding: utf-8 -*-
"""
codegate.db — «تسليم الرموز» storage inside the SAME brain.db (brain/db.py rules: no WAL,
journal_mode=DELETE, one short-lived connection per call, always closed).

WHAT THE SCHEMA ENFORCES
  * One booking = one row (res_id PRIMARY KEY): a double tick or a redeploy never posts a
    second card.
  * First press wins: release() only updates a row whose released_at IS NULL.
  * A card lives in ONE room: set_room() to a different channel forgets the old card.
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
    room_kind        TEXT,
    room_close_pending INTEGER DEFAULT 0,
    sent_by_bot      INTEGER DEFAULT 0,
    held_channel_id  TEXT,
    card_room_fail_count INTEGER DEFAULT 0,
    held_room_fail_count INTEGER DEFAULT 0,
    moving_to        TEXT,
    card_lost_at     TEXT,
    room_refusals    INTEGER DEFAULT 0,
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
-- codegate_headers (revision 1's per-person header latch) is no longer created; a brain.db
-- that already has it keeps it, unused and harmless.
CREATE TABLE IF NOT EXISTS codegate_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT,
    by     TEXT,
    at     TEXT
);
"""

# Columns added after the first deploy: a table that already exists keeps its old shape (CREATE
# TABLE IF NOT EXISTS is a no-op on it), so each is added once, additively, in _ensure.
_LATE_COLUMNS = (("prelive_checked_at", "TEXT"),
                 ("room_kind", "TEXT"),                    # "turnover" | "code"
                 ("room_close_pending", "INTEGER DEFAULT 0"),
                 ("sent_by_bot", "INTEGER DEFAULT 0"),
                 ("held_channel_id", "TEXT"),              # the turnover room the bot HELD
                 ("card_room_fail_count", "INTEGER DEFAULT 0"),   # failed closes, per room
                 ("held_room_fail_count", "INTEGER DEFAULT 0"),
                 ("moving_to", "TEXT"),                    # "<lid>|<day>": a move whose close
#                                                            is still owed (the row is FROZEN)
                 ("card_lost_at", "TEXT"),                 # live lost a card (room deleted):
#                                                            placement no longer waits for a
#                                                            turnover room that won't reopen
                 ("room_refusals", "INTEGER DEFAULT 0"))   # rooms that took no card today

STAMP_COLUMNS = ("alert_2h_at", "alert_late_at", "code_check_at", "code_warned_at",
                 "card_lost_at")
# A booking moved to another date OR another unit: what belonged to the old arrival (its card and
# room, a held room, its alert stamps, the honesty check, a release) starts over. flow.tick closes
# the old code-only room and the old held room BEFORE this reset (or skips the upsert to retry).
_DAY_RESET = ("channel_id", "card_message_id", "card_hash", "alert_2h_at", "alert_late_at",
              "code_seen", "code_check_at", "code_warned_at", "released_by", "released_by_did",
              "released_at", "room_kind", "room_close_pending", "sent_by_bot",
              "held_channel_id", "card_room_fail_count", "held_room_fail_count",
              "card_lost_at", "room_refusals")
_RESET_TO_ZERO = ("room_close_pending", "sent_by_bot", "card_room_fail_count",
                  "held_room_fail_count", "room_refusals")                                   # flags, not NULL
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
    # SQLite evaluates every SET expression against the OLD row, so `day`/`lid` below are the
    # stored ones
    sets += ", " + ", ".join("%s=CASE WHEN codegate_items.day IS excluded.day AND "
                             "codegate_items.lid IS excluded.lid THEN %s ELSE %s END"
                             % (k, k, "0" if k in _RESET_TO_ZERO else "NULL")
                             for k in _DAY_RESET)
    _x("INSERT INTO codegate_items(res_id, %s, cancelled, created_at, updated_at) "
       "VALUES (?, %s, 0, ?, ?) "
       "ON CONFLICT(res_id) DO UPDATE SET %s, cancelled=0, moving_to=NULL, "
       "updated_at=excluded.updated_at"
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
           "code_seen=NULL, code_check_at=NULL, code_warned_at=NULL, sent_by_bot=0, "
           "undone_by=?, undone_at=?, "
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


def set_room(res_id, channel_id, kind):
    """The room the card lives in ("turnover" | "code"), or (None, None) to place it again.
    A DIFFERENT channel forgets the card (it is not in the new room). room_close_pending is
    deliberately kept: the bot may hold a turnover room before the card is placed in it."""
    ch = None if channel_id is None else str(channel_id)
    # SQLite evaluates every SET expression against the OLD row
    _x("UPDATE codegate_items SET "
       "card_message_id=CASE WHEN channel_id IS ? THEN card_message_id ELSE NULL END, "
       "card_hash=CASE WHEN channel_id IS ? THEN card_hash ELSE NULL END, "
       "channel_id=?, room_kind=?, updated_at=? WHERE res_id=?",
       (ch, ch, ch, kind, _now(), str(res_id)))


def set_close_pending(res_id, on):
    _x("UPDATE codegate_items SET room_close_pending=?, updated_at=? WHERE res_id=?",
       (1 if on else 0, _now(), str(res_id)))


def set_held(res_id, channel_id):
    """The bot held a turnover room for this arrival's code. channel_id None = held, but the
    room is looked up (find_room) when it is time to close it."""
    _x("UPDATE codegate_items SET room_close_pending=1, held_channel_id=?, updated_at=? "
       "WHERE res_id=?", (None if channel_id is None else str(channel_id), _now(), str(res_id)))


def room_closed(res_id, channel_id, held=False):
    """Forget a room that is closed (or given up on). It is the card's room → the card goes with
    it; it is the held room (held=True, or equal to held_channel_id) → the held close is done.
    Only the tally of the room(s) actually forgotten resets."""
    ch = None if channel_id is None else str(channel_id)
    # SQLite evaluates every SET expression against the OLD row
    card = "channel_id IS NOT NULL AND channel_id IS ?"
    hold = "(%d=1 OR (held_channel_id IS NOT NULL AND held_channel_id IS ?))" % (1 if held else 0)
    _x("UPDATE codegate_items SET "
       "card_message_id=CASE WHEN {c} THEN NULL ELSE card_message_id END, "
       "card_hash=CASE WHEN {c} THEN NULL ELSE card_hash END, "
       "room_kind=CASE WHEN {c} THEN NULL ELSE room_kind END, "
       "channel_id=CASE WHEN {c} THEN NULL ELSE channel_id END, "
       "held_channel_id=CASE WHEN {h} THEN NULL ELSE held_channel_id END, "
       "room_close_pending=CASE WHEN {h} THEN 0 ELSE room_close_pending END, "
       "card_room_fail_count=CASE WHEN {c} THEN 0 ELSE card_room_fail_count END, "
       "held_room_fail_count=CASE WHEN {h} THEN 0 ELSE held_room_fail_count END, "
       "updated_at=? WHERE res_id=?".format(c=card, h=hold),
       (ch, ch, ch, ch, ch, ch, ch, ch, _now(), str(res_id)))


def delete_failed(res_id, held):
    """One more failed close of this row's held room (held=True) or card room; returns that
    room's new count. Each room has its own tally, so "at most 3 tries" holds per room."""
    col = "held_room_fail_count" if held else "card_room_fail_count"
    _x("UPDATE codegate_items SET %s=COALESCE(%s, 0)+1, updated_at=? WHERE res_id=?"
       % (col, col), (_now(), str(res_id)))
    rows = _q("SELECT %s AS n FROM codegate_items WHERE res_id=?" % col, (str(res_id),))
    return int(rows[0]["n"] or 0) if rows else 0


def bump_refusals(res_id):
    """One more room that took no card (gone, or the bot may not write there); returns the
    new count. flow stops placing the item for the day at flow.ROOM_REFUSALS_MAX."""
    _x("UPDATE codegate_items SET room_refusals=COALESCE(room_refusals, 0)+1, updated_at=? "
       "WHERE res_id=?", (_now(), str(res_id)))
    rows = _q("SELECT room_refusals AS n FROM codegate_items WHERE res_id=?", (str(res_id),))
    return int(rows[0]["n"] or 0) if rows else 0


def set_moving(res_id, lid, day):
    """FREEZE: the booking moved to (lid, day) but a close on its old arrival is still owed, so
    the upsert waits. A frozen row is skipped by the tick, ignored by should_hold and refuses
    presses. upsert_arrival clears it; so does clear_moving_except when the move stops."""
    _x("UPDATE codegate_items SET moving_to=?, updated_at=? WHERE res_id=?",
       ("%s|%s" % (lid, day), _now(), str(res_id)))


def clear_moving_except(res_ids):
    keep = sorted({str(x) for x in res_ids or ()})
    marks = ",".join("?" * len(keep))
    _x("UPDATE codegate_items SET moving_to=NULL WHERE moving_to IS NOT NULL" +
       (" AND res_id NOT IN (%s)" % marks if keep else ""), tuple(keep))


def items_moving_to(lid, day):
    return [_shape(r) for r in _q("SELECT * FROM codegate_items WHERE moving_to=? "
                                  "ORDER BY res_id", ("%s|%s" % (lid, day),))]


def mark_sent_by_bot(res_id):
    _x("UPDATE codegate_items SET sent_by_bot=1, updated_at=? WHERE res_id=?",
       (_now(), str(res_id)))


def code_room_items(older_than_day=None):
    """Rows whose card sits in a code-only room that still exists (channel_id set)."""
    sql = ("SELECT * FROM codegate_items WHERE room_kind='code' AND channel_id IS NOT NULL "
           "AND channel_id != ''")
    args = ()
    if older_than_day:
        sql += " AND day < ?"
        args = (older_than_day,)
    return [_shape(r) for r in _q(sql + " ORDER BY day, res_id", args)]


def held_room_items(older_than_day=None):
    """Rows with a held turnover room (room_close_pending) — the deferred close codegate owes.
    Tracked by held_channel_id, whatever room the card itself is in (or none)."""
    sql = "SELECT * FROM codegate_items WHERE room_close_pending=1"
    args = ()
    if older_than_day:
        sql += " AND day < ?"
        args = (older_than_day,)
    return [_shape(r) for r in _q(sql + " ORDER BY day, res_id", args)]


def items_for(lid, day):
    try:
        lid = int(lid)
    except (TypeError, ValueError):
        return []
    return [_shape(r) for r in _q("SELECT * FROM codegate_items WHERE lid=? AND day=? "
                                  "ORDER BY res_id", (lid, day))]


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
