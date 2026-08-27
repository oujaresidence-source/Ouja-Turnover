import unittest


from monthly_public.showcase_contracts import (
    ShowcaseContextError,
    ShowcaseContractError,
    issue_showcase_context,
    parse_showcase,
    verify_showcase_context,
)


SECRET = b"test-only-monthly-showcase-key-32b"


def valid_group(**overrides):
    value = {
        "name_ar": "مساكن الملقا",
        "name_en": "Ouja Al Malqa Residences",
        "slug": "al-malqa-residences",
        "description_ar": "ثمان شقق عوجا في مبنى واحد.",
        "description_en": "Eight Ouja homes in one building.",
        "image_url": "https://images.example.test/building.jpg",
        "listing_ids": ["101"],
        "fixed_monthly_rate_sar": 12500,
        "fixed_price_enabled": True,
    }
    value.update(overrides)
    return value


class ShowcaseContractTest(unittest.TestCase):
    def test_normalizes_one_approved_group_without_losing_members(self):
        value = parse_showcase(
            valid_group(listing_ids=["101", "102", "103"]),
            known_listing_ids={"101", "102", "103"},
        )

        self.assertEqual(value["listing_ids"], ["101", "102", "103"])
        self.assertEqual(value["fixed_monthly_rate_sar"], 12500)

    def test_rejects_unknown_duplicate_or_empty_membership(self):
        for members in ([], ["101", "101"], ["999"]):
            with self.subTest(members=members), self.assertRaises(
                ShowcaseContractError
            ):
                parse_showcase(valid_group(listing_ids=members), {"101"})

    def test_fixed_price_is_required_only_when_enabled(self):
        parsed = parse_showcase(
            valid_group(
                fixed_price_enabled=False,
                fixed_monthly_rate_sar=None,
            ),
            {"101"},
        )
        self.assertIsNone(parsed["fixed_monthly_rate_sar"])

        with self.assertRaises(ShowcaseContractError):
            parse_showcase(
                valid_group(
                    fixed_price_enabled=True,
                    fixed_monthly_rate_sar=None,
                ),
                {"101"},
            )

    def test_rejects_unapproved_fields_and_untrusted_image_urls(self):
        with self.assertRaises(ShowcaseContractError) as caught:
            parse_showcase(valid_group(discount_percent=30), {"101"})
        self.assertEqual(caught.exception.code, "unknown_field")

        with self.assertRaises(ShowcaseContractError) as caught:
            parse_showcase(valid_group(image_url="http://images.example.test/a.jpg"), {"101"})
        self.assertEqual(caught.exception.field, "image_url")

    def test_approved_slug_is_lowercase_and_path_safe(self):
        for slug in ("Al-Malqa", "../malqa", "malqa/residences", "malqa--homes"):
            with self.subTest(slug=slug), self.assertRaises(ShowcaseContractError):
                parse_showcase(valid_group(slug=slug), {"101"})

    def test_context_contains_no_price_and_rejects_tampering(self):
        token = issue_showcase_context(SECRET, "showcase_ab12", 4)

        self.assertNotIn("12500", token)
        self.assertEqual(
            verify_showcase_context(token, SECRET),
            {"group_id": "showcase_ab12", "revision": 4},
        )
        with self.assertRaises(ShowcaseContextError):
            verify_showcase_context(token[:-1] + "x", SECRET)

    def test_context_rejects_a_different_server_secret(self):
        token = issue_showcase_context(SECRET, "showcase_ab12", 4)

        with self.assertRaises(ShowcaseContextError):
            verify_showcase_context(token, b"another-test-showcase-key-32bytes")


if __name__ == "__main__":
    unittest.main()
