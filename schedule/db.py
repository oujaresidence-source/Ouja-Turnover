"""
schedule.db — schedule_* tables inside the SAME brain.db SQLite file (reuses brain.db.connect
for the proven NO-WAL / journal_mode=DELETE / busy_timeout rules). Build spec §3.

Tables: schedule_employees, schedule_apartments, schedule_coverage_overrides, schedule_settings,
schedule_absences (Ouja ad-hoc-leave extension), schedule_date_overrides (leave-plan pins for ONE
concrete date — the primitive the «مخطط الإجازات» planner is built on). FK integrity:
  * deleting an employee who still owns apartments is BLOCKED (checked in the route for a clean
    Arabic message; declared RESTRICT here as a backstop).
  * deleting an apartment CASCADEs its coverage overrides AND its date pins.

A NEW table needs no _migrate entry: SCHEMA runs on every _ensure and CREATE TABLE IF NOT EXISTS
adds it to an already-existing brain.db. _migrate is only for columns added to a table that
already exists.
"""

import datetime
import threading
from contextlib import closing, contextmanager

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
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    title              TEXT,
    subtitle           TEXT,
    max_units_per_day  INTEGER,        -- advisory overload cap  (NULL = not computed yet)
    max_minutes_per_day INTEGER,       -- PRIMARY overload cap   (NULL = not computed yet)
    caps_source        TEXT,           -- 'observed' (p90 of our own history) | 'manual'
    caps_computed_at   TEXT
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
CREATE TABLE IF NOT EXISTS schedule_date_overrides (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    date                 TEXT NOT NULL,          -- YYYY-MM-DD, ONE concrete day (not a weekday)
    apartment_id         INTEGER REFERENCES schedule_apartments(id) ON DELETE CASCADE,
    covering_employee_id INTEGER REFERENCES schedule_employees(id)  ON DELETE CASCADE,
    plan_id              INTEGER,                -- groups a whole leave plan for one-click undo
    note                 TEXT,
    created_by           TEXT,
    created_at           TEXT,
    UNIQUE(date, apartment_id)
);
CREATE INDEX IF NOT EXISTS idx_sched_apt_owner ON schedule_apartments(owner_id);
CREATE INDEX IF NOT EXISTS idx_sched_dov_date  ON schedule_date_overrides(date);
CREATE INDEX IF NOT EXISTS idx_sched_dov_plan  ON schedule_date_overrides(plan_id);
CREATE INDEX IF NOT EXISTS idx_sched_ov_day    ON schedule_coverage_overrides(day_of_week);
CREATE INDEX IF NOT EXISTS idx_sched_abs_date  ON schedule_absences(start_date, end_date);
"""

_inited = set()
_init_lock = threading.Lock()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:                # two threads racing the first init would
        if path in _inited:         # run SCHEMA/migrations concurrently
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
    # Overload caps live on the settings row. They are DERIVED from this team's own last-60-day
    # history (p90), never guessed — so they start NULL and stay NULL until there is real
    # history to learn from, and no overload flag is raised while they are NULL.
    scols = {r["name"] for r in cx.execute("PRAGMA table_info(schedule_settings)").fetchall()}
    for col, decl in (("max_units_per_day", "INTEGER"), ("max_minutes_per_day", "INTEGER"),
                      ("caps_source", "TEXT"), ("caps_computed_at", "TEXT")):
        if col not in scols:
            cx.execute("ALTER TABLE schedule_settings ADD COLUMN %s %s" % (col, decl))


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


@contextmanager
def transaction():
    """One connection, one commit — a multi-statement write (e.g. reset+reseed)
    must be all-or-nothing; per-statement commits could wipe the schedule and
    then die mid-seed."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise


# ---- typed readers ----

def employees():
    return q("SELECT * FROM schedule_employees ORDER BY sort_order, id")


def apartments():
    return q("SELECT * FROM schedule_apartments ORDER BY sort_order, id")


def overrides():
    return q("SELECT * FROM schedule_coverage_overrides")


def date_overrides_on(date_iso):
    """Apartment pins for ONE concrete date (the leave-plan primitive). Ordered so the engine
    reads them deterministically."""
    return q("SELECT * FROM schedule_date_overrides WHERE date=? ORDER BY apartment_id, id",
             (date_iso,))


def absences_on(date_iso):
    return q("SELECT * FROM schedule_absences WHERE status='approved' "
             "AND start_date<=? AND end_date>=?", (date_iso, date_iso))


def settings():
    return q1("SELECT * FROM schedule_settings WHERE id=1")
