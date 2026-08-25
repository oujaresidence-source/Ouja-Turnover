# -*- coding: utf-8 -*-
"""
wifi — «اشتراكات النت», the internet-subscription tracker (Phase 1).

The problem it exists to end: ~70 furnished units each need internet, bought either from
a telco directly or from a shop that resells at a discount. Nothing recorded which
apartment had which subscription, from whom, for how much, or when it ended — so
subscriptions died silently, sometimes with a guest inside, and we occasionally paid
twice for the same unit.

Phase 1 does two things and nothing else: it makes the double-paying structurally
impossible, and it starts collecting the data.

    engine.py  — PURE date maths. Trust the label first; correct it only with evidence.
    db.py      — wifi_* tables inside the existing brain.db. THE LOCK LIVES HERE, as a
                 partial unique index, so the database itself refuses a second active
                 subscription per apartment.
    routes.py  — /api/wifi/*. Two doors: the dashboard (login + permission) and the
                 public /wifi-fill backfill page (add-only).
    page.py    — /wifi-fill, phone-first Arabic, no login, no token.

NOT in Phase 1, on purpose: Discord reminders, the accountant money view, router/device
tracking, and any approval workflow. Anyone logs; nobody approves.
"""

from .host import HOST, wire  # noqa: F401
from . import db, engine, page, routes  # noqa: F401


def register_routes(app):
    routes.register(app)
