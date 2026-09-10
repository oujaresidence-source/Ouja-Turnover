# -*- coding: utf-8 -*-
"""
directpay.* tables inside the SAME brain.db (NO WAL, journal DELETE, busy_timeout, one short
connection per call via closing(connect()) — the proven rules, see CLAUDE.md). Modelled on
decor/db.py: SCHEMA, _inited + _init_lock, _ensure(), _migrate(cx), reset_init_cache().

THE STRUCTURAL GUARANTEE
    UNIQUE(reservation_id) on directpay_tickets. A reservation gets ONE ticket, ever — a fact
    about the database, not a promise about a loop. open_ticket() is INSERT OR IGNORE and
    returns None when the row already existed.

directpay_events is the audit trail: every open, nudge, close attempt (INCLUDING every refused
one, with who tried), void, reopen. Append-only — there is deliberately no update/delete helper.
"""
import datetime
import json
import threading
import uuid
from contextlib import closing

from brain import db as _bdb

# Column list = the single source for CREATE TABLE and for the additive migration. Constraint
# columns (PRIMARY KEY / UNIQUE) can never be ALTER-added, so they sit first and never move.
TICKET_COLS = [
    ("id", "TEXT PRIMARY KEY"),                 # dp_<uuid12>
    ("reservation_id", "TEXT NOT NULL UNIQUE"), # THE anti-duplicate guarantee
    ("seq", "INTEGER"),                         # _next_counter("directpay_ticket")
    ("confirmation_code", "TEXT"),
    ("listing_id", "INTEGER"),
    ("unit_name", "TEXT"),
    ("guest_name", "TEXT"),
    ("guest_phone", "TEXT"),
    ("channel_raw", "TEXT"),                    # the raw channelName, verbatim
    ("arrival", "TEXT"),
    ("departure", "TEXT"),
    ("nights", "INTEGER"),
    ("total_sar", "REAL"),                      # Hostaway totalPrice at open
    ("total_sar_current", "REAL"),              # refreshed each tick; drift is surfaced
    ("booked_at", "TEXT"),
    ("ha_status", "TEXT"),                      # Hostaway reservation status, last seen
    ("ha_payment_status", "TEXT"),              # from _payment_signal — evidence, not truth
    ("ha_paid_amount", "REAL"),
    ("ha_remaining", "REAL"),
    ("ha_payment_fields", "TEXT"),              # which fields _payment_signal actually read
    ("channel_id", "TEXT"),                     # Discord room id
    ("card_msg_id", "TEXT"),
    ("status", "TEXT NOT NULL DEFAULT 'open'"), # open | verified | written_off | void
    ("received_sar", "REAL"),
    ("stayhub_ref", "TEXT"),
    ("proof_path", "TEXT"),                     # relative path under STATE_DIR
    ("proof_meta", "TEXT"),                     # JSON: filename, size, content_type, uploader
    ("variance_sar", "REAL"),
    ("variance_reason", "TEXT"),
    ("closed_by", "TEXT"),
    ("closed_by_id", "TEXT"),
    ("closed_at", "TEXT"),
    ("close_note", "TEXT"),
    ("void_reason", "TEXT"),
    ("nudge_count", "INTEGER DEFAULT 0"),
    ("last_nudge_at", "TEXT"),
    ("dryrun", "INTEGER DEFAULT 0"),
    ("created_at", "TEXT"),
    ("reopened_at", "TEXT"),
    ("room_requested_at", "TEXT"),              # when the 'open' notify last fired (retry after 1h)
    ("refreshed_at", "TEXT"),                   # last time Hostaway was re-read for this row
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS directpay_tickets (
    %s
);
CREATE INDEX IF NOT EXISTS idx_dp_status  ON directpay_tickets(status, created_at);
CREATE INDEX IF NOT EXISTS idx_dp_listing ON directpay_tickets(listing_id, arrival);
CREATE INDEX IF NOT EXISTS idx_dp_channel ON directpay_tickets(channel_id);

CREATE TABLE IF NOT EXISTS directpay_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    at        TEXT,
    actor     TEXT,
    actor_id  TEXT,
    kind      TEXT,
    detail    TEXT
);
CREATE INDEX IF NOT EXISTS idx_dp_ev ON directpay_events(ticket_id, at);

CREATE TABLE IF NOT EXISTS directpay_settings (k TEXT PRIMARY KEY, v TEXT);
""" % ", ".join("%s %s" % (n, t) for n, t in TICKET_COLS)

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
    that already exists. Every column in TICKET_COLS that the live table lacks is ALTER-added
    (constraint columns excluded: SQLite cannot add those, and they never move)."""
    have = {r["name"] for r in cx.execute("PRAGMA table_info(directpay_tickets)").fetchall()}
    for name, typ in TICKET_COLS:
        if name in have:
            continue
        if "PRIMARY KEY" in typ or "UNIQUE" in typ or "NOT NULL" in typ:
            continue
        cx.execute("ALTER TABLE directpay_tickets ADD COLUMN %s %s" % (name, typ))


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


# ---------------- tickets ----------------

_INSERTABLE = {n for n, _ in TICKET_COLS} - {"id"}
_UPDATABLE = {n for n, _ in TICKET_COLS} - {"id", "reservation_id", "created_at"}


