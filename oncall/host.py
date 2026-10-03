# -*- coding: utf-8 -*-
"""
oncall.host — the ONE bridge between this package and bot.py (schedule/ops/reviewask pattern).
bot.py calls oncall.wire({...}) once at web-server start. This package NEVER does
`import bot`: bot.py runs as __main__, so importing it by name would boot a second bot.
"""


class _Host:
    # --- web / auth ---
    dash_auth = None         # (request) -> bool
    req_role = None          # (request) -> role string
    actor = None             # (request) -> display name of the logged-in user
    json_response = None     # (data, status=200) -> web.Response
    web = None               # aiohttp web module
    web_thread = None        # async (fn, *a) -> result   (bot.web_thread — never to_thread)

    # --- clock ---
    now = None               # () -> tz-aware Riyadh datetime

    # --- delivery ---
    # send(payload) -> None. bot.py schedules the Discord work from ANY thread and, when it
    # is done, calls oncall.notify.delivered(report, dm_ok, dm_mid, ch_ok, ch_mid).
    send = None

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("oncall used '%s' before oncall.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
