"""Synthetic-data tests for ops_audit (the read-only !ouja-audit inventory).

No Discord connection: a fake guild made of duck-typed objects is walked by the
real `collect()`, then the derived summary/CSV/warnings are asserted. This is the
CLAUDE.md "feed fake data into the new function and assert the numbers" gate.
"""
import asyncio
import csv
import io
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ops_audit

NOW = datetime.now(timezone.utc)


# ----------------------------------------------------------------- the fakes
class FakeOverwrite:
    """Mimics discord.PermissionOverwrite: iterates (name, True/False)."""

    def __init__(self, **kw):
        self._kw = kw

    def __iter__(self):
        return iter(self._kw.items())

    def __getattr__(self, item):
        return self._kw.get(item)


class FakeRole:
    def __init__(self, rid, name, position=0, admin=False, mentionable=False, members=()):
        self.id, self.name, self.position = rid, name, position
        self.mentionable = mentionable
        self.members = list(members)
        self.permissions = type("P", (), {"administrator": admin})()


class FakeMember:
    def __init__(self, mid, name, bot=False):
        self.id, self.name, self.bot = mid, name, bot


class FakeMsg:
    def __init__(self, created_at, author):
        self.created_at, self.author = created_at, author


class FakeChannel:
    def __init__(self, cid, name, ctype="text", category=None, position=0,
                 topic="", messages=(), overwrites=None, forbidden=False,
                 visible_to=None):
        self.id, self.name, self.type = cid, name, ctype
        self.category, self.position, self.topic = category, position, topic
        self.created_at = NOW - timedelta(days=400)
        self.overwrites = overwrites or {}
        self._messages = list(messages)
        self._forbidden = forbidden
        self._visible_to = visible_to           # None => everyone

    def history(self, limit=100, after=None):
        import discord

        async def gen():
            if self._forbidden:
                raise discord.Forbidden(
                    type("R", (), {"status": 403, "reason": "Forbidden"})(), "no")
            n = 0
            for m in self._messages:            # newest first, like discord.py
                if after is not None and m.created_at <= after:
                    continue
                if n >= limit:
                    return
                n += 1
                yield m
        return gen()

    def permissions_for(self, member):
        ok = self._visible_to is None or member.id in self._visible_to
        return type("P", (), {"view_channel": ok})()


class NoHistoryChannel(FakeChannel):
    """Forum + voice channels expose no history() — must not be a failure."""

    def __getattribute__(self, item):
        if item == "history":
            raise AttributeError("history")
        return object.__getattribute__(self, item)


class FakeCategory(FakeChannel):
    def __init__(self, cid, name, position=0, overwrites=None):
        super().__init__(cid, name, ctype="category", position=position,
                         overwrites=overwrites)


class FakeThread:
    def __init__(self, parent_id):
        self.parent_id = parent_id


class FakeGuild:
    def __init__(self, channels, roles, members, threads=()):
        self.name, self.id = "Ouja", 1
        self.channels, self.roles = channels, roles
        self._members, self._threads = members, list(threads)
        self.default_role = roles[0]
        self.member_count = len(members)

    @property
    def members(self):
        return self._members

    async def active_threads(self):
        return self._threads


