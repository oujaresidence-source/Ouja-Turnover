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


# ─────────────────── the reconciliation invariant, property-tested ───────────────────

class ReconciliationInvariantTest(unittest.TestCase):
    """Hand-picked cases are what missed this the first two times it happened.
    These sweep the space instead."""

    def test_it_refuses_a_column_that_does_not_add_up(self):
        with self.assertRaises(engine.ReconciliationError):
            engine.check_reconciles([{"sar": 100}, {"sar": 50}], 1000)

    def test_it_accepts_floating_point_noise_but_not_real_money(self):
        engine.check_reconciles([{"sar": 33.333333}, {"sar": 66.666667}], 100.0)
        with self.assertRaises(engine.ReconciliationError):
            engine.check_reconciles([{"sar": 33.0}, {"sar": 66.0}], 100.0)

    def test_a_missing_total_is_an_error_not_a_pass(self):
        with self.assertRaises(engine.ReconciliationError):
            engine.check_reconciles([{"sar": 100}], None)

    def test_every_floor_waterfall_reconciles_across_the_whole_input_space(self):
        """4,800 randomized units: cheap and dear, empty and full, tiny turnover
        costs and absurd ones. Any combination whose column does not sum to its
        own headline raises at construction, so this test would fail loudly
        rather than a wrong number reaching a screen."""
        import random
        rnd = random.Random(20260819)          # seeded: a failure is reproducible
        checked = 0
        for _ in range(4800):
            adr = rnd.choice([0.0, 45.0, 120.0, 380.0, 700.0, 1500.0, 6000.0])
            occ = rnd.choice([0.0, 0.05, 0.35, 0.62, 0.88, 1.0])
            c = engine.costs(
                turnover_cost_sar=rnd.choice([1, 60, 140, 400, 1200]),
                alos=rnd.choice([1.0, 1.5, 2.9, 6.0, 30.0]),
                blended_channel_pct=rnd.choice([0.001, 0.03, 0.15, 0.30, 0.55]),
                utilities_month=rnd.choice([1, 350, 2000]),
                consumables_month=rnd.choice([1, 120, 900]),
                wifi_month=rnd.choice([1, 150, 600]),
                min_margin_sar=rnd.choice([1, 650, 5000]))
            f = engine.floor_price(adr, occ, c)
            if f is None:
                continue
            checked += 1
            self.assertAlmostEqual(sum(x["sar"] for x in f["components"]),
                                   f["floor"], places=2)
            self.assertGreater(f["floor"], 0, "a floor must never be zero or negative")
        self.assertGreater(checked, 4000, "the sweep did not actually exercise anything")

    def test_the_floor_never_falls_below_the_cost_of_serving_a_monthly_let(self):
        """Whatever the nightly side does, we cannot rationally let a unit for
        less than it costs us to run plus our margin."""
        import random
        rnd = random.Random(7)
        for _ in range(600):
            c = engine.costs(turnover_cost_sar=rnd.uniform(1, 900),
                             utilities_month=rnd.uniform(1, 1500),
                             consumables_month=rnd.uniform(1, 800),
                             wifi_month=rnd.uniform(1, 500),
                             min_margin_sar=rnd.uniform(1, 4000))
            f = engine.floor_price(rnd.uniform(50, 3000), rnd.uniform(0, 1), c)
            self.assertGreaterEqual(
                f["floor"] + 0.01, f["monthly_direct_cost"] + c["min_margin_sar"])


# ═══════════════════ S7 — two gates, the payload, the break-even ═══════════════════

def _own(n=12):
    return [obs(500, 0.8, 1, nights=n)]


class BaseRateTest(unittest.TestCase):
    def test_base_comes_from_our_own_realised_history(self):
        """30 nights at the pool's own ADR and occupancy — what a unit like this
        actually earns us in a month."""
        b = engine.base_rate(district=[obs(500, 0.8, 1)], bedroom=[])
        self.assertAlmostEqual(b["base"], 30 * 500 * 0.8)
        self.assertEqual(b["basis"], "district_pool")

    def test_it_falls_back_to_the_bedroom_pool(self):
        b = engine.base_rate(district=[], bedroom=[obs(400, 0.7, 2)])
        self.assertEqual(b["basis"], "bedroom_pool")

    def test_no_pool_means_no_base_and_therefore_no_model_price(self):
        b = engine.base_rate(district=[], bedroom=[])
        self.assertIsNone(b["base"])

    def test_the_pool_is_not_pre_scaled_by_the_units_quality(self):
        """quality_mult is applied ONCE, by model_price. If base_rate scaled too,
        a good unit would be counted twice."""
        b = engine.base_rate(district=[obs(500, 0.8, 1)], bedroom=[])
        self.assertAlmostEqual(b["base"], 12000)


