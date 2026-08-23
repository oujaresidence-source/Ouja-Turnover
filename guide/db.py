# -*- coding: utf-8 -*-
"""guide_units + guide_entries inside brain.db (NO WAL / journal DELETE /
busy_timeout — the proven rules; schedule/db.py patterns)."""

import datetime
import json
import sqlite3
import threading
import time
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS guide_units (
    slug            TEXT PRIMARY KEY,       -- the public id, e.g. '6b-htn'
    listing_id      INTEGER,                -- Hostaway match (nullable)
    listing_name    TEXT,
    map_link        TEXT,
    complex_pic     TEXT, complex_caption  TEXT,
    building_pic    TEXT, building_caption TEXT,
    elevator_pic    TEXT, elevator_caption TEXT,
    door_pic        TEXT, door_caption     TEXT,
    wifi_name       TEXT, wifi_pass        TEXT,
    notes           TEXT,
    media_local     TEXT,                   -- JSON {field: local filename} for mirrored pics
    active          INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT, updated_by TEXT
);
CREATE TABLE IF NOT EXISTS guide_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT,                       -- unit slug; '' / NULL = every active unit
    section     TEXT NOT NULL DEFAULT 'faq',
    title_ar    TEXT, title_en TEXT,
    body_ar     TEXT, body_en  TEXT,
    image_paths TEXT,                       -- JSON list
    sort        INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'published',
    source      TEXT,                       -- gap | admin
    created_at  TEXT, updated_at TEXT, updated_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_guide_entries_slug ON guide_entries(slug, status);
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
    return datetime.datetime.now().isoformat(timespec="seconds")


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
        _bump_public_version()          # any guide write invalidates data.json
        return cur.lastrowid


UNIT_FIELDS = ("listing_id", "listing_name", "map_link",
               "complex_pic", "complex_caption", "building_pic", "building_caption",
               "elevator_pic", "elevator_caption", "door_pic", "door_caption",
               "wifi_name", "wifi_pass", "notes", "media_local", "active",
               "updated_at", "updated_by")


def upsert_unit(slug, **fields):
    slug = (slug or "").strip().lower()
    if not slug:
        raise ValueError("slug required")
    fields.setdefault("updated_at", now_iso())
    cur = q1("SELECT slug FROM guide_units WHERE slug=?", (slug,))
    cols = [k for k in UNIT_FIELDS if k in fields]
    if cur is None:
        execute("INSERT INTO guide_units(slug," + ",".join(cols) + ") VALUES(?" +
                ",?" * len(cols) + ")", tuple([slug] + [fields[k] for k in cols]))
    elif cols:
        execute("UPDATE guide_units SET " + ",".join(k + "=?" for k in cols) +
                " WHERE slug=?", tuple([fields[k] for k in cols] + [slug]))
    return slug


def get_unit(slug):
    return q1("SELECT * FROM guide_units WHERE slug=?", ((slug or "").strip().lower(),))


def unit_by_listing(listing_id):
    try:
        return q1("SELECT * FROM guide_units WHERE listing_id=?", (int(listing_id),))
    except (TypeError, ValueError):
        return None


def units(active_only=True):
    if active_only:
        return q("SELECT * FROM guide_units WHERE active=1 ORDER BY slug")
    return q("SELECT * FROM guide_units ORDER BY slug")


def entries_for(slug, status="published"):
    """Entries for one unit: its own rows + the for-every-unit rows ('' slug)."""
    return q("SELECT * FROM guide_entries WHERE status=? AND (slug=? OR slug='' OR slug IS NULL) "
             "ORDER BY sort, id", (status, (slug or "").strip().lower()))


def all_entries(status=None):
    if status:
        return q("SELECT * FROM guide_entries WHERE status=? ORDER BY id DESC", (status,))
    return q("SELECT * FROM guide_entries ORDER BY id DESC")


def add_entry(slug, section, title_ar="", title_en="", body_ar="", body_en="",
              image_paths=None, sort=0, status="published", source="admin", by=""):
    return execute(
        "INSERT INTO guide_entries(slug,section,title_ar,title_en,body_ar,body_en,"
        "image_paths,sort,status,source,created_at,updated_at,updated_by) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ((slug or "").strip().lower(), section or "faq", title_ar, title_en, body_ar, body_en,
         json.dumps(image_paths or [], ensure_ascii=False), int(sort or 0),
         status, source, now_iso(), now_iso(), by))


