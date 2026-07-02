# -*- coding: utf-8 -*-
"""
guide — دليل الشقق (in-house Guide Engine).

Brings the guest guide (oujaguide.netlify.app — Netlify + Supabase) in-house:
  * guide/db.py        — guide_units + guide_entries inside brain.db
  * guide/importer.py  — one-shot import from the Supabase CSV export
                         (supabase_export_listings.csv) + Google-Drive media
  * guide/templates/guide.html — the LIVE site reproduced 1:1 (dark warm-brown
                         theme, AR/EN, الإرشادات / لحظات عوجا / أرقام الطوارئ),
                         data now served from our DB instead of Supabase
  * routes (wired from bot.py) — public /guide, /guide/{slug},
    /guide/data.json (+ /data.json for the elite-map geo compat), media files,
    and login-gated admin APIs.

The gap loop: watchman «نقص في الدليل» tickets gain an «أضِفها للدليل» button
that writes a guide_entries FAQ row — closing guest-question → guide loop."""

from . import db, importer, routes  # noqa: F401
from .routes import register_routes, wire  # noqa: F401
