# -*- coding: utf-8 -*-
"""Financial statements + budget math — PURE functions only.

No aiohttp, no bot.py access, no I/O: callers pass in plain dicts/lists
(imported Daftra journals, chart of accounts, budgets) and get plain dicts
back. That keeps every number here unit-testable with synthetic data.

Filled in by Slice 7 (القوائم المالية + الميزانية).
"""
