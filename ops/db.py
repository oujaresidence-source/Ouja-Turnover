# -*- coding: utf-8 -*-
"""
ops.db — «نظام الالتزام» storage, inside the SAME brain.db file every other package uses.

Connection rules are NOT re-invented here: brain.db.connect() already encodes the fixes that
cost a live outage in June — no WAL (its shared-memory file is unsupported on the Railway
volume), journal_mode=DELETE, ordinary locking, and one short-lived connection per call via
`with closing(connect())`. Read brain/db.py's docstring before changing anything here.

TWO RULES ARE ENFORCED BY THE SCHEMA, NOT BY CAREFUL CODE
  1. One obligation can never produce two warnings — UNIQUE(obligation_id) on ops_warnings.
     If the ladder tick runs twice, or Railway restarts mid-tick, the second INSERT fails.
  2. One obligation exists per (kind, employee, week) — UNIQUE(kind, employee, period_key).
Both are the same structural approach the decor package uses for the owner's intake rule:
a promise a future edit cannot quietly break.

Every table is prefixed `ops_`. The spec named them `obligations` / `warnings`; in a database
shared with brain_*, schedule_*, decor_* and finance tables, a table called `warnings` is an
accident waiting to happen.
"""

import datetime
import json
import secrets
import threading
from contextlib import closing, contextmanager

from brain import db as _bdb
from . import engine

