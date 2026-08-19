# -*- coding: utf-8 -*-
"""
monthly.db — monthly_* tables inside the SAME brain.db file, reusing
brain.db.connect for the proven NO-WAL / journal_mode=DELETE / short-lived
connection rules (see brain/db.py: WAL's -shm file is unsupported on the Railway
volume, and EXCLUSIVE locking produced "database is locked").

A NEW table needs no migration entry: SCHEMA runs on every _ensure and
CREATE TABLE IF NOT EXISTS adds it to an already-existing brain.db. _migrate is
only for columns added to a table that already exists.

TWO STORAGE DECISIONS WORTH DEFENDING

1. `value` in monthly_unit_attrs is nullable and a NULL means UNANSWERED. It is
   never coerced to a middle score on the way in or the way out. attrs.to_score
   is the only thing that turns a value into a number, and it returns None for
   None.

2. `payload_json` in monthly_quotes is FROZEN at issue time. When an owner asks
   in November why we quoted 11,800 in August, he is shown August's reasoning —
   not a recomputation against November's betas. A quote is a thing we said, and
   what we said does not change.

monthly_outcomes is wired now although it stays empty for months. Retrofitting
it later means losing the first season of evidence, which is the only thing that
can ever turn the betas from a guess into a measurement.
"""

import datetime
import json
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS monthly_unit_attrs (
    unit_id     INTEGER NOT NULL,
    attr_key    TEXT    NOT NULL,
    value       TEXT,                    -- NULL = unanswered. Never coerce to 5.
    scored_by   TEXT,
    scored_at   TEXT,
    PRIMARY KEY (unit_id, attr_key)
);
CREATE TABLE IF NOT EXISTS monthly_ejar_refs (
    district    TEXT NOT NULL,
    bedrooms    INTEGER NOT NULL,
    annual_rent REAL NOT NULL,
    txn_count   INTEGER,
    source      TEXT,                    -- 'sakani' | 'rega' | 'manual'
    obs_type    TEXT NOT NULL,           -- 'transacted' | 'asking'
    as_of       TEXT NOT NULL,
    entered_by  TEXT,
    PRIMARY KEY (district, bedrooms, as_of)
);
CREATE TABLE IF NOT EXISTS monthly_source_calib (
    source      TEXT NOT NULL,
    district    TEXT NOT NULL,
    bedrooms    INTEGER NOT NULL,
    mape        REAL,
    bias_factor REAL DEFAULT 1.0,
    n_obs       INTEGER,
    trust_tier  TEXT,                    -- 'allowed' | 'corrected' | 'blocked'
    updated_at  TEXT,
    PRIMARY KEY (source, district, bedrooms)
);
CREATE TABLE IF NOT EXISTS monthly_quotes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id       INTEGER NOT NULL,
    month         TEXT NOT NULL,          -- 'YYYY-MM'
    price         REAL NOT NULL,          -- FINAL, before override
    override_pct  REAL DEFAULT 0,
    final_price   REAL NOT NULL,          -- price x (1 + override_pct)
    bound_by      TEXT,
    confidence    TEXT,
    beta_version  INTEGER,
    payload_json  TEXT NOT NULL,          -- the full explainability object, frozen
    created_by    TEXT,
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_monthly_quotes_unit ON monthly_quotes(unit_id, month);
CREATE TABLE IF NOT EXISTS monthly_overrides (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id    INTEGER NOT NULL,
    from_pct    REAL,
    to_pct      REAL,
    reason      TEXT,                     -- REQUIRED. The write is refused without it.
    actor       TEXT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS monthly_outcomes (
    quote_id      INTEGER PRIMARY KEY,
    booked        INTEGER,                -- 0/1
    booked_price  REAL,
    booked_at     TEXT
);
"""

_init_lock = threading.Lock()
_inited = set()


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


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def reset_for_tests():
    _inited.clear()


# ───────────────────────────── unit attributes ─────────────────────────────

def unit_attrs(unit_id):
    """{attr_key: value} for one unit. Keys absent from the dict are unanswered,
    and so are keys stored with a NULL value — both mean the same thing and both
    must reach attrs.to_score as None."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT attr_key, value FROM monthly_unit_attrs WHERE unit_id=?",
            (int(unit_id),)).fetchall()
    return {r[0]: r[1] for r in rows if r[1] is not None}


