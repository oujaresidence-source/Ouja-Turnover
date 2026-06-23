"""
brain.db — the Brain's own SQLite store (brain.db on STATE_DIR).

SQLite (not JSON) because the Governor asks relational questions JSON handles poorly:
"who was messaged in the last 7 days", "last contact per member", "consecutive ignores".
This is the FIRST sqlite use in the project; it is fully isolated to the Brain and never
touches the existing JSON state files.

Connection model: one connection per call (SQLite is fine for this low write volume),
WAL mode for concurrent reads while the aiohttp loop serves the dashboard. Every write
goes through a short-lived `with connect() as cx:` block so it commits and closes cleanly.
"""

import os
import sqlite3
import json
import threading
from .host import HOST

_DB_PATH_OVERRIDE = None       # tests set this to a temp file
_init_lock = threading.Lock()
_initialized_paths = set()


def db_path():
    if _DB_PATH_OVERRIDE:
        return _DB_PATH_OVERRIDE
    return HOST.require("state_path")("brain.db")


def set_db_path_for_tests(path):
    """Point the Brain at a throwaway db (used by the synthetic-data logic tests)."""
    global _DB_PATH_OVERRIDE
    _DB_PATH_OVERRIDE = path
    _initialized_paths.discard(path)


SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name           TEXT,
    phone                TEXT UNIQUE,
    tier                 TEXT,                 -- Silver | Gold | Turaif | Quarantine
    stays_count          INTEGER DEFAULT 0,
    total_spend          REAL DEFAULT 0,
    last_stay_date       TEXT,
    has_upcoming_booking INTEGER DEFAULT 0,
    in_house             INTEGER DEFAULT 0,
    engagement_score     REAL DEFAULT 0,
    consecutive_ignores  INTEGER DEFAULT 0,
    rested_until         TEXT,                 -- ISO date; NULL = not rested
    opted_out            INTEGER DEFAULT 0,
    best_send_hour       INTEGER,              -- learned later (Phase 3)
    source               TEXT DEFAULT 'crm',   -- crm | file | manual
    last_contacted       TEXT,
    updated_at           TEXT
);
CREATE INDEX IF NOT EXISTS ix_members_tier   ON members(tier);
CREATE INDEX IF NOT EXISTS ix_members_phone  ON members(phone);

CREATE TABLE IF NOT EXISTS campaigns (
    code             TEXT PRIMARY KEY,
    name             TEXT,
    tier_targets     TEXT,                     -- JSON array
    trigger_type     TEXT,
    offer            TEXT,
    lever            TEXT,
    message_template TEXT,                      -- Meta-approved body (uses {{1}} for the name)
    template_name    TEXT,                      -- Meta-approved template id (what Karzoum selects)
    footer           TEXT,
    image_prompt     TEXT,
    cooldown_class   TEXT,
    active           INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS recommendations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT,                  -- YYYY-MM-DD (Riyadh)
    campaign_code       TEXT,
    audience            TEXT,                  -- JSON [member_id,...]
    audience_size       INTEGER DEFAULT 0,
    projected_replies   REAL DEFAULT 0,
    projected_bookings  REAL DEFAULT 0,
    projected_revenue   REAL DEFAULT 0,
    rationale           TEXT,
    signals_json        TEXT,                  -- snapshot of the signals it was based on
    excluded_json       TEXT,                  -- JSON [{member_id, reason}] (governor)
    status              TEXT DEFAULT 'proposed', -- proposed|approved|rejected|sent|silent
    created_at          TEXT
);
CREATE INDEX IF NOT EXISTS ix_recs_date ON recommendations(date);

CREATE TABLE IF NOT EXISTS contact_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER,
    campaign_code TEXT,
    sent_at       TEXT,                        -- ISO datetime (the governor reads this)
    status        TEXT DEFAULT 'queued',       -- queued|sent|delivered|failed
    replied       INTEGER DEFAULT 0,
    reply_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_contact_member ON contact_log(member_id);
CREATE INDEX IF NOT EXISTS ix_contact_sent   ON contact_log(sent_at);

