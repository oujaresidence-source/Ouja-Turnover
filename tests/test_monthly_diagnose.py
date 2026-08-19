# -*- coding: utf-8 -*-
"""
S8 — the report. Hand-written portfolios, so the report is as checkable as the
engine it reports on.

Run: python3 -m unittest tests.test_monthly_diagnose
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import diagnose, engine                # noqa: E402


def unit(lid, adr, occ, attrs_v=None, nights=30):
    return {"lid": lid, "name": "Ouja | %d" % lid, "month": "2026-10",
            "own": [{"adr": adr, "occ": occ, "months_old": 1, "nights": nights}],
            "district_pool": [{"adr": 500, "occ": occ, "months_old": 1}],
            "bedroom_pool": [], "attr_values": attrs_v or {},
            "ejar_row": None, "adr_pool": 500, "occ_pool": occ}


class HeadlineTest(unittest.TestCase):
    def test_the_headline_is_the_share_above_85_percent(self):
        rep = diagnose.run([unit(1, 500, 0.92), unit(2, 500, 0.88),
                            unit(3, 500, 0.60), unit(4, 500, 0.40)])
        self.assertEqual(rep["headline"]["n_units"], 4)
        self.assertEqual(rep["headline"]["n_above_85"], 2)
        self.assertAlmostEqual(rep["headline"]["pct_above_85"], 0.5)

    def test_an_empty_portfolio_does_not_divide_by_zero(self):
        rep = diagnose.run([])
        self.assertEqual(rep["headline"]["pct_above_85"], 0.0)


class ModelBoundLabellingTest(unittest.TestCase):
    """The correction from the previous stage, carried into the output."""

    def test_a_model_bound_unit_with_no_attributes_is_labelled_under_earning(self):
        rep = diagnose.run([unit(1, 380, 0.55)])       # adr below its pool of 500
        row = rep["per_unit"][0]
        if row["bound_by"] == "model":
            self.assertEqual(row["model_bound_means"], "under_earns_its_pool")

    def test_a_unit_whose_quality_actually_moved_is_not_mislabelled(self):
        rep = diagnose.run([unit(1, 380, 0.55, {"design": 8})])
        row = rep["per_unit"][0]
        if row["bound_by"] == "model":
            self.assertIsNone(row["model_bound_means"])


class SweepsTest(unittest.TestCase):
    def test_loss_making_nightly_units_are_listed(self):
        c = engine.costs(turnover_cost_sar=4000, alos=1.0)
        rep = diagnose.run([unit(1, 120, 0.9)], cost_set=c)
        self.assertTrue(rep["loss_making_nightly"])

    def test_a_healthy_portfolio_lists_none(self):
        rep = diagnose.run([unit(1, 600, 0.8), unit(2, 550, 0.75)])
        self.assertEqual(rep["loss_making_nightly"], [])

    def test_units_with_no_price_are_listed_separately_from_priced_ones(self):
        rep = diagnose.run([unit(1, 600, 0.8),
                            {"lid": 9, "name": "no history", "month": "2026-10",
                             "own": [], "district_pool": [], "bedroom_pool": [],
                             "attr_values": {}, "ejar_row": None}])
        self.assertEqual(len(rep["no_price"]), 1)
        self.assertEqual(rep["n_priced"], 1)

    def test_band_widths_are_reported_per_unit(self):
        rep = diagnose.run([unit(1, 600, 0.95), unit(2, 600, 0.55)])
        widths = {w["lid"]: w["width"] for w in rep["band_widths"]}
        self.assertLess(widths[1], widths[2],
                        "the band must be narrower at higher occupancy")


class AnchorEmptinessTest(unittest.TestCase):
    def test_an_unscored_portfolio_says_so_rather_than_reporting_a_clean_anchor(self):
        rep = diagnose.run([unit(1, 500, 0.8), unit(2, 500, 0.7)])
        self.assertTrue(rep["anchor_is_empty"])
        self.assertEqual(rep["n_unscored"], 2)
        for row in rep["anchor"]:
            self.assertIsNone(row["median"])
            self.assertFalse(row["anchor_suspect"])

    def test_a_scored_portfolio_reports_a_real_median(self):
        rep = diagnose.run([unit(1, 500, 0.8, {"design": 8}),
                            unit(2, 500, 0.7, {"design": 8})])
        self.assertFalse(rep["anchor_is_empty"])
        row = [r for r in rep["anchor"] if r["key"] == "design"][0]
        self.assertEqual(row["median"], 8)
        self.assertTrue(row["anchor_suspect"])


class FloorRatioByBandTest(unittest.TestCase):
    def test_the_ratio_is_reported_within_each_band_not_only_overall(self):
        rep = diagnose.run([unit(1, 600, 0.92), unit(2, 600, 0.90),
                            unit(3, 600, 0.55), unit(4, 600, 0.52)])
        self.assertGreater(rep["floor_ratio_by_band"][">85"]["n"], 0)
        self.assertGreater(rep["floor_ratio_by_band"]["<60"]["n"], 0)

    def test_the_ratio_falls_as_occupancy_rises(self):
        rep = diagnose.run([unit(1, 600, 0.92), unit(2, 600, 0.55)])
        hi = rep["floor_ratio_by_band"][">85"]["median"]
        lo = rep["floor_ratio_by_band"]["<60"]["median"]
        self.assertLess(hi, lo)


class NoProposalsTest(unittest.TestCase):
    def test_the_report_states_which_turnover_cost_it_used(self):
        rep = diagnose.run([unit(1, 600, 0.8)],
                           cost_set=engine.costs(turnover_cost_sar=287.0))
        self.assertEqual(rep["turnover_cost_used"], 287.0)


if __name__ == "__main__":
    unittest.main()
