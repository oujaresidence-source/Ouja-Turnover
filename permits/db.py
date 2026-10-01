# -*- coding: utf-8 -*-
"""
permits.db — permits_* tables inside the SAME brain.db SQLite file (wifi/db.py pattern).
Reuses brain.db.connect for the proven NO-WAL / journal_mode=DELETE / busy_timeout rules;
every call is wrapped in `with closing(connect())`.

THE GUARANTEE LIVES HERE, IN SQL
--------------------------------
    CREATE UNIQUE INDEX idx_permits_one_live_ticket
        ON permits_tickets(permit_id) WHERE state IN ('opening','open')

The DATABASE refuses a second live ticket for one permit — two bot copies overlapping
during a Railway deploy cannot both open a channel, because the second INSERT fails.
And every Discord side effect goes through permits_outbox, whose `ref` is UNIQUE, so the
same reminder / digest can never be enqueued twice. DO NOT REMOVE EITHER TO "SIMPLIFY".

There is deliberately NO unique index on permit_no: the real seed carries the same number
on two rows (serials 19/44). A duplicate number is a REVIEW flag, never a reason to drop
or block a row — dropping one could silently lose a permit.
"""

import datetime
import json
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS permits_permits (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  permit_type     TEXT NOT NULL,
  permit_no       TEXT DEFAULT '',
  title           TEXT DEFAULT '',
  scope           TEXT NOT NULL DEFAULT 'other',
  listing_id      INTEGER,
  unit_text       TEXT DEFAULT '',
  building        TEXT DEFAULT '',
  issuer          TEXT DEFAULT '',
  holder          TEXT DEFAULT '',
  start_date      TEXT,
  end_date        TEXT,
  start_date_raw  TEXT DEFAULT '',
  end_date_raw    TEXT DEFAULT '',
  district        TEXT DEFAULT '',
  street          TEXT DEFAULT '',
  building_no     TEXT DEFAULT '',
  unit_no         TEXT DEFAULT '',
  ownership_kind  TEXT DEFAULT '',
  holder_id_last4 TEXT DEFAULT '',
  doc_name        TEXT DEFAULT '',
  doc_url         TEXT DEFAULT '',
  review_issues   TEXT DEFAULT '[]',
  listing_link_kind TEXT DEFAULT '',
  serial          INTEGER,
  date_issue      TEXT DEFAULT '',
  lead_days       INTEGER,
  cost_sar        REAL,
  responsible_name TEXT DEFAULT '',
  responsible_discord_id TEXT DEFAULT '',
  renew_notes     TEXT DEFAULT '',
  notes           TEXT DEFAULT '',
  extra_json      TEXT DEFAULT '{}',
  doc_path        TEXT DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'active',
  needs_data      INTEGER NOT NULL DEFAULT 0,
  replaces_id     INTEGER,
  replaced_by_id  INTEGER,
  cancel_reason   TEXT DEFAULT '',
  source          TEXT DEFAULT 'manual',
  source_ref      TEXT DEFAULT '',
  created_by TEXT, created_at TEXT, updated_by TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_permits_no ON permits_permits(permit_no);
CREATE INDEX IF NOT EXISTS idx_permits_status_end ON permits_permits(status, end_date);

CREATE TABLE IF NOT EXISTS permits_tickets (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  permit_id     INTEGER NOT NULL,
  state         TEXT NOT NULL,
  channel_id    TEXT DEFAULT '',
  card_msg_id   TEXT DEFAULT '',
  claimed_by    TEXT DEFAULT '', claimed_by_id TEXT DEFAULT '', claimed_at TEXT,
  opened_at     TEXT, closed_at TEXT, closed_by TEXT, close_kind TEXT,
  last_reminder_date TEXT,
  attempts      INTEGER DEFAULT 0, last_error TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_permits_one_live_ticket
  ON permits_tickets(permit_id) WHERE state IN ('opening','open');

CREATE TABLE IF NOT EXISTS permits_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  ref  TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  claimed_at TEXT, attempts INTEGER DEFAULT 0, last_error TEXT DEFAULT '', created_at TEXT, done_at TEXT,
  next_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_permits_outbox_ref ON permits_outbox(ref);

CREATE TABLE IF NOT EXISTS permits_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, permit_id INTEGER, ticket_id INTEGER,
  kind TEXT, payload_json TEXT, actor TEXT, at TEXT
);
CREATE INDEX IF NOT EXISTS idx_permits_events_permit ON permits_events(permit_id);
CREATE TABLE IF NOT EXISTS permits_settings (key TEXT PRIMARY KEY, value TEXT);
"""

# Columns a later release adds go here, guarded by PRAGMA table_info (schedule/db.py pattern).
_MIGRATIONS = {
    "permits_outbox": [("next_at", "TEXT")],
}

_inited = set()
_init_lock = threading.Lock()


def _migrate(cx):
    for table, cols in _MIGRATIONS.items():
        have = {r["name"] for r in cx.execute("PRAGMA table_info(%s)" % table).fetchall()}
        for name, decl in cols:
            if name not in have:
                cx.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, decl))


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            _migrate(cx)
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()


def now_iso():
    """UTC, seconds — the storage timestamp (display code converts)."""
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
    """-> (lastrowid, rowcount)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid, cur.rowcount


@contextmanager
def transaction():
    """One connection, one commit — a renewal is all-or-nothing."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise


# ---------------- settings ----------------

def get_setting(key, default=None):
    r = q1("SELECT value FROM permits_settings WHERE key=?", (key,))
    return r["value"] if r and r["value"] is not None else default


def set_setting(key, value, cx=None):
    sql = ("INSERT INTO permits_settings(key, value) VALUES(?,?) "
           "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    if cx is not None:
        cx.execute(sql, (key, None if value is None else str(value)))
        return
    execute(sql, (key, None if value is None else str(value)))


# ---------------- events ----------------

def log_event(kind, permit_id=None, ticket_id=None, payload=None, actor="", cx=None):
    args = (permit_id, ticket_id, kind, json.dumps(payload or {}, ensure_ascii=False),
            actor or "", now_iso())
    sql = ("INSERT INTO permits_events(permit_id, ticket_id, kind, payload_json, actor, at) "
           "VALUES(?,?,?,?,?,?)")
    if cx is not None:
        return cx.execute(sql, args).lastrowid
    return execute(sql, args)[0]


def events_for(permit_ids, limit=50):
    ids = [int(i) for i in permit_ids if i is not None]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return q("SELECT * FROM permits_events WHERE permit_id IN (%s) ORDER BY id DESC LIMIT %d"
             % (marks, int(limit)), tuple(ids))


# ---------------- permits ----------------

PERMIT_FIELDS = (
    "permit_type", "permit_no", "title", "scope", "listing_id", "unit_text", "building",
    "issuer", "holder", "start_date", "end_date", "start_date_raw", "end_date_raw",
    "district", "street", "building_no", "unit_no", "ownership_kind", "holder_id_last4",
    "doc_name", "doc_url", "review_issues", "listing_link_kind", "serial", "date_issue",
    "lead_days", "cost_sar", "responsible_name", "responsible_discord_id", "renew_notes",
    "notes", "extra_json", "doc_path", "status", "needs_data", "replaces_id",
    "replaced_by_id", "cancel_reason", "source", "source_ref", "created_by", "updated_by",
)


def insert_permit(data, actor="", cx=None):
    row = {k: data.get(k) for k in PERMIT_FIELDS if k in data}
    row.setdefault("status", "active")
    row["permit_type"] = (row.get("permit_type") or "").strip() or "تصريح"
    row["needs_data"] = 1 if (row.get("needs_data") or not row.get("end_date")) else 0
    for k in ("review_issues",):
        if isinstance(row.get(k), (list, tuple)):
            row[k] = json.dumps(row[k], ensure_ascii=False)
    if isinstance(row.get("extra_json"), dict):
        row["extra_json"] = json.dumps(row["extra_json"], ensure_ascii=False)
    row["created_by"] = row.get("created_by") or actor or ""
    ts = now_iso()
    cols = list(row.keys()) + ["created_at", "updated_at"]
    vals = [row[k] for k in row] + [ts, ts]
    sql = "INSERT INTO permits_permits(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols)))
    if cx is not None:
        return cx.execute(sql, vals).lastrowid
    return execute(sql, vals)[0]


def update_permit(pid, fields, actor="", cx=None):
    sets, args = [], []
    for k, v in fields.items():
        if k not in PERMIT_FIELDS:
            continue
        if isinstance(v, (list, tuple)) or (k == "extra_json" and isinstance(v, dict)):
            v = json.dumps(v, ensure_ascii=False)
        sets.append(k + "=?")
        args.append(v)
    if not sets:
        return 0
    sets += ["updated_at=?", "updated_by=?"]
    args += [now_iso(), actor or "", int(pid)]
    sql = "UPDATE permits_permits SET " + ", ".join(sets) + " WHERE id=?"
    if cx is not None:
        return cx.execute(sql, args).rowcount
    return execute(sql, args)[1]


def permit(pid):
    return q1("SELECT * FROM permits_permits WHERE id=?", (int(pid),))


def permits(status=None):
    if status:
        return q("SELECT * FROM permits_permits WHERE status=? ORDER BY id", (status,))
    return q("SELECT * FROM permits_permits ORDER BY id")


def count_permits():
    return (q1("SELECT COUNT(*) n FROM permits_permits") or {}).get("n", 0)


def chain(pid):
    """Every term of this permit's renewal chain, newest first."""
    seen, out = set(), []
    cur = permit(pid)
    while cur and cur.get("replaced_by_id") and cur["replaced_by_id"] not in seen:
        seen.add(cur["id"])
        cur = permit(cur["replaced_by_id"])
    while cur and cur["id"] not in seen:
        seen.add(cur["id"])
        out.append(cur)
        cur = permit(cur["replaces_id"]) if cur.get("replaces_id") else None
    return out


# ---------------- tickets ----------------

def ticket(tid):
    return q1("SELECT * FROM permits_tickets WHERE id=?", (int(tid),))


def live_ticket(pid):
    return q1("SELECT * FROM permits_tickets WHERE permit_id=? AND state IN ('opening','open')",
              (int(pid),))


def live_tickets():
    return q("SELECT * FROM permits_tickets WHERE state IN ('opening','open') ORDER BY id")


def tickets_for(pid):
    return q("SELECT * FROM permits_tickets WHERE permit_id=? ORDER BY id DESC", (int(pid),))


def update_ticket(tid, cx=None, **fields):
    sets = [k + "=?" for k in fields]
    args = list(fields.values()) + [int(tid)]
    sql = "UPDATE permits_tickets SET " + ", ".join(sets) + " WHERE id=?"
    if cx is not None:
        return cx.execute(sql, args).rowcount
    return execute(sql, args)[1]


# ---------------- outbox ----------------

def enqueue(kind, ref, payload, state="pending", cx=None):
    """INSERT OR IGNORE on the unique ref: enqueuing the same thing twice is a no-op.
    -> the new row id, or None when it already existed."""
    sql = ("INSERT OR IGNORE INTO permits_outbox(kind, ref, payload_json, state, created_at, next_at) "
           "VALUES(?,?,?,?,?,?)")
    args = (kind, ref, json.dumps(payload or {}, ensure_ascii=False), state, now_iso(), None)
    if cx is not None:
        cur = cx.execute(sql, args)
    else:
        _ensure()
        with closing(_bdb.connect()) as c2:
            cur = c2.execute(sql, args)
            c2.commit()
    return cur.lastrowid if cur.rowcount == 1 else None


def outbox(ref):
    return q1("SELECT * FROM permits_outbox WHERE ref=?", (ref,))


def outbox_rows(state=None):
    if state:
        return q("SELECT * FROM permits_outbox WHERE state=? ORDER BY id", (state,))
    return q("SELECT * FROM permits_outbox ORDER BY id")


def claim_outbox(oid, at):
    """Atomic claim — exactly one bot copy gets rowcount 1."""
    _lid, n = execute("UPDATE permits_outbox SET state='claimed', claimed_at=? "
                      "WHERE id=? AND state IN ('pending','failed')", (at, int(oid)))
    return n == 1
