# -*- coding: utf-8 -*-
"""
recovery.host — the ONE bridge between this package and bot.py.

Same pattern as schedule/, decor/, ops/ and coverage_study/. This package NEVER does
`import bot`: bot.py runs as __main__, so importing it by name would boot a second Discord
client. bot.py calls recovery.wire({...}) once at web-server start and hands over only the
few callables this feature needs.
"""

from types import SimpleNamespace

HOST = SimpleNamespace(
    # --- web / auth (the same objects every other package gets) ---
    dash_auth=None,        # (request) -> bool     any authenticated staff
    req_role=None,         # (request) -> role string
    actor=None,            # (request) -> display name of the logged-in user
    json_response=None,    # (obj, status=200) -> web.Response
    web=None,              # aiohttp web module
    tz=None,

    # --- the public origin for the /call/{token} link ---
    # bot.py already resolves this itself (_dispatch_base_url: env override -> the address
    # auto-captured from a real incoming request -> the site's own domain), so the owner
    # never has to supply it. Injected rather than re-derived so there is one answer.
    public_base=None,      # () -> 'https://…'

    # --- the guest verdict. recovery NEVER re-scores a guest: /guest is the one source. ---
    guest_rows=None,       # () -> the rows build_guests_rows() produces
    reservation_info=None, # (reservation_id) -> {'channel','phone','confirmation',...}
    conversation_msgs=None,# (conversation_id) -> raw Hostaway messages
    msg_is_inbound=None,   # (msg) -> bool
    msg_time=None,         # (msg) -> iso string

    # --- who permanently owns an apartment (schedule.owners) ---
    unit_owner=None,       # (listing_id, name) -> owner name or None

    # --- delivery ---
    notify=None,           # (payload) -> None    Discord side, DRY-RUN aware
    open_maintenance=None, # (payload) -> ticket id   the EXISTING maintenance system
)


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST


def call(name, *a, **kw):
    """Call an injected capability, or return None if bot.py never provided it. A missing
    capability degrades the feature; it must never raise into the web server."""
    fn = getattr(HOST, name, None)
    if not callable(fn):
        return None
    return fn(*a, **kw)
