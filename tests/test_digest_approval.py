# -*- coding: utf-8 -*-
"""digest.approval + digest.notify — dry-run is provably inert (the publisher is never
called), each button's state transition, rulings written, message text pure."""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "digest"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain import db as bdb
from digest import approval, build, db as ddb, notify
from digest.render import build as rbuild
from test_digest_build import fixture_http

TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime(2026, 9, 2, 13, 0, tzinfo=TZ)
_CHROMIUM = rbuild.chromium_available()


class Transitions(unittest.TestCase):
    def test_table(self):
        self.assertEqual(approval.transition("preview", "approve"), "approved")
        self.assertEqual(approval.transition("preview", "alt"), "preview")
        self.assertEqual(approval.transition("preview", "rephrase"), "preview")
        self.assertEqual(approval.transition("preview", "drop"), "preview")
        self.assertEqual(approval.transition("preview", "rebuild"), "building")
        self.assertEqual(approval.transition("failed", "rebuild"), "building")
        self.assertIsNone(approval.transition("published", "approve"))
        self.assertIsNone(approval.transition("published", "drop"))
        self.assertIsNone(approval.transition("approved", "alt"))
        self.assertEqual(approval.allowed("preview"), ["approve", "alt", "rephrase", "drop", "rebuild"])
        self.assertEqual(approval.allowed("published"), [])
        self.assertEqual(approval.allowed("failed"), ["rebuild"])


class Notify(unittest.TestCase):
    def test_message_lists_sections_drops_sources_and_is_pure(self):
        p = rbuild.reference_payload()
        m = notify.build_message(p, 12, p["dropped"], "https://oujares.com")
        self.assertIn("العدد ١٢", m)
        self.assertIn("نور الرياض يرجع", m)
        self.assertIn("الشباب × الهلال (الجمعة ٩:٠٠م)", m)
        self.assertIn("حذفنا:", m)
        self.assertIn("مؤتمر التقنية المالية", m)
        self.assertIn("المصادر: Platinumlist", m)
        self.assertIn("https://oujares.com/digest", m)
        self.assertNotIn(chr(92), m)
        self.assertEqual(notify.build_message({"sections": []}, 1), "")
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "digest", "notify.py"), encoding="utf-8") as fh:
            self.assertNotIn(chr(92), fh.read())

    def test_status_line(self):
        self.assertEqual(notify.status_line(None), "ما فيه عدد بعد")
        self.assertIn("جاهز للاعتماد", notify.status_line({"issue_no": 3, "week_of": "2026-09-03", "status": "preview"}))


class _Recorder(object):
    def __init__(self):
        self.calls = []

    def __call__(self, row):
        self.calls.append(row["id"])


@unittest.skipUnless(_CHROMIUM, "Chromium not available")
class Act(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="digestappr_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        ddb.reset_init_cache()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        for t in ("digest_rulings", "digest_candidates", "digest_items", "digest_issues"):
            ddb.execute("DELETE FROM " + t)
        self.rep = build.build_issue(NOW, fixture_http(), out_root=self.tmp)
        self.iid = self.rep["issue_id"]

    def test_dryrun_is_inert(self):
        pub = _Recorder()
        res = approval.act(self.iid, "approve", "faisal", NOW, fixture_http(), dry_run=True, publisher=pub, out_root=self.tmp)
        self.assertEqual(pub.calls, [])
        self.assertEqual(res["status"], "approved")
        self.assertEqual(ddb.issue(self.iid)["status"], "approved")
        self.assertIsNone(ddb.issue(self.iid)["published_at"])

    def test_live_approve_calls_the_publisher_once_and_publishes(self):
        pub = _Recorder()
        res = approval.act(self.iid, "approve", "faisal", NOW, fixture_http(), dry_run=False, publisher=pub, out_root=self.tmp)
        self.assertEqual(pub.calls, [self.iid])
        self.assertEqual(res["status"], "published")
        self.assertTrue(ddb.issue(self.iid)["published_at"])
        with self.assertRaises(approval.ApprovalError):
            approval.act(self.iid, "drop", "faisal", NOW, fixture_http(), section="events", slot=0, out_root=self.tmp)

    def test_each_button_writes_a_ruling(self):
        http = fixture_http()
        approval.act(self.iid, "alt", "faisal", NOW, http, section="events", slot=0, rank_no=1, out_root=self.tmp)
        approval.act(self.iid, "drop", "faisal", NOW, http, section="events", slot=1, out_root=self.tmp)
        approval.act(self.iid, "rephrase", "faisal", NOW, http, model_call=None, out_root=self.tmp)
        acts = [r["action"] for r in ddb.rulings_for(self.iid)]
        self.assertEqual(acts, ["alt", "drop", "rephrase"])
        self.assertTrue(all(r["who"] == "faisal" for r in ddb.rulings_for(self.iid)))
        self.assertEqual(ddb.issue(self.iid)["status"], "preview")

    def test_bad_requests_are_named_not_crashed(self):
        with self.assertRaises(approval.ApprovalError):
            approval.act(self.iid, "alt", "faisal", NOW, fixture_http(), out_root=self.tmp)
        with self.assertRaises(approval.ApprovalError):
            approval.act(999999, "approve", "faisal", NOW, fixture_http(), out_root=self.tmp)
        with self.assertRaises(approval.ApprovalError):
            approval.act(self.iid, "alt", "faisal", NOW, fixture_http(), section="events", slot=0, rank_no=99, out_root=self.tmp)


if __name__ == "__main__":
    unittest.main()
