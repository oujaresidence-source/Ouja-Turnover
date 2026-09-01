# -*- coding: utf-8 -*-
"""digest — the weekly «وش صاير بالرياض» weekend digest.

Same DI pattern as studio/schedule: bot.py calls digest.wire({...}) then
digest.register_routes(app). Storage reuses brain.db (digest_* tables). Everything
that touches the network goes through HOST.http (digest.net_live) so the whole
pipeline runs offline in tests. Nothing publishes without the owner's tap."""

from .host import HOST, wire as _wire_host
from . import db  # noqa: F401

__all__ = ["wire", "register_routes", "bootstrap", "HOST", "db"]


def bootstrap():
    try:
        db._ensure()
        print("[digest] db ready")
    except Exception as e:
        print("[digest] bootstrap error:", e)


def wire(caps):
    _wire_host(caps)
    bootstrap()
    return HOST


def register_routes(app):
    from . import routes
    routes.register(app)
