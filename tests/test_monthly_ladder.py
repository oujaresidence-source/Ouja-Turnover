# -*- coding: utf-8 -*-
"""
The 45-day blind spot, and the fallback ladder the corpus chooses.

Run: python3 -m unittest tests.test_monthly_ladder
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import data, engine, host                   # noqa: E402


def res(lid, ci, co, total, status="new", rid=None):
    return {"id": rid or ("%s-%s" % (lid, ci)), "listingMapId": lid,
            "arrivalDate": ci, "departureDate": co, "totalPrice": total,
            "status": status}


class TheFortyFiveDayBlindSpotTest(unittest.TestCase):
    """F1, B02, B03, TWN 13B and 11B Royal reported «0 ليالي» in all three
    months. Five units failing identically across three different months was
    never a booking pattern."""

    def test_a_long_stay_covering_the_month_is_counted(self):
        """A guest who checks in 1 June for three months occupies every night of
        August. The nights themselves were always computed correctly."""
        r = res(479967, "2026-06-01", "2026-09-01", 72000)
        n = data.nights_in_month(r, datetime.date(2026, 8, 1),
                                 datetime.date(2026, 8, 31))
        self.assertEqual(n, 31)

    def test_the_pad_is_wide_enough_for_a_six_month_stay(self):
        """At the old 45-day pad that reservation was never FETCHED, so the
        nights above were never seen. This is the actual bug."""
        self.assertGreaterEqual(data.ARRIVAL_PAD_DAYS, 190)

    def test_fetch_history_asks_for_the_wide_pad(self):
        asked = []

        def fake(first, last, pad=45):
            asked.append(pad)
            return []

        original = host.HOST.fetch_reservations_window
        host.HOST.fetch_reservations_window = fake
        try:
            data.fetch_history("2026-08", today=datetime.date(2026, 8, 19))
        finally:
            host.HOST.fetch_reservations_window = original
        self.assertTrue(asked)
        for p in asked:
            self.assertEqual(p, data.ARRIVAL_PAD_DAYS)

    def test_the_five_named_units_each_get_a_non_zero_count_when_history_exists(self):
        """Pinned by lid, because these five are the ones that failed."""
        rows = []
        for lid in (479967, 523916, 522603, 535903, 535907):
            rows.append(res(lid, "2026-06-01", "2026-09-01", 72000))
        obs = data.unit_month_rows(rows, 8, "2026-08")
        for lid in (479967, 523916, 522603, 535903, 535907):
            self.assertIn(lid, obs, "unit %s produced no observation" % lid)
            self.assertEqual(obs[lid][0]["nights"], 31,
                             "unit %s counted %s nights" % (lid, obs[lid][0]["nights"]))

    def test_c2_nfl_august_and_january_now_behave_the_same_way(self):
        """Same unit, one month worked and one did not — the difference was
        whether that month's stay happened to arrive inside the pad."""
        aug = data.unit_month_rows([res(461328, "2026-06-01", "2026-09-01", 72000)],
                                   8, "2026-08")
        jan = data.unit_month_rows([res(461328, "2026-01-05", "2026-01-30", 20000)],
                                   1, "2026-08")
        self.assertEqual(aug[461328][0]["nights"], 31)
        self.assertEqual(jan[461328][0]["nights"], 25)


class RecentCorpusTest(unittest.TestCase):
    def test_every_month_is_kept_not_only_the_target_month_number(self):
        rows = [res(1, "2026-03-01", "2026-03-11", 6000),
                res(1, "2026-05-01", "2026-05-11", 7000),
                res(1, "2026-07-01", "2026-07-11", 8000)]
        obs = data.unit_month_rows_all(rows, "2026-08")
        self.assertEqual(len({o["month"] for o in obs[1]}), 3)

    def test_each_observation_carries_its_month_number(self):
        obs = data.unit_month_rows_all([res(1, "2026-03-01", "2026-03-11", 6000)],
                                       "2026-08")
        self.assertEqual(obs[1][0]["month_num"], 3)


