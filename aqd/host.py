# -*- coding: utf-8 -*-
"""
aqd.host — the ONE bridge between the «العقود» package and bot.py (onboarding/host.py shape).
bot.py calls aqd.wire({...}) once at web-server start. Nothing in this package imports bot.py,
so the engine and the routes can be driven by a test with plain lambdas.
"""


class _Host:
    dash_auth = None         # (request) -> bool   any authenticated staff
    req_role = None          # (request) -> 'admin'|'ops'|'viewer'|...
    actor = None             # (request) -> display name
    json_response = None     # (data, status=200) -> web.Response (ensure_ascii=False)
    web = None               # aiohttp web module
    state_dir = None         # str — $STATE_DIR; artifacts live under <state_dir>/aqd/
    tz = None
    now = None               # () -> tz-aware Riyadh datetime
    web_thread = None        # async (fn, *a) -> result — REQUEST handlers only (the web pool, never the default executor)
    listings = None          # () -> [{id, name, active}]  optional unit link (blocking; via web_thread)
    notify = None            # (payload) -> None   Discord push; thread-safe in bot.py
    log_event = None         # (category, text) -> None
    public_base = None       # () -> 'https://…'  for the signing link
    discord_ids = None       # () -> {employee name: discord id}

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("aqd used '%s' before aqd.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
