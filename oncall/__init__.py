# -*- coding: utf-8 -*-
"""
oncall — «المناوبة», the evening on-call rotation (17:00-24:00).

Spec: docs/superpowers/specs/2026-10-03-oncall-rotation-design.md

    engine.py — PURE rules: the fair rotation, check times, miss ladder, ownership, swaps
    db.py     — oncall_* tables inside brain.db (idempotency by UNIQUE, not by care)
    roster.py — who can work tonight (Employee Calendar + ops Discord ids) and the supervisor
    texts.py  — every Arabic word the feature sends
    notify.py — the minute tick + button/hook handlers; the ONLY ops warning call site
    routes.py — /api/oncall/* (login + «oncall» permission; writes re-check admin/ops)
    static/oncall_tab.js — the dashboard tab (a real file: no DASHBOARD_HTML backslash trap)
"""

from . import engine, db, roster, texts, notify, routes  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401
