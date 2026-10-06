# -*- coding: utf-8 -*-
"""
owner_meet.db — meet_* tables inside the SAME brain.db (permits/db.py pattern): brain.db.connect
(NO WAL, journal_mode=DELETE, busy_timeout), every call wrapped in `with closing(connect())`.

THE GUARANTEE LIVES HERE, IN SQL
--------------------------------
A frozen (sent) snapshot is immutable: two triggers make the DATABASE refuse any UPDATE or DELETE
of a row whose frozen = 1. Reopening a sent meeting writes version + 1; it never edits the old
row. DO NOT REMOVE THE TRIGGERS TO "SIMPLIFY" — the owner holds a link to that exact version.
"""

import datetime
import hashlib
import json
import os
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meet_meetings (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  owner         TEXT NOT NULL,
  lids          TEXT NOT NULL DEFAULT '[]',
  period_kind   TEXT NOT NULL DEFAULT '',
  period_from   TEXT NOT NULL,
  period_to     TEXT NOT NULL,
  months        TEXT NOT NULL DEFAULT '[]',
  meeting_date  TEXT NOT NULL,
  state         TEXT NOT NULL DEFAULT 'draft',
  build_progress INTEGER NOT NULL DEFAULT 0,
  build_step    TEXT DEFAULT '',
  build_error   TEXT DEFAULT '',
  created_by    TEXT, created_at TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_meet_meetings_owner ON meet_meetings(owner, meeting_date);

CREATE TABLE IF NOT EXISTS meet_snapshots (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  meeting_id    INTEGER NOT NULL,
  version       INTEGER NOT NULL,
  sha256        TEXT NOT NULL,
  data_as_of    TEXT,
  schema_version INTEGER NOT NULL,
  json          TEXT NOT NULL,
  frozen        INTEGER NOT NULL DEFAULT 0,
  reopen_reason TEXT DEFAULT '',
  reopened_by   TEXT DEFAULT '',
  created_at    TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_meet_snap_version ON meet_snapshots(meeting_id, version);
CREATE TRIGGER IF NOT EXISTS meet_snap_frozen_upd BEFORE UPDATE ON meet_snapshots
  WHEN OLD.frozen = 1 BEGIN SELECT RAISE(ABORT, 'meet_snapshot_frozen'); END;
CREATE TRIGGER IF NOT EXISTS meet_snap_frozen_del BEFORE DELETE ON meet_snapshots
  WHEN OLD.frozen = 1 BEGIN SELECT RAISE(ABORT, 'meet_snapshot_frozen'); END;

CREATE TABLE IF NOT EXISTS meet_decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id INTEGER NOT NULL,
  text TEXT NOT NULL, amount_sar REAL, lid INTEGER, created_by TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS meet_commitments (
  id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id INTEGER NOT NULL,
  side TEXT NOT NULL, text TEXT NOT NULL, role TEXT DEFAULT '', due TEXT, lid INTEGER,
  status TEXT NOT NULL DEFAULT 'open', evidence TEXT DEFAULT '', linked_ticket TEXT DEFAULT '',
  created_by TEXT, created_at TEXT, updated_by TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_meet_commit_meeting ON meet_commitments(meeting_id);
CREATE TABLE IF NOT EXISTS meet_links (
  token TEXT PRIMARY KEY, meeting_id INTEGER NOT NULL, snapshot_version INTEGER NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, opens INTEGER NOT NULL DEFAULT 0, last_opened_at TEXT,
  created_by TEXT, created_at TEXT, revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS meet_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, meeting_id INTEGER, kind TEXT NOT NULL,
  detail TEXT DEFAULT '', actor TEXT DEFAULT '', at TEXT
);
CREATE INDEX IF NOT EXISTS idx_meet_events_meeting ON meet_events(meeting_id);
CREATE TABLE IF NOT EXISTS meet_abnb_imports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, data_as_of TEXT, filename TEXT, sha256 TEXT,
  rows INTEGER, fx_sar_per_usd REAL, uploaded_by TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS meet_abnb_rows (
  import_id INTEGER NOT NULL, airbnb_id TEXT NOT NULL, json TEXT NOT NULL,
  PRIMARY KEY (import_id, airbnb_id)
);
CREATE TABLE IF NOT EXISTS meet_abnb_map (
  airbnb_id TEXT PRIMARY KEY, lid INTEGER, method TEXT NOT NULL, confirmed_by TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS meet_annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
  text_ar TEXT NOT NULL, created_by TEXT, at TEXT
);
CREATE TABLE IF NOT EXISTS meet_settings (key TEXT PRIMARY KEY, value TEXT);
"""

# The first-boot annotation (spec §7 ch.4). Admin-editable afterwards; seeded only when empty.
SEED_ANNOTATIONS = (
    ("2026-09-01", "2026-09-16", "توقّف التشغيل حتى 16 سبتمبر"),
)

_inited = set()
_init_lock = threading.Lock()


def _now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure():
    path = _bdb.db_path()
    if path in _inited and os.path.exists(path):
        return
    with _init_lock:
        if path in _inited and os.path.exists(path):
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            empty = cx.execute("SELECT COUNT(*) FROM meet_annotations").fetchone()[0] == 0
            seeded = cx.execute("SELECT value FROM meet_settings WHERE key='annotations_seeded'").fetchone()
            if empty and seeded is None:
                for s, e, t in SEED_ANNOTATIONS:
                    cx.execute("INSERT INTO meet_annotations(start_date,end_date,text_ar,created_by,at) VALUES(?,?,?,?,?)",
                               (s, e, t, "seed", _now()))
                cx.execute("INSERT OR REPLACE INTO meet_settings(key,value) VALUES('annotations_seeded','1')")
            cx.commit()
        _inited.add(path)


def q(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        return [dict(r) for r in cx.execute(sql, args).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid


# ------------------------------------------------------------------ meetings
def _meeting(row):
    if row is None:
        return None
    row = dict(row)
    row["lids"] = json.loads(row.get("lids") or "[]")
    row["months"] = json.loads(row.get("months") or "[]")
    return row


def create_meeting(owner, lids, period, meeting_date, by):
    now = _now()
    return execute(
        "INSERT INTO meet_meetings(owner,lids,period_kind,period_from,period_to,months,meeting_date,"
        "state,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (owner, json.dumps([int(x) for x in lids]), period.get("kind") or "", period["start"],
         period["end"], json.dumps(period["months"]), meeting_date, "draft", by, now, now))


def meeting(mid):
    return _meeting(q1("SELECT * FROM meet_meetings WHERE id=?", (int(mid),)))


def meetings_for(owner):
    return [_meeting(r) for r in q("SELECT * FROM meet_meetings WHERE owner=? ORDER BY meeting_date DESC, id DESC",
                                   (owner,))]


def last_meeting_before(owner, meeting_date, exclude_id=None):
    """The latest PRESENTED/SENT meeting before `meeting_date` — chapter 0 and «منذ آخر اجتماع»."""
    rows = q("SELECT * FROM meet_meetings WHERE owner=? AND meeting_date<? AND state IN "
             "('presented','sent','reopened') ORDER BY meeting_date DESC, id DESC", (owner, meeting_date))
    rows = [r for r in rows if exclude_id is None or r["id"] != exclude_id]
    return _meeting(rows[0]) if rows else None


def set_build(mid, state=None, progress=None, step=None, error=None):
    sets, args = ["updated_at=?"], [_now()]
    for col, val in (("state", state), ("build_progress", progress), ("build_step", step),
                     ("build_error", error)):
        if val is not None:
            sets.append("%s=?" % col)
            args.append(val)
    args.append(int(mid))
    execute("UPDATE meet_meetings SET %s WHERE id=?" % ", ".join(sets), tuple(args))


# ------------------------------------------------------------------ snapshots
def canonical(snap):
    return json.dumps(snap, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_of(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_snapshot(mid, snap):
    """Write a NEW version (never edits an old one). -> (version, sha256)."""
    text = canonical(snap)
    sha = sha256_of(text)
    _ensure()
    with closing(_bdb.connect()) as cx:
        row = cx.execute("SELECT COALESCE(MAX(version),0) FROM meet_snapshots WHERE meeting_id=?",
                         (int(mid),)).fetchone()
        ver = int(row[0]) + 1
        cx.execute("INSERT INTO meet_snapshots(meeting_id,version,sha256,data_as_of,schema_version,json,"
                   "frozen,created_at) VALUES(?,?,?,?,?,?,0,?)",
                   (int(mid), ver, sha, (snap.get("meta") or {}).get("data_as_of"), SCHEMA_VERSION, text,
                    _now()))
        cx.commit()
    return ver, sha


def snapshot(mid, version=None):
    if version is None:
        row = q1("SELECT * FROM meet_snapshots WHERE meeting_id=? ORDER BY version DESC LIMIT 1", (int(mid),))
    else:
        row = q1("SELECT * FROM meet_snapshots WHERE meeting_id=? AND version=?", (int(mid), int(version)))
    if row is None:
        return None
    row["data"] = json.loads(row["json"])
    return row


def freeze(mid, version):
    execute("UPDATE meet_snapshots SET frozen=1 WHERE meeting_id=? AND version=? AND frozen=0",
            (int(mid), int(version)))


def log_event(mid, kind, detail="", actor=""):
    execute("INSERT INTO meet_events(meeting_id,kind,detail,actor,at) VALUES(?,?,?,?,?)",
            (mid, kind, detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False),
             actor or "", _now()))


def fail_interrupted():
    """At boot: a build that was running when the container stopped can never finish — say so
    instead of leaving the tab spinning on «جاري التجهيز» forever. -> rows changed."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute("UPDATE meet_meetings SET state='error', build_error=?, updated_at=? WHERE state='building'",
                         ("انقطع التجهيز بسبب إعادة تشغيل النظام — اضغط «تجهيز الاجتماع» مرة ثانية", _now()))
        cx.commit()
        return cur.rowcount


# ------------------------------------------------------------------ annotations
def annotations():
    return q("SELECT id,start_date,end_date,text_ar FROM meet_annotations ORDER BY start_date")


# ------------------------------------------------------------------ the meeting record (S5)
SIDES = ("decision", "ouja", "owner")
STATUSES = ("open", "in_progress", "done", "not_done")


def add_decision(mid, text, amount_sar=None, lid=None, by=""):
    return execute("INSERT INTO meet_decisions(meeting_id,text,amount_sar,lid,created_by,at) VALUES(?,?,?,?,?,?)",
                   (int(mid), text, amount_sar, lid, by, _now()))


def add_commitment(mid, side, text, role="", due=None, lid=None, linked_ticket="", by=""):
    now = _now()
    return execute("INSERT INTO meet_commitments(meeting_id,side,text,role,due,lid,status,evidence,linked_ticket,"
                   "created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,'open','',?,?,?,?,?)",
                   (int(mid), side, text, role or "", due, lid, linked_ticket or "", by, now, by, now))


def update_commitment(cid, status=None, evidence=None, linked_ticket=None, by=""):
    sets, args = ["updated_by=?", "updated_at=?"], [by, _now()]
    for col, val in (("status", status), ("evidence", evidence), ("linked_ticket", linked_ticket)):
        if val is not None:
            sets.append("%s=?" % col)
            args.append(val)
    args.append(int(cid))
    execute("UPDATE meet_commitments SET %s WHERE id=?" % ", ".join(sets), tuple(args))


def commitment(cid):
    return q1("SELECT * FROM meet_commitments WHERE id=?", (int(cid),))


def delete_record(kind, rid):
    table = "meet_decisions" if kind == "decision" else "meet_commitments"
    execute("DELETE FROM %s WHERE id=?" % table, (int(rid),))


def record(mid):
    return {"decisions": q("SELECT * FROM meet_decisions WHERE meeting_id=? ORDER BY id", (int(mid),)),
            "commitments": q("SELECT * FROM meet_commitments WHERE meeting_id=? ORDER BY id", (int(mid),))}


# ------------------------------------------------------------------ owner links (S5)
def create_link(token, mid, version, by):
    execute("INSERT INTO meet_links(token,meeting_id,snapshot_version,active,opens,created_by,created_at) "
            "VALUES(?,?,?,1,0,?,?)", (token, int(mid), int(version), by, _now()))


def link(token):
    return q1("SELECT * FROM meet_links WHERE token=?", (token,))


def links_for(mid):
    return q("SELECT token, snapshot_version, active, opens, last_opened_at, created_at, revoked_at FROM meet_links "
             "WHERE meeting_id=? ORDER BY created_at DESC", (int(mid),))


def active_link(mid, version):
    return q1("SELECT * FROM meet_links WHERE meeting_id=? AND snapshot_version=? AND active=1 ORDER BY created_at DESC LIMIT 1",
              (int(mid), int(version)))


def touch_link(token):
    execute("UPDATE meet_links SET opens=opens+1, last_opened_at=? WHERE token=?", (_now(), token))


def revoke_link(token):
    execute("UPDATE meet_links SET active=0, revoked_at=? WHERE token=?", (_now(), token))
