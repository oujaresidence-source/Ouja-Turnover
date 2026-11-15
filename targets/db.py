# -*- coding: utf-8 -*-
"""
targets.db — «الأهداف ودفتر العملاء» storage inside the SAME brain.db every other package uses.

Connection rules are brain.db's (no WAL, journal_mode=DELETE, one short connection per call
via `with closing(connect())`) — read brain/db.py before changing anything here.

RULES THE SCHEMA AND THIS FILE ENFORCE, SO CAREFUL CODE IS NOT THE ONLY GUARD
  1. A contact is logged by the system. `insert_contact` is the ONLY INSERT into tg_contacts
     and it is reachable only from book.log_contact, which stamps the server clock. There is
     no update of `at`, `employee` or `phone_key` anywhere.
  2. «لا تتصل» is permanent: there is no DELETE on tg_dnc.
  3. One booking belongs to one contact — tg_attr.res_id is the PRIMARY KEY.
  4. One approval per month — tg_approvals.month_key is the PRIMARY KEY, and nothing in this
     package writes to payroll or the ERP: an approval is a row here and nothing else.
Every table is prefixed `tg_`.
"""

import json
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS tg_settings (
    key     TEXT PRIMARY KEY,
    value   TEXT,
    set_by  TEXT,
    set_at  TEXT
);
CREATE TABLE IF NOT EXISTS tg_res (
    res_id       TEXT PRIMARY KEY,
    unit         TEXT NOT NULL,          -- Hostaway listing id as text, or 'n:<name>' (history only)
    listing_name TEXT,
    phone_key    TEXT,
    phone        TEXT,
    guest_name   TEXT,
    channel      TEXT,                   -- direct | airbnb | other
    status       TEXT,
    arrival      TEXT,
    departure    TEXT,
    created      TEXT,
    total        REAL,
    source       TEXT,                   -- seed | api
    updated_at   TEXT
);
CREATE INDEX IF NOT EXISTS tg_res_unit ON tg_res(unit, arrival);
CREATE INDEX IF NOT EXISTS tg_res_phone ON tg_res(phone_key);
CREATE TABLE IF NOT EXISTS tg_blocked (
    unit   TEXT NOT NULL,
    date   TEXT NOT NULL,
    source TEXT,
    PRIMARY KEY (unit, date)
);
CREATE TABLE IF NOT EXISTS tg_names (
    name       TEXT PRIMARY KEY,         -- normalised listing name from the seed file
    shown      TEXT,
    listing_id TEXT,
    status     TEXT,                     -- auto | manual | history | unmapped
    set_by     TEXT,
    set_at     TEXT
);
CREATE TABLE IF NOT EXISTS tg_targets (
    quarter     TEXT NOT NULL,           -- '2026-Q4'
    unit        TEXT NOT NULL,
    name        TEXT,
    employee    TEXT,                    -- frozen at approval: units move at quarter start only
    baseline    REAL,
    bronze      REAL,
    silver      REAL,
    gold        REAL,
    floor       REAL,
    ceiling     REAL,
    ceiling_suggested REAL,
    typical     REAL,
    basis       TEXT,
    status      TEXT,                    -- proposed | approved
    approved_by TEXT,
    approved_at TEXT,
    PRIMARY KEY (quarter, unit)
);
CREATE TABLE IF NOT EXISTS tg_contacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_key  TEXT NOT NULL,
    guest_name TEXT,
    employee   TEXT NOT NULL,
    at         TEXT NOT NULL,            -- server clock, never client supplied
    quarter    TEXT,
    unit       TEXT,
    night      TEXT,
    bucket     INTEGER,                  -- past stays at contact time: 1, 2, 3 (=3 or more)
    outcome    TEXT,
    outcome_at TEXT
);
CREATE INDEX IF NOT EXISTS tg_contacts_phone ON tg_contacts(phone_key, at);
CREATE INDEX IF NOT EXISTS tg_contacts_emp ON tg_contacts(employee, at);
CREATE TABLE IF NOT EXISTS tg_consent (
    phone_key TEXT PRIMARY KEY,
    source    TEXT,
    slug      TEXT,
    at        TEXT
);
CREATE TABLE IF NOT EXISTS tg_dnc (
    phone_key TEXT PRIMARY KEY,
    by        TEXT,
    at        TEXT
);
CREATE TABLE IF NOT EXISTS tg_attr (
    res_id     TEXT PRIMARY KEY,
    contact_id INTEGER NOT NULL,
    employee   TEXT,
    set_at     TEXT
);
CREATE TABLE IF NOT EXISTS tg_results (
    month_key   TEXT PRIMARY KEY,
    payload     TEXT,
    computed_at TEXT
);
CREATE TABLE IF NOT EXISTS tg_approvals (
    month_key  TEXT PRIMARY KEY,
    by         TEXT,
    at         TEXT,
    total_paid REAL,
    payload    TEXT
);
CREATE TABLE IF NOT EXISTS tg_links (
    user_id  TEXT PRIMARY KEY,
    employee TEXT,
    set_by   TEXT,
    set_at   TEXT
);
CREATE TABLE IF NOT EXISTS tg_rescue (
    month_key TEXT NOT NULL,
    day       INTEGER NOT NULL,
    payload   TEXT,
    at        TEXT,
    PRIMARY KEY (month_key, day)
);
CREATE TABLE IF NOT EXISTS tg_log (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     TEXT,
    kind   TEXT,
    by     TEXT,
    detail TEXT
);
"""

_inited = set()
_init_lock = threading.Lock()
_version = {"n": 0}          # bumped on every write: the in-memory guest cache keys on it


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
    bump()


def bump():
    _version["n"] += 1


def version():
    return (_bdb.db_path(), _version["n"])


# ------------------------------------------------------------------ thin sql helpers

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
    """Returns (lastrowid, rowcount)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
    bump()
    return cur.lastrowid, cur.rowcount


