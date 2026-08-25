# -*- coding: utf-8 -*-
"""
pricecheck.host — the ONE bridge to bot.py (the kb/wifi/decor pattern). bot.py calls
pricecheck.wire({...}) once at web-server start; this package never imports bot.
"""


class _Host:
    dash_auth = None            # (request) -> bool
    json_response = None        # (data, status=200) -> web.Response
    web = None                  # aiohttp web module
    api_get = None              # (path, params=None) -> dict   raw Hostaway GET
    fetch_reservations_window = None   # (start_date, end_date, pad_days) -> [raw res]
    fetch_calendar_days = None  # (listing_id, start_date, end_date) -> [raw day]
    get_listings_map = None     # () -> {listing_id: name}

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("pricecheck used '%s' before pricecheck.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
