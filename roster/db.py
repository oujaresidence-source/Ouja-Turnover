"""
roster.db — roster tables living inside the SAME brain.db SQLite file.

We deliberately REUSE brain.db's connection helper (brain.db.connect) so we inherit its
hard-won rules: NORMAL locking + busy_timeout + journal_mode=DELETE (NO WAL — the Railway
volume can't back WAL's -shm file → "disk I/O error"; NO locking_mode=EXCLUSIVE — it holds
the lock for the connection's life → "database is locked" under the two-loop process). Every
call opens a short-lived connection via `with closing(connect())` and commits immediately.

Tables (build spec §3): employees, properties, absences, assignment_log, coverage_ledger.
"""

import datetime
from contextlib import closing

from brain import db as _bdb   # reuse the proven connection + path resolution


SCHEMA = """
CREATE TABLE IF NOT EXISTS roster_employees (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name_ar      TEXT NOT NULL,
    initial_ar   TEXT,
    weekly_off   TEXT DEFAULT '',          -- 'sun'..'sat' | '' (no day off)
    role         TEXT DEFAULT 'employee',  -- owner|ops_manager|team_leader|employee
    is_active    INTEGER DEFAULT 1,
    discord_id   TEXT,
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS roster_properties (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hostaway_listing_id TEXT,
    display_name_ar     TEXT NOT NULL,
    primary_owner_id    INTEGER,
    zone                TEXT,
    turnover_weight     REAL DEFAULT 1,
    status              TEXT DEFAULT 'active',  -- active|paused|offboarded
    created_at          TEXT
);
CREATE TABLE IF NOT EXISTS roster_absences (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id  INTEGER NOT NULL,
    start_date   TEXT NOT NULL,
    end_date     TEXT NOT NULL,
    type         TEXT,                     -- sick|vacation|emergency|half_day|late|training|no_show|unpaid
    status       TEXT DEFAULT 'approved',  -- requested|approved|rejected
    note         TEXT,
    created_by   TEXT,
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS roster_assignment_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT NOT NULL,
    property_id       INTEGER NOT NULL,
    responsible_id    INTEGER,
    is_coverage       INTEGER DEFAULT 0,
    original_owner_id INTEGER,
    locked            INTEGER DEFAULT 0,
    override_by       TEXT,
    override_reason   TEXT,
    computed_at       TEXT
);
CREATE TABLE IF NOT EXISTS roster_coverage_ledger (
    employee_id   INTEGER NOT NULL,
    date          TEXT NOT NULL,
    covered_count INTEGER DEFAULT 0,
    PRIMARY KEY (employee_id, date)
);
CREATE INDEX IF NOT EXISTS idx_roster_abs_emp  ON roster_absences(employee_id);
CREATE INDEX IF NOT EXISTS idx_roster_abs_date ON roster_absences(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_roster_log_date ON roster_assignment_log(date);
CREATE INDEX IF NOT EXISTS idx_roster_log_lock ON roster_assignment_log(date, locked);
"""

# Columns added after first release — applied to already-deployed brain.db files.
_MIGRATIONS = [
    # (table, column, ALTER sql)
]

_inited = set()


def _ensure():
    """Create roster tables once per resolved db path. Safe to call repeatedly."""
    path = _bdb.db_path()
    if path in _inited:
        return
    with closing(_bdb.connect()) as cx:
        cx.executescript(SCHEMA)
        for table, col, sql in _MIGRATIONS:
            try:
                cols = {r[1] for r in cx.execute("PRAGMA table_info(%s)" % table).fetchall()}
                if col not in cols:
                    cx.execute(sql)
            except Exception:
                pass
        cx.commit()
    _inited.add(path)


def reset_init_cache():
    """Tests point brain.db at a temp file; forget which paths we've created tables in."""
    _inited.clear()


def now_iso():
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


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


def executemany(sql, seq):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.executemany(sql, seq)
        cx.commit()


# ---- typed readers used by the engine + routes ----

def employees(active_only=False):
    sql = "SELECT * FROM roster_employees"
    if active_only:
        sql += " WHERE is_active=1"
    return q(sql + " ORDER BY id")


def properties(include_inactive=True):
    sql = "SELECT * FROM roster_properties"
    if not include_inactive:
        sql += " WHERE status='active'"
    return q(sql + " ORDER BY id")


def absences_on(date_iso):
    """All absences whose [start_date,end_date] window contains date_iso."""
    return q("SELECT * FROM roster_absences WHERE start_date<=? AND end_date>=?",
             (date_iso, date_iso))


def locks_on(date_iso):
    """Locked overrides recorded for a specific date."""
    return q("SELECT property_id, responsible_id, original_owner_id, override_by, "
             "override_reason FROM roster_assignment_log WHERE date=? AND locked=1",
             (date_iso,))
