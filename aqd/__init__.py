# -*- coding: utf-8 -*-
"""
«العقود» (aqd, from عقد) — survey → filled operating contract → e-sign link → countersign.

An employee answers a short survey; the answers fill the owner's frozen legal template (v2.1);
the client opens a token link on a phone, passes a last-4 identity check, reads, draws a
signature and signs; Ouja is notified; an admin countersigns and the final PDF is sealed.
Modelled on DocuSign / Adobe Sign (link per signer, access check, immutable hash, evidence page).

Same DI pattern as onboarding / permits: bot.py calls aqd.wire({...}) then
aqd.register_routes(app); nothing here imports bot.py.

    catalogue.py — the survey (single source)       engine.py — PURE rules, render, states
    db.py        — aqd_* tables in brain.db          files.py  — $STATE_DIR/aqd/<id>/ artifacts
    pdf.py       — shared Chromium, HTML fallback    notify.py — Arabic texts, once-only latch
    routes.py    — /api/aqd/*, /api/aqd-t/*, /sign/  sign_page.py — the public page shell
"""

from .host import HOST, wire as _wire_host
from . import catalogue, config, db, engine, files, notify, pdf, routes, sign_page  # noqa: F401

__all__ = ["wire", "register_routes", "bootstrap", "HOST", "engine", "catalogue", "db"]


def bootstrap():
    try:
        db._ensure()
        n = len(db.contracts())
        print("[aqd] ready: contracts=%d template=%s approved=%s"
              % (n, config.template_name(), routes.is_approved()))
    except Exception as e:
        print("[aqd] bootstrap error:", e)


def wire(caps):
    _wire_host(caps)
    bootstrap()
    return HOST


def register_routes(app):
    routes.register(app)
