# -*- coding: utf-8 -*-
"""
«طلبات سام» golden set — 122 real Sam messages from the history study, redacted, hand-labelled.

Offline (always): the set is big enough and balanced (≥60, ≥25 requests, ≥25 not), every label
is well-formed, and the recorded baseline produces the precision/threshold table.
Live (only with ANTHROPIC_API_KEY + RRDESK_LIVE_EVAL=1): the real Haiku classifier is graded
on the same set and the table is printed — the number the owner uses to switch detection to
'auto'. Inside the bot the same run happens with /rrdesk-study.

Run: python3 -m unittest tests.test_rrdesk_golden
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                     # noqa: E402
from rrdesk import db, engine, evalset          # noqa: E402


def table_text(res):
    rows = ["t=%.2f n=%3d precision=%s recall=%s" % (
        r["t"], r["n"], "—" if r["precision"] is None else "%.2f" % r["precision"],
        "—" if r["recall"] is None else "%.2f" % r["recall"]) for r in res["table"]]
    return chr(10).join(rows + ["→ mode=%s threshold=%s" % (res["mode"], res["threshold"])])


class Golden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = evalset.load()

    def test_size_and_balance(self):
        n = len(self.rows)
        yes = sum(1 for r in self.rows if r["label"]["is_request"])
        self.assertGreaterEqual(n, 60)
        self.assertGreaterEqual(yes, 25)
        self.assertGreaterEqual(n - yes, 25)
        self.assertEqual(len({r["id"] for r in self.rows}), n)

    def test_labels_are_well_formed(self):
        for r in self.rows:
            lab = r["label"]
            self.assertIn(lab["kind"], ("request", "followup", "not_request"))
            self.assertEqual(lab["is_request"], lab["kind"] == "request")
            if lab["is_request"]:
                self.assertTrue(lab["asks"])
                self.assertTrue(set(lab["asks"]) <= set(engine.ASKS), lab)
            self.assertTrue(r["text"].strip())

    def test_followups_are_not_new_requests(self):
        fu = [r for r in self.rows if r["label"]["kind"] == "followup"]
        self.assertGreaterEqual(len(fu), 8)
        self.assertTrue(all(not r["label"]["is_request"] for r in fu))

    def test_baseline_table(self):
        res = evalset.baseline_table(self.rows)
        self.assertIn(res["mode"], ("auto", "confirm", "explicit"))
        self.assertTrue(res["table"])
        print(chr(10) + "[golden] heuristic baseline (no model):" + chr(10) + table_text(res))

    @unittest.skipUnless(os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("RRDESK_LIVE_EVAL") == "1",
                         "live eval needs ANTHROPIC_API_KEY + RRDESK_LIVE_EVAL=1")
    def test_live_haiku(self):
        bdb.set_db_path_for_tests(os.path.join(tempfile.mkdtemp(), "brain.db"))
        db.reset_init_cache()
        res = evalset.run_live()
        print(chr(10) + "[golden] live Haiku:" + chr(10) + table_text(res))
        self.assertGreater(res["n"], 50)


if __name__ == "__main__":
    unittest.main()
