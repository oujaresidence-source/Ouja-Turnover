# -*- coding: utf-8 -*-
"""
stayhub.config — every STAYHUB_* environment variable, read at call time (never cached).

SAFE BY CONSTRUCTION
    * No credentials  ⇒ nothing runs (configured() is False): no sync, no push, no calls.
    * No unit mapped  ⇒ no reservation is ever pushed. A Hostaway listing reaches StayHub only
      after an administrator maps it to a StayHub property (POST /api/stayhub/map).
    * Only Airbnb reservations are pushed by default. Direct bookings are already handled in
      StayHub by the team (see directpay/) — pushing them too would double-book the unit there.

The client secret lives in Railway variables ONLY. Never commit it, never print it.
"""
import os

_TRUE = ("1", "true", "True", "yes")

SANDBOX_BASE = "https://sandbox.apis.stayhub.sa"


def _env(name, default=""):
    v = os.environ.get(name)
    return default if v is None else v


def _flag(name, default):
    return _env(name, default).strip() in _TRUE


def _int(name, default):
    try:
        return int(str(_env(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return int(default)


def enabled():
    return _flag("STAYHUB_ENABLED", "1")


def dryrun():
    """1 ⇒ everything is computed and logged but hold/confirm/modify/cancel are NOT sent.
    Default 1, like every other module here: real pushes need STAYHUB_DRYRUN=0 on top of the
    credentials and a unit an administrator mapped by hand."""
    return _flag("STAYHUB_DRYRUN", "1")


def host_base():
    return (_env("STAYHUB_BASE_URL", SANDBOX_BASE).strip() or SANDBOX_BASE).rstrip("/")


def api_base():
    return host_base() + "/api/v2/connectivity"


def ops_base():
    return host_base() + "/api/v2/operations"


def token_url():
    return _env("STAYHUB_TOKEN_URL", "").strip() or (host_base() + "/connectivity/oauth/token")


def client_id():
    return _env("STAYHUB_CLIENT_ID", "").strip()


def client_secret():
    return _env("STAYHUB_CLIENT_SECRET", "").strip()


def partner_id():
    return _env("STAYHUB_PARTNER_ID", "").strip()


def scope():
    return _env("STAYHUB_SCOPE", "stayhub-connectivity").strip() or "stayhub-connectivity"


def configured():
    return bool(enabled() and client_id() and client_secret())


def webhook_secrets():
    """Candidate HMAC keys for the signed webhooks / sync probe, in order. StayHub has not yet
    told us which key signs them: an explicit STAYHUB_WEBHOOK_SECRET wins, then the client
    secret. An empty list ⇒ every signed call is refused (fail closed)."""
    out = []
    for v in (_env("STAYHUB_WEBHOOK_SECRET", ""), _env("STAYHUB_PROBE_SECRET", ""), client_secret()):
        v = (v or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def signature_max_age_s():
    return max(30, _int("STAYHUB_SIG_MAX_AGE_S", 300))


def push_channels():
    """finance_channel values pushed to StayHub. Default airbnb only (see module doc)."""
    raw = _env("STAYHUB_CHANNELS", "airbnb")
    return {p.strip().lower() for p in raw.replace("،", ",").split(",") if p.strip()}


def sync_every_s():
    return max(30, _int("STAYHUB_SYNC_SEC", 60))


def push_every_min():
    return max(2, _int("STAYHUB_PUSH_MIN", 10))


def horizon_days():
    return min(500, max(30, _int("STAYHUB_HORIZON_DAYS", 400)))


def max_push_per_tick():
    return max(0, _int("STAYHUB_MAX_PUSH_PER_TICK", 8))


def retry_rejected_hours():
    return max(1, _int("STAYHUB_RETRY_REJECTED_HOURS", 6))


def max_rejected_attempts():
    return max(1, _int("STAYHUB_MAX_REJECTED_ATTEMPTS", 8))


def recon_hour():
    return min(23, max(0, _int("STAYHUB_RECON_HOUR", 4)))


def recon_days_ahead():
    return max(7, _int("STAYHUB_RECON_DAYS", 90))


def http_timeout_s():
    return max(3, _int("STAYHUB_HTTP_TIMEOUT_S", 20))


def default_currency():
    return (_env("STAYHUB_CURRENCY", "SAR").strip() or "SAR").upper()