@contextmanager
def transaction():
    _ensure()
    with closing(_bdb.connect()) as cx:
        try:
            yield cx
            cx.commit()
        except Exception:
            cx.rollback()
            raise
    bump()


# ------------------------------------------------------------------ settings / log

def setting(key, default=""):
    r = q1("SELECT value FROM tg_settings WHERE key=?", (key,))
    return default if r is None or r["value"] is None else r["value"]


def set_setting(key, value, by="", at=""):
    execute("INSERT INTO tg_settings(key,value,set_by,set_at) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, set_by=excluded.set_by, "
            "set_at=excluded.set_at", (key, value, by or "", at or ""))


def log(kind, at, by="", detail=None):
    execute("INSERT INTO tg_log(at,kind,by,detail) VALUES(?,?,?,?)",
            (at, kind, by or "", json.dumps(detail or {}, ensure_ascii=False)))


# ------------------------------------------------------------------ reservations

RES_COLS = ("res_id", "unit", "listing_name", "phone_key", "phone", "guest_name", "channel",
            "status", "arrival", "departure", "created", "total", "source", "updated_at")


def upsert_res(rows):
    """rows: dicts with RES_COLS. An API row replaces a seed row of the same reservation."""
    if not rows:
        return 0
    sql = ("INSERT INTO tg_res(%s) VALUES(%s) ON CONFLICT(res_id) DO UPDATE SET %s"
           % (",".join(RES_COLS), ",".join("?" * len(RES_COLS)),
              ",".join("%s=excluded.%s" % (c, c) for c in RES_COLS[1:])))
    with transaction() as cx:
        cx.executemany(sql, [tuple(r.get(c) for c in RES_COLS) for r in rows])
    return len(rows)


def all_res():
    return q("SELECT * FROM tg_res")


def res_for_unit(unit):
    return q("SELECT * FROM tg_res WHERE unit=?", (unit,))


def res_by_ids(ids):
    ids = [str(i) for i in ids]
    if not ids:
        return []
    out = []
    for i in range(0, len(ids), 400):
        part = ids[i:i + 400]
        out.extend(q("SELECT * FROM tg_res WHERE res_id IN (%s)" % ",".join("?" * len(part)), part))
    return out


def res_count():
    return (q1("SELECT COUNT(*) AS n FROM tg_res") or {}).get("n", 0)


def remap_unit(listing_name_norm_rows, unit):
    """Move history rows (by their stored listing_name list) onto another unit key."""
    with transaction() as cx:
        for nm in listing_name_norm_rows:
            cx.execute("UPDATE tg_res SET unit=? WHERE listing_name=?", (unit, nm))


# ------------------------------------------------------------------ blocked nights

def set_blocked(unit, dates, source, clear_from=None, clear_to=None):
    """Replace this source's blocked nights for the unit inside [clear_from, clear_to)."""
    with transaction() as cx:
        if clear_from and clear_to:
            cx.execute("DELETE FROM tg_blocked WHERE unit=? AND source=? AND date>=? AND date<?",
                       (unit, source, clear_from, clear_to))
        cx.executemany("INSERT OR IGNORE INTO tg_blocked(unit,date,source) VALUES(?,?,?)",
                       [(unit, d, source) for d in dates])


