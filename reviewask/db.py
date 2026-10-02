# -*- coding: utf-8 -*-
"""
reviewask.db — «رفع التقييم» storage, inside the SAME brain.db every other package uses.

Connection rules come from brain.db.connect() (no WAL, journal_mode=DELETE, one short-lived
connection per call) — read brain/db.py's docstring before changing anything here.

WHAT THE SCHEMA ENFORCES
  * One reservation = one ticket, ever: rv_tickets.reservation_id is UNIQUE (layer 1 of the
    three anti-duplicate layers; _once_claim and the topic rebuild are layers 2 and 3).
  * First final wins: transition() is a conditional UPDATE under a lock.
  * The record outlives the room: rv_events + rv_transcripts are never deleted — the Discord
    room goes after 7 days (spec §13), the history stays in the dashboard forever.
  * One owner text: save_templates() is the ONLY writer (dashboard editor and /review-message
    both call it) and keeps every previous version in rv_template_history.
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
CREATE TABLE IF NOT EXISTS rv_tickets (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id    TEXT NOT NULL UNIQUE,
    lid               INTEGER,
    day               TEXT,                  -- departure date D (Riyadh)
    arrival           TEXT,
    unit              TEXT,
    guest             TEXT,
    phone             TEXT,
    conversation_id   TEXT,
    mode              TEXT NOT NULL DEFAULT 'review',   -- review | care
    care_reason       TEXT,
    state             TEXT NOT NULL DEFAULT 'waiting',
    stage_due_at      TEXT,
    pinged_at         TEXT,
    remind_count      INTEGER NOT NULL DEFAULT 0,
    missed_at         TEXT,
    next_due_at       TEXT,
    calls_used        INTEGER NOT NULL DEFAULT 0,
    later_used        INTEGER NOT NULL DEFAULT 0,
    care_ok           INTEGER NOT NULL DEFAULT 0,
    wa_note           TEXT,
    responsible       TEXT,
    responsible_did   TEXT,
    channel_id        TEXT,
    card_message_id   TEXT,
    avg_at_open       REAL,
    n_at_open         INTEGER,
    needed_at_open    INTEGER,
    review_id         TEXT,
    review_stars      REAL,
    state_by          TEXT,
    state_by_did      TEXT,
    state_at          TEXT,
    close_note        TEXT,
    closed_at         TEXT,
    deleted_at        TEXT,
    delete_note       TEXT,
    created_by        TEXT,
    created_at        TEXT,
    updated_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_rv_tickets_state ON rv_tickets(state);
CREATE INDEX IF NOT EXISTS idx_rv_tickets_day ON rv_tickets(day);
CREATE INDEX IF NOT EXISTS idx_rv_tickets_card ON rv_tickets(card_message_id);
CREATE TABLE IF NOT EXISTS rv_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL,
    at         TEXT NOT NULL,
    kind       TEXT NOT NULL,
    actor      TEXT,
    actor_did  TEXT,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS idx_rv_events_t ON rv_events(ticket_id, kind);
CREATE INDEX IF NOT EXISTS idx_rv_events_at ON rv_events(at);
-- every message that carries buttons (the card, pings, reminders) → its ticket, so a press on
-- ANY of them finds the row after a redeploy (cw_messages pattern)
CREATE TABLE IF NOT EXISTS rv_messages (
    message_id  TEXT PRIMARY KEY,
    ticket_id   INTEGER NOT NULL,
    channel_id  TEXT,
    kind        TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_rv_msgs_t ON rv_messages(ticket_id, active);
-- the one-tap WhatsApp short link /rv/<token> (Discord caps a link button at 512 chars)
CREATE TABLE IF NOT EXISTS rv_links (
    token       TEXT PRIMARY KEY,
    ticket_id   INTEGER NOT NULL UNIQUE,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS rv_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT,
    by     TEXT,
    at     TEXT
);
CREATE TABLE IF NOT EXISTS rv_template_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    at           TEXT,
    by           TEXT,
    ar           TEXT,
    en           TEXT,
    call_script  TEXT
);
CREATE TABLE IF NOT EXISTS rv_transcripts (
    ticket_id  INTEGER PRIMARY KEY,
    at         TEXT,
    n          INTEGER,
    body       TEXT
);
CREATE TABLE IF NOT EXISTS rv_overrides (
    lid     INTEGER PRIMARY KEY,
    mode    TEXT NOT NULL,          -- in | out
    reason  TEXT,
    by      TEXT,
    at      TEXT
);
"""

