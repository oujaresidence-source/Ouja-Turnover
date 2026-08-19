# -*- coding: utf-8 -*-
"""
S4 — the forecast and the FLOOR. Hand-written inputs only; this module never
touches a network, a database or a clock, which is the whole reason its numbers
can be argued with.

THE FLOOR IS THE NUMBER THAT ENDS A LOWBALL CONVERSATION. Below it we earn less
than we would by simply letting the unit nightly. It is never a suggestion, so
these tests care most about it being impossible to quietly under-state.

Run: python3 -m unittest tests.test_monthly_engine
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import engine                        # noqa: E402


def obs(adr, occ, months_old, nights=30):
    return {"adr": adr, "occ": occ, "months_old": months_old, "nights": nights}


class FreshnessTest(unittest.TestCase):
    def test_this_month_counts_fully(self):
        self.assertEqual(engine.freshness_weight(0), 1.0)

    def test_six_months_counts_half(self):
        self.assertAlmostEqual(engine.freshness_weight(6), 0.5)

    def test_a_year_ago_counts_a_quarter(self):
        self.assertAlmostEqual(engine.freshness_weight(12), 0.25)

    def test_weight_never_goes_negative_or_grows_with_age(self):
        prev = 2.0
        for k in range(0, 40):
            w = engine.freshness_weight(k)
            self.assertGreater(w, 0.0)
            self.assertLess(w, prev)
            prev = w


class ForecastTest(unittest.TestCase):
    def test_a_single_observation_is_returned_as_is(self):
        f = engine.forecast([obs(500, 0.8, 0)])
        self.assertAlmostEqual(f["adr"], 500)
        self.assertAlmostEqual(f["occ"], 0.8)

    def test_recent_months_outweigh_old_ones(self):
        """Two observations, equal in every way except age. The forecast must sit
        nearer the recent one — if it lands on the midpoint the weighting is
        doing nothing."""
        f = engine.forecast([obs(600, 0.9, 0), obs(400, 0.5, 12)])
        self.assertGreater(f["adr"], 520)       # midpoint would be 500
        self.assertLess(f["adr"], 600)

    def test_no_observations_is_none_not_zero(self):
        self.assertIsNone(engine.forecast([]))
        self.assertIsNone(engine.forecast(None))

    def test_occupancy_is_never_forecast_above_one(self):
        f = engine.forecast([obs(500, 1.4, 0)])
        self.assertLessEqual(f["occ"], 1.0)


class FallbackLadderTest(unittest.TestCase):
    def test_own_history_wins_when_it_is_thick_enough(self):
        r = engine.forecast_unit(own=[obs(500, 0.8, 1, nights=30)],
                                 district=[obs(900, 0.9, 1)], bedroom=[obs(300, 0.5, 1)])
        self.assertEqual(r["basis"], "own_history")
        self.assertAlmostEqual(r["adr"], 500)

    def test_thin_own_history_falls_to_the_district_pool(self):
        r = engine.forecast_unit(own=[obs(500, 0.8, 1, nights=3)],
                                 district=[obs(900, 0.9, 1)], bedroom=[obs(300, 0.5, 1)])
        self.assertEqual(r["basis"], "district_pool")

    def test_the_pool_is_adjusted_by_this_units_quality(self):
        """A pool average describes the pool, not this flat. Multiplying by the
        unit's own quality index is what makes it about this flat."""
        r = engine.forecast_unit(own=[], district=[obs(1000, 0.8, 1)], bedroom=[],
                                 quality_index=1.2)
        self.assertAlmostEqual(r["adr"], 1200)

    def test_bedroom_pool_is_the_last_rung(self):
        r = engine.forecast_unit(own=[], district=[], bedroom=[obs(700, 0.7, 2)])
        self.assertEqual(r["basis"], "bedroom_pool")

    def test_nothing_anywhere_returns_insufficient_and_no_numbers(self):
        """A blank beats a confident wrong number. There must be no adr to
        accidentally render."""
        r = engine.forecast_unit(own=[], district=[], bedroom=[])
        self.assertEqual(r["basis"], "insufficient")
        self.assertIsNone(r["adr"])
        self.assertIsNone(r["occ"])

    def test_own_obs_count_is_reported_for_the_confidence_chip(self):
        r = engine.forecast_unit(own=[obs(500, 0.8, 1, nights=14),
                                      obs(520, 0.7, 2, nights=9)],
                                 district=[], bedroom=[])
        self.assertEqual(r["own_obs"], 23)


