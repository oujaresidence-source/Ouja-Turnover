# -*- coding: utf-8 -*-
"""
monthly.host — the ONE bridge to bot.py (the pricecheck/kb/wifi/decor pattern).
bot.py calls monthly.wire({...}) once at web-server start; this package never
imports bot.

Every capability below is READ-ONLY against Hostaway. There is deliberately no
api_post and no api_put in this list: «التسعير الشهري» computes and explains a
price, it never writes one. Applying a price is _pe_apply_night's job in bot.py
and is a separate, owner-approved action. A capability that cannot be reached
cannot be misused, so the safest place to enforce read-only is right here.
"""


class _Host:
    # --- request plumbing -------------------------------------------------
    dash_auth = None            # (request) -> bool          login gate
    req_role = None             # (request) -> str           'admin' | 'ops' | 'viewer' | ...
    actor = None                # (request) -> str           who is acting, for audit rows
    json_response = None        # (data, status=200) -> web.Response
    web = None                  # aiohttp web module

    # --- clock ------------------------------------------------------------
    tz = None                   # ZoneInfo
    now = None                  # () -> datetime in Riyadh

    # --- Hostaway, GET ONLY -----------------------------------------------
    api_get = None              # (path, params=None) -> dict
    # CLAUDE.md trap #4: get_reservations_cached() truncates at ~6,000 rows and
    # silently drops the NEWEST months. It produced a wrong owner statement once
    # (18,842 instead of 48,114). A monthly price built on a truncated history is
    # a wrong price sent to an owner, so the cache is NOT wired in here at all.
    fetch_reservations_window = None   # (start, end, pad_days=45) -> [raw res]
    fetch_calendar_days = None         # (listing_id, start, end) -> [raw day]
    get_listings_map = None            # () -> {listing_id: name}

    # --- state files ------------------------------------------------------
    load_json = None            # (name, default) -> obj
    save_json = None            # (name, obj) -> None
    state_path = None           # (name) -> absolute path

    # --- shared, already-tested machinery (consume, never re-implement) ----
    base_url = None             # () -> str  resolver: env -> auto-captured -> oujares.com
    saudi_events = None         # SAUDI_EVENTS
    pe_band = None              # (adrs) -> realized ADR band
    pe_build_dataset = None     # (reservations, units, today) -> night-level dataset

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("monthly used '%s' before monthly.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
