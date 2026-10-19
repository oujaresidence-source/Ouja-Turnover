# -*- coding: utf-8 -*-
"""
Closed «صيانة» rooms: saved to Drive (every file as bytes), then deleted on day 3 (2026-10-19).
The REFUSALS come first — "could not save" must never become "deleted".

Run: python3 -m unittest tests.test_maint_cleanup
"""

import asyncio
import datetime
import os
import re
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import maint_cleanup as M  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))
NOW = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=TZ)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(c):
    return asyncio.run(c)


class Att:
    def __init__(self, name, fail=False):
        self.filename, self.fail = name, fail
        self.size, self.content_type, self.url = 3, "image/jpeg", "https://cdn/x"

    async def read(self):
        if self.fail:
            raise RuntimeError("cdn 404")
        return b"img"


class Msg:
    def __init__(self, i, content, atts=()):
        self.id, self.content, self.attachments = i, content, list(atts)
        self.created_at = datetime.datetime(2026, 10, 19, 9, i, tzinfo=TZ)
        self.edited_at, self.reference, self.embeds, self.reactions = None, None, [], []
        self.pinned = False
        self.author = types.SimpleNamespace(display_name="Ali", name="ali", id=7, bot=False)


class Chan:
    def __init__(self, cid, name="مغلقة-صيانة-070-narjis", topic="ouja-ticket:maint lid:5 seq:70",
                 msgs=None):
        self.id, self.name, self.topic = cid, name, topic
        self.category = types.SimpleNamespace(name="صيانه")
        self.msgs = msgs if msgs is not None else [Msg(1, "المكيف خربان"),
                                                    Msg(2, "الفاتورة", [Att("invoice.jpg")])]
        self.deleted = False
        self.log = None

    def history(self, limit=None, oldest_first=True):
        msgs = list(self.msgs)

        async def gen():
            for m in msgs:
                yield m
        return gen()

    async def delete(self, reason=""):
        assert self.log is not None and ("upload", "invoice.jpg") in self.log or not any(
            m.attachments for m in self.msgs), "deleted before the files reached Drive"
        self.deleted = True


class Guild:
    def __init__(self, chans):
        self.chans = {c.id: c for c in chans}

    def get_channel(self, cid):
        return self.chans.get(cid)

    async def fetch_channel(self, cid):
        class NotFound(Exception):
            pass
        raise NotFound("gone")


class Sink:
    def __init__(self, configured=True, fail_upload=False):
        self._c, self.fail_upload, self.log = configured, fail_upload, []

    def configured(self):
        return self._c

    def root_id(self):
        return "root"

    def folder(self, parent, name):
        return "%s/%s" % (parent, name)

    def upload(self, folder, filename, data, mime=None):
        if self.fail_upload:
            raise RuntimeError("storage quota exceeded")
        self.log.append(("upload", filename.split("_", 1)[-1] if filename[:3].isdigit() else filename))
        return {"id": "f", "url": "u"}


class Host:
    def __init__(self, tickets):
        self._dtk = {"tickets": tickets}
        self._tickets = [{"id": "D1", "log": []}]
        self.saved = 0

    def _dtk_save(self):
        self.saved += 1

    def _dash_ticket(self, tid):
        return next((t for t in self._tickets if t["id"] == tid), None)

    def _ticket_log(self, t, who, what):
        t["log"].append(what)

    def _save_json(self, name, obj):
        pass


def rec(**kw):
    r = {"kind": "maint", "status": "closed", "closed_at": "2026-10-19T15:00:00+03:00",
         "delete_on": "2026-10-21", "dash_id": "D1"}
    r.update(kw)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        os.environ["STATE_DIR"] = tempfile.mkdtemp(prefix="mc_")
        M._RUNNING["run"] = False

    def go(self, tickets, chans, sink=None):
        host = Host(tickets)
        sink = sink or Sink()
        for c in chans:
            c.log = sink.log
        rep = run(M.run(Guild(chans), host, now=NOW, sink=sink, pause=0))
        return host, rep


class TestRules(unittest.TestCase):
    def test_day3_is_close_date_plus_two(self):
        self.assertEqual(M.delete_on("2026-10-19T23:30:00+03:00"), "2026-10-21")
        self.assertEqual(M.delete_on("2026-10-19T21:30:00+00:00"), "2026-10-22")   # Riyadh date

    def test_due(self):
        t = {"1": rec(), "2": rec(delete_on="2026-10-22"), "3": rec(status="open"),
             "4": rec(kind="rr"), "5": rec(delete_on=None), "6": rec(room_deleted_at="x"),
             "7": rec(cleanup_refused="x"),
             "8": rec(cleanup_tried_at="2026-10-21T08:00:00+03:00"),
             "9": rec(cleanup_tried_at="2026-10-21T03:00:00+03:00")}
        self.assertEqual([c for c, _r in M.due(t, NOW)], ["1", "9"])

    def test_room_is_ours(self):
        self.assertTrue(M.room_is_ours(Chan(1)))
        self.assertFalse(M.room_is_ours(Chan(1, name="صيانة-070-narjis")))
        self.assertFalse(M.room_is_ours(Chan(1, topic="ouja-ticket:rr")))


