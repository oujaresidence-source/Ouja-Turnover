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

    def test_v2_columns_roundtrip(self):
        story = _story()
        story["angle"] = "الفريق حل الموقف بسرعة"
        sid = sdb.add_story("c-v2", "101", "Ouja | A", 9, "hero_save",
                            story, "2026-07-08 09:00:00")
        self.assertEqual(sdb.story(sid)["angle"], "الفريق حل الموقف بسرعة")
        idea = {"hook_spoken": "لو عندك شقة في الرياض", "visual_title": "رقم حقيقي",
                "visual_sub": "", "angle": "", "why_it_works": "هوك الهوية أقوى صيغة",
                "script": [], "video_type": "talking", "cta": "", "audience": "niche",
                "trigger": "identity"}
        iid = sdb.add_idea(sid, idea, "2026-07-08 09:00:00")
        got = [r for r in sdb.ideas() if r["id"] == iid][0]
        self.assertEqual(got["why_it_works"], "هوك الهوية أقوى صيغة")

    def test_top_posted_archetypes(self):
        s1 = sdb.add_story("c-a", "101", "Ouja | A", 9, "hero_save", _story(), "t")
        s2 = sdb.add_story("c-b", "101", "Ouja | A", 9, "transformation", _story(), "t")
        base = {"hook_spoken": "h", "visual_title": "t", "visual_sub": "", "angle": "",
                "why_it_works": "w", "script": [], "video_type": "talking", "cta": "",
                "audience": "niche", "trigger": "curiosity"}
        i1 = sdb.add_idea(s1, base, "t")
        i2 = sdb.add_idea(s2, base, "t")
        sdb.set_idea_status(i1, "posted", views=900000)
        sdb.set_idea_status(i2, "posted", views=100000)
        top = sdb.top_posted_archetypes()
        self.assertEqual(top[0][0], "hero_save")   # highest views first
        self.assertGreater(top[0][1], top[1][1])


if __name__ == "__main__":
    unittest.main()
