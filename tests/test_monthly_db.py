# -*- coding: utf-8 -*-
"""
S3 — storage. The tests that matter here are about what the schema REFUSES.

    * unanswered stays unanswered — never coerced to a middle score
    * an override with no reason is refused, not silently accepted
    * a frozen quote stays frozen when the model moves underneath it

Run: python3 -m unittest tests.test_monthly_db
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                       # noqa: E402
from monthly import attrs, db                     # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="monthly_db_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_for_tests()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class UnansweredTest(_Base):
    def test_a_unit_with_nothing_stored_has_16_unanswered(self):
        self.assertEqual(db.unit_attrs(999), {})
        self.assertEqual(attrs.unanswered(db.unit_attrs(999)), 16)

    def test_unanswered_contributes_exactly_one(self):
        """The whole three-state rule in one assertion: a missing answer must not
        move the price by a hair in either direction."""
        for k in attrs.keys():
            self.assertEqual(attrs.multiplier(k, None), 1.0)

    def test_stored_null_reads_back_as_unanswered_not_as_zero(self):
        db.set_attr(101, "majlis", None, actor="tester")
        self.assertNotIn("majlis", db.unit_attrs(101))
        self.assertEqual(attrs.multiplier("majlis", db.unit_attrs(101).get("majlis")), 1.0)

    def test_clearing_an_attribute_is_possible(self):
        db.set_attr(102, "design", 8, actor="tester")
        self.assertEqual(db.unit_attrs(102)["design"], "8")
        db.set_attr(102, "design", None, actor="tester")
        self.assertNotIn("design", db.unit_attrs(102))

    def test_provenance_is_recorded(self):
        db.set_attr(103, "sqm", 145, actor="faisal")
        d = db.unit_attrs_detailed(103)["sqm"]
        self.assertEqual(d["scored_by"], "faisal")
        self.assertTrue(d["scored_at"])


class EjarTest(_Base):
    def test_latest_row_wins_but_history_is_kept(self):
        db.ejar_upsert("الملقا", 85000, "2026-01-01", bedrooms=2, txn_count=310)
        db.ejar_upsert("الملقا", 92000, "2026-07-01", bedrooms=2, txn_count=344)
        self.assertEqual(db.ejar_latest("الملقا", bedrooms=2)["annual_rent"], 92000)
        self.assertEqual(len(db.ejar_all()), 2)

    def test_obs_type_is_stored_because_asking_is_not_transacted(self):
        db.ejar_upsert("النرجس", 120000, "2026-06-01", bedrooms=3, obs_type="asking")
        self.assertEqual(db.ejar_latest("النرجس", bedrooms=3)["obs_type"], "asking")

    def test_unknown_cell_is_none_not_zero(self):
        self.assertIsNone(db.ejar_latest("حي ما موجود", bedrooms=1))


class OverrideTest(_Base):
    def _quote(self):
        return db.save_quote(555, "2026-10", 11800, 11800, "owner_gate", "high",
                             attrs.BETA_VERSION, {"price": 11800}, created_by="faisal")

    def test_override_without_a_reason_is_refused(self):
        qid = self._quote()
        with self.assertRaises(db.ReasonRequired):
            db.log_override(qid, 0.0, 0.05, "", actor="faisal")
        with self.assertRaises(db.ReasonRequired):
            db.log_override(qid, 0.0, 0.05, "   ", actor="faisal")
        self.assertEqual(db.overrides_for(qid), [])
        self.assertEqual(db.get_quote(qid)["final_price"], 11800)

    def test_override_with_a_reason_moves_the_final_price_only(self):
        qid = self._quote()
        db.log_override(qid, 0.0, 0.05, "المالك طلب هامش أعلى", actor="faisal")
        q = db.get_quote(qid)
        self.assertEqual(q["price"], 11800)              # the computed number is untouched
        self.assertAlmostEqual(q["final_price"], 12390)  # only the final moves
        self.assertEqual(db.overrides_for(qid)[0]["reason"], "المالك طلب هامش أعلى")


class FrozenQuoteTest(_Base):
    def test_a_saved_quote_does_not_change_when_the_model_does(self):
        """August's quote must still explain itself in November, in August's
        terms — not recomputed against whatever the betas say by then."""
        payload = {"price": 11800, "bound_by": "owner_gate",
                   "multipliers": [{"key": "sqm", "beta": 0.25}]}
        qid = db.save_quote(777, "2026-10", 11800, 11800, "owner_gate", "high",
                            1, payload, created_by="faisal")
        payload["price"] = 99999                      # the caller mutates its own dict
        payload["multipliers"][0]["beta"] = 0.99
        stored = db.get_quote(qid)["payload"]
        self.assertEqual(stored["price"], 11800)
        self.assertEqual(stored["multipliers"][0]["beta"], 0.25)

    def test_payload_survives_arabic_intact(self):
        qid = db.save_quote(778, "2026-10", 100, 100, "floor", "low", 1,
                            {"note": "رفعناه عشان يبقى دخل المالك أعلى"})
        self.assertIn("المالك", json.dumps(db.get_quote(qid)["payload"], ensure_ascii=False))


class OutcomeTest(_Base):
    def test_paired_obs_starts_at_zero_and_counts_only_booked_with_a_price(self):
        self.assertEqual(db.paired_obs_count(), 0)
        q1 = db.save_quote(1, "2026-10", 100, 100, "floor", "low", 1, {})
        q2 = db.save_quote(2, "2026-10", 100, 100, "floor", "low", 1, {})
        db.record_outcome(q1, booked=False)
        self.assertEqual(db.paired_obs_count(), 0)
        db.record_outcome(q2, booked=True, booked_price=11500)
        self.assertEqual(db.paired_obs_count(), 1)

    def test_model_is_uncalibrated_until_the_evidence_exists(self):
        self.assertLess(db.paired_obs_count(), attrs.CALIBRATED_AT)


if __name__ == "__main__":
    unittest.main()


class EjarSchemaTest(_Base):
    """The S3 schema had two defects that only real data exposed."""

    def test_five_unit_types_in_one_district_are_five_rows_not_a_collision(self):
        for ut, rent in (("شقة", 54396), ("استديو", 50433), ("دوبلاكس", 72015),
                         ("فله", 154432), ("دور", 66874)):
            db.ejar_upsert("القيروان", rent, "2026-06-30", bedrooms=None, unit_type=ut)
        self.assertEqual(len(db.ejar_all()), 5)
        self.assertEqual(db.ejar_latest("القيروان", unit_type="فله")["annual_rent"], 154432)

    def test_reloading_the_same_cell_updates_instead_of_duplicating(self):
        """SQLite treats NULLs in a PRIMARY KEY as DISTINCT, so the S3 shape would
        have added five fresh rows on every re-run of the seed."""
        for _ in range(3):
            db.ejar_upsert("القيروان", 54396, "2026-06-30", bedrooms=None, unit_type="شقة")
        self.assertEqual(len(db.ejar_all()), 1)

    def test_all_bedrooms_and_three_bedrooms_are_different_cells(self):
        """Asking for 3BR must never be answered with the all-bedrooms average."""
        db.ejar_upsert("الملقا", 51213, "2026-06-30", bedrooms=None, unit_type="شقة")
        db.ejar_upsert("الملقا", 54845, "2026-06-30", bedrooms=3, unit_type="شقة")
        self.assertEqual(len(db.ejar_all()), 2)
        self.assertEqual(db.ejar_latest("الملقا", bedrooms=None)["annual_rent"], 51213)
        self.assertEqual(db.ejar_latest("الملقا", bedrooms=3)["annual_rent"], 54845)

    def test_the_seed_loads_and_is_idempotent(self):
        n = db.ejar_load_seed()
        self.assertEqual(n, 26)
        self.assertEqual(len(db.ejar_all()), 26)
        db.ejar_load_seed()
        self.assertEqual(len(db.ejar_all()), 26)

    def test_every_seeded_row_keeps_its_provenance_and_uncertainty(self):
        db.ejar_load_seed()
        for r in db.ejar_all():
            self.assertEqual(r["source"], "sakani_rei")
            self.assertEqual(r["obs_type"], "transacted")
            self.assertEqual(r["period"], "2026-01/2026-08")
            self.assertEqual(r["as_of"], "2026-06-30")
            self.assertIn("شهري", r["note"])       # the toggle uncertainty, kept
            self.assertTrue(r["entered_by"])

    def test_price_ranges_are_flagged_as_a_follow_up_not_silently_absent(self):
        db.ejar_load_seed()
        self.assertEqual(len(db.ejar_missing_ranges()), 26)