SCHEMA = """
CREATE TABLE IF NOT EXISTS ops_obligations (
    id            TEXT PRIMARY KEY,          -- 'wr_<employee>_<2026-W30>'
    kind          TEXT NOT NULL,             -- 'wr' = weekly report
    employee      TEXT NOT NULL,
    employee_did  TEXT,                      -- Discord id, '' when we cannot reach them
    period_key    TEXT NOT NULL,             -- '2026-W30'
    due_at        TEXT NOT NULL,             -- ISO, Riyadh offset
    status        TEXT NOT NULL DEFAULT 'pending',   -- pending|done|missed|waived|excused
    done_at       TEXT,
    waived_by     TEXT,
    waived_reason TEXT,
    created_at    TEXT,
    UNIQUE(kind, employee, period_key)
);
CREATE TABLE IF NOT EXISTS ops_warnings (
    id             TEXT PRIMARY KEY,
    employee       TEXT NOT NULL,
    employee_did   TEXT,
    obligation_id  TEXT NOT NULL UNIQUE,     -- <<< one obligation, at most one warning, ever
    month_key      TEXT NOT NULL,            -- '2026-07'
    issued_at      TEXT NOT NULL,
    reason_ar      TEXT,
    status         TEXT NOT NULL DEFAULT 'active',   -- active|voided|retired
    voided_by      TEXT,
    voided_reason  TEXT,
    voided_at      TEXT,
    appeal_token   TEXT UNIQUE,
    retired_through TEXT                      -- the clean streak that earned it back
);
CREATE TABLE IF NOT EXISTS ops_appeals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    warning_id     TEXT NOT NULL,
    opened_at      TEXT NOT NULL,
    employee_text  TEXT,
    evidence_json  TEXT DEFAULT '[]',
    stage          TEXT NOT NULL DEFAULT 's1',       -- s1 أصيل | s2 ريم | s3 فيصل | closed
    stage_due_at   TEXT,
    decisions_json TEXT NOT NULL DEFAULT '[]',
    outcome        TEXT                               -- accepted|rejected
);
CREATE TABLE IF NOT EXISTS ops_free_passes (
    employee     TEXT NOT NULL,
    quarter_key  TEXT NOT NULL,
    used_at      TEXT,
    warning_id   TEXT,
    obligation_id TEXT,
    PRIMARY KEY(employee, quarter_key)
);
CREATE TABLE IF NOT EXISTS ops_commission_ledger (
    employee       TEXT NOT NULL,
    month_key      TEXT NOT NULL,
    warnings_count INTEGER NOT NULL DEFAULT 0,
    multiplier     REAL NOT NULL DEFAULT 1.0,
    computed_at    TEXT,
    PRIMARY KEY(employee, month_key)
);
-- Discord ids the owner typed in /compliance (or set with «!ouja اربط»). This is NOT a second
-- employee list: the PEOPLE still come from the Employee Calendar, this only remembers how to
-- reach one of them. It wins over assignments.json, which is import-generated and has already
-- been wrong once (عهود missing, مآثر spelled ماذر).
CREATE TABLE IF NOT EXISTS ops_identity (
    employee   TEXT PRIMARY KEY,
    discord_id TEXT,
    updated_by TEXT,
    updated_at TEXT
);
-- which ladder steps actually went out, and by which road. This is also how we know whether
-- a person is REACHABLE: a warning is refused for somebody every path failed on.
CREATE TABLE IF NOT EXISTS ops_ladder_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    obligation_id TEXT NOT NULL,
    employee      TEXT,
    level         TEXT NOT NULL,             -- L1..L4 | issue
    path          TEXT NOT NULL,             -- dm | channel | lead | failed | dryrun
    detail        TEXT,
    sent_at       TEXT NOT NULL,
    UNIQUE(obligation_id, level)
);
-- DRY-RUN IS A FIRST-CLASS MODE: everything the live system WOULD have done lands here,
-- readable at /compliance, while ops_warnings stays empty.
CREATE TABLE IF NOT EXISTS ops_dryrun_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    at         TEXT NOT NULL,
    kind       TEXT NOT NULL,               -- ladder | verdict | warning | commission | summary
    employee   TEXT,
    period_key TEXT,
    detail     TEXT,
    payload    TEXT
);
-- ===================== PHASE 2 «القفل» — turnover nudges =====================
-- Split the same way Phase 1 splits obligations/ladder_log: ops_nudge_items is the LIVE state
-- of one turnover (crucially the id of the ONE message we keep editing), ops_nudges is the
-- append-only record of which levels actually went out. Keeping message_id in the database
-- rather than in memory is the lesson from the Musaed duplicate-spam incident: a redeploy
-- must not make the bot forget it already has a message open and start a second one.
CREATE TABLE IF NOT EXISTS ops_nudge_items (
    work_item_id      TEXT PRIMARY KEY,     -- '<listing id>:YYYY-MM-DD' (the stable turnover key)
    unit              TEXT,
    date              TEXT,
    employee          TEXT,
    employee_did      TEXT,
    checkin_at        TEXT,                 -- the GUEST's arrival, the anchor for every step
    channel           TEXT,                 -- where the one message lives ('dm' or a channel name)
    channel_id        TEXT,
    message_id        TEXT,                 -- <<< the ONE message, edited in place
    last_edit_at      TEXT,
    acked_at          TEXT,
    acked_by          TEXT,
    problem_at        TEXT,
    reassigned_to     TEXT,
    reassigned_reason TEXT,
    closed_at         TEXT,
    created_at        TEXT
);
CREATE TABLE IF NOT EXISTS ops_nudges (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    work_item_id  TEXT NOT NULL,
    employee      TEXT,
    employee_did  TEXT,
    level         TEXT NOT NULL,            -- L1..L5
    sent_at       TEXT NOT NULL,
    path          TEXT,                     -- dm | channel | lead | ops | failed | dryrun
    acked_at      TEXT,
    channel       TEXT,
    message_id    TEXT,
    reassigned_to     TEXT,
    reassigned_reason TEXT,
    UNIQUE(work_item_id, level)
);
CREATE INDEX IF NOT EXISTS idx_ops_nudge_item ON ops_nudges(work_item_id);
CREATE INDEX IF NOT EXISTS idx_ops_nudge_msg  ON ops_nudge_items(message_id);
CREATE INDEX IF NOT EXISTS idx_ops_ob_period  ON ops_obligations(period_key);
CREATE INDEX IF NOT EXISTS idx_ops_ob_emp     ON ops_obligations(employee, period_key);
CREATE INDEX IF NOT EXISTS idx_ops_warn_emp   ON ops_warnings(employee, status);
CREATE INDEX IF NOT EXISTS idx_ops_appeal_w   ON ops_appeals(warning_id);
CREATE INDEX IF NOT EXISTS idx_ops_ladder_ob  ON ops_ladder_log(obligation_id);
CREATE INDEX IF NOT EXISTS idx_ops_dry_at     ON ops_dryrun_log(at);
"""

