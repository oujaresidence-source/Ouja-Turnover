# -*- coding: utf-8 -*-
"""
staff.host — the ONE bridge between this package and bot.py (schedule/targets/oncall pattern).
bot.py calls staff.wire({...}) once at web-server start. This package NEVER does `import bot`
(bot.py runs as __main__; importing it by name would boot a second bot).

STAFF_ENABLED=0 removes /team and /api/staff/* entirely.
"""

import os

_ON = ("1", "true", "True", "yes", "on")


def enabled():
    return os.environ.get("STAFF_ENABLED", "1") in _ON


class _Host:
    dash_auth = None       # (request) -> bool           logged in (session or owner token)
    req_role = None        # (request) -> role string
    actor = None           # (request) -> the login's display name
    can = None             # (request, tab, action) -> bool   the per-page permission matrix
    employee_of = None     # (request) -> schedule employee linked to this login ('' if none)
    is_manager = None      # (request) -> bool           the ops manager login («targets»)
    has_targets = None     # () -> bool                  «أهدافي» routes are live
    # the day's inputs (staff.gather) — caches and local tables only, never Hostaway
    schedule_day = None    # (date_iso) -> schedule.routes.schedule_day board
    today_snapshot = None  # () -> (snapshot dict, epoch) | None   the dashboard's cached «اليوم»
    listing_names = None   # () -> {listing_id: internal name}     (cached map, never fetched here)
    catalog_units = None   # () -> [{id, name, ...}]
    tickets = None         # () -> maintenance tickets
    promises = None        # () -> open promise_ledger rows
    cleaning_reports = None  # () -> cleaning photo reports
    route_status = None    # () -> {"lid|date": last route ping}
    oncall_state = None    # () -> oncall.routes.state_payload(now)
    pending_replies = None   # () -> int   Musaed drafts awaiting a human
    open_escalations = None  # () -> int   unclaimed escalations
    today_iso = None       # () -> 'YYYY-MM-DD' in Riyadh
    now_iso = None         # () -> Riyadh ISO timestamp without tz
    json_response = None   # (data, status=200) -> web.Response
    web = None             # aiohttp web module
    web_thread = None      # async (fn, *a) -> result   (bot.web_thread — never to_thread)

    def call(self, attr, default, *a):
        fn = getattr(self, attr, None)
        if fn is None:
            return default
        try:
            v = fn(*a)
        except Exception as e:
            print("[staff] host.%s failed: %s" % (attr, e))
            return default
        return default if v is None else v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
