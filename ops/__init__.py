# -*- coding: utf-8 -*-
"""
ops — «نظام الالتزام», the accountability layer (Phase 1: weekly-report warnings).

THE PRINCIPLE THIS PACKAGE EXISTS TO PROTECT
    The system accuses. Humans only forgive.
There is no endpoint, command or button anywhere in here that lets a person issue a warning.
`db.issue_warning` is the only INSERT into ops_warnings and it is reachable only from the
deadline path in notify.tick(). A team leader's three possible actions are excuse, waive and
accept an appeal — all of them mercy.

MONEY RULE
    Warnings SUBTRACT commission. Nothing here ever adds a bonus (that is Phase 3's job) and
    nothing here writes to payroll or the ERP: the multiplier is computed and displayed.

Layout mirrors schedule/ and decor/:
    engine.py — PURE rules: multiplier, deadline, ladder clock, forgiveness, the verdict
    db.py     — ops_* tables inside the existing brain.db (one obligation = one warning, by UNIQUE)
    notify.py — phase 1 ladder + Arabic wording; delivery is HOST.notify, DRY-RUN by default
    turnover.py — phase 2 «القفل»: check-in-anchored nudges, one message edited in place
    scorecard.py — phase 3 «كرت التقييم»: monthly 1-5, BONUS only, owner-approved
    routes.py — /api/ops/* (login + admin/ops) and the token-gated appeal endpoints
    page.py   — /compliance (login) and /appeal/{token} (public, token, zero backslashes)
"""

from . import engine, db, notify, turnover, scorecard, routes, page  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "engine", "db", "notify", "turnover",
           "scorecard", "routes", "page"]


def bootstrap():
    try:
        db._ensure()
        print("[ops] ready: warn-dryrun=%s enabled=%s · nudge-dryrun=%s enabled=%s"
              % (notify.dryrun(), notify.enabled(), turnover.dryrun(), turnover.enabled()))
    except Exception as e:
        print("[ops] bootstrap error:", e)
