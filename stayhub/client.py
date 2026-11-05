# -*- coding: utf-8 -*-
"""
stayhub.client — the only code that talks to StayHub over the network. Blocking (requests);
callers run it off the event loop (bot loops use asyncio.to_thread, handlers use web_thread).

Token: OAuth client_credentials, lifetime 300 s. Cached and shared by every thread, refreshed
60 s before expiry, and once more on any 401 (AUTH_INVALID_TOKEN / AUTH_EXPIRED_TOKEN).

Retry policy (integration guide, slide 12 — part of certification):
    401                → refresh the token, retry ONCE
    429 RATE_LIMITED   → sleep Retry-After (or 2/4/8 s), max 3 times
    5xx INTERNAL_ERROR → exponential backoff, max 3 — ONLY for idempotent calls
                         (GETs, confirm, modify, cancel — StayHub de-duplicates those by
                         externalReservationId + externalRevision). hold is never re-sent blind.
    anything else      → raised as StayHubError with the code, HTTP status, detail and traceId.

Responses are unwrapped: StayHub answers {"success":true,"data":{…}}; callers get data.
The client secret and the token are never printed.
"""
import threading
import time

import requests

from . import config


class StayHubError(Exception):
    def __init__(self, code, status=None, message="", detail=None, trace_id=None):
        super().__init__("%s (%s) %s" % (code, status, message))
        self.code = code or "UNKNOWN"
        self.status = status
        self.message = message or ""
        self.detail = detail
        self.trace_id = trace_id


_session = requests.Session()
_tok = {"value": None, "exp": 0.0}
_tok_lock = threading.Lock()
_sleep = time.sleep                       # tests replace this
_clock = time.time


def set_session_for_tests(s):
    global _session
    _session = s
    reset_token()


def reset_token():
    with _tok_lock:
        _tok["value"], _tok["exp"] = None, 0.0


def _trace(resp, body):
    tid = None
    try:
        tid = resp.headers.get("X-Trace-Id") or resp.headers.get("x-trace-id")
    except Exception:
        pass
    if not tid and isinstance(body, dict):
        tid = body.get("traceId") or ((body.get("error") or {}).get("traceId") if isinstance(body.get("error"), dict) else None)
        if not tid and isinstance(body.get("data"), dict):
            tid = body["data"].get("traceId")
    return tid


def _json(resp):
    try:
        return resp.json()
    except Exception:
        return None


def _error_from(resp, body):
    code, msg, detail = None, "", None
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            code, msg, detail = err.get("code"), err.get("message") or "", err.get("detail")
        elif isinstance(err, str):
            code, msg = err, body.get("error_description") or ""
    if not code:
        code = {401: "AUTH_INVALID_TOKEN", 403: "FORBIDDEN", 404: "NOT_FOUND", 429: "RATE_LIMITED"}.get(
            resp.status_code, "INTERNAL_ERROR" if resp.status_code >= 500 else "HTTP_%s" % resp.status_code)
    return StayHubError(code, resp.status_code, msg, detail, _trace(resp, body))


def token(force=False):
    """A valid bearer token (cached). Raises StayHubError on bad credentials."""
    if not config.configured():
        raise StayHubError("NOT_CONFIGURED", None, "STAYHUB_CLIENT_ID / STAYHUB_CLIENT_SECRET missing")
    with _tok_lock:
        if not force and _tok["value"] and _clock() < _tok["exp"] - 60:
            return _tok["value"]
        try:
            resp = _session.post(config.token_url(), data={
                "grant_type": "client_credentials", "client_id": config.client_id(),
                "client_secret": config.client_secret(), "scope": config.scope()},
                timeout=config.http_timeout_s())
        except requests.RequestException as e:
            raise StayHubError("NETWORK", None, type(e).__name__)
        body = _json(resp)
        if resp.status_code != 200 or not isinstance(body, dict) or not body.get("access_token"):
            raise _error_from(resp, body)
        _tok["value"] = body["access_token"]
        try:
            life = float(body.get("expires_in") or 300)
        except (TypeError, ValueError):
            life = 300.0
        _tok["exp"] = _clock() + life
        return _tok["value"]


