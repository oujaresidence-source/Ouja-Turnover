# -*- coding: utf-8 -*-
"""
aqd.db — aqd_* tables inside the SAME brain.db (onboarding/db.py rules).

Never opens SQLite itself: brain.db.connect encodes the rules that cost a live outage
(journal_mode=DELETE, busy_timeout, one short-lived connection per call). Readers return plain
dicts. A NEW table needs no migration (CREATE TABLE IF NOT EXISTS); _migrate is only for
columns added later to a table that already exists.

Every status change goes through transition(): ONE conditional UPDATE (… WHERE status IN …),
so a double-tapped «توقيع العقد» or two admins countersigning at once can only ever win once.
"""

import datetime
import json
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS aqd_contracts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    ref                TEXT UNIQUE,
    status             TEXT NOT NULL DEFAULT 'draft',
    client_kind        TEXT,
    client_name        TEXT,
    gender             TEXT,
    id_last4           TEXT,
    mobile             TEXT,
    units_count        INTEGER,
    op_pct             REAL,
    answers_json       TEXT,
    warnings_json      TEXT,
    template_version   TEXT,
    template_name      TEXT,
    doc_sha256         TEXT,
    token              TEXT UNIQUE,
    token_created_at   TEXT,
    expires_at         TEXT,
    created_by         TEXT,
    created_at         TEXT,
    updated_at         TEXT,
    sent_at            TEXT,
    first_open_at      TEXT,
    open_count         INTEGER NOT NULL DEFAULT 0,
    verified_at        TEXT,
    verify_fails       INTEGER NOT NULL DEFAULT 0,
    locked_until       TEXT,
    view_key           TEXT,
    view_key_until     TEXT,
    signed_at          TEXT,
    signer_typed_name  TEXT,
    signer_ip          TEXT,
    signer_ua          TEXT,
    countersigned_by   TEXT,
    countersigned_at   TEXT,
    voided_by          TEXT,
    voided_at          TEXT,
    void_reason        TEXT,
    notified_signed_at TEXT,
    notified_completed_at TEXT
);
CREATE TABLE IF NOT EXISTS aqd_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    at          TEXT,
    actor       TEXT,
    kind        TEXT,
    detail_json TEXT
);
CREATE TABLE IF NOT EXISTS aqd_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_by TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_aqd_events_cid ON aqd_events(contract_id, id);
CREATE INDEX IF NOT EXISTS idx_aqd_contracts_status ON aqd_contracts(status);
"""

_inited = set()
_init_lock = threading.Lock()

COLUMNS = (
    "ref", "status", "client_kind", "client_name", "gender", "id_last4", "mobile", "units_count",
    "op_pct", "answers_json", "warnings_json", "template_version", "template_name", "doc_sha256",
    "token", "token_created_at", "expires_at", "created_by", "created_at", "updated_at", "sent_at",
    "first_open_at", "open_count", "verified_at", "verify_fails", "locked_until", "view_key",
    "view_key_until", "signed_at", "signer_typed_name", "signer_ip", "signer_ua",
    "countersigned_by", "countersigned_at", "voided_by", "voided_at", "void_reason",
    "notified_signed_at", "notified_completed_at",
)


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


def _migrate(cx):
    cols = {r["name"] for r in cx.execute("PRAGMA table_info(aqd_contracts)").fetchall()}
    for col in ("view_key", "view_key_until", "template_name", "notified_completed_at", "updated_at"):
        if cols and col not in cols:
            cx.execute("ALTER TABLE aqd_contracts ADD COLUMN %s TEXT" % col)


def reset_init_cache():
    _inited.clear()


def now_iso():
    """UTC, naive, seconds — every timestamp in these tables."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()


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
        return cur.lastrowid, cur.rowcount


def _check_cols(fields):
    bad = [k for k in fields if k not in COLUMNS]
    if bad:
        raise ValueError("unknown aqd column(s): %s" % ", ".join(bad))


# ------------------------------------------------------------------ contracts

def create(fields):
    _check_cols(fields)
    f = dict(fields)
    f.setdefault("status", "draft")
    f.setdefault("created_at", now_iso())
    f["updated_at"] = now_iso()
    keys = list(f.keys())
    cid, _n = execute("INSERT INTO aqd_contracts (%s) VALUES (%s)"
                      % (", ".join(keys), ", ".join("?" * len(keys))), [f[k] for k in keys])
    return cid


def get(cid):
    try:
        return q1("SELECT * FROM aqd_contracts WHERE id=?", (int(cid),))
    except (TypeError, ValueError):
        return None


