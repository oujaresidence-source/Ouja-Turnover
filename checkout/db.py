# -*- coding: utf-8 -*-
"""
checkout.db — «متابعة الخروج» storage, inside the SAME brain.db every other package uses.

Connection rules come from brain.db.connect() (no WAL, journal_mode=DELETE, one short-lived
connection per call) — read brain/db.py's docstring before changing anything here.

WHAT THE SCHEMA ENFORCES
  * One turnover = one row: work_key is the PRIMARY KEY, so a double tick or a redeploy can
    never post a second card for the same apartment and day.
  * One 17:00 summary per day: cw_daily.day is the PRIMARY KEY (the persisted latch).
  * Demo rows carry demo=1 and every reader that feeds the board, the report, the risk
    analysis or the 17:00 summary filters them out by default.
"""

import datetime
import json
import os
import secrets
import threading
import time
from contextlib import closing

from brain import db as _bdb
from . import engine

SCHEMA = """
CREATE TABLE IF NOT EXISTS cw_items (
    work_key          TEXT PRIMARY KEY,      -- '<lid>:<YYYY-MM-DD>' | 'demo:<n>'
    lid               INTEGER,
    day               TEXT,
    res_id            TEXT,
    unit              TEXT,
    guest             TEXT,
    phone             TEXT,
    conversation_id   TEXT,
    channel_name      TEXT,                  -- the Hostaway channel (Airbnb, Booking…)
    checkout_at       TEXT,
    checkin_at        TEXT,
    clean_minutes     INTEGER,
    responsible       TEXT,
    responsible_did   TEXT,                  -- '<id>' | 'role:<id>' | ''
    responsible_emoji TEXT,                  -- the person's calendar colour (🟡) for the card
    channel_id        TEXT,
    card_message_id   TEXT,
    state             TEXT NOT NULL DEFAULT 'waiting',
    state_by          TEXT,
    state_by_did      TEXT,
    state_at          TEXT,
    reason_code       TEXT,
    reason_text       TEXT,
    expected_out_at   TEXT,
    remind_count      INTEGER NOT NULL DEFAULT 0,
    next_action_at    TEXT,
    airbnb_sent       INTEGER NOT NULL DEFAULT 0,
    airbnb_note       TEXT,                  -- why the last Airbnb message did not go out
    pinged_at         TEXT,
    demo              INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT,
    updated_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_cw_items_day  ON cw_items(day, demo);
CREATE INDEX IF NOT EXISTS idx_cw_items_card ON cw_items(card_message_id);
CREATE TABLE IF NOT EXISTS cw_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    work_key   TEXT NOT NULL,
    at         TEXT NOT NULL,
    kind       TEXT NOT NULL,
    actor      TEXT,
    actor_did  TEXT,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_cw_events_key ON cw_events(work_key, kind);
-- Every message that carries answer buttons (the card, pings, reminders, re-asks), so a press
-- on ANY of them finds its turnover after a redeploy — no per-item view registration.
CREATE TABLE IF NOT EXISTS cw_messages (
    message_id  TEXT PRIMARY KEY,
    work_key    TEXT NOT NULL,
    channel_id  TEXT,
    kind        TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_cw_msgs_key ON cw_messages(work_key, active);
-- The one-tap contact button. Discord caps a link button's URL at 512 characters and the
-- ready-made WhatsApp message alone is ~730 once encoded, so the button points at a SHORT
-- link on our own server (/cw/<token>) that rebuilds the message and redirects. airbnb_url
-- is the fallback button when the guest has no phone, looked up once when the card is made.
CREATE TABLE IF NOT EXISTS cw_links (
    token       TEXT PRIMARY KEY,
    work_key    TEXT NOT NULL UNIQUE,
    airbnb_url  TEXT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS cw_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT,
    by     TEXT,
    at     TEXT
);
CREATE TABLE IF NOT EXISTS cw_daily (
    day               TEXT PRIMARY KEY,
    summary_posted_at TEXT
);
"""

EVENT_KINDS = ("card_posted", "ping", "yes", "no", "noanswer", "remind", "reask", "wa_link",
               "airbnb_sent", "airbnb_failed", "surprise", "submitted", "approved",
               "deadline_miss", "converted")

_LATE_COLUMNS = (("responsible_emoji", "TEXT"),)

_inited = set()
_init_lock = threading.Lock()
_answer_lock = threading.Lock()        # first-final-wins, like _decide_early_checkin


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            # Columns added after the first live deploy: CREATE TABLE IF NOT EXISTS does not
            # touch an existing table, so each one is added here once, additively.
            have = {r[1] for r in cx.execute("PRAGMA table_info(cw_items)").fetchall()}
            for col, decl in _LATE_COLUMNS:
                if col not in have:
                    cx.execute("ALTER TABLE cw_items ADD COLUMN %s %s" % (col, decl))
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()
    invalidate()