def add_blocked(pairs, source):
    with transaction() as cx:
        cx.executemany("INSERT OR IGNORE INTO tg_blocked(unit,date,source) VALUES(?,?,?)",
                       [(u, d, source) for u, d in pairs])


def blocked_dates(unit, start_iso, end_iso):
    return {r["date"] for r in q("SELECT date FROM tg_blocked WHERE unit=? AND date>=? AND date<?",
                                 (unit, start_iso, end_iso))}


def all_blocked():
    out = {}
    for r in q("SELECT unit, date FROM tg_blocked"):
        out.setdefault(r["unit"], set()).add(r["date"])
    return out


# ------------------------------------------------------------------ listing-name map

def names():
    return q("SELECT * FROM tg_names ORDER BY shown")


def name_row(name):
    return q1("SELECT * FROM tg_names WHERE name=?", (name,))


def set_name(name, shown, listing_id, status, by="", at=""):
    execute("INSERT INTO tg_names(name,shown,listing_id,status,set_by,set_at) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET shown=excluded.shown, listing_id=excluded.listing_id, "
            "status=excluded.status, set_by=excluded.set_by, set_at=excluded.set_at",
            (name, shown, listing_id, status, by or "", at or ""))


# ------------------------------------------------------------------ targets

def targets(quarter):
    return q("SELECT * FROM tg_targets WHERE quarter=? ORDER BY employee, name", (quarter,))


def target(quarter, unit):
    return q1("SELECT * FROM tg_targets WHERE quarter=? AND unit=?", (quarter, unit))


def save_proposals(quarter, rows):
    """Proposals never overwrite an approved row."""
    with transaction() as cx:
        for r in rows:
            ex = cx.execute("SELECT status FROM tg_targets WHERE quarter=? AND unit=?",
                            (quarter, r["unit"])).fetchone()
            if ex and ex["status"] == "approved":
                continue
            cx.execute(
                "INSERT INTO tg_targets(quarter,unit,name,employee,baseline,bronze,silver,gold,"
                "floor,ceiling,ceiling_suggested,typical,basis,status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'proposed') "
                "ON CONFLICT(quarter,unit) DO UPDATE SET name=excluded.name, "
                "employee=excluded.employee, baseline=excluded.baseline, bronze=excluded.bronze, "
                "silver=excluded.silver, gold=excluded.gold, floor=excluded.floor, "
                "ceiling_suggested=excluded.ceiling_suggested, typical=excluded.typical, "
                "basis=excluded.basis",
                (quarter, r["unit"], r.get("name"), r.get("employee"), r.get("baseline"),
                 r.get("bronze"), r.get("silver"), r.get("gold"), r.get("floor"),
                 r.get("ceiling"), r.get("ceiling_suggested"), r.get("typical"), r.get("basis")))


def edit_target(quarter, unit, floor, ceiling):
    """Owner edits the price bounds of a row that is still a proposal."""
    _, n = execute("UPDATE tg_targets SET floor=?, ceiling=? WHERE quarter=? AND unit=? "
                   "AND status='proposed'", (floor, ceiling, quarter, unit))
    return n


def approve_targets(quarter, by, at):
    _, n = execute("UPDATE tg_targets SET status='approved', approved_by=?, approved_at=? "
                   "WHERE quarter=? AND status='proposed'", (by or "", at, quarter))
    return n


# ------------------------------------------------------------------ contacts (system-logged)