def build_guild(members_on=True, n_open=3):
    everyone = FakeRole(10, "@everyone", position=0)
    ops = FakeRole(11, "ops", position=1, admin=True, mentionable=True)
    members = [FakeMember(100, "a"), FakeMember(101, "b"), FakeMember(999, "bot", bot=True)]
    if not members_on:
        members = []

    cat_full = FakeCategory(20, "صيانه", position=0)
    cat_priv = FakeCategory(21, "خاص", position=1,
                            overwrites={everyone: FakeOverwrite(view_channel=False)})

    chans = []
    # fresh, open to all
    chans.append(FakeChannel(30, "general", category=cat_full, position=0,
                             messages=[FakeMsg(NOW - timedelta(days=1), "faisal")]))
    # stale (90 days)
    chans.append(FakeChannel(31, "old-cleaning", category=cat_full, position=1,
                             messages=[FakeMsg(NOW - timedelta(days=90), "sara")]))
    # never had a message
    chans.append(FakeChannel(32, "empty", category=cat_full, position=2))
    # restricted + only member 100 can see it
    chans.append(FakeChannel(33, "private", category=cat_priv, position=0,
                             overwrites={everyone: FakeOverwrite(view_channel=False),
                                         ops: FakeOverwrite(view_channel=True)},
                             messages=[FakeMsg(NOW - timedelta(days=2), "faisal")],
                             visible_to={100}))
    # forbidden history
    chans.append(FakeChannel(34, "locked", category=cat_priv, position=1, forbidden=True))
    # voice/forum channel: no history() api at all
    chans.append(NoHistoryChannel(35, "صوت", ctype="voice", category=cat_full, position=3))

    for i in range(n_open):                            # padding, all open+fresh
        chans.append(FakeChannel(200 + i, f"pad{i}", category=cat_full, position=10 + i,
                                 messages=[FakeMsg(NOW - timedelta(days=3), "x")]))

    return FakeGuild([cat_full, cat_priv] + chans, [everyone, ops], members,
                     threads=[FakeThread(30), FakeThread(30), FakeThread(31)])


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ------------------------------------------------------------------- the tests
class TestPureHelpers(unittest.TestCase):
    def test_stale_rules(self):
        self.assertTrue(ops_audit._is_stale(None, NOW))                       # never posted
        self.assertTrue(ops_audit._is_stale(NOW - timedelta(days=61), NOW))
        self.assertFalse(ops_audit._is_stale(NOW - timedelta(days=59), NOW))

    def test_overwrite_rows_split_allow_deny(self):
        everyone = FakeRole(10, "@everyone")
        rows = ops_audit._overwrite_rows(
            {everyone: FakeOverwrite(view_channel=False, send_messages=True)})
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["kind"], "role")
        self.assertEqual(r["deny"], ["view_channel"])
        self.assertEqual(r["allow"], ["send_messages"])
        self.assertTrue(r["hides_channel"])
        self.assertFalse(r["grants_view"])

    def test_type_name_handles_real_and_fake(self):
        import discord
        self.assertEqual(ops_audit._type_name(
            type("C", (), {"type": discord.ChannelType.category})()), "category")
        self.assertEqual(ops_audit._type_name(type("C", (), {"type": "voice"})()), "voice")


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.inv = run(ops_audit.collect(build_guild()))

    def test_counts_exclude_categories(self):
        self.assertEqual(self.inv["limits"]["channels"]["used"], 9)
        self.assertEqual(self.inv["limits"]["categories"]["used"], 2)
        self.assertEqual(self.inv["limits"]["channels"]["max"], 500)

    def test_active_threads_total_and_per_channel(self):
        self.assertEqual(self.inv["limits"]["active_threads"]["used"], 3)
        by_name = {c["name"]: c for c in self.inv["channels"]}
        self.assertEqual(by_name["general"]["active_threads"], 2)
        self.assertEqual(by_name["old-cleaning"]["active_threads"], 1)
        self.assertEqual(by_name["empty"]["active_threads"], 0)

    def test_stale_and_last_message(self):
        by_name = {c["name"]: c for c in self.inv["channels"]}
        self.assertFalse(by_name["general"]["stale"])
        self.assertEqual(by_name["general"]["last_message_by"], "faisal")
        self.assertTrue(by_name["old-cleaning"]["stale"])
        self.assertTrue(by_name["empty"]["stale"])
        self.assertIsNone(by_name["empty"]["last_message_at"])

    def test_forbidden_is_recorded_not_fatal(self):
        by_name = {c["name"]: c for c in self.inv["channels"]}
        self.assertFalse(by_name["locked"]["accessible"])
        self.assertEqual(by_name["locked"]["read_note"], "forbidden")
        self.assertTrue(by_name["locked"]["stale"])
        self.assertEqual(by_name["صوت"]["read_note"], "no_history_api")
        self.assertTrue(by_name["صوت"]["accessible"])

    def test_restricted_and_visibility(self):
        by_name = {c["name"]: c for c in self.inv["channels"]}
        self.assertTrue(by_name["private"]["restricted"])
        self.assertFalse(by_name["general"]["restricted"])
        # 2 non-bot members; the private channel is visible to 1 of them
        self.assertEqual(by_name["general"]["of_members"], 2)
        self.assertEqual(by_name["general"]["can_see"], 2)
        self.assertEqual(by_name["private"]["can_see"], 1)

    def test_category_rows(self):
        by_name = {c["name"]: c for c in self.inv["categories"]}
        self.assertEqual(by_name["صيانه"]["channel_count"], 7)
        self.assertFalse(by_name["صيانه"]["at_cap"])
        self.assertTrue(by_name["خاص"]["everyone_denied_view"])
        self.assertEqual(by_name["خاص"]["channel_count"], 2)

    def test_roles(self):
        ops = [r for r in self.inv["roles"] if r["name"] == "ops"][0]
        self.assertTrue(ops["is_admin"])
        self.assertTrue(ops["mentionable"])

    def test_no_deep_fields_in_normal_mode(self):
        self.assertNotIn("messages_30d", self.inv["channels"][0])
        self.assertEqual(self.inv["mode"], "normal")

    def test_members_intent_off_records_none_not_a_guess(self):
        inv = run(ops_audit.collect(build_guild(members_on=False)))
        self.assertFalse(inv["members_intent_available"])
        for c in inv["channels"]:
            self.assertIsNone(c["can_see"])
            self.assertIsNone(c["of_members"])

    def test_deep_mode_counts_30d_window(self):
        g = build_guild()
        ch = FakeChannel(300, "busy", category=None, messages=[
            FakeMsg(NOW - timedelta(days=1), "a"),
            FakeMsg(NOW - timedelta(days=10), "b"),
            FakeMsg(NOW - timedelta(days=40), "c"),      # outside the window
        ])
        g.channels.append(ch)
        inv = run(ops_audit.collect(g, deep=True))
        busy = [c for c in inv["channels"] if c["name"] == "busy"][0]
        self.assertEqual(busy["messages_30d"], 2)
        self.assertEqual(busy["messages_30d_capped_at"], 200)
        self.assertEqual(inv["mode"], "deep")


