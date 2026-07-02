# -*- coding: utf-8 -*-
"""
Regression: opening a صيانة/RR/مشتريات ticket must not die when the Discord
category hits its hard 50-channel cap. Closed tickets are KEPT as an audit
trail, so a busy category fills up; _tk_make_channel must spill into an overflow
category and still return a channel. And _tk_open_error_msg must surface the
REAL Discord reason (server-full / no permission) instead of a generic message.

Run:  python3 -m unittest tests.test_ticket_channel_overflow
"""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import discord  # noqa: E402
import bot  # noqa: E402


def _http_error(code, message):
    """Build a discord.HTTPException carrying a Discord error code + text."""
    resp = type("R", (), {"status": 400, "reason": "Bad Request"})()
    return discord.HTTPException(resp, {"code": code, "message": message})


CATEGORY_FULL = lambda: _http_error(50035, "Maximum number of channels in category reached (50)")
SERVER_FULL = lambda: _http_error(50035, "Maximum number of channels reached (500)")


class FakeCategory:
    _n = 0

    def __init__(self, name):
        FakeCategory._n += 1
        self.id = FakeCategory._n
        self.name = name


class FakeChannel:
    def __init__(self, name, category):
        self.name = name
        self.category = category


class FakeGuild:
    """Category #1 is full (raises CATEGORY_FULL); everything else succeeds."""

    def __init__(self):
        self.categories = []
        self.created = []

    async def create_category(self, name):
        c = FakeCategory(name)
        self.categories.append(c)
        return c

    async def create_text_channel(self, name, category=None, topic=None):
        if category is not None and category.id == 1:
            raise CATEGORY_FULL()
        ch = FakeChannel(name, category)
        self.created.append(ch)
        return ch


class TicketOverflowTest(unittest.TestCase):
    def setUp(self):
        FakeCategory._n = 0
        self.guild = FakeGuild()
        self.base = FakeCategory("صيانه")  # id=1, the full one
        self.guild.categories.append(self.base)
        # _tk_make_channel calls _tk_category(guild, kind); stub it to our full base
        self._orig = bot._tk_category

        async def _fake_cat(guild, kind):
            return self.base

        bot._tk_category = _fake_cat

    def tearDown(self):
        bot._tk_category = self._orig

    def test_spills_into_overflow_category_when_primary_full(self):
        ch = asyncio.run(
            bot._tk_make_channel(self.guild, "maint", "صيانة-050-test", "ouja-ticket:maint"))
        self.assertIsNotNone(ch)
        self.assertEqual(ch.name, "صيانة-050-test")
        # landed in a NEW overflow category, not the full base one
        self.assertIsNotNone(ch.category)
        self.assertNotEqual(ch.category.id, 1)

    def test_category_full_detector(self):
        self.assertTrue(bot._tk_category_full(CATEGORY_FULL()))
        self.assertFalse(bot._tk_category_full(SERVER_FULL()))
        self.assertFalse(bot._tk_category_full(_http_error(50013, "Missing Permissions")))

    def test_error_message_surfaces_server_full(self):
        msg = bot._tk_open_error_msg(SERVER_FULL(), "base")
        self.assertIn("مغلقة-", msg)  # tells owner what to delete

    def test_error_message_includes_real_reason_for_unknown(self):
        msg = bot._tk_open_error_msg(_http_error(0, "boom"), "الأساس")
        self.assertIn("الأساس", msg)
        self.assertIn("boom", msg)


if __name__ == "__main__":
    unittest.main()
