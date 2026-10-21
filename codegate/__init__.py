# -*- coding: utf-8 -*-
"""
codegate — «تسليم الرموز». On gated listings the guest replies «أوافق» to the house-rules
message and the employee covering the unit that day releases the door code BY HAND.

    engine.py — PURE: replies, alerts, permission, every word
    db.py     — codegate_* tables in brain.db
    host.py   — HOST bridge filled by bot.py (codegate.wire)
    flow.py   — tick + the two buttons

The bot never decides agreement and never sends a code (owner ruling 2026-10-21).
"""

from . import engine, db, flow  # noqa: F401
from .host import HOST, wire  # noqa: F401

__all__ = ["engine", "db", "flow", "HOST", "wire", "bootstrap"]


def bootstrap():
    try:
        db._ensure()
        print("[codegate] enabled=%s units=%d" % (int(flow.enabled()), len(flow.units())))
    except Exception as e:
        print("[codegate] bootstrap error:", e)
