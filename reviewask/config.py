# -*- coding: utf-8 -*-
"""
reviewask.config — every env knob, read at CALL time (a Railway change lands without a code
change, and the tests set os.environ freely). Defaults are the owner-approved values; the owner
never opens Railway, so a default must already be right (spec §16).
"""

import os

from . import engine


def _env(name, default):
    v = os.environ.get(name)
    if v is None or str(v).strip() == "":
        return default
    return str(v).strip()


def _int(name, default, lo=None):
    try:
        v = int(_env(name, str(default)))
    except ValueError:
        return default
    return max(lo, v) if lo is not None else v


def _hhmm(name, default):
    v = _env(name, default)
    return v if engine.parse_hhmm(v) else default


def enabled():
    return _env("REVIEWASK_ENABLED", "1") == "1"


def live_env():
    """Owner ruling 2026-10-03 («شغل البوت بدون ما اسوي شي»): ON by default — he never opens
    Railway or types /reviews-start. /reviews-stop (the stored switch) still wins over this."""
    return _env("REVIEWASK_LIVE", "1") == "1"


def threshold():
    v = _env("REVIEWASK_THRESHOLD", "4.75")
    try:
        f = float(v)
    except ValueError:
        return "4.75"
    return v if 0 < f < 5 else "4.75"


def min_reviews():
    return _int("REVIEWASK_MIN_REVIEWS", 3, 0)


def wa_at():
    return _hhmm("REVIEWASK_WA_AT", "17:00")


def call_at():
    v = _env("REVIEWASK_CALL_AT", "auto")
    return v if engine.parse_hhmm(v) else "auto"


def max_calls():
    return _int("REVIEWASK_MAX_CALLS", 2, 1)


def window_days():
    return _int("REVIEWASK_WINDOW_DAYS", 14, 1)


def quiet_from():
    return _hhmm("REVIEWASK_QUIET_FROM", "22:00")


def quiet_to():
    return _hhmm("REVIEWASK_QUIET_TO", "13:00")


def delete_after_days():
    return _int("REVIEWASK_DELETE_AFTER_DAYS", 7, 1)


def category():
    return _env("REVIEWASK_CATEGORY", "طلبات التقييم")


def board_channel():
    return _env("REVIEWASK_BOARD_CHANNEL", "متابعة-التقييمات")


def review_url():
    return _env("REVIEWASK_REVIEW_URL", "https://www.airbnb.com/users/reviews")


def open_at():
    return _hhmm("REVIEWASK_OPEN_AT", "00:05")


def report_every():
    return _int("REVIEWASK_REPORT_MIN", 30, 10)


def report_from():
    return _hhmm("REVIEWASK_REPORT_FROM", "17:00")


def summary_at():
    return _hhmm("REVIEWASK_SUMMARY_AT", "22:00")


def _hijri_month():
    """hijridate's Umm al-Qura month when importable (Ramadan = 9), else None (spec §8)."""
    try:
        from hijridate import Gregorian
    except Exception:
        return None

    def month(d):
        return Gregorian(d.year, d.month, d.day).to_hijri().month
    return month


def snapshot():
    """The engine's cfg dict, built fresh from the environment."""
    c = engine.default_cfg()
    c.update({
        "threshold": threshold(), "min_reviews": min_reviews(), "wa_at": wa_at(),
        "call_at": call_at(), "max_calls": max_calls(), "window_days": window_days(),
        "quiet_from": quiet_from(), "quiet_to": quiet_to(),
        "ramadan": engine.parse_ramadan(_env("REVIEWASK_RAMADAN", "")),
        "hijri_month": _hijri_month(),
    })
    return c
