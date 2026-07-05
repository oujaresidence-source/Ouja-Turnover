"""
Ops Watchdog «الرقيب التشغيلي» — read-only operations monitor.

Same DI pattern as schedule/brain: a pure deterministic engine (watchdog.engine) computes
flags + renders phone-first Discord text; storage reuses brain.db (watchdog_* tables);
bot.py calls watchdog.wire({...}) then watchdog.register_routes(app) and runs the 30-min
cycle + Discord posting itself. This package NEVER writes to Hostaway and NEVER messages
guests — it only observes and reports.
"""

from .host import HOST, wire as _wire_host
from . import db, engine, routes  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "engine", "db"]


def wire(caps):
    _wire_host(caps)
    try:
        db._ensure()
        print("[watchdog] db ready")
    except Exception as e:
        print("[watchdog] bootstrap error:", e)
    return HOST


def register_routes(app):
    routes.register(app)
