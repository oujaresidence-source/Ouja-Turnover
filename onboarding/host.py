# -*- coding: utf-8 -*-
"""
onboarding.host — the ONE bridge between the onboarding package and bot.py (same pattern as
schedule.host / decor.host). bot.py calls onboarding.wire({...}) once at web-server start.

Nothing in this package imports bot.py. Every capability it needs arrives through HOST, so the
engine and the routes can be driven by a test with plain lambdas and no event loop.
"""


class _Host:
    dash_auth = None         # _dash_auth(request) -> bool   (any authenticated staff)
    req_role = None          # _req_role(request) -> 'admin'|'ops'|'viewer'
    actor = None             # _req_actor(request) -> display name
    json_response = None     # _json(data, status=200)  — ensure_ascii=False
    web = None               # aiohttp web module
    state_dir = None
    tz = None
    now = None               # () -> tz-aware datetime in Riyadh
    listings = None          # () -> [{id, name, ...}] Hostaway listings for the unit picker
    pmo_projects = None      # () -> {project_id: project dict}  (the «تجهيز الشقق» link)
    notify = None            # (payload) -> None   Discord push; DRY-RUN by default
    log_event = None         # (category, text) -> None
    discord_ids = None       # () -> {employee name: discord id}
    public_base = None       # () -> 'https://...'  for the employee link

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("onboarding used '%s' before onboarding.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