class TwoGatesTest(unittest.TestCase):
    def test_the_floor_binds_when_it_is_the_higher(self):
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(200, 0.4, 1)],
                              attr_values={})
        self.assertEqual(p["bound_by"], "floor")
        # The floor is the highest of the two GATES THAT PUSH UP. The ceiling is
        # a cap, so comparing against max(all gates) stopped being meaningful the
        # moment a third gate started pulling the other way.
        self.assertGreater(p["gates"]["floor"], p["gates"]["model"])

    def test_the_model_binds_when_quality_carries_it_higher(self):
        # Inputs retuned so the model lands BETWEEN the floor and the ceiling.
        # The old inputs (ADR 900, every attribute maxed) now correctly resolve
        # to 'ceiling' — the model wanted more than a guest would pay booking the
        # 30 nights one at a time, which is the whole point of the new cap.
        p = engine.price_unit(1, "2026-10", own=_own(),
                              district=[obs(500, 0.8, 1)],
                              attr_values={"design": 6})
        self.assertEqual(p["bound_by"], "model")
        self.assertGreater(p["gates"]["model"], p["gates"]["floor"])
        self.assertLess(p["gates"]["model"], p["gates"]["ceiling"])

    def test_the_gates_are_floor_model_ceiling_and_never_owner_gate(self):
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                              attr_values={})
        # Three gates now — floor and model push up, ceiling caps. owner_gate is
        # not among them and cannot be.
        self.assertEqual(set(p["gates"]), {"floor", "model", "ceiling"})
        self.assertIn(p["bound_by"], engine.BOUND_BY_VALUES)
        self.assertNotIn("owner_gate", p["gates"])

    def test_a_unit_with_no_history_anywhere_gets_no_price(self):
        p = engine.price_unit(1, "2026-10", own=[], district=[], bedroom=[],
                              attr_values={})
        self.assertEqual(p["confidence"], "insufficient")
        self.assertIsNone(p["price"])

    def test_a_missing_base_still_produces_a_floor_backed_price(self):
        """We can know what a unit costs us without knowing what its street
        fetches. The floor alone is a legitimate price."""
        p = engine.price_unit(1, "2026-10", own=_own(), district=[], bedroom=[],
                              attr_values={})
        self.assertIsNotNone(p["price"])
        self.assertEqual(p["bound_by"], "floor")
        self.assertIsNone(p["gates"]["model"])


class OwnerGateIsUnreachableTest(unittest.TestCase):
    """Instruction from the owner: keep the math, but it must not find a silent
    way back into a price."""

    def test_the_engine_never_names_the_owner_gate_math_IN_CODE(self):
        """Parsed, not grepped. A text search tripped on the engine's own comment
        explaining that it does NOT import this — so the check reads the AST and
        sees only code, never comments or prose."""
        import ast, inspect
        tree = ast.parse(inspect.getsource(engine))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    names.add(a.name.split(".")[-1])
        self.assertNotIn("owner_annual_net", names)
        self.assertNotIn("owner_gate", names)

    def test_pricing_a_unit_never_calls_the_owner_gate_math_at_runtime(self):
        """Stronger than any static check: make the function explode, then price
        a unit. If the pricing path can reach it, this test says so."""
        from monthly import ejar
        original = ejar.owner_annual_net

        def _forbidden(*a, **k):
            raise AssertionError(
                "the pricing path reached ejar.owner_annual_net — the retired "
                "owner gate has found a way back into a price")

        ejar.owner_annual_net = _forbidden
        try:
            p = engine.price_unit(1, "2026-10", own=_own(),
                                  district=[obs(500, 0.8, 1)],
                                  attr_values={"design": 9},
                                  ejar_row=MarketContextIsNeverBindingTest.ROW)
            self.assertIsNotNone(p["price"])
        finally:
            ejar.owner_annual_net = original

    def test_the_payload_carries_no_owner_gate_anywhere(self):
        import json
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                              attr_values={"design": 8})
        self.assertNotIn("owner_gate", json.dumps(p, ensure_ascii=False))
        self.assertNotIn("owner", p)

    def test_calling_the_owner_gate_math_still_works_for_acquisition(self):
        """Kept, not deleted."""
        from monthly import ejar
        self.assertGreater(ejar.owner_annual_net(85000), 0)