_inited = set()
_init_lock = threading.Lock()


def _ensure():
    path = _bdb.db_path()
    if path in _inited:
        return
    with _init_lock:                 # two threads racing the first init would run SCHEMA twice
        if path in _inited:
            return
        with closing(_bdb.connect()) as cx:
            cx.executescript(SCHEMA)
            cx.commit()
        _inited.add(path)


def reset_init_cache():
    _inited.clear()


def now_dt():
    return datetime.datetime.now(engine.tz())


def now_iso():
    return now_dt().isoformat(timespec="seconds")


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
    _ensure()
    with closing(_bdb.connect()) as cx:
        cur = cx.execute(sql, args)
        cx.commit()
        return cur.lastrowid


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


def counts():
    """Row counts per table — the tests use this to prove that a dry-run tick, or a guest of
    any other feature, creates nothing here."""
    out = {}
    for t in ("ops_obligations", "ops_warnings", "ops_appeals", "ops_free_passes",
              "ops_commission_ledger", "ops_ladder_log", "ops_dryrun_log", "ops_identity",
              "ops_nudge_items", "ops_nudges"):
        out[t] = (q1("SELECT COUNT(*) c FROM %s" % t) or {}).get("c", 0)
    return out


# ------------------------------------------------------------------ obligations

def obligation_id(kind, employee, period_key):
    return "%s_%s_%s" % (kind, employee, period_key)


def ensure_obligation(kind, employee, employee_did, period_key, due_at):
    """Create this week's obligation if it is not there yet, and return it.

    INSERT OR IGNORE + read-back: the UNIQUE key makes a double tick harmless, and the
    read-back means the caller always gets the row that actually exists (not the one it
    tried to write)."""
    oid = obligation_id(kind, employee, period_key)
    execute("INSERT OR IGNORE INTO ops_obligations"
            "(id,kind,employee,employee_did,period_key,due_at,status,created_at)"
            " VALUES(?,?,?,?,?,?, 'pending', ?)",
            (oid, kind, employee, employee_did or "", period_key,
             due_at if isinstance(due_at, str) else due_at.isoformat(timespec="seconds"),
             now_iso()))
    # keep the Discord id fresh without disturbing status/history
    execute("UPDATE ops_obligations SET employee_did=? WHERE id=? AND IFNULL(employee_did,'')<>?",
            (employee_did or "", oid, employee_did or ""))
    return obligation(oid)


def obligation(oid):
    return q1("SELECT * FROM ops_obligations WHERE id=?", (oid,))


def obligations_for_period(period_key, kind="wr"):
    return q("SELECT * FROM ops_obligations WHERE period_key=? AND kind=? ORDER BY employee",
             (period_key, kind))


def obligations_for_employee(employee, kind="wr", limit=52):
    return q("SELECT * FROM ops_obligations WHERE employee=? AND kind=? "
             "ORDER BY period_key DESC LIMIT ?", (employee, kind, int(limit)))


def set_status(oid, status, done_at=None, waived_by=None, waived_reason=None):
    execute("UPDATE ops_obligations SET status=?, done_at=COALESCE(?,done_at), "
            "waived_by=COALESCE(?,waived_by), waived_reason=COALESCE(?,waived_reason) WHERE id=?",
            (status, done_at, waived_by, waived_reason, oid))
    return obligation(oid)


