"""
brain.host — the ONE bridge between the Brain and the existing bot.py monolith.

The Brain never imports bot.py (that would be a circular import, and bot.py is the
`__main__` entry). Instead, bot.py calls `brain.wire({...})` once at web-server start
and hands us references to the capabilities the Brain is allowed to use — ALL of them
read-only against pricing/turnover/calendar state. Everything the Brain touches in the
host is listed here, so the blast radius is auditable in one place.

If a capability is used before wiring, we raise a clear error instead of failing with a
confusing AttributeError — that only happens if routes are hit before start_web_server().
"""


class _Host:
    # --- filled in by brain.wire() ---
    # state + serialization (Railway volume)
    state_path = None            # _state_path(name) -> absolute path under STATE_DIR
    load_json = None             # _load_json(name, default) -> obj
    save_json = None             # _save_json(name, obj) -> None
    state_dir = None             # STATE_DIR string

    # web plumbing (auth + responses)
    dash_auth = None             # _dash_auth(request) -> bool
    json_response = None         # _json(data, status=200) -> web.Response
    web = None                   # the aiohttp `web` module (Response/FileResponse)

    # cached calendar (PRIMARY inventory source — reuse, don't re-fetch)
    cache_get = None             # _cache_get(key) -> cached value or None
    kick_compute = None          # _kick_compute(key, fn) -> None (lazy warm)
    compute_calendar_grid = None # _compute_calendar_grid(days=45) -> units x nights grid
    get_forward_calendar = None  # get_forward_calendar(days, ttl) -> per-date portfolio pace

    # pricing softness signals (already-discounted nights)
    latest_last_minute_diagnostics = None  # (limit) -> recent discount runs (items[] per unit)
    load_discount_state = None             # () -> {date: {lid: {orig price}}}

    # reservations / checkouts / listings
    ha_reservations_window = None  # (pstart, pend, start_iso, end_iso) -> [raw HA res], <=1000
    fetch_upcoming_checkouts = None# () -> [{res_id, lid, listing, guest, checkout}]
    get_listings_map = None        # () -> {listingMapId: internal_name}
    ls_get = None                  # () -> listings store dict {"listings": {str(lid): rec}}

    # guest CRM (the member seed source)
    guest_profiles = None        # () -> the live _guest_profiles dict (read-only use)
    normalize_phone = None       # _normalize_phone(s) -> "+9665..." or ""

    # time
    tz = None                    # TZ (zoneinfo)
    now = None                   # () -> tz-aware datetime in Riyadh
    weekend_days = None          # set of weekday ints that are weekend (Thu/Fri here)

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError(
                "Ouja Brain used capability '%s' before brain.wire() ran. "
                "wire() is called inside start_web_server()." % attr)
        return v


HOST = _Host()


def wire(caps: dict):
    """Populate HOST from a dict of bot.py capabilities. Idempotent."""
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