class RoundingTest(unittest.TestCase):
    def test_the_price_is_rounded_to_the_nearest_fifty(self):
        self.assertEqual(engine.round_to_50(11834, 11834), 11850)
        self.assertEqual(engine.round_to_50(11820, 11820), 11850)

    def test_rounding_never_drops_below_the_binding_gate(self):
        """Rounding down would put the price under the constraint that set it —
        a rounded price that breaches a gate is a bug, not a cosmetic choice."""
        for raw in (10001, 10010, 10024, 10025, 10049):
            r = engine.round_to_50(raw, raw)
            self.assertGreaterEqual(r, raw)
            self.assertEqual(r % 50, 0)

    def test_an_exact_multiple_is_left_alone(self):
        self.assertEqual(engine.round_to_50(11850, 11850), 11850)

    def test_no_price_rounds_to_no_price(self):
        self.assertIsNone(engine.round_to_50(None, None))

    def test_the_rounded_price_never_breaches_a_gate_across_the_input_space(self):
        import random
        rnd = random.Random(999)
        for _ in range(3000):
            p = engine.price_unit(
                1, "2026-10",
                own=[obs(rnd.uniform(150, 2000), rnd.uniform(0.1, 1.0), 1, nights=30)],
                district=[obs(rnd.uniform(150, 2000), rnd.uniform(0.1, 1.0), 1)],
                attr_values={"design": rnd.randint(1, 10), "sqm": rnd.uniform(60, 300)})
            if p["price"] is None:
                continue
            # The band, not the maximum: a price must clear the floor and stay
            # under the ceiling. Asserting against max(gates) was a two-gate idea.
            self.assertGreaterEqual(p["price"] + 1e-9, p["gates"]["floor"])
            self.assertLessEqual(p["price"], p["gates"]["ceiling"] + 1e-9)
            self.assertEqual(p["price"] % 50, 0)


class WaterfallEndsOnThePriceTest(unittest.TestCase):
    def test_the_waterfall_sums_to_the_price_at_the_top_of_the_page(self):
        p = engine.price_unit(1, "2026-10", own=_own(),
                              district=[obs(900, 0.95, 1)],
                              attr_values={"design": 10, "sqm": 300})
        self.assertAlmostEqual(sum(c["sar"] for c in p["components"]), p["price"])

    def test_a_model_bound_price_shows_the_quality_step(self):
        # Same retune as above: the old inputs are now ceiling-bound by design.
        p = engine.price_unit(1, "2026-10", own=_own(),
                              district=[obs(500, 0.8, 1)],
                              attr_values={"design": 6})
        self.assertEqual(p["bound_by"], "model")
        self.assertIn("quality_uplift", [c["key"] for c in p["components"]])

    def test_a_floor_bound_price_shows_no_quality_step(self):
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(150, 0.3, 1)],
                              attr_values={})
        self.assertNotIn("quality_uplift", [c["key"] for c in p["components"]])

    def test_rounding_appears_as_its_own_visible_step(self):
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(517, 0.83, 1)],
                              attr_values={"design": 7})
        keys = [c["key"] for c in p["components"]]
        if p["price"] != p["price_unrounded"]:
            self.assertIn("rounding", keys)

    def test_every_payload_reconciles_across_the_input_space(self):
        import random
        rnd = random.Random(4242)
        for _ in range(3000):
            p = engine.price_unit(
                1, "2026-10",
                own=[obs(rnd.uniform(100, 2500), rnd.uniform(0, 1), rnd.randint(0, 24),
                         nights=rnd.randint(0, 30))],
                district=[obs(rnd.uniform(100, 2500), rnd.uniform(0, 1), 1)],
                bedroom=[obs(rnd.uniform(100, 2500), rnd.uniform(0, 1), 3)],
                attr_values={"design": rnd.randint(1, 10),
                             "majlis": rnd.choice([True, False, None])})
            if p["price"] is None:
                continue
            self.assertAlmostEqual(sum(c["sar"] for c in p["components"]),
                                   p["price"], places=2)