def insert_contact(phone_key, guest_name, employee, at, quarter, unit, night, bucket,
                   cooldown_since):
    """THE only insert into tg_contacts. Refuses (returns None) when this guest already has a
    contact at or after `cooldown_since` — checked inside the same transaction as the insert,
    so two colleagues pressing at once cannot both win."""
    with transaction() as cx:
        ex = cx.execute("SELECT id FROM tg_contacts WHERE phone_key=? AND at>=? LIMIT 1",
                        (phone_key, cooldown_since)).fetchone()
        if ex:
            return None
        cur = cx.execute(
            "INSERT INTO tg_contacts(phone_key,guest_name,employee,at,quarter,unit,night,bucket) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (phone_key, guest_name, employee, at, quarter, unit, night, bucket))
        return cur.lastrowid


def contacts(employee=None, since=None, until=None):
    sql, args = "SELECT * FROM tg_contacts WHERE 1=1", []
    if employee is not None:
        sql += " AND employee=?"
        args.append(employee)
    if since:
        sql += " AND at>=?"
        args.append(since)
    if until:
        sql += " AND at<?"
        args.append(until)
    return q(sql + " ORDER BY at, id", args)


def contact(contact_id):
    return q1("SELECT * FROM tg_contacts WHERE id=?", (contact_id,))


def last_contacts():
    """{phone_key: latest contact iso}."""
    return {r["phone_key"]: r["m"] for r in
            q("SELECT phone_key, MAX(at) AS m FROM tg_contacts GROUP BY phone_key")}


def set_outcome(contact_id, employee, outcome, at):
    """Only the employee who logged the contact may record how it went."""
    _, n = execute("UPDATE tg_contacts SET outcome=?, outcome_at=? WHERE id=? AND employee=?",
                   (outcome, at, contact_id, employee))
    return n


# ------------------------------------------------------------------ consent / do-not-contact

def add_consent(phone_key, source, slug, at):
    execute("INSERT OR IGNORE INTO tg_consent(phone_key,source,slug,at) VALUES(?,?,?,?)",
            (phone_key, source, slug or "", at))


def consents():
    return {r["phone_key"] for r in q("SELECT phone_key FROM tg_consent")}


def add_dnc(phone_key, by, at):
    execute("INSERT OR IGNORE INTO tg_dnc(phone_key,by,at) VALUES(?,?,?)", (phone_key, by or "", at))


def dnc():
    return {r["phone_key"] for r in q("SELECT phone_key FROM tg_dnc")}


# ------------------------------------------------------------------ attribution

def replace_attr(pairs, at):
    """pairs: [(res_id, contact_id, employee)] — recomputed whole every run (first logger wins
    is a property of the rule, so a recompute can never move a booking to a later colleague)."""
    with transaction() as cx:
        cx.execute("DELETE FROM tg_attr")
        cx.executemany("INSERT INTO tg_attr(res_id,contact_id,employee,set_at) VALUES(?,?,?,?)",
                       [(str(r), c, e, at) for r, c, e in pairs])


def attrs():
    return q("SELECT * FROM tg_attr")


# ------------------------------------------------------------------ month results / approvals

def save_result(month_key, payload, at):
    execute("INSERT INTO tg_results(month_key,payload,computed_at) VALUES(?,?,?) "
            "ON CONFLICT(month_key) DO UPDATE SET payload=excluded.payload, "
            "computed_at=excluded.computed_at",
            (month_key, json.dumps(payload, ensure_ascii=False), at))


def result(month_key):
    r = q1("SELECT * FROM tg_results WHERE month_key=?", (month_key,))
    if not r:
        return None
    try:
        return json.loads(r["payload"])
    except Exception:
        return None


def approval(month_key):
    return q1("SELECT month_key, by, at, total_paid FROM tg_approvals WHERE month_key=?",
              (month_key,))


def approve_month(month_key, by, at, total_paid, payload):
    """Records the row and nothing else. Returns False when the month was already approved."""
    with transaction() as cx:
        if cx.execute("SELECT 1 FROM tg_approvals WHERE month_key=?", (month_key,)).fetchone():
            return False
        cx.execute("INSERT INTO tg_approvals(month_key,by,at,total_paid,payload) VALUES(?,?,?,?,?)",
                   (month_key, by or "", at, total_paid, json.dumps(payload, ensure_ascii=False)))
    return True


# ------------------------------------------------------------------ user -> employee links

def links():
    return {r["user_id"]: r["employee"] for r in q("SELECT user_id, employee FROM tg_links")}


def link(user_id):
    r = q1("SELECT employee FROM tg_links WHERE user_id=?", (str(user_id or ""),))
    return (r or {}).get("employee") or ""


def set_link(user_id, employee, by, at):
    if employee:
        execute("INSERT INTO tg_links(user_id,employee,set_by,set_at) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET employee=excluded.employee, "
                "set_by=excluded.set_by, set_at=excluded.set_at",
                (str(user_id), employee, by or "", at))
    else:
        execute("DELETE FROM tg_links WHERE user_id=?", (str(user_id),))


# ------------------------------------------------------------------ rescue snapshots

def save_rescue(month_key, day, payload, at):
    execute("INSERT OR IGNORE INTO tg_rescue(month_key,day,payload,at) VALUES(?,?,?,?)",
            (month_key, int(day), json.dumps(payload, ensure_ascii=False), at))


def rescues(month_key):
    out = []
    for r in q("SELECT * FROM tg_rescue WHERE month_key=? ORDER BY day", (month_key,)):
        try:
            out.append({"day": r["day"], "at": r["at"], "units": json.loads(r["payload"])})
        except Exception:
            continue
    return out