def prior_misses(employee, quarter_key, kind="wr", before_period=None):
    """Real misses this quarter — obligations that actually produced a warning. A week
    covered by leave or an excuse is not a miss and must not spend the free pass."""
    rows = q("SELECT o.period_key FROM ops_obligations o "
             "JOIN ops_warnings w ON w.obligation_id = o.id "
             "WHERE o.employee=? AND o.kind=? AND o.status='missed'", (employee, kind))
    n = 0
    for r in rows:
        try:
            mon = engine.week_monday(r["period_key"])
        except ValueError:
            continue
        if engine.quarter_key(mon) != quarter_key:
            continue
        if before_period and r["period_key"] >= before_period:
            continue
        n += 1
    return n


# ------------------------------------------------------------------ who is who

def identity_map():
    """{employee name -> discord id} as typed by the owner.

    A row with an EMPTY id is kept on purpose and means «this person has no way to be
    reached», which suppresses whatever assignments.json says. Emptying the box in
    /compliance has to actually stick — silently falling back to the number the owner just
    deleted would put it straight back on screen and look broken. A true revert-to-file is
    clear_identity(), which removes the row entirely."""
    return {r["employee"]: (r["discord_id"] or "")
            for r in q("SELECT employee, discord_id FROM ops_identity")}


def set_identity(employee, discord_id, by=""):
    execute("INSERT INTO ops_identity(employee,discord_id,updated_by,updated_at)"
            " VALUES(?,?,?,?) ON CONFLICT(employee) DO UPDATE SET "
            "discord_id=excluded.discord_id, updated_by=excluded.updated_by, "
            "updated_at=excluded.updated_at",
            (employee, (discord_id or "").strip(), by or "", now_iso()))
    return q1("SELECT * FROM ops_identity WHERE employee=?", (employee,))


def clear_identity(employee):
    execute("DELETE FROM ops_identity WHERE employee=?", (employee,))


# ------------------------------------------------------------------ the ladder log

def record_ladder(obligation_id_, employee, level, path, detail=""):
    """Remember that this step went out (and by which road). UNIQUE(obligation, level) means
    a retry can never double-send: the second INSERT is ignored."""
    execute("INSERT OR IGNORE INTO ops_ladder_log"
            "(obligation_id,employee,level,path,detail,sent_at) VALUES(?,?,?,?,?,?)",
            (obligation_id_, employee, level, path, detail or "", now_iso()))


def set_ladder_path(obligation_id_, level, path, detail=""):
    """bot.py calls this once it knows which road actually worked. record_ladder() claims the
    step the moment it is handed over (so a slow or failing Discord can never cause the same
    level to go out twice); this fills in the truth afterwards."""
    execute("UPDATE ops_ladder_log SET path=?, detail=? WHERE obligation_id=? AND level=?",
            (path, (detail or "")[:400], obligation_id_, level))


def sent_levels(obligation_id_):
    return [r["level"] for r in
            q("SELECT level FROM ops_ladder_log WHERE obligation_id=?", (obligation_id_,))]


def ladder_rows(obligation_id_):
    return q("SELECT * FROM ops_ladder_log WHERE obligation_id=? ORDER BY id", (obligation_id_,))


def is_reachable(obligation_id_, employee_did, dry=False):
    """Did we actually get a message to this person for this obligation?

    No Discord id at all -> no. In dry-run nothing is really sent, so a known id counts as
    reachable (otherwise the dry-run log would accuse everybody of being unreachable and
    teach us nothing). Live: reachable unless every single attempt failed."""
    if not (employee_did or "").strip():
        return False
    if dry:
        return True
    rows = ladder_rows(obligation_id_)
    if not rows:
        return True                    # nothing attempted yet — not evidence of a dead line
    # 'failed' is the only negative signal. 'queued' means handed to Discord and not yet
    # reported back, which is not evidence of a dead line either.
    return any(r["path"] != "failed" for r in rows)