class MonthsLetBreakEvenTest(unittest.TestCase):
    def test_it_answers_how_many_months_let_monthly_match_a_year_let_nightly(self):
        c = engine.costs()
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                              attr_values={}, cost_set=c)
        m = p["breakeven"]["months_let"]
        keep_per_month = p["price"] - p["floor_detail"]["monthly_direct_cost"]
        self.assertAlmostEqual(m * keep_per_month,
                               12 * p["floor_detail"]["nightly"]["nightly_net"],
                               places=2)

    def test_it_inverts_exactly(self):
        """Feed the months back through and land on the nightly year again."""
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                              attr_values={})
        b = p["breakeven"]
        self.assertAlmostEqual(b["months_let"] * b["kept_per_month"],
                               b["nightly_year_net"], places=2)

    def test_a_price_that_cannot_cover_its_own_running_cost_has_no_breakeven(self):
        c = engine.costs(utilities_month=99999)
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(100, 0.1, 1)],
                              attr_values={}, cost_set=c)
        if p["price"] is not None and p["price"] <= p["floor_detail"]["monthly_direct_cost"]:
            self.assertIsNone(p["breakeven"]["months_let"])

    def test_more_than_twelve_months_means_monthly_cannot_match_nightly(self):
        b = engine.months_let_breakeven(price=1000, monthly_direct_cost=500,
                                        nightly_year_net=12000)
        self.assertEqual(b["months_let"], 24.0)
        self.assertTrue(b["exceeds_year"])


class MarketContextIsNeverBindingTest(unittest.TestCase):
    ROW = {"district": "الملقا", "bedrooms": 3, "unit_type": "شقة",
           "annual_rent": 54845, "txn_count": 1365, "source": "sakani_rei",
           "obs_type": "transacted", "as_of": "2026-06-30"}

    def test_the_multiple_is_the_price_over_the_annual_equivalent_month(self):
        from monthly import ejar
        ctx = ejar.market_context(12000, self.ROW, today="2026-08-19")
        self.assertAlmostEqual(ctx["annual_equivalent_month"], 54845 / 12.0)
        self.assertAlmostEqual(ctx["multiple"], 12000 / (54845 / 12.0))
        self.assertFalse(ctx["binding"])

    def test_the_real_malqa_number_gives_a_recognisable_multiple(self):
        from monthly import ejar
        ctx = ejar.market_context(12000, self.ROW, today="2026-08-19")
        self.assertGreater(ctx["multiple"], 2.5)
        self.assertLess(ctx["multiple"], 3.0)

    def test_context_does_not_move_the_price_at_all(self):
        """The same inputs must produce the same price whether or not a market
        row exists. If this ever fails, context has become a gate."""
        a = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                              attr_values={"design": 8})
        b = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                              attr_values={"design": 8}, ejar_row=self.ROW)
        self.assertEqual(a["price"], b["price"])
        self.assertEqual(a["bound_by"], b["bound_by"])
        self.assertEqual([c["sar"] for c in a["components"]],
                         [c["sar"] for c in b["components"]])

    def test_a_missing_market_row_is_reported_not_hidden(self):
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                              attr_values={}, ejar_row=None)
        self.assertFalse(p["market_context"]["available"])
        self.assertIn("ejar_missing", p["market_context"]["warnings"])

    def test_a_stale_market_row_never_lowers_the_prices_own_confidence(self):
        """Ejar does not feed the price, so it has no business degrading how
        confidently the price is stated."""
        stale = dict(self.ROW, as_of="2024-01-01")
        fresh = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                                  attr_values={}, ejar_row=self.ROW)
        old = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                                attr_values={}, ejar_row=stale)
        self.assertEqual(fresh["confidence"], old["confidence"])


