import unittest

from monthly_public.pricing import add_months, quote_for
from monthly_public.publication import validate_listing
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


def prepared_listing(**overrides):
    result = validate_listing(valid_listing(**overrides), valid_settings(), NOW)
    assert result.publishable, [issue.code for issue in result.blockers]
    return result.listing


def plain(value):
    if hasattr(value, "items"):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


class PublicPricingTests(unittest.TestCase):
    def test_one_month_uses_the_verified_start_month_rate(self):
        quote = quote_for(
            prepared_listing(),
            {"move_in": "2026-09-01", "duration_months": 1},
            NOW,
        )
        self.assertEqual(quote["monthly_rate_sar"], 12000)
        self.assertEqual(quote["stay_total_sar"], 12000)
        self.assertEqual(quote["move_out"], "2026-10-01")
        self.assertEqual(quote["currency"], "SAR")

    def test_one_to_six_month_total_uses_one_official_request_rate(self):
        for months in range(1, 7):
            with self.subTest(months=months):
                quote = quote_for(
                    prepared_listing(),
                    {"move_in": "2026-09-15", "duration_months": months},
                    NOW,
                )
                self.assertEqual(quote["monthly_rate_sar"], 12000)
                self.assertEqual(quote["stay_total_sar"], 12000 * months)
                self.assertEqual(quote["months"], months)

    def test_missing_selected_month_price_returns_no_quote(self):
        self.assertIsNone(
            quote_for(
                prepared_listing(),
                {"move_in": "2026-10-01", "duration_months": 1},
                NOW,
            )
        )

    def test_stale_or_future_price_verification_returns_no_quote(self):
        for verified_at in (
            "2026-08-25T03:29:00+03:00",
            "2026-08-25T10:06:00+03:00",
            "not-a-time",
        ):
            copy_prices = {
                "2026-09": {
                    "monthly_rate_sar": 12000,
                    "currency": "SAR",
                    "source": "engine_verified",
                    "verified_at": verified_at,
                }
            }
            with self.subTest(verified_at=verified_at):
                listing = dict(prepared_listing())
                listing["official_prices"] = copy_prices
                self.assertIsNone(
                    quote_for(
                        listing,
                        {"move_in": "2026-09-01", "duration_months": 1},
                        NOW,
                    )
                )

    def test_legacy_price_fields_are_never_fallbacks(self):
        listing = dict(prepared_listing())
        listing["official_prices"] = {}
        listing["price_base"] = 999
        listing["m_after"] = 9999
        self.assertIsNone(
            quote_for(
                listing,
                {"move_in": "2026-09-01", "duration_months": 1},
                NOW,
            )
        )

    def test_explicit_non_anniversary_departure_requires_exact_cached_quote(self):
        request = {
            "move_in": "2026-09-01",
            "move_out": "2026-11-15",
            "duration_days": 75,
        }
        self.assertIsNone(quote_for(prepared_listing(), request, NOW))

        listing = dict(prepared_listing())
        listing["official_request_quotes"] = {
            "2026-09-01|2026-11-15": {
                "monthly_rate_sar": 12500,
                "stay_total_sar": 31000,
                "currency": "SAR",
                "source": "official_override",
                "verified_at": "2026-08-25T09:30:00+03:00",
            }
        }
        quote = quote_for(listing, request, NOW)
        self.assertEqual(quote["monthly_rate_sar"], 12500)
        self.assertEqual(quote["stay_total_sar"], 31000)
        self.assertEqual(quote["duration_days"], 75)
        self.assertNotIn("months", quote)

    def test_terms_are_complete_and_source_is_not_mutated(self):
        listing = prepared_listing()
        before = plain(listing)
        quote = quote_for(
            listing,
            {"move_in": "2026-09-01", "duration_months": 2},
            NOW,
        )
        self.assertEqual(quote["included"], ("internet", "maintenance"))
        self.assertEqual(quote["utilities"]["mode"], "variable")
        self.assertEqual(quote["cleaning"]["mode"], "optional")
        self.assertEqual(quote["cleaning"]["amount_sar"], 300)
        self.assertEqual(quote["deposit"]["amount_sar"], 2000)
        self.assertEqual(len(quote["payment_methods"]), 2)
        self.assertEqual(plain(listing), before)

    def test_four_to_six_months_use_the_approved_preliminary_label(self):
        for months in (4, 5, 6):
            quote = quote_for(
                prepared_listing(),
                {"move_in": "2026-09-01", "duration_months": months},
                NOW,
            )
            self.assertTrue(quote["preliminary_contract"])
            self.assertEqual(
                quote["preliminary_label_ar"],
                "سعر مبدئي. يؤكد فريق عوجا نوع العقد والشروط قبل الالتزام.",
            )
            self.assertTrue(quote["preliminary_label_en"])

    def test_public_quote_contains_no_discount_comparison_fields(self):
        quote = quote_for(
            prepared_listing(),
            {"move_in": "2026-09-01", "duration_months": 1},
            NOW,
        )
        forbidden = {"before", "saved", "pct", "ceiling", "discount", "m_after"}
        self.assertFalse(forbidden.intersection(quote))

    def test_add_months_clamps_calendar_end(self):
        self.assertEqual(add_months("2026-01-31", 1), "2026-02-28")


if __name__ == "__main__":
    unittest.main()
