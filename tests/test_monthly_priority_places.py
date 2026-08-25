from collections import Counter
import unittest

from monthly_public.priority_places import (
    PRIORITY_PLACE_MIGRATION_ID,
    distance_km,
    load_priority_places,
    nearest_places,
)


class PriorityPlaceDataTest(unittest.TestCase):
    def test_vetted_dataset_contains_only_the_approved_25_places(self):
        rows = load_priority_places()

        self.assertEqual(PRIORITY_PLACE_MIGRATION_ID, "priority_places_2026_08_25_v1")
        self.assertEqual(len(rows), 25)
        self.assertEqual(len({row["id"] for row in rows}), 25)
        self.assertFalse(any(row["id"].startswith("edu_") for row in rows))
        self.assertEqual(
            Counter(row["category_id"] for row in rows),
            Counter(
                {
                    "business_hubs": 5,
                    "hospitals": 5,
                    "family_retail": 5,
                    "riyadh_season": 5,
                    "events": 5,
                }
            ),
        )

    def test_every_place_has_verified_riyadh_coordinates_and_https_evidence(self):
        for row in load_priority_places():
            with self.subTest(place_id=row["id"]):
                self.assertTrue(24.0 <= row["lat"] <= 25.6)
                self.assertTrue(46.0 <= row["lng"] <= 47.6)
                self.assertTrue(row["official_source_url"].startswith("https://"))
                self.assertTrue(row["coordinate_source_url"].startswith("https://"))
                self.assertTrue(row["map_url"].startswith("https://"))
                self.assertEqual(row["verified_at"], "2026-08-25")

    def test_purposes_are_reduced_to_the_approved_customer_journey(self):
        expected = {
            "business_hubs": ["work"],
            "hospitals": ["treatment", "family"],
            "family_retail": ["family", "visit"],
            "riyadh_season": ["visit", "family"],
            "events": ["work", "visit"],
        }
        for row in load_priority_places():
            with self.subTest(place_id=row["id"]):
                self.assertEqual(row["purposes"], expected[row["category_id"]])


class PriorityPlaceDistanceTest(unittest.TestCase):
    def setUp(self):
        self.origin = {
            "lat": 24.7500,
            "lng": 46.6500,
            "source": "staff_maps_pin",
            "verified": True,
        }

    def test_distance_requires_two_verified_coordinate_pairs(self):
        destination = {
            "lat": 24.7600,
            "lng": 46.6600,
            "source": "priority_places_2026_08_25",
            "verified": True,
        }
        self.assertGreater(distance_km(self.origin, destination), 0)
        self.assertIsNone(distance_km({**self.origin, "verified": False}, destination))
        self.assertIsNone(distance_km(self.origin, {**destination, "source": ""}))

    def test_nearest_places_returns_five_stable_staff_safe_results(self):
        places = {}
        for index in range(7):
            places["place_%d" % index] = {
                "kind": "destination",
                "label_ar": "مكان %d" % index,
                "label_en": "Place %d" % index,
                "category_id": "business_hubs",
                "category_ar": "مراكز الأعمال",
                "category_en": "Business hubs",
                "priority": 7 - index,
                "lat": 24.7510 + (index * 0.01),
                "lng": 46.6510,
                "source": "priority_places_2026_08_25",
                "verified": True,
                "map_url": "https://maps.example/%d" % index,
                "official_source_url": "https://official.example/%d" % index,
                "coordinate_source_url": "https://source.example/%d" % index,
                "verified_at": "2026-08-25",
                "review_interval_ar": "سنوي",
                "review_interval_en": "Annual",
            }

        results = nearest_places(self.origin, places)

        self.assertEqual(len(results), 5)
        self.assertEqual(
            [row["distance_km"] for row in results],
            sorted(row["distance_km"] for row in results),
        )
        self.assertEqual(set(results[0]), {
            "id", "label_ar", "label_en", "category_id", "category_ar",
            "category_en", "priority", "distance_km", "map_url",
            "official_source_url", "coordinate_source_url", "verified_at",
            "review_interval_ar", "review_interval_en",
        })

    def test_nearest_places_returns_empty_without_a_verified_apartment_pin(self):
        self.assertEqual(nearest_places({**self.origin, "verified": False}, {}), [])


if __name__ == "__main__":
    unittest.main()