class ConfidenceTest(unittest.TestCase):
    def test_thick_own_history_and_a_scored_unit_is_high(self):
        vals = {k: 7 for k in ["design", "compound", "furniture", "living_room",
                               "view_light", "metro", "floor_lift", "wifi_tier"]}
        vals.update({"sqm": 150, "review_score": 4.8, "bathrooms": 2,
                     "new_build": True, "parking_covered": True})
        p = engine.price_unit(1, "2026-10", own=[obs(500, 0.8, 1, nights=28)],
                              district=[obs(500, 0.8, 1)], attr_values=vals)
        self.assertEqual(p["confidence"], "high")

    def test_a_pool_priced_unit_is_never_high(self):
        p = engine.price_unit(1, "2026-10", own=[], district=[obs(500, 0.8, 1)],
                              attr_values={})
        self.assertIn(p["confidence"], ("low", "medium"))

    def test_an_unscored_unit_is_lowered(self):
        thick = [obs(500, 0.8, 1, nights=28)]
        scored = {k: 7 for k in ["design", "compound", "furniture", "living_room",
                                 "view_light", "metro", "floor_lift", "wifi_tier"]}
        scored.update({"sqm": 150, "review_score": 4.8, "bathrooms": 2,
                       "new_build": True, "parking_covered": True})
        hi = engine.price_unit(1, "2026-10", own=thick, district=[obs(500, .8, 1)],
                               attr_values=scored)
        lo = engine.price_unit(1, "2026-10", own=thick, district=[obs(500, .8, 1)],
                               attr_values={})
        self.assertEqual(hi["confidence"], "high")
        self.assertNotEqual(lo["confidence"], "high")

    def test_an_uncalibrated_model_is_labelled_an_estimate(self):
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, .8, 1)],
                              attr_values={}, paired_obs=0)
        self.assertTrue(p["is_estimate"])
        self.assertEqual(p["label_ar"], "تقدير")

    def test_a_calibrated_model_may_call_it_a_price(self):
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, .8, 1)],
                              attr_values={}, paired_obs=250)
        self.assertFalse(p["is_estimate"])
        self.assertEqual(p["label_ar"], "سعر")


# ═══════════════════ S7b — the ceiling: the constraint that was missing ═══════════════════

class CeilingTest(unittest.TestCase):
    """A guest can always book 30 nights one at a time. If our monthly price is
    above that, the product has no reason to exist."""

    def test_the_ceiling_is_thirty_nights_less_the_commitment_discount(self):
        c = engine.costs(monthly_commitment_discount=0.15)
        self.assertAlmostEqual(engine.ceiling_price(628, c), 30 * 628 * 0.85)

    def test_committing_to_a_month_must_cost_less_than_booking_night_by_night(self):
        c = engine.costs()
        rack = 30 * 628
        self.assertLess(engine.ceiling_price(628, c), rack)

    def test_the_discount_is_owner_editable(self):
        loose = engine.ceiling_price(628, engine.costs(monthly_commitment_discount=0.05))
        tight = engine.ceiling_price(628, engine.costs(monthly_commitment_discount=0.30))
        self.assertGreater(loose, tight)

    def test_no_forecast_means_no_ceiling(self):
        self.assertIsNone(engine.ceiling_price(None, engine.costs()))

    def test_a_runaway_model_is_capped_and_says_so(self):
        """The case that exposed this: 628/night, model wanted 23,506, rack rate
        for 30 nights is 18,840. Nobody takes that monthly deal."""
        p = engine.price_unit(
            1, "2026-10",
            own=[obs(628, 0.85, 6, nights=50)],
            district=[obs(590, 0.83, 10)],
            attr_values={"design": 10, "furniture": 10, "compound": 10,
                         "living_room": 10, "view_light": 10, "majlis": True,
                         "parking_covered": True, "sqm": 300})
        self.assertEqual(p["bound_by"], "ceiling")
        self.assertLessEqual(p["price"], p["gates"]["ceiling"])
        self.assertLess(p["price"], 30 * p["data"]["adr"])

    def test_a_ceiling_bound_price_is_a_warning_not_a_normal_outcome(self):
        p = engine.price_unit(
            1, "2026-10", own=[obs(628, 0.85, 6, nights=50)],
            district=[obs(590, 0.83, 10)],
            attr_values={"design": 10, "furniture": 10, "compound": 10,
                         "living_room": 10, "view_light": 10, "sqm": 300})
        self.assertIn("model_above_ceiling", p["warnings"])

    def test_the_price_never_exceeds_the_ceiling_across_the_input_space(self):
        import random
        rnd = random.Random(31337)
        for _ in range(3000):
            adr = rnd.uniform(120, 2500)
            p = engine.price_unit(
                1, "2026-10",
                own=[obs(adr, rnd.uniform(0.2, 1.0), 1, nights=30)],
                district=[obs(rnd.uniform(120, 2500), rnd.uniform(0.2, 1.0), 1)],
                attr_values={"design": rnd.randint(1, 10),
                             "sqm": rnd.uniform(60, 320),
                             "majlis": rnd.choice([True, False, None])})
            if p["price"] is None:
                continue
            self.assertLessEqual(p["price"], p["gates"]["ceiling"] + 1e-9)
            self.assertGreaterEqual(p["price"] + 1e-9, p["gates"]["floor"])

    def test_a_floor_above_the_ceiling_returns_no_price_and_does_not_split(self):
        """Not lettable monthly at a sane price. Do not average the two."""
        c = engine.costs(min_margin_sar=90000, monthly_commitment_discount=0.15)
        p = engine.price_unit(1, "2026-10", own=[obs(300, 0.5, 1, nights=30)],
                              district=[obs(300, 0.5, 1)], attr_values={}, cost_set=c)
        self.assertIsNone(p["price"])
        self.assertIn("floor_above_ceiling", p["warnings"])
        self.assertIsNone(p["bound_by"])

    def test_bound_by_now_has_four_possible_answers(self):
        self.assertEqual(set(engine.BOUND_BY_VALUES), {"floor", "model", "ceiling"})

    def test_the_waterfall_still_lands_on_the_price_when_the_ceiling_binds(self):
        p = engine.price_unit(
            1, "2026-10", own=[obs(628, 0.85, 6, nights=50)],
            district=[obs(590, 0.83, 10)],
            attr_values={"design": 10, "furniture": 10, "compound": 10,
                         "living_room": 10, "view_light": 10, "sqm": 300})
        self.assertAlmostEqual(sum(c["sar"] for c in p["components"]), p["price"])
        self.assertIn("ceiling_cap", [c["key"] for c in p["components"]])

    def test_rounding_at_the_ceiling_rounds_DOWN_not_up(self):
        """The floor rule was 'round up when rounding down would breach'. Against
        a ceiling that rule is backwards — rounding up breaches the cap."""
        self.assertEqual(engine.round_to_50(12040, floor=11000, ceiling=12045), 12000)

    def test_rounding_still_rounds_up_off_the_floor(self):
        self.assertEqual(engine.round_to_50(10010, floor=10010, ceiling=99999), 10050)

    def test_a_band_with_no_fifty_step_in_it_returns_no_price(self):
        self.assertIsNone(engine.round_to_50(10020, floor=10010, ceiling=10040))


