# -*- coding: utf-8 -*-
"""
recovery.db — «استرداد التجربة» storage, inside the SAME brain.db every other package uses.

Connection rules are NOT re-invented here. brain/db.py already encodes the fixes that cost a
live outage in June — no WAL, journal_mode=DELETE, ordinary locking, one short-lived
connection per call via `with closing(connect())`. Read its docstring before changing
anything in this file.

TWO RULES ARE ENFORCED BY THE SCHEMA, NOT BY CAREFUL CODE

  1. ONE TICKET PER RESERVATION, EVER — UNIQUE(reservation_id) on recovery_tickets.
     §2 says "no open recovery ticket already exists for this reservation_id" and §15.1 says
     a guest scored 6.2 produces exactly one ticket. A Python check would hold only until the
     16:00 job overlaps a restart, or an in-house guest fires the immediate path while the
     batch is mid-flight. The INSERT simply fails instead.

  2. ONE ANALYSIS PER (reservation, conversation) — PRIMARY KEY(reservation_id, content_hash)
     on recovery_analysis_cache. This is §3.1's cost guarantee made structural: a re-run
     cannot buy a second API call for a conversation that has not changed, no matter how the
     calling code is refactored later.

Every table is prefixed `recovery_`. In a database shared with brain_*, schedule_*, ops_*,
decor_* and the finance tables, a table called `tickets` is an accident waiting to happen.
"""

