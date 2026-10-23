# -*- coding: utf-8 -*-
"""
rrdesk — «طلبات سام» (RR Desk): translation in RR ticket rooms, Sam's requests tracked with an
owner, SLAs and a reminder ladder, and misses that become ops warnings (dry-run money).

Spec: docs/superpowers/specs/2026-10-24-rrdesk-design.md · Debug: rrdesk/DEBUG.md

    engine.py     PURE rules (language, skips, state machine, working-minute SLAs, ladder,
                  judge, owner order, KPIs, calibration)
    db.py         rrdesk_* tables inside brain.db (idempotency by UNIQUE, not by care)
    translate.py  phrase table → cache → daily cap → one Haiku call
    flow.py       messages, presses, the tick; the ONLY ops warning call (_warn)
    outbox.py     every Discord side effect, claimed atomically, backed off 1/5/15/60
    bridge.py     the only file that touches discord.py objects
    texts.py      every word sent (Najdi for staff, plain English for Sam)
    study.py      the read-only history study (also /rrdesk-study, monthly)
    routes.py     /api/rrdesk/* (login + «rrdesk»), /rrdesk/health (public, counts only)
    replay.py     python3 -m rrdesk.replay <room.json> — a real room through the engine offline
NEVER `import bot` (bot.py runs as __main__). Zero backslashes in this package.
"""

from . import engine, db, texts, translate, outbox, flow, study, routes, bridge  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401

__all__ = ["wire", "register_routes", "HOST", "engine", "db", "texts", "translate", "outbox",
           "flow", "study", "routes", "bridge", "bootstrap"]


def bootstrap():
    try:
        db._ensure()
        print("[rrdesk] ready: translate=%s requests=%s ladder=%s warn_live=%s force_off=%s sam=%s"
              % (flow.switch("translate"), flow.switch("requests"), flow.switch("ladder"),
                 flow.switch("warn_live"), flow.switch("force_off"), ",".join(flow.sam_ids()) or "?"))
    except Exception as e:
        print("[rrdesk] bootstrap error:", e)
