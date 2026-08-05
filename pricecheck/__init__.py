# -*- coding: utf-8 -*-
"""
pricecheck — «فحص الأسعار», the price-disagreement examiner.

THE PROBLEM IT EXISTS TO END (owner, 2026-08-05)
An employee creates a manual direct booking in the Hostaway mobile app and edits the
price. Afterwards the Calendar shows one number and Financial Reporting → Analytics
and Reporting → Rental Activity → «Rental Revenue» shows another for the same stay.
Nobody knows how many bookings are affected, because the ones anyone noticed were
already corrected by hand — so the tool has to find them on its own.

THE OWNER'S RULE: THE CALENDAR IS THE TRUTH.

    engine.py — PURE rules. Which nights belong to a stay, which numbers are money,
                which Hostaway field tracks the calendar. Unit-tested, no network.
    scan.py   — the only file that talks to Hostaway, and only with GET.
    routes.py — /pricecheck and GET /api/pricecheck/scan, owner-only.
    page.py   — the page. ZERO BACKSLASHES (see the note at its top).

READ-ONLY, ON PURPOSE. This package contains no write of any kind. Correcting a price
is a separate step the owner approves separately — a tool that can both accuse and
change is a tool that can quietly change the wrong thing.
"""

from .host import HOST, wire  # noqa: F401
from . import engine, page, routes, scan  # noqa: F401


def register_routes(app):
    routes.register(app)
