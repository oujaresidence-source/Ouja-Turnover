# -*- coding: utf-8 -*-
"""
contracting.host — the ONE bridge to bot.py (oncall/host.py pattern). bot.py calls
contracting.wire({...}) once; the package never imports bot.
"""


class _Host:
    dash_auth = None      # (request) -> bool
    req_role = None       # (request) -> role string
    actor = None          # (request) -> display name
    json_response = None  # (data, status=200) -> web.Response
    web = None            # aiohttp web module
    web_thread = None     # async (fn, *a) -> result   blocking work off the event loop
    now = None            # () -> tz-aware Riyadh datetime
    send = None           # (payload) -> None   Discord delivery (bot decides HOW)
    lookup_did = None     # (name) -> discord id string or ""   the ops identity map
    roster = None         # () -> {"rows": [{"id","name","user"}], "loading": bool}   Discord members

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("contracting used '%s' before contracting.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
