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


class PredictionsOnRecordTest(unittest.TestCase):
    """Recorded before the endpoint ever ran. If we rationalise whatever the
    numbers say, the diagnosis is worthless."""

    def test_every_report_carries_the_predictions(self):
        rep = diagnose.run([unit(1, 500, 0.8)])
        self.assertTrue(rep["predictions"]["stated_before_any_live_run"])
        self.assertEqual(rep["predictions"]["stated_on"], "2026-08-19")

    def test_all_three_months_are_predicted(self):
        p = diagnose.PREDICTIONS["pct_above_85"]
        for m in ("2026-08", "2026-10", "2027-01"):
            lo, hi = p[m]
            self.assertLess(lo, hi)

    def test_the_seasonal_prediction_is_directional_not_a_hedge(self):
        p = diagnose.PREDICTIONS["pct_above_85"]
        self.assertLess(p["2026-08"][1], p["2027-01"][0],
                        "August and January must be predicted as disjoint ranges "
                        "or the prediction cannot be wrong")


class FallbackVisibilityTest(unittest.TestCase):
    """The failure that would look like a finding."""

    def test_a_portfolio_mostly_on_the_pool_is_flagged_as_untrustworthy(self):
        thin = [{"lid": i, "name": "u", "month": "2026-10", "own": [],
                 "district_pool": [{"adr": 500, "occ": 0.8, "months_old": 1}],
                 "bedroom_pool": [], "attr_values": {}, "ejar_row": None,
                 "adr_pool": 500, "occ_pool": 0.8} for i in range(10)]
        rep = diagnose.run(thin)
        self.assertEqual(rep["headline"]["units_on_fallback"], 10)
        self.assertEqual(rep["headline"]["units_with_own_history"], 0)
        self.assertFalse(rep["headline"]["trustworthy"])
        kinds = [w["kind"] for w in rep["headline"]["warnings"]]
        self.assertIn("on_fallback", kinds)

    def test_a_portfolio_on_its_own_history_is_trustworthy(self):
        rep = diagnose.run([unit(i, 500, 0.8) for i in range(10)])
        self.assertEqual(rep["headline"]["units_with_own_history"], 10)
        self.assertTrue(rep["headline"]["trustworthy"])
        self.assertEqual(rep["headline"]["warnings"], [])

    def test_the_split_sits_in_the_headline_not_the_detail(self):
        rep = diagnose.run([unit(1, 500, 0.8)])
        for k in ("units_with_own_history", "units_on_fallback", "pct_own_history"):
            self.assertIn(k, rep["headline"])


class RenderTextTest(unittest.TestCase):
    def _multi(self):
        r = diagnose.run([unit(1, 500, 0.92), unit(2, 500, 0.55)])
        r["month"] = "2026-10"
        return {"months": [r], "compare": [
            {"month": "2026-10", "pct_above_85": r["headline"]["pct_above_85"],
             "ceiling_share": r["segmented"]["overall"]["ceiling_share"],
             "floor_ratio_median": r["floor_ratio"]["median"],
             "no_price": 0, "trustworthy": True}]}

    def test_the_trust_check_is_printed_before_the_headline(self):
        txt = diagnose.render_text(self._multi())
        self.assertLess(txt.index("TRUST CHECK FIRST"), txt.index("HEADLINE"))

    def test_the_predictions_are_printed_above_everything(self):
        txt = diagnose.render_text(self._multi())
        self.assertLess(txt.index("PREDICTIONS ON RECORD"), txt.index("TRUST CHECK"))

    def test_no_stray_percent_escapes_reach_the_reader(self):
        self.assertNotIn("%%", diagnose.render_text(self._multi()))

    def test_an_untrustworthy_month_is_shouted_not_whispered(self):
        thin = [{"lid": i, "name": "u", "month": "2026-10", "own": [],
                 "district_pool": [{"adr": 500, "occ": 0.8, "months_old": 1}],
                 "bedroom_pool": [], "attr_values": {}, "ejar_row": None,
                 "adr_pool": 500, "occ_pool": 0.8} for i in range(5)]
        r = diagnose.run(thin); r["month"] = "2026-10"
        txt = diagnose.render_text({"months": [r], "compare": []})
        self.assertIn("NOT TRUSTWORTHY", txt)

    def test_a_failed_month_reports_its_error_rather_than_vanishing(self):
        txt = diagnose.render_text({"months": [{"month": "2027-01",
                                                "error": "RuntimeError: boom"}],
                                    "compare": [{"month": "2027-01", "error": "x"}]})
        self.assertIn("ERROR", txt)
        self.assertIn("2027-01", txt)