class NightlyEconomicsTest(unittest.TestCase):
    def setUp(self):
        self.costs = engine.costs(turnover_cost_sar=140, alos=3.0,
                                  blended_channel_pct=0.15)

    def test_gross_is_thirty_nights_at_the_forecast(self):
        e = engine.nightly_economics(500, 0.8, self.costs)
        self.assertAlmostEqual(e["nightly_gross"], 12000)      # 30 * 500 * 0.8

    def test_stays_come_from_length_of_stay_not_a_guess(self):
        e = engine.nightly_economics(500, 0.8, self.costs)
        self.assertAlmostEqual(e["stays"], 8.0)                # 24 nights / 3.0

    def test_every_stay_costs_a_turnover(self):
        e = engine.nightly_economics(500, 0.8, self.costs)
        self.assertAlmostEqual(e["turnover_cost_tot"], 1120)   # 8 * 140

    def test_net_is_gross_less_turnover_and_commission(self):
        e = engine.nightly_economics(500, 0.8, self.costs)
        self.assertAlmostEqual(e["channel_fee_tot"], 1800)     # 12000 * 0.15
        self.assertAlmostEqual(e["nightly_net"], 12000 - 1120 - 1800)

    def test_zero_occupancy_produces_no_stays_and_no_negative_net(self):
        e = engine.nightly_economics(500, 0.0, self.costs)
        self.assertEqual(e["stays"], 0)
        self.assertEqual(e["nightly_net"], 0)


