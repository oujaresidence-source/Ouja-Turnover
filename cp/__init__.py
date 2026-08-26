# -*- coding: utf-8 -*-
"""
cp/ — the public company profile at /cp (seeds §0, superprompt §3).

The Arabic edition is canonical and ships first. Its copy is the approved
document, ported byte-for-byte by cp/tools/tokenise_source.py; its figures come
from cp.stats with a source and a date attached to each one; and every rendered
page passes through cp.guard, which fails on any figure the seeds file withholds.

bot.py calls cp.wire({...}) then cp.register_routes(app).
"""
from .host import HOST, wire as _wire_host
from . import guard, stats, page, routes, snapshot  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "guard", "stats", "page", "snapshot"]


def wire(caps):
    _wire_host(caps)
    return HOST


def register_routes(app):
    routes.register(app)
