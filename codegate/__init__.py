# -*- coding: utf-8 -*-
"""
codegate — «تسليم الرموز». On gated listings the guest replies «أوافق» to the house-rules
message; the employee covering the unit that day presses one button and the bot sends the door
code (or records one sent by hand). Spec §9, revision 2.

    engine.py — PURE: replies, alerts, permission, every word
    db.py     — codegate_* tables in brain.db
    host.py   — HOST bridge filled by bot.py (codegate.wire)
    flow.py   — tick, room placement/holds/closes, the send/manual/undo buttons

The bot never decides agreement; it sends a code only when a person presses «✅ وافق — أرسل
الرمز» on a live gated unit (owner ruling 2026-10-22, replacing 2026-10-21's "never sends").
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
