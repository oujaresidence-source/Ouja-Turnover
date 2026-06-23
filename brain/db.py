"""
brain.db — the Brain's own SQLite store (brain.db on STATE_DIR).

SQLite (not JSON) because the Governor asks relational questions JSON handles poorly:
"who was messaged in the last 7 days", "last contact per member", "consecutive ignores".
This is the FIRST sqlite use in the project; it is fully isolated to the Brain and never
touches the existing JSON state files.

Connection model: one SHORT-LIVED connection per call (SQLite is fine for this low write
volume), using ORDINARY locking so each transaction releases its lock immediately — the bot
is one long-lived process running TWO concurrent loops (Discord + the aiohttp dashboard), and
the Brain tab fires several API calls in parallel, so many small connections must interleave
safely. We deliberately do NOT use locking_mode=EXCLUSIVE (it never releases the file lock for
the life of the connection → concurrent queries became "database is locked") and NOT WAL (its
-shm shared-memory file is unsupported on the Railway volume → "disk I/O error"). The journal
is DELETE (a plain rollback journal that needs no shared memory) and every call closes its
connection via `with closing(connect()) as cx:`.
"""

import os
import sqlite3
import json
import threading
import tempfile
from contextlib import closing
from .host import HOST

_DB_PATH_OVERRIDE = None       # tests set this to a temp file
_init_lock = threading.Lock()
_initialized_paths = set()
_journal_normalized = set()    # paths whose WAL->DELETE conversion we've already forced once
_resolved_path = None          # the path we actually opened (primary, or a fallback if /data is dead)
STORAGE = {"path": None, "primary": None, "is_fallback": False, "reason": "", "free_mb": None}


def _dir_writable(d):
    """True iff we can actually create+write+delete a file in d right now (unique name, so
    concurrent probes never race each other into a false negative)."""
    try:
        os.makedirs(d, exist_ok=True)
        fd, p = tempfile.mkstemp(prefix=".brain_probe.", dir=d)
        os.write(fd, b"ok")
        os.close(fd)
        os.remove(p)
        return True, ""
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)


def _free_mb(d):
    try:
        st = os.statvfs(d)
        return round(st.f_bavail * st.f_frsize / 1e6, 1)
    except Exception:
        return None


def _resolve_path():
    """Decide ONCE per process where brain.db lives. Normally the Railway volume
    (STATE_DIR/brain.db). But if that directory can't be written RIGHT NOW (volume full,
    detached, or read-only — which would otherwise hard-500 the whole Brain tab), fall back to a
    writable local dir so the Brain still works. The fallback is ephemeral (resets on redeploy),
    but the Brain rebuilds itself from the campaign catalog + guest CRM, and Phase 1 sends
    nothing live, so a working-but-ephemeral Brain beats a dead page. The chosen path + the
    reason are recorded in STORAGE and surfaced on the health endpoint so the real volume
    problem is visible and not silently masked."""
    global _resolved_path
    if _DB_PATH_OVERRIDE:
        return _DB_PATH_OVERRIDE
    # Once we've settled on the REAL volume it's stable — keep it and skip the per-call probe.
    # But if we're currently on a FALLBACK, re-probe the primary every time so we SELF-HEAL back
    # to the volume the instant it recovers (e.g. after the owner grows the Railway volume) —
    # no container restart required.
    if _resolved_path and not STORAGE.get("is_fallback"):
        return _resolved_path
    primary = HOST.require("state_path")("brain.db")
    pdir = os.path.dirname(primary) or "."
    STORAGE["primary"] = primary
    ok, why = _dir_writable(pdir)
    if ok:
        if _resolved_path and STORAGE.get("is_fallback"):
            print("[brain] STORAGE: %s is writable again — switching back from fallback to the volume" % pdir)
        _resolved_path = primary
        STORAGE.update(path=primary, is_fallback=False, reason="", free_mb=_free_mb(pdir))
        return _resolved_path
    # Primary volume is not writable — use the first writable fallback (or keep the current one).
    for cand in (os.path.join(tempfile.gettempdir(), "ouja_brain"),
                 os.path.join(os.getcwd(), ".brain_fallback")):
        cok, _ = _dir_writable(cand)
        if cok:
            was_fallback = STORAGE.get("is_fallback")
            _resolved_path = os.path.join(cand, "brain.db")
            STORAGE.update(path=_resolved_path, is_fallback=True,
                           reason="%s not writable (%s); free=%sMB" % (pdir, why, _free_mb(pdir)),
                           free_mb=_free_mb(cand))
            if not was_fallback:        # log only on the transition into fallback, not each re-probe
                print("[brain] STORAGE WARNING: %s not writable (%s) — using fallback %s" %
                      (pdir, why, _resolved_path))
            return _resolved_path
    # Nothing writable anywhere (extreme) — keep primary so the error stays honest.
    _resolved_path = primary
    STORAGE.update(path=primary, is_fallback=False,
                   reason="no writable location found; %s: %s" % (pdir, why), free_mb=_free_mb(pdir))
    return _resolved_path


def db_path():
    return _resolve_path()