def del_entry(eid):
    execute("DELETE FROM guide_entries WHERE id=?", (int(eid),))


def media_map(unit):
    try:
        return json.loads(unit.get("media_local") or "{}") or {}
    except (TypeError, ValueError):
        return {}


# ---- data.json cache --------------------------------------------------------
# The guest guide page fetches /guide/data.json on EVERY open, and building it
# used to cost 1 + N database connections (one per unit, ~68 of them) on the
# shared thread pool. On 2026-08-23 that pool jammed and the page hung on
# «جارٍ التحميل» for hours. These records change only when the owner edits the
# guide, so we keep the last build in memory: a bump on every write and a TTL
# floor, and the page is served from RAM without touching the DB at all.
PUBLIC_TTL = 120.0                      # seconds before a quiet rebuild
_pub_cache = {"recs": None, "ts": 0.0, "ver": -1}
_pub_lock = threading.Lock()
_pub_version = 0


def _bump_public_version():
    global _pub_version
    with _pub_lock:
        _pub_version += 1


def public_version():
    with _pub_lock:
        return _pub_version


def _faq_rows(status="published"):
    """Every published entry ONCE, in the same (sort, id) order the per-unit
    query returned — filtering this list per unit yields an identical result."""
    return q("SELECT slug, section, title_ar, title_en, body_ar, body_en "
             "FROM guide_entries WHERE status=? ORDER BY sort, id", (status,))


def public_records(media_url_base="/guide/media"):
    """The data.json shape the live site renders — one flat record per active
    unit, pics swapped to our mirrored copy when we have one, plus faq[]."""
    rows = [e for e in _faq_rows() if e.get("section") == "faq"]
    out = []
    for u in units(active_only=True):
        mm = media_map(u)
        rec = {"id": u["slug"], "listing_name": u.get("listing_name") or "",
               "map_link": u.get("map_link") or ""}
        for f in ("complex", "building", "elevator", "door"):
            local = mm.get(f + "_pic")
            rec[f + "_pic"] = ("%s/%s/%s" % (media_url_base, u["slug"], local)
                               if local else (u.get(f + "_pic") or ""))
            rec[f + "_caption"] = u.get(f + "_caption") or ""
        rec["wifi_name"] = u.get("wifi_name") or ""
        rec["wifi_pass"] = u.get("wifi_pass") or ""
        rec["notes"] = u.get("notes") or ""
        slug = u["slug"]
        rec["faq"] = [{"title_ar": e.get("title_ar") or "", "title_en": e.get("title_en") or "",
                       "body_ar": e.get("body_ar") or "", "body_en": e.get("body_en") or ""}
                      for e in rows
                      if e.get("slug") == slug or not (e.get("slug") or "").strip()]
        out.append(rec)
    return out


def public_records_fresh(media_url_base="/guide/media"):
    """Rebuild from the DB, fill the cache, return the records. BLOCKING —
    call it off the event loop."""
    ver = public_version()
    recs = public_records(media_url_base)
    if media_url_base == "/guide/media":            # only the served shape is cached
        with _pub_lock:
            _pub_cache["recs"], _pub_cache["ts"], _pub_cache["ver"] = recs, time.time(), ver
    return recs


def public_records_cached():
    """(records_or_None, stale) — a pure memory read. NEVER touches the DB, so
    it cannot block, cannot queue, and cannot be starved by anything."""
    with _pub_lock:
        recs, ts, ver, cur = (_pub_cache["recs"], _pub_cache["ts"],
                              _pub_cache["ver"], _pub_version)
    if recs is None:
        return None, True
    return recs, (ver != cur or (time.time() - ts) > PUBLIC_TTL)


def reset_public_cache():
    """Tests (and the importer) start from a clean slate."""
    with _pub_lock:
        _pub_cache["recs"], _pub_cache["ts"], _pub_cache["ver"] = None, 0.0, -1
