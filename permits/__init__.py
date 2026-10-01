# -*- coding: utf-8 -*-
"""
permits — «التصاريح», the permit & licence expiry tracker.

The problem it exists to end: Ouja holds dated permits — today 45 Ministry of Tourism
hospitality-facility permits, one per apartment, each valid one year and issued in the
OWNER's name — and nothing watched them, so one could expire unnoticed.

The guarantee: NO PERMIT EXPIRES WITHOUT A TICKET. At ≤ 10 days left (catch-up included)
a ticket channel opens under «صيانه»; it nudges daily and escalates; it closes only by
renewal-with-proof, an authorised «لن يُجدَّد» with a reason, or a date correction.

    dates.py    — Hijri / Gregorian / Arabic digits / Excel serials → ISO, flagged never guessed.
    engine.py   — PURE rules: one band function, plan(), text builders inside Discord limits,
                  header mapping, unique-or-nothing unit matching.
    db.py       — permits_* tables in brain.db. One live ticket per permit is a UNIQUE INDEX.
    importer.py — CSV/XLSX/JSON → preview → commit (re-parsed). National IDs: last 4 only.
    service.py  — the tick: reconcile → plan → enqueue → drain the outbox. Dry by default.
    port.py     — the DiscordPort contract bot.py implements and the tests fake.
    routes.py   — /api/permits/* (+ the tab script at /permits/static/permits_tab.js).
    seed/       — the committed normalized seed (the raw xlsx is git-ignored).
"""

from .host import HOST, wire as _wire
from . import dates, db, engine, importer, port, routes, service  # noqa: F401
from .seed import seed as _seed


def wire(caps):
    return _wire(caps)


def bootstrap():
    """Tables + first-boot seed (only when empty) + unit auto-link. -> rows seeded."""
    db._ensure()
    return _seed.seed_if_empty(listings=HOST.listings)


def register_routes(app):
    routes.register(app)