class TestDerived(unittest.TestCase):
    def test_warnings_flag_cap_and_stale(self):
        inv = run(ops_audit.collect(build_guild()))
        # small guild: no near-cap warning, but stale + visibility lines exist
        joined = " ".join(inv["warnings"])
        self.assertIn("قناة ميتة", joined)
        self.assertIn("🌍", joined)
        self.assertIn("ما قدر البوت يقرأ", joined)
        self.assertNotIn("قريب من حد ديسكورد", joined)

    def test_near_cap_and_full_category_warnings(self):
        inv = {
            "limits": {"channels": {"used": 450, "max": 500},
                       "categories": {"used": 20, "max": 50},
                       "active_threads": {"used": 5, "max": 1000, "error": None}},
            "categories": [{"name": "صيانه", "channel_count": 50, "at_cap": True}],
            "channels": [{"name": "x", "stale": False, "restricted": False,
                          "accessible": True, "can_see": None, "of_members": None}],
        }
        w = " ".join(ops_audit.build_warnings(inv))
        self.assertIn("450 من 500", w)
        self.assertIn("ممتلئ", w)

    def test_csv_is_utf8_sig_and_round_trips_arabic(self):
        inv = run(ops_audit.collect(build_guild()))
        raw = ops_audit.build_csv(inv)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))          # Excel BOM
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertEqual(len(rows), len(inv["channels"]))
        priv = [r for r in rows if r["channel"] == "private"][0]
        self.assertEqual(priv["restricted"], "yes")
        self.assertEqual(priv["hides_from"], "@everyone")
        self.assertEqual(priv["grants_view_to"], "ops")
        self.assertTrue(any(r["channel"] == "صوت" for r in rows))

    def test_summary_is_arabic_and_fits_discord(self):
        inv = run(ops_audit.collect(build_guild()))
        s = ops_audit.build_summary(inv)
        self.assertLessEqual(len(s), 2000)
        self.assertIn("جرد سيرفر ديسكورد", s)
        self.assertIn("من 500", s)
        self.assertIn("قراءة فقط", s)

    def test_files_are_named_by_day(self):
        inv = run(ops_audit.collect(build_guild()))
        files = ops_audit.build_files(inv)
        day = inv["guild"]["generated_at"][:10]
        self.assertEqual([f.filename for f in files],
                         [f"ouja_audit_{day}.json", f"ouja_audit_{day}.csv"])


class TestGate(unittest.TestCase):
    def _msg(self, uid, admin):
        author = type("A", (), {"id": uid, "bot": False,
                                "guild_permissions": type("P", (), {"administrator": admin})()})()
        return type("M", (), {"author": author})()

    def test_owner_env_allows(self):
        old = os.environ.get("OWNER_DISCORD_ID")
        os.environ["OWNER_DISCORD_ID"] = "777"
        try:
            self.assertTrue(ops_audit._is_allowed(self._msg(777, False)))
            self.assertFalse(ops_audit._is_allowed(self._msg(778, False)))
            self.assertTrue(ops_audit._is_allowed(self._msg(778, True)))
        finally:
            if old is None:
                os.environ.pop("OWNER_DISCORD_ID", None)
            else:
                os.environ["OWNER_DISCORD_ID"] = old

    def test_admin_fallback_without_env(self):
        old = os.environ.pop("OWNER_DISCORD_ID", None)
        try:
            self.assertTrue(ops_audit._is_allowed(self._msg(1, True)))
            self.assertFalse(ops_audit._is_allowed(self._msg(1, False)))
        finally:
            if old is not None:
                os.environ["OWNER_DISCORD_ID"] = old