class ScoreAnchorTest(unittest.TestCase):
    """The anchor IS the calibration. If a scorer reads 5 as 'fine' rather than
    'the median Ouja unit', every multiplier points up and the whole portfolio
    inflates by the same amount."""

    def test_the_anchor_is_stated_on_every_attribute_shown_to_a_scorer(self):
        from monthly import attrs
        for row in attrs.rows_for_ui({}):
            self.assertTrue(row["anchor_ar"].strip())
            self.assertIn("5", row["anchor_ar"])

    def test_the_anchor_names_our_own_portfolio_not_an_abstract_scale(self):
        from monthly import attrs
        self.assertIn("عوجا", attrs.SCORE_ANCHOR_AR)
        self.assertIn("median", attrs.SCORE_ANCHOR_EN.lower())

    def test_a_median_report_flags_an_attribute_anchored_too_high(self):
        from monthly import attrs
        units = [{"design": 8}, {"design": 8}, {"design": 7}, {"design": 9},
                 {"design": 8}]
        rep = attrs.median_report(units)
        row = [r for r in rep if r["key"] == "design"][0]
        self.assertEqual(row["median"], 8)
        self.assertTrue(row["anchor_suspect"])

    def test_a_correctly_anchored_attribute_is_not_flagged(self):
        from monthly import attrs
        units = [{"design": 3}, {"design": 5}, {"design": 5}, {"design": 7},
                 {"design": 5}]
        row = [r for r in attrs.median_report(units) if r["key"] == "design"][0]
        self.assertEqual(row["median"], 5)
        self.assertFalse(row["anchor_suspect"])

    def test_an_unscored_attribute_reports_no_median_rather_than_zero(self):
        from monthly import attrs
        row = [r for r in attrs.median_report([{}, {}]) if r["key"] == "sqm"][0]
        self.assertIsNone(row["median"])
        self.assertFalse(row["anchor_suspect"])


