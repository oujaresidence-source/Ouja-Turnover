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
    status       TEXT NOT NULL DEFAULT 'new',
    views        INTEGER NOT NULL DEFAULT 0,
    perf_note    TEXT NOT NULL DEFAULT '',
    created_at   TEXT
);
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
        "(convo_id, listing_id, unit, score, story_type, title, summary, beats, "
        " quotes, emotion, lesson, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (str(convo_id), str(listing_id or ""), unit or "", int(score or 0),
         story_type or "other", story["title"], story["summary"],
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
    return execute(
        "INSERT INTO studio_ideas (story_id, hook_spoken, visual_title, visual_sub, "
        "angle, script, video_type, cta, audience, trigger_kind, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (int(story_id or 0), idea["hook_spoken"], idea["visual_title"],
         idea["visual_sub"], idea["angle"],
         json.dumps(idea["script"], ensure_ascii=False), idea["video_type"],
         idea["cta"], idea["audience"], idea["trigger"], ts))


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
