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
    district      TEXT NOT NULL,
    bedrooms      INTEGER,               -- NULL = not broken out by bedrooms (filter الكل,
                                         -- and every non-apartment type: the index has no
                                         -- bedroom tabs for استديو/دوبلاكس/فله/دور)
    unit_type     TEXT NOT NULL DEFAULT 'شقة',   -- شقة | استديو | دوبلاكس | فله | دور
    annual_rent   REAL NOT NULL,
    txn_count     INTEGER,
    range_low_sar REAL,                  -- «النطاق السعري» — NOT captured yet, see note
    range_high_sar REAL,
    source        TEXT,                  -- 'sakani_rei' | 'rega' | 'manual'
    obs_type      TEXT NOT NULL,         -- 'transacted' | 'asking'
    period        TEXT,                  -- the range selected in the tool, e.g. '2026-01/2026-08'
    as_of         TEXT NOT NULL,
    note          TEXT,                  -- recorded uncertainties, kept rather than resolved
    entered_by    TEXT
);
-- Uniqueness CANNOT live in a PRIMARY KEY here: bedrooms is legitimately NULL for
-- filter الكل and for every non-apartment type, and SQLite treats NULLs in a PK as
-- DISTINCT — so the upsert would never fire and re-running the seed would duplicate
-- every one of those rows. IFNULL(bedrooms,-1) makes "not broken out" a real value
-- for the index while the column keeps saying NULL, which is the truth.
CREATE UNIQUE INDEX IF NOT EXISTS idx_monthly_ejar_cell
    ON monthly_ejar_refs(district, unit_type, IFNULL(bedrooms, -1), as_of);
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
            _migrate_pre(cx)
            cx.executescript(SCHEMA)
            cx.commit()
        _inited.add(path)


def _migrate_pre(cx):
    """Runs BEFORE the schema script, for tables that already exist in a live
    brain.db. CREATE TABLE IF NOT EXISTS cannot reshape an existing table, so the
    S3 shape of monthly_ejar_refs — bedrooms NOT NULL, no unit_type, a PRIMARY KEY
    that silently duplicates NULL rows — has to be rebuilt in place.

    Rebuild rather than ALTER because the PRIMARY KEY itself is the defect, and
    SQLite cannot drop one. Existing rows are carried over; the table is empty in
    practice (this ships before any row was entered), but a migration that
    discards data it did not check for is how data gets lost.
    """
    try:
        cols = [r[1] for r in cx.execute("PRAGMA table_info(monthly_ejar_refs)").fetchall()]
    except Exception:
        return
    if not cols or "unit_type" in cols:
        return                                  # absent (fresh) or already migrated
    cx.execute("ALTER TABLE monthly_ejar_refs RENAME TO monthly_ejar_refs_s3")
    cx.executescript(SCHEMA)
    cx.execute(
        "INSERT INTO monthly_ejar_refs (district, bedrooms, unit_type, annual_rent, "
        "txn_count, source, obs_type, as_of, entered_by) "
        "SELECT district, bedrooms, 'شقة', annual_rent, txn_count, source, obs_type, "
        "as_of, entered_by FROM monthly_ejar_refs_s3")
    cx.execute("DROP TABLE monthly_ejar_refs_s3")


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

def _ejar_row(r):
    return {"district": r[0], "bedrooms": r[1], "unit_type": r[2], "annual_rent": r[3],
            "txn_count": r[4], "range_low_sar": r[5], "range_high_sar": r[6],
            "source": r[7], "obs_type": r[8], "period": r[9], "as_of": r[10],
            "note": r[11], "entered_by": r[12]}


_EJAR_COLS = ("district, bedrooms, unit_type, annual_rent, txn_count, range_low_sar, "
              "range_high_sar, source, obs_type, period, as_of, note, entered_by")


def ejar_latest(district, bedrooms=None, unit_type="شقة"):
    """The most recent row for this cell, or None.

    bedrooms=None means "the row that is not broken out by bedrooms" — the الكل
    filter — and is matched as a real value, not as "any bedroom count". Asking
    for 3BR must not silently answer with the all-bedrooms average; they are
    different numbers about different things.
    """
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute(
            "SELECT " + _EJAR_COLS + " FROM monthly_ejar_refs WHERE district=? "
            "AND unit_type=? AND IFNULL(bedrooms,-1)=? ORDER BY as_of DESC LIMIT 1",
            (str(district), str(unit_type),
             -1 if bedrooms is None else int(bedrooms))).fetchone()
    return _ejar_row(r) if r else None


