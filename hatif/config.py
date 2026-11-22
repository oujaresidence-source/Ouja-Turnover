# -*- coding: utf-8 -*-
"""
hatif.config — every HATIF_* environment variable, read at call time (never cached).

SAFE BY CONSTRUCTION
    * HATIF_DRYRUN defaults to 1 ⇒ nothing is ever sent to a guest and no conversation is
      touched; the would-be reply is posted to Discord instead.
    * No HATIF_WEBHOOK_SECRET ⇒ the webhook refuses every request (401).
    * No client id/secret ⇒ listen-only: date messages are answered on Discord only.
    * HATIF_TEST_NUMBERS set ⇒ live sends reach only those numbers.

Secrets live in Railway variables ONLY. Never commit them, never print them.
"""
import os
import re

_TRUE = ("1", "true", "True", "yes")
API_BASE = "https://api.voxa.sa"


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
    return _flag("HATIF_ENABLED", "1")


def dryrun():
    return _flag("HATIF_DRYRUN", "1")


def api_base():
    return (_env("HATIF_API_BASE", API_BASE).strip() or API_BASE).rstrip("/")


def client_id():
    return _env("HATIF_CLIENT_ID").strip()


def client_secret():
    return _env("HATIF_CLIENT_SECRET").strip()


def configured():
    """True when the API can be called (needed to learn the guest's number and to send)."""
    return bool(client_id() and client_secret())


def webhook_secret():
    return _env("HATIF_WEBHOOK_SECRET").strip()


def channel_id():
    """When set, messages from any other Hatif channel are ignored."""
    return _env("HATIF_CHANNEL_ID").strip()


def bot_user_id():
    """The Hatif seat the menu flow assigns a conversation to when the guest wants live dates."""
    return _env("HATIF_BOT_USER_ID").strip()


def human_user_id():
    """Who gets the conversation when the bot cannot read the dates twice. Empty ⇒ unassign."""
    return _env("HATIF_HUMAN_USER_ID").strip()


def gate():
    """"assigned" (default): answer only conversations assigned to the bot seat.
    "dates": answer any unassigned conversation whose message reads as dates (the menu flow
    may answer too — use only when the flow is built to stay quiet)."""
    g = _env("HATIF_GATE", "assigned").strip().lower()
    return g if g in ("assigned", "dates") else "assigned"


def release_after_reply():
    return _flag("HATIF_RELEASE", "1")


def ack():
    """Send «لحظة أشيك لك» before the search (one extra message per answer)."""
    return _flag("HATIF_ACK", "1")


def test_numbers():
    """Normalised digits of the allowed test numbers. Empty set ⇒ no allowlist."""
    from . import engine
    out = set()
    for part in re.split(r"[,;\n]+", _env("HATIF_TEST_NUMBERS")):
        n = engine.normalize_phone(part)
        if n:
            out.add(n)
    return out


def max_per_min():
    return max(1, _int("HATIF_MAX_PER_MIN", 20))


def max_units():
    return min(10, max(1, _int("HATIF_MAX_UNITS", 6)))


def max_nights():
    return max(1, _int("HATIF_MAX_NIGHTS", 30))


def timeout_s():
    return max(3, _int("HATIF_TIMEOUT_S", 15))


# ---- the WhatsApp «reader» (brain.py) — Phase 1 is SILENT: it composes, never sends ----
def ai_enabled():
    """HATIF_AI=0 switches the reader off entirely (back to exactly the pre-reader behaviour)."""
    return _flag("HATIF_AI", "1")


def ai_max_per_min():
    """Cap on AI reads per minute (cost guard). Over it, messages are skipped, not queued."""
    return max(1, _int("HATIF_AI_MAX_PER_MIN", 10))
