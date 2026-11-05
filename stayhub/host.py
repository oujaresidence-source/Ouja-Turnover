# -*- coding: utf-8 -*-
"""
stayhub.host — the ONE bridge between this package and bot.py (directpay/host.py pattern).
bot.py calls stayhub.wire({...}) once at web-server start. The package never imports bot,
never imports discord. It talks to StayHub itself (client.py, requests) and to Hostaway and
Discord only through the capabilities below.
"""


class _Host:
    dash_auth = None            # (request) -> bool          any authenticated staff
    req_role = None             # (request) -> role string   ("admin" may edit the unit map)
    req_actor = None            # (request) -> display name
    json_response = None        # (data, status=200) -> web.Response
    web = None                  # aiohttp web module
    run = None                  # async (fn, *a) -> result   bot.web_thread (request handlers)
    background = None           # (fn) -> None   run a blocking fn off the loop, fire-and-forget
    now = None                  # () -> tz-aware Riyadh datetime
    listings = None             # () -> {listing_id: internal name}
    notify = None               # (text) -> None   one Discord message; None in tests
    log_event = None            # (category, text) -> None   the dashboard activity feed
    finance_channel = None      # (reservation) -> "direct" | "airbnb" | "other"  (bot._finance_channel)
    confirmed_statuses = None   # () -> set   zero-arg lambda: a mutable bot global, never held stale
    ha_reservations_window = None   # (param_start, param_end, start_iso, end_iso) -> [reservations]
    ha_reservation = None       # (reservation_id) -> reservation dict or None   ONE targeted GET

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("stayhub used '%s' before stayhub.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
