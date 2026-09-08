# -*- coding: utf-8 -*-
"""
Two numbers, never one.

    compliance_pct = available / (available + missing)        quality of what was SEEN
    inspected_pct  = (available + missing) / denominator      how much of the unit was covered

A round with inspected_pct < 100 may never be exported as evidence, and the denominator
follows has_pool (61 / 67). Engine only — plain dicts, no DB, no web.

Run: python3 -m unittest tests.test_mot_score
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mot import catalogue as C, engine  # noqa: E402


def results_for(has_pool, state="available", override=None):
    r = {c["key"]: {"state": state} for c in C.components(has_pool)}
    for k, v in (override or {}).items():
        r[k] = {"state": v}
    return r


class TestDenominator(unittest.TestCase):
    def test_follows_has_pool(self):
        self.assertEqual(engine.score({}, False)["denominator"], 60)
        self.assertEqual(engine.score({}, True)["denominator"], 66)
        self.assertEqual(engine.score({}, False, "2026-09")["denominator"], 62)   # 61 + the later-added qibla marker

    def test_pool_results_ignored_when_unit_has_no_pool(self):
        r = results_for(False)
        r["c46.pool_rescue"] = {"state": "missing"}      # stray row from a wrong pool flag
        s = engine.score(r, False)
        self.assertEqual(s["missing"], 0)
        self.assertEqual(s["compliance_pct"], 100.0)


class TestTwoPercentages(unittest.TestCase):
    def test_all_available(self):
        s = engine.score(results_for(False), False)
        self.assertEqual((s["compliance_pct"], s["inspected_pct"]), (100.0, 100.0))

    def test_partial_inspection_keeps_the_two_apart(self):
        # 40 available, 10 missing, 10 unchecked (60 total)
        keys = [c["key"] for c in C.components(False)]
        r = {}
        for i, k in enumerate(keys):
            r[k] = {"state": "available" if i < 40 else ("missing" if i < 50 else "unchecked")}
        s = engine.score(r, False)
        self.assertEqual(s["available"], 40)
        self.assertEqual(s["missing"], 10)
        self.assertEqual(s["not_inspected"], 10)
        self.assertEqual(s["compliance_pct"], 80.0)           # 40 / 50, NOT 40 / 60
        self.assertEqual(s["inspected_pct"], round(50 / 60 * 100, 1))

    def test_nothing_seen_is_not_zero_compliance(self):
        s = engine.score({}, False)
        self.assertIsNone(s["compliance_pct"])
        self.assertEqual(s["inspected_pct"], 0.0)

    def test_missing_rows_count_as_unchecked(self):
        r = {"c04.price_board": {"state": "missing"}}
        s = engine.score(r, False)
        self.assertEqual(s["not_inspected"], 59)


class TestEvidenceGate(unittest.TestCase):
    def test_partial_round_cannot_be_evidence(self):
        r = results_for(False, override={"c10.iron": "unchecked"})
        ok, why = engine.can_export_evidence({"closed_at": "2026-09-06T10:00:00"}, r, False)
        self.assertFalse(ok)
        self.assertIn("1", why)

    def test_open_round_cannot_be_evidence(self):
        ok, _ = engine.can_export_evidence({"closed_at": None}, results_for(False), False)
        self.assertFalse(ok)

    def test_abandoned_round_cannot_be_evidence(self):
        ok, _ = engine.can_export_evidence({"closed_at": "x", "note": "abandoned"},
                                           results_for(False), False)
        self.assertFalse(ok)

    def test_complete_closed_round_can(self):
        ok, why = engine.can_export_evidence({"closed_at": "x"}, results_for(False), False)
        self.assertTrue(ok, why)


class TestBlockers(unittest.TestCase):
    def test_structural_failures_listed(self):
        r = results_for(False, override={"c03.elevator": "missing", "c10.iron": "missing"})
        b = engine.blockers(r, False)
        self.assertEqual([x["key"] for x in b], ["c03.elevator"])


class TestDefaultQty(unittest.TestCase):
    meta = {"bedrooms": 2, "bathrooms": 3, "beds": 3}

    def test_hints(self):
        self.assertEqual(engine.default_qty(C.by_key("c09.bin"), self.meta), 2)
        self.assertEqual(engine.default_qty(C.by_key("c30.shampoo"), self.meta), 3)
        self.assertEqual(engine.default_qty(C.by_key("c21.mattress"), self.meta), 3)
        self.assertEqual(engine.default_qty(C.by_key("c16.tv"), self.meta), 1)

    def test_beds_fall_back_to_bedrooms_then_one(self):
        self.assertEqual(engine.default_qty(C.by_key("c21.mattress"), {"bedrooms": 2}), 2)
        self.assertEqual(engine.default_qty(C.by_key("c21.mattress"), {}), 1)

    def test_studio_has_at_least_one_of_everything(self):
        self.assertEqual(engine.default_qty(C.by_key("c09.bin"), {"bedrooms": 0}), 1)


if __name__ == "__main__":
    unittest.main()