def unreachable_report(limit=200):
    """People the system could not reach — a silently unreachable employee is an invisible
    hole, so /compliance shows this at the top."""
    rows = q("SELECT employee, COUNT(*) failures, MAX(sent_at) last_at FROM ops_ladder_log "
             "WHERE path='failed' GROUP BY employee ORDER BY failures DESC LIMIT ?", (int(limit),))
    no_id = q("SELECT DISTINCT employee FROM ops_obligations "
              "WHERE IFNULL(employee_did,'')='' ORDER BY employee")
    return {"delivery_failures": rows, "no_discord_id": [r["employee"] for r in no_id]}


# ------------------------------------------------------------------ warnings

def issue_warning(ob, reason_ar, at=None):
    """THE ONLY INSERT INTO ops_warnings IN THIS PROJECT.

    Callable only from the deadline path, never from a route: no human can accuse anybody.
    Returns the warning, or the EXISTING one if this obligation already produced one — the
    UNIQUE(obligation_id) constraint makes 'at most one warning, ever' a fact about the
    database rather than a promise about the code."""
    existing = warning_for_obligation(ob["id"])
    if existing:
        return existing
    at = at or now_iso()
    wid = "wn_%s_%s" % (ob["employee"], ob["period_key"])
    token = secrets.token_urlsafe(24)
    try:
        execute("INSERT INTO ops_warnings"
                "(id,employee,employee_did,obligation_id,month_key,issued_at,reason_ar,"
                " status,appeal_token) VALUES(?,?,?,?,?,?,?, 'active', ?)",
                (wid, ob["employee"], ob.get("employee_did") or "", ob["id"],
                 engine.month_key(at[:10]), at, reason_ar or "", token))
    except Exception:
        # lost a race with a concurrent tick — the other one's row is the truth
        return warning_for_obligation(ob["id"])
    return warning(wid)


def warning(wid):
    return q1("SELECT * FROM ops_warnings WHERE id=?", (wid,))


def warning_for_obligation(oid):
    return q1("SELECT * FROM ops_warnings WHERE obligation_id=?", (oid,))


def warning_by_token(token):
    if not (token or "").strip():
        return None
    return q1("SELECT * FROM ops_warnings WHERE appeal_token=?", (token,))


def warnings_for(employee, status=None):
    if status:
        return q("SELECT * FROM ops_warnings WHERE employee=? AND status=? ORDER BY issued_at",
                 (employee, status))
    return q("SELECT * FROM ops_warnings WHERE employee=? ORDER BY issued_at", (employee,))


def all_warnings(limit=500):
    return q("SELECT * FROM ops_warnings ORDER BY issued_at DESC LIMIT ?", (int(limit),))


def active_warning_count(employee):
    return len(warnings_for(employee, "active"))


def void_warning(wid, by, reason):
    """Forgiveness. The employee's commission is recomputed by the caller IMMEDIATELY —
    a voided warning that still shows as money lost is worse than no appeal at all."""
    execute("UPDATE ops_warnings SET status='voided', voided_by=?, voided_reason=?, voided_at=? "
            "WHERE id=? AND status='active'", (by or "", reason or "", now_iso(), wid))
    return warning(wid)


def retirement_claimed(employee, through):
    """Has this exact clean streak already earned a warning back?

    Without this the streak stays 4-weeks-long forever and the 5-minute loop would retire
    another warning on every single tick — the whole ledger wiped out in an hour."""
    if not through:
        return False
    return q1("SELECT 1 x FROM ops_warnings WHERE employee=? AND retired_through=?",
              (employee, through)) is not None


def retire_oldest_active(employee, through=None):
    """4 clean weeks -> the OLDEST active warning is earned back. Once per streak."""
    if retirement_claimed(employee, through):
        return None
    rows = warnings_for(employee, "active")
    if not rows:
        return None
    oldest = sorted(rows, key=lambda w: w.get("issued_at") or "")[0]
    execute("UPDATE ops_warnings SET status='retired', voided_by='system', voided_reason=?, "
            "voided_at=?, retired_through=? WHERE id=? AND status='active'",
            ("٤ أسابيع نظيفة متتالية%s" % (" حتى %s" % through if through else ""),
             now_iso(), through, oldest["id"]))
    return warning(oldest["id"])


