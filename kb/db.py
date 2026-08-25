# -*- coding: utf-8 -*-
"""
kb.db — kb_* tables inside the SAME brain.db SQLite file (schedule/wifi pattern). No new
database file, and every call is wrapped in `with closing(connect())` so it inherits
brain.db's proven NO-WAL / journal_mode=DELETE / busy_timeout rules. The handoff's
schema.sql opened with `PRAGMA journal_mode = WAL`; that pragma is deliberately dropped —
WAL's -shm shared-memory file is unsupported on the Railway volume and took the whole
database down once already.

EVERY WRITE IS APPENDED, NEVER OVERWRITTEN
------------------------------------------
`update_unit` diffs field by field and writes one kb_audit row per ACTUALLY changed field
(an unchanged value writes nothing, so the log stays readable). Deletes set is_active=0 —
nothing in this module ever issues a DELETE against a fact. The point of the tool is that
a number can always be traced back to the person who typed it.

SEARCH IS A FOLDED HAYSTACK PLUS `LIKE`
---------------------------------------
See kb/engine.py for why this is substring matching and not FTS5. The haystack is rebuilt
on every write; if a rename ever stopped reindexing, search would quietly keep answering
with the old name, which is worse than an error.
"""

import json
import re
import secrets
from contextlib import closing

from brain import db as _bdb

from . import engine

SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_owner (
    owner_id      TEXT PRIMARY KEY,
    name_ar       TEXT NOT NULL,
    aliases       TEXT DEFAULT '[]',      -- JSON array of spelling variants / nicknames
    is_ouja       INTEGER NOT NULL DEFAULT 0,
    updated_by    TEXT,
    updated_at    TEXT,
    last_reviewed TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS kb_unit (
    unit_id              TEXT PRIMARY KEY,
    unit_name            TEXT NOT NULL,
    listing_code         TEXT,             -- Hostaway listing id; NOT unique in the source
    owner_id             TEXT,
    district             TEXT,             -- canonical Arabic spelling only
    district_en          TEXT,
    cleaning_policy      TEXT,             -- 'ouja' | 'owner' | NULL (not recorded)
    cleaning_monthly_sar REAL,
    payment_cycle        TEXT,             -- 'monthly' | 'biweekly_quarter_month' | 'quarterly'
    ouja_owned           INTEGER NOT NULL DEFAULT 0,
    note                 TEXT,
    source_row           INTEGER,          -- provenance: row in فيصل.xlsx
    updated_by           TEXT,
    updated_at           TEXT,
    last_reviewed        TEXT,
    is_active            INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_kb_unit_owner ON kb_unit(owner_id);
CREATE INDEX IF NOT EXISTS idx_kb_unit_code  ON kb_unit(listing_code);
CREATE TABLE IF NOT EXISTS kb_search (
    entity_type TEXT NOT NULL,             -- 'unit' | 'owner' | 'faq'
    entity_id   TEXT NOT NULL,
    hay         TEXT NOT NULL,
    PRIMARY KEY (entity_type, entity_id)
);
CREATE TABLE IF NOT EXISTS kb_faq (
    faq_id          TEXT PRIMARY KEY,
    q_ar            TEXT NOT NULL,
    a_ar            TEXT NOT NULL,
    tags            TEXT DEFAULT '[]',
    related_unit_id TEXT,
    owner_dri       TEXT,                  -- who is accountable for this answer being right
    ask_count       INTEGER NOT NULL DEFAULT 0,
    updated_by      TEXT,
    updated_at      TEXT,
    last_reviewed   TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS kb_question (
    question_id     TEXT PRIMARY KEY,
    text            TEXT NOT NULL,
    asked_by        TEXT,
    asked_at        TEXT,
    status          TEXT NOT NULL DEFAULT 'open',   -- open | answered | duplicate
    resolved_faq_id TEXT
);
CREATE TABLE IF NOT EXISTS kb_audit (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    field       TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_by  TEXT,
    changed_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_kb_audit_entity ON kb_audit(entity_type, entity_id);
CREATE TABLE IF NOT EXISTS kb_search_log (
    log_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    q            TEXT,
    q_fold       TEXT,
    result_count INTEGER,
    searched_by  TEXT,
    searched_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_kb_log_zero ON kb_search_log(result_count, searched_at);
CREATE TABLE IF NOT EXISTS kb_setting (
    k          TEXT PRIMARY KEY,
    v          TEXT,
    updated_by TEXT,
    updated_at TEXT
);
"""

# The share link's secret. Long and random, because the whole security of the public door
# is that the URL cannot be guessed — there is nothing else in front of it.
SHARE_KEY = "share_token"

UNIT_FIELDS = ("unit_name", "listing_code", "owner_id", "district", "district_en",
               "cleaning_policy", "cleaning_monthly_sar", "payment_cycle", "ouja_owned",
               "note", "last_reviewed")

_inited = set()


def set_db_path(path):
    """Point at a throwaway database (tests only)."""
    _bdb.set_db_path_for_tests(path)
    _inited.clear()


def connect():
    return _bdb.connect()


def init():
    path = _bdb.db_path()
    if path in _inited:
        return
    with closing(connect()) as cx:
        cx.executescript(SCHEMA)
        cx.commit()
    _inited.add(path)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _today():
    return _now()[:10]


def _rows(cx, sql, args=()):
    return [dict(r) for r in cx.execute(sql, args).fetchall()]


# ---------------- reading ----------------

def _decorate(u, conflicts=None):
    """One place turns a stored row into what the UI shows, so a gap or a conflict can
    never be computed one way on the card and another way in the filter."""
    u = dict(u)
    u["ouja_owned"] = bool(u.get("ouja_owned"))
    u["gaps"] = engine.gaps(u)
    u["is_complete"] = not u["gaps"]
    u["conflicts"] = (conflicts or {}).get(u.get("unit_id"), [])
    u["policy_ar"] = engine.POLICY_AR.get(u.get("cleaning_policy"))
    u["cycle_ar"] = engine.CYCLE_AR.get(u.get("payment_cycle"))
    return u


def all_units(active_only=True):
    init()
    with closing(connect()) as cx:
        rows = _rows(cx, """SELECT u.*, o.name_ar AS owner_ar FROM kb_unit u
                            LEFT JOIN kb_owner o ON o.owner_id = u.owner_id
                            %s ORDER BY u.unit_name""" % ("WHERE u.is_active=1" if active_only else ""))
    conf = engine.find_conflicts(rows)
    return [_decorate(r, conf) for r in rows]


def unit(unit_id):
    init()
    with closing(connect()) as cx:
        rows = _rows(cx, """SELECT u.*, o.name_ar AS owner_ar FROM kb_unit u
                            LEFT JOIN kb_owner o ON o.owner_id = u.owner_id
                            WHERE u.unit_id=?""", (unit_id,))
        if not rows:
            return None
        siblings = _rows(cx, "SELECT unit_id, unit_name, listing_code FROM kb_unit WHERE is_active=1")
    return _decorate(rows[0], engine.find_conflicts(siblings))


def owner(owner_id):
    init()
    with closing(connect()) as cx:
        rows = _rows(cx, "SELECT * FROM kb_owner WHERE owner_id=?", (owner_id,))
    if not rows:
        return None
    o = rows[0]
    o["aliases"] = _loads(o.get("aliases"))
    o["units"] = [u for u in all_units() if u.get("owner_id") == owner_id]
    o["unit_count"] = len(o["units"])
    return o


def _loads(s):
    try:
        v = json.loads(s or "[]")
        return v if isinstance(v, list) else []
    except (ValueError, TypeError):
        return []


def counts():
    init()
    with closing(connect()) as cx:
        u = cx.execute("SELECT COUNT(*) FROM kb_unit WHERE is_active=1").fetchone()[0]
        o = cx.execute("SELECT COUNT(*) FROM kb_owner WHERE is_active=1").fetchone()[0]
        oo = cx.execute("SELECT COUNT(*) FROM kb_unit WHERE is_active=1 AND ouja_owned=1").fetchone()[0]
        f = cx.execute("SELECT COUNT(*) FROM kb_faq WHERE is_active=1").fetchone()[0]
    gaps_n = sum(1 for x in all_units() if x["gaps"])
    return {"units": u, "owners": o, "ouja_owned": oo, "faqs": f, "gaps": gaps_n}


def _hays(cx, entity_type):
    return {r["entity_id"]: r["hay"] for r in
            cx.execute("SELECT entity_id, hay FROM kb_search WHERE entity_type=?",
                       (entity_type,)).fetchall()}


def search(q, type="all", district=None, owned="all", gaps=False, limit=200, log_as=None):
    """The one read the whole tab is built on. `gaps` and the card badge come from the
    SAME engine.gaps(), so the filter can never disagree with what the card shows."""
    init()
    toks = engine.query_tokens(q)
    with closing(connect()) as cx:
        urows = _rows(cx, """SELECT u.*, o.name_ar AS owner_ar FROM kb_unit u
                             LEFT JOIN kb_owner o ON o.owner_id = u.owner_id
                             WHERE u.is_active=1 ORDER BY u.unit_name""")
        uhay = _hays(cx, "unit")
        orows = _rows(cx, "SELECT * FROM kb_owner WHERE is_active=1")
        ohay = _hays(cx, "owner")
        frows = _rows(cx, "SELECT * FROM kb_faq WHERE is_active=1")
        fhay = _hays(cx, "faq")

    conf = engine.find_conflicts(urows)
    units = []
    if type in ("all", "unit"):
        for r in urows:
            if not engine.matches(uhay.get(r["unit_id"], ""), toks):
                continue
            d = _decorate(r, conf)
            if district and d.get("district") != district:
                continue
            if owned == "ouja" and not d["ouja_owned"]:
                continue
            if owned == "inv" and d["ouja_owned"]:
                continue
            if gaps and not d["gaps"]:
                continue
            units.append(d)

    owners = []
    if type in ("all", "owner") and toks:
        counts_by_owner = {}
        for r in urows:
            counts_by_owner[r.get("owner_id")] = counts_by_owner.get(r.get("owner_id"), 0) + 1
        for o in orows:
            if not engine.matches(ohay.get(o["owner_id"], ""), toks):
                continue
            n = counts_by_owner.get(o["owner_id"], 0)
            # A single-unit owner adds nothing above the unit card itself.
            if n > 1:
                owners.append({"owner_id": o["owner_id"], "name_ar": o["name_ar"],
                               "is_ouja": bool(o["is_ouja"]), "unit_count": n,
                               "units": [{"unit_id": u["unit_id"], "unit_name": u["unit_name"]}
                                         for u in urows if u.get("owner_id") == o["owner_id"]]})

    faqs = []
    if type in ("all", "faq") and toks:
        for f in frows:
            if engine.matches(fhay.get(f["faq_id"], ""), toks):
                f = dict(f)
                f["tags"] = _loads(f.get("tags"))
                faqs.append(f)

    units = units[:limit]
    if log_as is not None:
        _log_search(q, len(units) + len(faqs), log_as)
    return {"query": q, "count": len(units), "units": units,
            "owners": owners, "faqs": faqs}


def districts():
    init()
    with closing(connect()) as cx:
        rows = cx.execute("""SELECT district, COUNT(*) c FROM kb_unit
                             WHERE is_active=1 AND district IS NOT NULL AND district<>''
                             GROUP BY district ORDER BY c DESC, district""").fetchall()
    return [{"district": r[0], "count": r[1]} for r in rows]


# ---------------- writing ----------------

def _audit(cx, entity_type, entity_id, field, old, new, actor):
    cx.execute("""INSERT INTO kb_audit
                  (entity_type, entity_id, field, old_value, new_value, changed_by, changed_at)
                  VALUES (?,?,?,?,?,?,?)""",
               (entity_type, entity_id, field,
                None if old is None else str(old), None if new is None else str(new),
                actor or "", _now()))


def _reindex_unit(cx, unit_id):
    row = cx.execute("SELECT * FROM kb_unit WHERE unit_id=?", (unit_id,)).fetchone()
    if not row:
        return
    u = dict(row)
    orow = cx.execute("SELECT * FROM kb_owner WHERE owner_id=?", (u.get("owner_id"),)).fetchone()
    o = dict(orow) if orow else None
    if o:
        o["aliases"] = _loads(o.get("aliases"))
    hay = engine.build_hay(u, o)
    cx.execute("INSERT OR REPLACE INTO kb_search (entity_type, entity_id, hay) VALUES ('unit',?,?)",
               (unit_id, hay))


def _reindex_owner(cx, owner_id):
    row = cx.execute("SELECT * FROM kb_owner WHERE owner_id=?", (owner_id,)).fetchone()
    if not row:
        return
    o = dict(row)
    o["aliases"] = _loads(o.get("aliases"))
    cx.execute("INSERT OR REPLACE INTO kb_search (entity_type, entity_id, hay) VALUES ('owner',?,?)",
               (owner_id, engine.build_owner_hay(o)))
    # An owner rename changes what his units answer to, so their haystacks follow.
    for r in cx.execute("SELECT unit_id FROM kb_unit WHERE owner_id=?", (owner_id,)).fetchall():
        _reindex_unit(cx, r[0])


def update_unit(unit_id, patch, actor=""):
    """Returns (changed_field_count, error_ar). One audit row per changed field."""
    init()
    clean, err = engine.validate(patch)
    if err:
        return False, err
    clean = {k: v for k, v in clean.items() if k in UNIT_FIELDS}
    if not clean:
        return 0, None
    with closing(connect()) as cx:
        row = cx.execute("SELECT * FROM kb_unit WHERE unit_id=?", (unit_id,)).fetchone()
        if not row:
            return False, "الوحدة غير موجودة"
        cur = dict(row)
        after = dict(cur)
        after.update(clean)
        rule = engine.check_amount_rule(after)
        if rule:
            return False, rule
        n = 0
        for k, v in clean.items():
            if _same(cur.get(k), v):
                continue
            cx.execute("UPDATE kb_unit SET %s=? WHERE unit_id=?" % k, (v, unit_id))
            _audit(cx, "unit", unit_id, k, cur.get(k), v, actor)
            n += 1
        if n:
            cx.execute("UPDATE kb_unit SET updated_by=?, updated_at=?, last_reviewed=? WHERE unit_id=?",
                       (actor or "", _now(), _today(), unit_id))
            _reindex_unit(cx, unit_id)
        cx.commit()
    return n, None


def _same(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    return str(a) == str(b)


def _slug(name):
    return re.sub(r"[^A-Za-z0-9]+", "", str(name or "")).upper()[:12] or "NEW"


def create_unit(data, actor=""):
    init()
    name = (data.get("unit_name") or "").strip()
    if not name:
        return None, "لازم اسم الشقة"
    clean, err = engine.validate({k: v for k, v in data.items() if k in UNIT_FIELDS})
    if err:
        return None, err
    clean["unit_name"] = name
    rule = engine.check_amount_rule(clean)
    if rule:
        return None, rule
    with closing(connect()) as cx:
        code = (clean.get("listing_code") or "").strip()
        base = "UNT-" + (code if code else _slug(name))
        uid, i = base, 1
        while cx.execute("SELECT 1 FROM kb_unit WHERE unit_id=?", (uid,)).fetchone():
            i += 1
            uid = "%s-%d" % (base, i)
        cols = ["unit_id"] + list(clean.keys()) + ["updated_by", "updated_at", "last_reviewed"]
        vals = [uid] + list(clean.values()) + [actor or "", _now(), _today()]
        cx.execute("INSERT INTO kb_unit (%s) VALUES (%s)"
                   % (",".join(cols), ",".join("?" * len(cols))), vals)
        _audit(cx, "unit", uid, "created", None, name, actor)
        _reindex_unit(cx, uid)
        cx.commit()
    return uid, None


def soft_delete_unit(unit_id, actor=""):
    init()
    with closing(connect()) as cx:
        cx.execute("UPDATE kb_unit SET is_active=0, updated_by=?, updated_at=? WHERE unit_id=?",
                   (actor or "", _now(), unit_id))
        _audit(cx, "unit", unit_id, "is_active", 1, 0, actor)
        cx.commit()
    return True


def upsert_owner(o, actor="seed"):
    init()
    with closing(connect()) as cx:
        cx.execute("""INSERT OR REPLACE INTO kb_owner
                      (owner_id, name_ar, aliases, is_ouja, updated_by, updated_at, last_reviewed, is_active)
                      VALUES (?,?,?,?,?,?,?,1)""",
                   (o["owner_id"], o["name_ar"],
                    json.dumps(list(o.get("aliases") or []), ensure_ascii=False),
                    1 if o.get("is_ouja") else 0, actor, _now(), _today()))
        _reindex_owner(cx, o["owner_id"])
        cx.commit()


def audit_for(entity_type, entity_id, limit=100):
    init()
    with closing(connect()) as cx:
        return _rows(cx, """SELECT * FROM kb_audit WHERE entity_type=? AND entity_id=?
                            ORDER BY audit_id DESC LIMIT ?""", (entity_type, entity_id, limit))


# ---------------- FAQs ----------------

def create_faq(data, actor=""):
    init()
    q = (data.get("q_ar") or "").strip()
    a = (data.get("a_ar") or "").strip()
    if not q or not a:
        return None, "لازم سؤال وجواب"
    with closing(connect()) as cx:
        n = cx.execute("SELECT COUNT(*) FROM kb_faq").fetchone()[0]
        fid = "FAQ-%03d" % (n + 1)
        while cx.execute("SELECT 1 FROM kb_faq WHERE faq_id=?", (fid,)).fetchone():
            n += 1
            fid = "FAQ-%03d" % (n + 1)
        cx.execute("""INSERT INTO kb_faq (faq_id, q_ar, a_ar, tags, related_unit_id,
                                          owner_dri, updated_by, updated_at, last_reviewed)
                      VALUES (?,?,?,?,?,?,?,?,?)""",
                   (fid, q, a, json.dumps(list(data.get("tags") or []), ensure_ascii=False),
                    data.get("related_unit_id"), data.get("owner_dri"),
                    actor or "", _now(), _today()))
        cx.execute("INSERT OR REPLACE INTO kb_search (entity_type, entity_id, hay) VALUES ('faq',?,?)",
                   (fid, engine.fold(q + " " + a + " " + " ".join(data.get("tags") or []))))
        _audit(cx, "faq", fid, "created", None, q, actor)
        cx.commit()
    return fid, None


def update_faq(faq_id, patch, actor=""):
    init()
    fields = ("q_ar", "a_ar", "owner_dri", "related_unit_id")
    with closing(connect()) as cx:
        row = cx.execute("SELECT * FROM kb_faq WHERE faq_id=?", (faq_id,)).fetchone()
        if not row:
            return False, "السؤال غير موجود"
        cur = dict(row)
        n = 0
        for k in fields:
            if k not in patch:
                continue
            v = (patch.get(k) or "").strip() or None
            if _same(cur.get(k), v):
                continue
            cx.execute("UPDATE kb_faq SET %s=? WHERE faq_id=?" % k, (v, faq_id))
            _audit(cx, "faq", faq_id, k, cur.get(k), v, actor)
            cur[k] = v
            n += 1
        if n:
            cx.execute("UPDATE kb_faq SET updated_by=?, updated_at=?, last_reviewed=? WHERE faq_id=?",
                       (actor or "", _now(), _today(), faq_id))
            cx.execute("INSERT OR REPLACE INTO kb_search (entity_type, entity_id, hay) VALUES ('faq',?,?)",
                       (faq_id, engine.fold((cur.get("q_ar") or "") + " " + (cur.get("a_ar") or ""))))
        cx.commit()
    return n, None


def soft_delete_faq(faq_id, actor=""):
    init()
    with closing(connect()) as cx:
        cx.execute("UPDATE kb_faq SET is_active=0 WHERE faq_id=?", (faq_id,))
        _audit(cx, "faq", faq_id, "is_active", 1, 0, actor)
        cx.commit()
    return True


def bump_faq(faq_id):
    init()
    with closing(connect()) as cx:
        cx.execute("UPDATE kb_faq SET ask_count=ask_count+1 WHERE faq_id=?", (faq_id,))
        cx.commit()


# ---------------- the capture queue ----------------

def log_question(text, asked_by=""):
    """Every unanswered search can become a logged question, and every logged question is
    documentation debt: it ends as a FAQ or as a filled field. This is the mechanism that
    grows the base without anyone running a documentation project."""
    init()
    text = (text or "").strip()
    if not text:
        return None
    with closing(connect()) as cx:
        n = cx.execute("SELECT COUNT(*) FROM kb_question").fetchone()[0] + 1
        qid = "Q-%04d" % n
        while cx.execute("SELECT 1 FROM kb_question WHERE question_id=?", (qid,)).fetchone():
            n += 1
            qid = "Q-%04d" % n
        cx.execute("""INSERT INTO kb_question (question_id, text, asked_by, asked_at, status)
                      VALUES (?,?,?,?, 'open')""", (qid, text, asked_by or "", _now()))
        cx.commit()
    return qid


def questions(status=None, limit=200):
    init()
    with closing(connect()) as cx:
        if status:
            return _rows(cx, """SELECT * FROM kb_question WHERE status=?
                                ORDER BY asked_at DESC LIMIT ?""", (status, limit))
        return _rows(cx, "SELECT * FROM kb_question ORDER BY asked_at DESC LIMIT ?", (limit,))


def resolve_question(question_id, status="answered", faq_id=None, actor=""):
    init()
    if status not in ("open", "answered", "duplicate"):
        return False, "حالة غير معروفة"
    with closing(connect()) as cx:
        cx.execute("UPDATE kb_question SET status=?, resolved_faq_id=? WHERE question_id=?",
                   (status, faq_id, question_id))
        _audit(cx, "question", question_id, "status", None, status, actor)
        cx.commit()
    return True, None


# ---------------- quality + stats ----------------

def _log_search(q, n, who):
    try:
        with closing(connect()) as cx:
            cx.execute("""INSERT INTO kb_search_log (q, q_fold, result_count, searched_by, searched_at)
                          VALUES (?,?,?,?,?)""",
                       ((q or "")[:200], engine.fold(q)[:200], n, who or "", _now()))
            cx.commit()
    except Exception:
        # A search must never fail because its own logging failed.
        pass


def quality():
    """Computed live from the database, never from a file — the whole point is that these
    numbers shrink as people fill the gaps."""
    units = all_units()
    dup = {}
    for u in units:
        for c in u["conflicts"]:
            dup.setdefault(c["code"], set()).update([u["unit_id"]] + list(c["with"]))
    by_name = {}
    for u in units:
        for uid in [u["unit_id"]]:
            by_name[uid] = u["unit_name"]
    missing = {"cleaning": 0, "cycle": 0, "district": 0}
    gap_units = []
    for u in units:
        g = u["gaps"]
        if not g:
            continue
        gap_units.append({"unit_id": u["unit_id"], "unit_name": u["unit_name"],
                          "owner_ar": u.get("owner_ar"), "gaps": g})
        if engine.GAP_CLEANING in g:
            missing["cleaning"] += 1
        if engine.GAP_CYCLE in g:
            missing["cycle"] += 1
        if engine.GAP_DISTRICT in g:
            missing["district"] += 1
    return {
        "counts": counts(),
        "missing": missing,
        "gap_units": gap_units,
        "duplicate_codes": [{"code": c, "units": sorted(ids),
                             "names": [by_name.get(i, i) for i in sorted(ids)]}
                            for c, ids in sorted(dup.items())],
        "district_variants": [{"canonical": k, "variants": v}
                              for k, v in sorted(engine.DISTRICT_VARIANTS.items())],
    }


# ---------------- settings + the share token ----------------

def get_setting(k, default=None):
    init()
    with closing(connect()) as cx:
        row = cx.execute("SELECT v FROM kb_setting WHERE k=?", (k,)).fetchone()
    return row[0] if row else default


def set_setting(k, v, actor=""):
    init()
    with closing(connect()) as cx:
        cx.execute("""INSERT OR REPLACE INTO kb_setting (k, v, updated_by, updated_at)
                      VALUES (?,?,?,?)""", (k, v, actor or "", _now()))
        cx.commit()


def share_token(create=True):
    """The secret in the public URL. Created once and then persisted, so a Railway
    redeploy does not silently invalidate a link the team already saved."""
    t = get_setting(SHARE_KEY)
    if t or not create:
        return t
    t = secrets.token_urlsafe(24)
    set_setting(SHARE_KEY, t, actor="system")
    return t


def rotate_share_token(actor=""):
    """Kills every copy of the old link at once. Audited: who burned the old link and
    when is the first thing anyone will ask afterwards."""
    old = get_setting(SHARE_KEY)
    new = secrets.token_urlsafe(24)
    set_setting(SHARE_KEY, new, actor=actor)
    with closing(connect()) as cx:
        # Only the last 6 characters are logged. A full old token in an audit row anyone
        # can read would just be the same secret in a second place.
        _audit(cx, "setting", SHARE_KEY, "rotated",
               ("…" + old[-6:]) if old else None, "…" + new[-6:], actor)
        cx.commit()
    return new


def token_ok(t):
    real = get_setting(SHARE_KEY)
    if not real or not t:
        return False
    return secrets.compare_digest(str(t), str(real))


def stats():
    init()
    with closing(connect()) as cx:
        s7 = cx.execute("""SELECT COUNT(*) FROM kb_search_log
                           WHERE searched_at >= datetime('now','-7 day')""").fetchone()[0]
        z7 = cx.execute("""SELECT COUNT(*) FROM kb_search_log
                           WHERE result_count=0 AND searched_at >= datetime('now','-7 day')""").fetchone()[0]
        # Zero-result searches are the most valuable rows in the system: each one is
        # either a missing fact or a missing alias, and both are one-line fixes.
        zq = _rows(cx, """SELECT q, COUNT(*) n, MAX(searched_at) last FROM kb_search_log
                          WHERE result_count=0 AND q<>'' GROUP BY q_fold
                          ORDER BY n DESC, last DESC LIMIT 20""")
        top = _rows(cx, """SELECT q, COUNT(*) n FROM kb_search_log
                           WHERE q<>'' AND searched_at >= datetime('now','-30 day')
                           GROUP BY q_fold ORDER BY n DESC LIMIT 10""")
        oq = cx.execute("SELECT COUNT(*) FROM kb_question WHERE status='open'").fetchone()[0]
    c = counts()
    pct = round(100.0 * (c["units"] - c["gaps"]) / c["units"], 1) if c["units"] else 0.0
    return {"searches_7d": s7, "zero_result_searches_7d": z7, "open_questions": oq,
            "units_complete_pct": pct, "faq_count": c["faqs"],
            "top_queries_30d": top, "zero_queries": zq}