class ClampIsADiagnosticTest(unittest.TestCase):
    def test_a_clamped_unit_is_recorded_as_a_clamp_hit(self):
        p = engine.price_unit(1, "2026-10", own=_own(), district=[obs(500, 0.8, 1)],
                              attr_values={"design": 10, "furniture": 10,
                                           "compound": 10, "living_room": 10,
                                           "view_light": 10, "sqm": 320})
        self.assertTrue(p["quality"]["clamped"])
        self.assertIn("quality_clamped", p["warnings"])

    def test_a_portfolio_clamping_too_often_is_flagged_as_an_anchor_problem(self):
        results = [{"quality": {"clamped": i < 3}} for i in range(20)]
        rep = engine.clamp_report(results)
        self.assertAlmostEqual(rep["rate"], 0.15)
        self.assertTrue(rep["anchor_suspect"])

    def test_a_healthy_portfolio_is_not_flagged(self):
        results = [{"quality": {"clamped": i < 1}} for i in range(50)]
        self.assertFalse(engine.clamp_report(results)["anchor_suspect"])


class CeilingAndGrossAreIndependentTest(unittest.TestCase):
    """In the first worked example ceiling and nightly_gross both came to 16,014.
    That is a COINCIDENCE, not a relationship: occupancy was 0.85 and the
    commitment discount 0.15, so (1 - discount) happened to equal occ.

        ceiling       = 30 x adr x (1 - discount)      <- no occupancy term
        nightly_gross = 30 x adr x occ                 <- no discount term

    Documented here so it never becomes folklore."""

    def test_they_coincide_only_when_occupancy_equals_one_minus_the_discount(self):
        c = engine.costs(monthly_commitment_discount=0.15)
        e = engine.nightly_economics(628, 0.85, c)
        self.assertAlmostEqual(engine.ceiling_price(628, c), e["nightly_gross"])

    def test_at_sixty_percent_occupancy_they_separate(self):
        c = engine.costs(monthly_commitment_discount=0.15)
        e = engine.nightly_economics(628, 0.60, c)
        self.assertAlmostEqual(e["nightly_gross"], 30 * 628 * 0.60)
        self.assertAlmostEqual(engine.ceiling_price(628, c), 30 * 628 * 0.85)
        self.assertGreater(engine.ceiling_price(628, c), e["nightly_gross"])

    def test_occupancy_moves_gross_and_leaves_the_ceiling_untouched(self):
        c = engine.costs()
        base = engine.ceiling_price(628, c)
        for occ in (0.1, 0.35, 0.6, 0.85, 1.0):
            self.assertAlmostEqual(engine.ceiling_price(628, c), base)
            self.assertAlmostEqual(engine.nightly_economics(628, occ, c)["nightly_gross"],
                                   30 * 628 * occ)

    def test_the_discount_moves_the_ceiling_and_leaves_gross_untouched(self):
        gross = engine.nightly_economics(628, 0.85, engine.costs())["nightly_gross"]
        for d in (0.05, 0.15, 0.30):
            c = engine.costs(monthly_commitment_discount=d)
            self.assertAlmostEqual(engine.nightly_economics(628, 0.85, c)["nightly_gross"],
                                   gross)
            self.assertAlmostEqual(engine.ceiling_price(628, c), 30 * 628 * (1 - d))


class CeilingBindingThresholdTest(unittest.TestCase):
    """Instrumentation for the S8 diagnosis: at what quality multiplier does the
    ceiling start to bind? Diagnosis only — no treatment here."""

    def test_the_threshold_matches_the_worked_example(self):
        t = engine.ceiling_binds_above(adr_unit=628, adr_pool=590, occ_pool=0.83,
                                       cost_set=engine.costs())
        self.assertAlmostEqual(t, 1.090, places=2)

    def test_for_a_typical_unit_the_threshold_is_one_minus_discount_over_occupancy(self):
        t = engine.ceiling_binds_above(adr_unit=500, adr_pool=500, occ_pool=0.80,
                                       cost_set=engine.costs(monthly_commitment_discount=0.15))
        self.assertAlmostEqual(t, 0.85 / 0.80)

    def test_high_occupancy_makes_the_ceiling_bind_even_below_median_quality(self):
        """Ouja targets ~95% occupancy. Above (1 - discount) the threshold drops
        under 1.0, so the ceiling binds for units the model rates BELOW average."""
        t = engine.ceiling_binds_above(adr_unit=500, adr_pool=500, occ_pool=0.95,
                                       cost_set=engine.costs())
        self.assertLess(t, 1.0)

    def test_low_occupancy_gives_the_model_real_room(self):
        t = engine.ceiling_binds_above(adr_unit=500, adr_pool=500, occ_pool=0.60,
                                       cost_set=engine.costs())
        self.assertGreater(t, 1.4)

    def test_no_pool_means_no_threshold(self):
        self.assertIsNone(engine.ceiling_binds_above(500, None, 0.8, engine.costs()))


