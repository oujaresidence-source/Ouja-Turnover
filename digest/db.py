# -*- coding: utf-8 -*-
"""digest_* tables inside the SAME brain.db SQLite file (NO WAL, journal DELETE,
busy_timeout, closing(connect()) — the proven rules; see CLAUDE.md brain-sqlite notes).

digest_issues      — one row per weekend (week_of = the Thursday, UNIQUE). That UNIQUE
                     constraint IS the scheduler's latch: a redeploy cannot post twice.
digest_items       — the items that shipped (or were dropped) for an issue.
digest_candidates  — the ranked alternates per slot, pre-built so «بدائل» is instant.
digest_rulings     — every owner button press (who / when / what); rank.py learns from it."""

import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS digest_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  week_of TEXT NOT NULL UNIQUE,
  issue_no INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'building',
  payload TEXT NOT NULL DEFAULT '',
  html_sha TEXT NOT NULL DEFAULT '',
  msg_id INTEGER,
  channel_id INTEGER,
  rebuilds INTEGER NOT NULL DEFAULT 0,
  error TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  published_at TEXT
);
CREATE TABLE IF NOT EXISTS digest_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue_id INTEGER NOT NULL,
  section TEXT NOT NULL,
  slot INTEGER NOT NULL,
  item TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'primary'
);
CREATE TABLE IF NOT EXISTS digest_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue_id INTEGER NOT NULL,
  section TEXT NOT NULL,
  slot INTEGER NOT NULL,
  rank INTEGER NOT NULL,
  score REAL NOT NULL DEFAULT 0,
  cand TEXT NOT NULL,
  reasons TEXT NOT NULL DEFAULT '[]',
  used INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS digest_rulings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue_id INTEGER NOT NULL,
  ts TEXT NOT NULL,
  who TEXT NOT NULL,
  action TEXT NOT NULL,
  section TEXT,
  slot INTEGER,
  detail TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_digest_cand ON digest_candidates(issue_id, section, slot, rank);
CREATE INDEX IF NOT EXISTS ix_digest_items ON digest_items(issue_id, section, slot);
"""

# Additive columns for brains created before a schema change: (table, col, decl).
_MIGRATIONS = ()

_inited = set()
_init_lock = threading.Lock()

ISSUE_COLS = ("status", "payload", "html_sha", "msg_id", "channel_id", "rebuilds",
              "error", "published_at")


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            for table, col, decl in _MIGRATIONS:
                cols = {r[1] for r in cx.execute("PRAGMA table_info(%s)" % table)}
                if col not in cols:
                    cx.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()


def q(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.row_factory = sqlite3.Row
        return [dict(r) for r in cx.execute(sql, args).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def execute(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount


def now_iso():
    """Riyadh time when wired, UTC otherwise (tests) — never a naive clock."""
    try:
        from .host import HOST
        if HOST.now:
            return HOST.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _dumps(v):
    return json.dumps(v, ensure_ascii=False)


def _loads(s, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


# ---------------- issues ----------------

def _hydrate_issue(row):
    if row is None:
        return None
    row["payload"] = _loads(row.get("payload"), {})
    return row


def open_issue(week_of, issue_no):
    """Create the issue row for a weekend. Raises sqlite3.IntegrityError if the week
    already has one — that is the latch, and callers rely on it."""
    ts = now_iso()
    return execute(
        "INSERT INTO digest_issues(week_of, issue_no, status, created_at, updated_at) "
        "VALUES(?,?,?,?,?)", (week_of, int(issue_no), "building", ts, ts))


def next_issue_no():
    r = q1("SELECT MAX(issue_no) AS m FROM digest_issues")
    return int((r or {}).get("m") or 0) + 1


def issue_for_week(week_of):
    return _hydrate_issue(q1("SELECT * FROM digest_issues WHERE week_of=?", (week_of,)))


def issue(issue_id):
    return _hydrate_issue(q1("SELECT * FROM digest_issues WHERE id=?", (int(issue_id),)))


def issue_by_msg(msg_id):
    return _hydrate_issue(q1("SELECT * FROM digest_issues WHERE msg_id=?", (int(msg_id),)))


def latest_issue():
    return _hydrate_issue(q1("SELECT * FROM digest_issues ORDER BY issue_no DESC, id DESC LIMIT 1"))


def set_issue(issue_id, **cols):
    sets, args = [], []
    for k, v in cols.items():
        if k not in ISSUE_COLS:
            raise ValueError("digest.db.set_issue: unknown column %r" % k)
        if k == "payload" and not isinstance(v, str):
            v = _dumps(v)
        sets.append("%s=?" % k)
        args.append(v)
    sets.append("updated_at=?")
    args.append(now_iso())
    args.append(int(issue_id))
    return execute("UPDATE digest_issues SET %s WHERE id=?" % ", ".join(sets), tuple(args))


def bump_rebuilds(issue_id):
    execute("UPDATE digest_issues SET rebuilds=rebuilds+1, updated_at=? WHERE id=?",
            (now_iso(), int(issue_id)))
    return int((issue(issue_id) or {}).get("rebuilds") or 0)


# ---------------- items ----------------

def set_items(issue_id, items):
    """Replace the issue's item rows. Each item dict carries section/slot and an
    optional state ('primary' default, or 'dropped')."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("DELETE FROM digest_items WHERE issue_id=?", (int(issue_id),))
        for it in items or []:
            cx.execute("INSERT INTO digest_items(issue_id, section, slot, item, state) VALUES(?,?,?,?,?)",
                       (int(issue_id), it.get("section", ""), int(it.get("slot", 0)),
                        _dumps(it), it.get("state") or "primary"))
        cx.commit()


