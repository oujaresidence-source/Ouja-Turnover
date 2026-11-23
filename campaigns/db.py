# -*- coding: utf-8 -*-
"""
campaign_* tables inside the SAME brain.db on STATE_DIR (journal DELETE, one short connection
per call via closing(connect()) — the rules proven in hatif/db.py and stayhub/db.py).

    campaign_hits      one row per Hostaway guest message that carried a code word.
                       PRIMARY KEY = Hostaway message id → a message is alerted once, even when
                       the webhook and the poll loop (or two bot copies) both see it.
    campaign_taps      one row per Hatif button tap. PRIMARY KEY = Hatif's event id (Hatif
                       retries a delivery up to 5 times).
    campaign_optouts   THE SUPPRESSION LIST. Kept forever (never pruned). Keyed by the phone's
                       salted HMAC (engine.phone_key) and, when Hatif gave no number, by the
                       Hatif contact id. The number itself is never stored — last 4 only.
    campaign_settings  key/value: the HMAC salt (made once, never changes) and the weekly
                       report latch (the date it last posted).

PRIVACY: no phone number, no message body beyond 200 masked characters.
"""
import datetime
import json
import secrets
import threading
from contextlib import closing

from brain import db as _bdb

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_hits (
    message_id      TEXT PRIMARY KEY,
    code            TEXT,
    created_at      TEXT,
    conversation_id TEXT,
    reservation_id  TEXT,
    listing_id      TEXT,
    unit            TEXT,
    guest           TEXT,
    guest_key       TEXT,
    res_status      TEXT,
    check_in        TEXT,
    check_out       TEXT,
    offer           TEXT,
    body            TEXT
);
CREATE INDEX IF NOT EXISTS campaign_hits_created ON campaign_hits(created_at);
CREATE TABLE IF NOT EXISTS campaign_taps (
    event_id        TEXT PRIMARY KEY,
    created_at      TEXT,
    conversation_id TEXT,
    contact_id      TEXT,
    template        TEXT,
    label           TEXT,
    kind            TEXT,
    phone_key       TEXT,
    last4           TEXT,
    guest           TEXT,
    guest_key       TEXT,
    outcome         TEXT,
    raw_keys        TEXT
);
CREATE INDEX IF NOT EXISTS campaign_taps_created ON campaign_taps(created_at);
CREATE TABLE IF NOT EXISTS campaign_optouts (
    opt_key         TEXT PRIMARY KEY,
    created_at      TEXT,
    contact_id      TEXT,
    conversation_id TEXT,
    last4           TEXT,
    source          TEXT,
    template        TEXT
);
CREATE TABLE IF NOT EXISTS campaign_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS campaign_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT,
    created_at  TEXT,
    message_id  TEXT,
    channel_id  TEXT,
    state       TEXT,
    claimed_by  TEXT,
    actor       TEXT,
    action      TEXT,
    acted_at    TEXT,
    note        TEXT,
    ctx         TEXT
);
CREATE INDEX IF NOT EXISTS campaign_alerts_msg ON campaign_alerts(message_id);
CREATE TABLE IF NOT EXISTS campaign_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch       TEXT,
    campaign    TEXT,
    template    TEXT,
    lang        TEXT,
    phone       TEXT,
    phone_key   TEXT,
    last4       TEXT,
    vals        TEXT,
    image_url   TEXT,
    send_at     TEXT,
    state       TEXT,
    created_at  TEXT,
    sent_at     TEXT,
    error       TEXT,
    UNIQUE(campaign, phone_key)
);
CREATE INDEX IF NOT EXISTS campaign_queue_due ON campaign_queue(state, send_at);
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


def reset_init_cache():
    _inited.clear()


def now_iso():
    """UTC, seconds — the same clock hatif_events uses."""
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------- settings
def get_setting(key, default=None):
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute("SELECT value FROM campaign_settings WHERE key=?", (str(key),)).fetchone()
    return r[0] if r else default


