# -*- coding: utf-8 -*-
"""
hatif — live availability answers on WhatsApp through Hatif (api.voxa.sa).

A guest writes their dates on WhatsApp; Hatif pushes the message to /hatif/webhook; this
package runs the SAME availability search the guest site uses (bot._gw_search — one calendar,
so WhatsApp and oujares.com can never disagree) and answers through Hatif's sendText.

Layout (mirrors stayhub/):
    config.py   — every HATIF_* env var, read live. Safe defaults: dry-run ON.
    parse.py    — PURE: a Najdi/English message → check-in, check-out, nights, guests, size, area
    engine.py   — PURE: signature check, phone normalisation, the reply text
    client.py   — the only network code: token cache, get conversation, assign, sendText
    db.py       — hatif_* tables inside brain.db (no phone numbers stored)
    service.py  — one inbound message → at most one answer (handle)
    routes.py   — POST /hatif/webhook (signed, public) + GET /api/hatif/status (login)
    answers.py  — the approved answer bank (answers_seed.json; $STATE_DIR/hatif_answers.json wins)
    brain.py    — the «reader»: AI picks a door, the words come from the bank or the live search
    firewall.py — PURE rules every reader reply must pass (count, booked, ready, price, blanks)

THE READER (2026-11-22) is SILENT in Phase 1: service.shadow composes the reply for every typed
message and posts it to Discord. It has NO send path at all — going live is a later, separate
change. HATIF_AI=0 turns it off.

THE TRAPS THIS PACKAGE CLOSES — do not simplify:
    * Hatif's webhook fires for OUR OWN outgoing messages too. Only direction=Inbound is ever
      answered, or the bot would talk to itself forever.
    * A button/list tap arrives as a Text message carrying `interactiveReply`. Those belong to
      the Hatif menu flow, never to this package.
    * The menu flow and this package must not both answer. Default gate = "assigned": only a
      conversation the flow handed to the bot's own Hatif seat (HATIF_BOT_USER_ID) is
      answered, and it is handed back (unassigned) right after, so the menu resumes.
    * The bot can only SHOW availability and price. It never says a booking is confirmed: an
      Airbnb booking is finished by the guest in Airbnb.
    * "Could not check" is never worded as "nothing available" (engine.build_reply).
    * HATIF_DRYRUN defaults to 1: nothing is sent, the would-be reply goes to Discord. With
      HATIF_TEST_NUMBERS set, live sends reach only those numbers.
    * The webhook fails closed: no HATIF_WEBHOOK_SECRET or a bad X-Voxa-Signature ⇒ 401.
    * One delivery is handled once (hatif_events primary key) — Hatif retries up to 5 times.
"""

from . import answers, brain, client, config, db, engine, firewall, parse, routes, service  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401


def bootstrap():
    """Create the tables. Safe to call more than once."""
    db._ensure()
    return {"configured": config.configured(), "dryrun": config.dryrun(), "gate": config.gate(),
            "webhook_secret": bool(config.webhook_secret())}
