"""
Ouja Brain — the WhatsApp-marketing DECISION layer, built inside the existing bot.py app.

The Brain decides what campaign to run today, to exactly which guests, and how many; runs
every outbound through the Governor; and hands a ready package to the sender (CSV in Phase 1,
Karzoum later). It is READ-ONLY against all pricing/turnover/calendar state — it reaches the
host only through the capabilities injected by wire().

Usage from bot.py (inside start_web_server):
    import brain
    brain.wire({ ... host capabilities ... })
    brain.register_routes(app)
"""

from .host import HOST, wire as _wire_host
from . import db, settings, campaigns, members, signals, audience, governor, recommend, adapters, routes
from . import gaps, retier, playbook, cards, gap_routes

__all__ = ["wire", "register_routes", "HOST"]


def bootstrap():
    """Idempotent: create tables, seed settings + campaign catalog. Member seeding is heavier
    (it reads the guest CRM) so it happens lazily on first dashboard hit, not at startup."""
    try:
        db.init_db()
        settings.seed_defaults()
        campaigns.seed_campaigns()
    except Exception as e:
        print("[brain] bootstrap error:", e)


def wire(caps):
    """Inject bot.py capabilities, then seed settings + campaigns. Safe to call once."""
    _wire_host(caps)
    bootstrap()
    return HOST


def register_routes(app):
    routes.register(app)
    gap_routes.register(app)
