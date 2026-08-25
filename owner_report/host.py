# -*- coding: utf-8 -*-
"""
owner_report.host — the single DI bridge between this package and bot.py (same pattern as
schedule.host / watchdog.host). bot.py calls owner_report.wire({...}) once at web-server start.

Every Hostaway cap here is a READ helper. There is deliberately no write cap — the module is
read-only against Hostaway, forever.
"""


class _Host:
    # storage + auth (reused from bot.py)
    state_path = None        # _state_path(name)
    load_json = None         # _load_json(name, default)
    save_json = None         # _save_json(name, obj)
    dash_auth = None         # _dash_auth(request) -> bool
    req_role = None          # _req_role(request) -> role str
    actor = None             # _req_actor(request) -> str
    json_response = None     # _json(data, status=200)
    web = None               # aiohttp web module
    tz = None
    now = None               # () -> tz-aware datetime (Riyadh)

    # Hostaway READ caps (no writes ever)
    listings_map = None              # get_listings_map() -> {lid: name}
    fetch_window_checked = None      # (start,end) -> (rows, degraded)
    normalize = None                 # (raw, listings) -> finance row
    calendar_days = None             # (lid, start, end) -> [day dicts]
    reviews = None                   # () -> [review dicts]
    expenses_source = None           # () -> {id: expense}
    exp_posted = None                # (exp) -> bool

    # optional Discord push for issued reports
    notify = None

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("owner_report used '%s' before owner_report.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