# Columns added after the first live deploy go here: CREATE TABLE IF NOT EXISTS never alters an
# existing table, so _ensure() adds each one once (checkout/db.py pattern).
_LATE_COLUMNS = ()

TICKET_FIELDS = (
    "reservation_id", "lid", "day", "arrival", "unit", "guest", "phone", "conversation_id",
    "mode", "care_reason", "state", "stage_due_at", "pinged_at", "remind_count", "missed_at",
    "next_due_at", "calls_used", "later_used", "care_ok", "wa_note", "responsible",
    "responsible_did", "channel_id", "card_message_id", "avg_at_open", "n_at_open",
    "needed_at_open", "review_id", "review_stars", "state_by", "state_by_did", "state_at",
    "close_note", "closed_at", "deleted_at", "delete_note", "created_by")

SEED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.seed.json")

_inited = set()
_init_lock = threading.Lock()
_answer_lock = threading.Lock()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            have = {r[1] for r in cx.execute("PRAGMA table_info(rv_tickets)").fetchall()}
            for col, decl in _LATE_COLUMNS:
                if col not in have:
                    cx.execute("ALTER TABLE rv_tickets ADD COLUMN %s %s" % (col, decl))
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


# ------------------------------------------------------------------ tickets

def insert_ticket(fields, at=None):
    """INSERT OR IGNORE on reservation_id. -> (created, row). Only the call that really created
    the row gets created=True — that call alone may open the Discord room."""
    at = at or now_iso()
    cols, vals = ["created_at", "updated_at"], [at, at]
    for k in TICKET_FIELDS:
        if k in fields:
            cols.append(k)
            vals.append(fields[k])
    n = execute("INSERT OR IGNORE INTO rv_tickets (%s) VALUES (%s)"
                % (",".join(cols), ",".join("?" * len(cols))), vals)
    return n == 1, by_reservation(fields.get("reservation_id"))


def ticket(tid):
    return q1("SELECT * FROM rv_tickets WHERE id=?", (int(tid),))


def by_reservation(res_id):
    return q1("SELECT * FROM rv_tickets WHERE reservation_id=?", (str(res_id or ""),))


def by_channel(channel_id):
    return q1("SELECT * FROM rv_tickets WHERE channel_id=?", (str(channel_id or ""),))


def by_message(message_id):
    mid = str(message_id or "")
    if not mid:
        return None
    row = q1("SELECT * FROM rv_tickets WHERE card_message_id=?", (mid,))
    if row:
        return row
    m = q1("SELECT ticket_id FROM rv_messages WHERE message_id=?", (mid,))
    return ticket(m["ticket_id"]) if m else None


def update_ticket(tid, fields, at=None):
    fields = {k: v for k, v in (fields or {}).items() if k in TICKET_FIELDS}
    if not fields:
        return 0
    fields["updated_at"] = at or now_iso()
    sets = ",".join("%s=?" % k for k in fields)
    return execute("UPDATE rv_tickets SET %s WHERE id=?" % sets, list(fields.values()) + [int(tid)])


def transition(tid, allowed_from, fields, at=None):
    """Move the row ONLY if it is still in one of `allowed_from` -> (moved, row_after).
    Two people pressing at once cannot both win."""
    fields = {k: v for k, v in (fields or {}).items() if k in TICKET_FIELDS}
    fields["updated_at"] = at or now_iso()
    sets = ",".join("%s=?" % k for k in fields)
    marks = ",".join("?" * len(allowed_from))
    with _answer_lock:
        n = execute("UPDATE rv_tickets SET %s WHERE id=? AND state IN (%s)" % (sets, marks),
                    list(fields.values()) + [int(tid)] + list(allowed_from))
        return n == 1, ticket(tid)


def open_tickets():
    marks = ",".join("?" * len(engine.OPEN))
    return q("SELECT * FROM rv_tickets WHERE state IN (%s) ORDER BY day, unit" % marks,
             list(engine.OPEN))


def tickets_for_days(days):
    days = list(days)
    if not days:
        return []
    return q("SELECT * FROM rv_tickets WHERE day IN (%s) ORDER BY day, unit"
             % ",".join("?" * len(days)), days)


def tickets_between(start_day, end_day):
    return q("SELECT * FROM rv_tickets WHERE day>=? AND day<=? ORDER BY day, unit",
             (start_day, end_day))


