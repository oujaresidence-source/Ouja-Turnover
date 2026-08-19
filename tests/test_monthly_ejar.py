# -*- coding: utf-8 -*-
"""
S6 — the data trust ladder.

THE LESSON THIS ENCODES: AirDNA was checked against reality and found wrong. It
scrapes calendars and infers. So an external number is never trusted by default;
it is calibrated against ours first, and what cannot prove it was TRANSACTED is
not evidence of a price, only of an ambition.

Run: python3 -m unittest tests.test_monthly_ejar
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import ejar                          # noqa: E402


class TierTest(unittest.TestCase):
    def test_our_own_history_is_gold(self):
        self.assertEqual(ejar.tier_for("ouja", "transacted"), "gold")

    def test_ejar_and_rega_are_silver(self):
        self.assertEqual(ejar.tier_for("sakani", "transacted"), "silver")
        self.assertEqual(ejar.tier_for("rega", "transacted"), "silver")

    def test_scrapers_are_bronze(self):
        for src in ("airdna", "bayut", "aqar", "عقار"):
            self.assertEqual(ejar.tier_for(src, "transacted"), "bronze")

    def test_an_asking_price_is_demoted_to_bronze_whatever_its_source(self):
        """An asking price is not a transaction. A landlord's hope is not a
        market rate, and no amount of source prestige changes that."""
        self.assertEqual(ejar.tier_for("sakani", "asking"), "bronze")
        self.assertEqual(ejar.tier_for("rega", "asking"), "bronze")

    def test_only_gold_may_set_a_price(self):
        self.assertTrue(ejar.may_set_price("gold"))
        self.assertFalse(ejar.may_set_price("silver"))
        self.assertFalse(ejar.may_set_price("bronze"))

    def test_silver_may_still_serve_as_the_annual_lease_reference(self):
        self.assertTrue(ejar.may_reference_annual("silver"))
        self.assertFalse(ejar.may_reference_annual("bronze"))

    def test_an_unknown_source_is_bronze_not_trusted(self):
        self.assertEqual(ejar.tier_for("some-new-site", "transacted"), "bronze")


class CalibrationTest(unittest.TestCase):
    def test_a_close_source_is_allowed(self):
        c = ejar.calibrate([100, 200, 300], [105, 195, 310])
        self.assertLessEqual(c["mape"], 0.10)
        self.assertEqual(c["trust_tier"], "allowed")
        self.assertEqual(c["bias_factor"], 1.0)

    def test_a_consistently_high_source_is_corrected_not_discarded(self):
        """Learning that a source runs ~18% high in a district is worth more than
        throwing it away."""
        ours = [100, 200, 300, 400]
        theirs = [118, 236, 354, 472]
        c = ejar.calibrate(ours, theirs)
        self.assertEqual(c["trust_tier"], "corrected")
        self.assertAlmostEqual(c["bias_factor"], 1 / 1.18, places=3)

    def test_applying_the_bias_factor_brings_it_back_to_ours(self):
        # FOUR pairs, not two: MIN_CALIB_PAIRS is 3, and the test directly above
        # asserts that two pairs is 'uncalibrated' with a bias of 1.0. Two pairs
        # here would have been asking this module to break its own rule.
        c = ejar.calibrate([100, 200, 300, 400], [118, 236, 354, 472])
        self.assertAlmostEqual(118 * c["bias_factor"], 100, places=2)

    def test_a_wild_source_is_blocked(self):
        c = ejar.calibrate([100, 200, 300], [400, 30, 900])
        self.assertGreater(c["mape"], 0.25)
        self.assertEqual(c["trust_tier"], "blocked")

    def test_a_blocked_cell_cannot_contribute_to_a_price(self):
        c = ejar.calibrate([100, 200, 300], [400, 30, 900])
        self.assertFalse(ejar.usable(c))

    def test_too_few_pairs_is_uncalibrated_not_allowed(self):
        """Two matching numbers is a coincidence, not a calibration."""
        c = ejar.calibrate([100], [101])
        self.assertEqual(c["trust_tier"], "uncalibrated")
        self.assertFalse(ejar.usable(c))

    def test_mismatched_lists_do_not_crash_or_silently_truncate_wrongly(self):
        c = ejar.calibrate([100, 200, 300], [105])
        self.assertEqual(c["n_obs"], 1)


class ReferenceTest(unittest.TestCase):
    FRESH = {"district": "الملقا", "bedrooms": 2, "annual_rent": 85000,
             "txn_count": 314, "source": "sakani", "obs_type": "transacted",
             "as_of": "2026-07-01"}

    def test_a_fresh_well_sampled_row_is_usable(self):
        r = ejar.reference(self.FRESH, today="2026-08-19")
        self.assertTrue(r["usable"])
        self.assertEqual(r["annual_rent"], 85000)
        self.assertEqual(r["warnings"], [])

    def test_a_row_older_than_180_days_is_stale_and_lowers_confidence(self):
        row = dict(self.FRESH, as_of="2025-12-01")
        r = ejar.reference(row, today="2026-08-19")
        self.assertIn("ejar_stale", r["warnings"])
        self.assertTrue(r["confidence_penalty"])

    def test_a_thin_district_is_flagged(self):
        """The published index itself uses 200 transactions as its threshold."""
        row = dict(self.FRESH, txn_count=40)
        r = ejar.reference(row, today="2026-08-19")
        self.assertIn("thin_district", r["warnings"])

    def test_an_asking_row_is_never_usable_as_a_reference(self):
        row = dict(self.FRESH, obs_type="asking")
        r = ejar.reference(row, today="2026-08-19")
        self.assertFalse(r["usable"])
        self.assertIn("asking_not_transacted", r["warnings"])

    def test_a_missing_row_is_unavailable_and_says_so(self):
        """THE IMPORTANT ONE. With no reference the owner gate is UNKNOWN — it
        must never read as satisfied. A silently-zero gate would drop the most
        important constraint out of max() and the screen would look fine."""
        r = ejar.reference(None, today="2026-08-19")
        self.assertFalse(r["usable"])
        self.assertIsNone(r["annual_rent"])
        self.assertIn("ejar_missing", r["warnings"])

    def test_a_nonsense_rent_is_refused(self):
        for bad in (0, -5000, None, "غالي"):
            row = dict(self.FRESH, annual_rent=bad)
            self.assertFalse(ejar.reference(row, today="2026-08-19")["usable"])


class OwnerNetTest(unittest.TestCase):
    def test_the_owners_annual_lease_position_is_net_of_what_they_still_pay(self):
        """An owner comparing paths compares what reaches their pocket, not the
        headline rent. Broker, void, maintenance and Ejar admin all come off."""
        net = ejar.owner_annual_net(85000)
        gross_after_pcts = 85000 * (1 - 0.025 - 0.05)
        self.assertAlmostEqual(net, gross_after_pcts - 4000 - 400)
        self.assertLess(net, 85000)

    def test_terms_match_the_owner_report_reference_data(self):
        """One set of lease terms in this codebase, not two that disagree."""
        import sys as _s
        _s.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "owner_report", "renderer"))
        import reference_data as rd
        self.assertEqual(ejar.DEFAULT_TERMS["broker_pct"], rd.EJAR["broker_pct"])
        self.assertEqual(ejar.DEFAULT_TERMS["vacancy_pct"], rd.EJAR["vacancy_pct"])
        self.assertEqual(ejar.DEFAULT_TERMS["owner_maintenance"], rd.EJAR["owner_maintenance"])
        self.assertEqual(ejar.DEFAULT_TERMS["admin_fees"], rd.EJAR["admin_fees"])

    def test_overriding_one_term_keeps_the_rest(self):
        net = ejar.owner_annual_net(85000, {"broker_pct": 0.0})
        self.assertGreater(net, ejar.owner_annual_net(85000))

    def test_no_rent_means_no_position(self):
        self.assertIsNone(ejar.owner_annual_net(None))
        self.assertIsNone(ejar.owner_annual_net(0))


if __name__ == "__main__":
    unittest.main()
