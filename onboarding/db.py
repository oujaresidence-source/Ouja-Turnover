# -*- coding: utf-8 -*-
"""
onboarding.db — onb_* tables inside the SAME brain.db SQLite file.

Never opens SQLite itself: brain.db.connect already encodes the rules that cost a live outage
(journal_mode=DELETE not WAL, busy_timeout=30000, row_factory=Row, one short-lived connection
per call). Every reader returns plain dicts, never sqlite3.Row, so the engine and the tests
never depend on a cursor type.

A NEW table needs no _migrate entry — SCHEMA runs on every _ensure and CREATE TABLE IF NOT
EXISTS adds it to an already-existing brain.db. _migrate is only for columns added later to a
table that already exists.
"""

import datetime
import json
import secrets
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb
from . import catalogue

SCHEMA = """
CREATE TABLE IF NOT EXISTS onb_projects (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ref               TEXT UNIQUE,
    client_name       TEXT NOT NULL,
    client_type       TEXT NOT NULL,
    client_whatsapp   TEXT NOT NULL,
    client_email      TEXT,
    sublet_ok         INTEGER,
    unit_name         TEXT NOT NULL,
    district          TEXT NOT NULL,
    unit_kind         TEXT,
    bedrooms          INTEGER,
    area_sqm          REAL,
    listing_id        INTEGER,
    amenities         TEXT,
    furnish_state     TEXT,
    strategy          TEXT,
    ouja_rate_pct     REAL,
    cleaning_sar      REAL,
    cleaning_absorbed INTEGER DEFAULT 0,
    contract_signed_at TEXT,
    ceo_approval      TEXT,
    ceo_approval_note TEXT,
    license_no        TEXT,
    license_expiry    TEXT,
    photos_url        TEXT,
    photos_approved   INTEGER DEFAULT 0,
    access_notes      TEXT,
    wifi_notes        TEXT,
    house_rules       TEXT,
    checkin_time      TEXT,
    checkout_time     TEXT,
    client_promises   TEXT,
    client_prefs      TEXT,
    handover_target   TEXT,
    pmo_project_id    TEXT,
    thread_id         TEXT,
    stage             TEXT NOT NULL DEFAULT 'lead',
    status            TEXT NOT NULL DEFAULT 'active',
    walk_reason       TEXT,
    published_at      TEXT,
    published_by      TEXT,
    created_at        TEXT,
    created_by        TEXT,
    updated_at        TEXT
);
CREATE TABLE IF NOT EXISTS onb_tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES onb_projects(id) ON DELETE CASCADE,
    catalogue_key TEXT NOT NULL,
    stage         TEXT NOT NULL,
    seq           INTEGER NOT NULL,
    title_ar      TEXT NOT NULL,
    owner_role    TEXT NOT NULL,
    gate          INTEGER NOT NULL DEFAULT 0,
    assignee_id   INTEGER,
    assignee_name TEXT,
    notified_at   TEXT,
    resolution    TEXT NOT NULL DEFAULT 'open',
    reason        TEXT,
    due           TEXT,
    note          TEXT,
    resolved_by   TEXT,
    resolved_at   TEXT,
    updated_at    TEXT,
    UNIQUE(project_id, catalogue_key)
);
CREATE TABLE IF NOT EXISTS onb_assignees (
    project_id    INTEGER NOT NULL REFERENCES onb_projects(id) ON DELETE CASCADE,
    employee_id   INTEGER NOT NULL,
    employee_name TEXT NOT NULL,
    employee_did  TEXT,
    access_token  TEXT UNIQUE,
    is_primary    INTEGER NOT NULL DEFAULT 0,
    added_by      TEXT,
    added_at      TEXT,
    PRIMARY KEY (project_id, employee_id)
);
CREATE TABLE IF NOT EXISTS onb_handover (
    project_id  INTEGER PRIMARY KEY REFERENCES onb_projects(id) ON DELETE CASCADE,
    snapshot    TEXT NOT NULL,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS onb_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  INTEGER NOT NULL,
    at          TEXT,
    who         TEXT,
    text_ar     TEXT
);
CREATE INDEX IF NOT EXISTS idx_onb_log_pid ON onb_log(project_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_onb_tasks_pid ON onb_tasks(project_id, stage, seq);
CREATE INDEX IF NOT EXISTS idx_onb_tasks_assignee ON onb_tasks(project_id, assignee_id);
CREATE INDEX IF NOT EXISTS idx_onb_asg_token ON onb_assignees(access_token);
"""