def ejar_all():
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT " + _EJAR_COLS + " FROM monthly_ejar_refs "
            "ORDER BY district, unit_type, IFNULL(bedrooms,-1), as_of DESC").fetchall()
    return [_ejar_row(r) for r in rows]


def ejar_upsert(district, annual_rent, as_of, bedrooms=None, unit_type="شقة",
                txn_count=None, source="manual", obs_type="transacted",
                period=None, note=None, entered_by=None,
                range_low_sar=None, range_high_sar=None):
    """One reference cell. Keyed on (district, unit_type, bedrooms, as_of) via the
    expression index, so re-running a seed updates rather than duplicates."""
    _ensure()
    bk = -1 if bedrooms is None else int(bedrooms)
    with closing(_bdb.connect()) as cx:
        cx.execute(
            "DELETE FROM monthly_ejar_refs WHERE district=? AND unit_type=? "
            "AND IFNULL(bedrooms,-1)=? AND as_of=?",
            (str(district), str(unit_type), bk, str(as_of)[:10]))
        cx.execute(
            "INSERT INTO monthly_ejar_refs (" + _EJAR_COLS + ") "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(district), None if bedrooms is None else int(bedrooms), str(unit_type),
             float(annual_rent), None if txn_count is None else int(txn_count),
             range_low_sar, range_high_sar, str(source), str(obs_type),
             period, str(as_of)[:10], note, entered_by))
        cx.commit()
    return True


def ejar_missing_ranges():
    """Cells whose «النطاق السعري» was never captured — the follow-up worklist.
    A point figure with no range around it cannot say how tight the market is."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT district, unit_type, bedrooms, as_of FROM monthly_ejar_refs "
            "WHERE range_low_sar IS NULL OR range_high_sar IS NULL "
            "ORDER BY district, unit_type").fetchall()
    return [{"district": r[0], "unit_type": r[1], "bedrooms": r[2], "as_of": r[3]}
            for r in rows]


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

# The only constraints a price may be bound by. 'owner_gate' was retired on
# 2026-08-19 when the owner-versus-annual-lease comparison left the pricing path;
# the math survives in ejar.owner_annual_net for acquisition material. Validating
# here is the structural half of that decision — a rule nothing enforces is a
# rule that comes back.
BOUND_BY_VALUES = ("floor", "model", "ceiling")


class RetiredBoundBy(ValueError):
    """A quote claiming to be bound by a constraint the engine cannot produce."""


def save_quote(unit_id, month, price, final_price, bound_by, confidence,
               beta_version, payload, override_pct=0.0, created_by=None):
    """Freeze one quote. payload is serialised HERE and never rewritten."""
    if bound_by not in BOUND_BY_VALUES:
        raise RetiredBoundBy(
            "bound_by must be one of %s — got %r" % (BOUND_BY_VALUES, bound_by))
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


def ejar_load_seed(path=None):
    """Load monthly/ejar_seed.json into monthly_ejar_refs. Idempotent — the
    expression index keys each cell, so re-running updates rather than
    duplicates. Every row carries its source, period, capture date and the
    recorded uncertainty; a figure that forgets where it came from cannot be
    re-checked when an owner queries it eight months later."""
    import os
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "ejar_seed.json")
    with open(path, encoding="utf-8") as fh:
        blob = json.load(fh)
    note = blob.get("_note") or ""
    n = 0
    for r in blob.get("rows") or []:
        ejar_upsert(
            district=r["district"], annual_rent=r["annual_rent"],
            as_of=blob["_as_of"], bedrooms=r.get("bedrooms"),
            unit_type=r.get("unit_type") or "شقة", txn_count=r.get("txn_count"),
            source=blob["_source_key"], obs_type=blob["_obs_type"],
            period=blob["_period"], entered_by=blob["_entered_by"],
            note=(note + " | filter: " + str(r.get("filter") or "")).strip())
        n += 1
    return n
