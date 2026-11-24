# -*- coding: utf-8 -*-
"""
campaigns.host — the ONE bridge to bot.py (hatif/host.py pattern). bot.py calls
campaigns.wire({...}) once at web-server start. The package never imports bot or discord.
"""


class _Host:
    dash_auth = None        # (request) -> bool
    is_admin = None         # (request) -> bool   the per-person queue upload is admin-only
    json_response = None    # (data, status=200) -> web.Response
    run = None              # async (fn, *a) -> result   bot.web_thread
    now = None              # () -> tz-aware Riyadh datetime
    post = None             # (where, text, role_id="", card=None) -> None   where: "offers" | "owners"
                            # card = cards.render() + alert_id → an embed with buttons
    send_guest = None       # (conversation_id, body, comm_type) -> Hostaway reply | a SEND_* refusal string
    log_event = None        # (category, text) -> None
    calendar = None         # (listing_id, start_date, end_date) -> [{date, isAvailable, price, ...}]
    floor = None            # (listing_id) -> int SAR, the unit's minimum (0 = none on file)
    responsible = None      # (listing_id, unit_name) -> today's coverer / permanent owner name
    links = None            # (reservation_id, comm_type) -> [(url, label)]
    dates_from_text = None  # (history_text) -> (start_iso, end_iso, confidence)
    reservations = None     # (start_date, end_date) -> Hostaway reservations CREATED in the window
    search = None           # (check_in, check_out, guests, type, hood) -> _gw_search dict
    site_host = None        # () -> "oujares.com"
    web = None              # aiohttp.web — the «الحملات» tab script is served as JavaScript

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("campaigns used '%s' before campaigns.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
