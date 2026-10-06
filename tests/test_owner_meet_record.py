# -*- coding: utf-8 -*-
"""The meeting record: immutability, versions, reopen, and chapter 0 (gate G14).

Run: python3 -m unittest tests.test_owner_meet_record
"""
import copy
import datetime
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiohttp import web  # noqa: E402

from brain import db as bdb  # noqa: E402
import owner_meet  # noqa: E402
from owner_meet import db, jobs, render, routes, snapshot  # noqa: E402

FULL = json.loads((ROOT / "tests" / "fixtures" / "owner_meet" / "snapshot_full.json").read_text(encoding="utf-8"))
TODAY = datetime.date(2026, 10, 6)
TZ = datetime.timezone(datetime.timedelta(hours=3))


class _DB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db._inited.clear()
        self.tickets = {}
        self._pdf = jobs._pool.submit
        jobs._pool.submit = lambda *a, **k: None          # no PDF printing inside these tests
        owner_meet.wire({"state_dir": self.tmp, "link_base": lambda: "https://example.test",
                         "ticket_status": lambda ref: self.tickets.get(ref, {"found": False}),
                         "staff_names": lambda: [], "web": web,
                         "now": lambda: datetime.datetime(2026, 10, 6, 12, 0, tzinfo=TZ)})
        owner_meet.bootstrap()
        p = FULL["meta"]["period"]
        self.mid = db.create_meeting("مالك", [77], p, "2026-10-06", "t")
        db.save_snapshot(self.mid, FULL)
        db.set_build(self.mid, state="ready", progress=100)

    def tearDown(self):
        jobs._pool.submit = self._pdf
        shutil.rmtree(self.tmp, ignore_errors=True)


class Immutability(_DB):
    def test_sha_matches_and_a_frozen_row_refuses_update_and_delete(self):
        row = db.snapshot(self.mid)
        self.assertEqual(row["sha256"], db.sha256_of(row["json"]))
        st, out = routes.core_send(self.mid, "Faisal", "admin")
        self.assertEqual(st, 200, out)
        sent = db.snapshot(self.mid)
        self.assertEqual(sent["version"], 2)
        self.assertTrue(sent["frozen"])
        with closing(bdb.connect()) as cx:
            for sql in ("UPDATE meet_snapshots SET json='{}' WHERE meeting_id=? AND version=2",
                        "UPDATE meet_snapshots SET frozen=0 WHERE meeting_id=? AND version=2",
                        "DELETE FROM meet_snapshots WHERE meeting_id=? AND version=2"):
                with self.assertRaises(sqlite3.DatabaseError):
                    cx.execute(sql, (self.mid,))
        self.assertEqual(db.snapshot(self.mid, 2)["sha256"], sent["sha256"])

    def test_the_sent_version_carries_what_was_agreed(self):
        db.add_decision(self.mid, "وافق على تصوير جديد", 900, by="Faisal")
        db.add_commitment(self.mid, "ouja", "مراجعة السعر أسبوعياً", due="2026-10-31", by="Faisal")
        routes.core_send(self.mid, "Faisal", "admin")
        ag = db.snapshot(self.mid)["data"]["owner"]["agreed"]
        self.assertEqual(ag["decisions"][0]["amount_sar"], 900)
        self.assertEqual(ag["commitments"][0]["due"], "2026-10-31")
        self.assertIn("ما اتفقنا عليه اليوم", render.presentation_html(db.snapshot(self.mid)["data"], 1))

    def test_a_sent_meeting_record_cannot_be_edited(self):
        routes.core_send(self.mid, "Faisal", "admin")
        st, out = routes.core_record_add(self.mid, {"kind": "decision", "text": "x"}, "Faisal")
        self.assertEqual(st, 409)


