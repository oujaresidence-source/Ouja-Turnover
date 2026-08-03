# -*- coding: utf-8 -*-
"""
kb — «قاعدة المعرفة», the searchable single source of truth for units and owners.

The problem it exists to end: the operational facts about ~56 furnished units — who owns
which apartment, who pays the cleaning subscription and how much, when the owner gets paid
— live in one accountant's memory. A second accountant interrupts her dozens of times a
week to ask. The company has a bus factor of one.

    engine.py — PURE rules: the Arabic fold, the haystack, the completeness rule, enum
                validation, conflict detection. Tests drive this without a database.
    db.py     — kb_* tables inside the existing brain.db. Every write is audited, every
                delete is soft, and the haystack is rebuilt on every write.
    seed.py   — the one-time fill from seed_kb.json. Never re-runs over live edits.
    routes.py — /api/kb/*, behind login + the `kb` permission.

Deliberately NOT here: RAG, embeddings, a chatbot, a vector database. The dataset is 56
units. Exact-match plus substring search is faster, cheaper, and — unlike a language model
— cannot invent a cleaning amount that was never agreed.
"""

from .host import HOST, wire  # noqa: F401
from . import db, engine, routes, seed  # noqa: F401


def register_routes(app):
    routes.register(app)
