# -*- coding: utf-8 -*-
"""`!ouja-tidy` — the bot.py side: overflow categories copy their parent, archived collection
rooms stay "known", every close path ends by moving the room to the archive (and survives
that move failing), a reopened collection room comes back, and the members intent is gated.

Run: python3 -m unittest tests.test_ops_tidy_bot
"""
import asyncio
import os
import re
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-tidy")
os.makedirs(os.environ["STATE_DIR"], exist_ok=True)

import discord  # noqa: E402
import bot  # noqa: E402
sys.stdout.flush()
import ops_tidy_rules as R  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _Resp:
    status, reason = 400, "Bad Request"


def _category_full():
    return discord.HTTPException(_Resp(), {
        "code": 50035, "message": "Invalid Form Body",
        "errors": {"parent_id": {"_errors": [{"code": "CHANNEL_PARENT_MAX_CHANNELS",
                                              "message": "Maximum number of channels in category reached (50)"}]}}})


class Cat:
    _n = 7000

    def __init__(self, name, overwrites=None):
        Cat._n += 1
        self.id, self.name = Cat._n, name
        self.overwrites = dict(overwrites or {})
        self.text_channels = []
        self.position = 0


class Room:
    _n = 9000

    def __init__(self, name, cat=None, topic=""):
        Room._n += 1
        self.id, self.name, self.topic = Room._n, name, topic
        self.category = cat
        self.overwrites = {}
        self.calls = []
        if cat is not None:
            cat.text_channels.append(self)

    async def edit(self, **kw):
        self.calls.append(("edit", kw))
        if "name" in kw:
            self.name = kw["name"]
        if "category" in kw:
            self.category = kw["category"]

    async def send(self, *a, **kw):
        self.calls.append(("send", a))
        room = self

        class _M:
            async def pin(self):
                room.calls.append(("pin",))
        return _M()


class TestSpill(unittest.TestCase):
    def test_overflow_category_is_born_with_the_parents_overwrites(self):
        parent_ow = {"@everyone": discord.PermissionOverwrite(view_channel=False),
                     "RR-role": discord.PermissionOverwrite(view_channel=True)}
        parent = Cat("RR", parent_ow)
        made = []

        class G:
            categories = [parent]

            async def create_text_channel(self, name, category=None, topic=None):
                if category is parent:
                    raise _category_full()
                return Room(name, category, topic or "")

            async def create_category(self, name, overwrites=None, **kw):
                made.append((name, overwrites))
                c = Cat(name, overwrites)
                G.categories.append(c)
                return c

        ch = _run(bot._make_channel_spill(G(), parent, "rr-051-x", "ouja-ticket:rr seq:51"))
        self.assertEqual(made[0][0], "RR ٢")
        self.assertEqual(made[0][1], parent_ow)
        self.assertIsNot(made[0][1], parent.overwrites)          # a copy, not the live dict
        self.assertEqual(ch.category.name, "RR ٢")


class TestDirectpayKnownRooms(unittest.TestCase):
    def test_rooms_in_the_archive_are_still_known(self):
        dp = Cat(bot.DIRECTPAY_CATEGORY)
        arch = Cat(R.archive_name(1))
        Room("تحصيل-001-a", dp, "ouja-dp:111 seq:1")
        Room("مغلقة-تحصيل-002-b", arch, "ouja-dp:222 seq:2")
        Room("مغلقة-rr-003", arch, "ouja-ticket:rr seq:3")
        g = types.SimpleNamespace(categories=[dp, arch])
        rooms = bot._directpay_known_rooms(g)
        self.assertEqual(set(rooms), {"111", "222"})
        self.assertEqual(rooms["222"]["seq"], 2)

    def test_archive_scanned_even_when_the_collection_category_is_gone(self):
        arch = Cat(R.archive_name(2))
        Room("مغلقة-تحصيل-009", arch, "ouja-dp:999 seq:9")
        rooms = bot._directpay_known_rooms(types.SimpleNamespace(categories=[arch]))
        self.assertIn("999", rooms)


class _CloseHarness(unittest.TestCase):
    def setUp(self):
        self.order = []

    async def _ok(self, ch):
        self.order.append(("archive", ch.id))
        return True

    async def _boom(self, ch):
        self.order.append(("archive", ch.id))
        raise RuntimeError("discord down")


