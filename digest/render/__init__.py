# -*- coding: utf-8 -*-
"""digest.render — payload → HTML → PDF (810×1440 pt) + story PNG (1080×1920) + JSON.

tokens.py  the :root palette, the ONLY place a colour is declared
fonts.py   @font-face with file:// urls into fonts/ (Chromium subsets + embeds)
html.py    pure: payload -> html string. No network, no host, no db.
audit.py   overflow / clip / link-pill-size checks, run on EVERY build
build.py   guard -> chromium -> pdf + png + json (+ layout fingerprint)
test_render_frozen.py + golden_fingerprint.json — the look, locked."""