class FloorTest(unittest.TestCase):
    def setUp(self):
        self.costs = engine.costs(turnover_cost_sar=140, alos=3.0,
                                  blended_channel_pct=0.15, utilities_month=350,
                                  consumables_month=120, wifi_month=150,
                                  min_margin_sar=650)

    def test_floor_covers_the_nightly_net_plus_monthly_cost_plus_margin(self):
        f = engine.floor_price(500, 0.8, self.costs)
        nightly_net = 12000 - 1120 - 1800
        monthly_direct = 140 + 350 + 120 + 150
        self.assertAlmostEqual(f["floor"], nightly_net + monthly_direct + 650)

    def test_the_monthly_path_pays_for_exactly_one_clean(self):
        """The whole reason a monthly let can be cheaper per night: one turnover,
        not eight."""
        f = engine.floor_price(500, 0.8, self.costs)
        self.assertAlmostEqual(f["monthly_direct_cost"], 140 + 350 + 120 + 150)

    def test_the_waterfall_sums_exactly_to_the_floor(self):
        """A column of numbers shown to an owner must add up to the number at the
        top of it. This is the assertion that keeps the screen honest."""
        f = engine.floor_price(500, 0.8, self.costs)
        self.assertAlmostEqual(sum(c["sar"] for c in f["components"]), f["floor"])

    def test_costs_that_the_nightly_path_pays_are_shown_as_negative(self):
        f = engine.floor_price(500, 0.8, self.costs)
        by = {c["key"]: c["sar"] for c in f["components"]}
        self.assertLess(by["turnover_cost"], 0)
        self.assertLess(by["channel_fee"], 0)
        self.assertGreater(by["nightly_gross"], 0)
        self.assertGreater(by["margin"], 0)

    def test_every_component_is_labelled_in_both_languages(self):
        f = engine.floor_price(500, 0.8, self.costs)
        for c in f["components"]:
            self.assertTrue(c["label_ar"].strip())
            self.assertTrue(c["label_en"].strip())

    def test_a_higher_margin_requirement_raises_the_floor(self):
        low = engine.floor_price(500, 0.8, engine.costs(min_margin_sar=100))
        high = engine.floor_price(500, 0.8, engine.costs(min_margin_sar=900))
        self.assertAlmostEqual(high["floor"] - low["floor"], 800)

    def test_the_waterfall_still_sums_when_nightly_letting_loses_money(self):
        """A cheap unit with short stays and heavy turnover can cost more to let
        nightly than it earns. nightly_net clamps at zero (we would simply not
        do it), and the waterfall MUST clamp with it — otherwise the column on
        screen shows a negative total under a positive headline."""
        c = engine.costs(turnover_cost_sar=400, alos=1.5, blended_channel_pct=0.20)
        f = engine.floor_price(120, 0.6, c)
        self.assertEqual(f["nightly"]["nightly_net"], 0.0)
        self.assertAlmostEqual(sum(x["sar"] for x in f["components"]), f["floor"])

    def test_a_loss_making_nightly_path_says_so_in_one_honest_row(self):
        c = engine.costs(turnover_cost_sar=400, alos=1.5, blended_channel_pct=0.20)
        f = engine.floor_price(120, 0.6, c)
        keys = [x["key"] for x in f["components"]]
        self.assertIn("nightly_net_zero", keys)
        self.assertNotIn("nightly_gross", keys)     # the three raw rows would mislead
        row = [x for x in f["components"] if x["key"] == "nightly_net_zero"][0]
        self.assertEqual(row["sar"], 0)
        self.assertTrue(row["label_ar"].strip())

    def test_no_forecast_means_no_floor(self):
        self.assertIsNone(engine.floor_price(None, 0.8, self.costs))
        self.assertIsNone(engine.floor_price(500, None, self.costs))


class CostsTest(unittest.TestCase):
    def test_defaults_exist_so_a_missing_setting_never_reads_as_zero(self):
        """A cost silently defaulting to 0 understates the floor, which is the
        one direction this feature must never fail in."""
        c = engine.costs()
        for k in ("turnover_cost_sar", "utilities_month", "consumables_month",
                  "wifi_month", "min_margin_sar", "blended_channel_pct", "alos"):
            self.assertGreater(c[k], 0, "%s must not default to zero" % k)

    def test_overrides_are_taken_and_the_rest_keep_defaults(self):
        c = engine.costs(turnover_cost_sar=999)
        self.assertEqual(c["turnover_cost_sar"], 999)
        self.assertGreater(c["utilities_month"], 0)

    def test_alos_can_never_be_zero_because_it_divides(self):
        c = engine.costs(alos=0)
        self.assertGreater(c["alos"], 0)


if __name__ == "__main__":
    unittest.main()


# ──────────────────────────── S5 — the quality model ────────────────────────────

