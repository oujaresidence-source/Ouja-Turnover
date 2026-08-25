# -*- coding: utf-8 -*-
"""M6 regression — turnover/cleaning channels must survive the 50-channel
category cap (the same failure class fixed for tickets in cb779d3), and the
existence scans must cover overflow categories so nothing gets duplicated.

Run: python3 -m unittest tests.test_turnover_channel_overflow_m6
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-m6")
os.makedirs("/tmp/ouja-test-state-m6", exist_ok=True)

import discord  # noqa: E402
import bot  # noqa: E402


def _http_error(code, message):
    resp = type("R", (), {"status": 400, "reason": "Bad Request"})()
    return discord.HTTPException(resp, {"code": code, "message": message})


CATEGORY_FULL = lambda: _http_error(50035, "Maximum number of channels in category reached (50)")


class FakeCategory:
    _n = 0

    def __init__(self, name):
        FakeCategory._n += 1
        self.id = FakeCategory._n
        self.name = name
        self.text_channels = []


class FakeChannel:
    def __init__(self, name, category, topic=None):
        self.name = name
        self.category = category
        self.topic = topic


class FakeGuild:
    def __init__(self, full_ids=frozenset()):
        self.categories = []
        self.created = []
        self.full_ids = set(full_ids)

    async def create_category(self, name):
        c = FakeCategory(name)
        self.categories.append(c)
        return c

    async def create_text_channel(self, name, category=None, topic=None):
        if category is not None and category.id in self.full_ids:
            raise CATEGORY_FULL()
        ch = FakeChannel(name, category, topic)
        if category is not None:
            category.text_channels.append(ch)
        self.created.append(ch)
        return ch


class TurnoverOverflowM6Test(unittest.TestCase):
    def setUp(self):
        FakeCategory._n = 0

    def test_spill_into_overflow_when_category_full(self):
        guild = FakeGuild(full_ids={1})
        base = FakeCategory("مهام-التنظيف")            # id 1 — full
        guild.categories.append(base)
        ch = asyncio.run(bot._make_channel_spill(guild, base, "ouja-101a", topic="t"))
        self.assertIsNotNone(ch)
        self.assertIsNotNone(ch.category, "must land in an overflow category, not the root")
        self.assertIn("٢", ch.category.name)

    def test_non_cap_errors_bubble_up(self):
        guild = FakeGuild()
        base = FakeCategory("مهام-التنظيف")

        async def forbidden(name, category=None, topic=None):
            raise discord.Forbidden(type("R", (), {"status": 403, "reason": "Forbidden"})(),
                                    {"code": 50013, "message": "Missing Permissions"})
        guild.create_text_channel = forbidden
        with self.assertRaises(discord.Forbidden):
            asyncio.run(bot._make_channel_spill(guild, base, "ouja-101a"))

    def test_category_family_finds_overflow_twins(self):
        guild = FakeGuild()
        base = FakeCategory("مهام-التنظيف")
        twin = FakeCategory("مهام-التنظيف ٢")
        other = FakeCategory("صيانه")
        guild.categories += [base, twin, other]
        fam = bot._category_family(guild, base)
        self.assertIn(base, fam)
        self.assertIn(twin, fam, "overflow twins must be scanned (else duplicates)")
        self.assertNotIn(other, fam)


if __name__ == "__main__":
    unittest.main()