def call(method, path, params=None, body=None, idempotent=None, base=None, _auth_retry=0, _attempt=0):
    """One API call → the unwrapped `data` (dict/list) plus the trace id: (data, trace_id)."""
    idem = (method == "GET") if idempotent is None else bool(idempotent)
    url = (base or config.api_base()) + path
    headers = {"Authorization": "Bearer %s" % token(), "Accept": "application/json"}
    try:
        resp = _session.request(method, url, params=params, json=body if method != "GET" else None,
                                headers=headers, timeout=config.http_timeout_s())
    except requests.RequestException as e:
        if idem and _attempt < 3:
            _sleep(2 ** (_attempt + 1))
            return call(method, path, params, body, idempotent, base, _auth_retry, _attempt + 1)
        raise StayHubError("NETWORK", None, type(e).__name__)
    data = _json(resp)
    if 200 <= resp.status_code < 300:
        payload = data.get("data", data) if isinstance(data, dict) else data
        return payload, _trace(resp, data)
    err = _error_from(resp, data)
    if resp.status_code == 401 and _auth_retry == 0:
        token(force=True)
        return call(method, path, params, body, idempotent, base, 1, _attempt)
    if (resp.status_code == 429 or err.code == "RATE_LIMITED") and _attempt < 3:
        try:
            wait = float(resp.headers.get("Retry-After") or 0)
        except (TypeError, ValueError):
            wait = 0
        _sleep(wait if wait > 0 else 2 ** (_attempt + 1))
        return call(method, path, params, body, idempotent, base, _auth_retry, _attempt + 1)
    if resp.status_code >= 500 and idem and _attempt < 3:
        _sleep(2 ** (_attempt + 1))
        return call(method, path, params, body, idempotent, base, _auth_retry, _attempt + 1)
    raise err


# ---------------- endpoints ----------------

def sync(cursor=None):
    data, _ = call("GET", "/sync", params={"since": cursor or "null"})
    return data or {}


def property_bundle(property_id):
    data, _ = call("GET", "/properties/%s" % property_id)
    return data or {}


def availability(property_id, date_from, date_to, rate_plan_id=None, pre_booking=False):
    p = {"from": date_from, "to": date_to}
    if rate_plan_id:
        p["ratePlanId"] = rate_plan_id
    if pre_booking:
        p["pre_booking"] = "true"
    data, _ = call("GET", "/properties/%s/availability" % property_id, params=p)
    return data or {}


def rates(property_id):
    data, _ = call("GET", "/properties/%s/rates" % property_id)
    return data or {}


def hold(body):
    return call("POST", "/reservations/hold", body=body, idempotent=False)


def confirm(body):
    return call("POST", "/reservations/confirm", body=body, idempotent=True)


def modify(reservation_id, body):
    return call("POST", "/reservations/%s/modify" % reservation_id, body=body, idempotent=True)


def cancel(reservation_id, body):
    return call("POST", "/reservations/%s/cancel" % reservation_id, body=body, idempotent=True)


def get_reservation(reservation_id):
    data, _ = call("GET", "/reservations/%s" % reservation_id)
    return data or {}


def list_reservations(property_id=None, page=1, limit=200):
    p = {"limit": limit, "page": page}
    if property_id:
        p["propertyId"] = property_id
    data, _ = call("GET", "/reservations", params=p)
    return data


def recon_snapshot():
    data, _ = call("GET", "/reconciliation/snapshot")
    return data or {}


def recon_report(body):
    return call("POST", "/reconciliation/report", body=body, idempotent=True)


def trace(trace_id):
    data, _ = call("GET", "/connectivity-traces/%s" % trace_id, base=config.ops_base())
    return data or {}
