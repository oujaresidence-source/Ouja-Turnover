# -*- coding: utf-8 -*-
"""
permits.seed.seed — load the committed seed on first boot ONLY, then link units.

Same pattern as schedule/seed.py: idempotent, seeds only when permits_permits is empty,
so a redeploy never duplicates and an owner's later edits are never overwritten.

Unit linking (link_units) is unique-or-nothing against the LIVE listings store, re-run
for still-unlinked rows by the daily batch. A MANUAL link (set in the dashboard) is never
touched by the auto-linker.
"""

import json
import os

from .. import db, engine

JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "permits_seed.normalized.json")


def load_rows(path=JSON_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def seed_if_empty(listings=None, path=JSON_PATH, actor="seed"):
    """-> number of permits inserted (0 when the table already had rows)."""
    if db.count_permits() > 0:
        return 0
    try:
        data = load_rows(path)
    except (OSError, ValueError) as e:
        print("[permits] seed JSON unreadable — nothing seeded:", e)
        return 0
    n = 0
    with db.transaction() as cx:
        # re-check inside the transaction: two bot copies booting together seed once
        if cx.execute("SELECT COUNT(*) FROM permits_permits").fetchone()[0] > 0:
            return 0
        for r in data.get("rows") or []:
            row = dict(r)
            row["source"] = "seed"
            pid = db.insert_permit(row, actor, cx=cx)
            n += 1
            db.log_event("seeded", pid, payload={"source_ref": row.get("source_ref")}, actor=actor, cx=cx)
    if listings is not None:
        try:
            link_units(listings)
        except Exception as e:                       # linking is best-effort; seeding is not
            print("[permits] unit linking skipped:", e)
    print("[permits] seeded %d permits from %s" % (n, os.path.basename(path)))
    return n


def _listing_rows(listings):
    """Accept the host's listings in either shape: [{id, internal_name, ...}] or {id: rec}."""
    raw = listings() if callable(listings) else listings
    if isinstance(raw, dict):
        out = []
        for k, v in raw.items():
            v = dict(v or {}) if isinstance(v, dict) else {"internal_name": str(v)}
            v["id"] = int(k)
            out.append(v)
        return out
    return list(raw or [])


def link_units(listings, actor="auto-link"):
    """Auto-link every live, unit-scoped, still-unlinked, non-manual permit.
    -> {"linked": n, "unlinked": [unit_text, ...]}."""
    rows = _listing_rows(listings)
    if not rows:
        return {"linked": 0, "unlinked": [p["unit_text"] for p in db.permits("active")
                                         if not p.get("listing_id") and p.get("unit_text")]}
    linked, unlinked = 0, []
    for p in db.permits("active"):
        if p.get("listing_id") or p.get("listing_link_kind") == "manual" or not p.get("unit_text"):
            continue
        lid, how, _cands = engine.match_unit(p["unit_text"], rows)
        if lid:
            db.update_permit(p["id"], {"listing_id": int(lid), "listing_link_kind": "auto"}, actor)
            db.log_event("linked", p["id"], payload={"listing_id": lid, "how": how}, actor=actor)
            linked += 1
        else:
            unlinked.append(p["unit_text"])
    return {"linked": linked, "unlinked": unlinked}
