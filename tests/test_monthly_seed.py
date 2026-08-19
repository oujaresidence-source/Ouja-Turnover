# -*- coding: utf-8 -*-
"""
S3 — seeding. Every test here is about a REFUSAL to invent.

Run: python3 -m unittest tests.test_monthly_seed
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import attrs, seed                   # noqa: E402


class SmoothedRatingTest(unittest.TestCase):
    def test_a_5_from_two_reviews_loses_to_a_49_from_ninety(self):
        thin = seed.smoothed_rating(5.0, 2)
        deep = seed.smoothed_rating(4.9, 90)
        self.assertLess(thin, deep)

    def test_no_reviews_is_not_a_rating_of_46(self):
        self.assertIsNone(seed.smoothed_rating(None, 0))
        self.assertIsNone(seed.smoothed_rating(4.8, 0))
        self.assertIsNone(seed.smoothed_rating(0, 10))

    def test_it_matches_the_match_engine_constants(self):
        """One rating model in this codebase, not two that disagree."""
        from match import engine as mengine
        self.assertEqual(seed.PRIOR_RATING, mengine.PRIOR_RATING)
        self.assertEqual(seed.PRIOR_WEIGHT, mengine.PRIOR_WEIGHT)


class HonestMappingTest(unittest.TestCase):
    def test_private_parking_alone_does_not_become_covered_parking(self):
        l = {"id": 1, "name": "Ouja | Stay", "amenities": ["Free parking", "موقف خاص"]}
        self.assertNotIn("parking_covered", seed.seed_for_unit(l))

    def test_a_garage_does_become_covered_parking(self):
        l = {"id": 1, "name": "Ouja | Stay", "amenities": ["Private garage"]}
        self.assertTrue(seed.seed_for_unit(l)["parking_covered"])
        l2 = {"id": 2, "name": "Ouja | Stay", "desc": "فيها كراج مغلق"}
        self.assertTrue(seed.seed_for_unit(l2)["parking_covered"])

    def test_private_entrance_does_not_become_self_entry(self):
        l = {"id": 1, "name": "Ouja", "amenities": ["مدخل مستقل", "private entrance"]}
        self.assertNotIn("self_entry", seed.seed_for_unit(l))

    def test_a_smart_lock_does_become_self_entry(self):
        l = {"id": 1, "name": "Ouja", "amenities": ["Self check-in with smart lock"]}
        self.assertTrue(seed.seed_for_unit(l)["self_entry"])

    def test_absence_of_a_word_is_unanswered_not_false(self):
        """Not finding 'majlis' proves nobody wrote it down — not that there
        isn't one. False would be a claim; absent is the truth."""
        vals = seed.seed_for_unit({"id": 1, "name": "Ouja | Studio"})
        self.assertNotIn("majlis", vals)
        self.assertEqual(attrs.multiplier("majlis", vals.get("majlis")), 1.0)

    def test_a_view_bool_never_becomes_a_view_light_score(self):
        l = {"id": 1, "name": "Ouja", "amenities": ["إطلالة رائعة", "great view"]}
        self.assertNotIn("view_light", seed.seed_for_unit(l))

    def test_compound_score_is_never_derived_from_a_compound_name(self):
        l = {"id": 1, "name": "Ouja | Grand 3BR | Calma 90", "compound": "Calma 90"}
        self.assertNotIn("compound", seed.seed_for_unit(l))

    def test_sqm_is_never_invented(self):
        l = {"id": 1, "name": "Ouja | Grand 3BR", "beds": 3, "desc": "شقة واسعة جدا"}
        self.assertNotIn("sqm", seed.seed_for_unit(l))


class WifiTest(unittest.TestCase):
    def test_speed_maps_into_range_and_clamps(self):
        self.assertEqual(seed._wifi_score(25), 1.0)
        self.assertEqual(seed._wifi_score(300), 10.0)
        self.assertEqual(seed._wifi_score(5), 1.0)
        self.assertEqual(seed._wifi_score(900), 10.0)

    def test_unknown_speed_is_unanswered(self):
        self.assertIsNone(seed._wifi_score(None))
        self.assertIsNone(seed._wifi_score(""))
        self.assertIsNone(seed._wifi_score("fast"))


class SeedAllTest(unittest.TestCase):
    def test_it_keys_by_listing_id_and_skips_unusable_rows(self):
        out = seed.seed_all(
            [{"id": 7, "name": "Ouja", "amenities": ["Self check-in"]},
             {"id": "bad", "name": "Ouja"},
             {"name": "no id"}],
            ratings={7: {"rating": 4.9, "count": 40}})
        self.assertEqual(list(out), [7])
        self.assertTrue(out[7]["self_entry"])
        self.assertIn("review_score", out[7])


class CoverageReportTest(unittest.TestCase):
    def test_it_names_the_worklist_in_weight_order(self):
        """The most valuable missing fact should come first — that is the whole
        point of the report."""
        seeded = seed.seed_all([{"id": i, "name": "Ouja"} for i in range(53)])
        rows = seed.coverage_report(seeded, 53)
        self.assertEqual(rows[0]["key"], "sqm")
        self.assertEqual(rows[0]["missing"], 53)
        self.assertEqual(rows[0]["beta"], 0.25)

    def test_every_attribute_appears_even_when_fully_seeded(self):
        rows = seed.coverage_report({}, 0)
        self.assertEqual(len(rows), len(attrs.keys()))


if __name__ == "__main__":
    unittest.main()
