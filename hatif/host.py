# -*- coding: utf-8 -*-
"""
hatif.host — the ONE bridge between this package and bot.py (stayhub/host.py pattern).
bot.py calls hatif.wire({...}) once at web-server start. The package never imports bot and
never imports discord.
"""


class _Host:
    dash_auth = None        # (request) -> bool          any authenticated staff
    json_response = None    # (data, status=200) -> web.Response
    web = None              # aiohttp web module
    run = None              # async (fn, *a) -> result   bot.web_thread
    background = None       # (fn) -> None   run a blocking fn off the loop, fire-and-forget
    now = None              # () -> tz-aware Riyadh datetime
    notify = None           # (text) -> None   one Discord message; None in tests
    log_event = None        # (category, text) -> None   the dashboard activity feed
    search = None           # (check_in, check_out, guests, type, neighborhood) -> _gw_search dict
    neighborhoods = None    # () -> [(key, arabic, english)]
    site_host = None        # () -> "oujares.com"
    classify = None         # (system, user) -> dict|None   the reader's one AI call (claude_json)
    notify_reader = None    # (text) -> None   the silent reader's Discord channel (falls back to notify)
    catalog = None          # () -> [unit dicts]   browse-mode _gw_search results (no availability)

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("hatif used '%s' before hatif.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
