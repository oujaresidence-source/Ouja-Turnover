# -*- coding: utf-8 -*-
"""
decor.host — the ONE bridge between this package and bot.py (schedule/host.py pattern).
bot.py calls decor.wire({...}) once at web-server start. The package never imports bot.
"""


class _Host:
    dash_auth = None         # (request) -> bool   any authenticated staff
    req_role = None          # (request) -> role string
    actor = None             # (request) -> display name
    json_response = None     # (data, status=200) -> web.Response
    web = None               # aiohttp web module
    state_dir = None
    tz = None
    now = None               # () -> tz-aware Riyadh datetime
    listings = None          # () -> {listing_id: name}
    inhouse = None           # (date) -> [reservation dicts]  targeted Hostaway query
    guide_units = None       # () -> [{slug, listing_id, listing_name}]
    notify = None            # (payload) -> None   Discord delivery, DRY-RUN by default

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("decor used '%s' before decor.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
