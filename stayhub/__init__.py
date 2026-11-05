# -*- coding: utf-8 -*-
"""
stayhub — Ouja as a CHANNEL PARTNER on the StayHub Connectivity API (v2), like Gathern/Airbnb.
Owner decision 2026-11-05: stay on Hostaway; every confirmed Airbnb reservation of a mapped unit
is pushed into StayHub so StayHub holds the full record per unit (ID verification link,
Ministry of Tourism reporting, Shomoos from the StayHub host app).

Layout (mirrors directpay/):
    config.py  — every STAYHUB_* env var, read live. No credentials ⇒ nothing runs.
    client.py  — the only network code: OAuth token cache + the per-error-code retry policy
    engine.py  — PURE rules: eligibility, plan, snapshot, phone, error playbook, HMAC check
    db.py      — stayhub_* tables inside brain.db (no guest names / phones stored)
    sync.py    — the /sync cursor loop → local catalog/day cache
    push.py    — Hostaway reservation → probe → hold → confirm / modify / cancel
    probe.py   — our answer to StayHub's sync probe (required, certification)
    recon.py   — the daily reconciliation report + Discord summary of refused bookings
    notify.py  — Arabic Discord lines (delivery = HOST.notify)
    routes.py  — /stayhub/webhook + /stayhub/sync-probe (signed, public) and /api/stayhub/*

THE TRAPS THIS PACKAGE CLOSES — do not simplify:
    * only units an admin MAPPED are ever pushed (POST /api/stayhub/map) — no auto-mapping
    * only Airbnb by default (STAYHUB_CHANNELS) — direct bookings already live in StayHub
    * the hold snapshot is StayHub's own probe answer, never the Airbnb price (their Q1 answer);
      financial.total on confirm is the Airbnb amount
    * UNIQUE(ha_reservation_id) + a per-reservation lock — the poller and the Hostaway hook can
      never push the same reservation twice
    * a refused booking is retried slowly (STAYHUB_RETRY_REJECTED_HOURS), reported once in
      Discord and every day in the reconciliation, then parked as «يحتاج تدخل»
    * every signed endpoint fails closed: no secret or a bad signature ⇒ 401
"""

from . import client, config, db, engine, notify, probe, push, recon, routes, sync  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401


def bootstrap():
    """Create the tables. Safe to call more than once."""
    db._ensure()
    return {"configured": config.configured(), "dryrun": config.dryrun(), "mapped": len(db.maps())}