def set_setting(key, value):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("INSERT INTO campaign_settings(key, value) VALUES(?,?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(key), str(value)))
        cx.commit()


def claim_setting(key, expected_old, new):
    """Compare-and-set: True only for the ONE caller that moved key from expected_old to new
    (the weekly latch — two bot copies during a redeploy post one report)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("INSERT OR IGNORE INTO campaign_settings(key, value) VALUES(?, '')", (str(key),))
        cur = cx.execute("UPDATE campaign_settings SET value=? WHERE key=? AND value=?",
                         (str(new), str(key), str(expected_old or "")))
        cx.commit()
        return cur.rowcount == 1


def salt():
    """The per-install HMAC salt. Made once; INSERT OR IGNORE so two copies agree on one."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("INSERT OR IGNORE INTO campaign_settings(key, value) VALUES('salt', ?)",
                   (secrets.token_hex(16),))
        cx.commit()
        return cx.execute("SELECT value FROM campaign_settings WHERE key='salt'").fetchone()[0]


# ---------------------------------------------------------------- code-word hits
def claim_hit(message_id, row):
    """True exactly once per Hostaway message id."""
    _ensure()
    r = dict(row or {})
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT OR IGNORE INTO campaign_hits(message_id, code, created_at, conversation_id, "
            "reservation_id, listing_id, unit, guest, guest_key, res_status, check_in, check_out, "
            "offer, body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(message_id), r.get("code"), r.get("created_at") or now_iso(),
             _s(r.get("conversation_id")), _s(r.get("reservation_id")), _s(r.get("listing_id")),
             r.get("unit"), r.get("guest"), r.get("guest_key"), r.get("res_status"),
             r.get("check_in"), r.get("check_out"), None, (r.get("body") or "")[:200]))
        cx.commit()
        return cur.rowcount == 1


def finish_hit(message_id, offer):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("UPDATE campaign_hits SET offer=? WHERE message_id=?",
                   (json.dumps(offer, ensure_ascii=False, default=str), str(message_id)))
        cx.commit()


