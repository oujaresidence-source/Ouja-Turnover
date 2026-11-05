# -*- coding: utf-8 -*-
"""
stayhub.* tables inside the SAME brain.db (journal DELETE, one short connection per call via
closing(connect()) — the proven rules, see CLAUDE.md and directpay/db.py).

    stayhub_properties  the StayHub catalog Ouja is authorised on (from /sync)
    stayhub_days        per-day cache: rooms + rate per (property, rate plan, date) — what the
                        sync probe reports back to StayHub
    stayhub_map         Hostaway listing ⇄ StayHub property + rate plan (set by an admin)
    stayhub_bookings    one row per Hostaway reservation pushed (or refused) — UNIQUE on the
                        Hostaway id, so a reservation can never be pushed twice
    stayhub_events      append-only audit trail (no guest names, no phone numbers)
    stayhub_settings    the /sync cursor, last-run latches

PRIVACY: guest name / phone / email are NEVER stored here. They are read fresh from Hostaway
at push time and sent to StayHub only.
"""
import datetime
import json
import threading
from contextlib import closing

from brain import db as _bdb

BOOKING_COLS = [
    ("ha_reservation_id", "TEXT PRIMARY KEY"),      # Hostaway reservation id — the anti-duplicate key
    ("external_id", "TEXT"),                        # Airbnb confirmation code (HM…) → externalReservationId
    ("listing_id", "INTEGER"),
    ("property_id", "TEXT"),
    ("rate_plan_id", "TEXT"),
    ("sh_reservation_id", "TEXT"),                  # StayHub reservationId, after confirm
    ("revision", "INTEGER DEFAULT 0"),              # last externalRevision StayHub accepted
    ("status", "TEXT"),                             # see engine.STATUSES
    ("check_in", "TEXT"),                           # what Hostaway says now
    ("check_out", "TEXT"),
    ("adults", "INTEGER"),
    ("total", "REAL"),
    ("currency", "TEXT"),
    ("pushed_check_in", "TEXT"),                    # what StayHub holds
    ("pushed_check_out", "TEXT"),
    ("pushed_total", "REAL"),
    ("hold_id", "TEXT"),
    ("hold_expires", "TEXT"),
    ("attempts", "INTEGER DEFAULT 0"),
    ("last_code", "TEXT"),
    ("last_error", "TEXT"),
    ("last_trace", "TEXT"),
    ("next_try_at", "TEXT"),
    ("notified", "INTEGER DEFAULT 0"),
    ("dryrun", "INTEGER DEFAULT 0"),
    ("created_at", "TEXT"),
    ("updated_at", "TEXT"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS stayhub_properties (
    property_id    TEXT PRIMARY KEY,
    title          TEXT,
    version        INTEGER,
    rate_plans     TEXT,
    status         TEXT DEFAULT 'active',
    updated_at     TEXT
);
CREATE TABLE IF NOT EXISTS stayhub_days (
    property_id    TEXT NOT NULL,
    rate_plan_id   TEXT NOT NULL DEFAULT '',
    date           TEXT NOT NULL,
    rooms          INTEGER,
    rate           REAL,
    restrictions   TEXT,
    updated_at     TEXT,
    PRIMARY KEY (property_id, rate_plan_id, date)
);
CREATE TABLE IF NOT EXISTS stayhub_map (
    listing_id     INTEGER PRIMARY KEY,
    property_id    TEXT NOT NULL UNIQUE,
    rate_plan_id   TEXT,
    mapped_by      TEXT,
    mapped_at      TEXT
);
CREATE TABLE IF NOT EXISTS stayhub_bookings (
    %s
);
CREATE INDEX IF NOT EXISTS idx_shb_status   ON stayhub_bookings(status, next_try_at);
CREATE INDEX IF NOT EXISTS idx_shb_property ON stayhub_bookings(property_id, check_in);
CREATE INDEX IF NOT EXISTS idx_shb_external ON stayhub_bookings(external_id);
CREATE TABLE IF NOT EXISTS stayhub_events (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    at                 TEXT,
    ha_reservation_id  TEXT,
    kind               TEXT,
    detail             TEXT,
    trace_id           TEXT
);
CREATE INDEX IF NOT EXISTS idx_she_res ON stayhub_events(ha_reservation_id, at);
CREATE TABLE IF NOT EXISTS stayhub_settings (k TEXT PRIMARY KEY, v TEXT);
""" % ", ".join("%s %s" % (n, t) for n, t in BOOKING_COLS)

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
            _migrate(cx)
            cx.commit()
        _inited.add(path)


def _migrate(cx):
    have = {r["name"] for r in cx.execute("PRAGMA table_info(stayhub_bookings)").fetchall()}
    for name, typ in BOOKING_COLS:
        if name in have or "PRIMARY KEY" in typ or "UNIQUE" in typ or "NOT NULL" in typ:
            continue
        cx.execute("ALTER TABLE stayhub_bookings ADD COLUMN %s %s" % (name, typ))


def reset_init_cache():
    _inited.clear()


def now_iso():
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


def q(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        return [dict(r) for r in cx.execute(sql, args).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def x(sql, args=()):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.rowcount


def xmany(sql, rows):
    _ensure()
    rows = list(rows)
    if not rows:
        return 0
    with closing(_bdb.connect()) as cx:
        cx.executemany(sql, rows)
        cx.commit()
        return len(rows)


# ---------------- settings ----------------

def setting_get(k, default=None):
    r = q1("SELECT v FROM stayhub_settings WHERE k=?", (k,))
    return r["v"] if r else default


def setting_set(k, v):
    x("INSERT INTO stayhub_settings(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
      (k, None if v is None else str(v)))


# ---------------- catalog ----------------

def upsert_property(property_id, title=None, version=None, rate_plans=None, status=None, at=None):
    pid = str(property_id or "").strip()
    if not pid:
        return
    cur = property_row(pid) or {}
    plans = rate_plans if rate_plans is not None else json.loads(cur.get("rate_plans") or "[]")
    x("""INSERT INTO stayhub_properties(property_id, title, version, rate_plans, status, updated_at)
         VALUES(?,?,?,?,?,?)
         ON CONFLICT(property_id) DO UPDATE SET title=excluded.title, version=excluded.version,
           rate_plans=excluded.rate_plans, status=excluded.status, updated_at=excluded.updated_at""",
      (pid,
       title if title is not None else cur.get("title"),
       version if version is not None else cur.get("version"),
       json.dumps(list(plans or []), ensure_ascii=False),
       status or cur.get("status") or "active",
       at or now_iso()))


def set_property_status(property_id, status, at=None):
    x("UPDATE stayhub_properties SET status=?, updated_at=? WHERE property_id=?",
      (status, at or now_iso(), str(property_id)))


def property_row(property_id):
    return q1("SELECT * FROM stayhub_properties WHERE property_id=?", (str(property_id),))


def properties():
    return q("SELECT * FROM stayhub_properties ORDER BY title, property_id")


def clear_catalog():
    """CURSOR_EXPIRED ⇒ the guide says discard the cache and bootstrap fresh. The unit map and
    the bookings ledger are OURS and are never discarded."""
    x("DELETE FROM stayhub_days")
    x("DELETE FROM stayhub_properties")


def put_days(property_id, rate_plan_id, days, at=None):
    """days: [{date, rooms?, rate?, restrictions?}] — a None field keeps the cached value."""
    pid, rp, at = str(property_id), str(rate_plan_id or ""), at or now_iso()
    rows = []
    for d in days or []:
        date = str(d.get("date") or "")[:10]
        if len(date) != 10:
            continue
        rows.append((pid, rp, date, d.get("rooms"), d.get("rate"),
                     json.dumps(d["restrictions"], ensure_ascii=False) if d.get("restrictions") is not None else None,
                     at))
    return xmany("""INSERT INTO stayhub_days(property_id, rate_plan_id, date, rooms, rate, restrictions, updated_at)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(property_id, rate_plan_id, date) DO UPDATE SET
                      rooms=COALESCE(excluded.rooms, stayhub_days.rooms),
                      rate=COALESCE(excluded.rate, stayhub_days.rate),
                      restrictions=COALESCE(excluded.restrictions, stayhub_days.restrictions),
                      updated_at=excluded.updated_at""", rows)


def days(property_id, date_from, date_to):
    return q("""SELECT * FROM stayhub_days WHERE property_id=? AND date>=? AND date<=?
                ORDER BY date, rate_plan_id""", (str(property_id), date_from, date_to))


# ---------------- unit map ----------------

def set_map(listing_id, property_id, rate_plan_id, by="", at=None):
    lid = int(listing_id)
    pid = str(property_id).strip()
    x("DELETE FROM stayhub_map WHERE property_id=? AND listing_id<>?", (pid, lid))
    x("""INSERT INTO stayhub_map(listing_id, property_id, rate_plan_id, mapped_by, mapped_at)
         VALUES(?,?,?,?,?)
         ON CONFLICT(listing_id) DO UPDATE SET property_id=excluded.property_id,
           rate_plan_id=excluded.rate_plan_id, mapped_by=excluded.mapped_by, mapped_at=excluded.mapped_at""",
      (lid, pid, str(rate_plan_id or "").strip() or None, by, at or now_iso()))


def unmap(listing_id):
    return x("DELETE FROM stayhub_map WHERE listing_id=?", (int(listing_id),))


def map_for_listing(listing_id):
    try:
        return q1("SELECT * FROM stayhub_map WHERE listing_id=?", (int(listing_id),))
    except (TypeError, ValueError):
        return None


def map_for_property(property_id):
    return q1("SELECT * FROM stayhub_map WHERE property_id=?", (str(property_id),))


def maps():
    return q("SELECT * FROM stayhub_map ORDER BY listing_id")


# ---------------- bookings ----------------

_BOOKING_NAMES = {n for n, _ in BOOKING_COLS}


def booking(ha_reservation_id):
    return q1("SELECT * FROM stayhub_bookings WHERE ha_reservation_id=?", (str(ha_reservation_id),))


def booking_by_sh(sh_reservation_id):
    return q1("SELECT * FROM stayhub_bookings WHERE sh_reservation_id=?", (str(sh_reservation_id),))


def insert_booking(**f):
    """INSERT OR IGNORE — returns the row when it was created, None when it already existed."""
    f = {k: v for k, v in f.items() if k in _BOOKING_NAMES}
    f.setdefault("created_at", now_iso())
    f.setdefault("updated_at", f["created_at"])
    cols = list(f)
    n = x("INSERT OR IGNORE INTO stayhub_bookings(%s) VALUES(%s)" % (",".join(cols), ",".join("?" * len(cols))),
          tuple(f[c] for c in cols))
    return booking(f["ha_reservation_id"]) if n else None


def update_booking(ha_reservation_id, **patch):
    patch = {k: v for k, v in patch.items() if k in _BOOKING_NAMES and k != "ha_reservation_id"}
    if not patch:
        return booking(ha_reservation_id)
    patch.setdefault("updated_at", now_iso())
    x("UPDATE stayhub_bookings SET %s WHERE ha_reservation_id=?" % ",".join("%s=?" % k for k in patch),
      tuple(patch.values()) + (str(ha_reservation_id),))
    return booking(ha_reservation_id)


def bookings(status=None, limit=500):
    if status:
        return q("SELECT * FROM stayhub_bookings WHERE status=? ORDER BY check_in LIMIT ?", (status, int(limit)))
    return q("SELECT * FROM stayhub_bookings ORDER BY updated_at DESC LIMIT ?", (int(limit),))


def bookings_for_property(property_id, date_from=None, date_to=None, statuses=None):
    sql, args = "SELECT * FROM stayhub_bookings WHERE property_id=?", [str(property_id)]
    if date_from:
        sql += " AND check_out>?"
        args.append(date_from)
    if date_to:
        sql += " AND check_in<=?"
        args.append(date_to)
    if statuses:
        sql += " AND status IN (%s)" % ",".join("?" * len(statuses))
        args.extend(statuses)
    return q(sql + " ORDER BY check_in", tuple(args))


def due_retries(now_iso_str, limit=20):
    return q("""SELECT * FROM stayhub_bookings
                WHERE status IN ('pending','retry','rejected') AND (next_try_at IS NULL OR next_try_at<=?)
                ORDER BY check_in LIMIT ?""", (now_iso_str, int(limit)))


def counts():
    return {r["status"]: r["n"] for r in q("SELECT status, COUNT(*) n FROM stayhub_bookings GROUP BY status")}


def active_holds(property_id, now_iso_str):
    return q("""SELECT * FROM stayhub_bookings WHERE property_id=? AND hold_id IS NOT NULL
                AND status='held' AND hold_expires>?""", (str(property_id), now_iso_str))


# ---------------- audit ----------------

def add_event(ha_reservation_id, kind, detail="", trace_id=None, at=None):
    x("INSERT INTO stayhub_events(at, ha_reservation_id, kind, detail, trace_id) VALUES(?,?,?,?,?)",
      (at or now_iso(), str(ha_reservation_id or ""), kind, (detail or "")[:1000], trace_id))


def events(ha_reservation_id=None, limit=100):
    if ha_reservation_id:
        return q("SELECT * FROM stayhub_events WHERE ha_reservation_id=? ORDER BY id DESC LIMIT ?",
                 (str(ha_reservation_id), int(limit)))
    return q("SELECT * FROM stayhub_events ORDER BY id DESC LIMIT ?", (int(limit),))
