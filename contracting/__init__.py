# -*- coding: utf-8 -*-
"""
contracting — «المقاولات», Ouja Design's contracting projects (owner plan 2026-11-23).

A signed quote becomes a project: each quote line gets ONE date, list order = work order.
«ابدأ» is refused until owner + unit + site supervisor + signed + paid + dates in order.
Then a Discord channel per project (category «المقاولات») and reminders that only close with
an answer: 2 days before → the due day 4 PM «خلص؟» → 7 PM Asil → next morning Faisal.
«خلص» closes a line only with photos. Never a reminder on Friday.

    engine.py  PURE rules (dates, gate, schedule) — tests/test_contracting_engine.py
    db.py      contracting_* tables in brain.db; claim() = one key, one message, ever
    notify.py  the words + tick() + button handlers; live by default; CONTRACTING_DRYRUN=1 = rehearsal
    routes.py  /api/contr/* (login + «contr» permission + admin/ops for writes)
    seed.py    the two signed projects of 22 Nov 2026 and the team
    static/contracting_tab.js   the dashboard tab (a real file: no backslash trap)
"""

from . import db, engine, notify, routes, seed  # noqa: F401
from .host import HOST, wire  # noqa: F401
from .routes import register_routes  # noqa: F401
