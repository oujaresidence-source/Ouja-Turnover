# -*- coding: utf-8 -*-
"""
staff — «عوجا فريق»: the employees' phone app at /team.

Layout mirrors schedule/, targets/ and oncall/:
    engine.py  — PURE: one employee's day from data bot.py already holds (tested)
    gather.py  — collects the day from bot.py bridges (caches/local tables only)
    routes.py  — /team, its manifest, GET /api/staff/today (login; read-only)
    page.py    — the app itself (ZERO backslashes: a normal triple-quoted string)
    host.py    — the one bridge to bot.py + the STAFF_ENABLED switch

Nothing here writes. It never calls Hostaway: every input is a cache or a local table.
"""

from . import engine, gather, routes, page  # noqa: F401
from .host import HOST, wire, enabled  # noqa: F401
from .routes import register_routes  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "enabled", "engine", "routes", "page"]
