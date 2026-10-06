# -*- coding: utf-8 -*-
"""
owner_meet — «اجتماع المالك», the Owner Meeting Room (spec docs/superpowers/specs/2026-10-06-owner-meet-design.md).

One click before an owner meeting builds a FROZEN snapshot of one apartment (or one owner's units)
for a period; Faisal walks it as a 16:9 presentation, records decisions, and — only by his own tap —
sends the owner a read-only link + PDF of exactly what was shown.

    host.py           — the ONE bridge to bot.py (caps). The package never imports bot, never calls Hostaway.
    config.py         — env flags + the owner-editable rules file (seed ← $STATE_DIR override).
    periods.py        — PURE: period -> statement months + exact window.
    money.py          — PURE: sums the statement's own fields (M1); waterfall; per-100.
    engine.py         — PURE: percentile bands (R1), fair-share index, exact ratings, promo split.
    airbnb_import.py  — PURE: the Airbnb opportunity report, parsed by header name.
    snapshot.py       — builds {"meta","owner","presenter"} from caps + the pure modules.
    jobs.py           — the build pool (never the web lane).
    texts.py          — every owner-facing Arabic word; dates as words, never ISO.
    charts.py         — PURE deterministic SVG (bars, waterfall, peer bands).
    render.py         — the presentation + presenter window, server-rendered from the snapshot.
    routes.py         — /api/meet/* (login + «meet» permission), /meet/{id}, /meet/{id}/notes, static.
    db.py             — meet_* tables in brain.db; a frozen snapshot is immutable IN SQL.

Nothing in this package sends anything to an owner on its own. There is no scheduler.
"""

from .host import HOST, wire as _wire
from . import airbnb_import, charts, config, db, engine, jobs, money, periods, render, routes, snapshot, texts  # noqa: F401


def enabled():
    return config.enabled()


def wire(caps):
    return _wire(caps)


def bootstrap():
    """Tables + the one seeded annotation (only when empty) + fail builds a restart interrupted."""
    db._ensure()
    db.fail_interrupted()


def register_routes(app):
    """All doors; OWNER_MEET_ENABLED=0 registers none."""
    routes.register(app)
