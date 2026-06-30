"""
schedule.db — schedule_* tables inside the SAME brain.db SQLite file (reuses brain.db.connect
for the proven NO-WAL / journal_mode=DELETE / busy_timeout rules). Build spec §3.

Tables: schedule_employees, schedule_apartments, schedule_coverage_overrides, schedule_settings,
schedule_absences (Ouja ad-hoc-leave extension). FK integrity:
  * deleting an employee who still owns apartments is BLOCKED (checked in the route for a clean
    Arabic message; declared RESTRICT here as a backstop).
  * deleting an apartment CASCADEs its coverage overrides.
"""

import datetime
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedule_employees (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    off_day     INTEGER,                 -- 0=الأحد .. 6=السبت (NULL = no day off)
    color       TEXT,
    emoji       TEXT,                    -- per-employee marker shown after the apartment name
    sort_order  INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS schedule_apartments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    owner_id    INTEGER REFERENCES schedule_employees(id) ON DELETE RESTRICT,
    listing_id  INTEGER,                 -- Hostaway listingMapId this apartment maps to (NULL = unlinked)
    sort_order  INTEGER DEFAULT 0,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS schedule_coverage_overrides (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    day_of_week          INTEGER,
    apartment_id         INTEGER REFERENCES schedule_apartments(id) ON DELETE CASCADE,
    covering_employee_id INTEGER REFERENCES schedule_employees(id) ON DELETE CASCADE,
    created_at           TEXT,
    UNIQUE(day_of_week, apartment_id)
);
CREATE TABLE IF NOT EXISTS schedule_settings (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    title     TEXT,
    subtitle  TEXT
);
CREATE TABLE IF NOT EXISTS schedule_absences (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    start_date  TEXT NOT NULL,
    end_date    TEXT NOT NULL,
    type        TEXT,
    status      TEXT DEFAULT 'approved',
    note        TEXT,
    created_by  TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sched_apt_owner ON schedule_apartments(owner_id);
CREATE INDEX IF NOT EXISTS idx_sched_ov_day    ON schedule_coverage_overrides(day_of_week);
CREATE INDEX IF NOT EXISTS idx_sched_abs_date  ON schedule_absences(start_date, end_date);
"""

_inited = set()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with closing(_bdb.connect()) as cx:
        cx.executescript(SCHEMA)
        _migrate(cx)
        cx.commit()
    _inited.add(path)


def _migrate(cx):
    """Additive column migrations for an already-existing brain.db (CREATE TABLE IF NOT EXISTS
    never adds columns to a table that already exists). Each ALTER is guarded by table_info."""
    cols = {r["name"] for r in cx.execute("PRAGMA table_info(schedule_employees)").fetchall()}
    if "emoji" not in cols:
        cx.execute("ALTER TABLE schedule_employees ADD COLUMN emoji TEXT")
        # Backfill the default emoji for the known seed employees so an existing roster isn't all
        # blank after the upgrade. Only fills NULL/blank — never overwrites an owner-set emoji.
        from . import seed as _seed
        for e in _seed.EMPLOYEES:
            cx.execute("UPDATE schedule_employees SET emoji=? WHERE name=? AND (emoji IS NULL OR emoji='')",
                       (e.get("emoji"), e["name"]))
    acols = {r["name"] for r in cx.execute("PRAGMA table_info(schedule_apartments)").fetchall()}
    if "listing_id" not in acols:
        cx.execute("ALTER TABLE schedule_apartments ADD COLUMN listing_id INTEGER")


def reset_init_cache():
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


def executescript(sql):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.executescript(sql)
        cx.commit()


# ---- typed readers ----

def employees():
    return q("SELECT * FROM schedule_employees ORDER BY sort_order, id")


def apartments():
    return q("SELECT * FROM schedule_apartments ORDER BY sort_order, id")


def overrides():
    return q("SELECT * FROM schedule_coverage_overrides")


def absences_on(date_iso):
    return q("SELECT * FROM schedule_absences WHERE status='approved' "
             "AND start_date<=? AND end_date>=?", (date_iso, date_iso))


def settings():
    return q1("SELECT * FROM schedule_settings WHERE id=1")
