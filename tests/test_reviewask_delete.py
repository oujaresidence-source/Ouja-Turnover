# -*- coding: utf-8 -*-
"""
«رفع التقييم» — the 7-day room sweep (owner ruling R7, spec §13). The REFUSALS come first:
the only rooms this package may ever delete are review rooms whose ticket closed ≥ 7 days ago,
fetched by the stored id, whose topic carries the SAME reservation, after the transcript is
saved. "Couldn't check" is never "deleted".

Run: python3 -m unittest tests.test_reviewask_delete
"""

import asyncio
import io
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb  # noqa: E402
from reviewask import db, engine, flow  # noqa: E402
from reviewask.host import HOST  # noqa: E402

TZ = engine.tz()
NOW = datetime.datetime(2026, 11, 1, 3, 0, tzinfo=TZ)


def run(coro):
    return asyncio.run(coro)


class Rooms:
    def __init__(self):
        self.rooms = {}              # channel id -> topic
        self.deleted = []
        self.fail_info = set()
        self.fail_transcript = set()
        self.calls = []

    async def room_info(self, cid):
        self.calls.append(("info", cid))
        if cid in self.fail_info:
            raise RuntimeError("discord 500")
        if cid == "none":
            return None
        if cid not in self.rooms:
            return {"exists": False, "topic": ""}
        return {"exists": True, "topic": self.rooms[cid]}

    async def fetch_transcript(self, cid, limit):
        self.calls.append(("transcript", cid))
        if cid in self.fail_transcript:
            raise RuntimeError("history refused")
        return [{"author": "bot", "at": "2026-10-20T10:00:00+03:00", "content": "card",
                 "embeds": [], "attachments": []}]

    async def delete_room(self, cid):
        # the transcript MUST already be in the database when Discord is asked to delete
        t = db.by_channel(cid)
        assert t and db.transcript(t["id"]) is not None, "deleted before the transcript was saved"
        self.calls.append(("delete", cid))
        self.deleted.append(cid)
        self.rooms.pop(cid, None)
        return True


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="rv_del_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        db.reset_init_cache()
        flow._locks.clear()
        os.environ.pop("REVIEWASK_DELETE_AFTER_DAYS", None)
        self.r = Rooms()
        HOST.room_info = self.r.room_info
        HOST.fetch_transcript = self.r.fetch_transcript
        HOST.delete_room = self.r.delete_room
        HOST.now = lambda: NOW

    def make(self, res, cid, state=engine.REVIEWED, closed_days_ago=8, topic=None):
        created, row = db.insert_ticket({"reservation_id": res, "lid": 1, "day": "2026-10-10",
                                         "unit": "Ouja | A", "guest": "G", "state": state,
                                         "channel_id": cid})
        closed = NOW - datetime.timedelta(days=closed_days_ago) if closed_days_ago is not None else None
        db.update_ticket(row["id"], {"closed_at": engine.iso(closed)})
        self.r.rooms[cid] = topic if topic is not None else engine.topic(res, 1, row["id"])
        return db.ticket(row["id"])

    def sweep(self):
        return run(flow.sweep_closed(NOW, pause=0))


