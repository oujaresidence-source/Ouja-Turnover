# -*- coding: utf-8 -*-
"""
directpay — «التحصيل» direct-booking collection tickets.

THE OWNER RULE THIS PACKAGE EXISTS TO PROTECT (2026-09-10):
    Every direct reservation in Hostaway is an open debt until an ADMINISTRATOR uploads a
    file proving the money landed in StayHub and types the amount and the StayHub reference.
    Nobody else closes it — not the opener, not ops, not the bot. There is no plain
    "close anyway": the only shortcut («إغلاق بدون إثبات») is permanent, red and counted
    forever. StayHub is NEVER called by this code — this is a human attestation ledger.

The traps this package closes structurally (see CLAUDE.md «التحصيل»):
    start-date cutoff (persisted on first boot) · dry-run by default · per-tick cap ·
    UNIQUE(reservation_id) + once-claim + rebuild-from-channel-topics · _make_channel_spill ·
    proof scan FAILS CLOSED · proof bytes re-hosted under STATE_DIR · administrator-only gate
    (never manage_guild) · garbled DIRECTPAY_CLOSE_IDS ⇒ admins only · no auto-void on
    cancellation · no web close endpoint · persisted daily latch.

Layout mirrors decor/:
    config.py   — every DIRECTPAY_* env var, read live
    engine.py   — PURE rules: eligibility, variance, the state machine, aging, clocks, gate
    db.py       — directpay_* tables inside the existing brain.db
    proof.py    — the evidence file: find (fails closed), check, store the BYTES
    service.py  — reservations in → ledger + notifications out (poller = webhook path)
    notify.py   — Arabic text; delivery is HOST.notify, DRY-RUN by default
    routes.py   — /api/directpay/* read + note endpoints (login-gated); NO close endpoint
"""

from . import config, db, engine, notify, proof, routes, service  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401


def bootstrap():
    """Create the tables and seed the start date. Safe to call more than once."""
    db._ensure()
    return service.start_date()
