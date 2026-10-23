# -*- coding: utf-8 -*-
"""
rrdesk.db — «طلبات سام» storage, inside the SAME brain.db every other package uses.

Connection rules come from brain.db.connect() (no WAL, journal_mode=DELETE, one short-lived
connection per call) — read brain/db.py's docstring before changing anything here.

WHAT THE SCHEMA ENFORCES (idempotency is a fact about the database, not a promise in code)
  * one translation per source message        rrdesk_translations UNIQUE(source_message_id)
  * one request per Sam message               rrdesk_requests     UNIQUE(source_message_id)
  * each ladder step once                     rrdesk_ladder       UNIQUE(request_id, step)
  * one miss per request per owner            rrdesk_misses       UNIQUE(request_id, gen)
  * each Discord side effect once             rrdesk_outbox       UNIQUE(ref)
  * daily/weekly latches                      rrdesk_settings     key 'latch:<name>'
rrdesk_events is append-only: the debug log. Nothing here deletes a row except the outbox
janitor (done rows older than 30 days) and the cache janitor.
"""

import datetime
import json
import threading
from contextlib import closing

from brain import db as _bdb
from ops import engine as oeng

SCHEMA = """
CREATE TABLE IF NOT EXISTS rrdesk_rooms (
    channel_id    TEXT PRIMARY KEY,
    translate_on  INTEGER NOT NULL DEFAULT 1,
    set_by        TEXT,
    set_at        TEXT,
    last_seen_at  TEXT
);
CREATE TABLE IF NOT EXISTS rrdesk_translations (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    source_message_id  TEXT NOT NULL UNIQUE,
    channel_id         TEXT,
    author_id          TEXT,
    is_bot             INTEGER NOT NULL DEFAULT 0,
    direction          TEXT,
    state              TEXT NOT NULL DEFAULT 'claimed',  -- claimed|done|failed|skipped
    skip_reason        TEXT,
    our_message_ids    TEXT NOT NULL DEFAULT '[]',
    chars              INTEGER NOT NULL DEFAULT 0,
    source             TEXT,                             -- model|cache|phrase
    tokens_in          INTEGER NOT NULL DEFAULT 0,
    tokens_out         INTEGER NOT NULL DEFAULT 0,
    cost_usd           REAL NOT NULL DEFAULT 0,
    question           TEXT,                             -- 'asked' | 'yes' | 'no'  (path 4)
    classify_json      TEXT,
    has_media          INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_rrd_tr_day ON rrdesk_translations(created_at);
CREATE TABLE IF NOT EXISTS rrdesk_cache (
    key          TEXT PRIMARY KEY,
    direction    TEXT,
    result_json  TEXT NOT NULL,
    hits         INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT,
    last_hit_at  TEXT
);
CREATE TABLE IF NOT EXISTS rrdesk_requests (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    source_message_id  TEXT NOT NULL UNIQUE,
    channel_id         TEXT NOT NULL,
    ticket_seq         TEXT,
    ticket_code        TEXT,
    lid                TEXT,
    text               TEXT,
    summary_en         TEXT,
    summary_ar         TEXT,
    asks_json          TEXT NOT NULL DEFAULT '[]',
    urgent             INTEGER NOT NULL DEFAULT 0,
    urgent_why         TEXT,
    path               TEXT NOT NULL,
    confidence         REAL,
    owner_did          TEXT,
    owner_name         TEXT,
    owner_rule         INTEGER,
    unowned            INTEGER NOT NULL DEFAULT 0,
    gen                INTEGER NOT NULL DEFAULT 1,
    asked_at           TEXT NOT NULL,
    clock_at           TEXT NOT NULL,
    resp_due           TEXT,
    deliv_due          TEXT,
    state              TEXT NOT NULL DEFAULT 'open',
    acked_at           TEXT,
    acked_by           TEXT,
    delivered_at       TEXT,
    delivered_by       TEXT,
    delivered_note     TEXT,                 -- «ما عندنا»: why it cannot be delivered
    proof_unchecked    INTEGER NOT NULL DEFAULT 0,
    confirmed_at       TEXT,
    confirmed_by       TEXT,
    rework             INTEGER NOT NULL DEFAULT 0,
    rework_note        TEXT,
    cancel_reason      TEXT,
    cancelled_by       TEXT,
    card_message_id    TEXT,
    leave_checked_day  TEXT,
    created_at         TEXT,
    updated_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_rrd_req_state ON rrdesk_requests(state);
CREATE INDEX IF NOT EXISTS idx_rrd_req_chan  ON rrdesk_requests(channel_id, state);
CREATE INDEX IF NOT EXISTS idx_rrd_req_card  ON rrdesk_requests(card_message_id);
CREATE TABLE IF NOT EXISTS rrdesk_ladder (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  INTEGER NOT NULL,
    step        TEXT NOT NULL,
    owner_did   TEXT,
    sent_at     TEXT,
    UNIQUE(request_id, step)
);
CREATE TABLE IF NOT EXISTS rrdesk_misses (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id      INTEGER NOT NULL,
    gen             INTEGER NOT NULL DEFAULT 1,       -- the owner generation that missed
    owner_name      TEXT,
    owner_did       TEXT,
    week            TEXT NOT NULL,
    missed_at       TEXT NOT NULL,
    eligible        INTEGER NOT NULL DEFAULT 1,
    excused_by      TEXT,
    excused_reason  TEXT,
    excused_at      TEXT,
    verdict         TEXT,
    judged_at       TEXT,
    line_message_id TEXT,
    UNIQUE(request_id, gen)
);
CREATE INDEX IF NOT EXISTS idx_rrd_miss_week ON rrdesk_misses(owner_name, week);
CREATE TABLE IF NOT EXISTS rrdesk_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    kind        TEXT NOT NULL,
    request_id  INTEGER,
    channel_id  TEXT,
    message_id  TEXT,
    actor       TEXT,
    detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_rrd_ev_req  ON rrdesk_events(request_id);
CREATE INDEX IF NOT EXISTS idx_rrd_ev_chan ON rrdesk_events(channel_id);
CREATE INDEX IF NOT EXISTS idx_rrd_ev_at   ON rrdesk_events(at);
CREATE TABLE IF NOT EXISTS rrdesk_outbox (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ref          TEXT NOT NULL UNIQUE,
    kind         TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    state        TEXT NOT NULL DEFAULT 'queued',   -- queued|claimed|done|failed
    attempts     INTEGER NOT NULL DEFAULT 0,
    next_at      TEXT,
    claimed_at   TEXT,
    done_at      TEXT,
    result_json  TEXT,
    error        TEXT,
    created_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_rrd_ob_state ON rrdesk_outbox(state, next_at);
CREATE TABLE IF NOT EXISTS rrdesk_settings (
    key    TEXT PRIMARY KEY,
    value  TEXT,
    by     TEXT,
    at     TEXT
);
CREATE TABLE IF NOT EXISTS rrdesk_files (
    message_id  TEXT PRIMARY KEY,
    channel_id  TEXT NOT NULL,
    author_id   TEXT,
    n           INTEGER NOT NULL DEFAULT 1,
    at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rrd_files_chan ON rrdesk_files(channel_id, at);
CREATE TABLE IF NOT EXISTS rrdesk_voice (
    message_id   TEXT PRIMARY KEY,
    channel_id   TEXT,
    author_id    TEXT,
    author_name  TEXT,
    at           TEXT
);
"""

