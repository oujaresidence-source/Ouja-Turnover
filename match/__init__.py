"""Stay Match — pure scoring engine for the /stay/match guest quiz.

Nothing in this package performs I/O, network calls, or clock reads. bot.py
supplies inventory, availability, prices and coordinates; this package only
ranks. That keeps the whole thing unit-testable with fabricated data.
"""

# match/engine.py (and its `score` re-export) lands in Task 2 — left out here
# on purpose so this package stays importable before that file exists.
