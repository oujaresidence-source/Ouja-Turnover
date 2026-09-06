# -*- coding: utf-8 -*-
"""
mot.host — the ONE bridge to bot.py. Everything mot/ needs from the host is injected via
wire({...}) inside start_web_server; nothing here imports bot.

Caps (all set by bot.py):
    dash_auth(request) -> bool            actor(request) -> str
    json_response(data, status) -> Response          web = aiohttp.web
    tz, now()                             state_dir (photos live under it)
    web_thread(fn, *a) -> awaitable       the WEB pool — never asyncio.to_thread
    listings() -> {listing_id: name}      active units from the listings master store
    unit_meta(lid) -> {bedrooms, bathrooms, beds, owner, owner_phone}
    unit_features(lid) -> None | [..]     decor's pool/jacuzzi sheet; None = unknown
    set_unit_features(lid, feats, by)     write back through the decor resolver
    wifi_status(lid) -> True|False|None   active wifi row / none / wifi package absent
    save_quote(payload) -> quote dict     the existing quotes store (sync; caller persists)
    persist()                             persist_state
    ticket_create(title, **kw) -> ticket  the dashboard ticket tracker (_ticket_create)
    onb_license_tasks(lid, keys) -> dict  re-seed the unit's onboarding project (lid<0 = project)
    onb_fresh_units() -> [project]        active onboarding projects (fresh apartments)
    onb_create_unit(fields, by) -> project   open an onboarding project = a fresh apartment
    log_event(cat, text)                  public_base() -> str
"""


class _Host:
    dash_auth = None
    actor = None
    json_response = None
    web = None
    tz = None
    now = None
    state_dir = "/data"
    web_thread = None
    listings = None
    unit_meta = None
    unit_features = None
    set_unit_features = None
    wifi_status = None
    save_quote = None
    persist = None
    ticket_create = None
    onb_license_tasks = None
    onb_fresh_units = None
    onb_create_unit = None
    log_event = None
    public_base = None

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("mot used '%s' before mot.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    return HOST
