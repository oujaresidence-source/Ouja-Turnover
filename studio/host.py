# -*- coding: utf-8 -*-
"""studio.host — the ONE bridge between the studio package and bot.py (same DI
pattern as watchdog/schedule/finchat). bot.py calls studio.wire({...}) once at
web-server start."""


class _Host:
    state_path = None       # _state_path(name)
    load_json = None
    save_json = None
    dash_auth = None        # _dash_auth(request) -> bool
    req_role = None         # _req_role(request) -> role string
    json_response = None    # _json(data, status=200)
    web = None              # aiohttp web module
    listings = None         # () -> {lid:int -> name}
    api_get = None          # bot.api_get (Hostaway GET with auth+retry)
    claude_json = None      # bot.claude_json(system, user, max_tokens=, model=)
    model_fast = None       # cheap model id (triage)
    model_premium = None    # premium model id (stories + ideas)
    tz = None
    now = None              # () -> tz-aware Riyadh datetime

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("studio used '%s' before studio.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
