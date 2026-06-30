"""
roster.host — the ONE bridge between the roster package and the bot.py monolith.

Same pattern as brain.host: bot.py calls roster.wire({...}) once at web-server start and
hands over the capabilities the roster is allowed to use (state paths, auth, JSON response,
the Hostaway listings reader, the Discord notifier, time helpers). The roster never imports
bot.py (circular import). Everything it touches is listed here so the blast radius is
auditable in one place.
"""


class _Host:
    # state + serialization (Railway volume) — reused for the owner-editable seed override
    state_path = None        # _state_path(name) -> absolute path under STATE_DIR
    load_json = None         # _load_json(name, default) -> obj
    save_json = None         # _save_json(name, obj) -> None

    # web plumbing (auth + responses)
    dash_auth = None         # _dash_auth(request) -> bool
    req_role = None          # _req_role(request) -> 'admin'|'ops'|'accountant'|'viewer'
    json_response = None     # _json(data, status=200) -> web.Response
    web = None               # the aiohttp `web` module

    # listings (read-only) for Hostaway sync
    get_listings_map = None  # () -> {listingMapId: internal_name}
    ls_get = None            # () -> {"listings": {str(lid): rec}}  (rec has group/zone)

    # discord notify (optional; roster works without it)
    notify = None            # (payload_dict) -> None  — schedules a coroutine on the bot loop

    # time
    tz = None                # ZoneInfo
    now = None               # () -> tz-aware datetime in Riyadh

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError(
                "roster used capability '%s' before roster.wire() ran "
                "(wire() is called inside start_web_server())." % attr)
        return v


HOST = _Host()


def wire(caps):
    """Populate HOST from a dict of bot.py capabilities. Idempotent."""
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