class TestTicketCloseArchives(_CloseHarness):
    class _User:
        id, mention = 1, "<@1>"

        def __str__(self):
            return "فيصل"

    def _interaction(self, ch):
        return types.SimpleNamespace(channel=ch, user=self._User())

    def test_tk_close_ends_with_the_archive_move(self):
        ch = Room("rr-070-x", Cat("RR"))
        with mock.patch.object(bot.ops_tidy, "archive_closed_channel", self._ok):
            _run(bot._tk_close(self._interaction(ch)))
        self.assertEqual(ch.name, "مغلقة-rr-070-x")
        self.assertEqual(self.order, [("archive", ch.id)])
        self.assertEqual(ch.calls[-1], ("pin",))       # the close note went out BEFORE the move

    def test_tk_close_survives_a_failing_move(self):
        ch = Room("صيانة-071-x", Cat("صيانه"))
        with mock.patch.object(bot.ops_tidy, "archive_closed_channel", self._boom):
            _run(bot._tk_close(self._interaction(ch)))          # must not raise
        self.assertEqual(ch.name, "مغلقة-صيانة-071-x")
        self.assertEqual(self.order, [("archive", ch.id)])

    def test_directpay_close_ends_with_the_archive_move(self):
        ch = Room("تحصيل-010-x", Cat(bot.DIRECTPAY_CATEGORY))
        with mock.patch.object(bot.ops_tidy, "archive_closed_channel", self._ok):
            _run(bot._directpay_finalize_close(ch, {"id": "dp_x"}, "تم"))
        self.assertEqual(ch.name, "مغلقة-تحصيل-010-x")
        self.assertEqual(self.order, [("archive", ch.id)])

    def test_directpay_close_survives_a_failing_move(self):
        ch = Room("تحصيل-011-x", Cat(bot.DIRECTPAY_CATEGORY))
        with mock.patch.object(bot.ops_tidy, "archive_closed_channel", self._boom):
            _run(bot._directpay_finalize_close(ch, {"id": "dp_y"}, "تم"))
        self.assertEqual(ch.name, "مغلقة-تحصيل-011-x")

    def test_every_close_rename_in_bot_py_is_followed_by_the_archive_call(self):
        """grep '"مغلقة-" +' — every path that renames a room closed must also archive it."""
        with open(bot.__file__, encoding="utf-8") as f:
            src = f.read().splitlines()
        sites = [i for i, ln in enumerate(src) if '"مغلقة-" +' in ln]
        self.assertGreaterEqual(len(sites), 3)
        for i in sites:
            window = "\n".join(src[i:i + 30])
            self.assertIn("ops_tidy.archive_closed_channel(", window, "line %d" % (i + 1))


class TestDirectpayReopenFromArchive(unittest.TestCase):
    @unittest.skipUnless(getattr(bot, "_HAS_DIRECTPAY", False), "directpay package not importable")
    def test_price_up_moves_the_room_back_before_unlocking(self):
        dp = Cat(bot.DIRECTPAY_CATEGORY)
        arch = Cat(R.archive_name(1))
        ch = Room("مغلقة-تحصيل-020-x", arch, "ouja-dp:555 seq:20")
        g = types.SimpleNamespace(categories=[dp, arch], roles=[],
                                  get_channel=lambda cid: ch if int(cid) == ch.id else None)
        t = {"id": "dp_z", "channel_id": str(ch.id), "status": "open"}
        with mock.patch.object(bot.bot, "get_guild", return_value=g), \
                mock.patch.object(bot._directpay.db, "ticket", return_value=t):
            _run(bot._directpay_deliver({"kind": "price_up", "ticket_id": "dp_z", "text": "ارتفع السعر"}))
        moves = [kw for op, *rest in ch.calls if op == "edit" for kw in rest if "category" in kw]
        self.assertEqual(moves[0], {"category": dp, "sync_permissions": True})
        self.assertIs(ch.category, dp)
        self.assertEqual(ch.name, "تحصيل-020-x")              # unlocked after it came back

    @unittest.skipUnless(getattr(bot, "_HAS_DIRECTPAY", False), "directpay package not importable")
    def test_price_up_uses_the_overflow_when_the_category_is_full(self):
        dp = Cat(bot.DIRECTPAY_CATEGORY)
        for i in range(50):
            Room("تحصيل-%03d" % i, dp)
        dp2 = Cat(bot.DIRECTPAY_CATEGORY + " ٢")
        arch = Cat(R.archive_name(1))
        ch = Room("مغلقة-تحصيل-021-x", arch, "ouja-dp:556 seq:21")
        g = types.SimpleNamespace(categories=[dp, dp2, arch], roles=[],
                                  get_channel=lambda cid: ch if int(cid) == ch.id else None)
        t = {"id": "dp_w", "channel_id": str(ch.id), "status": "open"}
        with mock.patch.object(bot.bot, "get_guild", return_value=g), \
                mock.patch.object(bot._directpay.db, "ticket", return_value=t):
            _run(bot._directpay_deliver({"kind": "price_up", "ticket_id": "dp_w", "text": "ارتفع"}))
        self.assertIs(ch.category, dp2)
        self.assertEqual(ch.name, "تحصيل-021-x")


class TestDirectpayCategoryCreation(unittest.TestCase):
    def test_falls_back_to_a_plain_category_if_the_locked_create_is_refused(self):
        made = []

        class G:
            categories = []
            roles = []
            default_role = Cat("@everyone")
            me = None

            def get_role(self, rid):
                return None

            def get_member(self, mid):
                return None

            async def create_category(self, name, overwrites=None, **kw):
                made.append(overwrites)
                if overwrites:
                    raise discord.Forbidden(type("R", (), {"status": 403, "reason": "x"})(), "no")
                c = Cat(name)
                G.categories.append(c)
                return c

        cat = _run(bot._directpay_category(G()))
        self.assertEqual(cat.name, bot.DIRECTPAY_CATEGORY)
        self.assertTrue(made[0])              # tried locked first
        self.assertIsNone(made[-1])           # a room can still open


class TestMembersIntent(unittest.TestCase):
    def test_off_unless_the_env_says_1(self):
        if os.environ.get("MEMBERS_INTENT", "0").strip() != "1":
            self.assertFalse(bot.intents.members)
            self.assertFalse(bot.bot.intents.members)

    def test_source_line_is_env_gated(self):
        with open(bot.__file__, encoding="utf-8") as f:
            src = f.read()
        lines = re.findall(r"^intents\.members\s*=.*$", src, re.M)
        self.assertEqual(len(lines), 1)
        self.assertIn('os.environ.get("MEMBERS_INTENT", "0").strip() == "1"', lines[0])

    def test_wired(self):
        self.assertTrue(hasattr(bot, "ops_tidy"))
        self.assertTrue(callable(bot.ops_tidy.archive_closed_channel))


if __name__ == "__main__":
    unittest.main()