import datetime
import json
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS recovery_tickets (
    id                       TEXT PRIMARY KEY,          -- 'rc_<epoch ms>_<seq>'
    reservation_id           TEXT NOT NULL UNIQUE,      -- <<< one ticket per reservation, ever
    conversation_id          TEXT,
    listing_id               INTEGER,
    guest_name               TEXT,
    guest_phone_e164         TEXT,
    phone_source             TEXT,                      -- hostaway | masked | none
    unit_name                TEXT,
    channel                  TEXT,                      -- Airbnb | Direct | Elite | ...
    checkin                  TEXT,
    checkout                 TEXT,
    nights                   INTEGER,
    total_price              REAL,
    repeat_guest             INTEGER DEFAULT 0,
    in_house                 INTEGER DEFAULT 0,
    score                    REAL,

    -- the extraction (§3.5)
    headline_ar              TEXT,
    timeline                 TEXT DEFAULT '[]',         -- JSON
    quotes                   TEXT DEFAULT '[]',         -- JSON
    root_cause               TEXT,
    physical_issue           INTEGER DEFAULT 0,
    already_promised_ar      TEXT,
    unresolved_ar            TEXT,
    severity                 INTEGER,
    call_opener_ar           TEXT,

    -- assignment (§4)
    assigned_agent_id        TEXT,
    assigned_agent_name      TEXT,
    conflict_excluded_agent_id   TEXT,
    conflict_excluded_agent_name TEXT,
    assignment_reason        TEXT,                      -- equity | conflict_reassigned | all_conflicted
    unit_owner_name          TEXT,
    month_key                TEXT,

    status                   TEXT NOT NULL DEFAULT 'OPEN',
    created_at               TEXT NOT NULL,
    posted_at                TEXT,
    due_at                   TEXT,

    -- contact (§8)
    call_token               TEXT UNIQUE,
    call_link_opened_at      TEXT,
    call_attempts            INTEGER NOT NULL DEFAULT 0,
    contacted_at             TEXT,
    contact_outcome          TEXT,
    contact_note             TEXT,
    escalation_offered       INTEGER DEFAULT 0,
    compensation_sar         REAL,

    resolved_at              TEXT,
    resolution_note          TEXT,
    maintenance_ticket_id    TEXT,
    maintenance_channel_id   TEXT,
    escalated_at             TEXT,
    followup_due             TEXT,
    sla_breached             INTEGER NOT NULL DEFAULT 0,

    thread_id                TEXT,                      -- the ticket ROOM's channel id
    message_id               TEXT,
    dryrun                   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS recovery_tickets_status ON recovery_tickets(status);
CREATE INDEX IF NOT EXISTS recovery_tickets_month  ON recovery_tickets(month_key);
CREATE INDEX IF NOT EXISTS recovery_tickets_unit   ON recovery_tickets(listing_id, created_at);

CREATE TABLE IF NOT EXISTS recovery_agent_stats (
    agent_id            TEXT NOT NULL,
    month_key           TEXT NOT NULL,
    agent_name          TEXT,
    assigned_count      INTEGER NOT NULL DEFAULT 0,
    contacted_count     INTEGER NOT NULL DEFAULT 0,
    resolved_count      INTEGER NOT NULL DEFAULT 0,
    sla_breached_count  INTEGER NOT NULL DEFAULT 0,
    conflict_debt       INTEGER NOT NULL DEFAULT 0,
    last_assigned_at    TEXT,
    PRIMARY KEY(agent_id, month_key)
);

-- §3.1 — the whole cost guarantee. The key is the reservation PLUS the hash of the
-- COMPACTED conversation, so a new template message or a bare «شكرا» (both dropped by
-- engine.compact) cannot buy a second call.
CREATE TABLE IF NOT EXISTS recovery_analysis_cache (
    reservation_id  TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    model           TEXT,
    output_json     TEXT,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    calls           INTEGER DEFAULT 1,
    escalated       INTEGER DEFAULT 0,
    cost_sar        REAL DEFAULT 0,
    compacted_chars INTEGER DEFAULT 0,
    raw_chars       INTEGER DEFAULT 0,
    created_at      TEXT,
    PRIMARY KEY(reservation_id, content_hash)
);

-- Every candidate the engine looked at and did NOT open a ticket for, with the reason.
-- Without this, «ليش ما فتحت تذكرة لهذا الضيف؟» has no answer.
CREATE TABLE IF NOT EXISTS recovery_skips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    at              TEXT NOT NULL,
    reservation_id  TEXT,
    guest_name      TEXT,
    unit_name       TEXT,
    score           REAL,
    reason          TEXT
);
"""

_inited = set()
_init_lock = threading.Lock()

TZ_NAME = "Asia/Riyadh"


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:                 # two threads racing the first init would run SCHEMA twice
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZ_NAME)
    except Exception:
        return datetime.timezone(datetime.timedelta(hours=3))


def now_dt():
    return datetime.datetime.now(_tz())


def now_iso():
    return now_dt().isoformat(timespec="seconds")


def month_key(dt=None):
    return (dt or now_dt()).strftime("%Y-%m")


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
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid


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


# ------------------------------------------------------------------ analysis cache (§3.1)

def cached_analysis(reservation_id, content_hash):
    row = q1("SELECT * FROM recovery_analysis_cache WHERE reservation_id=? AND content_hash=?",
             (str(reservation_id), str(content_hash)))
    if not row:
        return None
    try:
        row["output"] = json.loads(row.get("output_json") or "null")
    except Exception:
        row["output"] = None
    return row


def save_analysis(reservation_id, content_hash, output, meta, raw_chars=0, compacted_chars=0):
    execute(
        "INSERT OR REPLACE INTO recovery_analysis_cache"
        "(reservation_id,content_hash,model,output_json,input_tokens,output_tokens,calls,"
        " escalated,cost_sar,compacted_chars,raw_chars,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(reservation_id), str(content_hash), (meta or {}).get("model"),
         json.dumps(output, ensure_ascii=False),
         int((meta or {}).get("input_tokens") or 0),
         int((meta or {}).get("output_tokens") or 0),
         int((meta or {}).get("calls") or 1),
         1 if (meta or {}).get("escalated") else 0,
         float((meta or {}).get("cost_sar") or 0),
         int(compacted_chars or 0), int(raw_chars or 0), now_iso()))


def month_cost(mk=None):
    """§12's money line. Cache rows are keyed by reservation, not month, so the month is
    taken from created_at — a cache HIT in August for a call billed in July correctly bills
    nothing again, which is the whole point of the cache."""
    mk = mk or month_key()
    row = q1("SELECT COUNT(*) n, COALESCE(SUM(input_tokens),0) itok,"
             " COALESCE(SUM(output_tokens),0) otok, COALESCE(SUM(cost_sar),0) sar,"
             " COALESCE(SUM(calls),0) calls, COALESCE(SUM(escalated),0) escalated"
             " FROM recovery_analysis_cache WHERE substr(created_at,1,7)=?", (mk,))
    return row or {"n": 0, "itok": 0, "otok": 0, "sar": 0, "calls": 0, "escalated": 0}


# ------------------------------------------------------------------ agent stats (§4)

def agent_stats(month_key_):
    rows = q("SELECT * FROM recovery_agent_stats WHERE month_key=?", (month_key_,))
    return {r["agent_id"]: r for r in rows}


def stats_map(month_key_):
    """The shape engine.choose_agent expects."""
    return {aid: {"assigned_count": r.get("assigned_count") or 0,
                  "conflict_debt": r.get("conflict_debt") or 0,
                  "last_assigned_at": r.get("last_assigned_at")}
            for aid, r in agent_stats(month_key_).items()}


def _upsert_stat(agent_id, month_key_, agent_name=None):
    execute("INSERT OR IGNORE INTO recovery_agent_stats(agent_id,month_key,agent_name)"
            " VALUES(?,?,?)", (str(agent_id), month_key_, agent_name))


def bump_assigned(agent_id, month_key_, at_iso, agent_name=None):
    _upsert_stat(agent_id, month_key_, agent_name)
    execute("UPDATE recovery_agent_stats SET assigned_count=assigned_count+1,"
            " last_assigned_at=?, conflict_debt=MAX(0, conflict_debt-1)"
            " WHERE agent_id=? AND month_key=?", (at_iso, str(agent_id), month_key_))


def bump_conflict_debt(agent_id, month_key_, agent_name=None):
    _upsert_stat(agent_id, month_key_, agent_name)
    execute("UPDATE recovery_agent_stats SET conflict_debt=conflict_debt+1"
            " WHERE agent_id=? AND month_key=?", (str(agent_id), month_key_))


def bump_counter(agent_id, month_key_, column):
    if column not in ("contacted_count", "resolved_count", "sla_breached_count"):
        raise ValueError("refusing to update an unknown column: %r" % (column,))
    _upsert_stat(agent_id, month_key_)
    execute("UPDATE recovery_agent_stats SET %s=%s+1 WHERE agent_id=? AND month_key=?"
            % (column, column), (str(agent_id), month_key_))


# ------------------------------------------------------------------ tickets

def open_ticket_for(reservation_id):
    return q1("SELECT * FROM recovery_tickets WHERE reservation_id=?", (str(reservation_id),))


def has_open_ticket(reservation_id):
    return open_ticket_for(reservation_id) is not None


def unit_ticket_count(listing_id, since_iso):
    """§9's repeat-unit detector."""
    row = q1("SELECT COUNT(*) n FROM recovery_tickets WHERE listing_id=? AND created_at>=?",
             (listing_id, since_iso))
    return int((row or {}).get("n") or 0)


def log_skip(cand, reason):
    execute("INSERT INTO recovery_skips(at,reservation_id,guest_name,unit_name,score,reason)"
            " VALUES(?,?,?,?,?,?)",
            (now_iso(), str(cand.get("reservation_id") or ""), cand.get("guest_name"),
             cand.get("unit_name"), cand.get("score"), reason))
