"""
schedule.host — the ONE bridge between the schedule package and bot.py (same pattern as the
Brain / roster). bot.py calls schedule.wire({...}) once at web-server start.
"""


class _Host:
    state_path = None        # _state_path(name)
    load_json = None
    save_json = None
    dash_auth = None         # _dash_auth(request) -> bool  (any authenticated staff)
    req_role = None          # _req_role(request) -> role string
    json_response = None     # _json(data, status=200)
    web = None               # aiohttp web module
    notify = None            # (payload) -> None  (optional Discord push)
    listings = None          # () -> [{id, name, active, oujact}]  Hostaway listings for the picker
    tz = None
    now = None               # () -> tz-aware datetime in Riyadh

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("schedule used '%s' before schedule.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