_inited = set()
_init_lock = threading.Lock()

# Every column a client may PATCH through /api/onb/update. An allow-list, not a deny-list:
# id, ref, status, published_* and created_* must never be reachable from a request body.
EDITABLE_FIELDS = (
    "client_name", "client_type", "client_whatsapp", "client_email", "sublet_ok",
    "unit_name", "district", "unit_kind", "bedrooms", "area_sqm", "listing_id",
    "amenities", "furnish_state",
    "strategy", "ouja_rate_pct", "cleaning_sar", "cleaning_absorbed", "contract_signed_at",
    "ceo_approval", "ceo_approval_note",
    "license_no", "license_expiry", "photos_url", "photos_approved",
    "access_notes", "wifi_notes", "house_rules", "checkin_time", "checkout_time",
    "client_promises", "client_prefs", "handover_target",
    "pmo_project_id", "stage",
)

INT_FIELDS = ("sublet_ok", "bedrooms", "listing_id", "cleaning_absorbed", "photos_approved")
REAL_FIELDS = ("area_sqm", "ouja_rate_pct", "cleaning_sar")


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
    """Additive column migrations for an already-existing brain.db. Guarded by table_info, so
    running it on a fresh database is a no-op."""
    cols = {r["name"] for r in cx.execute("PRAGMA table_info(onb_projects)").fetchall()}
    for col, decl in (("handover_target", "TEXT"),):
        if cols and col not in cols:
            cx.execute("ALTER TABLE onb_projects ADD COLUMN %s %s" % (col, decl))


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


