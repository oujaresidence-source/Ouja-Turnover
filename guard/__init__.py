"""Deterministic safety guards for the guest-facing assistant «مساعد».

Additive by design: nothing in here sends a message, and nothing in here can make the
assistant say something it would not already have said. Every module only ever REMOVES
an outbound. bot.py imports this package behind a `_HAS_GUARD` flag, the same way it
imports ops/, so a broken import degrades to today's behaviour instead of a dead bot.

No network. No Anthropic key. No Hostaway. Everything here is a pure function of its
arguments so it can be unit-tested without a live system.
"""

from guard.outbound import Verdict, check_outbound, door_code_leak

__all__ = ["Verdict", "check_outbound", "door_code_leak"]