def release_hit(message_id):
    """Undo a claim when the alert could not be built, so the poll loop tries again."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("DELETE FROM campaign_hits WHERE message_id=? AND offer IS NULL", (str(message_id),))
        cx.commit()


def hits_between(start_iso, end_iso):
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(
            "SELECT message_id, code, created_at, conversation_id, reservation_id, listing_id, unit, "
            "guest, guest_key, res_status, check_in, check_out, offer FROM campaign_hits "
            "WHERE created_at >= ? AND created_at < ? ORDER BY created_at", (start_iso, end_iso)).fetchall()
    keys = ("message_id", "code", "created_at", "conversation_id", "reservation_id", "listing_id",
            "unit", "guest", "guest_key", "res_status", "check_in", "check_out", "offer")
    return [dict(zip(keys, r)) for r in rows]


# ---------------------------------------------------------------- button taps
def claim_tap(event_id, row):
    _ensure()
    r = dict(row or {})
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT OR IGNORE INTO campaign_taps(event_id, created_at, conversation_id, contact_id, "
            "template, label, kind, phone_key, last4, guest, guest_key, outcome, raw_keys) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(event_id), r.get("created_at") or now_iso(), _s(r.get("conversation_id")),
             _s(r.get("contact_id")), r.get("template"), (r.get("label") or "")[:80], r.get("kind"),
             r.get("phone_key"), r.get("last4"), r.get("guest"), r.get("guest_key"),
             r.get("outcome") or "claimed", r.get("raw_keys")))
        cx.commit()
        return cur.rowcount == 1


def update_tap(event_id, **fields):
    allowed = ("phone_key", "last4", "guest", "guest_key", "outcome", "template")
    sets = [(k, v) for k, v in fields.items() if k in allowed]
    if not sets:
        return
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("UPDATE campaign_taps SET %s WHERE event_id=?" % ", ".join("%s=?" % k for k, _ in sets),
                   tuple(v for _, v in sets) + (str(event_id),))
        cx.commit()


def taps_between(start_iso, end_iso):
    _ensure()
    keys = ("event_id", "created_at", "conversation_id", "contact_id", "template", "label", "kind",
            "phone_key", "last4", "guest", "guest_key", "outcome", "raw_keys")
    with closing(_bdb.connect()) as cx:
        rows = cx.execute("SELECT %s FROM campaign_taps WHERE created_at >= ? AND created_at < ? "
                          "ORDER BY created_at" % ", ".join(keys), (start_iso, end_iso)).fetchall()
    return [dict(zip(keys, r)) for r in rows]


def recent_taps(limit=30):
    _ensure()
    keys = ("created_at", "template", "label", "kind", "last4", "outcome", "raw_keys")
    with closing(_bdb.connect()) as cx:
        rows = cx.execute("SELECT %s FROM campaign_taps ORDER BY created_at DESC, rowid DESC LIMIT ?"
                          % ", ".join(keys), (int(limit),)).fetchall()
    return [dict(zip(keys, r)) for r in rows]


# ---------------------------------------------------------------- the suppression list
def add_optout(opt_key, contact_id=None, conversation_id=None, last4=None, source="button",
               template=None, created_at=None):
    """True when this is a NEW opt-out, False when the person was already on the list."""
    if not opt_key:
        return False
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT OR IGNORE INTO campaign_optouts(opt_key, created_at, contact_id, conversation_id, "
            "last4, source, template) VALUES(?,?,?,?,?,?,?)",
            (str(opt_key), created_at or now_iso(), _s(contact_id), _s(conversation_id), last4, source,
             template))
        cx.commit()
        return cur.rowcount == 1


def is_opted_out(keys, contact_id=None):
    """Any of the given keys (phone key, contact key) — or the Hatif contact — on the list."""
    keys = [str(k) for k in (keys or []) if k]
    if not keys and not contact_id:
        return False
    _ensure()
    q, args = [], []
    if keys:
        q.append("opt_key IN (%s)" % ",".join("?" * len(keys)))
        args.extend(keys)
    if contact_id:
        q.append("contact_id = ?")
        args.append(str(contact_id))
    with closing(_bdb.connect()) as cx:
        r = cx.execute("SELECT 1 FROM campaign_optouts WHERE %s LIMIT 1" % " OR ".join(q),
                       tuple(args)).fetchone()
    return r is not None


def optouts(since_iso=None, until_iso=None):
    _ensure()
    q = "SELECT opt_key, created_at, contact_id, conversation_id, last4, source, template FROM campaign_optouts"
    args = []
    if since_iso:
        q += " WHERE created_at >= ? AND created_at < ?"
        args = [since_iso, until_iso or "9999"]
    with closing(_bdb.connect()) as cx:
        rows = cx.execute(q + " ORDER BY created_at", tuple(args)).fetchall()
    keys = ("opt_key", "created_at", "contact_id", "conversation_id", "last4", "source", "template")
    return [dict(zip(keys, r)) for r in rows]


# ---------------------------------------------------------------- Discord alert cards
# One row per card posted in «عروض-خاصة» / «طلبات-الملاك». The Discord message id is the key a
# button press arrives with; ctx holds what the card shows and what a button sends (no phone
# number — last 4 + the Hatif conversation id, re-read from the Hatif API at press time).
# state: open → busy (a press in flight, compare-and-set) → open | waiting | done | dismissed.
_ALERT_KEYS = ("id", "kind", "created_at", "message_id", "channel_id", "state", "claimed_by",
               "actor", "action", "acted_at", "note", "ctx")


def _alert_row(r):
    if not r:
        return None
    a = dict(zip(_ALERT_KEYS, r))
    try:
        a["ctx"] = json.loads(a["ctx"] or "{}")
    except ValueError:
        a["ctx"] = {}
    return a


def new_alert(kind, ctx, state="open"):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute("INSERT INTO campaign_alerts(kind, created_at, state, ctx) VALUES(?,?,?,?)",
                         (str(kind), now_iso(), state,
                          json.dumps(ctx or {}, ensure_ascii=False, default=str)))
        cx.commit()
        return cur.lastrowid


def set_alert_message(alert_id, message_id, channel_id=None):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("UPDATE campaign_alerts SET message_id=?, channel_id=? WHERE id=?",
                   (_s(message_id), _s(channel_id), int(alert_id)))
        cx.commit()


def alert(alert_id):
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute("SELECT %s FROM campaign_alerts WHERE id=?" % ", ".join(_ALERT_KEYS),
                       (int(alert_id),)).fetchone()
    return _alert_row(r)


def alert_by_message(message_id):
    _ensure()
    with closing(_bdb.connect()) as cx:
        r = cx.execute("SELECT %s FROM campaign_alerts WHERE message_id=? ORDER BY id DESC LIMIT 1"
                       % ", ".join(_ALERT_KEYS), (_s(message_id),)).fetchone()
    return _alert_row(r)


def set_alert_ctx(alert_id, ctx):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("UPDATE campaign_alerts SET ctx=? WHERE id=?",
                   (json.dumps(ctx or {}, ensure_ascii=False, default=str), int(alert_id)))
        cx.commit()


def claim_alert(alert_id, who):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cx.execute("UPDATE campaign_alerts SET claimed_by=? WHERE id=?", (str(who)[:60], int(alert_id)))
        cx.commit()


def begin_alert_action(alert_id, from_states=("open", "waiting")):
    """Compare-and-set to «busy»: True for the ONE press that may act (two people pressing
    «أرسل» at once send one message). Returns the state it moved from, or None."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        for st in from_states:
            cur = cx.execute("UPDATE campaign_alerts SET state='busy' WHERE id=? AND state=?",
                             (int(alert_id), st))
            if cur.rowcount == 1:
                cx.commit()
                return st
        cx.commit()
    return None