def closed_between(start_iso, end_iso):
    return q("SELECT * FROM rv_tickets WHERE closed_at>=? AND closed_at<? ORDER BY closed_at",
             (start_iso, end_iso))


def due_for_sweep(cutoff_iso, limit=10):
    """Terminal rows closed on or before `cutoff_iso` whose room is not yet deleted."""
    marks = ",".join("?" * len(engine.TERMINAL))
    return q("SELECT * FROM rv_tickets WHERE state IN (%s) AND closed_at IS NOT NULL "
             "AND closed_at<=? AND deleted_at IS NULL AND channel_id IS NOT NULL "
             "AND channel_id<>'' AND (delete_note IS NULL OR delete_note NOT LIKE 'refused%%') "
             "ORDER BY closed_at LIMIT ?" % marks,
             list(engine.TERMINAL) + [cutoff_iso, int(limit)])


def archive(limit=200, offset=0):
    marks = ",".join("?" * len(engine.TERMINAL))
    return q("SELECT * FROM rv_tickets WHERE state IN (%s) ORDER BY closed_at DESC, id DESC "
             "LIMIT ? OFFSET ?" % marks, list(engine.TERMINAL) + [int(limit), int(offset)])


# ------------------------------------------------------------------ events

def log_event(tid, kind, actor="", actor_did="", detail="", at=None):
    execute("INSERT INTO rv_events (ticket_id, at, kind, actor, actor_did, detail) "
            "VALUES (?,?,?,?,?,?)",
            (int(tid), at or now_iso(), kind, actor or "", str(actor_did or ""),
             (detail or "")[:1000]))


def events(tid=None, kinds=None):
    sql, args = "SELECT * FROM rv_events WHERE 1=1", []
    if tid is not None:
        sql += " AND ticket_id=?"
        args.append(int(tid))
    if kinds:
        sql += " AND kind IN (%s)" % ",".join("?" * len(kinds))
        args.extend(kinds)
    return q(sql + " ORDER BY at, id", args)


def events_for(ids):
    ids = [int(i) for i in ids]
    out = []
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        if chunk:
            out.extend(q("SELECT * FROM rv_events WHERE ticket_id IN (%s) ORDER BY at, id"
                         % ",".join("?" * len(chunk)), chunk))
    return out


def events_between(start_iso, end_iso):
    return q("SELECT * FROM rv_events WHERE at>=? AND at<? ORDER BY at, id", (start_iso, end_iso))


def has_event(tid, kind):
    return bool(q1("SELECT 1 AS x FROM rv_events WHERE ticket_id=? AND kind=? LIMIT 1",
                   (int(tid), kind)))


# ------------------------------------------------------------------ button messages

def add_message(message_id, tid, channel_id="", kind="", at=None):
    execute("INSERT OR REPLACE INTO rv_messages (message_id, ticket_id, channel_id, kind, active, "
            "at) VALUES (?,?,?,?,1,?)",
            (str(message_id), int(tid), str(channel_id or ""), kind, at or now_iso()))


def active_messages(tid):
    return q("SELECT * FROM rv_messages WHERE ticket_id=? AND active=1 ORDER BY at", (int(tid),))


def deactivate_message(message_id):
    execute("UPDATE rv_messages SET active=0 WHERE message_id=?", (str(message_id),))


# ------------------------------------------------------------------ one-tap links

def ensure_link(tid):
    execute("INSERT OR IGNORE INTO rv_links (token, ticket_id, created_at) VALUES (?,?,?)",
            (secrets.token_urlsafe(12), int(tid), now_iso()))
    return q1("SELECT * FROM rv_links WHERE ticket_id=?", (int(tid),))


def link_for(tid):
    return q1("SELECT * FROM rv_links WHERE ticket_id=?", (int(tid),))


def by_token(token):
    t = str(token or "")
    if len(t) < 16:
        return None
    row = q1("SELECT ticket_id FROM rv_links WHERE token=?", (t,))
    return ticket(row["ticket_id"]) if row else None


# ------------------------------------------------------------------ settings + the switch

_cache = {"at": 0.0, "vals": {}}
_TTL = 3.0          # seconds — /reviews-stop must land fast, reads must stay cheap


def invalidate():
    _cache["at"] = 0.0


