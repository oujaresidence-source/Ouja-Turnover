# -*- coding: utf-8 -*-
"""
decor.* tables inside the SAME brain.db (NO WAL, journal DELETE, busy_timeout, one short
connection per call via `closing(connect())` — the proven rules, see CLAUDE.md).

THE STRUCTURAL GUARANTEE
    `decor_leads` and `decor_orders` are separate tables ON PURPOSE. A lead is what a guest
    tapping «أنا مهتم» produces, and the lead table has no assignee column, no deadline
    column, no thread column and no cake link — so a guest's tap cannot create work even if
    some future code forgets to check a status. `open_order()` below is the ONLY function
    that inserts into decor_orders, and it is unreachable from the public endpoint.
"""

import datetime
import json
import sqlite3   # noqa: F401  (brain.db factory returns sqlite3.Row)
import threading
import uuid
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS decor_leads (
    id              TEXT PRIMARY KEY,
    slug            TEXT NOT NULL,
    pack_id         TEXT NOT NULL,
    lang            TEXT,
    source          TEXT NOT NULL DEFAULT 'guide',   -- guide | assistant
    status          TEXT NOT NULL DEFAULT 'new',     -- new | opened | dismissed
    apartment       TEXT,
    listing_id      INTEGER,
    reservation_id  TEXT,
    guest_name      TEXT,
    checkin_date    TEXT,
    checkout_date   TEXT,
    order_id        TEXT,
    dismissed_by    TEXT,
    dismissed_at    TEXT,
    dismiss_reason  TEXT,
    msg_id          TEXT,                            -- the Discord message its buttons live on
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decor_leads_status ON decor_leads(status, created_at);

CREATE TABLE IF NOT EXISTS decor_orders (
    id                 TEXT PRIMARY KEY,
    lead_id            TEXT,
    slug               TEXT NOT NULL,
    pack_id            TEXT NOT NULL,
    apartment          TEXT,
    listing_id         INTEGER,
    reservation_id     TEXT,
    guest_name         TEXT,
    checkin_date       TEXT,
    state              TEXT NOT NULL DEFAULT 'awaiting_guest',
    deadline_at        TEXT,
    event_at           TEXT,
    work_start_at      TEXT,
    inputs             TEXT,
    na_input_keys      TEXT,
    capability_verdict TEXT,
    capability_stamp   TEXT,
    override_kind      TEXT,
    overridden_by      TEXT,
    overridden_at      TEXT,
    override_reason    TEXT,
    final_price_sar    REAL,
    vendor_cost_sar    REAL,
    assignee           TEXT,
    vendor             TEXT,
    opened_by          TEXT,
    opened_at          TEXT,
    dispatched_by      TEXT,
    dispatched_at      TEXT,
    done_by            TEXT,
    done_at            TEXT,
    cancel_reason      TEXT,
    thread_id          TEXT,
    escalated          INTEGER NOT NULL DEFAULT 0,
    notes              TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_decor_orders_state ON decor_orders(state, deadline_at);
CREATE INDEX IF NOT EXISTS idx_decor_orders_slug  ON decor_orders(slug);

CREATE TABLE IF NOT EXISTS decor_cake_tasks (
    id          TEXT PRIMARY KEY,
    order_id    TEXT NOT NULL,
    due_at      TEXT NOT NULL,
    state       TEXT NOT NULL DEFAULT 'pending',   -- pending | ordered | delivered | cancelled
    flavor      TEXT,
    writing     TEXT,
    supplier    TEXT,
    ordered_by  TEXT,
    ordered_at  TEXT,
    delivered_at TEXT,
    escalated   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_decor_cake_order ON decor_cake_tasks(order_id);
CREATE INDEX IF NOT EXISTS idx_decor_cake_due   ON decor_cake_tasks(state, due_at);

CREATE TABLE IF NOT EXISTS decor_unit_features (
    slug       TEXT PRIMARY KEY,
    features   TEXT NOT NULL,          -- JSON list, e.g. ["pool","jacuzzi"]
    apartment  TEXT,
    updated_at TEXT,
    updated_by TEXT
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
            _migrate(cx)
            cx.commit()
        _inited.add(path)


def _migrate(cx):
    """Additive column migrations — CREATE TABLE IF NOT EXISTS never adds a column to a table
    that already exists, and this package already shipped once."""
    cols = {r["name"] for r in cx.execute("PRAGMA table_info(decor_leads)").fetchall()}
    if "msg_id" not in cols:
        cx.execute("ALTER TABLE decor_leads ADD COLUMN msg_id TEXT")


def reset_init_cache():
    _inited.clear()


def now_iso():
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


def _uid(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:12])


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


# ---------------- unit features (the sheet the owner fills) ----------------

def unit_features(slug):
    """The features a unit HAS, or None when we have no record of it at all.

    None is not an empty list: 'we don't know' and 'we know it has nothing' are different
    answers, and the supervisor is shown different wording for each."""
    row = q1("SELECT features FROM decor_unit_features WHERE slug=?", (str(slug or "").lower(),))
    if not row:
        return None
    return _j(row["features"], [])


def all_unit_features():
    return {r["slug"]: _j(r["features"], []) for r in
            q("SELECT slug, features FROM decor_unit_features")}


def set_unit_features(slug, features, apartment=None, by=""):
    slug = str(slug or "").lower()
    feats = json.dumps(sorted({str(f).strip().lower() for f in (features or []) if str(f).strip()}),
                       ensure_ascii=False)
    execute("""INSERT INTO decor_unit_features(slug, features, apartment, updated_at, updated_by)
               VALUES(?,?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET features=excluded.features,
                   apartment=COALESCE(excluded.apartment, decor_unit_features.apartment),
                   updated_at=excluded.updated_at, updated_by=excluded.updated_by""",
            (slug, feats, apartment, now_iso(), by))
    return unit_features(slug)


def add_unit_features(slug, features, by=""):
    """Used by a `correction` override — teach the sheet, so the same apartment never asks
    again. Never removes anything."""
    have = set(unit_features(slug) or [])
    have.update(str(f).strip().lower() for f in (features or []) if str(f).strip())
    return set_unit_features(slug, have, by=by)


# ---------------- leads (a guest tapped a button — NOT work) ----------------

def create_lead(slug, pack_id, lang="ar", source="guide", **ctx):
    """The ONLY thing a guest's tap produces. Note what is absent: no assignee, no deadline,
    no thread, no cake. Those columns do not exist on this table."""
    lid = _uid("lead")
    execute("""INSERT INTO decor_leads(id, slug, pack_id, lang, source, status, apartment,
                   listing_id, reservation_id, guest_name, checkin_date, checkout_date, created_at)
               VALUES(?,?,?,?,?,'new',?,?,?,?,?,?,?)""",
            (lid, str(slug or "").lower(), str(pack_id or ""), lang or "ar", source,
             ctx.get("apartment"), ctx.get("listing_id"), ctx.get("reservation_id"),
             ctx.get("guest_name"), ctx.get("checkin_date"), ctx.get("checkout_date"), now_iso()))
    return lead(lid)


def lead(lead_id):
    return q1("SELECT * FROM decor_leads WHERE id=?", (lead_id,))


def leads(status=None, limit=200):
    if status:
        return q("SELECT * FROM decor_leads WHERE status=? ORDER BY created_at DESC LIMIT ?",
                 (status, int(limit)))
    return q("SELECT * FROM decor_leads ORDER BY created_at DESC LIMIT ?", (int(limit),))


def recent_lead(slug, pack_id, since_iso):
    """Dedupe: a double-tap, or a guest opening the guide twice, must not become two lines."""
    return q1("""SELECT * FROM decor_leads WHERE slug=? AND pack_id=? AND created_at>=?
                 ORDER BY created_at DESC LIMIT 1""",
              (str(slug or "").lower(), str(pack_id or ""), since_iso))


def set_lead_msg(lead_id, msg_id):
    """Remember which Discord message carries this lead's buttons, so a click can find its
    lead after a redeploy without any state in the button itself."""
    execute("UPDATE decor_leads SET msg_id=? WHERE id=?", (str(msg_id), lead_id))
    return lead(lead_id)


def lead_by_msg(msg_id):
    return q1("SELECT * FROM decor_leads WHERE msg_id=?", (str(msg_id),))


def dismiss_lead(lead_id, by="", reason=""):
    execute("""UPDATE decor_leads SET status='dismissed', dismissed_by=?, dismissed_at=?,
               dismiss_reason=? WHERE id=? AND status='new'""",
            (by, now_iso(), reason, lead_id))
    return lead(lead_id)


# ---------------- orders (a supervisor decided) ----------------

def open_order(lead_id, slug, pack_id, by, **fields):
    """The ONLY insert into decor_orders in the whole codebase. Reachable exclusively from
    the role-gated supervisor endpoint — never from the public guide endpoint."""
    oid = _uid("dec")
    cols = {
        "id": oid, "lead_id": lead_id, "slug": str(slug or "").lower(), "pack_id": str(pack_id or ""),
        "apartment": fields.get("apartment"), "listing_id": fields.get("listing_id"),
        "reservation_id": fields.get("reservation_id"), "guest_name": fields.get("guest_name"),
        "checkin_date": fields.get("checkin_date"), "state": fields.get("state") or "awaiting_guest",
        "deadline_at": fields.get("deadline_at"), "event_at": fields.get("event_at"),
        "work_start_at": fields.get("work_start_at"),
        "inputs": json.dumps(fields.get("inputs") or {}, ensure_ascii=False),
        "na_input_keys": json.dumps(fields.get("na_input_keys") or [], ensure_ascii=False),
        "capability_verdict": fields.get("capability_verdict"),
        "capability_stamp": fields.get("capability_stamp") or "",
        "override_kind": fields.get("override_kind"), "overridden_by": fields.get("overridden_by"),
        "overridden_at": fields.get("overridden_at"), "override_reason": fields.get("override_reason"),
        "final_price_sar": fields.get("final_price_sar"), "assignee": fields.get("assignee"),
        "opened_by": by, "opened_at": now_iso(), "created_at": now_iso(), "updated_at": now_iso(),
    }
    keys = list(cols)
    execute("INSERT INTO decor_orders(%s) VALUES(%s)" % (",".join(keys), ",".join("?" * len(keys))),
            tuple(cols[k] for k in keys))
    if lead_id:
        execute("UPDATE decor_leads SET status='opened', order_id=? WHERE id=?", (oid, lead_id))
    return order(oid)


def order(order_id):
    row = q1("SELECT * FROM decor_orders WHERE id=?", (order_id,))
    if row:
        row["inputs"] = _j(row.get("inputs"), {})
        row["na_input_keys"] = _j(row.get("na_input_keys"), [])
    return row


def order_by_thread(thread_id):
    """Which order does this Discord thread belong to? This is how the buttons survive a
    redeploy: they carry no id, the THREAD is the id."""
    row = q1("SELECT * FROM decor_orders WHERE thread_id=?", (str(thread_id),))
    if row:
        row["inputs"] = _j(row.get("inputs"), {})
        row["na_input_keys"] = _j(row.get("na_input_keys"), [])
    return row


def live_orders():
    """Orders still capable of running late — what the warning clock walks."""
    rows = q("""SELECT * FROM decor_orders
                WHERE state NOT IN ('done','cancelled') AND deadline_at IS NOT NULL""")
    for r in rows:
        r["inputs"] = _j(r.get("inputs"), {})
        r["na_input_keys"] = _j(r.get("na_input_keys"), [])
    return rows


def orders(state=None, limit=300):
    if state:
        rows = q("SELECT * FROM decor_orders WHERE state=? ORDER BY deadline_at IS NULL, deadline_at LIMIT ?",
                 (state, int(limit)))
    else:
        rows = q("SELECT * FROM decor_orders ORDER BY deadline_at IS NULL, deadline_at LIMIT ?",
                 (int(limit),))
    for r in rows:
        r["inputs"] = _j(r.get("inputs"), {})
        r["na_input_keys"] = _j(r.get("na_input_keys"), [])
    return rows


_UPDATABLE = ("state", "deadline_at", "event_at", "work_start_at", "final_price_sar",
              "vendor_cost_sar", "assignee", "vendor", "notes", "thread_id", "escalated",
              "dispatched_by", "dispatched_at", "done_by", "done_at", "cancel_reason")


def update_order(order_id, **fields):
    sets, args = [], []
    for k, v in fields.items():
        if k not in _UPDATABLE:
            continue
        sets.append("%s=?" % k)
        args.append(v)
    if not sets:
        return order(order_id)
    sets.append("updated_at=?")
    args.extend([now_iso(), order_id])
    execute("UPDATE decor_orders SET %s WHERE id=?" % ",".join(sets), tuple(args))
    return order(order_id)


def set_inputs(order_id, inputs):
    cur = order(order_id)
    if not cur:
        return None
    merged = dict(cur.get("inputs") or {})
    for k, v in (inputs or {}).items():
        merged[str(k)] = v
    execute("UPDATE decor_orders SET inputs=?, updated_at=? WHERE id=?",
            (json.dumps(merged, ensure_ascii=False), now_iso(), order_id))
    return order(order_id)


# ---------------- the cake: a separate job with a separate deadline ----------------

def create_cake_task(order_id, due_at, flavor=None, writing=None):
    cid = _uid("cake")
    execute("""INSERT INTO decor_cake_tasks(id, order_id, due_at, state, flavor, writing, created_at, updated_at)
               VALUES(?,?,?,'pending',?,?,?,?)""",
            (cid, order_id, due_at, flavor, writing, now_iso(), now_iso()))
    return cake_task(cid)


def cake_task(cake_id):
    return q1("SELECT * FROM decor_cake_tasks WHERE id=?", (cake_id,))


def cake_for_order(order_id):
    return q1("SELECT * FROM decor_cake_tasks WHERE order_id=? ORDER BY created_at LIMIT 1",
              (order_id,))


def cake_tasks(state=None):
    if state:
        return q("SELECT * FROM decor_cake_tasks WHERE state=? ORDER BY due_at", (state,))
    return q("SELECT * FROM decor_cake_tasks ORDER BY due_at")


def update_cake(cake_id, **fields):
    allowed = ("state", "flavor", "writing", "supplier", "ordered_by", "ordered_at",
               "delivered_at", "escalated", "due_at")
    sets, args = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append("%s=?" % k)
            args.append(v)
    if not sets:
        return cake_task(cake_id)
    sets.append("updated_at=?")
    args.extend([now_iso(), cake_id])
    execute("UPDATE decor_cake_tasks SET %s WHERE id=?" % ",".join(sets), tuple(args))
    return cake_task(cake_id)


def counts():
    """Cheap numbers for the dashboard chips and the tests' before/after assertions."""
    def n(sql, args=()):
        row = q1(sql, args)
        return list(row.values())[0] if row else 0
    return {
        "leads_new": n("SELECT COUNT(*) c FROM decor_leads WHERE status='new'"),
        "leads_total": n("SELECT COUNT(*) c FROM decor_leads"),
        "orders": n("SELECT COUNT(*) c FROM decor_orders"),
        "awaiting_guest": n("SELECT COUNT(*) c FROM decor_orders WHERE state='awaiting_guest'"),
        "ready": n("SELECT COUNT(*) c FROM decor_orders WHERE state='ready'"),
        "dispatched": n("SELECT COUNT(*) c FROM decor_orders WHERE state='dispatched'"),
        "cakes_pending": n("SELECT COUNT(*) c FROM decor_cake_tasks WHERE state='pending'"),
        "cakes": n("SELECT COUNT(*) c FROM decor_cake_tasks"),
    }
