# -*- coding: utf-8 -*-
"""
reviewask — «رفع التقييم», Review Push. Every Ouja apartment above 4.75 on Airbnb.

Every checkout from a weak apartment (≤ 4.75, or fewer than 3 reviews) — or from any apartment
where the guest had a maintenance ticket during the stay — gets its own Discord ROOM. The room
drives two human touches with one-tap tools: a WhatsApp message on checkout day and a phone call
the next evening if no review has arrived. Every press is recorded against the presser, and the
room closes itself when the review lands. Spec: docs/superpowers/specs/2026-10-03-review-push-design.md

    engine.py  — PURE: the 4.75 line, eligibility, the clock, the presses, the words
    config.py  — env, read at call time (defaults correct — the owner never opens Railway)
    texts.py   — every Arabic word; button labels carry NO emoji (owner rule R2)
    db.py      — rv_* tables in brain.db (UNIQUE reservation, conditional-UPDATE transitions)
    flow.py    — the tick, rooms, presses, board, reports, the 7-day sweep (own thread pool)
    host.py    — the ONE bridge to bot.py (never `import bot`)
    routes.py  — /rv/<token> (public, one-tap WhatsApp) + /api/reviewask/* (login + permission)

Ships OFF: nothing posts until an admin runs /reviews-start.
"""

from . import engine, config, texts, db, flow, routes  # noqa: F401
from .host import HOST, wire  # noqa: F401

__all__ = ["engine", "config", "texts", "db", "flow", "routes", "HOST", "wire", "bootstrap",
           "register_routes"]


def bootstrap():
    """Tables + the template seed. Never raises into boot."""
    try:
        db._ensure()
        db.templates()
        print("[reviewask] live=%s board=%s category=%s"
              % (int(flow.live()), config.board_channel(), config.category()))
    except Exception as e:
        print("[reviewask] bootstrap error:", e)


def register_routes(app):
    routes.register(app)
