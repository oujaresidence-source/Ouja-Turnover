# tests/test_finchat_kb.py
# -*- coding: utf-8 -*-
"""finchat.kb — normalization handles messy Arabic; retrieval ranks the right entry first."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from finchat import db as fdb
from finchat import kb as fkb


class TestNormalize(unittest.TestCase):
    def test_strips_tashkeel_and_unifies_letters(self):
        self.assertEqual(fkb.normalize_ar("كَيْفَ أعْتَمِدُ"), "كيف اعتمد")
        self.assertEqual(fkb.normalize_ar("إلى الأمام"), "الي الامام")
        self.assertEqual(fkb.normalize_ar("الفاتورة"), "الفاتوره")
        self.assertEqual(fkb.normalize_ar("مبنى"), "مبني")

    def test_lowercases_latin_and_collapses_space(self):
        self.assertEqual(fkb.normalize_ar("  EXPORT   فشل "), "export فشل")

    def test_strips_punctuation(self):
        self.assertEqual(fkb.normalize_ar("وش السالفة؟!"), "وش السالفه")


class TestRetrieve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fckb_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        fdb.reset_init_cache()
        fdb.kb_upsert("كيف اعتمد مصروف؟", "من المصاريف اضغط اعتماد", tags="مصاريف اعتماد موافقة", source="seed")
        fdb.kb_upsert("كيف اطلع كشف مالك؟", "من تبويب الملاك اختر المالك", tags="ملاك كشف تقرير", source="seed")
        fdb.kb_upsert("وش يعني تصدير معلق؟", "الدراي-رن يوقف عند exported", tags="تصدير دفترة dryrun", source="seed")

    def test_right_entry_wins_despite_messy_phrasing(self):
        got = fkb.retrieve("ابغي أعتمد مصروووف كيف", fdb.kb_all(), k=2)
        self.assertTrue(got)
        self.assertIn("اعتماد", got[0]["tags"])

    def test_tags_help_match(self):
        got = fkb.retrieve("الدفترة والتصدير واقف", fdb.kb_all(), k=2)
        self.assertTrue(got)
        self.assertIn("تصدير", got[0]["tags"])

    def test_no_match_returns_empty(self):
        self.assertEqual(fkb.retrieve("zzzz qqqq", fdb.kb_all(), k=3), [])


class TestSeed(unittest.TestCase):
    def test_seed_if_empty_imports_once(self):
        tmp = tempfile.mkdtemp(prefix="fcseed_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        fdb.reset_init_cache()
        import json
        seed_path = os.path.join(tmp, "seed.json")
        with open(seed_path, "w", encoding="utf-8") as f:
            json.dump([{"q_ar": "س1", "answer_ar": "ج1", "links": [], "tags": "t"}], f, ensure_ascii=False)
        self.assertEqual(fkb.seed_if_empty(seed_path), 1)
        self.assertEqual(fkb.seed_if_empty(seed_path), 0)  # second boot: no re-import
        self.assertEqual(fdb.kb_count(), 1)


if __name__ == "__main__":
    unittest.main()
