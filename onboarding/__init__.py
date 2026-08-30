# -*- coding: utf-8 -*-
"""
«ضم الوحدات» — Unit Onboarding & Handover Gate.

The 7-stage account-management process, from first client contact to handing a unit to the
operations team, as a surface that enforces itself: the checklist generates on its own, every
task ends in a resolution, at most two ops people carry a project, and the unit cannot be
PUBLISHED to operations until every piece of context ops will need is actually filled in.

Same DI pattern as schedule / decor: a pure engine (onboarding.engine) is the single source of
truth for every rule; storage reuses brain.db (onboarding.db, tables onb_*). bot.py calls
onboarding.wire({...}) then onboarding.register_routes(app).

It LINKS to «تجهيز الشقق» (pmo), it does not merge with it: a PMO task is a furniture line item
from a supplier PDF, an onboarding task is a process step with an owner role and a resolution.
Same word, different animal. The single merge point is stage-4 task s4.13.
"""

from .host import HOST, wire as _wire_host
from . import db, catalogue, engine, routes, page, emp_page  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "engine", "catalogue", "db"]


def bootstrap():
    try:
        db._ensure()
        c = db.counts()
        print("[onboarding] ready: projects=%d active=%d published=%d tasks=%d"
              % (c.get("projects", 0), c.get("active", 0), c.get("published", 0),
                 c.get("tasks", 0)))
    except Exception as e:
        print("[onboarding] bootstrap error:", e)


def wire(caps):
    _wire_host(caps)
    bootstrap()
    return HOST


def register_routes(app):
    routes.register(app)