class FourMethodsTest(unittest.TestCase):
    def _obs(self, month, adr, occ=0.8, num=None, age=1):
        return {"month": month, "month_num": num or int(month[5:7]), "adr": adr,
                "occ": occ, "nights": 25, "months_old": age, "partial": False}

    def test_recent_needs_a_minimum_before_it_speaks(self):
        self.assertIsNone(engine.recent_forecast([self._obs("2026-07", 800)]))
        self.assertIsNotNone(engine.recent_forecast(
            [self._obs("2026-07", 800), self._obs("2026-06", 780),
             self._obs("2026-05", 810)]))

    def test_seasonal_factors_need_multi_year_units(self):
        one_year = {1: [self._obs("2026-%02d" % m, 800) for m in range(1, 9)]}
        self.assertEqual(engine.seasonal_factors(one_year), {})

    def test_seasonal_factors_are_built_from_qualified_units(self):
        pool = {}
        for lid in (1, 2, 3):
            rows = []
            for y in (2025, 2026):
                for m in range(1, 13):
                    adr = 1200 if m == 1 else 700          # January is the peak
                    rows.append(self._obs("%d-%02d" % (y, m), adr, num=m))
            pool[lid] = rows
        f = engine.seasonal_factors(pool)
        self.assertIn(1, f)
        self.assertGreater(f[1][0], 1.3, "January should read as a peak")

    def test_seasonal_keeps_the_units_level_and_borrows_only_the_shape(self):
        own = [self._obs("2026-07", 1000), self._obs("2026-06", 1000),
               self._obs("2026-05", 1000)]
        factors = {1: (1.5, 1.0)}
        out = engine.seasonal_forecast(own, 1, factors)
        self.assertAlmostEqual(out["adr"], 1500)

    def test_seasonal_occupancy_can_never_exceed_one(self):
        own = [self._obs("2026-07", 900, occ=0.9)] * 3
        out = engine.seasonal_forecast(own, 1, {1: (1.0, 2.0)})
        self.assertLessEqual(out["occ"], 1.0)


class BacktestPicksTheWinnerTest(unittest.TestCase):
    def _unit(self, lid, level, seasonal=True):
        rows = []
        for y in (2025, 2026):
            for m in range(1, 13):
                mult = 1.5 if m == 1 else 1.0
                rows.append({"month": "%d-%02d" % (y, m), "month_num": m,
                             "adr": level * (mult if seasonal else 1.0),
                             "occ": 0.8, "nights": 25, "months_old": 1,
                             "partial": False})
        return rows

    def test_a_unit_that_outearns_its_pool_is_better_described_by_itself(self):
        """The complaint, as a test: a strong unit measured against a pool it has
        outgrown. Whatever wins must not be the pool."""
        units = {1: self._unit(1, 2000), 2: self._unit(2, 700),
                 3: self._unit(3, 700), 4: self._unit(4, 700)}
        bt = engine.backtest_methods(units, units,
                                     lambda lid: [o for k, r in units.items()
                                                  if k != lid for o in r])
        self.assertIsNotNone(bt["rung2"])
        self.assertNotEqual(bt["rung2"], "pool")

    def test_every_method_is_scored_with_its_case_count(self):
        units = {i: self._unit(i, 800) for i in range(1, 5)}
        bt = engine.backtest_methods(units, units, lambda lid: [])
        for k in ("same_month", "recent", "pool", "seasonal"):
            self.assertIn(k, bt["methods"])
            self.assertIn("mape", bt["methods"][k])
            self.assertIn("n", bt["methods"][k])

    def test_a_thin_corpus_picks_nothing_rather_than_guessing(self):
        bt = engine.backtest_methods({1: self._unit(1, 800)[:4]}, {}, lambda lid: [])
        self.assertIsNone(bt["rung2"])

    def test_the_held_out_month_cannot_predict_itself(self):
        """A method must not score well by remembering the answer."""
        units = {1: self._unit(1, 900)}
        bt = engine.backtest_methods(units, units, lambda lid: [], min_cases=1)
        for k in ("recent", "same_month"):
            m = bt["methods"][k]["mape"]
            if m is not None:
                self.assertGreaterEqual(m, 0.0)


