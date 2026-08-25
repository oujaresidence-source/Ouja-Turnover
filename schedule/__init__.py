"""
Employee Schedule & Coverage Calendar — تقويم موظفي عوجا.

A native feature inside the bot.py app (same DI pattern as the Brain): a pure, deterministic
engine (schedule.engine) is the single source of truth; the dashboard tab, the standalone
/team-calendar page, and the optional ops summary all render from it. Storage reuses brain.db
(schedule.db, tables schedule_*). bot.py calls schedule.wire({...}) then schedule.register_routes(app).
"""

from .host import HOST, wire as _wire_host
from . import db, engine, seed, notify, routes, page, coverage, owners  # noqa: F401
from .coverage import cover_emoji_for_listing  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "engine", "coverage", "cover_emoji_for_listing"]


def bootstrap():
    try:
        db._ensure()
        rep = seed.seed_if_empty()
        print("[schedule] ready: employees=%d apartments=%d (seeded=%s)"
              % (rep.get("employees", 0), rep.get("apartments", 0), rep.get("seeded")))
    except Exception as e:
        print("[schedule] bootstrap error:", e)


def wire(caps):
    _wire_host(caps)
    bootstrap()
    return HOST


def register_routes(app):
    routes.register(app)