def unit_attrs_detailed(unit_id):
    """As unit_attrs, but with who scored it and when — the provenance the
    attribute editor shows so a number always has a name attached."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT attr_key, value, scored_by, scored_at FROM monthly_unit_attrs "
            "WHERE unit_id=?", (int(unit_id),)).fetchall()
    return {r[0]: {"value": r[1], "scored_by": r[2], "scored_at": r[3]} for r in rows}


def set_attr(unit_id, attr_key, value, actor=None):
    """Store one attribute. value=None CLEARS it back to unanswered — un-knowing
    something has to be as possible as knowing it, or a mistyped score is
    permanent."""
    _ensure()
    v = None if value is None else str(value)
    with closing(_bdb.connect()) as cx:
        cx.execute(
            "INSERT INTO monthly_unit_attrs (unit_id, attr_key, value, scored_by, scored_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(unit_id, attr_key) DO UPDATE SET "
            "value=excluded.value, scored_by=excluded.scored_by, scored_at=excluded.scored_at",
            (int(unit_id), str(attr_key), v, actor, _now()))
        cx.commit()
    return True


def units_with_attrs():
    """Every unit_id that has at least one answered attribute."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT DISTINCT unit_id FROM monthly_unit_attrs WHERE value IS NOT NULL").fetchall()
    return [r[0] for r in rows]


# ─────────────────────────── ejar reference table ───────────────────────────

def ejar_latest(district, bedrooms):
    """The most recent reference row for this cell, or None. as_of is part of the
    key on purpose: history is kept, so a stale row can be SEEN to be stale
    rather than silently overwritten."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute(
            "SELECT district, bedrooms, annual_rent, txn_count, source, obs_type, "
            "as_of, entered_by FROM monthly_ejar_refs WHERE district=? AND bedrooms=? "
            "ORDER BY as_of DESC LIMIT 1", (str(district), int(bedrooms))).fetchone()
    if not r:
        return None
    return {"district": r[0], "bedrooms": r[1], "annual_rent": r[2], "txn_count": r[3],
            "source": r[4], "obs_type": r[5], "as_of": r[6], "entered_by": r[7]}


def ejar_all():
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT district, bedrooms, annual_rent, txn_count, source, obs_type, "
            "as_of, entered_by FROM monthly_ejar_refs ORDER BY district, bedrooms, as_of DESC"
        ).fetchall()
    return [{"district": r[0], "bedrooms": r[1], "annual_rent": r[2], "txn_count": r[3],
             "source": r[4], "obs_type": r[5], "as_of": r[6], "entered_by": r[7]} for r in rows]


def ejar_upsert(district, bedrooms, annual_rent, as_of, txn_count=None,
                source="manual", obs_type="transacted", entered_by=None):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute(
            "INSERT INTO monthly_ejar_refs (district, bedrooms, annual_rent, txn_count, "
            "source, obs_type, as_of, entered_by) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(district, bedrooms, as_of) DO UPDATE SET "
            "annual_rent=excluded.annual_rent, txn_count=excluded.txn_count, "
            "source=excluded.source, obs_type=excluded.obs_type, entered_by=excluded.entered_by",
            (str(district), int(bedrooms), float(annual_rent),
             None if txn_count is None else int(txn_count),
             str(source), str(obs_type), str(as_of)[:10], entered_by))
        cx.commit()
    return True


# ───────────────────────── source calibration table ─────────────────────────

def calib_get(source, district, bedrooms):
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute(
            "SELECT mape, bias_factor, n_obs, trust_tier, updated_at FROM monthly_source_calib "
            "WHERE source=? AND district=? AND bedrooms=?",
            (str(source), str(district), int(bedrooms))).fetchone()
    if not r:
        return None
    return {"mape": r[0], "bias_factor": r[1], "n_obs": r[2],
            "trust_tier": r[3], "updated_at": r[4]}


def calib_set(source, district, bedrooms, mape, bias_factor, n_obs, trust_tier):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute(
            "INSERT INTO monthly_source_calib (source, district, bedrooms, mape, bias_factor, "
            "n_obs, trust_tier, updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source, district, bedrooms) DO UPDATE SET "
            "mape=excluded.mape, bias_factor=excluded.bias_factor, n_obs=excluded.n_obs, "
            "trust_tier=excluded.trust_tier, updated_at=excluded.updated_at",
            (str(source), str(district), int(bedrooms), mape, bias_factor,
             n_obs, trust_tier, _now()))
        cx.commit()
    return True


# ──────────────────────────── quotes & overrides ────────────────────────────

def save_quote(unit_id, month, price, final_price, bound_by, confidence,
               beta_version, payload, override_pct=0.0, created_by=None):
    """Freeze one quote. payload is serialised HERE and never rewritten."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT INTO monthly_quotes (unit_id, month, price, override_pct, final_price, "
            "bound_by, confidence, beta_version, payload_json, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (int(unit_id), str(month), float(price), float(override_pct or 0.0),
             float(final_price), bound_by, confidence, int(beta_version),
             json.dumps(payload, ensure_ascii=False), created_by, _now()))
        cx.commit()
        return cur.lastrowid


