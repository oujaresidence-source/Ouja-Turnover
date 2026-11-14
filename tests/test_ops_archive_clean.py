# -*- coding: utf-8 -*-
"""!ouja-clean-archive — save every archived room into the dashboard, THEN delete it.

Owner rule (2026-11-14): «أهم شي تأكد إن غير الصور كل شي مسجل في الداشبورد».
So the guarantees locked here are:
  1. only rooms inside «📦 أرشيف N» are touched — a live room is never even read
  2. every message, embed (bot card) and non-photo file is stored on the dashboard
     side BEFORE the room is deleted; photos are recorded as a line, not as bytes
  3. a room is never deleted if anything except a photo failed to save
  4. a room that got a new message after it was saved is kept
  5. a room with threads is kept (deleting the room would delete the threads)
  6. dry-run saves everything and deletes nothing
  7. emptied archive categories are deleted, but the first one is always kept
  8. the dashboard reader returns exactly what was saved, and refuses non-admins
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ops_archive_clean as C
from test_ops_archive import FakeAttachment, FakeAuthor, FakeMsg

NOW = datetime.now(timezone.utc)
RECENT = NOW - timedelta(days=3)          # closed last week — the 60-day rule must NOT apply


class Cat:
    def __init__(self, cid, name, guild):
        self.id, self.name, self.guild = cid, name, guild
        self.type = type("T", (), {"name": "category"})()
        self.deleted = False

    @property
    def channels(self):
        return [c for c in self.guild.channels if c.category is self and not c.deleted]

    async def delete(self, reason=None):
        self.deleted = True
        self.guild.categories.remove(self)


class Room:
    def __init__(self, cid, name, category, messages=(), ctype="text", threads=0, raises=None):
        self.id, self.name, self.category = cid, name, category
        self.type = type("T", (), {"name": ctype})()
        self._messages = list(messages)
        self.deleted = False
        self.threads = ["t"] * threads
        self.raises = raises
        self.history_calls = 0

    def history(self, limit=None, oldest_first=False):
        chan = self

        class _It:
            def __aiter__(self):
                chan.history_calls += 1
                if chan.raises is not None:
                    raise chan.raises
                msgs = list(chan._messages)
                if not oldest_first:
                    msgs.reverse()
                if limit:
                    msgs = msgs[:limit]
                return self._gen(msgs)

            async def _gen(self, msgs):
                for m in msgs:
                    yield m

        return _It()

    def archived_threads(self, limit=None):
        async def _none():
            if False:
                yield None
        return _none()

    async def delete(self, reason=None):
        self.deleted = True


class Guild:
    def __init__(self):
        self.id, self.name = 1, "Ouja"
        self.channels, self.categories = [], []

    def cat(self, cid, name):
        c = Cat(cid, name, self)
        self.categories.append(c)
        return c

    def room(self, *a, **k):
        r = Room(*a, **k)
        self.channels.append(r)
        return r


class Embed:
    def __init__(self, d):
        self.d = d

    def to_dict(self):
        return dict(self.d)


def run(coro):
    return asyncio.run(coro)


SAM = FakeAuthor(10, "Sam")
BOT = FakeAuthor(11, "OujaBot", bot=True)


def msgs_with_everything():
    card = FakeMsg(1, RECENT, BOT, "")
    card.embeds = [Embed({"title": "تذكرة صيانة 070", "description": "المكيف ما يبرد",
                          "fields": [{"name": "الشقة", "value": "B14"}]})]
    photo = FakeAttachment("before.jpg", b"\xff\xd8jpegbytes", "image/jpeg")
    pdf = FakeAttachment("invoice.pdf", b"%PDF-1.4 invoice", "application/pdf")
    return [card,
            FakeMsg(2, RECENT, SAM, "تم الإصلاح", attachments=[photo, pdf]),
            FakeMsg(3, RECENT, SAM, "سكّرت التذكرة")]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["STATE_DIR"] = self.tmp
        self.g = Guild()
        self.a1 = self.g.cat(500, "📦 أرشيف ١")
        self.a2 = self.g.cat(501, "📦 أرشيف ٢")
        self.live = self.g.cat(600, "🔧 الصيانة")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def clean(self, dryrun=False):
        return run(C.run_clean(self.g, dryrun=dryrun, pause=0))


class TestScope(Base):
    def test_only_archive_rooms_are_touched(self):
        arch = self.g.room(1, "مغلقة-صيانة-070", self.a1, msgs_with_everything())
        live = self.g.room(2, "صيانة-071", self.live, msgs_with_everything())
        rep = self.clean()
        self.assertTrue(arch.deleted)
        self.assertFalse(live.deleted)
        self.assertEqual(live.history_calls, 0, "a live room must not even be read")
        self.assertEqual([d["name"] for d in rep["deleted"]], ["مغلقة-صيانة-070"])

    def test_sixty_day_rule_does_not_block_archive_rooms(self):
        r = self.g.room(1, "x", self.a1, [FakeMsg(1, NOW - timedelta(hours=2), SAM, "hi")])
        self.clean()
        self.assertTrue(r.deleted)


class TestSavedBeforeDelete(Base):
    def test_everything_but_photos_is_on_the_dashboard_side(self):
        self.g.room(1, "مغلقة-صيانة-070", self.a1, msgs_with_everything())
        self.clean()
        room = C.read_room("1")
        self.assertIsNotNone(room)
        self.assertEqual(room["message_count"], 3)
        texts = [m["content"] for m in room["messages"]]
        self.assertIn("تم الإصلاح", texts)
        self.assertIn("سكّرت التذكرة", texts)
        self.assertEqual(room["messages"][0]["embeds"][0]["title"], "تذكرة صيانة 070")
        atts = room["messages"][1]["attachments"]
        photo = [a for a in atts if a["filename"] == "before.jpg"][0]
        pdf = [a for a in atts if a["filename"] == "invoice.pdf"][0]
        self.assertTrue(photo.get("skipped_photo"))
        self.assertFalse(photo.get("failed"))
        self.assertEqual(C.read_file("1", pdf["stored_as"]), b"%PDF-1.4 invoice")
        self.assertIsNone(C.read_file("1", photo["stored_as"]), "photo bytes are not kept")
        idx = {e["id"]: e for e in C.list_rooms()}
        self.assertTrue(idx["1"]["deleted_at"])
        self.assertEqual(idx["1"]["photos_skipped"], 1)

    def test_failed_file_keeps_the_room(self):
        bad = FakeAttachment("contract.pdf", b"x", "application/pdf", fail_times=99)
        r = self.g.room(1, "r", self.a1, [FakeMsg(1, RECENT, SAM, "", attachments=[bad])])
        rep = self.clean()
        self.assertFalse(r.deleted)
        self.assertEqual(rep["kept"][0]["id"], "1")

    def test_failed_photo_never_blocks(self):
        bad = FakeAttachment("p.png", b"x", "image/png", fail_times=99)
        r = self.g.room(1, "r", self.a1, [FakeMsg(1, RECENT, SAM, "", attachments=[bad])])
        self.clean()
        self.assertTrue(r.deleted)
        self.assertEqual(bad.reads, 0, "photos are not even downloaded")

    def test_unreadable_room_is_kept(self):
        import discord

        class _Resp:
            status, reason = 403, "Forbidden"
        r = self.g.room(1, "r", self.a1, raises=discord.Forbidden(_Resp(), "no"))
        rep = self.clean()
        self.assertFalse(r.deleted)
        self.assertTrue(rep["kept"])

    def test_new_message_after_save_keeps_the_room(self):
        r = self.g.room(1, "r", self.a1, [FakeMsg(1, RECENT, SAM, "a")])
        orig = C._newest_id

        async def moved(ch):
            return "999"
        C._newest_id = moved
        try:
            self.clean()
        finally:
            C._newest_id = orig
        self.assertFalse(r.deleted)

    def test_room_with_threads_is_kept(self):
        r = self.g.room(1, "r", self.a1, [FakeMsg(1, RECENT, SAM, "a")], threads=1)
        self.clean()
        self.assertFalse(r.deleted)

    def test_voice_room_is_kept(self):
        r = self.g.room(1, "v", self.a1, [], ctype="voice")
        self.clean()
        self.assertFalse(r.deleted)


class TestDryRunAndCategories(Base):
    def test_dryrun_saves_but_deletes_nothing(self):
        r = self.g.room(1, "r", self.a1, msgs_with_everything())
        rep = self.clean(dryrun=True)
        self.assertFalse(r.deleted)
        self.assertEqual(len(rep["would_delete"]), 1)
        self.assertIsNotNone(C.read_room("1"))
        self.assertIn(self.a2, self.g.categories)

    def test_second_run_does_not_resave_unchanged_room(self):
        r = self.g.room(1, "r", self.a1, msgs_with_everything())
        self.clean(dryrun=True)
        calls = r.history_calls
        self.clean(dryrun=True)
        # one history() for the newest-id check only — no full re-read
        self.assertEqual(r.history_calls, calls + 1)

    def test_empty_archive_categories_go_but_first_stays(self):
        self.g.room(1, "a", self.a1, [FakeMsg(1, RECENT, SAM, "a")])
        self.g.room(2, "b", self.a2, [FakeMsg(2, RECENT, SAM, "b")])
        rep = self.clean()
        self.assertIn(self.a1, self.g.categories)
        self.assertNotIn(self.a2, self.g.categories)
        self.assertIn(self.live, self.g.categories)
        self.assertEqual(rep["categories_deleted"], ["📦 أرشيف ٢"])

    def test_category_with_a_kept_room_stays(self):
        self.g.room(1, "a", self.a2, [FakeMsg(1, RECENT, SAM, "a")], threads=1)
        self.clean()
        self.assertIn(self.a2, self.g.categories)


class TestStoreSafety(Base):
    def test_names_cannot_escape_the_store(self):
        s = C.LocalSink()
        f = s.folder(s.root_id(), "..")
        self.assertTrue(os.path.realpath(f).startswith(os.path.realpath(C._store_dir())))
        self.assertIsNone(C.read_file("1", "../../etc/passwd"))

    def test_preview_counts(self):
        self.g.room(1, "a", self.a1, [])
        self.g.room(2, "b", self.a2, [])
        self.g.room(3, "c", self.live, [])
        p = C.preview(self.g)
        self.assertEqual(p["rooms"], 2)
        self.assertEqual(p["categories"], 2)


class FakeHost:
    def __init__(self, role, authed=True):
        self.role, self.authed = role, authed

    def _dash_auth(self, request):
        return self.authed

    def _req_role(self, request):
        return self.role


class TestDashboardGate(Base):
    def test_only_admin_reads(self):
        self.assertTrue(C.may_read(FakeHost("admin"), None))
        self.assertFalse(C.may_read(FakeHost("ops"), None))
        self.assertFalse(C.may_read(FakeHost("admin", authed=False), None))

    def test_page_has_no_backslashes(self):
        self.assertNotIn(chr(92), C.PAGE_HTML)


if __name__ == "__main__":
    unittest.main()
