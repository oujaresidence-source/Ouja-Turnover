# -*- coding: utf-8 -*-
"""The Discord layer of `!ouja-tidy` (ops_tidy.py), driven against fakes — no network.

The fake guild records EVERY write (edit / set_permissions / create_* / delete) in one
shared log, together with what the command channel received, so order and "zero writes"
are asserted on the real code paths.

Run: python3 -m unittest tests.test_ops_tidy_discord -v
"""
import asyncio
import copy
import json
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import discord  # noqa: E402
import ops_audit  # noqa: E402
import ops_tidy  # noqa: E402
import ops_tidy_rules as R  # noqa: E402

NOW = datetime.now(timezone.utc)
RECENT = NOW - timedelta(days=2)
OLD = NOW - timedelta(days=200)
WRITE_OPS = ("edit", "set_permissions", "create_category", "create_text_channel", "delete")
FIX = os.path.join(ROOT, "tests", "fixtures", "tidy", "audit_2026-10-02.json")


def _run(coro):
    return asyncio.run(coro)


def _ov(allow=(), deny=()):
    kw = {n: True for n in allow if n in discord.Permissions.VALID_FLAGS}
    kw.update({n: False for n in deny if n in discord.Permissions.VALID_FLAGS})
    return discord.PermissionOverwrite(**kw)


def _copy_ov(ov):
    a, d = ov.pair()
    return discord.PermissionOverwrite.from_pair(a, d)


def _pairs(ows):
    """Comparable form of an overwrites dict: {target_id: (allow, deny)} minus empty rows."""
    out = {}
    for t, ov in (ows or {}).items():
        a, d = ov.pair()
        if a.value or d.value:
            out[str(t.id)] = (a.value, d.value)
    return out


class _Resp:
    def __init__(self, status, reason):
        self.status, self.reason = status, reason


def _forbidden():
    return discord.Forbidden(_Resp(403, "Forbidden"), "Missing Access")


# ----------------------------------------------------------------- the fakes
class FakeRole:
    def __init__(self, rid, name, admin=False):
        self.id, self.name = rid, name
        self.mentionable = False           # roles expose .mentionable; members don't
        self.managed = False
        self.permissions = discord.Permissions(administrator=admin)
        self.members = []

    def is_default(self):
        return self.name == "@everyone"


class FakeMember:
    def __init__(self, mid, name, roles=(), admin=False, bot=False):
        self.id, self.name, self.display_name, self.bot = mid, name, name, bot
        self.roles = list(roles)
        self.guild_permissions = discord.Permissions(administrator=admin)
        self.mention = "<@%s>" % mid

    def __str__(self):
        return self.name


class _HistMsg:
    def __init__(self, created_at):
        self.created_at = created_at
        self.author = "someone#0001"


class FakeChannel:
    """A text channel OR a category (is_cat). Writes go to guild.log."""

    def __init__(self, guild, cid, name, is_cat=False, category=None, position=0,
                 overwrites=None, last=None, accessible=True, topic=""):
        self.guild, self.id, self.name, self.is_cat = guild, cid, name, is_cat
        self.type = types.SimpleNamespace(name="category" if is_cat else "text")
        self.category = category
        self.position = position
        self._ow = dict(overwrites or {})
        self.last, self.accessible, self.topic = last, accessible, topic
        self.created_at = OLD
        self.raise_on = None               # exception raised by every write to this object

    # -- read side
    @property
    def category_id(self):
        return self.category.id if self.category is not None else None

    @property
    def overwrites(self):
        return dict(self._ow)

    @property
    def channels(self):
        return [c for c in self.guild.channels if not c.is_cat and c.category is self]

    @property
    def text_channels(self):
        return self.channels

    @property
    def permissions_synced(self):
        return self.category is not None and _pairs(self.category._ow) == _pairs(self._ow)

    def _key(self, target):
        return next((k for k in self._ow if k.id == target.id), target)

    def overwrites_for(self, target):
        ov = self._ow.get(self._key(target))
        return _copy_ov(ov) if ov is not None else discord.PermissionOverwrite()

    def permissions_for(self, m):
        if m.guild_permissions.administrator or any(r.permissions.administrator for r in m.roles):
            return types.SimpleNamespace(view_channel=True)
        view = True
        ev = self._ow.get(self._key(self.guild.default_role))
        if ev is not None and ev.view_channel is not None:
            view = ev.view_channel
        flags = [self._ow[self._key(r)].view_channel for r in m.roles if self._key(r) in self._ow]
        if False in flags:
            view = False
        if True in flags:
            view = True
        mo = self._ow.get(self._key(m))
        if mo is not None and mo.view_channel is not None:
            view = mo.view_channel
        return types.SimpleNamespace(view_channel=view)

    def history(self, limit=None, oldest_first=False):
        chan = self

        class _It:
            def __aiter__(self):
                if not chan.accessible:
                    raise _forbidden()
                return self._gen()

            async def _gen(self):
                if chan.last is not None:
                    yield _HistMsg(chan.last)

        return _It()

    # -- write side (all recorded)
    async def edit(self, **kw):
        self.guild.log.append(("edit", self.id, dict(kw)))
        if self.raise_on is not None:
            raise self.raise_on
        if "name" in kw:
            self.name = kw["name"]
        if "category" in kw:
            self.category = kw["category"]
            if "position" not in kw:
                self.position = 1000 + len(self.category.channels if self.category else [])
        if "position" in kw:
            self.position = kw["position"]
        if kw.get("sync_permissions") and self.category is not None:
            self._ow = {t: _copy_ov(o) for t, o in self.category._ow.items()}
        if "overwrites" in kw:
            self._ow = {t: _copy_ov(o) for t, o in kw["overwrites"].items()}
        return self

    async def set_permissions(self, target, overwrite=None, **kw):
        self.guild.log.append(("set_permissions", self.id, target.id))
        if self.raise_on is not None:
            raise self.raise_on
        key = self._key(target)
        if overwrite is None or overwrite.is_empty():
            self._ow.pop(key, None)
        else:
            self._ow[key] = _copy_ov(overwrite)

    async def delete(self, **kw):
        self.guild.log.append(("delete", self.id))


