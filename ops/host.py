# -*- coding: utf-8 -*-
"""
ops.host — the ONE bridge between this package and bot.py (schedule/host.py + decor/host.py
pattern). bot.py calls ops.wire({...}) once at web-server start. This package NEVER does
`import bot`: bot.py runs as __main__, so importing it by name would boot a second bot.
"""


class _Host:
    # --- web / auth (same objects every other package gets) ---
    dash_auth = None         # (request) -> bool     any authenticated staff
    req_role = None          # (request) -> role string
    actor = None             # (request) -> display name of the logged-in user
    json_response = None     # (data, status=200) -> web.Response
    web = None               # aiohttp web module
    tz = None
    now = None               # () -> tz-aware Riyadh datetime

    # --- the data this feature judges people on ---
    weekly_reports = None    # () -> [{employee, date}]   the dashboard's تقرير أسبوعي rows
    discord_ids = None       # () -> {employee name: discord id}   from assignments.json
    public_base = None       # () -> 'https://…'  for the appeal link

    # --- phase 2 «القفل» ---
    # turnover_items() -> [{work_item_id:'<lid>:<date>', unit, date, employee, employee_did,
    #                       checkin_at, photos: bool, done: bool,
    #                       backup: {name, did}}]
    # The whole picture bot.py alone can see: the open turnover rooms, the guest's real
    # check-in time from Hostaway, and whether cleaning photos exist yet.
    turnover_items = None
    has_photos = None        # (work_item_id) -> bool   re-checked at the moment «جاهزة» is pressed

    # --- phase 3 «كرت التقييم» ---
    # Response and escalation used to be fed from bot.py; they now come from ops' OWN tables,
    # written by ops.capture, because nothing in bot.py persisted them. Reviews still cross
    # the bridge — Hostaway is the only source. An empty return makes the line render
    # «بيانات ناقصة» and redistribute: never a zero for a gap in our own instrumentation.
    reviews_window = None       # (start, end) -> [{listing_id, date, categories:{cat: rating}}]

    # --- capture (ops.capture): the live guest-message path ---
    # The work window is bot.py's ONE definition (WORK_START_HOUR / WORK_END_HOUR /
    # WORK_END_MIN), passed in rather than re-declared inside the package.
    work_start_hour = None
    work_end_hour = None
    work_end_min = None
    msg_is_inbound = None      # (msg) -> bool          bot.py's _msg_is_inbound
    msg_time = None            # (msg) -> iso string    bot.py's _msg_time
    msg_is_automated = None    # (msg) -> bool          bot.py's _looks_automated on the body
    fetch_conversations = None # (days) -> [conversation]   backfill only
    fetch_messages = None      # (conversation_id) -> [msg] backfill only

    # --- delivery ---
    # notify(payload) -> None. bot.py schedules the Discord work and then calls
    # ops.db.record_ladder(...) with the road that actually worked (dm | channel | lead |
    # failed), which is ALSO how this package knows whether somebody is reachable at all.
    notify = None

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("ops used '%s' before ops.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
