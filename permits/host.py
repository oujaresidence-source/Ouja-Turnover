# -*- coding: utf-8 -*-
"""
permits.host — the ONE bridge between this package and bot.py (wifi/host.py pattern).
bot.py calls permits.wire({...}) once at web-server start. The package never imports bot.
"""


class _Host:
    dash_auth = None           # (request) -> bool          any logged-in staff
    req_role = None            # (request) -> 'admin'|'ops'|'viewer'|'accountant'
    actor = None               # (request) -> display name
    json_response = None       # (data, status=200) -> web.Response
    web = None                 # aiohttp web module
    tz = None
    now = None                 # () -> tz-aware Riyadh datetime
    web_thread = None          # async (fn, *a) -> result   — REQUEST handlers only (never to_thread)
    listings = None            # () -> [{id, internal_name, public_name, active}]   (non-blocking)
    guild_id = None            # int — for discord.com/channels/{guild}/{channel} links
    maint_assignee_for = None  # (listing_id) -> (name, discord_id)   maintenance owner of a unit
    dashboard_url = None       # () -> 'https://…/dashboard#permits'  (optional)
    onb_reader = None          # () -> [onb_projects rows]   READ-ONLY (optional)
    state_dir = None           # str — where permits_docs/ lives (STATE_DIR)

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("permits used '%s' before permits.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