class BoundByDistributionTest(unittest.TestCase):
    """The S8 exit condition, ready before the data arrives."""

    def _r(self, bound_by, mult, price=1000, model=1000, ceiling=1000):
        return {"bound_by": bound_by, "price": price,
                "quality": {"mult": mult, "clamped": mult >= 1.60},
                "gates": {"model": model, "ceiling": ceiling}}

    def test_it_counts_every_outcome_including_no_price(self):
        rows = [self._r("floor", 1.0), self._r("model", 1.05),
                self._r("ceiling", 1.3), {"bound_by": None, "price": None,
                                          "quality": {"mult": 1.0}}]
        rep = engine.bound_by_report(rows)
        self.assertEqual(rep["counts"], {"floor": 1, "model": 1, "ceiling": 1,
                                         "no_price": 1})

    def test_it_reads_a_collapsed_engine_plainly(self):
        rows = [self._r("ceiling", 1.3) for _ in range(6)] + [self._r("floor", 1.0)] * 4
        rep = engine.bound_by_report(rows)
        self.assertEqual(rep["verdict"], "model_contributes_nothing")

    def test_it_reads_a_healthy_guardrail(self):
        rows = ([self._r("ceiling", 1.2)] * 3 + [self._r("model", 1.1)] * 4
                + [self._r("floor", 1.0)] * 3)
        self.assertEqual(engine.bound_by_report(rows)["verdict"], "healthy")

    def test_it_names_marginal_units_when_the_floor_dominates(self):
        rows = [self._r("floor", 1.0)] * 8 + [self._r("model", 1.1)] * 2
        self.assertEqual(engine.bound_by_report(rows)["verdict"], "units_marginal")

    def test_it_reports_the_quality_multiplier_spread_and_clamp_share(self):
        rows = [self._r("model", m) for m in (0.9, 1.0, 1.1, 1.60, 1.60)]
        rep = engine.bound_by_report(rows)
        self.assertAlmostEqual(rep["quality_mult"]["min"], 0.9)
        self.assertAlmostEqual(rep["quality_mult"]["median"], 1.1)
        self.assertAlmostEqual(rep["quality_mult"]["max"], 1.60)
        self.assertAlmostEqual(rep["quality_mult"]["pct_at_clamp"], 0.4)

    def test_it_reports_how_far_ceiling_bound_models_overshot(self):
        rows = [self._r("ceiling", 1.3, model=23506, ceiling=16014)]
        rep = engine.bound_by_report(rows)
        self.assertAlmostEqual(rep["overshoot"]["median_pct"], 23506 / 16014 - 1,
                               places=4)


class ScoringProtocolTest(unittest.TestCase):
    """The protocol lives beside the scale it governs, in both languages, because
    whoever scores reads attrs.py and not a document."""

    def test_all_four_rules_are_present_in_both_languages(self):
        from monthly import attrs
        self.assertEqual(len(attrs.SCORING_PROTOCOL_AR), 4)
        self.assertEqual(len(attrs.SCORING_PROTOCOL_EN), 4)
        for line in attrs.SCORING_PROTOCOL_AR + attrs.SCORING_PROTOCOL_EN:
            self.assertTrue(line.strip())

    def test_it_names_the_one_scorer_one_sitting_rule(self):
        from monthly import attrs
        self.assertIn("53", attrs.SCORING_PROTOCOL_AR[0])
        self.assertIn("one sitting", attrs.SCORING_PROTOCOL_EN[0].lower())

    def test_it_requires_ranking_before_scoring(self):
        from monthly import attrs
        self.assertIn("rank", attrs.SCORING_PROTOCOL_EN[2].lower())

    def test_it_forbids_scoring_a_unit_across_all_sixteen(self):
        from monthly import attrs
        self.assertIn("attribute", attrs.SCORING_PROTOCOL_EN[3].lower())
        self.assertIn("53", attrs.SCORING_PROTOCOL_EN[3])
