# -*- coding: utf-8 -*-
"""
wifi.db — wifi_* tables inside the SAME brain.db SQLite file. Reuses brain.db.connect for
the proven NO-WAL / journal_mode=DELETE / busy_timeout rules; no new database file is
created, and every call is wrapped in `with closing(connect())`.

THE LOCK LIVES HERE, IN SQL, NOT IN DISCIPLINE
----------------------------------------------
    CREATE UNIQUE INDEX idx_wifi_one_active ON wifi_subs(listing_id) WHERE status='active'

A partial unique index means the DATABASE ITSELF refuses a second active subscription for
one apartment. The friendly Arabic message in routes.py is only politeness; this index is
the guarantee. DO NOT REMOVE IT TO "SIMPLIFY". A renewal therefore has to close the old
row and open the new one inside ONE transaction (`renew()`), or the index fires on a
perfectly legitimate renewal.
"""

import datetime
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb
from . import engine

SCHEMA = """
CREATE TABLE IF NOT EXISTS wifi_units (
    listing_id     INTEGER PRIMARY KEY,   -- Hostaway listingMapId
    apartment_name TEXT,                  -- snapshot at write time
    billed_to      TEXT,                  -- 'ouja' | 'owner' | '' (unset)
    assignee       TEXT,                  -- employee name; seeded from the Employee Calendar
    notes          TEXT,
    updated_at     TEXT,
    updated_by     TEXT
);
CREATE TABLE IF NOT EXISTS wifi_subs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER NOT NULL,
    apartment_name  TEXT,
    provider        TEXT,                 -- 'stc' | 'mobily' | 'zain' | 'salam' | 'other'
    source_kind     TEXT,                 -- 'first_party' | 'vendor'
    source_name     TEXT,                 -- shop name when source_kind='vendor'
    label_days      INTEGER,              -- 30 | 60 | 90 — what the package SAYS
    amount_sar      REAL DEFAULT 0,
    tax_invoice     INTEGER DEFAULT 0,    -- 0 = no فاتورة ضريبية, 1 = yes
    purchase_date   TEXT,                 -- YYYY-MM-DD
    activation_date TEXT,                 -- YYYY-MM-DD; defaults to purchase_date
    stated_end      TEXT,                 -- real expiry from the telco app, if known
    real_end        TEXT,                 -- the day it actually died, once observed
    status          TEXT,                 -- 'active' | 'dead' | 'replaced' | 'cancelled'
    paid_by         TEXT,
    pay_method      TEXT,                 -- 'cash' | 'transfer' | 'float' | 'card'
    override_reason TEXT,                 -- REQUIRED when this row broke the lock
    override_by     TEXT,
    is_backfill     INTEGER DEFAULT 0,    -- 1 = typed from memory during the initial sweep
    created_by      TEXT,
    created_at      TEXT,
    updated_at      TEXT
);
CREATE TABLE IF NOT EXISTS wifi_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_id      INTEGER NOT NULL,
    kind        TEXT,          -- 'exact_expiry' | 'died' | 'days_left' | 'still_working'
    observed_on TEXT,          -- YYYY-MM-DD the observation was made
    days_left   INTEGER,       -- for kind='days_left'
    end_date    TEXT,          -- for kind='exact_expiry' / 'died'
    note        TEXT,
    actor       TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_wifi_subs_unit   ON wifi_subs(listing_id, status);
CREATE INDEX IF NOT EXISTS idx_wifi_subs_status ON wifi_subs(status);
CREATE INDEX IF NOT EXISTS idx_wifi_checks_sub  ON wifi_checks(sub_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wifi_one_active
    ON wifi_subs(listing_id) WHERE status = 'active';
"""

