# -*- coding: utf-8 -*-
"""seed_kb.json — structural validation: required fields, valid routes, no dupes, size floor,
and the grounding rule (seed answers never state a live financial figure)."""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VALID_ROUTES = {"#today", "#bank", "#match", "#exp", "#custody", "#owners",
                "#close", "#stmts", "#budget", "#setup", "#guide", "#assist"}


class TestSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "finchat", "seed_kb.json")
        with open(p, encoding="utf-8") as f:
            cls.items = json.load(f)

    def test_size_floor(self):
        self.assertGreaterEqual(len(self.items), 150)

    def test_required_fields_and_routes(self):
        for it in self.items:
            self.assertTrue(it.get("q_ar"), it)
            self.assertTrue(it.get("answer_ar"), it)
            for l in it.get("links") or []:
                self.assertIn(l.get("route"), VALID_ROUTES, it["q_ar"])
                self.assertTrue(l.get("label_ar"), it["q_ar"])

    def test_no_duplicate_questions(self):
        qs = [it["q_ar"].strip() for it in self.items]
        self.assertEqual(len(qs), len(set(qs)))

    def test_no_numbers_promised(self):
        for it in self.items:
            self.assertIsNone(re.search(r"\d{4,}\s*(ر\.س|ريال|SAR)", it["answer_ar"]),
                              it["q_ar"])

    def test_retrieval_finds_seed_answers(self):
        """Synthetic-data logic test (CLAUDE.md): real mined questions must surface the
        right seed entry in the top-3 candidates."""
        import tempfile
        from brain import db as bdb
        from finchat import db as fdb
        from finchat import kb as fkb
        tmp = tempfile.mkdtemp(prefix="fcseedret_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        fdb.reset_init_cache()
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "finchat", "seed_kb.json")
        self.assertGreater(fkb.seed_if_empty(p), 0)
        entries = fdb.kb_all()
        # (mined question, token that must appear in a top-3 candidate's tags)
        cases = [
            ("المصروف يبلغ كل شهر بقيمة مختلفة وما تطلع نسبة عوجا", "نظافة"),
            ("ابغى اقسم مصروف ٣٠٠٠ على ثلاث شقق", "تقسيم"),
            ("ليش المصروف واقف على مصدرة؟", "dryrun"),
            ("كيف اطلع تقرير من تاريخ الى تاريخ للمالك", "فترة"),
            ("المالك يقول الرابط ما يشتغل", "رابط"),
            ("وين احط مصروف يدوي عشان يطلع في كشف الشقة", "يدوي"),
            ("كشف الراجحي كيف ارفعه", "استيراد"),
            ("العهده حقت الموظف ما تطلع", "عهدة"),
        ]
        for q, tag in cases:
            top3 = fkb.retrieve(q, entries, k=3)
            self.assertTrue(top3, q)
            self.assertTrue(any(tag in (e.get("tags") or "") for e in top3),
                            "%r did not surface a %r entry; got: %r"
                            % (q, tag, [e["q_ar"] for e in top3]))


if __name__ == "__main__":
    unittest.main()
