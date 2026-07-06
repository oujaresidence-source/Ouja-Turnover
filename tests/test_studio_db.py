# -*- coding: utf-8 -*-
"""studio.db — scanned cursor dedup, story round-trip (JSON fields), idea lifecycle."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from studio import db as sdb


def _story():
    return {"title": "الضيف اللي طلب ثلاجة ثانية", "summary": "طلب غريب وانحل",
            "beats": ["طلب", "استغراب", "حل"], "quotes": ["أبغى ثلاجة للكبسة"],
            "emotion": "استغراب ثم ضحك", "lesson": "الطلبات الغريبة فرصة"}


class TestStudioDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="studiotest_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()

    def test_scanned_cursor_dedup(self):
        sdb.mark_scanned("c1", "101", "Ouja | A", "محمد", "confirmed",
                         "2026-06-01 → 2026-06-03", 8, "no_story", 2, "other",
                         "عادي", "2026-07-06 10:00:00")
        sdb.mark_scanned("c1", "101", "Ouja | A", "محمد", "confirmed",
                         "2026-06-01 → 2026-06-03", 8, "no_story", 2, "other",
                         "عادي", "2026-07-06 10:00:00")
        self.assertIn("c1", sdb.scanned_ids())
        self.assertEqual(sdb.scan_counts().get("no_story"), 1)

    def test_story_roundtrip_and_unique_convo(self):
        rid = sdb.add_story("c2", "101", "Ouja | A", 8, "weird_request",
                            _story(), "2026-07-06 10:00:00")
        self.assertTrue(rid)
        sdb.add_story("c2", "101", "Ouja | A", 8, "weird_request",
                      _story(), "2026-07-06 10:00:00")   # dup convo → ignored
        rows = sdb.stories()
        self.assertEqual(len([r for r in rows if r["convo_id"] == "c2"]), 1)
        s = sdb.story(rid)
        self.assertEqual(s["beats"], ["طلب", "استغراب", "حل"])
        self.assertEqual(s["quotes"], ["أبغى ثلاجة للكبسة"])
        sdb.set_story_status(rid, "used")
        self.assertEqual(sdb.story(rid)["status"], "used")

    def test_idea_lifecycle(self):
        idea = {"hook_spoken": "ضيف طلب مني ثلاجة ثانية", "visual_title": "أغرب طلب",
                "visual_sub": "وسويناه", "angle": "قصة", "script": ["هوك", "قصة"],
                "video_type": "talking", "cta": "تابع", "audience": "escape",
                "trigger": "curiosity"}
        iid = sdb.add_idea(1, idea, "2026-07-06 10:00:00")
        self.assertTrue(iid)
        rows = sdb.ideas()
        mine = [r for r in rows if r["id"] == iid][0]
        self.assertEqual(mine["script"], ["هوك", "قصة"])
        self.assertEqual(mine["trigger_kind"], "curiosity")
        sdb.set_idea_status(iid, "posted", views=120000, perf_note="اشتغل زين")
        mine = [r for r in sdb.ideas() if r["id"] == iid][0]
        self.assertEqual(mine["status"], "posted")
        self.assertEqual(mine["views"], 120000)
        self.assertEqual(sdb.set_idea_status(999999, "posted"), 0)


if __name__ == "__main__":
    unittest.main()
