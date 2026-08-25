# -*- coding: utf-8 -*-
"""
promises — متتبع الوعود (Promise Keeper).

The durable LEDGER + accountability rules for promises made to guests.
Two sources feed it:
  * watchman  — «الرقيب» detects promises in finished chats and opens وعد-###
                ticket rooms (its Discord lifecycle stays as-is; every record is
                MIRRORED here so the dashboard/leaderboard see it).
  * assistant — promises inside replies a HUMAN approved through المساعد
                (approve / edit / dashboard send). Attributed to the approving
                person — something the watchman can never do for bot-signed
                messages. Per the owner's rule, unattended AUTO-sends never
                create promises (Musaed must not commit to anything).

Storage rides brain.db (schedule/db.py patterns: parameterized SQL, short
connections, init lock). Pure decision logic lives in engine.py (TDD)."""

from . import db, engine  # noqa: F401