_inited = set()
_init_lock = threading.Lock()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:                # two threads racing the first init would
        if path in _inited:         # run SCHEMA concurrently
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
    """One connection, one commit. A renewal MUST close the old row and open the new one
    all-or-nothing — a per-statement commit could close the old subscription and then die
    before the new one exists, leaving a unit silently uncovered."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise


# ---------------- units ----------------

_UNIT_FIELDS = ("apartment_name", "billed_to", "assignee", "notes")


def units():
    return q("SELECT * FROM wifi_units ORDER BY apartment_name")


def unit(listing_id):
    return q1("SELECT * FROM wifi_units WHERE listing_id=?", (int(listing_id),))


def upsert_unit(listing_id, actor=None, **fields):
    """Create or patch one unit row. Only the keys actually passed are written, so
    saving an assignee never blanks the notes."""
    lid = int(listing_id)
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("INSERT OR IGNORE INTO wifi_units(listing_id, updated_at) VALUES(?,?)",
                   (lid, now_iso()))
        sets, args = [], []
        for k in _UNIT_FIELDS:
            if k in fields and fields[k] is not None:
                sets.append(k + "=?")
                args.append(fields[k])
        sets.append("updated_at=?")
        args.append(now_iso())
        sets.append("updated_by=?")
        args.append(actor or "")
        args.append(lid)
        cx.execute("UPDATE wifi_units SET " + ", ".join(sets) + " WHERE listing_id=?", args)
        cx.commit()
    return unit(lid)


# ---------------- subscriptions ----------------

_SUB_FIELDS = ("listing_id", "apartment_name", "provider", "source_kind", "source_name",
               "label_days", "amount_sar", "tax_invoice", "purchase_date", "activation_date",
               "stated_end", "real_end", "status", "paid_by", "pay_method",
               "override_reason", "override_by", "is_backfill", "created_by")


def _insert_sub(cx, data):
    row = {k: data.get(k) for k in _SUB_FIELDS}
    row["listing_id"] = int(row["listing_id"])
    row["status"] = row.get("status") or "active"
    row["is_backfill"] = 1 if row.get("is_backfill") else 0
    row["tax_invoice"] = 1 if row.get("tax_invoice") else 0
    ts = now_iso()
    cols = list(_SUB_FIELDS) + ["created_at", "updated_at"]
    vals = [row[k] for k in _SUB_FIELDS] + [ts, ts]
    cur = cx.execute("INSERT INTO wifi_subs(" + ",".join(cols) + ") VALUES(" +
                     ",".join(["?"] * len(cols)) + ")", vals)
    return cur.lastrowid


def create_sub(data):
    """Open a subscription. Raises sqlite3.IntegrityError if the unit already has an
    active one — that is the lock doing its job, and routes.py turns it into Arabic."""
    with transaction() as cx:
        return _insert_sub(cx, data)


def active_sub(listing_id):
    return q1("SELECT * FROM wifi_subs WHERE listing_id=? AND status='active'",
              (int(listing_id),))


def sub(sub_id):
    return q1("SELECT * FROM wifi_subs WHERE id=?", (int(sub_id),))


def subs_for(listing_id):
    return q("SELECT * FROM wifi_subs WHERE listing_id=? "
             "ORDER BY COALESCE(activation_date, purchase_date, created_at) DESC, id DESC",
             (int(listing_id),))


def active_subs():
    return q("SELECT * FROM wifi_subs WHERE status='active'")


def all_subs():
    return q("SELECT * FROM wifi_subs")


def renew(listing_id, data, closed_status="replaced", real_end=None):
    """Close the current active subscription and open the new one in ONE transaction.

    Returns (new_id, closed_id). Doing this in two separate writes would either trip the
    partial unique index (insert first) or leave the apartment with no subscription at all
    if the process died between them (close first).
    """
    lid = int(listing_id)
    with transaction() as cx:
        row = cx.execute("SELECT id FROM wifi_subs WHERE listing_id=? AND status='active'",
                         (lid,)).fetchone()
        closed_id = row["id"] if row else None
        if closed_id is not None:
            cx.execute("UPDATE wifi_subs SET status=?, real_end=COALESCE(?, real_end), "
                       "updated_at=? WHERE id=?",
                       (closed_status, real_end, now_iso(), closed_id))
        data = dict(data)
        data["listing_id"] = lid
        new_id = _insert_sub(cx, data)
    return new_id, closed_id


def close_sub(sub_id, status="dead", real_end=None):
    return execute("UPDATE wifi_subs SET status=?, real_end=COALESCE(?, real_end), "
                   "updated_at=? WHERE id=?",
                   (status, real_end, now_iso(), int(sub_id)))


def update_sub(sub_id, **fields):
    sets, args = [], []
    for k, v in fields.items():
        if k in _SUB_FIELDS:
            sets.append(k + "=?")
            args.append(v)
    if not sets:
        return None
    sets.append("updated_at=?")
    args.append(now_iso())
    args.append(int(sub_id))
    return execute("UPDATE wifi_subs SET " + ", ".join(sets) + " WHERE id=?", args)


# ---------------- observations ----------------

def add_check(sub_id, kind, observed_on=None, days_left=None, end_date=None,
              note=None, actor=None):
    return execute(
        "INSERT INTO wifi_checks(sub_id, kind, observed_on, days_left, end_date, note, "
        "actor, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (int(sub_id), kind, observed_on, days_left, end_date, note, actor or "", now_iso()))


def checks_for(sub_id):
    return q("SELECT * FROM wifi_checks WHERE sub_id=? ORDER BY observed_on, id",
             (int(sub_id),))


def learned_map():
    """{learning_key: learned_days} built from every REAL observation we hold.

    BACKFILL ROWS ARE EXCLUDED, always. Those dates were typed from memory during the
    initial sweep; letting a remembered guess train the model would poison the very
    number the model exists to make trustworthy.
    """
    subs = {s["id"]: s for s in all_subs() if not s.get("is_backfill")}
    if not subs:
        return {}
    buckets = {}
    marks = ",".join(["?"] * len(subs))
    rows = q("SELECT * FROM wifi_checks WHERE sub_id IN (" + marks + ")", tuple(subs.keys()))
    for c in rows:
        s = subs.get(c["sub_id"])
        n = engine.real_days(s, c)
        if n is None:
            continue
        buckets.setdefault(engine.learning_key(s), []).append(n)
    return {k: v for k, v in ((k, engine.learned_days(v)) for k, v in buckets.items())
            if v is not None}


def observations_for_key(key):
    """The raw durations behind one learning key — so the UI can show WHY we shortened
    a countdown instead of just asserting a smaller number."""
    out = []
    for s in all_subs():
        if s.get("is_backfill") or engine.learning_key(s) != key:
            continue
        for c in checks_for(s["id"]):
            n = engine.real_days(s, c)
            if n is not None:
                out.append(n)
    return sorted(out)


def listing_ids_with_subs():
    """[{listing_id, apartment_name}] for every unit that has EVER had a subscription.

    A row here that Hostaway no longer returns is not noise: money was spent on that
    apartment and somebody may still be paying for it. The unit list unions this in so a
    deactivated or renamed listing cannot make a live subscription disappear from view.
    """
    return q("SELECT listing_id, MAX(apartment_name) AS apartment_name FROM wifi_subs "
             "GROUP BY listing_id")


def counts():
    """Row counts — used by the tests that assert a write created exactly what it claims."""
    return {
        "units": (q1("SELECT COUNT(*) n FROM wifi_units") or {}).get("n", 0),
        "subs": (q1("SELECT COUNT(*) n FROM wifi_subs") or {}).get("n", 0),
        "active": (q1("SELECT COUNT(*) n FROM wifi_subs WHERE status='active'") or {}).get("n", 0),
        "checks": (q1("SELECT COUNT(*) n FROM wifi_checks") or {}).get("n", 0),
    }
