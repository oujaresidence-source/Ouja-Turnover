# -*- coding: utf-8 -*-
"""watchdog_* tables inside the SAME brain.db SQLite file (NO WAL, journal DELETE,
busy_timeout, closing(connect()) — the proven rules; see CLAUDE.md brain-sqlite notes).

Read-only toward the business: this store only records what the watchdog OBSERVED
(code sends, ping dedup, per-employee message stats, automation fingerprints) plus the
owner-managed per-apartment code mode (auto | manual)."""

import json
import sqlite3
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchdog_code_mode (
    listing_id TEXT PRIMARY KEY,
    mode       TEXT NOT NULL DEFAULT 'auto',      -- auto | manual
    updated_at TEXT,
    updated_by TEXT
);
CREATE TABLE IF NOT EXISTS watchdog_code_sends (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id     TEXT,
    reservation_id TEXT,
    guest_name     TEXT,
    sent_by        TEXT,                           -- '' = unknown (Airbnb-app reply)
    sent_at        TEXT,
    arrival_ts     TEXT,
    on_time        INTEGER NOT NULL DEFAULT 0,
    detected_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wd_send_res ON watchdog_code_sends(reservation_id);
CREATE TABLE IF NOT EXISTS watchdog_flag_state (
    flag_key    TEXT PRIMARY KEY,
    first_seen  TEXT,
    last_seen   TEXT,
    pinged_at   TEXT,
    resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS watchdog_msg_stats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    day                 TEXT,
    employee            TEXT,
    replies             INTEGER NOT NULL DEFAULT 0,
    resp_min_sum        REAL    NOT NULL DEFAULT 0,
    resp_min_n          INTEGER NOT NULL DEFAULT 0,
    automations_skipped INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wd_stats ON watchdog_msg_stats(day, employee);
CREATE TABLE IF NOT EXISTS watchdog_fp (
    fp        TEXT PRIMARY KEY,
    n         INTEGER NOT NULL DEFAULT 0,
    convs     TEXT NOT NULL DEFAULT '[]',
    minutes   TEXT NOT NULL DEFAULT '[]',
    last_seen TEXT
);
CREATE TABLE IF NOT EXISTS watchdog_seen_msgs (
    conv_id TEXT,
    msg_id  TEXT,
    PRIMARY KEY (conv_id, msg_id)
);
CREATE TABLE IF NOT EXISTS watchdog_events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    day      TEXT,
    kind     TEXT,
    employee TEXT
);
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
        return cur.rowcount


# ---------------- code mode (auto | manual) ----------------

def code_mode(listing_id):
    r = q1("SELECT mode FROM watchdog_code_mode WHERE listing_id=?", (str(listing_id),))
    return (r or {}).get("mode") or "auto"


def set_code_mode(listing_id, mode, by=""):
    if mode not in ("auto", "manual"):
        raise ValueError("mode must be auto|manual")
    execute("INSERT INTO watchdog_code_mode(listing_id, mode, updated_at, updated_by) "
            "VALUES(?,?,datetime('now'),?) "
            "ON CONFLICT(listing_id) DO UPDATE SET mode=excluded.mode, "
            "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (str(listing_id), mode, by or ""))


def all_code_modes():
    return {r["listing_id"]: r["mode"] for r in q("SELECT listing_id, mode FROM watchdog_code_mode")}


def manual_listing_ids():
    return {r["listing_id"] for r in q("SELECT listing_id FROM watchdog_code_mode WHERE mode='manual'")}


# ---------------- code send log (permanent, idempotent per reservation) ----------------

def log_code_send(rec):
    execute("INSERT OR IGNORE INTO watchdog_code_sends"
            "(listing_id, reservation_id, guest_name, sent_by, sent_at, arrival_ts, on_time, detected_at) "
            "VALUES(?,?,?,?,?,?,?,datetime('now'))",
            (str(rec.get("listing_id") or ""), str(rec.get("reservation_id") or ""),
             rec.get("guest_name") or "", rec.get("sent_by") or "",
             rec.get("sent_at") or "", rec.get("arrival_ts") or "",
             int(bool(rec.get("on_time")))))


def code_sends_since(day_iso):
    return q("SELECT * FROM watchdog_code_sends WHERE detected_at >= ? ORDER BY detected_at",
             (day_iso,))


# ---------------- flag lifecycle + ping dedup ----------------

def flag_get(key):
    return q1("SELECT * FROM watchdog_flag_state WHERE flag_key=?", (key,))


def claim_ping(key, now_iso):
    """True exactly once per flag: first caller stamps pinged_at, later callers get False."""
    execute("INSERT OR IGNORE INTO watchdog_flag_state(flag_key, first_seen, last_seen) "
            "VALUES(?,?,?)", (key, now_iso, now_iso))
    execute("UPDATE watchdog_flag_state SET last_seen=?, resolved_at=NULL WHERE flag_key=?",
            (now_iso, key))
    n = execute("UPDATE watchdog_flag_state SET pinged_at=? WHERE flag_key=? AND pinged_at IS NULL",
                (now_iso, key))
    return n > 0


def reping_due(key, now_iso, hours):
    """True (and re-stamps pinged_at) iff the flag is still unresolved and the last ping
    is older than `hours`. SQLite datetime comparison on ISO strings."""
    n = execute("UPDATE watchdog_flag_state SET pinged_at=?, last_seen=? "
                "WHERE flag_key=? AND resolved_at IS NULL AND pinged_at IS NOT NULL "
                "AND datetime(pinged_at) <= datetime(?, ?)",
                (now_iso, now_iso, key, now_iso, "-%d minutes" % int(hours * 60)))
    return n > 0


def resolve_flag(key, now_iso):
    execute("UPDATE watchdog_flag_state SET resolved_at=? WHERE flag_key=? AND resolved_at IS NULL",
            (now_iso, key))


def open_flag_keys():
    return {r["flag_key"] for r in q("SELECT flag_key FROM watchdog_flag_state WHERE resolved_at IS NULL")}


# ---------------- per-employee daily message stats ----------------

def bump_stat(day, employee, resp_min=None, automated=False):
    execute("INSERT OR IGNORE INTO watchdog_msg_stats(day, employee) VALUES(?,?)",
            (day, employee or ""))
    if automated:
        execute("UPDATE watchdog_msg_stats SET automations_skipped=automations_skipped+1 "
                "WHERE day=? AND employee=?", (day, employee or ""))
    else:
        if resp_min is None:
            execute("UPDATE watchdog_msg_stats SET replies=replies+1 WHERE day=? AND employee=?",
                    (day, employee or ""))
        else:
            execute("UPDATE watchdog_msg_stats SET replies=replies+1, "
                    "resp_min_sum=resp_min_sum+?, resp_min_n=resp_min_n+1 "
                    "WHERE day=? AND employee=?", (float(resp_min), day, employee or ""))


def stats_since(day_iso):
    return q("SELECT employee, SUM(replies) AS replies, SUM(resp_min_sum) AS resp_min_sum, "
             "SUM(resp_min_n) AS resp_min_n, SUM(automations_skipped) AS automations_skipped "
             "FROM watchdog_msg_stats WHERE day >= ? GROUP BY employee", (day_iso,))


# ---------------- automation fingerprints ----------------

_FP_CAP = 12


def fp_bump(fp, conv, minute):
    execute("INSERT OR IGNORE INTO watchdog_fp(fp) VALUES(?)", (fp,))
    rec = q1("SELECT * FROM watchdog_fp WHERE fp=?", (fp,))
    convs = json.loads(rec.get("convs") or "[]")
    minutes = json.loads(rec.get("minutes") or "[]")
    if conv not in convs:
        convs = (convs + [conv])[-_FP_CAP:]
    minutes = (minutes + [int(minute)])[-_FP_CAP:]
    execute("UPDATE watchdog_fp SET n=n+1, convs=?, minutes=?, last_seen=datetime('now') WHERE fp=?",
            (json.dumps(convs), json.dumps(minutes), fp))


def fp_get(fp):
    rec = q1("SELECT * FROM watchdog_fp WHERE fp=?", (fp,))
    if not rec:
        return None
    rec["convs"] = json.loads(rec.get("convs") or "[]")
    rec["minutes"] = json.loads(rec.get("minutes") or "[]")
    return rec


# ---------------- generic events (e.g. escalation claims) ----------------

def log_event(day, kind, employee):
    execute("INSERT INTO watchdog_events(day, kind, employee) VALUES(?,?,?)",
            (day, kind, employee or ""))


def events_since(day_iso, kind):
    return q("SELECT * FROM watchdog_events WHERE day >= ? AND kind = ?", (day_iso, kind))


# ---------------- seen messages (stats pass idempotency) ----------------

def msg_seen(conv_id, msg_id):
    return q1("SELECT 1 AS x FROM watchdog_seen_msgs WHERE conv_id=? AND msg_id=?",
              (str(conv_id), str(msg_id))) is not None


def mark_msg_seen(conv_id, msg_id):
    execute("INSERT OR IGNORE INTO watchdog_seen_msgs(conv_id, msg_id) VALUES(?,?)",
            (str(conv_id), str(msg_id)))
