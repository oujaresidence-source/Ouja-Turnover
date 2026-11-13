# -*- coding: utf-8 -*-
"""
hatif.client — the only code that talks to Hatif (api.voxa.sa). Blocking (requests); callers
run it off the event loop.

Token: OAuth client_credentials at /connect/token with scope VoxaAPI. Cached and shared by
every thread, refreshed 60 s before expiry and once more on a 401.
Errors never carry the client secret or a response body (bodies can hold guest data).
"""
import threading
import time

from . import config

_lock = threading.Lock()
_token = {"value": None, "exp": 0.0}
_session = None


class HatifError(Exception):
    def __init__(self, message, status=None):
        Exception.__init__(self, message)
        self.status = status


def _sess():
    global _session
    if _session is None:
        import requests
        _session = requests.Session()
    return _session


def set_session_for_tests(s):
    global _session
    _session = s
    with _lock:
        _token.update({"value": None, "exp": 0.0})


def _fetch_token():
    try:
        r = _sess().request("POST", config.api_base() + "/connect/token", data={
            "client_id": config.client_id(), "client_secret": config.client_secret(),
            "grant_type": "client_credentials", "scope": "VoxaAPI"}, timeout=config.timeout_s())
    except Exception as e:
        raise HatifError("hatif token request failed: %s" % type(e).__name__)
    if r.status_code != 200:
        raise HatifError("hatif token refused (%s)" % r.status_code, r.status_code)
    try:
        b = r.json()
        tok = b["access_token"]
        ttl = float(b.get("expires_in") or 300)
    except Exception:
        raise HatifError("hatif token answer unreadable")
    _token.update({"value": tok, "exp": time.time() + max(30.0, ttl - 60.0)})
    return tok


def _bearer(force=False):
    with _lock:
        if force or not _token["value"] or time.time() >= _token["exp"]:
            return _fetch_token()
        return _token["value"]


def _call(method, path, body=None):
    if not config.configured():
        raise HatifError("hatif credentials are not set")
    url = config.api_base() + path
    for attempt in (0, 1):
        tok = _bearer(force=(attempt == 1))
        kw = {"headers": {"Authorization": "Bearer " + tok}, "timeout": config.timeout_s()}
        if body is not None:
            kw["json"] = body
        try:
            r = _sess().request(method, url, **kw)
        except Exception as e:
            raise HatifError("hatif %s %s failed: %s" % (method, path, type(e).__name__))
        if r.status_code == 401 and attempt == 0:
            continue
        if not (200 <= r.status_code < 300):
            raise HatifError("hatif %s %s -> %s" % (method, path, r.status_code), r.status_code)
        try:
            return r.json()
        except Exception:
            return {}
    raise HatifError("hatif %s %s -> 401" % (method, path), 401)


def get_conversation(conversation_id):
    return _call("GET", "/v2/conversations/service-account/%s" % conversation_id) or {}


def assign(conversation_id, user_id=None):
    """user_id None ⇒ unassign (empty body), which hands the chat back to the menu flow."""
    body = {"assignedUserId": user_id} if user_id else {}
    return _call("POST", "/v2/conversations/service-account/%s/assign" % conversation_id, body)


def send_text(channel_id, to_number, text):
    return _call("POST", "/v1/whatsapp/service-account/sendText", {
        "channelId": channel_id, "toNumber": str(to_number), "text": str(text)[:4096],
        "openConversation": True})
