# -*- coding: utf-8 -*-
"""digest.schedule — the pure "should the loop fire now?" decision.

bot.py's digest_loop ticks every 30 minutes (the repo's weekly-job house style, like
revenue_loop) and asks this function. It says yes only on DIGEST_DAY at DIGEST_HOUR in
Riyadh, and only if no issue row exists yet for this weekend (`existing_week_of`, read
from digest_issues — a PERSISTED latch, because a redeploy re-runs a loop's first
iteration and an in-memory latch would post twice)."""

from .dates import week_for, RIYADH

EARLIEST_HOUR = 13      # the owner's standing rule: never schedule before 1 PM
DEFAULT_DAY = 2         # Wednesday (Mon=0)
DEFAULT_HOUR = 13


def should_fire(now, day=DEFAULT_DAY, hour=DEFAULT_HOUR, existing_week_of=None):
    if now.tzinfo is None:
        raise ValueError("digest.schedule.should_fire needs a tz-aware datetime")
    local = now.astimezone(RIYADH)
    hour = max(int(hour), EARLIEST_HOUR)
    if local.weekday() != int(day) or local.hour != hour:
        return False
    return week_for(local).iso != (existing_week_of or "")
