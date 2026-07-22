# -*- coding: utf-8 -*-
"""studio_* tables inside the SAME brain.db SQLite file (NO WAL, journal DELETE,
busy_timeout, closing(connect()) — the proven rules; see CLAUDE.md brain-sqlite notes).

studio_scanned  — every conversation the miner has looked at (dedup cursor: a
                  convo is never re-sent to Claude). Guest name lives ONLY here.
studio_stories  — extracted story cards (already name-scrubbed).
studio_ideas    — generated video-idea cards + their lifecycle/performance."""

import json
import sqlite3
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS studio_scanned (
    convo_id   TEXT PRIMARY KEY,
    listing_id TEXT,
    unit       TEXT,
    guest      TEXT,
    res_status TEXT,
    stay_dates TEXT,
    msgs_n     INTEGER NOT NULL DEFAULT 0,
    verdict    TEXT,
    score      INTEGER NOT NULL DEFAULT 0,
    story_type TEXT,
    one_line   TEXT,
    scanned_at TEXT
);
CREATE TABLE IF NOT EXISTS studio_stories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    convo_id   TEXT UNIQUE,
    listing_id TEXT,
    unit       TEXT,
    score      INTEGER NOT NULL DEFAULT 0,
    story_type TEXT,
    title      TEXT,
    summary    TEXT,
    angle      TEXT NOT NULL DEFAULT '',
    beats      TEXT NOT NULL DEFAULT '[]',
    quotes     TEXT NOT NULL DEFAULT '[]',
    emotion    TEXT,
    lesson     TEXT,
    status     TEXT NOT NULL DEFAULT 'new',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS studio_ideas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id     INTEGER,
    hook_spoken  TEXT,
    visual_title TEXT,
    visual_sub   TEXT,
    angle        TEXT,
    script       TEXT NOT NULL DEFAULT '[]',
    video_type   TEXT,
    cta          TEXT,
    audience     TEXT,
    trigger_kind TEXT,
    why_it_works TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'new',
    views        INTEGER NOT NULL DEFAULT 0,
    perf_note    TEXT NOT NULL DEFAULT '',
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS studio_signals (
    sid        TEXT PRIMARY KEY,
    family     TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    title      TEXT NOT NULL DEFAULT '',
    fact       TEXT NOT NULL DEFAULT '',
    detail     TEXT NOT NULL DEFAULT '',
    url        TEXT NOT NULL DEFAULT '',
    as_of      TEXT NOT NULL DEFAULT '',
    strength   INTEGER NOT NULL DEFAULT 50,
    ref        TEXT NOT NULL DEFAULT '',
    nkey       TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'new',
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS studio_plan (
    day        TEXT NOT NULL,
    slot       INTEGER NOT NULL DEFAULT 0,
    idea_id    INTEGER NOT NULL,
    created_at TEXT,
    PRIMARY KEY (day, slot)
);
"""

# Additive columns for brains created before v2 (2026-07-08). CREATE TABLE IF NOT
# EXISTS won't add columns to an existing table, so ALTER them in idempotently.
_MIGRATIONS = (
    ("studio_stories", "angle", "TEXT NOT NULL DEFAULT ''"),
    ("studio_ideas", "why_it_works", "TEXT NOT NULL DEFAULT ''"),
    # v3 (2026-07-23): an idea now carries the SIGNAL it is grounded in (spec F3),
    # its freshness date (F10), a predicted strength (F9) and a novelty fingerprint.
    ("studio_ideas", "signal_sid", "TEXT NOT NULL DEFAULT ''"),
    ("studio_ideas", "signal_family", "TEXT NOT NULL DEFAULT ''"),
    ("studio_ideas", "signal_source", "TEXT NOT NULL DEFAULT ''"),
    ("studio_ideas", "signal_text", "TEXT NOT NULL DEFAULT ''"),
    ("studio_ideas", "signal_url", "TEXT NOT NULL DEFAULT ''"),
    ("studio_ideas", "signal_date", "TEXT NOT NULL DEFAULT ''"),
    ("studio_ideas", "strength", "INTEGER NOT NULL DEFAULT 0"),
    ("studio_ideas", "nkey", "TEXT NOT NULL DEFAULT ''"),
)

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


# ---------------- scanned cursor ----------------

def scanned_ids():
    return {r["convo_id"] for r in q("SELECT convo_id FROM studio_scanned")}


def mark_scanned(convo_id, listing_id, unit, guest, res_status, stay_dates,
                 msgs_n, verdict, score=0, story_type="", one_line="", ts=""):
    execute(
        "INSERT OR REPLACE INTO studio_scanned "
        "(convo_id, listing_id, unit, guest, res_status, stay_dates, msgs_n, "
        " verdict, score, story_type, one_line, scanned_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(convo_id), str(listing_id or ""), unit or "", guest or "",
         res_status or "", stay_dates or "", int(msgs_n or 0), verdict,
         int(score or 0), story_type or "", one_line or "", ts))


def scan_counts():
    rows = q("SELECT verdict, COUNT(*) n FROM studio_scanned GROUP BY verdict")
    return {r["verdict"]: r["n"] for r in rows}


# ---------------- stories ----------------

def add_story(convo_id, listing_id, unit, score, story_type, story, ts):
    return execute(
        "INSERT OR IGNORE INTO studio_stories "
        "(convo_id, listing_id, unit, score, story_type, title, summary, angle, beats, "
        " quotes, emotion, lesson, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(convo_id), str(listing_id or ""), unit or "", int(score or 0),
         story_type or "other", story["title"], story["summary"], story.get("angle", ""),
         json.dumps(story["beats"], ensure_ascii=False),
         json.dumps(story["quotes"], ensure_ascii=False),
         story["emotion"], story["lesson"], ts))


def stories(status=None, limit=200):
    if status:
        rows = q("SELECT * FROM studio_stories WHERE status=? "
                 "ORDER BY score DESC, id DESC LIMIT ?", (status, limit))
    else:
        rows = q("SELECT * FROM studio_stories "
                 "ORDER BY score DESC, id DESC LIMIT ?", (limit,))
    for r in rows:
        r["beats"] = json.loads(r.get("beats") or "[]")
        r["quotes"] = json.loads(r.get("quotes") or "[]")
    return rows


def story(story_id):
    r = q1("SELECT * FROM studio_stories WHERE id=?", (int(story_id),))
    if r:
        r["beats"] = json.loads(r.get("beats") or "[]")
        r["quotes"] = json.loads(r.get("quotes") or "[]")
    return r


def set_story_status(story_id, status):
    return execute("UPDATE studio_stories SET status=? WHERE id=?",
                   (status, int(story_id)))


# ---------------- ideas ----------------

def add_idea(story_id, idea, ts):
    """Persist one idea card. v3: the signal columns are what make spec Section C
    checkable after the fact — an idea row remembers exactly what grounded it."""
    return execute(
        "INSERT INTO studio_ideas (story_id, hook_spoken, visual_title, visual_sub, "
        "angle, why_it_works, script, video_type, cta, audience, trigger_kind, "
        "signal_sid, signal_family, signal_source, signal_text, signal_url, "
        "signal_date, strength, nkey, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (int(story_id or 0), idea["hook_spoken"], idea["visual_title"],
         idea["visual_sub"], idea["angle"], idea.get("why_it_works", ""),
         json.dumps(idea["script"], ensure_ascii=False), idea["video_type"],
         idea["cta"], idea["audience"], idea["trigger"],
         idea.get("signal_sid", ""), idea.get("signal_family", ""),
         idea.get("signal_source", ""), idea.get("signal_text", ""),
         idea.get("signal_url", ""), idea.get("signal_date", ""),
         int(idea.get("strength") or 0), idea.get("nkey", ""), ts))


def ideas(status=None, limit=300):
    if status:
        rows = q("SELECT * FROM studio_ideas WHERE status=? ORDER BY id DESC LIMIT ?",
                 (status, limit))
    else:
        rows = q("SELECT * FROM studio_ideas ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["script"] = json.loads(r.get("script") or "[]")
    return rows


def ideas_for_story(story_id):
    rows = q("SELECT * FROM studio_ideas WHERE story_id=? ORDER BY id DESC",
             (int(story_id),))
    for r in rows:
        r["script"] = json.loads(r.get("script") or "[]")
    return rows


def set_idea_status(idea_id, status, views=None, perf_note=None):
    r = q1("SELECT id FROM studio_ideas WHERE id=?", (int(idea_id),))
    if not r:
        return 0
    n = execute("UPDATE studio_ideas SET status=? WHERE id=?", (status, int(idea_id)))
    if views is not None:
        execute("UPDATE studio_ideas SET views=? WHERE id=?", (int(views), int(idea_id)))
    if perf_note is not None:
        execute("UPDATE studio_ideas SET perf_note=? WHERE id=?",
                (str(perf_note)[:500], int(idea_id)))
    return n


# ---------------- v3 signals ----------------

def add_signal(sig, nkey="", ts=""):
    """Upsert a validated signal. Content-addressed by sid, so re-collecting the same
    fact refreshes it instead of flooding the feed with duplicates. Returns the sid."""
    existing = q1("SELECT sid, status FROM studio_signals WHERE sid=?", (sig["sid"],))
    if existing:
        execute("UPDATE studio_signals SET strength=?, as_of=COALESCE(NULLIF(?,''), as_of) "
                "WHERE sid=?", (int(sig.get("strength") or 50), sig.get("as_of", ""),
                                sig["sid"]))
        return sig["sid"]
    execute(
        "INSERT INTO studio_signals (sid, family, source, title, fact, detail, url, "
        "as_of, strength, ref, nkey, status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sig["sid"], sig["family"], sig["source"], sig.get("title", ""), sig["fact"],
         sig.get("detail", ""), sig.get("url", ""), sig.get("as_of", ""),
         int(sig.get("strength") or 50), sig.get("ref", ""), nkey,
         sig.get("status", "new"), ts))
    return sig["sid"]


def signals(status=None, family=None, limit=200):
    sql = "SELECT * FROM studio_signals"
    where, args = [], []
    if status:
        where.append("status=?")
        args.append(status)
    if family:
        where.append("family=?")
        args.append(family)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY strength DESC, as_of DESC, rowid DESC LIMIT ?"
    args.append(limit)
    return q(sql, tuple(args))


def signal(sid):
    return q1("SELECT * FROM studio_signals WHERE sid=?", (str(sid),))


def set_signal_status(sid, status):
    return execute("UPDATE studio_signals SET status=? WHERE sid=?", (status, str(sid)))


def signal_nkeys(limit=400):
    return [r["nkey"] for r in q(
        "SELECT nkey FROM studio_signals ORDER BY rowid DESC LIMIT ?", (limit,)) if r["nkey"]]


def prune_signals(keep=400):
    """Keep the feed from growing forever: drop the oldest UNUSED signals."""
    return execute(
        "DELETE FROM studio_signals WHERE status='new' AND sid NOT IN "
        "(SELECT sid FROM studio_signals ORDER BY rowid DESC LIMIT ?)", (keep,))


# ---------------- v3 daily plan ----------------

def set_plan(day, idea_ids, ts=""):
    execute("DELETE FROM studio_plan WHERE day=?", (str(day),))
    for i, iid in enumerate(idea_ids or []):
        execute("INSERT OR REPLACE INTO studio_plan (day, slot, idea_id, created_at) "
                "VALUES (?,?,?,?)", (str(day), i, int(iid), ts))
    return len(idea_ids or [])


def plan_for(day):
    rows = q("SELECT p.slot slot, i.* FROM studio_plan p JOIN studio_ideas i "
             "ON i.id = p.idea_id WHERE p.day=? ORDER BY p.slot", (str(day),))
    for r in rows:
        r["script"] = json.loads(r.get("script") or "[]")
    return rows


def recent_nkeys(days_back_rows=120):
    """Novelty history (spec H4): fingerprints of the ideas we recently generated."""
    return [r["nkey"] for r in q(
        "SELECT nkey FROM studio_ideas ORDER BY id DESC LIMIT ?", (days_back_rows,))
        if r["nkey"]]


# ---------------- learn-loop + deep-rescan ----------------

def learn_rows(limit=500):
    """Posted ideas + their story type — the input to studio.learn.stats()."""
    rows = q("SELECT i.status status, i.views views, i.trigger_kind trigger_kind, "
             "i.audience audience, i.video_type video_type, i.signal_family signal_family, "
             "s.story_type story_type FROM studio_ideas i "
             "LEFT JOIN studio_stories s ON s.id = i.story_id "
             "ORDER BY i.id DESC LIMIT ?", (limit,))
    return rows



def top_posted_archetypes(limit=3):
    """[(story_type, total_views), …] from POSTED ideas joined to their story, best
    first. Feeds the generator a hint of what already works for this account."""
    _ensure()
    return [(r["story_type"] or "other", int(r["v"] or 0)) for r in q(
        "SELECT s.story_type story_type, SUM(i.views) v "
        "FROM studio_ideas i JOIN studio_stories s ON s.id = i.story_id "
        "WHERE i.status = 'posted' AND i.views > 0 "
        "GROUP BY s.story_type ORDER BY v DESC LIMIT ?", (limit,))]


def reset_for_deep_scan():
    """Owner-triggered v2 re-mine: drop the weak legacy cards + the scan cursor so
    conversations get re-evaluated under the new positive lens — but KEEP posted/filmed
    ideas and their stories so the performance history (learn-loop) survives.
    Returns a dict of how many rows were cleared."""
    _ensure()
    keep_story_ids = {r["story_id"] for r in q(
        "SELECT DISTINCT story_id FROM studio_ideas WHERE status IN ('posted','filmed')")}
    del_ideas = execute(
        "DELETE FROM studio_ideas WHERE status IN ('new','shortlisted','rejected')")
    if keep_story_ids:
        placeholders = ",".join("?" for _ in keep_story_ids)
        del_stories = execute(
            "DELETE FROM studio_stories WHERE status IN ('new','hidden') "
            "AND id NOT IN (%s)" % placeholders, tuple(keep_story_ids))
        # only re-scan convos whose story we actually dropped
        execute("DELETE FROM studio_scanned WHERE convo_id NOT IN "
                "(SELECT convo_id FROM studio_stories)")
    else:
        del_stories = execute(
            "DELETE FROM studio_stories WHERE status IN ('new','hidden')")
        execute("DELETE FROM studio_scanned WHERE convo_id NOT IN "
                "(SELECT convo_id FROM studio_stories)")
    return {"ideas": del_ideas, "stories": del_stories,
            "kept_stories": len(keep_story_ids)}