def open_ticket(**fields):
    """The ONLY insert into directpay_tickets. INSERT OR IGNORE against UNIQUE(reservation_id):
    returns the new row, or None when a ticket for that reservation already existed."""
    rid = fields.get("reservation_id")
    if rid is None or str(rid).strip() == "":
        return None
    cols = {"id": _uid("dp"), "reservation_id": str(rid).strip(),
            "status": fields.get("status") or "open",
            "created_at": fields.get("created_at") or now_iso(),
            "nudge_count": int(fields.get("nudge_count") or 0),
            "dryrun": int(fields.get("dryrun") or 0)}
    for k, v in fields.items():
        if k in _INSERTABLE and k not in cols:
            if k == "proof_meta" and isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            cols[k] = v
    keys = list(cols)
    n = execute("INSERT OR IGNORE INTO directpay_tickets(%s) VALUES(%s)"
                % (",".join(keys), ",".join("?" * len(keys))), tuple(cols[k] for k in keys))
    if not n:
        return None
    return ticket(cols["id"])


def ticket(ticket_id):
    return q1("SELECT * FROM directpay_tickets WHERE id=?", (str(ticket_id),))


def by_reservation(reservation_id):
    return q1("SELECT * FROM directpay_tickets WHERE reservation_id=?", (str(reservation_id).strip(),))


def by_channel(channel_id):
    """Which ticket does this Discord room belong to? The buttons carry no id — the ROOM is
    the id, so a press months later, after any number of redeploys, still finds its row."""
    if channel_id is None:
        return None
    return q1("SELECT * FROM directpay_tickets WHERE channel_id=?", (str(channel_id),))


def update(ticket_id, **fields):
    sets, args = [], []
    for k, v in fields.items():
        if k not in _UPDATABLE:
            continue
        if k == "proof_meta" and isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        sets.append("%s=?" % k)
        args.append(v)
    if not sets:
        return ticket(ticket_id)
    args.append(str(ticket_id))
    execute("UPDATE directpay_tickets SET %s WHERE id=?" % ",".join(sets), tuple(args))
    return ticket(ticket_id)


def known_reservation_ids():
    return {r["reservation_id"] for r in q("SELECT reservation_id FROM directpay_tickets")}


def open_tickets():
    return q("SELECT * FROM directpay_tickets WHERE status='open' ORDER BY created_at")


def tickets(status=None, limit=500):
    if status:
        return q("SELECT * FROM directpay_tickets WHERE status=? ORDER BY created_at DESC LIMIT ?",
                 (status, int(limit)))
    return q("SELECT * FROM directpay_tickets ORDER BY created_at DESC LIMIT ?", (int(limit),))


def live_tickets():
    """Rows Hostaway can still change our view of: open, plus verified (watched for a rise)."""
    return q("SELECT * FROM directpay_tickets WHERE status IN ('open','verified') ORDER BY created_at")


def roomless(before_iso=None, limit=5):
    """Open tickets with no Discord room yet (dry-run rows, or a room whose creation failed),
    whose last 'open' request is older than before_iso (or never made)."""
    if before_iso:
        return q("""SELECT * FROM directpay_tickets WHERE status='open' AND channel_id IS NULL
                    AND (room_requested_at IS NULL OR room_requested_at < ?)
                    ORDER BY created_at LIMIT ?""", (before_iso, int(limit)))
    return q("""SELECT * FROM directpay_tickets WHERE status='open' AND channel_id IS NULL
                AND room_requested_at IS NULL ORDER BY created_at LIMIT ?""", (int(limit),))


def roomless_count(before_iso=None):
    if before_iso:
        row = q1("""SELECT COUNT(*) c FROM directpay_tickets WHERE status='open' AND channel_id IS NULL
                    AND (room_requested_at IS NULL OR room_requested_at < ?)""", (before_iso,))
    else:
        row = q1("""SELECT COUNT(*) c FROM directpay_tickets WHERE status='open' AND channel_id IS NULL
                    AND room_requested_at IS NULL""")
    return int(row["c"] if row else 0)


# ---------------- events (append-only) ----------------

def add_event(ticket_id, kind, actor="", actor_id="", detail="", at=None):
    execute("INSERT INTO directpay_events(ticket_id, at, actor, actor_id, kind, detail) VALUES(?,?,?,?,?,?)",
            (str(ticket_id), at or now_iso(), str(actor or ""), str(actor_id or ""), str(kind or ""),
             str(detail or "")[:2000]))


def events(ticket_id, limit=500):
    return q("SELECT * FROM directpay_events WHERE ticket_id=? ORDER BY id LIMIT ?",
             (str(ticket_id), int(limit)))


# ---------------- settings ----------------

def setting_get(k, default=None):
    row = q1("SELECT v FROM directpay_settings WHERE k=?", (str(k),))
    return row["v"] if row else default


def setting_set(k, v):
    execute("INSERT INTO directpay_settings(k, v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (str(k), None if v is None else str(v)))


def counts():
    def n(sql, args=()):
        row = q1(sql, args)
        return list(row.values())[0] if row else 0
    return {
        "open": n("SELECT COUNT(*) c FROM directpay_tickets WHERE status='open'"),
        "verified": n("SELECT COUNT(*) c FROM directpay_tickets WHERE status='verified'"),
        "written_off": n("SELECT COUNT(*) c FROM directpay_tickets WHERE status='written_off'"),
        "void": n("SELECT COUNT(*) c FROM directpay_tickets WHERE status='void'"),
        "total": n("SELECT COUNT(*) c FROM directpay_tickets"),
        "events": n("SELECT COUNT(*) c FROM directpay_events"),
    }