class TwoDifferentFailuresTest(unittest.TestCase):
    """'on fallback' and 'no price' mean opposite things and the first version of
    the trust check printed the same sentence for both — which sent a live
    diagnosis chasing a data-matching bug that was really a missing-metadata bug."""

    def _no_history(self, n):
        return [{"lid": i, "name": "u%d" % i, "month": "2026-10", "own": [],
                 "district_pool": [], "bedroom_pool": [], "attr_values": {},
                 "ejar_row": None} for i in range(n)]

    def test_no_price_is_reported_separately_from_fallback(self):
        rep = diagnose.run(self._no_history(10))
        h = rep["headline"]
        self.assertEqual(h["units_with_no_price"], 10)
        self.assertEqual(h["units_on_fallback"], 0)

    def test_the_warning_names_no_price_not_fallback(self):
        rep = diagnose.run(self._no_history(10))
        kinds = [w["kind"] for w in rep["headline"]["warnings"]]
        self.assertIn("no_price", kinds)
        self.assertNotIn("on_fallback", kinds)

    def test_the_fallback_warning_only_fires_when_the_pool_path_ran(self):
        pooled = [{"lid": i, "name": "u", "month": "2026-10", "own": [],
                   "district_pool": [{"adr": 500, "occ": 0.8, "months_old": 1}],
                   "bedroom_pool": [], "attr_values": {}, "ejar_row": None,
                   "adr_pool": 500, "occ_pool": 0.8} for i in range(10)]
        kinds = [w["kind"] for w in diagnose.run(pooled)["headline"]["warnings"]]
        self.assertIn("on_fallback", kinds)
        self.assertNotIn("no_price", kinds)

    def test_a_no_price_unit_renders_occupancy_as_a_dash_not_zero(self):
        r = diagnose.run(self._no_history(3)); r["month"] = "2026-10"
        txt = diagnose.render_text({"months": [r], "compare": []})
        self.assertIn("occ   —", txt)
        self.assertNotIn("occ 0.00", txt)


class VerdictSuppressionTest(unittest.TestCase):
    """The verdict was reading data completeness as seasonality: January said
    'inconclusive' only because 41 units matched where August matched 20."""

    def _no_history(self, n):
        return [{"lid": i, "name": "u%d" % i, "month": "2026-10", "own": [],
                 "district_pool": [], "bedroom_pool": [], "attr_values": {},
                 "ejar_row": None} for i in range(n)]

    def test_a_broken_sample_suppresses_the_verdict(self):
        rep = diagnose.run(self._no_history(10))
        seg = rep["segmented"]
        self.assertTrue(seg["verdict_suppressed"])
        self.assertIn("SUPPRESSED", seg["verdict"])

    def test_the_suppressed_verdict_is_kept_for_later_not_destroyed(self):
        rep = diagnose.run(self._no_history(10))
        self.assertIn("verdict_would_have_been", rep["segmented"])

    def test_a_healthy_sample_still_gets_its_verdict(self):
        rep = diagnose.run([unit(i, 500, 0.8) for i in range(10)])
        self.assertFalse(rep["segmented"]["verdict_suppressed"])
        self.assertNotIn("SUPPRESSED", rep["segmented"]["verdict"])


class SuppressionCoversTheWholeTrustCheckTest(unittest.TestCase):
    """A run that was 68% priced from district pools printed *** NOT TRUSTWORTHY
    *** at the top and a confident verdict underneath it. Both cannot be true,
    and the confident one is the line people quote."""

    def _pooled(self, n):
        return [{"lid": i, "name": "u", "month": "2026-10", "own": [],
                 "district_pool": [{"adr": 500, "occ": 0.9, "months_old": 1}],
                 "bedroom_pool": [], "attr_values": {}, "ejar_row": None,
                 "adr_pool": 500, "occ_pool": 0.9} for i in range(n)]

    def test_a_pool_heavy_run_suppresses_the_verdict_too(self):
        rep = diagnose.run(self._pooled(10))
        self.assertFalse(rep["headline"]["trustworthy"])
        self.assertTrue(rep["segmented"]["verdict_suppressed"])
        self.assertIn("district pools", rep["segmented"]["verdict"])

    def test_the_suppressed_verdict_is_still_kept(self):
        rep = diagnose.run(self._pooled(10))
        self.assertIn("verdict_would_have_been", rep["segmented"])

    def test_trustworthy_and_suppressed_never_disagree(self):
        for units in (self._pooled(10), [unit(i, 500, 0.8) for i in range(10)]):
            rep = diagnose.run(units)
            self.assertEqual(rep["headline"]["trustworthy"],
                             not rep["segmented"]["verdict_suppressed"])