class Reopen(_DB):
    def test_reopen_needs_admin_and_a_reason_and_writes_version_plus_one(self):
        routes.core_send(self.mid, "Faisal", "admin")
        self.assertEqual(routes.core_reopen(self.mid, {"reason": "x"}, "ops", "ops")[0], 403)
        self.assertEqual(routes.core_reopen(self.mid, {"reason": "   "}, "Faisal", "admin")[0], 400)
        st, out = routes.core_reopen(self.mid, {"reason": "صححنا مصروفاً"}, "Faisal", "admin")
        self.assertEqual((st, out["version"]), (200, 3))
        row = db.snapshot(self.mid, 3)
        self.assertEqual((row["reopen_reason"], row["reopened_by"], row["frozen"]), ("صححنا مصروفاً", "Faisal", 0))
        self.assertNotIn("agreed", row["data"]["owner"])
        self.assertEqual(db.meeting(self.mid)["state"], "reopened")

    def test_links_keep_the_version_they_were_made_for(self):
        st, first = routes.core_send(self.mid, "Faisal", "admin")
        routes.core_reopen(self.mid, {"reason": "تصحيح"}, "Faisal", "admin")
        st, second = routes.core_send(self.mid, "Faisal", "admin")
        self.assertEqual(st, 200, second)
        self.assertNotEqual(first["token"], second["token"])
        self.assertEqual(db.link(first["token"])["snapshot_version"], 2)
        self.assertEqual(db.link(second["token"])["snapshot_version"], 4)

    def test_sending_twice_returns_the_same_link(self):
        _s, a = routes.core_send(self.mid, "Faisal", "admin")
        _s, b = routes.core_send(self.mid, "Faisal", "admin")
        self.assertEqual(a["token"], b["token"])
        self.assertTrue(b["already"])


class ChapterZero(_DB):
    def _prev(self):
        p = copy.deepcopy(FULL["meta"]["period"])
        prev = db.create_meeting("مالك", [77], p, "2026-07-05", "t")
        db.set_build(prev, state="sent")
        a = db.add_commitment(prev, "ouja", "تصوير احترافي جديد", due="2026-07-20", linked_ticket="tk_9")
        b = db.add_commitment(prev, "owner", "إرسال صورة التصريح", due="2026-08-01")
        c = db.add_commitment(prev, "ouja", "استبدال المرتبة", due="2026-12-01")
        d = db.add_commitment(prev, "ouja", "تنظيف السجاد")
        db.update_commitment(d, status="done", evidence="أُرسلت صور بعد التنظيف")
        return prev, (a, b, c, d)

    def test_previous_commitments_with_status_and_evidence(self):
        self._prev()
        self.tickets["tk_9"] = {"found": True, "closed": True, "closed_at": "2026-07-18T10:00:00+03:00"}
        pm = snapshot.collect_promises("مالك", self.mid, "2026-10-06", TODAY)
        self.assertEqual(pm["meeting_date"], "2026-07-05")
        st = [(i["text"], i["status"]) for i in pm["items"]]
        self.assertEqual(st, [("تصوير احترافي جديد", "done"), ("إرسال صورة التصريح", "not_done"),
                              ("استبدال المرتبة", "in_progress"), ("تنظيف السجاد", "done")])
        self.assertEqual(pm["items"][0]["evidence"], "أُغلقت التذكرة المرتبطة بتاريخ 18 يوليو 2026")
        self.assertEqual(pm["items"][3]["evidence"], "أُرسلت صور بعد التنظيف")

    def test_an_open_linked_ticket_is_not_evidence(self):
        self._prev()
        self.tickets["tk_9"] = {"found": True, "closed": False}
        pm = snapshot.collect_promises("مالك", self.mid, "2026-10-06", TODAY)
        self.assertEqual(pm["items"][0]["status"], "not_done")

    def test_no_previous_meeting_no_chapter_and_it_sits_after_the_cover(self):
        self.assertIsNone(snapshot.collect_promises("مالك", self.mid, "2026-10-06", TODAY))
        self.assertNotIn("promises", [c["key"] for c in render.chapters(FULL)])
        self._prev()
        snap = copy.deepcopy(FULL)
        snap["owner"]["promises"] = snapshot.collect_promises("مالك", self.mid, "2026-10-06", TODAY)
        keys = [c["key"] for c in render.chapters(snap)]
        self.assertEqual(keys[:2], ["cover", "promises"])

    def test_a_meeting_never_counts_itself_as_the_previous_one(self):
        db.set_build(self.mid, state="sent")
        db.add_commitment(self.mid, "ouja", "هذا الاجتماع نفسه")
        self.assertIsNone(snapshot.collect_promises("مالك", self.mid, "2026-10-06", TODAY))


if __name__ == "__main__":
    unittest.main()