# ------------------------------------------------------------------ free passes

def free_pass_used(employee, quarter_key):
    return q1("SELECT * FROM ops_free_passes WHERE employee=? AND quarter_key=?",
              (employee, quarter_key)) is not None


def spend_free_pass(employee, quarter_key, obligation_id_=None):
    execute("INSERT OR IGNORE INTO ops_free_passes"
            "(employee,quarter_key,used_at,obligation_id) VALUES(?,?,?,?)",
            (employee, quarter_key, now_iso(), obligation_id_))
    return q1("SELECT * FROM ops_free_passes WHERE employee=? AND quarter_key=?",
              (employee, quarter_key))


# ------------------------------------------------------------------ commission

def recompute_commission(employee, month_key=None):
    """Recomputed from the CURRENT active warnings every time, never incremented — so a
    voided warning restores the money the instant the appeal is accepted."""
    mk = month_key or engine.month_key(now_dt().date())
    n = active_warning_count(employee)
    mult = engine.compute_multiplier(n)
    execute("INSERT INTO ops_commission_ledger(employee,month_key,warnings_count,multiplier,computed_at)"
            " VALUES(?,?,?,?,?) ON CONFLICT(employee,month_key) DO UPDATE SET "
            "warnings_count=excluded.warnings_count, multiplier=excluded.multiplier, "
            "computed_at=excluded.computed_at",
            (employee, mk, n, mult, now_iso()))
    return {"employee": employee, "month_key": mk, "warnings_count": n, "multiplier": mult}


def commission(employee, month_key):
    return q1("SELECT * FROM ops_commission_ledger WHERE employee=? AND month_key=?",
              (employee, month_key))


def commission_month(month_key):
    return q("SELECT * FROM ops_commission_ledger WHERE month_key=? ORDER BY employee",
             (month_key,))


# ------------------------------------------------------------------ appeals

def open_appeal(warning_id, employee_text, evidence=None, sla_hours=24):
    """One appeal per warning. Re-opening returns the existing one instead of stacking."""
    ex = appeal_for_warning(warning_id)
    if ex:
        return ex
    opened = now_dt()
    execute("INSERT INTO ops_appeals(warning_id,opened_at,employee_text,evidence_json,stage,"
            "stage_due_at,decisions_json) VALUES(?,?,?,?,'s1',?,'[]')",
            (warning_id, opened.isoformat(timespec="seconds"), (employee_text or "")[:4000],
             json.dumps(evidence or [], ensure_ascii=False),
             engine.appeal_due_at(opened, sla_hours).isoformat(timespec="seconds")))
    return appeal_for_warning(warning_id)


def appeal_for_warning(warning_id):
    return q1("SELECT * FROM ops_appeals WHERE warning_id=? ORDER BY id DESC LIMIT 1",
              (warning_id,))


def appeal(aid):
    return q1("SELECT * FROM ops_appeals WHERE id=?", (int(aid),))


def open_appeals():
    return q("SELECT * FROM ops_appeals WHERE stage<>'closed' ORDER BY stage_due_at")


def appeal_decisions(a):
    try:
        return json.loads(a.get("decisions_json") or "[]")
    except Exception:
        return []


def add_decision(aid, stage, action, by, reason):
    """Append-only. Every stage transition, accept, reject and auto-escalation is written
    here so the employee can be shown WHY at each step."""
    a = appeal(aid)
    if not a:
        return None
    hist = appeal_decisions(a)
    hist.append({"stage": stage, "action": action, "by": by or "",
                 "reason": (reason or "")[:1000], "at": now_iso()})
    execute("UPDATE ops_appeals SET decisions_json=? WHERE id=?",
            (json.dumps(hist, ensure_ascii=False), int(aid)))
    return appeal(aid)


