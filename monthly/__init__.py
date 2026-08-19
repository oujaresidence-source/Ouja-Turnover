# -*- coding: utf-8 -*-
"""
monthly — «التسعير الشهري», the monthly-rent engine and its owner justification.

WHAT IT ANSWERS
For one unit, for one month: the monthly rent we should charge in SAR, WHY that
number and not another, and what it means for the property owner compared with
the annual Ejar lease they would otherwise sign.

    engine.py  — PURE math. No network, no db, no clock. Every number in it is
                 reachable from a unit test with hand-written inputs.
    ejar.py    — annual-rent reference + the data trust ladder (gold/silver/bronze).
    attrs.py   — the 16 scored unit attributes and their starting betas.
    db.py      — monthly_* tables inside brain.db (the schedule/db.py pattern).
    data.py    — the ONLY file that talks to Hostaway, and only with GET.
    quote.py   + quote_render.py — the 6-page owner PDF.
    page.py    — /monthly-lab, the internal tab. ZERO BACKSLASHES.
    routes.py  — endpoints + guards.

WHY THE ENDPOINTS ARE /api/mrent/ AND NOT /api/monthly/
/api/monthly/* was already taken, and it is PUBLIC: config, featured, deals,
search, listing, quote and admin all serve the live guest site at /monthly with
no login. This package exposes owner economics — floors, margins, management
fees, an owner's Ejar position. Those two things must not share a URL prefix.
This is the same rule the knowledge base learned the hard way when /api/kbp/
had to be split out from /api/kb/: the public door and the private door are
different doors, and a prefix is a door.

READ-ONLY AGAINST HOSTAWAY, BY CONSTRUCTION
host.py wires no api_post and no api_put, so no code path in this package can
write a price. Computing a price and applying a price are separate acts, and
only the second one needs to be feared.

──────────────────────────────────────────────────────────────────────────────
DECISIONS ON RECORD — owner, 2026-08-19. Written down BEFORE the code, so they
are not re-decided later in a moment of enthusiasm.

1. THE LIVE SITE IS SWITCHED, NOT REPLACED.
   /monthly keeps its existing price path (calendar total less a configured
   discount). monthly_config.json gains `price_source`: "discount" | "engine".
   It SHIPS DEFAULTING TO "discount" — the day this is pushed, the live site
   behaves exactly as it did the day before. The engine path must return the
   same 9 keys monthly_pricing() returns, or the switch is not allowed to flip.

2. THE FLIP CRITERION (S14 exit condition).
   Flip to "engine" only after the number has been spot-checked on 10 units
   across different districts and can be defended out loud on each. If two
   owners push back in the first month, flip back to "discount".

3. THE ADVERTISING-LICENCE FILTER GOES LIVE END OF SEPTEMBER 2026 (S15 exit
   condition). A deferred compliance switch with no date never turns on. Until
   then the licence number is stored and its expiry is flagged, but nothing is
   hidden. Still open, and it gates the public side: confirm the فال scope
   covers التسويق and not only الوساطة.

4. «الإشغال المتعادل» IS MEASURED AGAINST THE NIGHTLY PATH.
   The occupancy the unit must reach, let nightly, to match what the owner nets
   from their annual lease. The monthly path has no occupancy term in it, so the
   figure cannot be derived from it. The PDF also carries the months-let
   break-even: how many months of the year the unit must be let monthly to beat
   the same lease — the more honest framing for a monthly pitch.
──────────────────────────────────────────────────────────────────────────────
"""

from .host import HOST, wire  # noqa: F401
from . import routes  # noqa: F401


def bootstrap():
    """Create tables and seed what can be seeded. Safe to call on every boot.
    Stays a no-op until S3 introduces db.py — a bootstrap that half-creates
    something is worse than one that does nothing."""
    return None


def register_routes(app):
    routes.register(app)
