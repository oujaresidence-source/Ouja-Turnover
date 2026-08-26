import json
import unittest

from monthly_public.presentation import map_amenities, present_card, present_listing
from monthly_public.publication import validate_listing
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


class AmenityPresentationTests(unittest.TestCase):
    def test_amenities_are_exact_mapped_bilingual_and_deduplicated(self):
        groups, unknown = map_amenities(
            ["Wireless", "Internet", "Kitchen", "Free parking", "Mystery concierge"]
        )
        flattened = [item for group in groups for item in group["items"]]
        self.assertEqual([item["key"] for item in flattened].count("internet"), 1)
        self.assertIn("kitchen", {item["key"] for item in flattened})
        self.assertIn("free_parking", {item["key"] for item in flattened})
        self.assertEqual(unknown, ("Mystery concierge",))
        self.assertTrue(all(item["ar"] and item["en"] for item in flattened))

    def test_substring_and_description_inference_are_not_used(self):
        groups, unknown = map_amenities(["No free parking", "Parking attendant"])
        self.assertEqual(groups, ())
        self.assertEqual(set(unknown), {"No free parking", "Parking attendant"})


class ListingPresentationTests(unittest.TestCase):
    def _result(self, **overrides):
        return validate_listing(valid_listing(**overrides), valid_settings(), NOW)

    def test_arabic_and_english_never_cross_fallback(self):
        ar = present_listing(self._result(), "ar")
        en = present_listing(self._result(), "en")
        self.assertEqual(ar["title"], "عوجا | بيت بغرفتين في الملقا")
        self.assertEqual(en["title"], "Ouja | Two-bedroom home in Al Malqa")
        self.assertNotIn("Kitchen", json.dumps(ar, ensure_ascii=False))
        self.assertNotIn("المطبخ", json.dumps(en, ensure_ascii=False))

    def test_unknown_amenities_are_not_public(self):
        item = self._result(amenities=["Mystery concierge", "Kitchen"])
        public = present_listing(item, "en")
        self.assertNotIn("Mystery concierge", json.dumps(public))
        self.assertIn("untranslated_amenity", [issue.code for issue in item.warnings])

    def test_raw_descriptions_and_internal_audit_fields_do_not_render(self):
        public = present_listing(self._result(), "en")
        payload = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("Raw description that must not render", payload)
        self.assertNotIn("entered_by", payload)
        self.assertNotIn("updated_at", payload)
        self.assertNotIn("price_base", payload)
        self.assertNotIn("m_after", payload)

    def test_verified_rating_renders_and_unverified_rating_is_omitted(self):
        verified = present_card(self._result(), "en")
        unverified = present_card(self._result(rating_verified=False), "en")
        self.assertEqual(verified["rating"], 4.82)
        self.assertEqual(verified["reviews_count"], 34)
        self.assertNotIn("rating", unverified)
        self.assertNotIn("reviews_count", unverified)

    def test_listing_exposes_only_the_safe_review_projection(self):
        public = present_listing(
            self._result(
                public_reviews={
                    "rating_value": 5.0,
                    "rating_scale": 5,
                    "rating_count": 2,
                    "text_review_count": 1,
                    "source_label": "approved_public_reviews",
                    "topic_mentions": [
                        {"key": "cleanliness", "count": 1, "total": 1}
                    ],
                    "category_scores": [
                        {"key": "cleanliness", "rating": 4.9, "scale": 5}
                    ],
                    "latest_reviews": [
                        {
                            "id": "r1",
                            "rating": 5,
                            "guest_name": "Sara A.",
                            "text": "نظيف",
                            "language": "ar",
                            "channel": "Airbnb",
                            "date": "2026-05-01",
                            "private_review": "must never render",
                            "reservation_id": "secret",
                        }
                    ],
                    "empty_state_ar": "لا توجد مراجعات عامة نصية لهذه الشقة حاليًا.",
                    "empty_state_en": "No public written reviews are available for this home yet.",
                }
            ),
            "ar",
        )

        self.assertEqual(public["reviews"]["latest_reviews"][0]["text"], "نظيف")
        payload = json.dumps(public["reviews"], ensure_ascii=False)
        self.assertNotIn("private_review", payload)
        self.assertNotIn("reservation_id", payload)
        self.assertNotIn("must never render", payload)

    def test_gallery_has_unique_urls_and_localized_nonblank_alt_text(self):
        images = valid_listing()["images"]
        public = present_listing(self._result(images=images + [images[0]]), "ar")
        gallery = public["images"]
        self.assertEqual(len({item["url"] for item in gallery}), len(gallery))
        self.assertTrue(all(item["alt"].strip() for item in gallery))
        self.assertTrue(all("عوجا" in item["alt"] for item in gallery))

    def test_floor_area_comes_only_from_verified_floor_area_field(self):
        public = present_card(self._result(floor_area_sqm=None, area="Riyadh"), "en")
        self.assertNotIn("floor_area_sqm", public["facts"])
        self.assertNotIn("Riyadh", json.dumps(public["facts"]))

    def test_free_parking_does_not_become_private_parking(self):
        public = present_listing(
            self._result(amenities=["Free parking"], facts={"parking": False}), "en"
        )
        payload = json.dumps(public)
        self.assertIn("Free parking", payload)
        self.assertNotIn("Private parking", payload)

    def test_structured_sections_are_bilingual_complete_and_not_duplicated(self):
        public = present_listing(self._result(), "ar")
        bodies = [section["body"] for section in public["story"]]
        self.assertEqual(len(bodies), len(set(bodies)))
        self.assertNotIn("وصف خام لا يجب عرضه.", bodies)

    def test_detail_exposes_only_public_licence_fields(self):
        public = present_listing(self._result(), "en")
        self.assertEqual(
            public["licence"],
            {"number": "TEST-AD-1001", "expires": "2027-08-25"},
        )

    def test_output_has_no_coordinates_or_travel_time_claim(self):
        public = present_listing(self._result(), "en")
        payload = json.dumps(public).lower()
        for forbidden in ("lat", "lng", "minutes", "travel_time", "drive"):
            self.assertNotIn('"%s"' % forbidden, payload)


if __name__ == "__main__":
    unittest.main()
