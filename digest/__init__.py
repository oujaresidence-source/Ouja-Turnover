# -*- coding: utf-8 -*-
"""digest — the weekly «وش صاير بالرياض» weekend digest.

Same DI pattern as studio/schedule: bot.py calls digest.wire({...}) then
digest.register_routes(app). Storage reuses brain.db (digest_* tables). Everything
that touches the network goes through HOST.http (digest.net_live) so the whole
pipeline runs offline in tests. Nothing publishes without the owner's tap."""

from .host import HOST, wire as _wire_host
from . import db, dates, schedule, notify, net_live  # noqa: F401  — the light modules bot.py reaches for

__all__ = ["wire", "register_routes", "bootstrap", "HOST", "db", "dates", "schedule", "notify", "net_live",
           "build", "approval", "routes", "rank", "art", "guard", "voice", "schema"]

# The heavy chain (build → render → segno/Pillow/Chromium) is resolved on first use, so an
# import problem there degrades to «build unavailable» (see routes.render_ready) instead of
# taking the whole package — and every /digest route — down. bot.py writes `_digest.build`,
# `_digest.approval`; PEP 562 makes those attribute lookups import the module on demand.
_LAZY = {"build", "approval", "routes", "rank", "art", "guard", "voice", "schema", "links", "places"}


def __getattr__(name):
    if name in _LAZY:
        import importlib
        mod = importlib.import_module("." + name, __name__)
        globals()[name] = mod
        return mod
    raise AttributeError("module 'digest' has no attribute %r" % name)


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
