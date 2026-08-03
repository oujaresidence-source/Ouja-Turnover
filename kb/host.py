# -*- coding: utf-8 -*-
"""
kb.host — the ONE bridge between this package and bot.py (wifi/decor pattern).
bot.py calls kb.wire({...}) once at web-server start. The package never imports bot.
"""


class _Host:
    dash_auth = None         # (request) -> bool   any authenticated staff
    req_role = None          # (request) -> role string
    actor = None             # (request) -> display name, stamped on every edit
    json_response = None     # (data, status=200) -> web.Response
    web = None               # aiohttp web module

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("kb used '%s' before kb.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
