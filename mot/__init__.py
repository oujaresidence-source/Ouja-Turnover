# -*- coding: utf-8 -*-
"""
mot — «مطابقة وزارة السياحة», the Ministry of Tourism unit-standards compliance record.

Which of our units meets which of the 47 ministry standards, on what date, verified by whom
— as dated, photo-backed, immutable inspection ROUNDS, with every gap turned into a priced
purchase that gets bought and re-inspected.

    catalogue.py  — the 61/67 components as CODE with a version and stable keys
    engine.py     — PURE maths: two percentages, blockers, quote split, evidence gate
    db.py         — mot_* tables in brain.db; the one-open-round lock lives here
    routes.py     — /api/mot/* (manager) + /api/mot-t/{token} & /mot-check (inspector)
    page.py       — /mot manager page          check_page.py — /mot-check/{token} phone page
    photos.py     — local, shrunk evidence photos     report.py — the A4 evidence file

The invoice is a by-product. The dated, signed compliance record is the product.
"""

from .host import HOST, wire  # noqa: F401
from . import catalogue, db, engine, routes  # noqa: F401


def register_routes(app):
    routes.register(app)
