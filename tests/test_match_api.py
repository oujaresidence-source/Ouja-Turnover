import unittest
import bot


class TestPriceBands(unittest.TestCase):
    def test_thin_sample_returns_none(self):
        self.assertIsNone(bot._gw_price_bands([100, 200]))

    def test_returns_ascending_percentiles(self):
        prices = [200, 300, 400, 500, 600, 700, 800, 900]
        b = bot._gw_price_bands(prices)
        self.assertIsNotNone(b)
        self.assertLessEqual(b["p25"], b["median"])
        self.assertLessEqual(b["median"], b["p75"])

    def test_ignores_non_positive_prices(self):
        prices = [0, -5, None, 400, 500, 600, 700, 800]
        b = bot._gw_price_bands(prices)
        self.assertIsNotNone(b)
        self.assertGreater(b["p25"], 0)

    def test_all_values_are_ints(self):
        b = bot._gw_price_bands([100, 200, 300, 400, 500, 600])
        for k in ("p25", "median", "p75"):
            self.assertIsInstance(b[k], int)


class TestMatchAnswers(unittest.TestCase):
    def test_parses_query_into_the_answers_contract(self):
        a = bot._match_answers({"party": "5", "sleep": "pairs", "purpose": "boulevard",
                                "budget": "900", "check_in": "2026-08-01",
                                "check_out": "2026-08-04"})
        self.assertEqual(a["party_size"], 5)
        self.assertEqual(a["sleep_pref"], "pairs")
        self.assertEqual(a["purpose"], "boulevard")
        self.assertEqual(a["budget_max"], 900)

    def test_defaults_are_safe_on_empty_query(self):
        a = bot._match_answers({})
        self.assertEqual(a["party_size"], 1)
        self.assertIsNone(a["budget_max"])
        self.assertIsNone(a["check_in"])

    def test_party_size_is_clamped(self):
        self.assertEqual(bot._match_answers({"party": "999"})["party_size"], 16)
        self.assertEqual(bot._match_answers({"party": "0"})["party_size"], 1)
        self.assertEqual(bot._match_answers({"party": "junk"})["party_size"], 1)

    def test_unknown_sleep_pref_becomes_none(self):
        self.assertIsNone(bot._match_answers({"sleep": "hammock"})["sleep_pref"])

    def test_unknown_purpose_falls_back_to_rest(self):
        self.assertEqual(bot._match_answers({"purpose": "spelunking"})["purpose"], "rest")

    def test_dates_only_kept_when_both_valid(self):
        a = bot._match_answers({"check_in": "2026-08-01"})
        self.assertIsNone(a["check_in"])
        b = bot._match_answers({"check_in": "2026-08-04", "check_out": "2026-08-01"})
        self.assertIsNone(b["check_in"])

    def test_malformed_budget_becomes_none(self):
        self.assertIsNone(bot._match_answers({"budget": "lots"})["budget_max"])


class TestMatchRouteOrder(unittest.TestCase):
    def test_match_route_is_registered_before_the_slug_catchall(self):
        """/stay/{slug} is a catch-all. Registered after it, /stay/match 404s."""
        src = open("bot.py", encoding="utf-8").read()
        i_match = src.index('add_get("/stay/match"')
        i_slug = src.index('add_get("/stay/{slug}"')
        self.assertLess(i_match, i_slug,
                        "/stay/match must be registered before /stay/{slug}")


if __name__ == "__main__":
    unittest.main()
