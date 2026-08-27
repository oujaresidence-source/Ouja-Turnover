import unittest


from monthly_public.pricing import PRELIMINARY_AR, quote_for
from monthly_public.publication import validate_listing
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings
from tests.test_monthly_public_pricing import plain, prepared_listing


def price_missing_listing():
    return validate_listing(
        valid_listing(official_prices={}),
        valid_settings(),
        NOW,
    ).listing


def listing_with_request_quote():
    listing = dict(prepared_listing())
    listing["official_request_quotes"] = {
        "2026-09-01|2026-10-15": {
            "monthly_rate_sar": 14000,
            "stay_total_sar": 21000,
            "currency": "SAR",
            "source": "official_override",
            "verified_at": "2026-08-25T09:30:00+03:00",
        }
    }
    return listing


class ShowcasePricingTest(unittest.TestCase):
    def test_fixed_rate_replaces_only_full_month_quote(self):
        listing = prepared_listing()
        original = plain(listing["official_prices"])

        quote = quote_for(
            listing,
            {"move_in": "2026-09-01", "duration_months": 2},
            NOW,
            fixed_monthly_rate_sar=12500,
        )

        self.assertEqual(quote["monthly_rate_sar"], 12500)
        self.assertEqual(quote["stay_total_sar"], 25000)
        self.assertEqual(plain(listing["official_prices"]), original)

    def test_fixed_rate_can_supply_the_only_missing_price(self):
        quote = quote_for(
            price_missing_listing(),
            {"move_in": "2026-09-01", "duration_months": 1},
            NOW,
            fixed_monthly_rate_sar=12500,
        )

        self.assertEqual(quote["monthly_rate_sar"], 12500)
        self.assertEqual(quote["stay_total_sar"], 12500)

    def test_fixed_rate_does_not_prorate_partial_months(self):
        quote = quote_for(
            listing_with_request_quote(),
            {"move_in": "2026-09-01", "move_out": "2026-10-15"},
            NOW,
            fixed_monthly_rate_sar=12500,
        )

        self.assertEqual(quote["monthly_rate_sar"], 14000)
        self.assertEqual(quote["stay_total_sar"], 21000)

    def test_four_month_fixed_quote_keeps_preliminary_warning(self):
        quote = quote_for(
            prepared_listing(),
            {"move_in": "2026-09-01", "duration_months": 4},
            NOW,
            fixed_monthly_rate_sar=12500,
        )

        self.assertTrue(quote["preliminary_contract"])
        self.assertEqual(quote["preliminary_label_ar"], PRELIMINARY_AR)

    def test_invalid_override_fails_closed_instead_of_using_it(self):
        for value in (True, 0, -1, 1_000_001, float("inf"), "12500"):
            with self.subTest(value=value):
                self.assertIsNone(
                    quote_for(
                        prepared_listing(),
                        {"move_in": "2026-09-01", "duration_months": 1},
                        NOW,
                        fixed_monthly_rate_sar=value,
                    )
                )


if __name__ == "__main__":
    unittest.main()