class FakeSent:
    def __init__(self, content=None, files=None):
        self.content, self.files, self.edits = content, files, []

    async def edit(self, content=None):
        self.edits.append(content)
        self.content = content


class FakeChannelOut:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, files=None):
        s = FakeSent(content, files)
        self.sent.append(s)
        return s


class FakeMessage:
    def __init__(self, content, guild, uid=777, admin=True, is_bot=False):
        self.content, self.guild = content, guild
        self.author = type("A", (), {
            "id": uid, "bot": is_bot,
            "guild_permissions": type("P", (), {"administrator": admin})()})()
        self.channel = FakeChannelOut()
        self.replies = []

    async def reply(self, content=None, mention_author=True):
        s = FakeSent(content)
        self.replies.append(s)
        return s


class TestListenerEndToEnd(unittest.TestCase):
    """The whole !ouja-audit path with a fake message — no Discord connection."""

    def test_non_trigger_message_is_ignored(self):
        m = FakeMessage("مساء الخير", build_guild())
        run(ops_audit.handle_message(m))
        self.assertEqual(m.replies, [])
        self.assertEqual(m.channel.sent, [])

    def test_prefix_command_is_not_hijacked(self):
        m = FakeMessage("!ouja dispatch", build_guild())
        run(ops_audit.handle_message(m))
        self.assertEqual(m.replies, [])

    def test_bot_messages_ignored(self):
        m = FakeMessage("!ouja-audit", build_guild(), is_bot=True)
        run(ops_audit.handle_message(m))
        self.assertEqual(m.replies, [])

    def test_non_admin_is_refused_and_nothing_is_read(self):
        m = FakeMessage("!ouja-audit", build_guild(), uid=5, admin=False)
        old = os.environ.pop("OWNER_DISCORD_ID", None)
        try:
            run(ops_audit.handle_message(m))
        finally:
            if old is not None:
                os.environ["OWNER_DISCORD_ID"] = old
        self.assertEqual(len(m.replies), 1)
        self.assertIn("للمالك أو الأدمن فقط", m.replies[0].content)
        self.assertEqual(m.channel.sent, [])

    def test_admin_gets_status_then_summary_then_two_files(self):
        m = FakeMessage("!ouja-audit", build_guild(), admin=True)
        run(ops_audit.handle_message(m))
        self.assertEqual(len(m.replies), 1)
        status = m.replies[0]
        self.assertEqual(len(status.edits), 1)                  # small guild: no progress tick
        self.assertIn("جرد سيرفر ديسكورد", status.content)      # edited into the summary
        self.assertEqual(len(m.channel.sent), 1)
        files = m.channel.sent[0].files
        self.assertEqual(len(files), 2)
        self.assertTrue(files[0].filename.endswith(".json"))
        self.assertTrue(files[1].filename.endswith(".csv"))

    def test_progress_ticks_so_it_never_looks_frozen(self):
        g = build_guild(n_open=110)                             # 116 channels
        old_sleep = ops_audit.SLEEP_SECONDS
        ops_audit.SLEEP_SECONDS = 0                             # keep the test fast
        try:
            m = FakeMessage("!ouja-audit", g, admin=True)
            run(ops_audit.handle_message(m))
        finally:
            ops_audit.SLEEP_SECONDS = old_sleep
        edits = m.replies[0].edits
        self.assertEqual(edits[0], "⏳ 50/116 قناة… (قراءة فقط)")
        self.assertEqual(edits[1], "⏳ 100/116 قناة… (قراءة فقط)")
        self.assertIn("جرد سيرفر ديسكورد", edits[-1])

    def test_deep_word_is_accepted(self):
        m = FakeMessage("!ouja-audit deep", build_guild(), admin=True)
        run(ops_audit.handle_message(m))
        self.assertIn("مفصّل (deep)", m.replies[0].content)

    def test_failure_reports_the_real_exception_and_never_raises(self):
        g = build_guild()

        async def boom():
            raise RuntimeError("gateway exploded")
        g.active_threads = boom                 # blow up mid-collect
        real = ops_audit.collect

        async def bad(*a, **k):
            raise RuntimeError("gateway exploded")
        ops_audit.collect = bad
        try:
            m = FakeMessage("!ouja-audit", g, admin=True)
            run(ops_audit.handle_message(m))    # must NOT raise
        finally:
            ops_audit.collect = real
        self.assertIn("RuntimeError: gateway exploded", m.replies[0].content)

    def test_dm_is_rejected(self):
        m = FakeMessage("!ouja-audit", None, admin=True)
        run(ops_audit.handle_message(m))
        self.assertIn("داخل السيرفر", m.replies[0].content)


if __name__ == "__main__":
    unittest.main()
