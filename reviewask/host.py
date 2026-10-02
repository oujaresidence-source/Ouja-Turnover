# -*- coding: utf-8 -*-
"""
reviewask.host — the ONE bridge between this package and bot.py (checkout/host.py pattern).
bot.py calls reviewask.wire({...}). This package NEVER does `import bot`: bot.py runs as
__main__, so importing it by name would boot a second bot.

Blocking hooks (Hostaway, in-memory scans) run on the package's own pool (flow.run_blocking) or,
from a web request, on HOST.web_thread — never asyncio.to_thread (CLAUDE.md trap 6).
"""


class _Host:
    now = None               # () -> tz-aware Riyadh datetime

    # --- data (BLOCKING) ---
    # departures(start_iso, end_iso) -> [{res_id, lid, unit, guest, phone, conversation_id,
    #     status, channel ('airbnb'|'direct'|'other'), arrival, departure}]   targeted window,
    #     never the truncated reservation cache (CLAUDE.md trap 4)
    departures = None
    reservation = None       # (res_id) -> same shape | None (None = could not read)
    reviews = None           # () -> [normalised review dicts] (bot.py's _reviews, in memory)
    open_ticket_counts = None  # () -> {lid: open maintenance tickets}
    maint_tickets = None     # (lid) -> [{created_at, closed_at}]   Discord + dashboard tickets
    has_recovery = None      # (res_id) -> bool   a recovery ticket exists for the stay
    cover = None             # (lid, day) -> {name, did, role_id}   Employee Calendar first
    wa_number = None         # (phone) -> 'wa.me/<intl>' | ''      bot.py's _wa_from_phone
    guest_links = None       # (res_id) -> [(url, label)]           Airbnb conversation link
    listings = None          # () -> {lid: name}

    # --- Discord (coroutines) ---
    open_room = None         # async (name, topic) -> channel id   «طلبات التقييم» + spill
    known_rooms = None       # () -> {res_id: channel_id}   topics across the category family
    post = None              # async (channel_id, text=None, embed=None, buttons=None,
                             #        mentions=True) -> message id | None
    edit = None              # async (channel_id, message_id, text=None, embed=None,
                             #        buttons=None, disabled=False) -> bool
    room_info = None         # async (channel_id) -> {"exists": bool, "topic": str} | None
    fetch_transcript = None  # async (channel_id, limit) -> [message dicts]
    delete_room = None       # async (channel_id) -> bool   used ONLY by flow.sweep_closed
    board_channel = None     # async () -> channel id of «متابعة-التقييمات»
    monitor_channel = None   # async () -> channel id of «غرفة-المراقبة»
    link_base = None         # () -> "https://…" public base for /rv/<token>
    once_claim = None        # (key) -> bool   bot.py's _once_claim (cross-process)
    once_release = None      # (key) -> None

    # --- web (routes.py) ---
    dash_auth = None         # (request) -> bool
    req_role = None          # (request) -> 'admin' | 'ops' | 'viewer' | …
    actor = None             # (request) -> display name
    json_response = None     # (data, status) -> web.Response
    web = None               # aiohttp.web
    web_thread = None        # async (fn, *a) -> result   request handlers only
    guild_id = None          # int — for discord.com/channels links

    is_live = None           # optional override () -> bool; None = the stored switch

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("reviewask used '%s' before reviewask.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
