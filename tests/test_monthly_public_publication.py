import copy
import unittest

from monthly_public.publication import title_bedroom_conflict, validate_listing
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


def codes(issues):
    return [issue.code for issue in issues]


class PublicationValidationTests(unittest.TestCase):
    def test_valid_listing_is_publishable_and_exact_match_eligible(self):
        result = validate_listing(valid_listing(), valid_settings(), NOW)

        self.assertTrue(result.publishable)
        self.assertTrue(result.exact_match_eligible)
        self.assertEqual(result.availability_status, "confirmed")
        self.assertEqual(result.blockers, ())

    def test_validation_does_not_mutate_source(self):
        source = valid_listing()
        before = copy.deepcopy(source)
        validate_listing(source, valid_settings(), NOW)
        self.assertEqual(source, before)

    def test_malformed_nested_provider_fields_fail_closed_instead_of_raising(self):
        result = validate_listing(
            valid_listing(
                structured={"emblems": 3, "sections": "not-a-list"},
                facts=["workspace"],
                amenities={"Wireless": True},
                short_ar="",
                short_en="",
            ),
            valid_settings(),
            NOW,
        )
        self.assertFalse(result.publishable)
        self.assertIn("arabic_content_missing", codes(result.blockers))
        self.assertIn("english_content_missing", codes(result.blockers))

    def test_core_missing_fields_block_publication(self):
        cases = (
            ({"active": False}, "inactive_listing"),
            ({"id": None}, "listing_id_missing"),
            ({"bedrooms": None, "beds": None}, "bedrooms_missing"),
            ({"baths": None}, "bathrooms_missing"),
            ({"capacity": None}, "capacity_missing"),
            ({"neighborhood_verified": False}, "neighbourhood_missing"),
            ({"neighborhood": "", "neighborhood_ar": "", "neighborhood_en": ""}, "neighbourhood_missing"),
            ({"neighborhood_ar": "الرياض", "neighborhood_en": "Riyadh"}, "neighbourhood_missing"),
        )
        for override, expected in cases:
            with self.subTest(expected=expected):
                result = validate_listing(valid_listing(**override), valid_settings(), NOW)
                self.assertIn(expected, codes(result.blockers))
                self.assertFalse(result.publishable)

    def test_licence_validation_is_strict(self):
        cases = (
            ({"licence": None}, "licence_missing"),
            ({"licence": {"licence_no": "X", "expires": ""}}, "licence_expiry_missing"),
            ({"licence": {"licence_no": "X", "expires": "25/08/2027"}}, "licence_expiry_invalid"),
            ({"licence": {"licence_no": "X", "expires": "2026-08-24"}}, "licence_expired"),
        )
        for override, expected in cases:
            with self.subTest(expected=expected):
                result = validate_listing(valid_listing(**override), valid_settings(), NOW)
                self.assertIn(expected, codes(result.blockers))

    def test_licence_expiring_today_is_valid_and_soon_expiry_warns(self):
        today = validate_listing(
            valid_listing(licence={"licence_no": "X", "expires": "2026-08-25"}),
            valid_settings(),
            NOW,
        )
        soon = validate_listing(
            valid_listing(licence={"licence_no": "X", "expires": "2026-09-01"}),
            valid_settings(),
            NOW,
        )
        self.assertNotIn("licence_expired", codes(today.blockers))
        self.assertIn("licence_expiring", codes(today.warnings))
        self.assertIn("licence_expiring", codes(soon.warnings))

    def test_only_positive_verified_sar_prices_count(self):
        bad_prices = (
            {},
            {"2026-09": {"monthly_rate_sar": 0, "currency": "SAR", "source": "engine_verified"}},
            {"2026-09": {"monthly_rate_sar": 12000, "currency": "USD", "source": "engine_verified"}},
            {"2026-09": {"monthly_rate_sar": 12000, "currency": "SAR", "source": "legacy_discount"}},
            {"2026-09": {"m_after": 12000, "currency": "SAR", "source": "engine_verified"}},
        )
        for price in bad_prices:
            with self.subTest(price=price):
                result = validate_listing(
                    valid_listing(official_prices=price), valid_settings(), NOW
                )
                self.assertIn("price_missing", codes(result.blockers))

    def test_language_and_content_require_verified_bilingual_fields(self):
        cases = (
            ({"name_ar": "English title only"}, "arabic_title_missing"),
            ({"name_en": "عنوان عربي فقط"}, "english_title_missing"),
            ({"structured": None, "short_ar": "", "desc_ar": ""}, "arabic_content_missing"),
            ({"structured": None, "short_en": "", "desc_en": ""}, "english_content_missing"),
            ({"content_verified": False}, "content_unverified"),
        )
        for override, expected in cases:
            with self.subTest(expected=expected):
                result = validate_listing(valid_listing(**override), valid_settings(), NOW)
                self.assertIn(expected, codes(result.blockers))

    def test_title_bedroom_conflicts_block_but_screen_and_floor_numbers_do_not(self):
        known_conflicts = (
            ("Ground Floor 3BR + Huge Living | AlMajdiah", 2),
            ("Japandi #3BR", 5),
            ("Japandi Retreat . 3BR Smart Entry", 5),
            ("Modern 2BR w/ private cinema – 15 min to airport", 1),
            ("Modern Luxury 2BR near Airport | Al-Narjis", 3),
        )
        for title, bedrooms in known_conflicts:
            with self.subTest(title=title):
                self.assertTrue(title_bedroom_conflict(title, bedrooms))
        for title in ('39th Floor home with 98" TV #C3', "الوحدة ٣٩ في الدور التاسع"):
            with self.subTest(title=title):
                self.assertFalse(title_bedroom_conflict(title, 2))

        result = validate_listing(
            valid_listing(name_en="Ouja | 3BR home", bedrooms=2, beds=2),
            valid_settings(),
            NOW,
        )
        self.assertIn("title_bedroom_conflict", codes(result.blockers))

    def test_legacy_beds_can_supply_bedrooms_but_physical_beds_count_cannot(self):
        legacy = validate_listing(
            valid_listing(bedrooms=None, beds=2), valid_settings(), NOW
        )
        physical_only = validate_listing(
            valid_listing(bedrooms=None, beds=None, beds_count=2), valid_settings(), NOW
        )
        self.assertNotIn("bedrooms_missing", codes(legacy.blockers))
        self.assertIn("bedrooms_missing", codes(physical_only.blockers))

    def test_three_unique_https_images_are_required(self):
        for images in (
            ["https://x.test/1.jpg", "https://x.test/1.jpg", "https://x.test/2.jpg"],
            ["http://x.test/1.jpg", "https://x.test/2.jpg", "https://x.test/3.jpg"],
            ["https://x.test/1.jpg", "https://x.test/2.jpg"],
        ):
            with self.subTest(images=images):
                result = validate_listing(valid_listing(images=images), valid_settings(), NOW)
                self.assertIn("images_missing", codes(result.blockers))

    def test_missing_or_stale_calendar_is_pending_not_an_exact_claim(self):
        for calendar in (
            None,
            {
                "synced_at": "2026-08-25T08:59:00+03:00",
                "from": "2026-08-25",
                "to": "2027-03-23",
            },
        ):
            with self.subTest(calendar=calendar):
                result = validate_listing(
                    valid_listing(calendar=calendar), valid_settings(), NOW
                )
                self.assertTrue(result.publishable)
                self.assertFalse(result.exact_match_eligible)
                self.assertEqual(result.availability_status, "pending")
                self.assertTrue(
                    {"calendar_missing", "calendar_stale"}.intersection(codes(result.warnings))
                )

    def test_missing_listing_specific_commercial_terms_blocks(self):
        result = validate_listing(
            valid_listing(commercial_terms={}), valid_settings(), NOW
        )
        self.assertIn("commercial_terms_missing", codes(result.blockers))

    def test_rating_and_coordinate_proof_are_warnings_not_blockers(self):
        result = validate_listing(
            valid_listing(rating_verified=False, coordinates={}), valid_settings(), NOW
        )
        self.assertTrue(result.publishable)
        self.assertIn("rating_unverified", codes(result.warnings))
        self.assertIn("coordinates_unverified", codes(result.warnings))


if __name__ == "__main__":
    unittest.main()