CREATE TABLE IF NOT EXISTS replies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER,
    campaign_code TEXT,
    text          TEXT,
    received_at   TEXT
);

CREATE TABLE IF NOT EXISTS attributions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_id TEXT,
    campaign_code  TEXT,
    member_id      INTEGER,
    matched_on     TEXT,
    revenue        REAL DEFAULT 0,
    created_at     TEXT
);

CREATE TABLE IF NOT EXISTS opt_outs (
    phone       TEXT PRIMARY KEY,
    opted_out_at TEXT,
    source      TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    actor      TEXT,
    action     TEXT,
    payload    TEXT,                           -- JSON
    created_at TEXT
);
"""


def _ensure_parent_dir(path):
    """SQLite never creates missing directories — it just raises 'unable to open database
    file'. Every other STATE_DIR writer in bot.py makedirs() first; the Brain's raw sqlite
    open is the one place that didn't. Mirror that here so a cold volume can't 500 the Brain."""
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)


def _open_diagnostic(path, err):
    """Build a precise message when the DB still won't open after we've ensured the dir —
    tells us (and the owner, on screen) whether it's a missing mount or a permission issue
    on the Railway volume, instead of the opaque 'unable to open database file'."""
    d = os.path.dirname(path) or "."
    dir_exists = os.path.isdir(d)
    writable = False
    try:
        probe = os.path.join(d, ".brain_write_probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        writable = True
    except Exception:
        writable = False
    return ("cannot open brain.db at %s — dir_exists=%s dir_writable=%s. If dir_writable=False "
            "the STATE_DIR volume isn't mounted/writable on this deploy (a Railway volume issue, "
            "not a code bug). [%s]" % (path, dir_exists, writable, err))


def connect():
    path = db_path()
    try:
        _ensure_parent_dir(path)
    except Exception:
        pass
    try:
        cx = sqlite3.connect(path, timeout=30)
        cx.row_factory = sqlite3.Row
        try:
            cx.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass        # some volume filesystems can't back WAL's shared memory; default journal is fine
        cx.execute("PRAGMA foreign_keys=ON")
        return cx
    except sqlite3.OperationalError as e:
        raise sqlite3.OperationalError(_open_diagnostic(path, e))


# Columns added after the first release — applied to already-deployed brain.db files.
_MIGRATIONS = [
    ("campaigns", "template_name", "ALTER TABLE campaigns ADD COLUMN template_name TEXT"),
    ("campaigns", "footer", "ALTER TABLE campaigns ADD COLUMN footer TEXT"),
]


def _migrate(cx):
    for table, col, sql in _MIGRATIONS:
        try:
            cols = {r[1] for r in cx.execute("PRAGMA table_info(%s)" % table).fetchall()}
            if col not in cols:
                cx.execute(sql)
        except sqlite3.OperationalError:
            pass


def init_db():
    """Create tables once per process per path. Safe to call repeatedly."""
    path = db_path()
    if path in _initialized_paths:
        return
    with _init_lock:
        if path in _initialized_paths:
            return
        with connect() as cx:
            cx.executescript(SCHEMA)
            _migrate(cx)
        _initialized_paths.add(path)


# ---- tiny helpers so callers never hand-write boilerplate ----

def q(sql, args=()):
    """SELECT -> list of sqlite3.Row."""
    init_db()
    with connect() as cx:
        return list(cx.execute(sql, args).fetchall())


def q1(sql, args=()):
    """SELECT one -> sqlite3.Row or None."""
    init_db()
    with connect() as cx:
        return cx.execute(sql, args).fetchone()


def execute(sql, args=()):
    """INSERT/UPDATE/DELETE -> lastrowid."""
    init_db()
    with connect() as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid


def executemany(sql, seq):
    init_db()
    with connect() as cx:
        cx.executemany(sql, seq)
        cx.commit()


def audit(actor, action, payload=None):
    from .util import now_iso
    execute("INSERT INTO audit_log(actor, action, payload, created_at) VALUES(?,?,?,?)",
            (actor, action, json.dumps(payload or {}, ensure_ascii=False), now_iso()))