def get_quote(quote_id):
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute(
            "SELECT id, unit_id, month, price, override_pct, final_price, bound_by, "
            "confidence, beta_version, payload_json, created_by, created_at "
            "FROM monthly_quotes WHERE id=?", (int(quote_id),)).fetchone()
    if not r:
        return None
    return {"id": r[0], "unit_id": r[1], "month": r[2], "price": r[3],
            "override_pct": r[4], "final_price": r[5], "bound_by": r[6],
            "confidence": r[7], "beta_version": r[8],
            "payload": json.loads(r[9]), "created_by": r[10], "created_at": r[11]}


def latest_quote(unit_id, month=None):
    _ensure()
    sql = ("SELECT id FROM monthly_quotes WHERE unit_id=?"
           + (" AND month=?" if month else "")
           + " ORDER BY id DESC LIMIT 1")
    args = (int(unit_id), month) if month else (int(unit_id),)
    with closing(_bdb.connect()) as cx:
        r = cx.execute(sql, args).fetchone()
    return get_quote(r[0]) if r else None


class ReasonRequired(ValueError):
    """Raised when an override is attempted with no reason. The refusal is the
    feature: a price moved by a human with no recorded why is a price nobody can
    defend to an owner six weeks later."""


def log_override(quote_id, from_pct, to_pct, reason, actor=None):
    if not (reason or "").strip():
        raise ReasonRequired("اكتب سبب التعديل — ما ينحفظ تعديل بدون سبب")
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute(
            "INSERT INTO monthly_overrides (quote_id, from_pct, to_pct, reason, actor, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (int(quote_id), float(from_pct or 0.0), float(to_pct or 0.0),
             reason.strip(), actor, _now()))
        cx.execute("UPDATE monthly_quotes SET override_pct=?, final_price=price*(1+?) WHERE id=?",
                   (float(to_pct or 0.0), float(to_pct or 0.0), int(quote_id)))
        cx.commit()
    return True


def overrides_for(quote_id):
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT from_pct, to_pct, reason, actor, created_at FROM monthly_overrides "
            "WHERE quote_id=? ORDER BY id", (int(quote_id),)).fetchall()
    return [{"from_pct": r[0], "to_pct": r[1], "reason": r[2],
             "actor": r[3], "created_at": r[4]} for r in rows]


# ──────────────────────────────── outcomes ────────────────────────────────

def record_outcome(quote_id, booked, booked_price=None, booked_at=None):
    """The evidence that eventually refits the betas. Empty for months; wired now
    because the first season cannot be recovered later."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute(
            "INSERT INTO monthly_outcomes (quote_id, booked, booked_price, booked_at) "
            "VALUES (?,?,?,?) ON CONFLICT(quote_id) DO UPDATE SET "
            "booked=excluded.booked, booked_price=excluded.booked_price, "
            "booked_at=excluded.booked_at",
            (int(quote_id), 1 if booked else 0, booked_price, booked_at or _now()))
        cx.commit()
    return True


def paired_obs_count():
    """How many (predicted, actual) pairs exist. Drives the «تقدير» vs «سعر»
    wording — see attrs.CALIBRATED_AT."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute("SELECT COUNT(*) FROM monthly_outcomes WHERE booked=1 "
                       "AND booked_price IS NOT NULL").fetchone()
    return int(r[0]) if r else 0
