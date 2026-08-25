"""Stay Match — pure scoring engine for the /stay/match guest quiz.

Nothing in this package performs I/O, network calls, or clock reads. bot.py
supplies inventory, availability, prices and coordinates; this package only
ranks. That keeps the whole thing unit-testable with fabricated data.
"""

from .engine import score  # noqa: F401