class FakeGuild:
    def __init__(self, gid=1):
        self.id, self.name = gid, "Ouja"
        self.log = []
        self._chs = {}
        self._next = 50000
        self.default_role = FakeRole(gid, "@everyone")
        self.roles = [self.default_role]
        self.me = FakeMember(999, "Ouja Cleaning Bot", bot=True)
        self.members = [self.me]
        self.chunked = True
        self.owner_id = 1000
        self.member_count = 0
        self.raise_on_create = None

    # -- read side
    @property
    def channels(self):
        return list(self._chs.values())

    @property
    def categories(self):
        return sorted((c for c in self._chs.values() if c.is_cat), key=lambda c: c.position)

    @property
    def text_channels(self):
        return [c for c in self._chs.values() if not c.is_cat]

    def get_channel(self, cid):
        return self._chs.get(int(cid))

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == int(rid)), None)

    def get_member(self, mid):
        return next((m for m in self.members if m.id == int(mid)), None)

    async def active_threads(self):
        return []

    async def chunk(self):
        self.chunked = True

    # -- builders (NOT logged: they set the scene)
    def role(self, name, rid=None, admin=False):
        r = FakeRole(rid or self._nid(), name, admin)
        self.roles.append(r)
        return r

    def member(self, name, roles=(), admin=False, mid=None):
        m = FakeMember(mid or self._nid(), name, roles, admin)
        self.members.append(m)
        return m

    def add_category(self, name, cid=None, position=None, overwrites=None):
        c = FakeChannel(self, cid or self._nid(), name, is_cat=True,
                        position=len(self.categories) if position is None else position,
                        overwrites=overwrites)
        self._chs[c.id] = c
        return c

    def add_channel(self, name, category=None, cid=None, position=None, overwrites=None,
                    last=RECENT, accessible=True, topic="", synced=False):
        if synced and category is not None:
            overwrites = {t: _copy_ov(o) for t, o in category._ow.items()}
        c = FakeChannel(self, cid or self._nid(), name, category=category,
                        position=len(self._chs) if position is None else position,
                        overwrites=overwrites, last=last, accessible=accessible, topic=topic)
        self._chs[c.id] = c
        return c

    def _nid(self):
        self._next += 1
        return self._next

    # -- write side
    async def create_category(self, name, overwrites=None, position=None, reason=None):
        self.log.append(("create_category", name, {"position": position}))
        if self.raise_on_create is not None:
            raise self.raise_on_create
        return self.add_category(name, position=position,
                                 overwrites={t: _copy_ov(o) for t, o in (overwrites or {}).items()})

    async def create_text_channel(self, name, **kw):
        self.log.append(("create_text_channel", name, kw))
        return self.add_channel(name, category=kw.get("category"))


class SentMsg:
    def __init__(self, chan, content, files):
        self.chan, self.content, self.files = chan, content, files

    async def edit(self, content=None, **kw):
        self.content = content
        self.chan.log.append(("msg_edit", content))


class FakeCmdChannel:
    """Where the owner typed the command. Not part of guild.channels."""

    def __init__(self, log):
        self.id = 4242
        self.log = log
        self.sent = []

    async def send(self, content=None, file=None, files=None, **kw):
        fs = list(files or []) + ([file] if file is not None else [])
        m = SentMsg(self, content, fs)
        self.sent.append(m)
        self.log.append(("send", content, [f.filename for f in fs]))
        return m


class FakeAttachment:
    def __init__(self, filename, data):
        self.filename, self._data = filename, data

    async def read(self):
        return self._data


class FakeCommand:
    def __init__(self, guild, author, content, chan, attachments=()):
        self.guild, self.author, self.content, self.channel = guild, author, content, chan
        self.attachments = list(attachments)

    async def reply(self, content=None, **kw):
        kw.pop("mention_author", None)
        return await self.channel.send(content, **kw)


