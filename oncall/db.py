# -*- coding: utf-8 -*-
"""
oncall.db — «المناوبة» storage inside the SAME brain.db every other package uses.

Connection rules are brain.db's (no WAL, journal_mode=DELETE, one short connection per call
via `with closing(connect())`) — read brain/db.py before changing anything here.

THREE RULES ARE ENFORCED BY THE SCHEMA, NOT BY CAREFUL CODE
  1. One check per (slot, time) — UNIQUE(slot_id, due_at). A double tick cannot ping twice.
  2. One issue per Discord reference — UNIQUE(ref). A re-fired hook cannot double-own.
  3. One slot per start time per night — UNIQUE(date, start_min).
Every table is prefixed `oncall_`.
"""

import datetime
import json
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS oncall_config (
    key     TEXT PRIMARY KEY,
    value   TEXT,
    set_by  TEXT,
    set_at  TEXT
);
CREATE TABLE IF NOT EXISTS oncall_nights (
    date          TEXT PRIMARY KEY,           -- 'YYYY-MM-DD' (the evening)
    status        TEXT NOT NULL,              -- published | locked
    published_at  TEXT,
    locked_at     TEXT,
    message_id    TEXT,                       -- the schedule post in «المناوبة»
    roster_json   TEXT,                       -- [{name, ok, why}] as decided at publish time
    summary_at    TEXT
);
CREATE TABLE IF NOT EXISTS oncall_slots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT NOT NULL,
    employee     TEXT NOT NULL,
    employee_did TEXT,
    start_min    INTEGER NOT NULL,
    end_min      INTEGER NOT NULL,
    source       TEXT NOT NULL DEFAULT 'auto',  -- auto | swap | edit
    edited_by    TEXT,
    edit_reason  TEXT,
    reminded_at  TEXT,
    handover_at  TEXT,
    UNIQUE(date, start_min)
);
CREATE TABLE IF NOT EXISTS oncall_swaps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT NOT NULL,
    slot_id     INTEGER NOT NULL,
    requester   TEXT NOT NULL,
    requester_did TEXT,
    target      TEXT NOT NULL,
    target_did  TEXT,
    kind        TEXT NOT NULL,               -- exchange | takeover
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|accepted|declined|expired
    created_at  TEXT,
    decided_at  TEXT,
    message_id  TEXT                          -- the DM that carries «موافق / لا»
);
CREATE TABLE IF NOT EXISTS oncall_checks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id       INTEGER NOT NULL,
    date          TEXT NOT NULL,
    employee      TEXT NOT NULL,
    employee_did  TEXT,
    due_at        TEXT NOT NULL,
    sent_at       TEXT,
    dm_ok         INTEGER DEFAULT 0,
    channel_ok    INTEGER DEFAULT 0,
    dm_message_id TEXT,
    ch_message_id TEXT,
    answered_at   TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending|answered|missed|late|voided
    void_reason   TEXT,
    decided_at    TEXT,
    UNIQUE(slot_id, due_at)
);
CREATE TABLE IF NOT EXISTS oncall_issues (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,            -- escalation | maint
    ref             TEXT NOT NULL UNIQUE,     -- escalation card message id | ticket channel id
    title           TEXT,
    owner           TEXT NOT NULL,
    owner_did       TEXT,
    slot_id         INTEGER,
    date            TEXT,
    opened_at       TEXT NOT NULL,
    claimed_at      TEXT,
    claimed_by      TEXT,
    helper          TEXT,
    resolved_at     TEXT,
    resolved_by     TEXT,
    last_update_at  TEXT,
    claim_alerted_at TEXT,
    stale_alerted_night TEXT,
    note_message_id TEXT                      -- our «المناوب المسؤول» line (carries «انحلّت»)
);
CREATE TABLE IF NOT EXISTS oncall_events (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    at       TEXT NOT NULL,
    kind     TEXT NOT NULL,
    employee TEXT,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS oncall_checks_date ON oncall_checks(date, employee);
CREATE INDEX IF NOT EXISTS oncall_events_kind ON oncall_events(kind, at);
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


def iso(dt):
    return dt.isoformat(timespec="seconds") if dt is not None else None


def parse(s):
    return datetime.datetime.fromisoformat(s) if s else None


# ------------------------------------------------------------------ thin sql helpers

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
    """Returns (lastrowid, rowcount)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid, cur.rowcount


@contextmanager
def transaction():
    _ensure()
    with closing(_bdb.connect()) as cx:
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise


def counts():
    out = {}
    for t in ("oncall_config", "oncall_nights", "oncall_slots", "oncall_swaps",
              "oncall_checks", "oncall_issues", "oncall_events"):
        out[t] = (q1("SELECT COUNT(*) c FROM %s" % t) or {}).get("c", 0)
    return out


# ------------------------------------------------------------------ config

def config_get(key, default=""):
    r = q1("SELECT value FROM oncall_config WHERE key=?", (key,))
    v = (r or {}).get("value")
    return default if v is None else v


def config_set(key, value, by="", at=""):
    execute("INSERT INTO oncall_config(key,value,set_by,set_at) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, set_by=excluded.set_by, "
            "set_at=excluded.set_at", (key, value, by or "", at or ""))


def config_row(key):
    return q1("SELECT * FROM oncall_config WHERE key=?", (key,))


# ------------------------------------------------------------------ events

def log(kind, at, employee="", detail=None):
    execute("INSERT INTO oncall_events(at,kind,employee,detail) VALUES(?,?,?,?)",
            (iso(at) if not isinstance(at, str) else at, kind, employee or "",
             json.dumps(detail, ensure_ascii=False) if not isinstance(detail, str) else detail))


def events(kind=None, limit=200):
    if kind:
        return q("SELECT * FROM oncall_events WHERE kind=? ORDER BY id DESC LIMIT ?",
                 (kind, int(limit)))
    return q("SELECT * FROM oncall_events ORDER BY id DESC LIMIT ?", (int(limit),))


def downtimes(since):
    """[(start, end)] bot-down windows recorded by the heartbeat, newest first."""
    out = []
    for r in q("SELECT detail FROM oncall_events WHERE kind='downtime' AND at>=? ORDER BY id DESC",
               (iso(since),)):
        try:
            d = json.loads(r["detail"] or "{}")
            out.append((parse(d["from"]), parse(d["to"])))
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ nights + slots

def night(date_iso):
    return q1("SELECT * FROM oncall_nights WHERE date=?", (date_iso,))


def publish_night(date_iso, slots, roster, at):
    """Write a night and its slots in ONE transaction. Returns False if it already exists
    (a second tick, or a restart mid-publish, can never rebuild a published night)."""
    with transaction() as cx:
        cur = cx.execute("INSERT OR IGNORE INTO oncall_nights(date,status,published_at,roster_json)"
                         " VALUES(?,?,?,?)",
                         (date_iso, "published", iso(at), json.dumps(roster, ensure_ascii=False)))
        if cur.rowcount != 1:
            return False
        for s in slots:
            cx.execute("INSERT INTO oncall_slots(date,employee,employee_did,start_min,end_min,source)"
                       " VALUES(?,?,?,?,?, 'auto')",
                       (date_iso, s["employee"], s.get("employee_did") or "",
                        int(s["start_min"]), int(s["end_min"])))
    return True


def set_night_message(date_iso, message_id):
    execute("UPDATE oncall_nights SET message_id=? WHERE date=?", (str(message_id), date_iso))


def lock_night(date_iso, at):
    """published -> locked. Returns True only for the tick that actually flipped it."""
    _rid, n = execute("UPDATE oncall_nights SET status='locked', locked_at=? "
                      "WHERE date=? AND status='published'", (iso(at), date_iso))
    return n == 1


def mark_summary(date_iso, at):
    _rid, n = execute("UPDATE oncall_nights SET summary_at=? WHERE date=? AND summary_at IS NULL",
                      (iso(at), date_iso))
    return n == 1


def slots_for(date_iso):
    return q("SELECT * FROM oncall_slots WHERE date=? ORDER BY start_min", (date_iso,))


def slot(slot_id):
    return q1("SELECT * FROM oncall_slots WHERE id=?", (int(slot_id),))


def set_slot_employee(slot_id, employee, did, source, by="", reason=""):
    execute("UPDATE oncall_slots SET employee=?, employee_did=?, source=?, edited_by=?, "
            "edit_reason=?, reminded_at=NULL WHERE id=?",
            (employee, did or "", source, by or "", reason or "", int(slot_id)))
    return slot(slot_id)


def mark_slot(slot_id, field, at):
    """reminded_at | handover_at, set once. True only for the first caller."""
    assert field in ("reminded_at", "handover_at")
    _rid, n = execute("UPDATE oncall_slots SET %s=? WHERE id=? AND %s IS NULL" % (field, field),
                      (iso(at), int(slot_id)))
    return n == 1


def history(before_date_iso, nights=7):
    """[{date, slots}] for the `nights` published nights before the given date."""
    dates = [r["date"] for r in q("SELECT date FROM oncall_nights WHERE date<? "
                                  "ORDER BY date DESC LIMIT ?", (before_date_iso, int(nights)))]
    return [{"date": d, "slots": slots_for(d)} for d in sorted(dates)]


# ------------------------------------------------------------------ swaps

def create_swap(date_iso, slot_id, requester, requester_did, target, target_did, kind, at):
    rid, _n = execute("INSERT INTO oncall_swaps(date,slot_id,requester,requester_did,target,"
                      "target_did,kind,status,created_at) VALUES(?,?,?,?,?,?,?, 'pending', ?)",
                      (date_iso, int(slot_id), requester, requester_did or "", target,
                       target_did or "", kind, iso(at)))
    return swap(rid)


def swap(swap_id):
    return q1("SELECT * FROM oncall_swaps WHERE id=?", (int(swap_id),))


def swap_by_message(message_id):
    return q1("SELECT * FROM oncall_swaps WHERE message_id=?", (str(message_id),))


def set_swap_message(swap_id, message_id):
    execute("UPDATE oncall_swaps SET message_id=? WHERE id=?", (str(message_id), int(swap_id)))


def pending_swap_for_slot(slot_id):
    return q1("SELECT * FROM oncall_swaps WHERE slot_id=? AND status='pending'", (int(slot_id),))


def pending_swaps_on(date_iso):
    return q("SELECT * FROM oncall_swaps WHERE date=? AND status='pending'", (date_iso,))


def decide_swap(swap_id, status, at):
    """pending -> status. True only for the press that actually decided it."""
    _rid, n = execute("UPDATE oncall_swaps SET status=?, decided_at=? WHERE id=? AND status='pending'",
                      (status, iso(at), int(swap_id)))
    return n == 1


# ------------------------------------------------------------------ checks

def claim_check(slot_row, due_at, status="pending", void_reason=""):
    """INSERT OR IGNORE: returns the new row, or None when this (slot, time) already exists."""
    rid, n = execute("INSERT OR IGNORE INTO oncall_checks(slot_id,date,employee,employee_did,due_at,"
                     "status,void_reason) VALUES(?,?,?,?,?,?,?)",
                     (int(slot_row["id"]), slot_row["date"], slot_row["employee"],
                      slot_row.get("employee_did") or "", iso(due_at), status, void_reason))
    return check(rid) if n == 1 else None


def check(check_id):
    return q1("SELECT * FROM oncall_checks WHERE id=?", (int(check_id),))


def check_by_message(message_id):
    m = str(message_id)
    return q1("SELECT * FROM oncall_checks WHERE dm_message_id=? OR ch_message_id=?", (m, m))


def set_check_delivery(check_id, dm_ok, channel_ok, dm_mid, ch_mid, at):
    execute("UPDATE oncall_checks SET sent_at=?, dm_ok=?, channel_ok=?, dm_message_id=?, "
            "ch_message_id=? WHERE id=?",
            (iso(at), 1 if dm_ok else 0, 1 if channel_ok else 0,
             str(dm_mid or ""), str(ch_mid or ""), int(check_id)))


def pending_checks():
    return q("SELECT * FROM oncall_checks WHERE status='pending' ORDER BY due_at")


def decide_check(check_id, status, at, void_reason="", answered_at=None):
    """pending -> status. True only for whoever decided it first (button vs tick race)."""
    _rid, n = execute("UPDATE oncall_checks SET status=?, decided_at=?, void_reason=?, "
                      "answered_at=COALESCE(?, answered_at) WHERE id=? AND status='pending'",
                      (status, iso(at), void_reason or "", iso(answered_at), int(check_id)))
    return n == 1


def mark_late(check_id, at):
    execute("UPDATE oncall_checks SET status='late', answered_at=? WHERE id=? AND status='missed'",
            (iso(at), int(check_id)))


def misses_on(employee, date_iso):
    return (q1("SELECT COUNT(*) c FROM oncall_checks WHERE employee=? AND date=? "
               "AND status IN ('missed','late')", (employee, date_iso)) or {}).get("c", 0)


def checks_on(date_iso):
    return q("SELECT * FROM oncall_checks WHERE date=? ORDER BY due_at", (date_iso,))


def last_answered(employee, date_iso):
    return q1("SELECT * FROM oncall_checks WHERE employee=? AND date=? AND status='answered' "
              "ORDER BY due_at DESC LIMIT 1", (employee, date_iso))


def recent_problems(limit=60):
    return q("SELECT * FROM oncall_checks WHERE status IN ('missed','late','voided') "
             "ORDER BY due_at DESC LIMIT ?", (int(limit),))


# ------------------------------------------------------------------ issues

def open_issue(kind, ref, title, owner, owner_did, slot_id, date_iso, at):
    """Returns the issue row, or None if this ref already has one (the hook fired twice)."""
    rid, n = execute("INSERT OR IGNORE INTO oncall_issues(kind,ref,title,owner,owner_did,slot_id,"
                     "date,opened_at,last_update_at) VALUES(?,?,?,?,?,?,?,?,?)",
                     (kind, str(ref), title or "", owner, owner_did or "", slot_id, date_iso,
                      iso(at), iso(at)))
    return issue_by_ref(ref) if n == 1 else None


def issue_by_ref(ref):
    return q1("SELECT * FROM oncall_issues WHERE ref=?", (str(ref),))


def issue_by_note(message_id):
    return q1("SELECT * FROM oncall_issues WHERE note_message_id=?", (str(message_id),))


def set_issue_note(ref, message_id):
    execute("UPDATE oncall_issues SET note_message_id=? WHERE ref=?", (str(message_id), str(ref)))


def claim_issue(ref, by, helper, at):
    execute("UPDATE oncall_issues SET claimed_at=COALESCE(claimed_at, ?), "
            "claimed_by=COALESCE(claimed_by, ?), helper=COALESCE(helper, ?), last_update_at=? "
            "WHERE ref=? AND resolved_at IS NULL",
            (iso(at), by, helper, iso(at), str(ref)))


def touch_issue(ref, at):
    execute("UPDATE oncall_issues SET last_update_at=? WHERE ref=? AND resolved_at IS NULL",
            (iso(at), str(ref)))


def resolve_issue(ref, by, at):
    _rid, n = execute("UPDATE oncall_issues SET resolved_at=?, resolved_by=? "
                      "WHERE ref=? AND resolved_at IS NULL", (iso(at), by, str(ref)))
    return n == 1


def open_issues():
    return q("SELECT * FROM oncall_issues WHERE resolved_at IS NULL ORDER BY opened_at")


def recent_issues(limit=60):
    return q("SELECT * FROM oncall_issues ORDER BY id DESC LIMIT ?", (int(limit),))


def mark_issue(ref, field, value):
    assert field in ("claim_alerted_at", "stale_alerted_night")
    execute("UPDATE oncall_issues SET %s=? WHERE ref=?" % field, (value, str(ref)))
