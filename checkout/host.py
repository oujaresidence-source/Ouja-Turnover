# -*- coding: utf-8 -*-
"""
checkout.host — the ONE bridge between this package and bot.py (ops/host.py pattern).
bot.py calls checkout.wire({...}) once from start_web_server. This package NEVER does
`import bot`: bot.py runs as __main__, so importing it by name would boot a second bot.

Blocking hooks (Hostaway) run on the package's own pool (flow.run_blocking); Discord hooks
are coroutines and run on the bot's loop.
"""


class _Host:
    now = None               # () -> tz-aware Riyadh datetime

    # --- data (BLOCKING — the package runs these off the event loop) ---
    # today_turnovers() -> [{lid, day, res_id, unit, guest, phone, conversation_id,
    #                        channel_name, checkout_at, checkin_at, clean_minutes}]
    #   every departure TODAY from a targeted Hostaway window query (never the truncated cache)
    today_turnovers = None
    send_guest = None        # (conversation_id, body) -> api result | SEND_* code   (Hostaway)
    guest_links = None       # (res_id) -> [(url, label)]   WhatsApp/Airbnb deep links (Hostaway)

    # --- data (cheap, in-memory) ---
    channels = None          # () -> [{channel_id, key:'lid:day', review: bool}] every turnover
                             #       room in the Turnovers family (base + overflow categories)
    cover = None             # (lid, day, channel_id) -> {name, did, role_id}
    cleaning_status = None   # (lid, day, channel_id) -> 'none' | 'submitted' | 'approved'
    early_hint = None        # (lid) -> bool   Musaed read in chat that the guest left
    early_checkin = None     # (lid, day) -> bool   an approved early check-in for today's arrival
    set_oujact_state = None  # (lid, day, state, by) -> bool   the cleaners' warning
    log_oujact = None        # (lid, day, action, note, by)
    wa_number = None         # (phone) -> 'wa.me/<intl>' | ''    bot.py's _wa_from_phone
    clean_minutes_default = 40

    # --- Discord (coroutines) ---
    post = None              # async (channel_id, text, embed=None, buttons=None, demo=False)
                             #        -> message id | None
    edit = None              # async (channel_id, message_id, text=None, embed=None,
                             #        buttons=None, demo=False) -> bool
    board_channel = None     # async () -> channel id of «متابعة-الخروج» (created if missing)
    link_base = None         # () -> "https://…" public base for the one-tap /cw/<token> link

    is_live = None           # optional override () -> bool; None = the stored switch

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("checkout used '%s' before checkout.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