def move_appeal(aid, stage, sla_hours=24, outcome=None):
    due = (engine.appeal_due_at(now_dt(), sla_hours).isoformat(timespec="seconds")
           if stage != "closed" else None)
    execute("UPDATE ops_appeals SET stage=?, stage_due_at=?, outcome=COALESCE(?,outcome) WHERE id=?",
            (stage, due, outcome, int(aid)))
    return appeal(aid)


# ================================================================== PHASE 2 «القفل»

def nudge_item(work_item_id):
    return q1("SELECT * FROM ops_nudge_items WHERE work_item_id=?", (work_item_id,))


def nudge_item_by_message(message_id):
    """The button click arrives with a message id and nothing else. This is how a press still
    works after a redeploy: the link lives in the database, not in a view registered in
    memory."""
    if not message_id:
        return None
    return q1("SELECT * FROM ops_nudge_items WHERE message_id=?", (str(message_id),))


def ensure_nudge_item(work_item_id, unit, date, employee, employee_did, checkin_at):
    """Open the turnover's row once, then keep its live fields fresh. Never resets the
    message id, the ack, or a reassignment — those are the state we are protecting."""
    execute("INSERT OR IGNORE INTO ops_nudge_items"
            "(work_item_id,unit,date,employee,employee_did,checkin_at,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (work_item_id, unit, date, employee, employee_did or "",
             checkin_at if isinstance(checkin_at, str) else checkin_at.isoformat(timespec="seconds"),
             now_iso()))
    execute("UPDATE ops_nudge_items SET unit=?, checkin_at=?, employee=COALESCE(NULLIF(?,''),employee),"
            " employee_did=COALESCE(NULLIF(?,''),employee_did) WHERE work_item_id=?",
            (unit,
             checkin_at if isinstance(checkin_at, str) else checkin_at.isoformat(timespec="seconds"),
             employee or "", employee_did or "", work_item_id))
    return nudge_item(work_item_id)


def _stamp(at=None):
    """The TICK's clock, not the wall clock. The L3 countdown refresh compares this value
    against the tick's `now`; stamping it from a different clock makes the two disagree and
    the message re-edits on every single pass."""
    if at is None:
        return now_iso()
    return at if isinstance(at, str) else at.isoformat(timespec="seconds")


def set_nudge_message(work_item_id, channel, channel_id, message_id, at=None):
    execute("UPDATE ops_nudge_items SET channel=?, channel_id=?, message_id=?, last_edit_at=? "
            "WHERE work_item_id=?",
            (channel or "", str(channel_id or ""), str(message_id or ""), _stamp(at),
             work_item_id))


def touch_nudge_edit(work_item_id, at=None):
    execute("UPDATE ops_nudge_items SET last_edit_at=? WHERE work_item_id=?",
            (_stamp(at), work_item_id))


def ack_nudge(work_item_id, by):
    execute("UPDATE ops_nudge_items SET acked_at=?, acked_by=? WHERE work_item_id=? "
            "AND acked_at IS NULL", (now_iso(), by or "", work_item_id))
    execute("UPDATE ops_nudges SET acked_at=? WHERE work_item_id=? AND acked_at IS NULL",
            (now_iso(), work_item_id))
    return nudge_item(work_item_id)


def flag_nudge_problem(work_item_id, by):
    execute("UPDATE ops_nudge_items SET problem_at=?, acked_by=COALESCE(acked_by,?) "
            "WHERE work_item_id=?", (now_iso(), by or "", work_item_id))
    return nudge_item(work_item_id)


def reassign_nudge(work_item_id, to_name, reason):
    execute("UPDATE ops_nudge_items SET reassigned_to=?, reassigned_reason=? WHERE work_item_id=?",
            (to_name or "", reason or "", work_item_id))
    return nudge_item(work_item_id)


def close_nudge(work_item_id):
    execute("UPDATE ops_nudge_items SET closed_at=COALESCE(closed_at,?) WHERE work_item_id=?",
            (now_iso(), work_item_id))