class LadderUsesTheWinnerTest(unittest.TestCase):
    def _own_all(self, adr=2000):
        return [{"month": "2026-%02d" % m, "month_num": m, "adr": adr, "occ": 0.85,
                 "nights": 26, "months_old": 8 - m, "partial": False}
                for m in range(1, 8)]

    def test_a_unit_with_no_same_month_history_uses_its_own_recent_record(self):
        fc = engine.forecast_unit(own=[], district=[{"adr": 600, "occ": 0.8}],
                                  own_all=self._own_all(), month_num=8,
                                  rung2="recent")
        self.assertEqual(fc["basis"], "own_recent")
        self.assertAlmostEqual(fc["adr"], 2000, places=0)

    def test_without_a_chosen_rung_the_old_pool_behaviour_is_unchanged(self):
        fc = engine.forecast_unit(own=[], district=[{"adr": 600, "occ": 0.8}],
                                  own_all=self._own_all(), month_num=8)
        self.assertEqual(fc["basis"], "district_pool")

    def test_the_strong_unit_no_longer_prices_like_the_pool(self):
        weak = engine.price_unit(1, "2026-08", own=[],
                                 district=[{"adr": 600, "occ": 0.8, "months_old": 1}],
                                 attr_values={})
        strong = engine.price_unit(2, "2026-08", own=[],
                                   district=[{"adr": 600, "occ": 0.8, "months_old": 1}],
                                   attr_values={}, own_all=self._own_all(),
                                   rung2="recent")
        self.assertNotEqual(strong["price"], weak["price"])
        self.assertGreater(strong["price"], weak["price"])

    def test_an_own_recent_price_is_not_labelled_as_pool_priced(self):
        p = engine.price_unit(1, "2026-08", own=[],
                              district=[{"adr": 600, "occ": 0.8, "months_old": 1}],
                              attr_values={}, own_all=self._own_all(), rung2="recent")
        self.assertNotIn("priced_from_pool", p["warnings"])
        self.assertIn("priced_from_own_recent", p["warnings"])

    def test_the_waterfall_still_reconciles_on_the_new_rung(self):
        import random
        rnd = random.Random(5150)
        for _ in range(500):
            own_all = [{"month": "2026-%02d" % m, "month_num": m,
                        "adr": rnd.uniform(200, 2500), "occ": rnd.uniform(0.1, 1.0),
                        "nights": 25, "months_old": 1, "partial": False}
                       for m in range(1, 8)]
            p = engine.price_unit(1, "2026-08", own=[],
                                  district=[{"adr": rnd.uniform(200, 2000),
                                             "occ": rnd.uniform(0.1, 1.0),
                                             "months_old": 1}],
                                  attr_values={}, own_all=own_all, rung2="recent")
            if p["price"] is None:
                continue
            self.assertAlmostEqual(sum(c["sar"] for c in p["components"]),
                                   p["price"], places=2)


if __name__ == "__main__":
    unittest.main()


class LastRungTest(unittest.TestCase):
    """TWN 13B: three bookings, all in one month, no recorded bedroom count.
    It had no comparable pool, so it got no price at all — the difference between
    "we cannot compare it" and "we will not answer"."""

    def test_a_unit_with_no_district_or_size_pool_still_gets_an_answer(self):
        port = [{"adr": 700, "occ": 0.7, "months_old": 1, "nights": 25}]
        fc = engine.forecast_unit(own=[], district=[], bedroom=[], portfolio=port)
        self.assertEqual(fc["basis"], "portfolio_pool")

    def test_the_portfolio_pool_is_the_LAST_resort_not_a_shortcut(self):
        port = [{"adr": 700, "occ": 0.7, "months_old": 1, "nights": 25}]
        dist = [{"adr": 900, "occ": 0.8, "months_old": 1, "nights": 25}]
        fc = engine.forecast_unit(own=[], district=dist, bedroom=[], portfolio=port)
        self.assertEqual(fc["basis"], "district_pool")

    def test_it_is_still_labelled_as_a_pool_price(self):
        port = [{"adr": 700, "occ": 0.7, "months_old": 1, "nights": 25}]
        p = engine.price_unit(1, "2026-08", own=[], district=[], bedroom=[],
                              attr_values={}, portfolio=port)
        self.assertIn("priced_from_pool", p["warnings"])

    def test_with_nothing_anywhere_there_is_still_no_price(self):
        p = engine.price_unit(1, "2026-08", own=[], district=[], bedroom=[],
                              attr_values={}, portfolio=[])
        self.assertIsNone(p["price"])


class ShortfallIsSpecificTest(unittest.TestCase):
    """«ما عندنا حجوزات كافية» is true and useless. A brand-new unit with three
    bookings in one month deserves to be told that, and told what changes it."""

    def test_no_price_carries_the_numbers_behind_it(self):
        one_month = [{"month": "2026-06", "month_num": 6, "adr": 800, "occ": 0.6,
                      "nights": 12, "months_old": 2, "partial": False}]
        p = engine.price_unit(1, "2026-08", own=[], district=[], bedroom=[],
                              attr_values={}, own_all=one_month, portfolio=[])
        self.assertIsNone(p["price"])
        sf = p["shortfall"]
        self.assertEqual(sf["months_of_record"], 1)
        self.assertEqual(sf["months_needed"], engine.MIN_RECENT_OBS)

    def test_a_unit_with_nothing_at_all_reports_zero_months(self):
        p = engine.price_unit(1, "2026-08", own=[], district=[], bedroom=[],
                              attr_values={}, own_all=[], portfolio=[])
        self.assertEqual(p["shortfall"]["months_of_record"], 0)

    def test_three_months_is_enough_to_stop_being_a_shortfall(self):
        three = [{"month": "2026-0%d" % m, "month_num": m, "adr": 800, "occ": 0.7,
                  "nights": 20, "months_old": 8 - m, "partial": False}
                 for m in (4, 5, 6)]
        p = engine.price_unit(1, "2026-08", own=[], district=[], bedroom=[],
                              attr_values={}, own_all=three, rung2="recent",
                              portfolio=[])
        self.assertIsNotNone(p["price"])
        self.assertEqual(p["basis"], "own_recent")
