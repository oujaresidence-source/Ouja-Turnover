# -*- coding: utf-8 -*-
"""
checkout — «متابعة الخروج», hotel-style due-out control for every turnover room.

The ops manager tracked every checkout in her head: who left, who hasn't, whether somebody
reached the guest, where the cleaning is. This package moves that into the system, so each
responsible person is visibly accountable for their own apartment — and she gets NO new
messages. There is no escalation to her or to the owner; visibility is one live board channel
plus reminders inside the apartment's own room.

Layout mirrors ops/:
    engine.py — PURE: state machine, the clock, the late-exit cap, risk, the per-person report
    texts.py  — PURE: every Arabic/English word, the only source of wording
    db.py     — cw_* tables inside the existing brain.db (work_key PRIMARY KEY = one card)
    host.py   — the HOST bridge filled by bot.py (checkout.wire)
    flow.py   — the tick, the answers, WhatsApp, Airbnb, board, 17:00 summary, risk, demo

Ships OFF: nothing is posted until an admin runs /checkout-start.
"""

from . import engine, db, texts, flow  # noqa: F401
from .host import HOST, wire  # noqa: F401

__all__ = ["engine", "db", "texts", "flow", "HOST", "wire", "bootstrap"]


def bootstrap():
    try:
        db._ensure()
        print("[checkout] live=%s airbnb=%s board=%s"
              % (int(flow.live()), int(flow.airbnb_enabled()), flow.board_channel_name()))
    except Exception as e:
        print("[checkout] bootstrap error:", e)
