# -*- coding: utf-8 -*-
"""
contracting_* tables inside the SAME brain.db (NO WAL, journal DELETE, one short connection
per call via `closing(connect())` — the proven rules in CLAUDE.md / brain memory).

Two guarantees live here, not in the callers:
  - `claim()` is the ONLY way a reminder is recorded, and `contracting_sent.key` is the
    PRIMARY KEY: one reminder key = at most one message, ever (a restart mid-tick cannot
    double-post — the ops/oncall lesson).
  - a line is `done` only through `add_photos()` reaching PHOTOS_NEEDED. Pressing «خلص»
    alone moves it to `awaiting_photos`, nothing more. Photos dropped BEFORE the press are
    not lost (owner 2026-11-24): they wait in contracting_photo_batches until someone picks
    their line, and picking a line counts as its «خلص». The single exception is
    `mark_done()` — admin-only, from the dashboard, logged as `done_manual` (owner
    2026-11-24: the D2 survey was finished before the project started).
"""

import datetime
import json
import threading
import uuid
from contextlib import closing

from brain import db as _bdb

PHOTOS_NEEDED = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracting_projects (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    owner         TEXT,
    unit          TEXT,
    supervisor    TEXT,
    total_sar     REAL,
    signed        INTEGER NOT NULL DEFAULT 0,
    paid          INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'draft',      -- draft | active | done | cancelled
    channel_id    TEXT,
    channel_error TEXT,
    source        TEXT,                               -- where the lines came from (quote ref)
    created_by    TEXT,
    created_at    TEXT NOT NULL,
    started_by    TEXT,
    started_at    TEXT,                               -- Riyadh wall clock, naive ISO
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_ctr_proj_status ON contracting_projects(status);

CREATE TABLE IF NOT EXISTS contracting_items (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    pos           INTEGER NOT NULL,
    name          TEXT NOT NULL,
    amount_sar    REAL,
    due           TEXT,                               -- ISO date
    status        TEXT NOT NULL DEFAULT 'open',       -- open | awaiting_photos | blocked | done
    is_handover   INTEGER NOT NULL DEFAULT 0,
    photos        TEXT,                               -- JSON [{url, by, at}]
    proof_by      TEXT,
    done_by       TEXT,
    done_at       TEXT,
    blocked_at    TEXT,
    blocked_reason TEXT,
    delays        INTEGER NOT NULL DEFAULT 0,
    ask_msg_id    TEXT,
    updated_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_ctr_items_proj ON contracting_items(project_id, pos);

CREATE TABLE IF NOT EXISTS contracting_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    item_id     TEXT,
    kind        TEXT NOT NULL,     -- created | start | due_edit | delay | blocked | pressed_done | photo | done
    actor       TEXT,
    text        TEXT,
    old_due     TEXT,
    new_due     TEXT,
    at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ctr_events_proj ON contracting_events(project_id, at);

CREATE TABLE IF NOT EXISTS contracting_sent (
    key         TEXT PRIMARY KEY,
    project_id  TEXT,
    item_id     TEXT,
    kind        TEXT NOT NULL,
    text        TEXT,
    dryrun      INTEGER NOT NULL DEFAULT 0,
    delivered   INTEGER NOT NULL DEFAULT 0,
    error       TEXT,
    msg_id      TEXT,
    at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contracting_people (
    name        TEXT PRIMARY KEY,
    role        TEXT NOT NULL,     -- site | lead | boss | account
    did         TEXT,
    updated_at  TEXT,
    updated_by  TEXT
);

CREATE TABLE IF NOT EXISTS contracting_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Photos that arrived when the bot could not tell which line they prove (none or several
-- lines waiting). The channel gets a «لأي بند؟» picker; the choice resolves the batch.
-- choice: item id | 'progress' (work-in-progress, kept for the owner's file) | 'ignore'.
CREATE TABLE IF NOT EXISTS contracting_photo_batches (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    message_id    TEXT,
    photos        TEXT,                               -- JSON [{url, file, by, at, msg}]
    by            TEXT,
    at            TEXT NOT NULL,
    picker_msg_id TEXT,
    choice        TEXT,
    resolved_by   TEXT,
    resolved_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_ctr_batches_proj ON contracting_photo_batches(project_id, at);
"""

_inited = set()
_init_lock = threading.Lock()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()


def now_iso():
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


def _uid(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:10])


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
        return cur.rowcount


def _j(v, default):
    try:
        return json.loads(v) if v else default
    except (ValueError, TypeError):
        return default


def event(project_id, kind, actor="", text="", item_id=None, old_due=None, new_due=None):
    execute("INSERT INTO contracting_events (project_id, item_id, kind, actor, text, old_due, "
            "new_due, at) VALUES (?,?,?,?,?,?,?,?)",
            (project_id, item_id, kind, actor, (text or "")[:500], old_due, new_due, now_iso()))


def meta(key, default=None):
    r = q1("SELECT value FROM contracting_meta WHERE key=?", (key,))
    return r["value"] if r else default


def set_meta(key, value):
    execute("INSERT INTO contracting_meta (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


# ---------------------------------------------------------------- projects

def _item_out(r):
    r = dict(r)
    r["photos"] = _j(r.get("photos"), [])
    return r


def items(project_id):
    return [_item_out(r) for r in
            q("SELECT * FROM contracting_items WHERE project_id=? ORDER BY pos", (project_id,))]


def item(item_id):
    r = q1("SELECT * FROM contracting_items WHERE id=?", (item_id,))
    return _item_out(r) if r else None


def project(project_id, with_items=True):
    p = q1("SELECT * FROM contracting_projects WHERE id=?", (project_id,))
    if p and with_items:
        p["items"] = items(project_id)
    return p


def projects(statuses=None):
    if statuses:
        marks = ",".join("?" * len(statuses))
        rows = q("SELECT * FROM contracting_projects WHERE status IN (%s) ORDER BY created_at"
                 % marks, tuple(statuses))
    else:
        rows = q("SELECT * FROM contracting_projects WHERE status!='cancelled' ORDER BY created_at")
    for p in rows:
        p["items"] = items(p["id"])
    return rows


def project_by_channel(channel_id):
    p = q1("SELECT * FROM contracting_projects WHERE channel_id=?", (str(channel_id),))
    if p:
        p["items"] = items(p["id"])
    return p


def _write_items(cx, project_id, lines, handover_due):
    cx.execute("DELETE FROM contracting_items WHERE project_id=?", (project_id,))
    pos = 0
    for ln in lines:
        name = str(ln.get("name") or "").strip()
        if not name:
            continue
        pos += 1
        cx.execute("INSERT INTO contracting_items (id, project_id, pos, name, amount_sar, due, "
                   "updated_at) VALUES (?,?,?,?,?,?,?)",
                   (ln.get("id") or _uid("ci"), project_id, pos, name[:160], ln.get("amount"),
                    (ln.get("due") or "")[:10] or None, now_iso()))
    cx.execute("INSERT INTO contracting_items (id, project_id, pos, name, due, is_handover, "
               "updated_at) VALUES (?,?,?,?,?,1,?)",
               (_uid("ci"), project_id, pos + 1, "فحص وتسليم", handover_due or None, now_iso()))


def create_project(title, lines, by="", owner="", unit="", supervisor="", total_sar=None,
                   signed=0, paid=0, source="", handover_due=""):
    """A DRAFT with its lines, plus «فحص وتسليم» as the last line. Nothing reaches Discord
    until start_project()."""
    _ensure()
    pid = _uid("cp")
    with closing(_bdb.connect()) as cx:
        cx.execute("INSERT INTO contracting_projects (id, title, owner, unit, supervisor, "
                   "total_sar, signed, paid, source, created_by, created_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (pid, str(title).strip()[:120], owner, unit, supervisor, total_sar,
                    1 if signed else 0, 1 if paid else 0, source, by, now_iso()))
        _write_items(cx, pid, lines, handover_due)
        cx.commit()
    event(pid, "created", by, title)
    return project(pid)


DRAFT_FIELDS = ("title", "owner", "unit", "supervisor", "total_sar", "signed", "paid")


def save_draft(project_id, fields, dues, by=""):
    """Edit a draft: header fields + each line's date ({item_id: iso}). Lines themselves are
    the quote's and are not edited here."""
    p = project(project_id, with_items=False)
    if not p:
        return None, "المشروع مو موجود"
    if p["status"] != "draft":
        return None, "المشروع بدأ — التواريخ تتغير من سطر البند"
    sets, args = [], []
    for k in DRAFT_FIELDS:
        if k in fields:
            v = fields[k]
            if k in ("signed", "paid"):
                v = 1 if v else 0
            elif k == "total_sar":
                try:
                    v = float(v) if v not in (None, "") else None
                except (TypeError, ValueError):
                    v = p.get("total_sar")
            else:
                v = str(v or "").strip()[:120]
            sets.append("%s=?" % k)
            args.append(v)
    _ensure()
    with closing(_bdb.connect()) as cx:
        if sets:
            cx.execute("UPDATE contracting_projects SET %s, updated_at=? WHERE id=?"
                       % ", ".join(sets), tuple(args) + (now_iso(), project_id))
        for iid, due in (dues or {}).items():
            cx.execute("UPDATE contracting_items SET due=?, updated_at=? WHERE id=? AND project_id=?",
                       ((due or "")[:10] or None, now_iso(), iid, project_id))
        cx.commit()
    return project(project_id), ""


def delete_draft(project_id, by=""):
    p = project(project_id, with_items=False)
    if not p or p["status"] != "draft":
        return False
    execute("UPDATE contracting_projects SET status='cancelled', updated_at=? WHERE id=?",
            (now_iso(), project_id))
    event(project_id, "cancelled", by)
    return True


def start_project(project_id, by, started_at_local):
    n = execute("UPDATE contracting_projects SET status='active', started_by=?, started_at=?, "
                "updated_at=? WHERE id=? AND status='draft'",
                (by, started_at_local, now_iso(), project_id))
    if n:
        event(project_id, "start", by)
    return bool(n)


def set_channel(project_id, channel_id):
    execute("UPDATE contracting_projects SET channel_id=?, channel_error=NULL, updated_at=? "
            "WHERE id=?", (str(channel_id), now_iso(), project_id))


def set_channel_error(project_id, err):
    execute("UPDATE contracting_projects SET channel_error=?, updated_at=? WHERE id=?",
            (str(err)[:300], now_iso(), project_id))


# ---------------------------------------------------------------- line actions

def set_due(item_id, new_due, actor, reason="", kind="due_edit"):
    it = item(item_id)
    if not it:
        return None
    execute("UPDATE contracting_items SET due=?, status=CASE WHEN status='done' THEN 'done' "
            "ELSE 'open' END, delays=delays+?, blocked_at=NULL, updated_at=? WHERE id=?",
            (new_due, 1 if kind == "delay" else 0, now_iso(), item_id))
    event(it["project_id"], kind, actor, reason, item_id, it.get("due"), new_due)
    return item(item_id)


def press_done(item_id, actor):
    it = item(item_id)
    if not it or it["status"] == "done":
        return it
    execute("UPDATE contracting_items SET status='awaiting_photos', proof_by=?, blocked_at=NULL, "
            "updated_at=? WHERE id=?", (actor, now_iso(), item_id))
    event(it["project_id"], "pressed_done", actor, "", item_id)
    return item(item_id)


def block(item_id, actor, reason, at_local):
    it = item(item_id)
    if not it or it["status"] == "done":
        return it
    execute("UPDATE contracting_items SET status='blocked', blocked_at=?, blocked_reason=?, "
            "updated_at=? WHERE id=?", (at_local, (reason or "")[:300], now_iso(), item_id))
    event(it["project_id"], "blocked", actor, reason, item_id)
    return item(item_id)


def awaiting_photo_item(project_id):
    """The line photos in this channel belong to: the most recent «خلص» press."""
    r = q1("SELECT * FROM contracting_items WHERE project_id=? AND status='awaiting_photos' "
           "ORDER BY updated_at DESC LIMIT 1", (project_id,))
    return _item_out(r) if r else None


def _photo_rows(photos, actor):
    """urls (str) or ready dicts {url, file, msg} → stored rows."""
    out = []
    for u in photos or []:
        d = dict(u) if isinstance(u, dict) else {"url": u}
        if not d.get("url") and not d.get("file"):
            continue
        d.setdefault("by", actor)
        d.setdefault("at", now_iso())
        out.append(d)
    return out


def add_photos(item_id, urls, actor):
    """→ (item, became_done). Done only at PHOTOS_NEEDED photos."""
    it = item(item_id)
    if not it or it["status"] != "awaiting_photos":
        return it, False
    ph = it["photos"] + _photo_rows(urls, actor)
    done = len(ph) >= PHOTOS_NEEDED
    execute("UPDATE contracting_items SET photos=?, status=?, done_by=?, done_at=?, updated_at=? "
            "WHERE id=?",
            (json.dumps(ph, ensure_ascii=False), "done" if done else "awaiting_photos",
             actor if done else None, now_iso() if done else None, now_iso(), item_id))
    event(it["project_id"], "done" if done else "photo", actor, "%d صور" % len(ph), item_id)
    return item(item_id), done


def awaiting_items(project_id):
    return [_item_out(r) for r in
            q("SELECT * FROM contracting_items WHERE project_id=? AND status='awaiting_photos' "
              "ORDER BY updated_at DESC", (project_id,))]


def new_batch(project_id, photos, actor, message_id=""):
    bid = _uid("cb")
    execute("INSERT INTO contracting_photo_batches (id, project_id, message_id, photos, by, at) "
            "VALUES (?,?,?,?,?,?)",
            (bid, project_id, str(message_id or ""),
             json.dumps(_photo_rows(photos, actor), ensure_ascii=False), actor, now_iso()))
    return batch(bid)


def batch(batch_id):
    r = q1("SELECT * FROM contracting_photo_batches WHERE id=?", (batch_id,))
    if r:
        r["photos"] = _j(r.get("photos"), [])
    return r


def batches(project_id, choice=None):
    rows = q("SELECT * FROM contracting_photo_batches WHERE project_id=?" +
             (" AND choice=?" if choice else "") + " ORDER BY at",
             (project_id, choice) if choice else (project_id,))
    for r in rows:
        r["photos"] = _j(r.get("photos"), [])
    return rows


def set_batch_picker(batch_id, msg_id):
    execute("UPDATE contracting_photo_batches SET picker_msg_id=? WHERE id=?",
            (str(msg_id or ""), batch_id))


def resolve_batch(batch_id, choice, actor):
    """First answer wins — two people picking at once cannot count the photos twice."""
    n = execute("UPDATE contracting_photo_batches SET choice=?, resolved_by=?, resolved_at=? "
                "WHERE id=? AND choice IS NULL", (choice, actor, now_iso(), batch_id))
    return bool(n)


def known_photo_msgs(project_id):
    """Discord message ids whose photos are already counted somewhere (line or batch)."""
    seen = set()
    for it in items(project_id):
        seen |= {str(x.get("msg")) for x in it["photos"] if x.get("msg")}
    for b in batches(project_id):
        seen |= {str(x.get("msg")) for x in b["photos"] if x.get("msg")}
        if b.get("message_id"):
            seen.add(str(b["message_id"]))
    return seen


def mark_done(item_id, actor, note=""):
    """The ONE way a line is done without photos: an admin, from the dashboard, for work
    finished before the system knew about it. Logged as done_manual with who and why."""
    it = item(item_id)
    if not it or it["status"] == "done":
        return it
    execute("UPDATE contracting_items SET status='done', done_by=?, done_at=?, blocked_at=NULL, "
            "updated_at=? WHERE id=?", (actor, now_iso(), now_iso(), item_id))
    event(it["project_id"], "done_manual", actor, note or "انعلّم خالص من الداشبورد (بدون صور)",
          item_id)
    return item(item_id)


def finish_if_complete(project_id):
    """Every line done (handover included) → the project is done and goes quiet."""
    its = items(project_id)
    if its and all(i["status"] == "done" for i in its):
        n = execute("UPDATE contracting_projects SET status='done', updated_at=? "
                    "WHERE id=? AND status='active'", (now_iso(), project_id))
        if n:
            event(project_id, "finished", "system")
        return bool(n)
    return False


def events(project_id, limit=40):
    return q("SELECT * FROM contracting_events WHERE project_id=? ORDER BY id DESC LIMIT ?",
             (project_id, limit))


# ---------------------------------------------------------------- reminders sent

def claim(key, kind, project_id=None, item_id=None, text="", dryrun=False):
    """True only for the first caller of a key — ever."""
    try:
        n = execute("INSERT OR IGNORE INTO contracting_sent (key, project_id, item_id, kind, text, "
                    "dryrun, at) VALUES (?,?,?,?,?,?,?)",
                    (key, project_id, item_id, kind, (text or "")[:1900], 1 if dryrun else 0,
                     now_iso()))
    except Exception as e:
        print("[contracting] claim failed:", e)
        return False
    return n == 1


def unclaim(key):
    execute("DELETE FROM contracting_sent WHERE key=?", (key,))


def delivered(key, ok, msg_id="", error=""):
    execute("UPDATE contracting_sent SET delivered=?, msg_id=?, error=? WHERE key=?",
            (1 if ok else 0, str(msg_id or ""), (error or "")[:300], key))


def sent_keys(project_id=None, dryrun=False):
    """(claimed, landed). Live: `landed` = actually posted. Dry-run: posted OR recorded
    in the dry-run log — so flipping to live never lets an escalation accuse someone about
    a question that only ever existed in the log."""
    rows = q("SELECT key, delivered, dryrun FROM contracting_sent" +
             (" WHERE project_id=?" if project_id else ""), (project_id,) if project_id else ())
    claimed = {r["key"] for r in rows}
    landed = {r["key"] for r in rows if r["delivered"] or (dryrun and r["dryrun"])}
    return claimed, landed


def sent_log(limit=60):
    return q("SELECT * FROM contracting_sent ORDER BY at DESC LIMIT ?", (limit,))


def set_ask_msg(item_id, msg_id):
    execute("UPDATE contracting_items SET ask_msg_id=? WHERE id=?", (str(msg_id), item_id))


# ---------------------------------------------------------------- people

def people():
    return q("SELECT * FROM contracting_people ORDER BY CASE role WHEN 'boss' THEN 0 "
             "WHEN 'lead' THEN 1 WHEN 'account' THEN 2 ELSE 3 END, name")


def person(name):
    return q1("SELECT * FROM contracting_people WHERE name=?", (str(name or "").strip(),))


def set_person(name, role=None, did=None, by=""):
    name = str(name or "").strip()[:60]
    if not name:
        return None
    cur = person(name)
    role = role or (cur or {}).get("role") or "site"
    did = (cur or {}).get("did") if did is None else "".join(ch for ch in str(did) if ch.isdigit())
    execute("INSERT INTO contracting_people (name, role, did, updated_at, updated_by) "
            "VALUES (?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET role=excluded.role, "
            "did=excluded.did, updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (name, role, did or "", now_iso(), by))
    return person(name)


def names_with_role(role):
    return [p["name"] for p in people() if p["role"] == role]


def counts():
    out = {}
    for t in ("contracting_projects", "contracting_items", "contracting_events",
              "contracting_sent", "contracting_people", "contracting_photo_batches"):
        out[t] = q1("SELECT COUNT(*) AS n FROM %s" % t)["n"]
    return out
