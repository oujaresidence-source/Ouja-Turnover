# -*- coding: utf-8 -*-
"""digest.host — the ONE bridge between the digest package and bot.py (same DI
pattern as studio/schedule/finchat). bot.py calls digest.wire({...}) once at
web-server start. Every network call in the package goes through `http`
(the digest.net_live module) so tests can swap it for a fake."""


class _Host:
    state_path = None       # _state_path(name) -> absolute path under $STATE_DIR
    load_json = None
    save_json = None
    dash_auth = None        # _dash_auth(request) -> bool
    req_role = None         # _req_role(request) -> role string
    json_response = None    # _json(data, status=200)
    web = None              # aiohttp web module
    claude_json = None      # bot.claude_json(system, user, max_tokens=, model=) -> dict|None
    claude_search = None    # bot.claude_search_json(...) -> (data|None, [urls]) — LIVE WEB
    http = None             # digest.net_live (get_text / head / get_bytes) — the only socket
    listings = None         # () -> {lid:int -> name}
    public_base = None      # () -> public site base url (auto-captured, so CALLABLE)
    model_fast = None       # cheap model id
    model_premium = None    # premium model id (copy polish)
    tz = None
    now = None              # () -> tz-aware Riyadh datetime

    _wired = False

    def require(self, attr):
        v = getattr(self, attr, None)
        if v is None:
            raise RuntimeError("digest used '%s' before digest.wire()" % attr)
        return v


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        setattr(HOST, k, v)
    HOST._wired = True
    return HOST
