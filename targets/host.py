# -*- coding: utf-8 -*-
"""
targets.host — the ONE bridge between this package and bot.py (schedule/ops/oncall pattern).
bot.py calls targets.wire({...}) once at web-server start. This package NEVER does
`import bot`: bot.py runs as __main__, so importing it by name would boot a second bot.

The two switches live here so every module reads them the same way, at call time:
    TG_ENABLED=1         0 hides the whole feature (no tabs, no routes, dashboard untouched)
    TG_POOL_CHANNELS     who may be called: all (default since 2026-11-15, the owner's decision
                         and risk — Airbnb guests without consent). `direct,consented` narrows it.
"""

import os

_ON = ("1", "true", "True", "yes", "on")


def enabled():
    return os.environ.get("TG_ENABLED", "1") in _ON


def pool_channels():
    raw = os.environ.get("TG_POOL_CHANNELS", "all")
    return tuple(sorted({p.strip().lower() for p in raw.split(",") if p.strip()}))


class _Host:
    # --- web / auth ---
    dash_auth = None         # (request) -> bool
    req_role = None          # (request) -> role string
    actor = None             # (request) -> display name of the logged-in user
    user_id = None           # (request) -> session user id ('' when unknown, 'admin' for the token)
    users = None             # () -> [{id, name, role}]  (for the «مين هو مين» picker)
    json_response = None     # (data, status=200) -> web.Response
    web = None               # aiohttp web module
    web_thread = None        # async (fn, *a) -> result   (bot.web_thread — never to_thread)

    # --- clock / disk ---
    now = None               # () -> tz-aware Riyadh datetime
    state_dir = None         # str: where the uploaded seed file is kept (never the repo)

    # --- the live business ---
    listings = None          # () -> {listing_id: internal name}
    ownership = None         # () -> [{listing_id, name, employee}]   (schedule.owners)
    unit_meta = None         # (listing_id) -> {"compound": str}       (optional)
    floor = None             # (listing_id) -> SAR floor the owner set, 0 when none
    fee_pct = None           # (listing_id, name, date) -> Ouja's contract fee as a FRACTION, None if unknown
    ops_multiplier = None    # (employee, month_key) -> warnings x scorecard multiplier
    vip_keys = None          # () -> set of phone keys flagged VIP in the guest profiles
    unit_rating = None       # (listing_id, month_key) -> {"avg": out of 5, "n": reviews} or None
    fetch_window = None      # (start_date, end_date) -> raw Hostaway reservations
    calendar_days = None     # (listing_id, start_date, end_date) -> raw calendar days
    wa_url = None            # (phone, text) -> WhatsApp deep link

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("targets used '%s' before targets.wire()" % attr)
        return v

    def call(self, attr, default, *a):
        """Optional capability: a missing or failing bridge degrades to `default`."""
        fn = getattr(self, attr, None)
        if fn is None:
            return default
        try:
            v = fn(*a)
        except Exception as e:
            print("[targets] host.%s failed: %s" % (attr, e))
            return default
        return default if v is None else v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