def now_iso():
    return datetime.datetime.now(engine.tz()).isoformat(timespec="seconds")


def q(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        return [dict(r) for r in cx.execute(sql, args).fetchall()]


def q1(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute(sql, args).fetchone()
        return dict(r) if r else None


def execute(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.rowcount


# ------------------------------------------------------------------ items

ITEM_FIELDS = ("lid", "day", "res_id", "unit", "guest", "phone", "conversation_id",
               "channel_name", "checkout_at", "checkin_at", "clean_minutes", "responsible",
               "responsible_did", "responsible_emoji", "channel_id", "card_message_id", "state",
               "state_by", "state_by_did", "state_at", "reason_code", "reason_text", "expected_out_at",
               "remind_count", "next_action_at", "airbnb_sent", "airbnb_note", "pinged_at",
               "demo")


def insert_item(work_key, fields, at=None):
    """INSERT OR IGNORE — True only for the call that actually created the row. This is what
    makes posting a card idempotent across double ticks and redeploys."""
    at = at or now_iso()
    cols = ["work_key", "created_at", "updated_at"]
    vals = [work_key, at, at]
    for k in ITEM_FIELDS:
        if k in fields:
            cols.append(k)
            vals.append(fields[k])
    sql = "INSERT OR IGNORE INTO cw_items (%s) VALUES (%s)" % (
        ",".join(cols), ",".join("?" * len(cols)))
    return execute(sql, vals) == 1


def item(work_key):
    return q1("SELECT * FROM cw_items WHERE work_key=?", (work_key,))


def item_by_message(message_id):
    mid = str(message_id or "")
    if not mid:
        return None
    row = q1("SELECT * FROM cw_items WHERE card_message_id=?", (mid,))
    if row:
        return row
    m = q1("SELECT work_key FROM cw_messages WHERE message_id=?", (mid,))
    return item(m["work_key"]) if m else None


def update_item(work_key, fields, at=None):
    fields = {k: v for k, v in (fields or {}).items() if k in ITEM_FIELDS}
    if not fields:
        return 0
    fields["updated_at"] = at or now_iso()
    sets = ",".join("%s=?" % k for k in fields)
    return execute("UPDATE cw_items SET %s WHERE work_key=?" % sets,
                   list(fields.values()) + [work_key])


def transition(work_key, allowed_from, fields, at=None):
    """Move the row ONLY if it is still in one of `allowed_from`. Returns (moved, row_after).
    The conditional UPDATE under a lock is the first-final-wins rule: two people pressing at
    the same moment cannot both win."""
    fields = {k: v for k, v in (fields or {}).items() if k in ITEM_FIELDS}
    fields["updated_at"] = at or now_iso()
    sets = ",".join("%s=?" % k for k in fields)
    marks = ",".join("?" * len(allowed_from))
    with _answer_lock:
        n = execute("UPDATE cw_items SET %s WHERE work_key=? AND state IN (%s)" % (sets, marks),
                    list(fields.values()) + [work_key] + list(allowed_from))
        return n == 1, item(work_key)


def items_for_day(day, include_demo=False):
    if include_demo:
        return q("SELECT * FROM cw_items WHERE day=? ORDER BY checkout_at, unit", (day,))
    return q("SELECT * FROM cw_items WHERE day=? AND demo=0 ORDER BY checkout_at, unit", (day,))


def items_between(start_day, end_day):
    """Real (non-demo) turnovers in [start_day, end_day]."""
    return q("SELECT * FROM cw_items WHERE day>=? AND day<=? AND demo=0 ORDER BY day, unit",
             (start_day, end_day))


def demo_items():
    return q("SELECT * FROM cw_items WHERE demo=1 ORDER BY work_key")


def demo_item_by_channel(channel_id):
    return q1("SELECT * FROM cw_items WHERE demo=1 AND channel_id=?", (str(channel_id or ""),))


def delete_demo():
    """Removes demo rows and ONLY demo rows (and their events/messages/links)."""
    keys = [r["work_key"] for r in demo_items()]
    for k in keys:
        execute("DELETE FROM cw_events WHERE work_key=?", (k,))
        execute("DELETE FROM cw_messages WHERE work_key=?", (k,))
        execute("DELETE FROM cw_links WHERE work_key=?", (k,))
    execute("DELETE FROM cw_items WHERE demo=1")
    return len(keys)


# ------------------------------------------------------------------ events

def log_event(work_key, kind, actor="", actor_did="", detail="", at=None):
    execute("INSERT INTO cw_events (work_key, at, kind, actor, actor_did, detail) "
            "VALUES (?,?,?,?,?,?)",
            (work_key, at or now_iso(), kind, actor or "", str(actor_did or ""),
             (detail or "")[:500]))


def events(work_key=None, kinds=None):
    sql, args = "SELECT * FROM cw_events WHERE 1=1", []
    if work_key:
        sql += " AND work_key=?"
        args.append(work_key)
    if kinds:
        sql += " AND kind IN (%s)" % ",".join("?" * len(kinds))
        args.extend(kinds)
    return q(sql + " ORDER BY at, id", args)


def has_event(work_key, kind):
    return bool(q1("SELECT 1 AS x FROM cw_events WHERE work_key=? AND kind=? LIMIT 1",
                   (work_key, kind)))


def events_for_keys(keys):
    keys = list(keys)
    if not keys:
        return []
    out = []
    for i in range(0, len(keys), 400):
        chunk = keys[i:i + 400]
        out.extend(q("SELECT * FROM cw_events WHERE work_key IN (%s) ORDER BY at, id"
                     % ",".join("?" * len(chunk)), chunk))
    return out


# ------------------------------------------------------------------ button messages

def add_message(message_id, work_key, channel_id="", kind="", at=None):
    execute("INSERT OR REPLACE INTO cw_messages (message_id, work_key, channel_id, kind, "
            "active, at) VALUES (?,?,?,?,1,?)",
            (str(message_id), work_key, str(channel_id or ""), kind, at or now_iso()))


def active_messages(work_key, kinds=None):
    sql = "SELECT * FROM cw_messages WHERE work_key=? AND active=1"
    args = [work_key]
    if kinds:
        sql += " AND kind IN (%s)" % ",".join("?" * len(kinds))
        args.extend(kinds)
    return q(sql + " ORDER BY at", args)


def deactivate_message(message_id):
    execute("UPDATE cw_messages SET active=0 WHERE message_id=?", (str(message_id),))


# ------------------------------------------------------------------ one-tap contact links

def link_for(work_key):
    return q1("SELECT * FROM cw_links WHERE work_key=?", (work_key,))


def ensure_link(work_key, airbnb_url=""):
    """The row's short-link token, created once (INSERT OR IGNORE keeps the first)."""
    execute("INSERT OR IGNORE INTO cw_links (token, work_key, airbnb_url, created_at) "
            "VALUES (?,?,?,?)", (secrets.token_urlsafe(12), work_key, airbnb_url or "", now_iso()))
    return link_for(work_key)


def item_by_token(token):
    row = q1("SELECT work_key FROM cw_links WHERE token=?", (str(token or ""),))
    return item(row["work_key"]) if row else None


# ------------------------------------------------------------------ settings + the switch

_cache = {"at": 0.0, "vals": {}}
_TTL = 3.0          # seconds — /checkout-stop must land fast, reads must stay cheap


def invalidate():
    _cache["at"] = 0.0


def settings():
    now = time.time()
    if now - _cache["at"] < _TTL:
        return _cache["vals"]
    try:
        vals = {r["key"]: r["value"] for r in q("SELECT key, value FROM cw_settings")}
    except Exception as e:
        print("[checkout] settings read failed, falling back to env:", e)
        vals = {}
    _cache["at"], _cache["vals"] = now, vals
    return vals


def setting(key, default=None):
    v = settings().get(key)
    return default if v is None else v


def set_setting(key, value, by=""):
    execute("INSERT OR REPLACE INTO cw_settings (key, value, by, at) VALUES (?,?,?,?)",
            (key, value, by or "", now_iso()))
    invalidate()


def setting_row(key):
    return q1("SELECT * FROM cw_settings WHERE key=?", (key,))


def live():
    """stored value > CHECKOUT_WATCH_LIVE > '0'. Stored wins so a flip survives a redeploy."""
    v = setting("live")
    if v in ("0", "1"):
        return v == "1"
    return (os.environ.get("CHECKOUT_WATCH_LIVE", "0") or "0").strip() == "1"


def board_message_ids():
    try:
        v = json.loads(setting("board_message_ids") or "[]")
        return [str(x) for x in v if x]
    except Exception:
        return []


def set_board_message_ids(ids):
    set_setting("board_message_ids", json.dumps([str(x) for x in ids]))


# ------------------------------------------------------------------ the 17:00 latch

def claim_daily(day, at=None):
    """True for exactly one caller per day, across ticks and restarts."""
    return execute("INSERT OR IGNORE INTO cw_daily (day, summary_posted_at) VALUES (?,?)",
                   (day, at or now_iso())) == 1


def daily_claimed(day):
    return bool(q1("SELECT 1 AS x FROM cw_daily WHERE day=?", (day,)))


def counts():
    return {t: q1("SELECT COUNT(*) AS n FROM %s" % t)["n"]
            for t in ("cw_items", "cw_events", "cw_messages", "cw_links", "cw_settings",
                      "cw_daily")}
