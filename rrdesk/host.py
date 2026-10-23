# -*- coding: utf-8 -*-
"""
rrdesk.host — the ONE bridge between this package and bot.py (ops/oncall/checkout pattern).
bot.py calls rrdesk.wire({...}) once Discord is ready (and again at web-server start). This
package NEVER does `import bot`: bot.py runs as __main__, so importing it by name would boot a
second bot.

Every capability is optional at import time and checked at use: a missing one degrades that
one feature (logged as an event), never the bot.
"""


class _Host:
    # --- web / auth (the same objects every package gets) ---
    dash_auth = None         # (request) -> bool
    req_role = None          # (request) -> role string ('admin', 'ops', ...)
    actor = None             # (request) -> display name of the logged-in user
    json_response = None     # (data, status=200) -> web.Response
    web = None               # aiohttp web module
    web_thread = None        # async (fn, *a) -> result   (bot.web_thread — never to_thread)
    public_base = None       # () -> 'https://…'

    # --- clock ---
    now = None               # () -> tz-aware Riyadh datetime

    # --- Discord (only rrdesk.bridge touches these) ---
    bot = None               # the discord.ext.commands.Bot
    discord = None           # the discord module
    guild_id = None          # int
    is_admin = None          # (member) -> bool   bot.py's _can_delete_channels
    rr_categories = None     # (guild) -> [category]  RR family + overflow + «📦 أرشيف N»

    # --- RR tickets (bot.py owns discord_tickets.json) ---
    rr_record = None         # (channel_id) -> ticket dict | None   (kind == 'rr' only)
    rr_records = None        # () -> {channel_id: ticket dict}       (study + Sam id)
    enrich = None            # (code) -> {days_left, deadline_passed, lid, unit, ...}  BLOCKING

    # --- people (Employee Calendar via ops) ---
    responsible_for = None   # (listing_id, day) -> (name, did, owner|coverer|unknown)
    lead_id = None           # () -> discord id of the ops lead (أصيل)
    on_leave = None          # (name, day) -> bool
    employees = None         # () -> [{name, did}]       ops.notify.employees()
    off_today = None         # (name, day) -> bool       weekly day off OR recorded leave

    # --- model ---
    api_key = None           # () -> ANTHROPIC_API_KEY
    model = None             # () -> CLAUDE_MODEL (Haiku)

    # --- misc ---
    once_claim = None        # (name, ttl=None) -> bool   bot.py's _once_claim (FS marker)
    watchdog_channel = None  # () -> channel name (غرفة-المراقبة)

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("rrdesk used '%s' before rrdesk.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
