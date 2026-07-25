# -*- coding: utf-8 -*-
"""Synthetic-data tests for ops_archive (!ouja-archive / !ouja-purge).

No Discord and no Google Drive: a fake guild and a fake Drive sink are driven by the
REAL archive/purge code, then the bytes that actually landed in "Drive" are asserted.

The six guarantees the owner asked for, each locked by a test below:
  1. attachment BYTES are downloaded and stored — never the (expiring) CDN URL
  2. unreadable channels archive as {"unreadable": true} and are NEVER deletable
  3. purge refuses without a manifest from the same day
  4. purge skips a channel that received a message after it was archived
  5. dry-run deletes nothing
  6. resume skips channels that already finished
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

import ops_archive

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(days=200)          # comfortably past STALE_DAYS


# ----------------------------------------------------------------- the fakes
class FakeAttachment:
    """`read()` hands back real bytes, like discord.Attachment does. `url` is the
    signed CDN link that dies in ~24h — storing it instead of the bytes is the exact
    failure this module exists to prevent."""

    def __init__(self, filename, data=b"", content_type="image/png", fail_times=0):
        self.filename = filename
        self._data = data
        self.size = len(data)
        self.content_type = content_type
        self.url = "https://cdn.discordapp.com/attachments/1/2/%s?ex=deadbeef&is=expired" % filename
        self.fail_times = fail_times
        self.reads = 0

    async def read(self):
        self.reads += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("cdn hiccup")
        return self._data


class FakeAuthor:
    def __init__(self, aid, name, bot=False):
        self.id, self.name, self.display_name, self.bot = aid, name, name, bot

    def __str__(self):
        return "%s#0001" % self.name


class FakeMsg:
    def __init__(self, mid, created_at, author, content="", attachments=(), pinned=False):
        self.id, self.created_at, self.author = mid, created_at, author
        self.content = content
        self.attachments = list(attachments)
        self.embeds, self.reactions, self.pinned = [], [], pinned
        self.edited_at, self.reference = None, None


class FakeCategory:
    def __init__(self, cid, name):
        self.id, self.name = cid, name


class FakeChannel:
    def __init__(self, cid, name, messages=(), category=None, ctype="text", raises=None):
        self.id, self.name, self.type = cid, name, ctype
        self.category = category
        self._messages = list(messages)
        self.raises = raises
        self.deleted = False
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

    async def delete(self, reason=None):
        self.deleted = True


class FakeGuild:
    def __init__(self, channels, gid=99, name="Ouja"):
        self.id, self.name, self.channels = gid, name, list(channels)


class FakeSink:
    """Stands in for Google Drive. Records every folder and every uploaded byte."""

    def __init__(self):
        self.folders = {}          # folder_id -> (parent, name)
        self.files = {}            # (folder_id, filename) -> bytes
        self.mimes = {}

    def configured(self):
        return True

    def root_id(self):
        return "ROOT"

    def folder(self, parent_id, name):
        fid = "%s/%s" % (parent_id, name)
        self.folders[fid] = (parent_id, name)
        return fid

    def upload(self, folder_id, filename, data, mime=None):
        self.files[(folder_id, filename)] = data
        self.mimes[(folder_id, filename)] = mime
        return {"id": "f_%d" % len(self.files), "url": "https://drive/%s" % filename}

    # --- test conveniences
    def find(self, suffix):
        return {k: v for k, v in self.files.items() if k[1].endswith(suffix)}

    def one(self, filename):
        hits = [v for k, v in self.files.items() if k[1] == filename]
        assert len(hits) == 1, "expected exactly one %s, got %d" % (filename, len(hits))
        return hits[0]


class FakeMessage:
    """Just enough of discord.Message for the purge handler."""

    def __init__(self, guild, content="!ouja-purge", admin=True, uid=7):
        self.guild = guild
        self.content = content
        self.author = type("A", (), {"id": uid, "bot": False,
                                     "guild_permissions": type("P", (), {"administrator": admin})()})()
        self.replies, self.sent = [], []
        me = self

        class _Ch:
            id = 1

            async def send(self, content=None, files=None, **kw):
                me.sent.append(content or "")
                return type("M", (), {"edit": _noop_edit})()

        self.channel = _Ch()

    async def reply(self, text, **kw):
        self.replies.append(text)

    def said(self, needle):
        return any(needle in t for t in (self.replies + self.sent))


async def _noop_edit(content=None, **kw):
    return None


def run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ the tests
class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ouja-archive-test-")
        self._old_env = dict(os.environ)
        os.environ["STATE_DIR"] = self.tmp
        os.environ.pop("OWNER_DISCORD_ID", None)
        # no real sleeping in tests
        self._pauses = (ops_archive.CHANNEL_PAUSE, ops_archive.ATTACH_BACKOFF, ops_archive.MSG_PAUSE)
        ops_archive.CHANNEL_PAUSE = 0
        ops_archive.ATTACH_BACKOFF = 0
        ops_archive.MSG_PAUSE = 0
        ops_archive._RUNNING["archive"] = False
        ops_archive._RUNNING["purge"] = False

    def tearDown(self):
        (ops_archive.CHANNEL_PAUSE, ops_archive.ATTACH_BACKOFF,
         ops_archive.MSG_PAUSE) = self._pauses
        os.environ.clear()
        os.environ.update(self._old_env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- guarantee 1: bytes, not URLs
    def test_attachment_bytes_are_downloaded_and_stored(self):
        blob = b"\x89PNG\r\n\x1a\n-real-image-bytes-"
        att = FakeAttachment("proof.png", blob)
        cat = FakeCategory(1, "التنظيف")
        ch = FakeChannel(10, "ouja-101", category=cat, messages=[
            FakeMsg(1, OLD, FakeAuthor(5, "Aseel"), "خلصت", [att])])
        sink = FakeSink()
        man = run(ops_archive.archive_guild(FakeGuild([ch]), sink, day="2026-07-25"))

        stored = sink.find("_proof.png")
        self.assertEqual(len(stored), 1, "the attachment file itself must be in Drive")
        (folder, name), data = list(stored.items())[0]
        self.assertEqual(data, blob, "Drive must hold the BYTES, byte-for-byte")
        self.assertTrue(name.startswith("001_"), "files are stored as <NNN>_<original name>")
        self.assertTrue(folder.endswith("/files"), "attachments live in the channel's files/ folder")
        self.assertEqual(att.reads, 1, "attachment.read() must actually be called")

        # the expiring CDN link may be recorded as metadata, but is never the backup
        msgs = json.loads(sink.one("messages.json").decode("utf-8"))
        rec = msgs["messages"][0]["attachments"][0]
        self.assertEqual(rec["stored_as"], name)
        self.assertTrue(rec["drive_file_id"], "the stored copy must have a Drive id")
        self.assertIn("cdn.discordapp.com", rec["source_url"])
        for (_f, fname), payload in sink.files.items():
            if fname.endswith(".png"):
                self.assertNotIn(b"cdn.discordapp.com", payload,
                                 "a URL must never be stored in place of the file")

        self.assertEqual(man["totals"]["attachments"], 1)
        self.assertEqual(man["totals"]["bytes"], len(blob))

    def test_transcript_points_at_the_relative_files_path(self):
        att = FakeAttachment("shot.png", b"img")
        ch = FakeChannel(11, "room", messages=[FakeMsg(1, OLD, FakeAuthor(5, "Aseel"), "شوف", [att])])
        sink = FakeSink()
        run(ops_archive.archive_guild(FakeGuild([ch]), sink, day="2026-07-25"))
        html = sink.one("transcript.html").decode("utf-8")
        self.assertIn('src="files/001_shot.png"', html)
        self.assertIn('dir="rtl"', html)
        self.assertIn("Aseel", html)

    def test_failed_attachment_is_recorded_never_silently_dropped(self):
        att = FakeAttachment("gone.png", b"x", fail_times=99)
        ch = FakeChannel(12, "room", messages=[FakeMsg(1, OLD, FakeAuthor(5, "A"), "", [att])])
        sink = FakeSink()
        man = run(ops_archive.archive_guild(FakeGuild([ch]), sink, day="2026-07-25"))
        entry = man["channels"][0]
        self.assertEqual(att.reads, 1 + ops_archive.ATTACH_RETRIES, "one try + two retries")
        self.assertEqual(len(entry["failed_attachments"]), 1)
        self.assertEqual(man["totals"]["failed_attachments"], 1)
        msgs = json.loads(sink.one("messages.json").decode("utf-8"))
        self.assertTrue(msgs["messages"][0]["attachments"][0]["failed"])
        ok, why = ops_archive.deletable(entry)
        self.assertFalse(ok, "a channel with a lost attachment must not be deletable")
        self.assertIn("مرفقات", why)

    # ---- guarantee 2: unreadable channels
    def test_unreadable_channel_is_archived_as_unreadable_and_never_deletable(self):
        ch = FakeChannel(13, "private-room", raises=RuntimeError("Missing Access"))
        sink = FakeSink()
        man = run(ops_archive.archive_guild(FakeGuild([ch]), sink, day="2026-07-25"))
        body = json.loads(sink.one("messages.json").decode("utf-8"))
        self.assertTrue(body["unreadable"])
        self.assertIn("Missing Access", body["reason"])
        entry = man["channels"][0]
        self.assertFalse(entry["readable"])
        self.assertTrue(entry["completed"], "the folder still exists — no silent gap")
        self.assertEqual(man["totals"]["unreadable"], 1)
        ok, why = ops_archive.deletable(entry)
        self.assertFalse(ok)
        self.assertIn("ما يقدر يقرأ", why)

    def test_discord_forbidden_is_treated_as_unreadable(self):
        import discord
        resp = type("R", (), {"status": 403, "reason": "Forbidden"})()
        ch = FakeChannel(14, "locked", raises=discord.Forbidden(resp, "Missing Access"))
        sink = FakeSink()
        man = run(ops_archive.archive_guild(FakeGuild([ch]), sink, day="2026-07-25"))
        self.assertFalse(man["channels"][0]["readable"])
        self.assertFalse(ops_archive.deletable(man["channels"][0])[0])

    # ---- guarantee 6: resume
    def test_resume_skips_completed_channels(self):
        a = FakeChannel(20, "done", messages=[FakeMsg(1, OLD, FakeAuthor(5, "A"), "hi")])
        b = FakeChannel(21, "todo", messages=[FakeMsg(2, OLD, FakeAuthor(5, "A"), "hi")])
        sink = FakeSink()
        run(ops_archive.archive_guild(FakeGuild([a]), sink, day="2026-07-25"))
        self.assertEqual(a.history_calls, 1)

        state = ops_archive.load_state()
        self.assertTrue(state["channels"][str(a.id)]["completed"])

        sink2 = FakeSink()
        man = run(ops_archive.archive_guild(FakeGuild([a, b]), sink2, day="2026-07-25", state=state))
        self.assertEqual(a.history_calls, 1, "an already-archived channel must not be re-read")
        self.assertEqual(b.history_calls, 1)
        self.assertEqual(man["totals"]["channels"], 2, "the manifest still covers both")
        self.assertEqual(len(sink2.find("messages.json")), 1, "only the unfinished channel re-uploaded")


class PurgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ouja-purge-test-")
        self._old_env = dict(os.environ)
        os.environ["STATE_DIR"] = self.tmp
        os.environ.pop("OWNER_DISCORD_ID", None)
        self._pause = ops_archive.CHANNEL_PAUSE
        ops_archive.CHANNEL_PAUSE = 0
        ops_archive._RUNNING["archive"] = False
        ops_archive._RUNNING["purge"] = False

    def tearDown(self):
        ops_archive.CHANNEL_PAUSE = self._pause
        os.environ.clear()
        os.environ.update(self._old_env)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _entry(self, cid, name, last_id="1", last_at=None, **kw):
        e = {"id": str(cid), "name": name, "type": "text", "readable": True, "reason": None,
             "messages": 3, "attachments": 0, "bytes": 0, "failed_attachments": [],
             "last_message_id": last_id,
             "last_message_at": (last_at or OLD).isoformat(),
             "drive_folder_id": "d", "messages_sha256": "abc", "completed": True,
             "archived_at": NOW.isoformat()}
        e.update(kw)
        return e

    def _manifest(self, entries, day=None):
        return {"date": day or NOW.date().isoformat(), "guild": {"id": "99", "name": "Ouja"},
                "totals": {"channels": len(entries)}, "channels": entries}

    # ---- guarantee 3: no same-day manifest => refuse
    def test_purge_refuses_without_a_same_day_manifest(self):
        ch = FakeChannel(30, "dead-room")
        msg = FakeMessage(FakeGuild([ch]))
        run(ops_archive.handle_purge(msg, bot=None))
        self.assertTrue(msg.said("ما فيه أرشيف بتاريخ اليوم"))
        self.assertFalse(ch.deleted)

    def test_purge_ignores_a_manifest_from_another_day(self):
        old_day = (NOW - timedelta(days=3)).date().isoformat()
        ops_archive._write_json(ops_archive._manifest_path(old_day),
                                self._manifest([self._entry(30, "dead-room")], day=old_day))
        ch = FakeChannel(30, "dead-room")
        msg = FakeMessage(FakeGuild([ch]))
        run(ops_archive.handle_purge(msg, bot=None))
        self.assertTrue(msg.said("ما فيه أرشيف بتاريخ اليوم"))
        self.assertFalse(ch.deleted)

    # ---- guarantee 4: anything that moved since the archive is skipped
    def test_purge_skips_a_channel_that_got_a_new_message_after_archiving(self):
        ch = FakeChannel(31, "was-dead", messages=[
            FakeMsg("1", OLD, FakeAuthor(5, "A"), "old"),
            FakeMsg("999", NOW, FakeAuthor(5, "A"), "someone wrote today")])
        man = self._manifest([self._entry(31, "was-dead", last_id="1")])
        res = run(ops_archive.run_purge(FakeGuild([ch]), man, dryrun=False, pause=0))
        self.assertFalse(ch.deleted)
        self.assertEqual(res["deleted"], [])
        self.assertEqual(len(res["skipped"]), 1)
        self.assertIn("رسالة جديدة", res["skipped"][0]["skip_reason"])

    # ---- guarantee 5: dry run deletes nothing
    def test_dryrun_deletes_nothing(self):
        ch = FakeChannel(32, "dead", messages=[FakeMsg("1", OLD, FakeAuthor(5, "A"), "old")])
        man = self._manifest([self._entry(32, "dead", last_id="1")])
        res = run(ops_archive.run_purge(FakeGuild([ch]), man, dryrun=True, pause=0))
        self.assertFalse(ch.deleted)
        self.assertEqual(res["deleted"], [])
        self.assertTrue(res["dryrun"])
        self.assertIn("DRYRUN", res["skipped"][0]["skip_reason"])

    def test_real_purge_deletes_only_the_confirmed_dead(self):
        dead = FakeChannel(33, "dead", messages=[FakeMsg("1", OLD, FakeAuthor(5, "A"), "old")])
        unread = FakeChannel(34, "locked")
        alive = FakeChannel(35, "alive", messages=[FakeMsg("2", NOW, FakeAuthor(5, "A"), "today")])
        man = self._manifest([
            self._entry(33, "dead", last_id="1"),
            self._entry(34, "locked", readable=False, reason="forbidden"),
            self._entry(35, "alive", last_id="2", last_at=NOW),
        ])
        res = run(ops_archive.run_purge(FakeGuild([dead, unread, alive]), dryrun=False,
                                        manifest=man, pause=0))
        self.assertTrue(dead.deleted)
        self.assertFalse(unread.deleted, "unreadable channels are NEVER deletable")
        self.assertFalse(alive.deleted)
        self.assertEqual([d["name"] for d in res["deleted"]], ["dead"])
        self.assertEqual(len(res["blocked"]), 2)

    def test_purge_stops_everything_on_the_first_error(self):
        class Boom(FakeChannel):
            async def delete(self, reason=None):
                raise RuntimeError("Discord said no")

        a = FakeChannel(40, "a", messages=[FakeMsg("1", OLD, FakeAuthor(5, "A"), "x")])
        b = Boom(41, "b", messages=[FakeMsg("2", OLD, FakeAuthor(5, "A"), "x")])
        c = FakeChannel(42, "c", messages=[FakeMsg("3", OLD, FakeAuthor(5, "A"), "x")])
        man = self._manifest([self._entry(40, "a", last_id="1"),
                              self._entry(41, "b", last_id="2"),
                              self._entry(42, "c", last_id="3")])
        res = run(ops_archive.run_purge(FakeGuild([a, b, c]), man, dryrun=False, pause=0))
        self.assertTrue(a.deleted)
        self.assertFalse(c.deleted, "the run must stop, not carry on past an error")
        self.assertIn("Discord said no", res["error"])
        self.assertEqual([d["name"] for d in res["deleted"]], ["a"])

    def test_categories_and_non_text_channels_are_never_candidates(self):
        man = self._manifest([self._entry(50, "voice-room", type="voice"),
                              self._entry(51, "a-category", type="category")])
        cands, blocked = ops_archive.purge_candidates(man)
        self.assertEqual(cands, [])
        self.assertEqual(len(blocked), 2)

    def test_dryrun_env_flag_defaults_to_on(self):
        os.environ.pop("ARCHIVE_PURGE_DRYRUN", None)
        self.assertTrue(ops_archive._purge_dryrun())
        os.environ["ARCHIVE_PURGE_DRYRUN"] = "1"
        self.assertTrue(ops_archive._purge_dryrun())
        os.environ["ARCHIVE_PURGE_DRYRUN"] = "0"
        self.assertFalse(ops_archive._purge_dryrun())


if __name__ == "__main__":
    unittest.main()
