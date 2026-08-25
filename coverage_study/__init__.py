# -*- coding: utf-8 -*-
"""تغطية التنظيف — Cleaning Coverage.

A read-only study of where every apartment is, which crew cleans it, how OujaCT has
actually performed since its first logged day, and how many more people it would take
to cover everything in-house instead of paying third-party companies.

Same shape as schedule/ and decor/: a pure engine (coverage_study.engine) does all the maths
and is locked by tests/test_coverage_engine.py; bot.py calls coverage_study.wire({...}) then
coverage_study.register_routes(app). This package never imports bot.
"""

from .host import HOST, wire as _wire_host
from . import engine, geo, routes  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "engine", "geo"]


def wire(caps):
    return _wire_host(caps)


def register_routes(app):
    routes.register(app)
