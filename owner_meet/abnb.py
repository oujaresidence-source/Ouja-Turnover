# -*- coding: utf-8 -*-
"""
owner_meet.abnb — the Airbnb opportunity report, stored and mapped.

    import_file(bytes, name, by)  -> every import is a DATED SNAPSHOT (never overwritten). The same
                                     file twice is recognised by sha256 and stored once.
    latest(on_or_before)          -> the newest import whose data_as_of <= the meeting date.
    mapping()                     -> Airbnb row <-> Hostaway unit: Hostaway's own channel id first
                                     (method "payload", needs nobody), else a stored admin
                                     confirmation, else a title suggestion that waits for one.
                                     Unmapped rows are LISTED, never dropped.
"""

import difflib
import hashlib
import json

from . import airbnb_import, config, db
from .host import HOST

SUGGEST_MIN = 0.55


def _norm_title(t):
    t = (t or "").lower()
    for ch in "|·•-–—,.()+&/":
        t = t.replace(ch, " ")
    return " ".join(w for w in t.split() if w not in ("ouja", "self", "entry", "selfentry"))


def import_file(data, filename, by):
    """-> {"ok", "import_id", "data_as_of", "rows", "duplicate"} or raises ValueError(arabic)."""
    parsed = airbnb_import.parse(data, filename)
    sha = hashlib.sha256(data).hexdigest()
    prev = db.q1("SELECT id, data_as_of, rows FROM meet_abnb_imports WHERE sha256=?", (sha,))
    if prev:
        return {"ok": True, "import_id": prev["id"], "data_as_of": prev["data_as_of"], "rows": prev["rows"],
                "duplicate": True}
    fx = float(config.rules().get("fx_sar_per_usd", 3.75))
    iid = db.execute("INSERT INTO meet_abnb_imports(data_as_of,filename,sha256,rows,fx_sar_per_usd,uploaded_by,at) "
                     "VALUES(?,?,?,?,?,?,?)", (parsed["data_as_of"], filename, sha, len(parsed["rows"]), fx, by, db._now()))
    for r in parsed["rows"]:
        if r.get("airbnb_id"):
            db.execute("INSERT OR REPLACE INTO meet_abnb_rows(import_id,airbnb_id,json) VALUES(?,?,?)",
                       (iid, r["airbnb_id"], json.dumps(r, ensure_ascii=False)))
    db.log_event(None, "abnb_import", {"import_id": iid, "data_as_of": parsed["data_as_of"], "rows": len(parsed["rows"])}, by)
    return {"ok": True, "import_id": iid, "data_as_of": parsed["data_as_of"], "rows": len(parsed["rows"]),
            "duplicate": False}


def imports():
    return db.q("SELECT id, data_as_of, filename, rows, fx_sar_per_usd, uploaded_by, at FROM meet_abnb_imports "
                "ORDER BY data_as_of DESC, id DESC")


def latest(on_or_before=None):
    """-> (import_row, {airbnb_id: row}) or (None, {})."""
    if on_or_before:
        imp = db.q1("SELECT * FROM meet_abnb_imports WHERE data_as_of<=? ORDER BY data_as_of DESC, id DESC LIMIT 1",
                    (str(on_or_before)[:10],))
    else:
        imp = db.q1("SELECT * FROM meet_abnb_imports ORDER BY data_as_of DESC, id DESC LIMIT 1")
    if not imp:
        return None, {}
    rows = {r["airbnb_id"]: json.loads(r["json"]) for r in
            db.q("SELECT airbnb_id, json FROM meet_abnb_rows WHERE import_id=?", (imp["id"],))}
    return imp, rows


def confirm(airbnb_id, lid, by, method="manual"):
    db.execute("INSERT OR REPLACE INTO meet_abnb_map(airbnb_id,lid,method,confirmed_by,at) VALUES(?,?,?,?,?)",
               (str(airbnb_id), int(lid) if lid not in (None, "") else None, method, by, db._now()))


def mapping(rows=None):
    """-> {"by_airbnb": {aid: {lid, method}}, "by_lid": {lid: aid}, "unmapped": [{airbnb_id, title, suggest}]}.
    Order of trust: Hostaway's channel id > a stored confirmation > nothing (a suggestion is shown,
    never used, until somebody confirms it)."""
    if rows is None:
        _imp, rows = latest()
    payload = {}
    try:
        payload = {str(aid): int(lid) for lid, aid in (HOST.airbnb_room_ids() or {}).items()} if HOST.airbnb_room_ids else {}
    except Exception as e:
        print("[owner_meet] airbnb ids unavailable:", e)
    stored = {r["airbnb_id"]: r for r in db.q("SELECT airbnb_id, lid, method FROM meet_abnb_map")}
    titles = {}
    try:
        titles = HOST.listing_titles() or {} if HOST.listing_titles else {}
    except Exception:
        titles = {}
    by_aid, pending = {}, []
    for aid, row in sorted(rows.items(), key=lambda kv: kv[1].get("rank") or 0):
        if aid in payload:
            by_aid[aid] = {"lid": payload[aid], "method": "payload"}
        elif aid in stored and stored[aid]["lid"] is not None:
            by_aid[aid] = {"lid": stored[aid]["lid"], "method": stored[aid]["method"]}
        else:
            pending.append((aid, row))
    # Suggestions: score every (row, free unit) pair, then hand out the best pairs first so one unit is
    # never suggested for two rows. A suggestion is only a pre-selected choice — nothing uses it.
    taken = {v["lid"] for v in by_aid.values()} | {r["lid"] for r in stored.values() if r["lid"] is not None}
    pairs = []
    for aid, row in pending:
        want = _norm_title(row.get("title_clean"))
        for lid, t in titles.items():
            if lid in taken:
                continue
            sc = difflib.SequenceMatcher(None, want, _norm_title(t)).ratio()
            if sc >= SUGGEST_MIN:
                pairs.append((sc, aid, lid))
    suggest, used = {}, set()
    for sc, aid, lid in sorted(pairs, key=lambda x: (-x[0], x[1], x[2])):
        if aid in suggest or lid in used:
            continue
        suggest[aid] = {"lid": lid, "title": titles.get(lid), "score": round(sc, 2)}
        used.add(lid)
    unmapped = [{"airbnb_id": aid, "title": row.get("title_clean"), "rank": row.get("rank"),
                 "bedrooms": row.get("bedrooms"), "suggest": suggest.get(aid)} for aid, row in pending]
    return {"by_airbnb": by_aid, "by_lid": {v["lid"]: k for k, v in by_aid.items()}, "unmapped": unmapped}