def items(issue_id):
    rows = q("SELECT * FROM digest_items WHERE issue_id=? ORDER BY section, slot", (int(issue_id),))
    for r in rows:
        r["item"] = _loads(r.get("item"), {})
    return rows


def recent_issue_urls(n=6):
    """URLs that shipped as primaries in the last n issues — rank.py's novelty term."""
    ids = [r["id"] for r in q("SELECT id FROM digest_issues ORDER BY issue_no DESC, id DESC LIMIT ?",
                              (int(n),))]
    if not ids:
        return set()
    marks = ",".join("?" for _ in ids)
    rows = q("SELECT item FROM digest_items WHERE state='primary' AND issue_id IN (%s)" % marks,
             tuple(ids))
    out = set()
    for r in rows:
        u = (_loads(r.get("item"), {}) or {}).get("url")
        if u:
            out.add(u)
    return out


# ---------------- candidates (alternates) ----------------

def add_candidates(issue_id, section, slot, ranked):
    """Store the ranked candidates for one slot, best first; replaces any previous set."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("DELETE FROM digest_candidates WHERE issue_id=? AND section=? AND slot=?",
                   (int(issue_id), section, int(slot)))
        for i, c in enumerate(ranked or [], start=1):
            cx.execute(
                "INSERT INTO digest_candidates(issue_id, section, slot, rank, score, cand, reasons) "
                "VALUES(?,?,?,?,?,?,?)",
                (int(issue_id), section, int(slot), i, float(c.get("score") or 0.0),
                 _dumps(c), _dumps(c.get("reasons") or [])))
        cx.commit()


def candidates(issue_id, section, slot):
    rows = q("SELECT * FROM digest_candidates WHERE issue_id=? AND section=? AND slot=? ORDER BY rank",
             (int(issue_id), section, int(slot)))
    for r in rows:
        r["cand"] = _loads(r.get("cand"), {})
        r["reasons"] = _loads(r.get("reasons"), [])
    return rows


def all_candidates(issue_id):
    rows = q("SELECT * FROM digest_candidates WHERE issue_id=? ORDER BY section, slot, rank",
             (int(issue_id),))
    for r in rows:
        r["cand"] = _loads(r.get("cand"), {})
        r["reasons"] = _loads(r.get("reasons"), [])
    return rows


def mark_candidate_used(cand_id):
    execute("UPDATE digest_candidates SET used=1 WHERE id=?", (int(cand_id),))


# ---------------- rulings ----------------

def add_ruling(issue_id, who, action, section=None, slot=None, detail=None):
    return execute(
        "INSERT INTO digest_rulings(issue_id, ts, who, action, section, slot, detail) VALUES(?,?,?,?,?,?,?)",
        (int(issue_id), now_iso(), who or "", action or "", section,
         None if slot is None else int(slot), _dumps(detail or {})))


def rulings(limit=500):
    rows = q("SELECT * FROM digest_rulings ORDER BY id DESC LIMIT ?", (int(limit),))
    for r in rows:
        r["detail"] = _loads(r.get("detail"), {})
    return rows


def rulings_for(issue_id):
    rows = q("SELECT * FROM digest_rulings WHERE issue_id=? ORDER BY id", (int(issue_id),))
    for r in rows:
        r["detail"] = _loads(r.get("detail"), {})
    return rows
