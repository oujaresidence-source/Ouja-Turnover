# -*- coding: utf-8 -*-
"""
recovery — «استرداد التجربة», the guest-recovery layer.

THE PRINCIPLE THIS PACKAGE EXISTS TO PROTECT
    No guest leaves Ouja unhappy without a human voice reaching them the same day.

It does NOT judge guests and it does NOT re-score them. The `/guest` scorer in bot.py is
the ONE source of a guest's mood; this package only reads that verdict and turns a low one
into an accountable, time-boxed phone call. There is no second sentiment analyzer in here,
by design — two analyzers means two answers to «هل الضيف زعلان؟» and no way to tell which
one the team should believe.

SCOPE (owner, 2026-08-06): in-house guests only in v1. `/guest` builds its list from
`fetch_inhouse(today)` and has no notion of a departed guest; extending it to checked-out
stays would mean a fresh Sonnet scoring call on every departure, happy or not. That is a
separate decision with its own bill, so it is not smuggled in here.

Layout mirrors ops/ and decor/:
    engine.py — PURE rules: eligibility, priority, compaction, the assignment/equity math.
                No network, no Discord, no DB. Every invariant in tests/test_recovery_*.py
                is locked against THIS file.
    db.py     — recovery_* tables inside the existing brain.db (never a second database).
    llm.py    — the ONE extraction call, with token usage captured. Everything else in the
                project uses bot.claude_json, which throws the usage away; this feature is
                required to report its own bill in SAR, so it reads the raw response.
    notify.py — Arabic card + reminder wording (pure strings, no Discord objects).
    routes.py — /call/{token}, public by necessity: an agent taps it on a phone.
    host.py   — the ONE bridge to bot.py. This package NEVER does `import bot` (bot.py runs
                as __main__; importing it by name would boot a second Discord client).
"""

from . import engine  # noqa: F401

__all__ = ["engine"]
