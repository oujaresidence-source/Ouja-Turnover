# -*- coding: utf-8 -*-
"""
targets — «الأهداف ودفتر العملاء»: per-unit occupancy targets and the employees' client book.

THE PRINCIPLE THIS PACKAGE EXISTS TO PROTECT
    Ouja pays only from money that would not have come without the employee.
Cash comes only from bookings that follow a LOGGED guest contact, and the month's total is
capped at 50% of the uplift measured against a hidden group the team never sees. Occupancy
targets are a scoreboard: they move an employee's share between 30% and 40% and never pay
cash alone. Design: docs/superpowers/specs/2026-11-15-unit-targets-design.md.

Layout mirrors schedule/, ops/ and oncall/:
    engine.py  — PURE rules (delivered and tested; constants are owner-approved — do not edit)
    db.py      — tg_* tables inside the existing brain.db
    history.py — one-time seed import, nightly sync by month, blocked nights
    score.py   — the scoreboard: baselines, tiers, the gate, the rescue list
    book.py    — callable pool, hidden group, ranked call list, the logged contact, attribution
    money.py   — the month's payout sheet (like-with-like cap) and its approval row
    routes.py  — /api/targets/*, /api/book/*, the public consent box, dashboard splice
    page.py    — /my-targets and /my-book phone pages (zero backslashes)
    host.py    — the one bridge to bot.py + the four TG_* switches

Nothing here writes to payroll, the ERP or Hostaway.
"""

from . import engine, db, history, score, book, money, routes, page  # noqa: F401
from .host import HOST, wire, enabled, shadow, book_live, pool_channels  # noqa: F401
from .routes import register_routes  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "enabled", "shadow", "book_live", "pool_channels",
           "engine", "db", "history", "score", "book", "money", "routes", "page", "bootstrap"]


def bootstrap():
    try:
        db._ensure()
        print("[targets] ready: enabled=%s shadow=%s book_live=%s pool=%s"
              % (enabled(), shadow(), book_live(), ",".join(pool_channels())))
    except Exception as e:
        print("[targets] bootstrap error:", e)
