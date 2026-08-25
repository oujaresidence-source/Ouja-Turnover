# tests/test_finchat_db.py
# -*- coding: utf-8 -*-
"""finchat.db — KB CRUD, per-user chat log + daily cap counter, escalation lifecycle."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from finchat import db as fdb


class TestFinchatDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fctest_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        fdb.reset_init_cache()

    def test_kb_upsert_and_all(self):
        i = fdb.kb_upsert("كيف اعتمد مصروف؟", "من تبويب المصاريف اضغط اعتماد",
                          links=[{"label_ar": "المصاريف", "route": "#exp"}],
                          tags="مصاريف اعتماد", source="seed")
        self.assertIsInstance(i, int)
        rows = fdb.kb_all()
        self.assertEqual(len([r for r in rows if r["id"] == i]), 1)
        row = [r for r in rows if r["id"] == i][0]
        self.assertEqual(row["links"][0]["route"], "#exp")
        # update by id keeps same row
        fdb.kb_upsert("كيف اعتمد مصروف؟", "جواب محدث", id=i)
        row2 = [r for r in fdb.kb_all() if r["id"] == i][0]
        self.assertEqual(row2["answer_ar"], "جواب محدث")

    def test_kb_disable_hides_from_enabled(self):
        i = fdb.kb_upsert("سؤال مؤقت", "جواب", source="manual")
        fdb.kb_set_enabled(i, False)
        self.assertNotIn(i, [r["id"] for r in fdb.kb_all(enabled_only=True)])
        self.assertIn(i, [r["id"] for r in fdb.kb_all(enabled_only=False)])

    def test_kb_delete(self):
        i = fdb.kb_upsert("للحذف", "ج", source="manual")
        fdb.kb_delete(i)
        self.assertNotIn(i, [r["id"] for r in fdb.kb_all(enabled_only=False)])

    def test_msgs_roundtrip_and_daily_count(self):
        u = "acc1"
        before = fdb.msgs_today_count(u)
        fdb.msg_add(u, "user", "سؤالي")
        fdb.msg_add(u, "bot", "جوابي", kb_ids=[1, 2], model="haiku", confidence=0.9,
                    links=[{"label_ar": "الملاك", "route": "#owners"}])
        msgs = fdb.msgs_for(u, limit=10)
        self.assertEqual(msgs[-2]["role"], "user")
        self.assertEqual(msgs[-1]["links"][0]["route"], "#owners")
        self.assertEqual(fdb.msgs_today_count(u), before + 1)  # only role=user counts

    def test_escalation_lifecycle(self):
        e = fdb.esc_create("acc2", "الاكسبورت معلق", context={"last_msgs": ["x"]})
        self.assertIsInstance(e, int)
        self.assertIn(e, [r["id"] for r in fdb.esc_open_list()])
        fdb.esc_answer(e, "انحل — حدث الصفحة", saved_as_kb=1)
        self.assertNotIn(e, [r["id"] for r in fdb.esc_open_list()])
        row = fdb.esc_get(e)
        self.assertEqual(row["status"], "answered")
        self.assertEqual(row["answer"], "انحل — حدث الصفحة")
        # answering twice is a no-op that keeps the first answer
        fdb.esc_answer(e, "جواب ثاني", saved_as_kb=0)
        self.assertEqual(fdb.esc_get(e)["answer"], "انحل — حدث الصفحة")


if __name__ == "__main__":
    unittest.main()
