"""
Ouja Studio «استوديو عوجا» — TikTok content-idea factory.

Mines the last ~300 REAL guest conversations from Hostaway (inquiries and
dead-after-5-messages threads excluded), extracts story-worthy situations with
Claude (cheap triage pass → premium story pass), then turns each story into
ready-to-shoot idea cards: spoken hook (first words on camera), visual hook
(on-screen title + subtitle), beat script, CTA, niche-vs-escape audience tag —
all grounded in the researched hook playbook (studio/playbook.py).

Same DI pattern as watchdog/schedule/finchat: bot.py calls studio.wire({...})
then studio.register_routes(app). Storage reuses brain.db (studio_* tables).
READ-ONLY toward the business: never writes to Hostaway, never messages guests.
"""

from .host import HOST, wire as _wire_host
from . import db, engine, routes, mine, notify, ideas  # noqa: F401
from . import learn, hooks, plan, external, internal    # noqa: F401  (v3 signal bus)
from . import rank, mobile                              # noqa: F401  (phone page /s/{token})

__all__ = ["wire", "register_routes", "HOST", "engine", "db", "mine", "notify", "ideas",
           "learn", "hooks", "plan", "external", "internal", "rank", "mobile"]


def wire(caps):
    _wire_host(caps)
    try:
        db._ensure()
        print("[studio] db ready")
    except Exception as e:
        print("[studio] bootstrap error:", e)
    return HOST


def register_routes(app):
    routes.register(app)
