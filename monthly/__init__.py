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

4. THE OWNER-VERSUS-ANNUAL-LEASE COMPARISON IS OUT OF THE PRICING PATH.
   Superseded 2026-08-19. Ouja's owners are on revenue guarantees — they are not
   choosing between a yearly lease and us — so a gate built on that comparison
   answered a question nobody asks.
     * FINAL = max(FLOOR, MODEL). bound_by is 'floor' or 'model' only, and
       db.save_quote REFUSES any other value.
     * The gate math is kept, not deleted, in ejar.owner_annual_net for owner
       acquisition later. engine.py does not import it and a test asserts the
       pricing path cannot reach it.
     * Ejar becomes MARKET CONTEXT: our monthly price as a multiple of the
       district's annual-equivalent month. Shown, never acted on. A 2.8x is
       plausible for furnished and serviced; an 8x is a question worth being
       asked before an owner asks it.
     * `base` for the model price therefore comes from OUR OWN realised history.
       An annual-lease index feeding a variable called base_rate would be Ejar
       binding the price under a different name, invisibly.
     * BREAK-EVEN is months-let against the NIGHTLY path: how many months of the
       year this unit must be let monthly to match what it would have earned let
       nightly over the same period.
──────────────────────────────────────────────────────────────────────────────
"""

from .host import HOST, wire  # noqa: F401
from . import attrs, db, live, routes, seed, settings  # noqa: F401


def bootstrap():
    """Create the monthly_* tables. Safe to call on every boot: the schema is
    CREATE TABLE IF NOT EXISTS throughout.

    It deliberately does NOT seed attribute values. Seeding reads Hostaway, and
    a boot path that reaches the network is a boot path that can hang the bot;
    seeding is an explicit action from the page instead.

    Ordering-independent ON PURPOSE. Every db.py function calls _ensure() itself,
    so the tables get created on first real use whatever happens here. brain.wire()
    currently runs earlier in start_web_server than this does, but that is 400
    lines of a file several sessions edit at once, and this repo already carries a
    scar from boot code reaching the database before brain.wire() ran. So a
    not-yet-wired brain is a normal deferral here, not a failure.
    """
    try:
        db._ensure()
        print("[monthly] price source:", settings.apply_owner_flip(),
              "->", settings.price_source())
        return "created"
    except Exception as e:
        if "before brain.wire()" in str(e):
            return "deferred"               # first real query will create them
        print("[monthly] table bootstrap failed (tables created on first use):", e)
        return "deferred"


def register_routes(app):
    routes.register(app)