def set_db_path_for_tests(path):
    """Point the Brain at a throwaway db (used by the synthetic-data logic tests)."""
    global _DB_PATH_OVERRIDE, _resolved_path
    _DB_PATH_OVERRIDE = path
    _resolved_path = None
    _initialized_paths.discard(path)
    _journal_normalized.discard(path)


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


def _diag(e):
    """Wrap any sqlite OperationalError with volume context so the dashboard shows WHY the
    Brain DB failed (e.g. 'disk I/O error', 'unable to open database file') instead of a bare,
    unactionable message. Idempotent — re-wrapping an already-enriched error is a no-op."""
    msg = str(e)
    if msg.startswith("brain.db error at "):
        return e
    path = db_path()
    d = os.path.dirname(path) or "."
    exists = os.path.isdir(d)
    # Unique probe name (mkstemp) so concurrent failures can't race into a false negative.
    writable, why = _dir_writable(d)
    free = _free_mb(d)
    return sqlite3.OperationalError(
        "brain.db error at %s — dir_exists=%s dir_writable=%s free=%sMB probe=[%s] [%s] (brain-storage-v2)"
        % (path, exists, writable, free, why, msg))


def _normalize_journal(path):
    """ONE time per process per path: if the db file was left in WAL mode (pre-2026-06-23
    deploys ran `PRAGMA journal_mode=WAL`), the Railway volume can't back its -shm shared-memory
    file, so every later op fails with 'disk I/O error'. Open ONCE in EXCLUSIVE locking — that
    keeps the wal-index in heap so no -shm file is needed — rewrite the journal to DELETE (a
    plain rollback journal that needs no shared memory at all), then CLOSE immediately so no
    exclusive lock lingers. After this the file is DELETE-mode on disk and every normal
    connection can use ordinary (NORMAL) locking, which releases its lock after each transaction.
    Fresh dbs are created in rollback-journal mode already, so this is a no-op for them."""
    if path in _journal_normalized:
        return
    try:
        cx = sqlite3.connect(path, timeout=30)
        try:
            cx.execute("PRAGMA locking_mode=EXCLUSIVE")
            row = cx.execute("PRAGMA journal_mode=DELETE").fetchone()
        finally:
            cx.close()
        mode = (row[0] if row else "") or ""
        if mode.lower() != "wal":          # conversion took (or it was never WAL)
            _journal_normalized.add(path)
    except sqlite3.OperationalError:
        # Leave unmarked so a transient lock during conversion doesn't permanently wedge us
        # into believing the file is still WAL — we'll simply retry the conversion next open.
        pass


def connect():
    """Open the Brain DB with ORDINARY (NORMAL) locking + a busy timeout, so each short
    transaction releases its lock as soon as it commits and concurrent callers just wait the
    timeout out instead of erroring. We do NOT set locking_mode=EXCLUSIVE: it holds the file
    lock for the whole life of the connection, which on this long-lived two-loop process turned
    parallel Brain queries into 'database is locked'. journal_mode=DELETE keeps us off WAL's
    unsupported -shm file. Every PRAGMA is guarded so journal setup can't itself crash a request.
    CALLERS MUST CLOSE the connection (the helpers below use `with closing(connect())`)."""
    path = db_path()
    try:
        _ensure_parent_dir(path)
    except Exception:
        pass
    _normalize_journal(path)
    cx = sqlite3.connect(path, timeout=30)
    cx.row_factory = sqlite3.Row
    for pragma in ("PRAGMA busy_timeout=30000",
                   "PRAGMA journal_mode=DELETE",
                   "PRAGMA foreign_keys=ON"):
        try:
            cx.execute(pragma)
        except sqlite3.OperationalError:
            pass
    return cx


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
        try:
            with closing(connect()) as cx:
                cx.executescript(SCHEMA)
                _migrate(cx)
                cx.commit()
        except sqlite3.OperationalError as e:
            raise _diag(e)
        _initialized_paths.add(path)


# ---- tiny helpers so callers never hand-write boilerplate ----

def q(sql, args=()):
    """SELECT -> list of sqlite3.Row."""
    init_db()
    try:
        with closing(connect()) as cx:
            return list(cx.execute(sql, args).fetchall())
    except sqlite3.OperationalError as e:
        raise _diag(e)


def q1(sql, args=()):
    """SELECT one -> sqlite3.Row or None."""
    init_db()
    try:
        with closing(connect()) as cx:
            return cx.execute(sql, args).fetchone()
    except sqlite3.OperationalError as e:
        raise _diag(e)


def execute(sql, args=()):
    """INSERT/UPDATE/DELETE -> lastrowid."""
    init_db()
    try:
        with closing(connect()) as cx:
            cur = cx.execute(sql, args)
            cx.commit()
            return cur.lastrowid
    except sqlite3.OperationalError as e:
        raise _diag(e)


def executemany(sql, seq):
    init_db()
    try:
        with closing(connect()) as cx:
            cx.executemany(sql, seq)
            cx.commit()
    except sqlite3.OperationalError as e:
        raise _diag(e)


def audit(actor, action, payload=None):
    from .util import now_iso
    execute("INSERT INTO audit_log(actor, action, payload, created_at) VALUES(?,?,?,?)",
            (actor, action, json.dumps(payload or {}, ensure_ascii=False), now_iso()))