@contextmanager
def transaction():
    """One connection, one commit. A batch delegation must be all-or-nothing: a half-applied
    assignment is worse than a rejected one (build spec §9.1)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise


# ---------------------------------------------------------------- projects ------------------

def next_ref():
    row = q1("SELECT ref FROM onb_projects WHERE ref LIKE 'OJ-ONB-%' ORDER BY id DESC LIMIT 1")
    n = 0
    if row and row.get("ref"):
        try:
            n = int(str(row["ref"]).split("-")[-1])
        except (ValueError, IndexError):
            n = 0
    return "OJ-ONB-%04d" % (n + 1)


def create_project(fields, created_by=""):
    """Insert one project and seed its catalogue. Returns the full project dict."""
    now = now_iso()
    data = {k: fields.get(k) for k in EDITABLE_FIELDS if k in fields}
    data["ref"] = next_ref()
    data["created_at"] = now
    data["updated_at"] = now
    data["created_by"] = created_by
    data.setdefault("stage", "lead")
    cols = ", ".join(data.keys())
    marks = ", ".join("?" for _ in data)
    pid = execute("INSERT INTO onb_projects (%s) VALUES (%s)" % (cols, marks),
                  tuple(data.values()))
    seed_tasks(pid)
    return project(pid)


def project(pid):
    return q1("SELECT * FROM onb_projects WHERE id=?", (int(pid),))


def project_by_ref(ref):
    return q1("SELECT * FROM onb_projects WHERE ref=?", (ref,))


def projects(status=None):
    if status:
        return q("SELECT * FROM onb_projects WHERE status=? ORDER BY id DESC", (status,))
    return q("SELECT * FROM onb_projects ORDER BY id DESC")


def update_project(pid, **fields):
    """Patch only allow-listed columns. Unknown keys are dropped, never written."""
    data = {}
    for k, v in fields.items():
        if k not in EDITABLE_FIELDS:
            continue
        if k in INT_FIELDS and v is not None and v != "":
            try:
                v = int(v)
            except (TypeError, ValueError):
                continue
        elif k in REAL_FIELDS and v is not None and v != "":
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
        if v == "":
            v = None
        data[k] = v
    if not data:
        return project(pid)
    data["updated_at"] = now_iso()
    sets = ", ".join("%s=?" % k for k in data)
    execute("UPDATE onb_projects SET %s WHERE id=?" % sets, tuple(data.values()) + (int(pid),))
    return project(pid)


def set_thread_id(pid, thread_id):
    execute("UPDATE onb_projects SET thread_id=? WHERE id=?", (str(thread_id), int(pid)))


def publish(pid, snapshot, who):
    """The one-way stamped event (build spec R5). ONE transaction: the snapshot, the status and
    the log line land together or not at all. INSERT OR IGNORE on onb_handover — a snapshot is
    written once and a second publish can never rewrite history."""
    now = now_iso()
    with transaction() as cx:
        cx.execute("INSERT OR IGNORE INTO onb_handover (project_id, snapshot, created_at) "
                   "VALUES (?,?,?)",
                   (int(pid), json.dumps(snapshot, ensure_ascii=False), now))
        cx.execute("UPDATE onb_projects SET status='published', published_at=?, published_by=?, "
                   "stage='handover', updated_at=? WHERE id=?", (now, who, now, int(pid)))
        cx.execute("INSERT INTO onb_log (project_id, at, who, text_ar) VALUES (?,?,?,?)",
                   (int(pid), now, who, "نُشرت الوحدة وانسلّمت لفريق العمليات"))
    return project(pid)


def handover(pid):
    row = q1("SELECT * FROM onb_handover WHERE project_id=?", (int(pid),))
    if not row:
        return None
    try:
        row["snapshot"] = json.loads(row.get("snapshot") or "{}")
    except ValueError:
        row["snapshot"] = {}
    return row


def walk_away(pid, reason, who):
    now = now_iso()
    execute("UPDATE onb_projects SET status='walked_away', walk_reason=?, updated_at=? WHERE id=?",
            (reason, now, int(pid)))
    log(pid, who, "انسحبنا من المشروع — السبب: %s" % reason)
    return project(pid)


# ---------------------------------------------------------------- tasks ---------------------

def seed_tasks(pid):
    """Generate the full checklist (build spec R1). INSERT OR IGNORE + UNIQUE(project_id,
    catalogue_key): additive, never an update, never a delete. Safe to re-run forever."""
    now = now_iso()
    rows = [(int(pid), key, stage, seq, title, role, gate, now)
            for (key, stage, seq, title, role, gate) in catalogue.rows_for_seed()]
    executemany("INSERT OR IGNORE INTO onb_tasks "
                "(project_id, catalogue_key, stage, seq, title_ar, owner_role, gate, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)", rows)
    apply_auto_na(pid)
    return len(rows)


def apply_auto_na(pid):
    """Re-evaluate the shape-driven 'not applicable' rules.

    Only ever touches tasks still sitting at `open`. Flipping furnish_state later must never
    reopen or overwrite a human's resolution — that is a decision, and a decision is not data
    to be recomputed (the same rule that governs a typed manual expense in the ERP).
    """
    p = project(pid)
    if not p:
        return 0
    auto = catalogue.auto_na_for(p)
    if not auto:
        return 0
    now = now_iso()
    n = 0
    with transaction() as cx:
        for key, reason in auto.items():
            cur = cx.execute(
                "UPDATE onb_tasks SET resolution='na', reason=?, resolved_by='النظام', "
                "resolved_at=?, updated_at=? "
                "WHERE project_id=? AND catalogue_key=? AND resolution='open'",
                (reason, now, now, int(pid), key))
            n += cur.rowcount or 0
    return n


def tasks(pid, assignee_id=None):
    if assignee_id is not None:
        return q("SELECT * FROM onb_tasks WHERE project_id=? AND assignee_id=? "
                 "ORDER BY stage, seq, id", (int(pid), int(assignee_id)))
    return q("SELECT * FROM onb_tasks WHERE project_id=? ORDER BY stage, seq, id", (int(pid),))


def task(task_id):
    return q1("SELECT * FROM onb_tasks WHERE id=?", (int(task_id),))


def resolve_task(task_id, resolution, reason, who):
    now = now_iso()
    execute("UPDATE onb_tasks SET resolution=?, reason=?, resolved_by=?, resolved_at=?, "
            "updated_at=? WHERE id=?",
            (resolution, reason or None, who, now, now, int(task_id)))
    return task(task_id)


def stamp_notified(task_ids, when=None):
    """The ping ledger. Stamped ONLY after notify returned without raising, so a Discord outage
    leaves the stamp NULL and the next save retries the ping instead of swallowing it."""
    if not task_ids:
        return
    now = when or now_iso()
    executemany("UPDATE onb_tasks SET notified_at=? WHERE id=?",
                [(now, int(t)) for t in task_ids])


# ---------------------------------------------------------------- assignees -----------------

def assignees(pid):
    return q("SELECT * FROM onb_assignees WHERE project_id=? ORDER BY is_primary DESC, added_at",
             (int(pid),))


def assignee(pid, employee_id):
    return q1("SELECT * FROM onb_assignees WHERE project_id=? AND employee_id=?",
              (int(pid), int(employee_id)))


def assignee_by_token(token):
    if not token:
        return None
    return q1("SELECT * FROM onb_assignees WHERE access_token=?", (str(token),))


def add_assignee(pid, employee_id, employee_name, employee_did="", is_primary=0, added_by=""):
    token = secrets.token_urlsafe(24)
    execute("INSERT INTO onb_assignees (project_id, employee_id, employee_name, employee_did, "
            "access_token, is_primary, added_by, added_at) VALUES (?,?,?,?,?,?,?,?)",
            (int(pid), int(employee_id), employee_name, employee_did or "", token,
             int(is_primary), added_by, now_iso()))
    return assignee(pid, employee_id)


def remove_assignee(pid, employee_id):
    """Removing a person also releases every task they held on THIS project — otherwise the
    task keeps a name that is no longer on the project and the gate reads clean while nobody
    is actually responsible. One transaction: both or neither."""
    with transaction() as cx:
        cx.execute("UPDATE onb_tasks SET assignee_id=NULL, assignee_name=NULL, notified_at=NULL, "
                   "updated_at=? WHERE project_id=? AND assignee_id=?",
                   (now_iso(), int(pid), int(employee_id)))
        cx.execute("DELETE FROM onb_assignees WHERE project_id=? AND employee_id=?",
                   (int(pid), int(employee_id)))


def assignee_project_counts():
    """{employee_id: active project count} so the picker can show load."""
    rows = q("SELECT a.employee_id AS eid, COUNT(*) AS n FROM onb_assignees a "
             "JOIN onb_projects p ON p.id=a.project_id WHERE p.status='active' "
             "GROUP BY a.employee_id")
    return {int(r["eid"]): int(r["n"]) for r in rows}


# ---------------------------------------------------------------- log -----------------------

def log(pid, who, text_ar):
    execute("INSERT INTO onb_log (project_id, at, who, text_ar) VALUES (?,?,?,?)",
            (int(pid), now_iso(), who, text_ar))


def logs(pid, limit=120):
    return q("SELECT * FROM onb_log WHERE project_id=? ORDER BY id DESC LIMIT ?",
             (int(pid), int(limit)))


def counts():
    """Counters for the list header and for the tests that assert a tap changed nothing."""
    def one(sql, args=()):
        r = q1(sql, args) or {}
        return int(r.get("n") or 0)
    return {
        "projects": one("SELECT COUNT(*) AS n FROM onb_projects"),
        "active": one("SELECT COUNT(*) AS n FROM onb_projects WHERE status='active'"),
        "published": one("SELECT COUNT(*) AS n FROM onb_projects WHERE status='published'"),
        "walked_away": one("SELECT COUNT(*) AS n FROM onb_projects WHERE status='walked_away'"),
        "tasks": one("SELECT COUNT(*) AS n FROM onb_tasks"),
        "assignees": one("SELECT COUNT(*) AS n FROM onb_assignees"),
        "handovers": one("SELECT COUNT(*) AS n FROM onb_handover"),
    }
