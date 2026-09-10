# -*- coding: utf-8 -*-
"""
directpay.config — every DIRECTPAY_* environment variable, read at call time (never cached)
so a Railway change or a test's os.environ edit is seen immediately. Every default is safe
to deploy as-is: the feature is ON but DRY-RUN, and nothing is posted until the owner flips
DIRECTPAY_DRYRUN to 0.
"""
import os

_TRUE = ("1", "true", "True", "yes")


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


def _float(name, default):
    try:
        return float(str(_env(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return float(default)


def enabled():
    return _flag("DIRECTPAY_ENABLED", "1")


def dryrun():
    """ON by default. The first deploy is observable and silent; the owner flips it."""
    return _flag("DIRECTPAY_DRYRUN", "1")


def start_date_env():
    return _env("DIRECTPAY_START_DATE", "").strip()


def category():
    return _env("DIRECTPAY_CATEGORY", "تحصيل الحجوزات المباشرة").strip() or "تحصيل الحجوزات المباشرة"


def summary_channel():
    return _env("DIRECTPAY_SUMMARY_CHANNEL", "تحصيل-الملخص").strip() or "تحصيل-الملخص"


def parse_close_ids(raw):
    """Arabic comma tolerated (like _maint_close_ids). Anything that is not a whole number is
    dropped. A garbled or empty value therefore yields [] — 'administrators only' — and can
    never widen the gate to everybody."""
    out = []
    for p in str(raw or "").replace("،", ",").split(","):
        p = p.strip()
        if p.isdigit():
            out.append(int(p))
    return out


def close_ids():
    return parse_close_ids(_env("DIRECTPAY_CLOSE_IDS", ""))


def ping_role_id():
    v = _env("DIRECTPAY_PING_ROLE_ID", "").strip()
    return int(v) if v.isdigit() else 0


def poll_min():
    return max(2, _int("DIRECTPAY_POLL_MIN", 10))


def lookback_days():
    return max(0, _int("DIRECTPAY_LOOKBACK_DAYS", 3))


def horizon_days():
    return 400


def max_open_per_tick():
    return max(0, _int("DIRECTPAY_MAX_OPEN_PER_TICK", 5))


def nudge_after_days():
    return max(0, _int("DIRECTPAY_NUDGE_AFTER_DAYS", 2))


def nudge_every_days():
    return max(1, _int("DIRECTPAY_NUDGE_EVERY_DAYS", 2))


def summary_hour():
    return min(23, max(0, _int("DIRECTPAY_SUMMARY_HOUR", 13)))


def variance_sar():
    return max(0.0, _float("DIRECTPAY_VARIANCE_SAR", 1.0))


def variance_pct():
    return max(0.0, _float("DIRECTPAY_VARIANCE_PCT", 0.01))


def proof_max_mb():
    return max(1, _int("DIRECTPAY_PROOF_MAX_MB", 12))


def watch_days():
    return max(0, _int("DIRECTPAY_WATCH_DAYS", 30))


def extra_channels():
    """Lowercase substrings treated as direct IN ADDITION to bot._finance_channel. The
    classifier itself is never edited from here."""
    return [p.strip().lower() for p in _env("DIRECTPAY_EXTRA_CHANNELS", "").split(",") if p.strip()]


def refresh_every_hours():
    return max(1, _int("DIRECTPAY_REFRESH_HOURS", 6))


def refresh_max_per_tick():
    return max(0, _int("DIRECTPAY_REFRESH_MAX_PER_TICK", 5))


def summary_bucket_examples():
    return 5
