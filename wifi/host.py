# -*- coding: utf-8 -*-
"""
wifi.host — the ONE bridge between this package and bot.py (decor/host.py pattern).
bot.py calls wifi.wire({...}) once at web-server start. The package never imports bot.
"""


class _Host:
    dash_auth = None         # (request) -> bool   any authenticated staff
    req_role = None          # (request) -> role string
    actor = None             # (request) -> display name
    json_response = None     # (data, status=200) -> web.Response
    web = None               # aiohttp web module
    tz = None
    now = None               # () -> tz-aware Riyadh datetime
    listings = None          # () -> {listing_id: apartment name}
    permanent_map = None     # () -> schedule.owners.permanent_map()  (who owns which unit)

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("wifi used '%s' before wifi.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
