# -*- coding: utf-8 -*-
"""Dependency injection for the coverage module — same pattern as schedule/ and decor/.

coverage NEVER imports bot. bot.py hands it the few callables it needs, so the module
stays testable and a mistake in here cannot reach into the bot's globals.
"""

from types import SimpleNamespace

HOST = SimpleNamespace(
    dash_auth=None,        # (request) -> bool
    req_role=None,         # (request) -> role string
    json_response=None,    # (obj, status=200) -> web.Response
    load_json=None,        # (name, default) -> obj      (STATE_DIR)
    save_json=None,        # (name, obj) -> None
    listings=None,         # () -> list of listing store records
    teams=None,            # () -> list of cleaning-team dicts
    guide_units=None,      # () -> list of guide unit dicts (with listing_id)
    status_log=None,       # () -> oujact status events
    reports=None,          # () -> cleaning report dicts
    photos=None,           # () -> cleaning report photo dicts
    turnovers=None,        # (start, end) -> int  real Hostaway turnover count
    maps_key=None,         # () -> Google Maps API key or ""
    set_pin=None,          # (lid, link, lat, lng) -> bool   save one apartment's pin
    web=None,              # aiohttp.web (for the map-image response)
    tz=None,
)


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST


def call(name, *a, **kw):
    """Call an injected capability, or return None if bot.py never provided it."""
    fn = getattr(HOST, name, None)
    if not callable(fn):
        return None
    return fn(*a, **kw)
