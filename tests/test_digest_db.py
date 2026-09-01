# -*- coding: utf-8 -*-
"""digest.db — issues are unique per week (the loop's latch), candidates keep their rank,
rulings record who/what, and a Discord message id resolves to its issue.
Temp brain.db, no network."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from digest import db as ddb


class DigestDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="digesttest_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        ddb.reset_init_cache()

    def setUp(self):
        for t in ("digest_rulings", "digest_candidates", "digest_items", "digest_issues"):
            ddb.execute("DELETE FROM " + t)

    def test_issue_is_unique_per_week(self):
        a = ddb.open_issue("2026-09-03", 12)
        self.assertEqual(ddb.issue_for_week("2026-09-03")["id"], a)
        with self.assertRaises(Exception):
            ddb.open_issue("2026-09-03", 13)
        self.assertIsNone(ddb.issue_for_week("2026-09-10"))

    def test_issue_no_is_next_after_the_highest(self):
        self.assertEqual(ddb.next_issue_no(), 1)
        ddb.open_issue("2026-09-03", 12)
        self.assertEqual(ddb.next_issue_no(), 13)

    def test_candidates_round_trip_ranked(self):
        iid = ddb.open_issue("2026-09-03", 12)
        ddb.add_candidates(iid, "events", 0, [
            {"ttl": "أ", "score": 0.9, "reasons": ["قريب"]},
            {"ttl": "ب", "score": 0.7},
        ])
        rows = ddb.candidates(iid, "events", 0)
        self.assertEqual([r["rank"] for r in rows], [1, 2])
        self.assertEqual(rows[0]["cand"]["ttl"], "أ")
        self.assertEqual(rows[0]["reasons"], ["قريب"])
        self.assertEqual(rows[0]["score"], 0.9)
        # re-adding for the same slot replaces (a rebuild must not stack duplicates)
        ddb.add_candidates(iid, "events", 0, [{"ttl": "ج", "score": 0.5}])
        self.assertEqual([r["cand"]["ttl"] for r in ddb.candidates(iid, "events", 0)], ["ج"])

    def test_ruling_is_recorded_with_who_and_action(self):
        iid = ddb.open_issue("2026-09-03", 12)
        ddb.add_ruling(iid, "faisal", "drop", section="events", slot=1, detail={"why": "x"})
        r = ddb.rulings()[0]
        self.assertEqual((r["who"], r["action"], r["section"], r["slot"]),
                         ("faisal", "drop", "events", 1))
        self.assertEqual(r["detail"], {"why": "x"})
        self.assertTrue(r["ts"])

    def test_issue_by_msg_and_set_issue(self):
        iid = ddb.open_issue("2026-09-03", 12)
        ddb.set_issue(iid, msg_id=555, status="preview", payload={"issue": "١٢"})
        row = ddb.issue_by_msg(555)
        self.assertEqual(row["id"], iid)
        self.assertEqual(row["status"], "preview")
        self.assertEqual(row["payload"], {"issue": "١٢"})
        self.assertIsNone(ddb.issue_by_msg(556))

    def test_items_and_recent_urls_for_novelty(self):
        a = ddb.open_issue("2026-08-27", 11)
        b = ddb.open_issue("2026-09-03", 12)
        ddb.set_items(a, [{"section": "events", "slot": 0, "ttl": "أ", "url": "https://x/a"}])
        ddb.set_items(b, [{"section": "events", "slot": 0, "ttl": "ب", "url": "https://x/b"},
                          {"section": "events", "slot": 1, "ttl": "ج", "url": "https://x/c", "state": "dropped"}])
        self.assertEqual(ddb.recent_issue_urls(6), {"https://x/a", "https://x/b"})
        self.assertEqual(ddb.recent_issue_urls(1), {"https://x/b"})
        self.assertEqual(len(ddb.items(b)), 2)


if __name__ == "__main__":
    unittest.main()
