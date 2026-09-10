# -*- coding: utf-8 -*-
"""
directpay.host — the ONE bridge between this package and bot.py (decor/host.py pattern).
bot.py calls directpay.wire({...}) once at web-server start. The package never imports bot,
never imports discord, never opens a socket. Every capability below is a one-liner on purpose.
"""


class _Host:
    dash_auth = None            # (request) -> bool          any authenticated staff
    req_role = None             # (request) -> role string
    actor = None                # (request) -> display name  (the activity-log name)
    req_actor = None            # (request) -> display name  (same thing, bot's own name for it)
    json_response = None        # (data, status=200) -> web.Response
    web = None                  # aiohttp web module
    state_dir = None            # STATE_DIR (proof bytes live under it)
    state_path = None           # (name) -> absolute path under STATE_DIR
    tz = None                   # ZoneInfo Asia/Riyadh
    now = None                  # () -> tz-aware Riyadh datetime
    listings = None             # () -> {listing_id: internal name}
    notify = None               # (payload) -> None   Discord delivery; None in tests / dry-run
    log_event = None            # (category, text) -> None   the dashboard activity feed
    finance_channel = None      # (reservation) -> "direct" | "airbnb" | "other"  (bot._finance_channel)
    payment_signal = None       # (reservation) -> (status, paid, remaining, fields[])  (bot._payment_signal)
    ha_reservations_window = None   # (param_start, param_end, start_iso, end_iso) -> [reservations]
    ha_reservation = None       # (reservation_id) -> reservation dict or None   ONE targeted GET
    confirmed_statuses = None   # () -> set   zero-arg lambda: a mutable bot global, never held stale

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("directpay used '%s' before directpay.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