class FakeBot:
    def __init__(self, members_intent=True):
        self.intents = types.SimpleNamespace(members=members_intent)
        self.replies = []
        self.listeners = []
        self.reply_from = None

    def add_listener(self, fn, name):
        self.listeners.append((fn, name))

    async def wait_for(self, event, check=None, timeout=None):
        author, chan = self.reply_from
        while self.replies:
            m = types.SimpleNamespace(author=author, channel=chan, content=self.replies.pop(0))
            if check is None or check(m):
                return m
        raise asyncio.TimeoutError()


class FakeHost:
    def __init__(self):
        self.store = {}
        self.DIRECTPAY_PING_ROLE_ID = 555

    def _save_json(self, name, obj):
        self.store[name] = json.loads(json.dumps(obj, ensure_ascii=False))
        return True

    def _load_json(self, name, default):
        return copy.deepcopy(self.store.get(name, default))

    def _dp_close_ids(self):
        return [777]


# ------------------------------------------------------------- the harness
class _Harness(unittest.TestCase):
    def setUp(self):
        self._sleep = ops_audit.SLEEP_SECONDS
        ops_audit.SLEEP_SECONDS = 0
        self._env = {k: os.environ.get(k) for k in
                     ("TIDY_PAUSE", "TIDY_AUTO_ARCHIVE", "TIDY_ARCHIVE_ROLE", "OWNER_DISCORD_ID")}
        os.environ["TIDY_PAUSE"] = "0"
        os.environ.pop("TIDY_AUTO_ARCHIVE", None)
        os.environ.pop("TIDY_ARCHIVE_ROLE", None)
        os.environ.pop("OWNER_DISCORD_ID", None)
        self._wait = ops_tidy.CACHE_WAIT
        ops_tidy.CACHE_WAIT = 0.05
        self.host = FakeHost()
        self.bot = FakeBot()
        ops_tidy._MEM["plan"] = None
        ops_tidy._BUSY.update(op=None, step="", started=None)
        ops_tidy.setup(self.bot, self.host)

    def tearDown(self):
        ops_audit.SLEEP_SECONDS = self._sleep
        ops_tidy.CACHE_WAIT = self._wait
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # one owner (admin) + the command channel
    def wire(self, g):
        self.g = g
        self.owner = FakeMember(1000, "فيصل", admin=True)
        self.chan = FakeCmdChannel(g.log)
        self.bot.reply_from = (self.owner, self.chan)

    def cmd(self, text, attachments=()):
        m = FakeCommand(self.g, self.owner, text, self.chan, attachments)
        _run(ops_tidy.handle_message(m, self.bot))
        return m

    def writes(self, since=0):
        return [e for e in self.g.log[since:] if e[0] in WRITE_OPS]

    def last_text(self):
        return self.chan.sent[-1].content

    def run_with(self, *words):
        self.bot.replies = list(words)
        return self.cmd("!ouja-tidy run")


def small_guild():
    """A scene with every kind of row: panel, closed ticket, overflow leak, directpay leak,
    price channel, stale, dead category, untouched category, announcement."""
    g = FakeGuild()
    mg, op = g.role("Managment", 10), g.role("Operation", 11)
    acc, bo = g.role("Accounting", 12), g.role("Back Office", 13)
    g.role("dp-ping", 555)
    g.member("عامل", mid=2001)
    g.member("مدير", roles=[mg], mid=2002)
    g.member("أسيل", admin=True, mid=2003)
    g.member("مقفل", mid=777)
    deny_all = {g.default_role: _ov(deny=["view_channel"])}
    rr = g.add_category("RR", position=1, overwrites=dict(deny_all) | {
        acc: _ov(["view_channel"]), bo: _ov(["view_channel"]),
        mg: _ov(["view_channel"]), op: _ov(["view_channel"])})
    rr2 = g.add_category("RR ٢", position=2)
    dp = g.add_category(R.DIRECTPAY_CATEGORY, position=3, overwrites={op: _ov(["send_messages"])})
    ops = g.add_category("Operations", position=4,
                         overwrites=dict(deny_all) | {op: _ov(["view_channel"])})
    dump = g.add_category("DUMP", position=5)
    mgmt = g.add_category("Managment", position=6, overwrites=dict(deny_all) | {mg: _ov(["view_channel"])})
    c = {}
    c["panel"] = g.add_channel("فتح-تذكرة-rr", rr, synced=True)
    c["rr_closed"] = g.add_channel("مغلقة-rr-034-x", rr, synced=True)
    c["rr_live"] = g.add_channel("rr-050-live", rr, synced=True)
    c["rr2_live"] = g.add_channel("rr-063-live", rr2)
    c["rr2_closed"] = g.add_channel("مغلقة-rr-040", rr2)
    c["dp_live"] = g.add_channel("تحصيل-037-f2", dp, topic="ouja-dp:111 seq:37")
    c["dp_closed"] = g.add_channel("مغلقة-تحصيل-006", dp, topic="ouja-dp:222 seq:6",
                                   overwrites={g.default_role: _ov(deny=["send_messages"])})
    c["dp_summary"] = g.add_channel("تحصيل-الملخص", dp)
    c["pricing"] = g.add_channel("pricing-log", ops, overwrites=dict(deny_all) | {
        g.me: _ov(["view_channel"]), op: _ov(deny=["view_channel"])})
    c["esc"] = g.add_channel("escalations", ops, synced=True)
    c["stale"] = g.add_channel("old-chat", ops, last=OLD, synced=True)
    c["dump"] = g.add_channel("dump-1", dump)
    c["mgmt"] = g.add_channel("معلومات", mgmt, last=OLD, synced=True)
    c["news"] = g.add_channel("news", None)
    g.c = c
    return g


