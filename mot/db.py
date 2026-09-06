# -*- coding: utf-8 -*-
"""
mot.db — mot_* tables inside the existing brain.db (via brain.db.connect, like wifi/db.py).

THE LOCK LIVES HERE: `idx_mot_one_open` is a partial unique index — the database itself
refuses a second OPEN round for one apartment. Two inspectors on one unit is how
contradictory evidence gets created. The Arabic message in routes.py is politeness.

A CLOSED round is immutable: `set_result` refuses to touch a round with closed_at set.
A correction is a new round. History is the product.
"""
import datetime
import secrets
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS mot_inspection (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id         INTEGER NOT NULL,
    apartment_name     TEXT,
    catalogue_version  TEXT NOT NULL,
    has_pool           INTEGER NOT NULL,
    pool_source        TEXT,
    denominator        INTEGER NOT NULL,
    opened_at          TEXT NOT NULL,
    opened_by          TEXT,
    inspector          TEXT,
    closed_at          TEXT,
    compliance_pct     REAL,
    inspected_pct      REAL,
    recheck_due        TEXT,
    quote_id           TEXT,
    note               TEXT,
    fanout             TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mot_one_open
    ON mot_inspection(listing_id) WHERE closed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_mot_insp_listing ON mot_inspection(listing_id, id);

CREATE TABLE IF NOT EXISTS mot_result (
    inspection_id  INTEGER NOT NULL,
    comp_key       TEXT NOT NULL,
    state          TEXT NOT NULL,
    qty            INTEGER,
    billed_to      TEXT,
    source         TEXT,
    note           TEXT,
    updated_at     TEXT,
    updated_by     TEXT,
    PRIMARY KEY (inspection_id, comp_key)
);
CREATE TABLE IF NOT EXISTS mot_photo (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id  INTEGER NOT NULL,
    comp_key       TEXT,
    url            TEXT NOT NULL,
    added_at       TEXT,
    added_by       TEXT
);
CREATE INDEX IF NOT EXISTS idx_mot_photo_insp ON mot_photo(inspection_id, comp_key);
CREATE TABLE IF NOT EXISTS mot_price (
    comp_key   TEXT PRIMARY KEY,
    price_sar  REAL NOT NULL DEFAULT 0,
    set_by     TEXT,
    set_at     TEXT
);
CREATE TABLE IF NOT EXISTS mot_token (
    token          TEXT PRIMARY KEY,
    inspection_id  INTEGER NOT NULL,
    created_at     TEXT,
    created_by     TEXT,
    expires_at     TEXT
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


@contextmanager
def transaction():
    """One connection, one commit. Closing a round writes scores + quote id + fan-out record
    all-or-nothing."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise


class RoundClosed(Exception):
    """Raised on any write into a closed round. A correction opens a new round."""


class RoundAlreadyOpen(Exception):
    """Raised when the partial unique index refuses a second open round."""


# ---------------- rounds ----------------

def open_round(listing_id, apartment_name, catalogue_version, has_pool, pool_source,
               denominator, by="", inspector=""):
    import sqlite3
    try:
        return execute(
            """INSERT INTO mot_inspection(listing_id, apartment_name, catalogue_version, has_pool,
                   pool_source, denominator, opened_at, opened_by, inspector)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (int(listing_id), apartment_name, catalogue_version, 1 if has_pool else 0,
             pool_source, int(denominator), now_iso(), by, inspector or by))
    except sqlite3.IntegrityError as e:
        if "idx_mot_one_open" in str(e) or "UNIQUE" in str(e).upper():
            raise RoundAlreadyOpen(listing_id)
        raise


def round_(rid):
    try:
        return q1("SELECT * FROM mot_inspection WHERE id=?", (int(rid),))
    except (TypeError, ValueError):
        return None


def open_round_for(listing_id):
    return q1("SELECT * FROM mot_inspection WHERE listing_id=? AND closed_at IS NULL",
              (int(listing_id),))


def rounds_for(listing_id):
    return q("SELECT * FROM mot_inspection WHERE listing_id=? ORDER BY id DESC", (int(listing_id),))


def latest_closed_by_listing():
    """{listing_id: latest CLOSED, non-abandoned round} — one query for the portfolio."""
    rows = q("""SELECT i.* FROM mot_inspection i
                JOIN (SELECT listing_id, MAX(id) AS mid FROM mot_inspection
                      WHERE closed_at IS NOT NULL AND COALESCE(note,'') <> 'abandoned'
                      GROUP BY listing_id) m ON m.mid = i.id""")
    return {r["listing_id"]: r for r in rows}


def open_by_listing():
    return {r["listing_id"]: r for r in q("SELECT * FROM mot_inspection WHERE closed_at IS NULL")}


def results(rid):
    return {r["comp_key"]: r for r in q("SELECT * FROM mot_result WHERE inspection_id=?", (int(rid),))}


def results_many(rids):
    out = {}
    rids = [int(r) for r in rids]
    if not rids:
        return out
    marks = ",".join("?" * len(rids))
    for r in q("SELECT * FROM mot_result WHERE inspection_id IN (%s)" % marks, rids):
        out.setdefault(r["inspection_id"], {})[r["comp_key"]] = r
    return out


def set_result(rid, comp_key, state, qty=None, billed_to=None, source="inspector",
               note=None, by=""):
    rnd = round_(rid)
    if not rnd:
        raise KeyError(rid)
    if rnd.get("closed_at"):
        raise RoundClosed(rid)
    cur = q1("SELECT * FROM mot_result WHERE inspection_id=? AND comp_key=?", (int(rid), comp_key))
    qty = int(qty) if qty not in (None, "") else (cur or {}).get("qty")   # NULL = use the default
    qty = qty if (qty or 0) > 0 else None
    billed = billed_to if billed_to in ("ouja", "owner") else ((cur or {}).get("billed_to") or "")
    note = note if note is not None else (cur or {}).get("note") or ""
    execute("""INSERT INTO mot_result(inspection_id, comp_key, state, qty, billed_to, source, note,
                   updated_at, updated_by) VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(inspection_id, comp_key) DO UPDATE SET
                   state=excluded.state, qty=excluded.qty, billed_to=excluded.billed_to,
                   source=excluded.source, note=excluded.note,
                   updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
            (int(rid), comp_key, state, qty, billed, source, note, now_iso(), by))
    return q1("SELECT * FROM mot_result WHERE inspection_id=? AND comp_key=?", (int(rid), comp_key))


def close_round(rid, compliance_pct, inspected_pct, recheck_due, quote_id, fanout_json,
                note=None, by=""):
    with transaction() as cx:
        r = cx.execute("SELECT closed_at FROM mot_inspection WHERE id=?", (int(rid),)).fetchone()
        if not r:
            raise KeyError(rid)
        if r["closed_at"]:
            raise RoundClosed(rid)
        cx.execute("""UPDATE mot_inspection SET closed_at=?, compliance_pct=?, inspected_pct=?,
                          recheck_due=?, quote_id=?, fanout=?, note=COALESCE(?, note),
                          inspector=COALESCE(NULLIF(inspector,''), ?)
                      WHERE id=?""",
                   (now_iso(), compliance_pct, inspected_pct, recheck_due, quote_id, fanout_json,
                    note, by, int(rid)))
    return round_(rid)


def abandon_round(rid, by=""):
    with transaction() as cx:
        r = cx.execute("SELECT closed_at FROM mot_inspection WHERE id=?", (int(rid),)).fetchone()
        if not r:
            raise KeyError(rid)
        if r["closed_at"]:
            raise RoundClosed(rid)
        cx.execute("UPDATE mot_inspection SET closed_at=?, note='abandoned', opened_by=opened_by WHERE id=?",
                   (now_iso(), int(rid)))
    return round_(rid)


def set_recheck(rid, due):
    execute("UPDATE mot_inspection SET recheck_due=? WHERE id=?", (due, int(rid)))


# ---------------- photos ----------------

def add_photo(rid, comp_key, url, by=""):
    rnd = round_(rid)
    if not rnd:
        raise KeyError(rid)
    if rnd.get("closed_at"):
        raise RoundClosed(rid)
    return execute("INSERT INTO mot_photo(inspection_id, comp_key, url, added_at, added_by) VALUES(?,?,?,?,?)",
                   (int(rid), comp_key, url, now_iso(), by))


def photos(rid):
    return q("SELECT * FROM mot_photo WHERE inspection_id=? ORDER BY id", (int(rid),))


def photo_count(rid, comp_key):
    r = q1("SELECT COUNT(*) AS n FROM mot_photo WHERE inspection_id=? AND comp_key=?", (int(rid), comp_key))
    return int((r or {}).get("n") or 0)


# ---------------- prices ----------------

def prices():
    return {r["comp_key"]: r for r in q("SELECT * FROM mot_price")}


def set_price(comp_key, price_sar, by=""):
    execute("""INSERT INTO mot_price(comp_key, price_sar, set_by, set_at) VALUES(?,?,?,?)
               ON CONFLICT(comp_key) DO UPDATE SET price_sar=excluded.price_sar,
                   set_by=excluded.set_by, set_at=excluded.set_at""",
            (comp_key, float(price_sar), by, now_iso()))
    return q1("SELECT * FROM mot_price WHERE comp_key=?", (comp_key,))


# ---------------- inspector tokens ----------------

def mint_token(rid, by="", days=7):
    tok = secrets.token_urlsafe(18)
    exp = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat(timespec="seconds")
    execute("INSERT INTO mot_token(token, inspection_id, created_at, created_by, expires_at) VALUES(?,?,?,?,?)",
            (tok, int(rid), now_iso(), by, exp))
    return tok


def round_by_token(token):
    """The OPEN round behind a live token, or None. Expired, unknown, and closed all read None."""
    if not token:
        return None
    t = q1("SELECT * FROM mot_token WHERE token=?", (str(token),))
    if not t or (t.get("expires_at") and t["expires_at"] < now_iso()):
        return None
    rnd = round_(t["inspection_id"])
    if not rnd or rnd.get("closed_at"):
        return None
    return rnd


def counts():
    return {
        "rounds": q1("SELECT COUNT(*) AS n FROM mot_inspection")["n"],
        "open": q1("SELECT COUNT(*) AS n FROM mot_inspection WHERE closed_at IS NULL")["n"],
        "results": q1("SELECT COUNT(*) AS n FROM mot_result")["n"],
        "photos": q1("SELECT COUNT(*) AS n FROM mot_photo")["n"],
        "prices": q1("SELECT COUNT(*) AS n FROM mot_price")["n"],
    }