class TestRefusals(Base):
    def test_no_drive_deletes_nothing(self):
        c = Chan(11)
        host, rep = self.go({"11": rec()}, [c], Sink(configured=False))
        self.assertEqual(rep["blocked"], "drive")
        self.assertFalse(c.deleted)

    def test_upload_failure_keeps_the_room(self):
        c = Chan(12)
        host, rep = self.go({"12": rec()}, [c], Sink(fail_upload=True))
        self.assertFalse(c.deleted)
        self.assertIn("cleanup_error", host._dtk["tickets"]["12"])
        self.assertNotIn("room_deleted_at", host._dtk["tickets"]["12"])

    def test_a_file_that_cannot_be_read_keeps_the_room(self):
        c = Chan(13, msgs=[Msg(1, "x", [Att("a.jpg", fail=True)])])
        host, rep = self.go({"13": rec()}, [c])
        self.assertFalse(c.deleted)
        self.assertIn("failed", host._dtk["tickets"]["13"]["cleanup_error"])

    def test_renamed_or_foreign_room_is_refused_for_good(self):
        c = Chan(14, name="صيانة-070-narjis")
        host, rep = self.go({"14": rec()}, [c])
        self.assertFalse(c.deleted)
        self.assertTrue(host._dtk["tickets"]["14"]["cleanup_refused"])
        self.assertEqual(M.due(host._dtk["tickets"], NOW + datetime.timedelta(days=1)), [])

    def test_old_tickets_without_a_stamp_are_never_touched(self):
        c = Chan(15)
        host, rep = self.go({"15": rec(delete_on=None)}, [c])
        self.assertFalse(c.deleted)
        self.assertEqual(rep, {"deleted": [], "kept": [], "blocked": ""})

    def test_not_yet_day3(self):
        c = Chan(16)
        self.go({"16": rec(delete_on="2026-10-22")}, [c])
        self.assertFalse(c.deleted)


class TestDelete(Base):
    def test_saved_then_deleted_and_linked_on_the_dashboard(self):
        c = Chan(21)
        host, rep = self.go({"21": rec()}, [c])
        self.assertTrue(c.deleted)
        self.assertEqual(rep["deleted"], ["21"])
        r = host._dtk["tickets"]["21"]
        self.assertTrue(r["room_deleted_at"])
        self.assertEqual((r["archive_messages"], r["archive_files"]), (2, 1))
        self.assertTrue(r["archive_url"].startswith("https://drive.google.com/drive/folders/"))
        self.assertIn(("upload", "transcript.html"), c.log)
        self.assertTrue(any("Drive" in x for x in host._tickets[0]["log"]))
        self.assertTrue(os.path.exists(os.path.join(os.environ["STATE_DIR"], "maint_transcripts",
                                                    "21.json")))
        self.assertGreaterEqual(host.saved, 1)

    def test_room_already_gone_is_just_marked(self):
        host, rep = self.go({"22": rec()}, [])
        self.assertEqual(host._dtk["tickets"]["22"]["cleanup_note"], "كانت محذوفة")


class TestBotWiring(unittest.TestCase):
    """bot.py: the close stamps day 3 and maint rooms skip the archive move."""

    @classmethod
    def setUpClass(cls):
        src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
        i = src.index("async def _tk_close(interaction):")
        cls.close = src[i:src.index("\n_MAINT_CLOSE_REFUSAL", i)]
        cls.src = src

    def test_wired(self):
        self.assertIn("maint_cleanup.setup(bot, _oa_sys.modules[__name__])", self.src)

    def test_close_stamps_and_skips_archive_for_maint(self):
        self.assertIn('rec["delete_on"] = maint_cleanup.delete_on(rec["closed_at"])', self.close)
        stamp = self.close.index('rec["delete_on"]')
        self.assertLess(stamp, self.close.index("_dtk_save()"))
        skip = self.close.index("if maint_day3:\n        return")
        self.assertLess(skip, self.close.index("ops_tidy.archive_closed_channel(ch)"))
        self.assertTrue(re.search(r'maint_day3 = bool\(rec and rec.get\("kind"\) == "maint"', self.close))


if __name__ == "__main__":
    unittest.main()
