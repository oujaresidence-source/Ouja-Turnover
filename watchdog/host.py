"""
watchdog.host — the ONE bridge between the watchdog package and bot.py (same DI pattern
as schedule/brain). bot.py calls watchdog.wire({...}) once at web-server start.
"""


class _Host:
    state_path = None        # _state_path(name)
    load_json = None
    save_json = None
    dash_auth = None         # _dash_auth(request) -> bool  (any authenticated staff)
    req_role = None          # _req_role(request) -> role string
    json_response = None     # _json(data, status=200)
    web = None               # aiohttp web module
    listings = None          # () -> {lid:int -> name}  (get_listings_map)
    resolve_discord = None   # (name) -> discord id string ('' unknown)
    tz = None
    now = None               # () -> tz-aware datetime in Riyadh
    last_snapshot = None     # dict — the bot loop stores its latest snapshot here

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("watchdog used '%s' before watchdog.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
