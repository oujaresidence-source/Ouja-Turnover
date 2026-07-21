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


if __name__ == "__main__":
    unittest.main()