# =================================================================== tests
class TestPlanIsReadOnly(_Harness):
    def _fixture_guild(self):
        with open(FIX, encoding="utf-8") as f:
            inv = json.load(f)
        g = FakeGuild(gid=int(inv["guild"]["id"]))
        roles = {"@everyone": g.default_role}
        for r in inv["roles"]:
            if r["name"] != "@everyone":
                roles[r["name"]] = g.role(r["name"], int(r["id"]), bool(r["is_admin"]))
        people = {}

        def ows(rows):
            out = {}
            for o in rows or []:
                if o["kind"] == "role":
                    t = roles.get(o["target"])
                else:
                    tid = int(o["target_id"])
                    t = people.get(tid) or g.member("m%d" % tid, mid=tid)
                    people[tid] = t
                if t is not None:
                    out[t] = _ov(o["allow"], o["deny"])
            return out

        for c in inv["categories"]:
            g.add_category(c["name"], cid=int(c["id"]), position=c["position"],
                           overwrites=ows(c["overwrites"]))
        keep_cats = {"RR ٢", R.DIRECTPAY_CATEGORY, "Operations", "DUMP", "Managment"}
        rr_taken = 0
        for ch in inv["channels"]:
            take = ch["category"] in keep_cats or R.is_panel(ch["name"])
            if not take and ch["category"] == "RR" and rr_taken < 15:
                take, rr_taken = True, rr_taken + 1
            if not take:
                continue
            last = ch.get("last_message_at")
            g.add_channel(ch["name"], g.get_channel(int(ch["category_id"])) if ch["category_id"] else None,
                          cid=int(ch["id"]), position=ch["position"], overwrites=ows(ch["overwrites"]),
                          last=datetime.fromisoformat(last) if last else None,
                          accessible=bool(ch["accessible"]), topic=ch.get("topic") or "")
        g.member("موظف بلا رول", mid=31337)
        g.member("مدير", roles=[roles["Managment"]], mid=31338)
        return g

    def test_plan_writes_nothing_and_replies_once_with_two_files(self):
        self.wire(self._fixture_guild())
        before = len(self.g.log)
        self.cmd("!ouja-tidy plan")
        self.assertEqual(self.writes(before), [])
        self.assertEqual(len(self.chan.sent), 1)
        names = [f.filename for f in self.chan.sent[0].files]
        self.assertEqual(len(names), 2)
        self.assertTrue(names[0].startswith("tidy_plan_") and names[0].endswith(".json"), names)
        self.assertTrue(names[1].startswith("tidy_people_") and names[1].endswith(".csv"), names)
        plan = self.host.store["tidy_plan.json"]
        text = self.chan.sent[0].content
        for k in ("archive", "restrict", "keep"):
            self.assertIn("**%d**" % plan["counts"][k], text)
        self.assertGreater(plan["counts"]["archive"], 0)
        self.assertLessEqual(len(text), 2000)

    def test_people_csv_has_bom_header_and_everyone(self):
        self.wire(self._fixture_guild())
        self.cmd("!ouja-tidy plan")
        f = self.chan.sent[0].files[1]
        raw = f.fp.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        body = raw.decode("utf-8-sig").splitlines()
        self.assertEqual(body[0].split(","), ["الاسم", "يفقد قنوات شغالة", "عددها", "يفقد من الأرشيف", "يبقى يشوف"])
        humans = [m for m in self.g.members if not m.bot]
        self.assertEqual(len(body) - 1, len(humans))
        self.assertIn("🔴", self.chan.sent[0].content)   # the roleless worker loses live leaks

    def test_without_members_intent_the_report_is_skipped_and_explained(self):
        self.bot.intents.members = False
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        self.assertEqual(self.writes(), [])
        text = self.last_text()
        self.assertIn("Server Members Intent", text)
        self.assertIn("MEMBERS_INTENT=1", text)
        self.assertIsNone(self.host.store["tidy_plan.json"].get("people"))

    def test_strangers_are_ignored_silently(self):
        self.wire(small_guild())
        m = FakeCommand(self.g, FakeMember(5, "غريب"), "!ouja-tidy plan", self.chan)
        _run(ops_tidy.handle_message(m, self.bot))
        self.assertEqual(self.chan.sent, [])


