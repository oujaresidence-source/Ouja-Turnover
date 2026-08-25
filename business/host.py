# -*- coding: utf-8 -*-
"""
business.host — the one bridge between the business package and bot.py.
bot.py calls business.wire({...}) once at web-server start (same pattern as schedule).
"""


class _Host:
    web = None               # aiohttp web module
    json_response = None     # _json(data, status=200)
    ticket_create = None     # _ticket_create(title, ...) -> ticket  (existing intake)
    save_json = None         # _save_json(name, obj) -> bool  (durable lead fallback)
    load_json = None         # _load_json(name, default)
    base_url = ""            # PUBLIC_BASE_URL, e.g. https://oujares.com
    links = None             # {"book":..., "wa":..., "email":...}
    notify = None            # optional (payload) -> None Discord push
    dash_auth = None         # _dash_auth(request) -> bool  (gates the manage page)
    hostaway_listings = None  # () -> [{id, name, photo, city}]  (for the picker)

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("business used '%s' before business.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