def record_nudge(work_item_id, employee, employee_did, level, path, channel="", message_id="",
                 at=None):
    """Claim a level. UNIQUE(work_item_id, level) means a retry, a restart or a double tick
    can never send the same level twice.

    `at` is the tick's own clock, not the wall clock. The sleep-protection strike count reads
    these timestamps back, so stamping them with a different clock than the one deciding the
    ladder would make the two disagree — and a night reassignment that never fires is a
    person nudged awake at 3 AM for nothing."""
    execute("INSERT OR IGNORE INTO ops_nudges"
            "(work_item_id,employee,employee_did,level,sent_at,path,channel,message_id)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (work_item_id, employee, employee_did or "", level,
             at if isinstance(at, str) else (at.isoformat(timespec="seconds") if at else now_iso()),
             path, channel or "", str(message_id or "")))


def set_nudge_path(work_item_id, level, path, message_id=None):
    if message_id is None:
        execute("UPDATE ops_nudges SET path=? WHERE work_item_id=? AND level=?",
                (path, work_item_id, level))
    else:
        execute("UPDATE ops_nudges SET path=?, message_id=? WHERE work_item_id=? AND level=?",
                (path, str(message_id), work_item_id, level))


def nudge_levels_sent(work_item_id):
    return [r["level"] for r in
            q("SELECT level FROM ops_nudges WHERE work_item_id=?", (work_item_id,))]


def nudge_rows(work_item_id):
    return q("SELECT * FROM ops_nudges WHERE work_item_id=? ORDER BY id", (work_item_id,))


def unacked_nudges_in_window(work_item_id, since_iso):
    """How many nudges have gone out for this turnover since a given moment with no answer —
    the sleep-protection strike count."""
    return len(q("SELECT id FROM ops_nudges WHERE work_item_id=? AND acked_at IS NULL "
                 "AND sent_at>=?", (work_item_id, since_iso)))


def open_nudge_items(limit=200):
    return q("SELECT * FROM ops_nudge_items WHERE closed_at IS NULL "
             "ORDER BY checkin_at LIMIT ?", (int(limit),))


def nudge_items_for_date(date_iso, limit=300):
    return q("SELECT * FROM ops_nudge_items WHERE date=? ORDER BY checkin_at LIMIT ?",
             (date_iso, int(limit)))


def sleep_reassignments(since_iso, limit=200):
    """Repeated night reassignments are a STAFFING signal for the owner's screen — never a
    disciplinary one."""
    return q("SELECT employee, COUNT(*) n, MAX(created_at) last_at FROM ops_nudge_items "
             "WHERE reassigned_reason='reassigned_asleep' AND created_at>=? "
             "GROUP BY employee ORDER BY n DESC LIMIT ?", (since_iso, int(limit)))


# ------------------------------------------------------------------ dry-run log

def dry_log(kind, employee=None, period_key=None, detail="", payload=None):
    execute("INSERT INTO ops_dryrun_log(at,kind,employee,period_key,detail,payload)"
            " VALUES(?,?,?,?,?,?)",
            (now_iso(), kind, employee, period_key, (detail or "")[:1000],
             json.dumps(payload or {}, ensure_ascii=False)))


def dry_logged(kind, employee, period_key):
    """Already noted? The tick runs every 5 minutes; the log must stay readable."""
    return q1("SELECT 1 x FROM ops_dryrun_log WHERE kind=? AND IFNULL(employee,'')=? "
              "AND IFNULL(period_key,'')=?",
              (kind, employee or "", period_key or "")) is not None


def dry_rows(limit=300, kind=None):
    if kind:
        return q("SELECT * FROM ops_dryrun_log WHERE kind=? ORDER BY id DESC LIMIT ?",
                 (kind, int(limit)))
    return q("SELECT * FROM ops_dryrun_log ORDER BY id DESC LIMIT ?", (int(limit),))


def dry_clear():
    execute("DELETE FROM ops_dryrun_log")