def by_token(token):
    if not token or len(str(token)) < 20:
        return None
    return q1("SELECT * FROM aqd_contracts WHERE token=?", (str(token),))


def update(cid, **fields):
    """Unconditional field update (no status change)."""
    _check_cols(fields)
    if "status" in fields:
        raise ValueError("status changes go through transition()")
    fields["updated_at"] = now_iso()
    keys = list(fields.keys())
    _id, n = execute("UPDATE aqd_contracts SET %s WHERE id=?" % ", ".join("%s=?" % k for k in keys),
                     [fields[k] for k in keys] + [int(cid)])
    return n


def transition(cid, from_statuses, to_status, **fields):
    """Atomic compare-and-set. -> True only for the ONE caller that moved the row."""
    _check_cols(fields)
    fields = dict(fields, status=to_status, updated_at=now_iso())
    keys = list(fields.keys())
    froms = list(from_statuses)
    _id, n = execute("UPDATE aqd_contracts SET %s WHERE id=? AND status IN (%s)"
                     % (", ".join("%s=?" % k for k in keys), ", ".join("?" * len(froms))),
                     [fields[k] for k in keys] + [int(cid)] + froms)
    return n == 1


def update_where_status(cid, statuses, **fields):
    """Field update that only lands while the row is still in one of `statuses`."""
    _check_cols(fields)
    fields["updated_at"] = now_iso()
    keys = list(fields.keys())
    st = list(statuses)
    _id, n = execute("UPDATE aqd_contracts SET %s WHERE id=? AND status IN (%s)"
                     % (", ".join("%s=?" % k for k in keys), ", ".join("?" * len(st))),
                     [fields[k] for k in keys] + [int(cid)] + st)
    return n == 1


def bump(cid, column, by=1):
    if column not in ("open_count", "verify_fails"):
        raise ValueError(column)
    execute("UPDATE aqd_contracts SET %s=COALESCE(%s,0)+? WHERE id=?" % (column, column), (by, int(cid)))


def contracts(status=None):
    if status:
        return q("SELECT * FROM aqd_contracts WHERE status=? ORDER BY id DESC", (status,))
    return q("SELECT * FROM aqd_contracts ORDER BY id DESC")


def pending_signed_notify():
    return q("SELECT * FROM aqd_contracts WHERE status IN ('signed_owner','completed') "
             "AND signed_at IS NOT NULL AND (notified_signed_at IS NULL OR notified_signed_at LIKE 'claim:%')")


def pending_completed_notify():
    return q("SELECT * FROM aqd_contracts WHERE status='completed' "
             "AND (notified_completed_at IS NULL OR notified_completed_at LIKE 'claim:%')")


def answers(row):
    try:
        return json.loads(row.get("answers_json") or "{}")
    except ValueError:
        return {}


# ------------------------------------------------------------------ events (append-only)

def add_event(cid, actor, kind, detail=None):
    execute("INSERT INTO aqd_events (contract_id, at, actor, kind, detail_json) VALUES (?,?,?,?,?)",
            (int(cid), now_iso(), actor or "—", kind, json.dumps(detail or {}, ensure_ascii=False)))


def events(cid):
    rows = q("SELECT * FROM aqd_events WHERE contract_id=? ORDER BY id", (int(cid),))
    for r in rows:
        try:
            r["detail"] = json.loads(r.pop("detail_json") or "{}")
        except ValueError:
            r["detail"] = {}
    return rows


def last_event_at(cid):
    r = q1("SELECT at, kind FROM aqd_events WHERE contract_id=? ORDER BY id DESC LIMIT 1", (int(cid),))
    return r or {}


def recent_event(cid, kind, since_iso, ip=None):
    for r in q("SELECT detail_json FROM aqd_events WHERE contract_id=? AND kind=? AND at>=?",
               (int(cid), kind, since_iso)):
        if ip is None:
            return True
        try:
            if (json.loads(r["detail_json"] or "{}").get("ip")) == ip:
                return True
        except ValueError:
            pass
    return False


# ------------------------------------------------------------------ settings

def settings():
    return {r["key"]: r for r in q("SELECT * FROM aqd_settings")}


def setting(key, default=None):
    r = q1("SELECT value FROM aqd_settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key, value, by):
    execute("INSERT INTO aqd_settings (key, value, updated_by, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_by=excluded.updated_by, "
            "updated_at=excluded.updated_at", (key, "" if value is None else str(value), by, now_iso()))