class TestRunOrderAndSnapshot(_Harness):
    def _phase(self, e):
        if e[0] == "set_permissions":
            return "mgmt"
        if e[0] == "create_category":
            return "create"
        kw = e[2]
        if "category" in kw:
            return "move"
        if "overwrites" in kw and self.g.get_channel(e[1]).is_cat:
            return "fix"
        if kw == {"sync_permissions": True}:
            return "sync"
        return "other"

    def test_snapshot_first_then_the_fixed_order(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        mark = len(self.g.log)
        self.run_with("نفّذ")
        log = self.g.log[mark:]
        snap_i = next(i for i, e in enumerate(log)
                      if e[0] == "send" and any(n.startswith("tidy_snapshot_") for n in e[2]))
        first_write = next(i for i, e in enumerate(log) if e[0] in WRITE_OPS)
        self.assertLess(snap_i, first_write)
        phases = [self._phase(e) for e in log if e[0] in WRITE_OPS]
        self.assertNotIn("other", phases)
        order = ["fix", "sync", "mgmt", "create", "move"]
        self.assertEqual(sorted(set(phases), key=order.index), order)
        self.assertEqual(phases, sorted(phases, key=order.index))
        for e in log:
            if e[0] == "edit" and "category" in e[2]:
                self.assertIs(e[2].get("sync_permissions"), True)
        # the snapshot is also on disk
        self.assertTrue(any(k.startswith("tidy_snapshot_") for k in self.host.store))

    def test_effects(self):
        self.wire(small_guild())
        c = self.g.c
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        worker = self.g.get_member(2001)
        manager = self.g.get_member(2002)
        closer = self.g.get_member(777)
        for k in ("rr_closed", "rr2_closed", "dp_closed", "stale", "dump"):
            self.assertTrue(R.is_archive_category(c[k].category.name), k)
            self.assertFalse(c[k].permissions_for(worker).view_channel, k)
            self.assertTrue(c[k].permissions_for(manager).view_channel, k)
        self.assertEqual(c["rr_closed"].name, "مغلقة-rr-034-x")            # never renamed
        self.assertFalse(c["rr2_live"].permissions_for(worker).view_channel)   # RR ٢ leak closed
        self.assertFalse(c["dp_live"].permissions_for(worker).view_channel)    # directpay leak closed
        self.assertTrue(c["dp_live"].permissions_for(closer).view_channel)
        self.assertFalse(c["pricing"].permissions_for(worker).view_channel)
        self.assertTrue(c["pricing"].permissions_for(manager).view_channel)
        self.assertTrue(c["pricing"].permissions_for(self.g.me).view_channel)  # the bot keeps posting
        self.assertTrue(c["news"].permissions_for(worker).view_channel)
        self.assertEqual(self.host.store["tidy_state.json"].get("auto_archive"), True)
        self.assertIn("رجّع", self.last_text())

    def test_plain_word_without_shadda_is_accepted(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        mark = len(self.g.log)
        self.run_with("نفذ")
        self.assertTrue(self.writes(mark))

    def test_wrong_word_changes_nothing(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        mark = len(self.g.log)
        self.run_with("تمام")
        self.assertEqual(self.writes(mark), [])
        self.assertNotIn("tidy_state.json", self.host.store)

    def test_timeout_changes_nothing(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        mark = len(self.g.log)
        self.run_with()
        self.assertEqual(self.writes(mark), [])

    def test_no_report_needs_the_longer_word(self):
        self.bot.intents.members = False
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        mark = len(self.g.log)
        self.run_with("نفذ")
        self.assertEqual(self.writes(mark), [])
        self.run_with("نفّذ بدون تقرير")
        self.assertTrue(self.writes(mark))

    def test_refuses_without_a_plan_or_with_an_old_one(self):
        self.wire(small_guild())
        self.run_with("نفّذ")
        self.assertEqual(self.writes(), [])
        self.assertIn("!ouja-tidy plan", self.last_text())
        self.cmd("!ouja-tidy plan")
        plan = self.host.store["tidy_plan.json"]
        plan["generated_at"] = (NOW - timedelta(hours=25)).isoformat()
        self.host.store["tidy_plan.json"] = plan
        ops_tidy._MEM["plan"] = None
        mark = len(self.g.log)
        self.run_with("نفّذ")
        self.assertEqual(self.writes(mark), [])
        self.assertIn("!ouja-tidy plan", self.last_text())

    def test_second_plan_after_run_moves_nothing(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        self.cmd("!ouja-tidy plan")
        self.assertEqual(self.host.store["tidy_plan.json"]["counts"]["archive"], 0)


class TestRunSkips(_Harness):
    def test_reopened_and_forbidden_rows_are_skipped_not_fatal(self):
        self.wire(small_guild())
        c = self.g.c
        self.cmd("!ouja-tidy plan")
        rr2 = c["rr2_closed"].category
        c["rr2_closed"].name = "rr-040"                 # reopened after the plan
        c["dump"].raise_on = _forbidden()
        self.run_with("نفّذ")
        self.assertIs(c["rr2_closed"].category, rr2)
        self.assertEqual(c["dump"].category.name, "DUMP")
        self.assertTrue(R.is_archive_category(c["stale"].category.name))   # the run went on
        text = self.last_text()
        self.assertIn("تجاوزت", text)
        self.assertIn("rr-040", text)
        self.assertIn("Administrator", text)
        self.assertEqual(self.host.store["tidy_state.json"]["last_run"]["forbidden"], 1)

    def test_channels_never_sync_to_a_category_whose_lock_failed(self):
        self.wire(small_guild())
        c = self.g.c
        self.cmd("!ouja-tidy plan")
        dp = c["dp_live"].category
        dp.raise_on = _forbidden()
        self.run_with("نفّذ")
        synced = [e for e in self.writes() if e[0] == "edit" and e[2] == {"sync_permissions": True}]
        self.assertNotIn(c["dp_live"].id, [e[1] for e in synced])
        self.assertNotIn(c["dp_summary"].id, [e[1] for e in synced])
        self.assertIn(c["rr2_live"].id, [e[1] for e in synced])        # the other leak still closed
        self.assertIn("قفل القسم ما نجح", self.last_text())

    def test_a_lock_the_cache_never_confirms_is_treated_as_failed(self):
        self.wire(small_guild())
        c = self.g.c
        self.cmd("!ouja-tidy plan")
        real = ops_tidy._wait_cached

        async def lagging(guild, cid, want=None):
            return False if want is not None else await real(guild, cid, want)
        ops_tidy._wait_cached = lagging
        try:
            self.run_with("نفّذ")
        finally:
            ops_tidy._wait_cached = real
        synced = [e[1] for e in self.writes() if e[0] == "edit" and e[2] == {"sync_permissions": True}]
        self.assertNotIn(c["dp_live"].id, synced)
        self.assertNotIn(c["rr2_live"].id, synced)

    def test_moves_carry_the_archive_overwrites_explicitly(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        moves = [e for e in self.writes() if e[0] == "edit" and "category" in e[2]]
        self.assertTrue(moves)
        for e in moves:
            self.assertEqual(_pairs(e[2]["overwrites"]), _pairs(e[2]["category"]._ow))

    def test_moved_channel_since_plan_is_skipped(self):
        self.wire(small_guild())
        c = self.g.c
        self.cmd("!ouja-tidy plan")
        c["stale"].category = self.g.c["mgmt"].category
        self.run_with("نفّذ")
        self.assertEqual(c["stale"].category.name, "Managment")


class TestUndo(_Harness):
    def _state(self):
        out = {}
        for ch in self.g.channels:
            if ch.is_cat and R.is_archive_category(ch.name):
                continue
            out[ch.id] = (ch.category_id, ch.position, _pairs(ch._ow))
        return out

    def test_run_then_undo_restores_everything(self):
        self.wire(small_guild())
        before = self._state()
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        self.assertNotEqual(self._state(), before)
        self.bot.replies = ["رجع"]                        # no shadda — still accepted
        self.cmd("!ouja-tidy undo")
        self.assertEqual(self._state(), before)
        self.assertFalse(self.host.store["tidy_state.json"].get("auto_archive"))
        # archive categories stay (nothing is deleted)
        self.assertTrue(any(R.is_archive_category(c.name) for c in self.g.categories))
        self.assertFalse([e for e in self.g.log if e[0] == "delete"])

    def test_undo_from_an_attached_snapshot_when_the_disk_was_wiped(self):
        self.wire(small_guild())
        before = self._state()
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        snap = next(f for m in self.chan.sent for f in m.files if f.filename.startswith("tidy_snapshot_"))
        snap.fp.seek(0)
        data = snap.fp.read()
        self.host.store.clear()
        self.bot.replies = ["رجّع"]
        self.cmd("!ouja-tidy undo", attachments=[FakeAttachment(snap.filename, data)])
        self.assertEqual(self._state(), before)

    def test_undo_writes_a_position_only_when_it_changed(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        mark = len(self.g.log)
        self.bot.replies = ["رجّع"]
        self.cmd("!ouja-tidy undo")
        for e in self.writes(mark):
            if e[0] == "edit" and "position" in e[2]:
                self.assertIn("category", e[2])                 # only channels that moved
        unmoved = {self.g.c[k].id for k in ("rr2_live", "dp_live", "dp_summary", "pricing")}
        for e in self.writes(mark):
            if e[0] == "edit" and e[1] in unmoved:
                self.assertNotIn("position", e[2])

    def test_undo_wrong_word_changes_nothing(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        mark = len(self.g.log)
        self.bot.replies = ["لا"]
        self.cmd("!ouja-tidy undo")
        self.assertEqual(self.writes(mark), [])

    def test_status_reports_the_last_run(self):
        self.wire(small_guild())
        self.cmd("!ouja-tidy status")
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        self.cmd("!ouja-tidy status")
        self.assertIn("آخر تشغيل", self.last_text())


class TestPanelsUntouched(_Harness):
    PANELS = [("فتح-تذكرة-rr", "RR"), ("افتحت-تكت-طلب-اموال", "Finance"),
              ("افتح-تكت-دره-جديد", "DUMP"), ("فتح-تذكرة-مشتريات", "مشتريات"),
              ("تكت-اشتراك-النت", "اشتراكات النت"), ("افتح-مشروع-جديد", "Property Devolompment"),
              ("فتح-تذكرة-صيانة", "صيانه"), ("rr-tickets", "RR ٢"),
              # renamed «مغلقة…» panels: the rules alone would archive the second one
              ("مغلقة-فتح-تذكرة-قديم", "DUMP"), ("مغلقة-rr-tickets", R.DIRECTPAY_CATEGORY)]

    def test_panels_never_written_by_run_undo_or_auto_archive(self):
        g = FakeGuild()
        g.role("Managment", 10)
        g.member("عامل", mid=2001)
        cats = {}
        for i, (_n, cat) in enumerate(self.PANELS):
            if cat not in cats:
                cats[cat] = g.add_category(cat, position=i)
        panels = []
        for i, (n, cat) in enumerate(self.PANELS):
            panels.append(g.add_channel(n, cats[cat], last=OLD if i % 2 else RECENT, accessible=i % 3 != 0))
        g.add_channel("مغلقة-rr-100", cats["RR"])
        g.add_channel("rr-063-live", cats["RR ٢"])
        self.wire(g)
        ids = {p.id for p in panels}
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        self.bot.replies = ["رجّع"]
        self.cmd("!ouja-tidy undo")
        os.environ["TIDY_AUTO_ARCHIVE"] = "1"
        for p in panels:
            self.assertFalse(_run(ops_tidy.archive_closed_channel(p)))
        touched = [e for e in self.writes() if e[0] in ("edit", "set_permissions") and e[1] in ids]
        self.assertEqual(touched, [])
        renamed = next(p for p in panels if p.name == "مغلقة-rr-tickets")
        self.assertEqual(R.classify_channel({"name": renamed.name, "category": "x"}, NOW)[0],
                         "archive")                       # the rules alone WOULD move it …
        self.assertEqual(renamed.category.name, R.DIRECTPAY_CATEGORY)   # … ops_tidy refuses
        self.assertTrue(any(e[0] == "edit" and "category" in e[2] for e in self.writes()))  # the run did run


class TestAutoArchive(_Harness):
    def _guild_with_archive(self, n_in_first):
        g = FakeGuild()
        g.role("Managment", 10)
        rr = g.add_category("RR", position=0)
        a1 = g.add_category(R.archive_name(1), position=1)
        for i in range(n_in_first):
            g.add_channel("old-%d" % i, a1)
        self.wire(g)
        return g, rr, a1

    def test_noop_before_the_first_successful_run(self):
        g, rr, _a1 = self._guild_with_archive(0)
        ch = g.add_channel("مغلقة-rr-200", rr)
        self.assertFalse(_run(ops_tidy.archive_closed_channel(ch)))
        self.assertEqual(self.writes(), [])

    def test_env_zero_forces_off(self):
        g, rr, _a1 = self._guild_with_archive(0)
        self.host.store["tidy_state.json"] = {"auto_archive": True}
        os.environ["TIDY_AUTO_ARCHIVE"] = "0"
        ch = g.add_channel("مغلقة-rr-200", rr)
        self.assertFalse(_run(ops_tidy.archive_closed_channel(ch)))
        self.assertEqual(self.writes(), [])

    def test_env_one_forces_on(self):
        g, rr, a1 = self._guild_with_archive(0)
        os.environ["TIDY_AUTO_ARCHIVE"] = "1"
        ch = g.add_channel("مغلقة-rr-200", rr)
        self.assertTrue(_run(ops_tidy.archive_closed_channel(ch)))
        self.assertIs(ch.category, a1)

    def test_fills_one_to_fifty_then_creates_two(self):
        g, rr, a1 = self._guild_with_archive(49)
        self.host.store["tidy_state.json"] = {"auto_archive": True}
        ch1 = g.add_channel("مغلقة-rr-201", rr)
        ch2 = g.add_channel("مغلقة-rr-202", rr)
        self.assertTrue(_run(ops_tidy.archive_closed_channel(ch1)))
        self.assertIs(ch1.category, a1)
        self.assertEqual(len(a1.channels), 50)
        self.assertTrue(_run(ops_tidy.archive_closed_channel(ch2)))
        self.assertEqual(ch2.category.name, R.archive_name(2))
        self.assertEqual(ch2.category.name, "📦 أرشيف ٢")
        moves = [e for e in self.writes() if e[0] == "edit"]
        self.assertTrue(all(e[2].get("sync_permissions") is True for e in moves))
        self.assertIs(ch2.category._ow[g.default_role].view_channel, False)

    def test_noop_for_panels_and_channels_already_archived(self):
        g, rr, a1 = self._guild_with_archive(1)
        os.environ["TIDY_AUTO_ARCHIVE"] = "1"
        self.assertFalse(_run(ops_tidy.archive_closed_channel(a1.channels[0])))
        self.assertFalse(_run(ops_tidy.archive_closed_channel(g.add_channel("مغلقة-فتح-تذكرة-rr", rr))))
        self.assertEqual(self.writes(), [])

    def test_errors_return_false_and_never_raise(self):
        g, rr, _a1 = self._guild_with_archive(50)
        os.environ["TIDY_AUTO_ARCHIVE"] = "1"
        g.raise_on_create = RuntimeError("discord down")
        self.assertFalse(_run(ops_tidy.archive_closed_channel(g.add_channel("مغلقة-rr-1", rr))))
        g.raise_on_create = None
        ch = g.add_channel("مغلقة-rr-2", rr)
        ch.raise_on = _forbidden()
        self.assertFalse(_run(ops_tidy.archive_closed_channel(ch)))
        self.assertFalse(_run(ops_tidy.archive_closed_channel(object())))

    def test_turns_on_after_run(self):
        g = small_guild()
        self.wire(g)
        rr = g.c["rr_live"].category
        late = g.add_channel("rr-300", rr)                # live while the plan runs
        self.assertFalse(_run(ops_tidy.archive_closed_channel(late)))
        self.cmd("!ouja-tidy plan")
        self.run_with("نفّذ")
        late.name = "مغلقة-rr-300"
        self.assertTrue(_run(ops_tidy.archive_closed_channel(late)))
        self.assertTrue(R.is_archive_category(late.category.name))


class TestOverwriteBuilders(_Harness):
    def _g(self):
        g = FakeGuild()
        self.mg, self.op = g.role("Managment", 10), g.role("Operation", 11)
        self.acc = g.role("Accounting", 12)
        self.ping = g.role("dp-ping", 555)
        g.member("مقفل", mid=777)
        return g

    def test_directpay_keeps_existing_and_locks(self):
        g = self._g()
        existing = {self.op: _ov(["send_messages"]), g.default_role: _ov(["send_messages"])}
        ow = ops_tidy.directpay_overwrites(g, existing=existing)
        by = {t.id: o for t, o in ow.items()}
        self.assertIs(by[self.op.id].send_messages, True)                   # kept
        self.assertIs(by[g.default_role.id].view_channel, False)
        self.assertIs(by[g.default_role.id].send_messages, True)            # merged, not replaced
        self.assertIs(by[self.acc.id].view_channel, True)
        self.assertIs(by[self.mg.id].view_channel, True)
        self.assertIs(by[555].view_channel, True)
        self.assertIs(by[777].view_channel, True)
        self.assertIs(by[g.me.id].view_channel, True)
        self.assertIs(by[g.me.id].send_messages, True)
        # only a guild ADMINISTRATOR may put Manage Permissions in a channel overwrite — the bot
        # is not one after the run, so it must never ask for it (a 403 would kill every archive)
        self.assertIsNone(by[g.me.id].manage_permissions)
        self.assertIsNone(by[g.me.id].manage_channels)
        self.assertIsNone(existing[g.default_role].view_channel)            # input not mutated

    def test_directpay_closer_not_cached_still_listed(self):
        g = self._g()
        g.members = [g.me]
        ow = ops_tidy.directpay_overwrites(g)
        self.assertIn(777, {t.id for t in ow})

    def test_archive_overwrites(self):
        g = self._g()
        ow = {t.id: o for t, o in ops_tidy.archive_overwrites(g).items()}
        self.assertIs(ow[g.default_role.id].view_channel, False)
        m = ow[self.mg.id]
        self.assertIs(m.view_channel, True)
        self.assertIs(m.read_message_history, True)
        for flag in ("send_messages", "add_reactions", "create_public_threads",
                     "create_private_threads", "send_messages_in_threads"):
            self.assertIs(getattr(m, flag), False, flag)
        me = ow[g.me.id]
        for flag in ("view_channel", "send_messages", "read_message_history",
                     "embed_links", "attach_files"):
            self.assertIs(getattr(me, flag), True, flag)
        self.assertIsNone(me.manage_permissions)
        self.assertIsNone(me.manage_channels)
        self.assertNotIn(self.op.id, ow)

    def test_archive_role_from_env(self):
        g = self._g()
        os.environ["TIDY_ARCHIVE_ROLE"] = "Accounting"
        ow = {t.id: o for t, o in ops_tidy.archive_overwrites(g).items()}
        self.assertIn(self.acc.id, ow)
        self.assertNotIn(self.mg.id, ow)


class TestWordsAndWiring(unittest.TestCase):
    def test_diacritics_are_ignored(self):
        self.assertEqual(ops_tidy._norm_word("نفّذ"), ops_tidy._norm_word("نفذ"))
        self.assertEqual(ops_tidy._norm_word(" رجّع "), ops_tidy._norm_word("رجع"))
        self.assertNotEqual(ops_tidy._norm_word("نفذ"), ops_tidy._norm_word("نفّذ بدون تقرير"))

    def test_setup_registers_one_listener(self):
        b = FakeBot()
        ops_tidy.setup(b, FakeHost())
        self.assertEqual([n for _f, n in b.listeners], ["on_message"])


if __name__ == "__main__":
    unittest.main()