def settings():
    now = time.time()
    if now - _cache["at"] < _TTL:
        return _cache["vals"]
    try:
        vals = {r["key"]: r["value"] for r in q("SELECT key, value FROM rv_settings")}
    except Exception as e:
        print("[reviewask] settings read failed, falling back to env:", e)
        vals = {}
    _cache["at"], _cache["vals"] = now, vals
    return vals


def setting(key, default=None):
    v = settings().get(key)
    return default if v is None else v


def set_setting(key, value, by=""):
    execute("INSERT OR REPLACE INTO rv_settings (key, value, by, at) VALUES (?,?,?,?)",
            (key, value, by or "", now_iso()))
    invalidate()


def setting_row(key):
    return q1("SELECT * FROM rv_settings WHERE key=?", (key,))


def claim(key, by=""):
    """True for exactly one caller per key, across ticks and restarts (the persisted latch)."""
    n = execute("INSERT OR IGNORE INTO rv_settings (key, value, by, at) VALUES (?,?,?,?)",
                (key, "1", by or "", now_iso()))
    invalidate()
    return n == 1


def live(env_default=False):
    """stored value > REVIEWASK_LIVE > off. Stored wins so a flip survives a redeploy."""
    v = setting("live")
    if v in ("0", "1"):
        return v == "1"
    return bool(env_default)


# ------------------------------------------------------------------ templates (R4, R8)

def _seed():
    try:
        with open(SEED_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return {"ar": d.get("ar") or "", "en": d.get("en") or "",
                "call_script": d.get("call_script") or ""}
    except Exception as e:
        print("[reviewask] template seed unreadable:", e)
        return {"ar": "", "en": "", "call_script": ""}


def templates():
    """The owner's current text. Seeded from templates.seed.json on first read only."""
    raw = setting("templates")
    if raw:
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                return d
        except ValueError:
            pass
    seed = _seed()
    seed.update({"updated_by": "seed", "updated_at": now_iso()})
    execute("INSERT OR IGNORE INTO rv_settings (key, value, by, at) VALUES (?,?,?,?)",
            ("templates", json.dumps(seed, ensure_ascii=False), "seed", now_iso()))
    invalidate()
    return json.loads(setting("templates") or json.dumps(seed, ensure_ascii=False))


def save_templates(ar, en, call_script, by):
    """THE ONLY WRITER. The previous version goes to rv_template_history first."""
    prev = templates()
    execute("INSERT INTO rv_template_history (at, by, ar, en, call_script) VALUES (?,?,?,?,?)",
            (prev.get("updated_at") or now_iso(), prev.get("updated_by") or "",
             prev.get("ar") or "", prev.get("en") or "", prev.get("call_script") or ""))
    new = {"ar": str(ar or ""), "en": str(en or ""), "call_script": str(call_script or ""),
           "updated_by": by or "", "updated_at": now_iso()}
    set_setting("templates", json.dumps(new, ensure_ascii=False), by)
    return new


def template_history(limit=20):
    return q("SELECT * FROM rv_template_history ORDER BY id DESC LIMIT ?", (int(limit),))


# ------------------------------------------------------------------ owner pins

def overrides():
    return {r["lid"]: r for r in q("SELECT * FROM rv_overrides")}


def set_override(lid, mode, reason, by):
    if mode not in ("in", "out"):
        execute("DELETE FROM rv_overrides WHERE lid=?", (int(lid),))
        return None
    execute("INSERT OR REPLACE INTO rv_overrides (lid, mode, reason, by, at) VALUES (?,?,?,?,?)",
            (int(lid), mode, (reason or "")[:300], by or "", now_iso()))
    return overrides().get(int(lid))


# ------------------------------------------------------------------ transcripts

def save_transcript(tid, messages):
    execute("INSERT OR REPLACE INTO rv_transcripts (ticket_id, at, n, body) VALUES (?,?,?,?)",
            (int(tid), now_iso(), len(messages or []),
             json.dumps(messages or [], ensure_ascii=False)))
    return transcript(tid)


def transcript(tid):
    row = q1("SELECT * FROM rv_transcripts WHERE ticket_id=?", (int(tid),))
    if not row:
        return None
    try:
        row["messages"] = json.loads(row.pop("body") or "[]")
    except ValueError:
        row["messages"] = []
    return row


def counts():
    return {t: q1("SELECT COUNT(*) AS n FROM %s" % t)["n"]
            for t in ("rv_tickets", "rv_events", "rv_messages", "rv_links", "rv_settings",
                      "rv_template_history", "rv_transcripts", "rv_overrides")}