# Columns added after the first live deploy go here: CREATE TABLE IF NOT EXISTS never touches
# an existing table, so each one is added once, additively (checkout/db._LATE_COLUMNS).
_LATE_COLUMNS = {}

_inited = set()
_init_lock = threading.Lock()
_state_lock = threading.Lock()          # first-final-wins for request transitions


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            for table, cols in _LATE_COLUMNS.items():
                have = {r[1] for r in cx.execute("PRAGMA table_info(%s)" % table).fetchall()}
                for col, decl in cols:
                    if col not in have:
                        cx.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, col, decl))
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()
    _settings_cache.clear()


def now():
    return datetime.datetime.now(oeng.tz())


def iso(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat(timespec="seconds")


def parse(s):
    if not s:
        return None
    if isinstance(s, datetime.datetime):
        return s
    try:
        return datetime.datetime.fromisoformat(str(s))
    except ValueError:
        return None


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
        return cur.lastrowid, cur.rowcount


def _j(v):
    return json.dumps(v, ensure_ascii=False, default=str)


def loads(s, default=None):
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ settings + latches

_settings_cache = {}
_SETTINGS_TTL = 3.0                    # seconds — a switch flipped in Discord bites within 3 s


def setting(key, default=None):
    import time
    hit = _settings_cache.get(key)
    if hit and time.time() - hit[1] < _SETTINGS_TTL:
        v = hit[0]
    else:
        r = q1("SELECT value FROM rrdesk_settings WHERE key=?", (key,))
        v = r["value"] if r else None
        _settings_cache[key] = (v, time.time())
    return default if v is None else v


def set_setting(key, value, by="", at=None):
    execute("INSERT INTO rrdesk_settings(key,value,by,at) VALUES(?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, by=excluded.by, at=excluded.at",
            (key, None if value is None else str(value), by or "", iso(at or now())))
    _settings_cache.pop(key, None)


def settings_all():
    return {r["key"]: {"value": r["value"], "by": r["by"], "at": r["at"]}
            for r in q("SELECT * FROM rrdesk_settings ORDER BY key")}


def latch(name, at=None):
    """True for the FIRST caller only (a persisted once-per-period flag)."""
    _lid, n = execute("INSERT OR IGNORE INTO rrdesk_settings(key,value,by,at) VALUES(?,?,?,?)",
                      ("latch:" + name, "1", "tick", iso(at or now())))
    return n == 1


def incr(key, by=1):
    execute("INSERT INTO rrdesk_settings(key,value,by,at) VALUES(?,?, 'counter', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=CAST(COALESCE(value,'0') AS INTEGER)+?",
            (key, str(by), iso(now()), by))
    _settings_cache.pop(key, None)
    r = q1("SELECT value FROM rrdesk_settings WHERE key=?", (key,))
    try:
        return int(r["value"])
    except (TypeError, ValueError, KeyError):
        return 0


# ------------------------------------------------------------------ events (the debug log)

def log(kind, request_id=None, channel_id=None, message_id=None, actor=None, detail=None,
        at=None):
    try:
        execute("INSERT INTO rrdesk_events(at,kind,request_id,channel_id,message_id,actor,detail)"
                " VALUES(?,?,?,?,?,?,?)",
                (iso(at or now()), kind, request_id, str(channel_id or "") or None,
                 str(message_id or "") or None, actor, _j(detail or {})))
    except Exception as e:                 # the debug log must never break the feature
        print("[rrdesk] event log failed:", kind, e)


def events(request_id=None, channel_id=None, limit=200, kinds=None):
    where, args = [], []
    if request_id is not None:
        where.append("request_id=?")
        args.append(int(request_id))
    if channel_id is not None:
        where.append("channel_id=?")
        args.append(str(channel_id))
    if kinds:
        where.append("kind IN (%s)" % ",".join("?" * len(kinds)))
        args.extend(kinds)
    sql = "SELECT * FROM rrdesk_events"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(int(limit))
    rows = q(sql, args)
    for r in rows:
        r["detail"] = loads(r.get("detail"), {})
    return rows


def count_events(kind, since):
    r = q1("SELECT COUNT(*) n FROM rrdesk_events WHERE kind=? AND at>=?", (kind, iso(since)))
    return int((r or {}).get("n") or 0)


# ------------------------------------------------------------------ rooms

def room(channel_id):
    return q1("SELECT * FROM rrdesk_rooms WHERE channel_id=?", (str(channel_id),))


def translate_on(channel_id):
    r = room(channel_id)
    return True if r is None else bool(r["translate_on"])


def set_room_translate(channel_id, on, by=""):
    execute("INSERT INTO rrdesk_rooms(channel_id,translate_on,set_by,set_at) VALUES(?,?,?,?) "
            "ON CONFLICT(channel_id) DO UPDATE SET translate_on=excluded.translate_on, "
            "set_by=excluded.set_by, set_at=excluded.set_at",
            (str(channel_id), 1 if on else 0, by or "", iso(now())))


def touch_room(channel_id):
    execute("INSERT INTO rrdesk_rooms(channel_id,last_seen_at) VALUES(?,?) "
            "ON CONFLICT(channel_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",
            (str(channel_id), iso(now())))


# ------------------------------------------------------------------ translations

def claim_translation(source_message_id, channel_id, author_id, is_bot, direction_, at=None):
    """INSERT OR IGNORE — True only for the bot copy that gets to translate this message."""
    _lid, n = execute("INSERT OR IGNORE INTO rrdesk_translations"
                      "(source_message_id,channel_id,author_id,is_bot,direction,state,created_at,"
                      "updated_at) VALUES(?,?,?,?,?, 'claimed', ?, ?)",
                      (str(source_message_id), str(channel_id), str(author_id or ""),
                       1 if is_bot else 0, direction_, iso(at or now()), iso(at or now())))
    return n == 1


def release_translation(source_message_id):
    """A failed translation gives its claim back, so an edit (or a retry) can try again."""
    execute("DELETE FROM rrdesk_translations WHERE source_message_id=? AND state='claimed'",
            (str(source_message_id),))


TR_FIELDS = ("direction", "state", "skip_reason", "our_message_ids", "chars", "source",
             "tokens_in", "tokens_out", "cost_usd", "question", "classify_json", "has_media")


def update_translation(source_message_id, **fields):
    f = {k: (_j(v) if k in ("our_message_ids", "classify_json") and not isinstance(v, str) else v)
         for k, v in fields.items() if k in TR_FIELDS}
    if not f:
        return
    f["updated_at"] = iso(now())
    sets = ",".join("%s=?" % k for k in f)
    execute("UPDATE rrdesk_translations SET %s WHERE source_message_id=?" % sets,
            list(f.values()) + [str(source_message_id)])


def translation(source_message_id):
    r = q1("SELECT * FROM rrdesk_translations WHERE source_message_id=?", (str(source_message_id),))
    if r:
        r["our_message_ids"] = loads(r.get("our_message_ids"), []) or []
        r["classify"] = loads(r.get("classify_json"), {}) or {}
    return r


def translation_by_our_message(message_id):
    """The translation whose reply message is `message_id` (the question/image buttons)."""
    mid = str(message_id or "")
    if not mid:
        return None
    for r in q("SELECT source_message_id, our_message_ids FROM rrdesk_translations "
               "WHERE our_message_ids LIKE ?", ("%" + mid + "%",)):
        if mid in (loads(r["our_message_ids"], []) or []):
            return translation(r["source_message_id"])
    return None


def add_our_message(source_message_id, message_id):
    r = translation(source_message_id)
    if not r:
        return
    ids = list(r["our_message_ids"] or [])
    if str(message_id) not in ids:
        ids.append(str(message_id))
    update_translation(source_message_id, our_message_ids=ids)


def translation_stats(since):
    rows = q("SELECT state, source, COUNT(*) n, SUM(tokens_in) ti, SUM(tokens_out) tout, "
             "SUM(cost_usd) usd FROM rrdesk_translations WHERE created_at>=? "
             "GROUP BY state, source", (iso(since),))
    out = {"done": 0, "failed": 0, "skipped": 0, "model": 0, "cache": 0, "phrase": 0,
           "tokens_in": 0, "tokens_out": 0, "usd": 0.0}
    for r in rows:
        if r["state"] in out:
            out[r["state"]] += int(r["n"] or 0)
        if r["state"] == "done" and r["source"] in ("model", "cache", "phrase"):
            out[r["source"]] += int(r["n"] or 0)
        out["tokens_in"] += int(r["ti"] or 0)
        out["tokens_out"] += int(r["tout"] or 0)
        out["usd"] += float(r["usd"] or 0)
    done = out["model"] + out["cache"] + out["phrase"]
    out["cache_hit_rate"] = round((out["cache"] + out["phrase"]) / float(done), 3) if done else None
    out["usd"] = round(out["usd"], 4)
    return out


# ------------------------------------------------------------------ cache

def cache_get(key):
    r = q1("SELECT * FROM rrdesk_cache WHERE key=?", (key,))
    if not r:
        return None
    execute("UPDATE rrdesk_cache SET hits=hits+1, last_hit_at=? WHERE key=?", (iso(now()), key))
    return loads(r["result_json"], None)


def cache_put(key, direction_, result):
    execute("INSERT OR IGNORE INTO rrdesk_cache(key,direction,result_json,created_at) "
            "VALUES(?,?,?,?)", (key, direction_, _j(result), iso(now())))


# ------------------------------------------------------------------ files + voice

def record_file(message_id, channel_id, author_id, n, at):
    execute("INSERT OR IGNORE INTO rrdesk_files(message_id,channel_id,author_id,n,at) "
            "VALUES(?,?,?,?,?)", (str(message_id), str(channel_id), str(author_id or ""),
                                  int(n or 1), iso(at)))


def files_since(channel_ids, since, exclude_authors=()):
    """Files posted in these channels since `since`, NOT counting Sam's own attachments."""
    ids = [str(c) for c in (channel_ids or ()) if c]
    if not ids:
        return 0
    ex = [str(a) for a in (exclude_authors or ()) if a] or ["-"]
    r = q1("SELECT COUNT(*) n FROM rrdesk_files WHERE channel_id IN (%s) AND at>=? "
           "AND IFNULL(author_id,'') NOT IN (%s)" % (",".join("?" * len(ids)), ",".join("?" * len(ex))),
           ids + [iso(since)] + ex)
    return int((r or {}).get("n") or 0)


def record_voice(message_id, channel_id, author_id, author_name, at):
    _lid, n = execute("INSERT OR IGNORE INTO rrdesk_voice(message_id,channel_id,author_id,"
                      "author_name,at) VALUES(?,?,?,?,?)",
                      (str(message_id), str(channel_id), str(author_id or ""),
                       author_name or "", iso(at)))
    return n == 1


def voice_counts(since, until):
    return {r["author_id"]: int(r["n"]) for r in
            q("SELECT author_id, COUNT(*) n FROM rrdesk_voice WHERE at>=? AND at<? "
              "GROUP BY author_id", (iso(since), iso(until)))}


# ------------------------------------------------------------------ requests

REQ_FIELDS = ("ticket_seq", "ticket_code", "lid", "text", "summary_en", "summary_ar",
              "asks_json", "urgent", "urgent_why", "path", "confidence", "owner_did",
              "owner_name", "owner_rule", "unowned", "gen", "clock_at", "resp_due", "deliv_due",
              "state", "acked_at", "acked_by", "delivered_at", "delivered_by", "delivered_note",
              "proof_unchecked",
              "confirmed_at", "confirmed_by", "rework", "rework_note", "cancel_reason",
              "cancelled_by", "card_message_id", "leave_checked_day")


def _req(r):
    if r:
        r["asks"] = loads(r.get("asks_json"), []) or []
    return r


def open_request(source_message_id, channel_id, asked_at, path, fields):
    """INSERT OR IGNORE. Returns (request, created) — created is False when this message is
    already a request (a double tick, a second bot copy, a 📌 after /rr-ask)."""
    f = {k: v for k, v in (fields or {}).items() if k in REQ_FIELDS}
    if isinstance(f.get("asks_json"), (list, tuple)):
        f["asks_json"] = _j(list(f["asks_json"]))
    f.setdefault("clock_at", iso(asked_at))
    cols = ["source_message_id", "channel_id", "asked_at", "path", "created_at", "updated_at"]
    vals = [str(source_message_id), str(channel_id), iso(asked_at), path, iso(now()), iso(now())]
    for k, v in f.items():
        if k == "path":
            continue
        cols.append(k)
        vals.append(iso(v) if isinstance(v, datetime.datetime) else v)
    _lid, n = execute("INSERT OR IGNORE INTO rrdesk_requests(%s) VALUES(%s)"
                      % (",".join(cols), ",".join("?" * len(cols))), vals)
    return request_by_source(source_message_id), n == 1


def request(rid):
    return _req(q1("SELECT * FROM rrdesk_requests WHERE id=?", (int(rid),)))


def request_by_source(source_message_id):
    return _req(q1("SELECT * FROM rrdesk_requests WHERE source_message_id=?",
                   (str(source_message_id),)))


def request_by_card(message_id):
    return _req(q1("SELECT * FROM rrdesk_requests WHERE card_message_id=?", (str(message_id),)))


def update_request(rid, **fields):
    f = {k: (iso(v) if isinstance(v, datetime.datetime) else v)
         for k, v in fields.items() if k in REQ_FIELDS}
    if not f:
        return
    f["updated_at"] = iso(now())
    sets = ",".join("%s=?" % k for k in f)
    execute("UPDATE rrdesk_requests SET %s WHERE id=?" % sets, list(f.values()) + [int(rid)])


def move_request(rid, allowed_from, new_state, **fields):
    """Conditional UPDATE under a lock — first final answer wins. Returns (moved, row)."""
    allowed = list(allowed_from)
    f = {k: (iso(v) if isinstance(v, datetime.datetime) else v)
         for k, v in fields.items() if k in REQ_FIELDS}
    f["state"] = new_state
    f["updated_at"] = iso(now())
    sets = ",".join("%s=?" % k for k in f)
    with _state_lock:
        _lid, n = execute("UPDATE rrdesk_requests SET %s WHERE id=? AND state IN (%s)"
                          % (sets, ",".join("?" * len(allowed))),
                          list(f.values()) + [int(rid)] + allowed)
    return n == 1, request(rid)


def live_requests(channel_id=None):
    if channel_id is None:
        rows = q("SELECT * FROM rrdesk_requests WHERE state IN ('open','acknowledged','delivered')"
                 " ORDER BY asked_at")
    else:
        rows = q("SELECT * FROM rrdesk_requests WHERE channel_id=? AND "
                 "state IN ('open','acknowledged','delivered') ORDER BY asked_at",
                 (str(channel_id),))
    return [_req(r) for r in rows]


def requests_in(since, until):
    return [_req(r) for r in q("SELECT * FROM rrdesk_requests WHERE asked_at>=? AND asked_at<? "
                               "ORDER BY asked_at", (iso(since), iso(until)))]


def requests_for_channel(channel_id):
    return [_req(r) for r in q("SELECT * FROM rrdesk_requests WHERE channel_id=? ORDER BY asked_at",
                               (str(channel_id),))]


def recent_requests(limit=200):
    return [_req(r) for r in q("SELECT * FROM rrdesk_requests ORDER BY id DESC LIMIT ?",
                               (int(limit),))]


# ------------------------------------------------------------------ ladder

def ladder_sent(rid):
    return {r["step"] for r in q("SELECT step FROM rrdesk_ladder WHERE request_id=?", (int(rid),))}


def ladder_rows(rid):
    return q("SELECT * FROM rrdesk_ladder WHERE request_id=? ORDER BY id", (int(rid),))


def record_step(rid, step, owner_did, at):
    _lid, n = execute("INSERT OR IGNORE INTO rrdesk_ladder(request_id,step,owner_did,sent_at) "
                      "VALUES(?,?,?,?)", (int(rid), step, owner_did or "", iso(at)))
    return n == 1


# ------------------------------------------------------------------ misses

def record_miss(rid, gen, owner_name, owner_did, week, at, eligible=True):
    _lid, n = execute("INSERT OR IGNORE INTO rrdesk_misses(request_id,gen,owner_name,owner_did,"
                      "week,missed_at,eligible) VALUES(?,?,?,?,?,?,?)",
                      (int(rid), int(gen or 1), owner_name or "", owner_did or "", week, iso(at),
                       1 if eligible else 0))
    return n == 1


def miss(rid, gen=None):
    if gen is None:
        return q1("SELECT * FROM rrdesk_misses WHERE request_id=? ORDER BY gen DESC LIMIT 1",
                  (int(rid),))
    return q1("SELECT * FROM rrdesk_misses WHERE request_id=? AND gen=?", (int(rid), int(gen)))


def misses_for(rid):
    return q("SELECT * FROM rrdesk_misses WHERE request_id=? ORDER BY gen", (int(rid),))


def miss_by_line(message_id):
    return q1("SELECT * FROM rrdesk_misses WHERE line_message_id=?", (str(message_id),))


def set_miss(rid, gen, **fields):
    allowed = ("excused_by", "excused_reason", "excused_at", "verdict", "judged_at",
               "line_message_id")
    f = {k: iso(v) if isinstance(v, datetime.datetime) else v
         for k, v in fields.items() if k in allowed}
    if not f:
        return 0
    sets = ",".join("%s=?" % k for k in f)
    _lid, n = execute("UPDATE rrdesk_misses SET %s WHERE request_id=? AND gen=?" % sets,
                      list(f.values()) + [int(rid), int(gen or 1)])
    return n


def excuse_miss(rid, gen, by, reason, at):
    """Mercy: an excused miss stops counting. A warning already issued is forgiven only
    through the ops appeal chain — excusing here never touches ops_warnings."""
    _lid, n = execute("UPDATE rrdesk_misses SET excused_by=?, excused_reason=?, excused_at=? "
                      "WHERE request_id=? AND gen=? AND excused_at IS NULL",
                      (by, reason, iso(at), int(rid), int(gen or 1)))
    return n == 1


def misses_in_week(owner_name, week):
    return q("SELECT * FROM rrdesk_misses WHERE owner_name=? AND week=? AND eligible=1 "
             "AND excused_at IS NULL ORDER BY missed_at, request_id", (owner_name, week))


def unjudged_misses():
    return q("SELECT * FROM rrdesk_misses WHERE judged_at IS NULL AND eligible=1 "
             "ORDER BY missed_at, request_id")


def misses_between(since, until):
    return q("SELECT * FROM rrdesk_misses WHERE missed_at>=? AND missed_at<? ORDER BY missed_at",
             (iso(since), iso(until)))


# ------------------------------------------------------------------ outbox

def enqueue(ref, kind, payload, at=None):
    """INSERT OR IGNORE by ref — the same side effect can never be queued twice."""
    _lid, n = execute("INSERT OR IGNORE INTO rrdesk_outbox(ref,kind,payload_json,state,next_at,"
                      "created_at) VALUES(?,?,?, 'queued', ?, ?)",
                      (ref, kind, _j(payload), iso(at or now()), iso(at or now())))
    return n == 1


def outbox(ref):
    r = q1("SELECT * FROM rrdesk_outbox WHERE ref=?", (ref,))
    if r:
        r["payload"] = loads(r["payload_json"], {})
        r["result"] = loads(r.get("result_json"), {}) or {}
    return r


def outbox_due(at, limit=20):
    rows = q("SELECT * FROM rrdesk_outbox WHERE state='queued' AND (next_at IS NULL OR next_at<=?) "
             "ORDER BY id LIMIT ?", (iso(at), int(limit)))
    stale = iso(at - datetime.timedelta(minutes=STALE_CLAIM_MIN))
    rows += q("SELECT * FROM rrdesk_outbox WHERE state='claimed' AND claimed_at<? ORDER BY id "
              "LIMIT ?", (stale, int(limit)))
    for r in rows:
        r["payload"] = loads(r["payload_json"], {})
    return rows


STALE_CLAIM_MIN = 30


def claim_outbox(oid, at):
    """Atomic: exactly one bot copy wins a row. A claim older than 30 minutes is a crashed
    worker and may be taken over (long enough that a slow, rate-limited send is not re-sent)."""
    stale = iso(at - datetime.timedelta(minutes=STALE_CLAIM_MIN))
    _lid, n = execute("UPDATE rrdesk_outbox SET state='claimed', claimed_at=?, attempts=attempts+1"
                      " WHERE id=? AND (state='queued' OR (state='claimed' AND claimed_at<?))",
                      (iso(at), int(oid), stale))
    return n == 1


def finish_outbox(oid, result, at):
    execute("UPDATE rrdesk_outbox SET state='done', done_at=?, result_json=?, error=NULL "
            "WHERE id=?", (iso(at), _j(result or {}), int(oid)))


BACKOFF_MIN = (1, 5, 15, 60)
MAX_ATTEMPTS = 6


def fail_outbox(oid, error, at):
    r = q1("SELECT attempts FROM rrdesk_outbox WHERE id=?", (int(oid),))
    attempts = int((r or {}).get("attempts") or 1)
    if attempts >= MAX_ATTEMPTS:
        execute("UPDATE rrdesk_outbox SET state='failed', error=? WHERE id=?",
                (str(error)[:500], int(oid)))
        return "failed"
    wait = BACKOFF_MIN[min(attempts - 1, len(BACKOFF_MIN) - 1)]
    execute("UPDATE rrdesk_outbox SET state='queued', next_at=?, error=? WHERE id=?",
            (iso(at + datetime.timedelta(minutes=wait)), str(error)[:500], int(oid)))
    return "retry"


def outbox_backlog():
    r = q1("SELECT COUNT(*) n FROM rrdesk_outbox WHERE state IN ('queued','claimed')")
    f = q1("SELECT COUNT(*) n FROM rrdesk_outbox WHERE state='failed'")
    return int((r or {}).get("n") or 0), int((f or {}).get("n") or 0)


def janitor(at):
    cut = iso(at - datetime.timedelta(days=30))
    execute("DELETE FROM rrdesk_outbox WHERE state='done' AND done_at<?", (cut,))
    execute("DELETE FROM rrdesk_cache WHERE COALESCE(last_hit_at, created_at)<?",
            (iso(at - datetime.timedelta(days=120)),))