class QualityMultiplierTest(unittest.TestCase):
    def test_a_unit_we_know_nothing_about_multiplies_by_exactly_one(self):
        """16 unanswered attributes must leave the base rate untouched. If this
        drifts, every unscored unit in the portfolio is silently mispriced."""
        q = engine.quality_multiplier({})
        self.assertEqual(q["mult"], 1.0)
        self.assertEqual(q["unanswered"], 16)
        self.assertEqual(q["multipliers"], [])

    def test_a_middling_score_of_five_is_neutral(self):
        """score 5 sits at the centre of the 1..10 scale, so it must not move the
        price in either direction."""
        q = engine.quality_multiplier({"design": 5, "living_room": 5})
        self.assertAlmostEqual(q["mult"], 1.0)

    def test_a_good_unit_multiplies_above_one(self):
        q = engine.quality_multiplier({"design": 9, "furniture": 9, "view_light": 9})
        self.assertGreater(q["mult"], 1.0)

    def test_a_poor_unit_multiplies_below_one(self):
        q = engine.quality_multiplier({"design": 1, "furniture": 1, "view_light": 1})
        self.assertLess(q["mult"], 1.0)

    def test_the_clamp_holds_at_exactly_one_sixty(self):
        """One absurd input must not run away with the price. Every attribute at
        its maximum still cannot exceed the ceiling."""
        best = {k: 10 for k in ["design", "compound", "furniture", "living_room",
                                "view_light", "metro", "floor_lift", "wifi_tier"]}
        best.update({"sqm": 400, "review_score": 5.0, "bathrooms": 6,
                     "new_build": True, "parking_covered": True, "majlis": True,
                     "ac_central": True, "self_entry": True})
        q = engine.quality_multiplier(best)
        self.assertEqual(q["mult"], 1.60)
        self.assertTrue(q["clamped"])

    def test_the_clamp_holds_at_exactly_zero_sixty_five(self):
        worst = {k: 1 for k in ["design", "compound", "furniture", "living_room",
                                "view_light", "metro", "floor_lift", "wifi_tier"]}
        worst.update({"sqm": 10, "review_score": 3.0, "bathrooms": 0.5,
                      "new_build": False, "parking_covered": False, "majlis": False,
                      "ac_central": False, "self_entry": False})
        q = engine.quality_multiplier(worst)
        self.assertEqual(q["mult"], 0.65)
        self.assertTrue(q["clamped"])

    def test_an_unclamped_unit_says_so(self):
        q = engine.quality_multiplier({"design": 7})
        self.assertFalse(q["clamped"])

    def test_only_factors_that_moved_the_number_are_listed(self):
        """An unanswered attribute and a neutral 5 both contribute nothing, so
        neither belongs in the explanation."""
        q = engine.quality_multiplier({"design": 8, "furniture": 5})
        keys = [m["key"] for m in q["multipliers"]]
        self.assertEqual(keys, ["design"])

    def test_the_biggest_mover_is_listed_first(self):
        q = engine.quality_multiplier({"wifi_tier": 10, "sqm": 250, "design": 10})
        self.assertEqual(q["multipliers"][0]["key"], "sqm")


class ModelPriceTest(unittest.TestCase):
    def test_model_price_is_the_base_scaled_by_quality(self):
        m = engine.model_price(10000, {"design": 10})
        self.assertAlmostEqual(m["model"], 10000 * m["quality"]["mult"])

    def test_an_unscored_unit_prices_at_its_district_base(self):
        m = engine.model_price(10000, {})
        self.assertEqual(m["model"], 10000)

    def test_delta_sar_says_what_the_factor_is_worth_in_riyals(self):
        """delta_sar = what the price would LOSE without this factor. An owner
        asks 'what is my majlis worth?' and this is the sentence that answers."""
        m = engine.model_price(10000, {"majlis": True})
        row = m["quality"]["multipliers"][0]
        self.assertAlmostEqual(row["delta_sar"], m["model"] - m["model"] / row["mult"])
        self.assertGreater(row["delta_sar"], 0)

    def test_a_missing_base_produces_no_model_price(self):
        self.assertIsNone(engine.model_price(None, {"design": 9}))
        self.assertIsNone(engine.model_price(0, {"design": 9}))

    def test_a_clamped_unit_flags_that_its_factor_riyals_do_not_reconcile(self):
        """Once the product is clamped, the per-factor riyals no longer add up to
        the total — so the screen must be told, not left to imply otherwise."""
        best = {k: 10 for k in ["design", "compound", "furniture", "living_room",
                                "view_light", "metro", "floor_lift", "wifi_tier"]}
        best.update({"sqm": 400, "new_build": True, "majlis": True})
        m = engine.model_price(10000, best)
        self.assertTrue(m["quality"]["clamped"])
        self.assertEqual(m["model"], 16000)
