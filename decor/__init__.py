# -*- coding: utf-8 -*-
"""
decor — «تنسيق الحفلات» (Ouja Moments decoration orders).

THE OWNER RULE THIS PACKAGE EXISTS TO PROTECT (2026-07-26):
    A guest tapping «أنا مهتم» in the guide creates NOTHING — no ticket, no thread, no task,
    no assignment, and nobody is notified except the DEC supervisor seeing a new line.
    ONLY the supervisor opens a request. Everything else — thread, deadlines, the cake job,
    escalation — begins at their action.

That rule is enforced structurally, not by discipline: leads and orders live in two separate
tables, the public endpoint has no code path that reaches `db.open_order`, and
tests/test_decor_flow.py counts every other table before and after a guest tap.

Layout mirrors schedule/ and guide/:
    packs.py   — reads decor_packs.json (STATE_DIR copy wins; owner edits it live)
    engine.py  — PURE rules: capability, override stamp, guest-input gate, cake deadlines
    db.py      — decor_* tables inside the existing brain.db
    routes.py  — public inquire (leads only) + supervisor endpoints (login + role gated)
    notify.py  — Arabic text for Discord; delivery is HOST.notify, DRY-RUN by default
"""

from . import db, engine, notify, packs, routes  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401
