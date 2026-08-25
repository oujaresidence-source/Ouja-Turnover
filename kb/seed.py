# -*- coding: utf-8 -*-
"""
kb.seed — first fill of the knowledge base from seed_kb.json (56 units, 35 owners,
extracted from فيصل.xlsx sheet «معلومات» on 2026-08-03).

RUNS ONCE. After the first boot the database is the truth and people edit it through the
tab; re-running with force=True would overwrite hand-typed corrections with the
spreadsheet's older values, so boot only ever calls seed() without force, and that returns
immediately if any unit already exists.

NOTHING HERE FIXES DATA. The two duplicate Hostaway listing codes are inserted exactly as
they are in the sheet, because picking a side in code would silently move revenue between
two owners. They surface as red conflicts in the tab until a human resolves them.
"""

import json
import os

from . import db, engine

SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_kb.json")


def load():
    with open(SEED_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def seed(force=False):
    """Returns {'units': n, 'owners': n, 'skipped': bool}."""
    db.init()
    have = db.counts()
    if have["units"] and not force:
        return {"units": have["units"], "owners": have["owners"], "skipped": True}

    kb = load()
    owners = {o["owner_id"]: o for o in kb.get("owners", [])}
    for o in owners.values():
        db.upsert_owner(o, actor="seed")

    from contextlib import closing
    with closing(db.connect()) as cx:
        for u in kb.get("units", []):
            cx.execute("""INSERT OR REPLACE INTO kb_unit
                (unit_id, unit_name, listing_code, owner_id, district, district_en,
                 cleaning_policy, cleaning_monthly_sar, payment_cycle, ouja_owned, note,
                 source_row, updated_by, updated_at, last_reviewed, is_active)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'seed',?,NULL,1)""",
                (u["unit_id"], u["unit_name"], u.get("listing_code"), u.get("owner_id"),
                 u.get("district"), u.get("district_en"), u.get("cleaning_policy"),
                 u.get("cleaning_monthly_sar"), u.get("payment_cycle"),
                 1 if u.get("ouja_owned") else 0, u.get("note"), u.get("source_row"),
                 db._now()))
            # The seed carries per-unit aliases the extractor found; they belong in the
            # haystack, so index from the seed dict rather than from the stored row.
            orow = owners.get(u.get("owner_id"))
            cx.execute("""INSERT OR REPLACE INTO kb_search (entity_type, entity_id, hay)
                          VALUES ('unit',?,?)""",
                       (u["unit_id"], engine.build_hay(u, orow)))
        for f in kb.get("faqs", []):
            cx.execute("""INSERT OR REPLACE INTO kb_faq (faq_id, q_ar, a_ar, updated_by, updated_at)
                          VALUES (?,?,?, 'seed', ?)""",
                       (f["faq_id"], f["q_ar"], f["a_ar"], db._now()))
            cx.execute("""INSERT OR REPLACE INTO kb_search (entity_type, entity_id, hay)
                          VALUES ('faq',?,?)""",
                       (f["faq_id"], engine.fold(f["q_ar"] + " " + f["a_ar"])))
        cx.commit()

    c = db.counts()
    return {"units": c["units"], "owners": c["owners"], "skipped": False}