def end_alert_action(alert_id, state, actor=None, action=None, note=None):
    _ensure()
    with closing(_bdb.connect()) as cx:
        if actor is None:
            cx.execute("UPDATE campaign_alerts SET state=?, note=? WHERE id=?",
                       (state, note, int(alert_id)))
        else:
            cx.execute("UPDATE campaign_alerts SET state=?, actor=?, action=?, acted_at=?, note=? "
                       "WHERE id=?", (state, str(actor)[:60], action, now_iso(), note, int(alert_id)))
        cx.commit()


# ---------------------------------------------------------------- the per-person queue
# THE one place a phone number is kept, and only until it is sent: the number is needed to
# send, then erased (phone_key + last 4 stay for the report and the never-twice rule).
_Q_KEYS = ("id", "batch", "campaign", "template", "lang", "phone", "phone_key", "last4", "vals",
           "image_url", "send_at", "state", "created_at", "sent_at", "error")


def queue_add(row):
    """True when queued, False when this person already has this campaign (never twice)."""
    _ensure()
    r = dict(row)
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(
            "INSERT OR IGNORE INTO campaign_queue(batch, campaign, template, lang, phone, phone_key, "
            "last4, vals, image_url, send_at, state, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?)",
            (r["batch"], r["campaign"], r["template"], r.get("lang") or "ar", r["phone"], r["phone_key"],
             r.get("last4"), json.dumps(r.get("vals") or [], ensure_ascii=False), r.get("image_url"),
             r["send_at"], now_iso()))
        cx.commit()
        return cur.rowcount == 1


def queue_due(now_utc_iso, limit):
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute("SELECT %s FROM campaign_queue WHERE state='queued' AND send_at <= ? "
                          "ORDER BY send_at, id LIMIT ?" % ", ".join(_Q_KEYS),
                          (now_utc_iso, int(limit))).fetchall()
    out = []
    for r in rows:
        d = dict(zip(_Q_KEYS, r))
        try:
            d["vals"] = json.loads(d["vals"] or "[]")
        except ValueError:
            d["vals"] = []
        out.append(d)
    return out


def queue_claim(qid):
    """queued → sending, for ONE caller (two bot copies during a redeploy send once)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute("UPDATE campaign_queue SET state='sending' WHERE id=? AND state='queued'",
                         (int(qid),))
        cx.commit()
        return cur.rowcount == 1


def queue_finish(qid, state, error=None):
    """sent / suppressed / failed erase the number; «queued» puts it back (rate limit)."""
    _ensure()
    with closing(_bdb.connect()) as cx:
        if state == "queued":
            cx.execute("UPDATE campaign_queue SET state='queued' WHERE id=?", (int(qid),))
        else:
            cx.execute("UPDATE campaign_queue SET state=?, phone=NULL, sent_at=?, error=? WHERE id=?",
                       (state, now_iso(), (error or None) and str(error)[:120], int(qid)))
        cx.commit()


def queue_cancel(batch):
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute("UPDATE campaign_queue SET state='cancelled', phone=NULL "
                         "WHERE batch=? AND state='queued'", (str(batch),))
        cx.commit()
        return cur.rowcount


def queue_summary():
    _ensure()
    with closing(_bdb.connect()) as cx:
        rows = cx.execute("SELECT batch, campaign, state, COUNT(*), MIN(send_at), MAX(send_at) "
                          "FROM campaign_queue GROUP BY batch, campaign, state "
                          "ORDER BY MIN(send_at)").fetchall()
    return [{"batch": b, "campaign": c, "state": s, "n": n, "first": f, "last": l}
            for b, c, s, n, f, l in rows]


def _s(v):
    return None if v is None else str(v)
