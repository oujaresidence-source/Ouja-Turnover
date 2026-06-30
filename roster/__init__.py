"""
Ouja Auto-Coverage Duty Roster — the "who covers which unit today" decision layer, built
inside the existing bot.py app (same DI pattern as the Brain).

The engine (roster.engine) is a pure, deterministic single source of truth; both front-ends
(the dashboard tab + the standalone /roster page) and every Discord notification render from
it, so the numbers can never disagree. Storage reuses brain.db (roster.db). bot.py calls
roster.wire({...}) once at web-server start, then roster.register_routes(app).
"""

from .host import HOST, wire as _wire_host
from . import db, engine, seed, hostaway, notify, routes, page  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "engine"]


def bootstrap():
    """Idempotent: create roster tables + seed from the real ops data. Safe to call once."""
    try:
        db._ensure()
        rep = seed.seed_all()
        print("[roster] seeded: +%d employees, +%d properties; owners=%s"
              % (rep.get("employees_added", 0), rep.get("properties_added", 0),
                 rep.get("owner_counts")))
        for n in rep.get("notes", []):
            print("[roster] NOTE:", n)
    except Exception as e:
        print("[roster] bootstrap error:", e)


def wire(caps):
    _wire_host(caps)
    bootstrap()
    return HOST


def register_routes(app):
    routes.register(app)