class TestRefusals(Base):
    def test_open_ticket_is_never_deleted(self):
        for st in engine.OPEN:
            self.make("o-" + st, "c-" + st, state=st, closed_days_ago=30)
        self.sweep()
        self.assertEqual(self.r.deleted, [])

    def test_closed_less_than_seven_days_is_kept(self):
        self.make("r1", "c1", closed_days_ago=6)
        self.make("r2", "c2", closed_days_ago=None)
        self.sweep()
        self.assertEqual(self.r.deleted, [])

    def test_wrong_topic_is_refused_and_marked(self):
        t = self.make("r3", "c3", topic="ouja-rv:999 lid:1 seq:1")
        t2 = self.make("r4", "c4", topic="ouja-ticket:maint lid:1 seq:3")
        t3 = self.make("r5", "c5", topic="")
        self.sweep()
        self.assertEqual(self.r.deleted, [])
        for x in (t, t2, t3):
            row = db.ticket(x["id"])
            self.assertIsNone(row["deleted_at"])
            self.assertTrue(row["delete_note"].startswith("refused"))
            self.assertTrue(db.has_event(x["id"], "delete_refused"))
        self.r.calls.clear()
        self.sweep()                                         # a refusal is not retried every hour
        self.assertEqual(self.r.calls, [])

    def test_topic_prefix_of_another_reservation_is_refused(self):
        self.make("12", "c6", topic="ouja-rv:123 lid:1 seq:1")
        self.sweep()
        self.assertEqual(self.r.deleted, [])

    def test_could_not_check_is_never_deleted(self):
        t = self.make("r7", "c7")
        self.r.fail_info.add("c7")
        t2 = self.make("r8", "none")
        self.sweep()
        self.assertEqual(self.r.deleted, [])
        self.assertIsNone(db.ticket(t["id"])["deleted_at"])
        self.assertIsNone(db.ticket(t2["id"])["deleted_at"])

    def test_transcript_failure_keeps_the_room(self):
        t = self.make("r9", "c9")
        self.r.fail_transcript.add("c9")
        self.sweep()
        self.assertEqual(self.r.deleted, [])
        self.assertIsNone(db.ticket(t["id"])["deleted_at"])


class TestDeletes(Base):
    def test_closed_seven_days_with_matching_topic_is_deleted_after_transcript(self):
        t = self.make("r10", "c10", closed_days_ago=7)
        out = self.sweep()
        self.assertEqual(out, [t["id"]])
        self.assertEqual(self.r.deleted, ["c10"])
        order = [c[0] for c in self.r.calls]
        self.assertEqual(order, ["info", "transcript", "delete"])
        row = db.ticket(t["id"])
        self.assertTrue(row["deleted_at"])
        tr = db.transcript(t["id"])
        self.assertEqual(tr["n"], 1)
        self.assertEqual(tr["messages"][0]["content"], "card")
        self.assertTrue(db.has_event(t["id"], "room_deleted"))
        # the record stays forever
        self.assertEqual(db.ticket(t["id"])["state"], engine.REVIEWED)

    def test_missing_room_is_marked_not_deleted(self):
        t = self.make("r11", "c11")
        del self.r.rooms["c11"]
        self.sweep()
        self.assertEqual(self.r.deleted, [])
        row = db.ticket(t["id"])
        self.assertTrue(row["deleted_at"])
        self.assertEqual(row["delete_note"], "كانت محذوفة")

    def test_max_ten_per_run(self):
        for i in range(13):
            self.make("m%d" % i, "cm%d" % i)
        self.sweep()
        self.assertEqual(len(self.r.deleted), 10)
        self.sweep()
        self.assertEqual(len(self.r.deleted), 13)

    def test_env_days(self):
        os.environ["REVIEWASK_DELETE_AFTER_DAYS"] = "10"
        try:
            self.make("r12", "c12", closed_days_ago=8)
            self.sweep()
            self.assertEqual(self.r.deleted, [])
        finally:
            os.environ.pop("REVIEWASK_DELETE_AFTER_DAYS", None)

    def test_hourly_latch(self):
        self.make("r13", "c13")
        run(flow.maybe_sweep(NOW))
        self.make("r14", "c14")
        run(flow.maybe_sweep(NOW + datetime.timedelta(minutes=30)))
        self.assertEqual(self.r.deleted, ["c13"])


# The package logs with print(); the gate reads the LAST line of the combined output, so the
# logs are captured here (unittest reports on stderr, untouched).
_REAL_STDOUT = sys.stdout


def setUpModule():
    sys.stdout = io.StringIO()


def tearDownModule():
    sys.stdout = _REAL_STDOUT


if __name__ == "__main__":
    unittest.main()
