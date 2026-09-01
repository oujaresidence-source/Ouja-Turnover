# -*- coding: utf-8 -*-
"""digest.places — district chips from a curated venue table (no Google Places), and
proximity to the nearest Ouja unit pin. Unknown venue → «الرياض», never a guess."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import places


class Districts(unittest.TestCase):
    def test_known_venues(self):
        self.assertEqual(places.district_for("مسرح بكر الشدي"), "حطين")
        self.assertEqual(places.district_for("Boulevard City"), "حطين")
        self.assertEqual(places.district_for("KAFD Conference Centre"), "العقيق")
        self.assertEqual(places.district_for("اس اتش جي ارينا (الرياض)"), "الملقا")
        self.assertEqual(places.district_for("الأول بارك (الرياض)"), "الملز")
        self.assertEqual(places.district_for("", "ذكريات سبيستون في مسرح بكر الشدي في الرياض"), "حطين")

    def test_unknown_is_riyadh_not_a_guess(self):
        self.assertEqual(places.district_for("قاعة ما أحد يعرفها"), "الرياض")
        self.assertEqual(places.district_for(""), "الرياض")
        self.assertIsNone(places.coords_for("قاعة ما أحد يعرفها"))

    def test_generic_riyadh_key_never_beats_a_specific_one(self):
        self.assertEqual(places.district_for("بوليفارد سيتي، الرياض"), "حطين")


class Proximity(unittest.TestCase):
    def test_pins_loaded_from_the_coverage_study(self):
        self.assertGreaterEqual(len(places.OUJA_POINTS), 30)

    def test_score_decays_with_distance(self):
        near = places.coords_for("مسرح بكر الشدي")
        far = (24.9490, 45.9920)                                  # حافة العالم
        self.assertGreater(places.proximity_score(near), 0.7)
        self.assertEqual(places.proximity_score(far), 0.0)
        self.assertEqual(places.proximity_score(None), 0.35)
        self.assertLess(places.km_to_nearest_ouja(near), 8)

    def test_fallback_points_when_pin_file_missing(self):
        self.assertEqual(len(places.FALLBACK_POINTS), 3)
        self.assertGreater(places.proximity_score((24.8094, 46.5951), points=list(places.FALLBACK_POINTS)), 0.99)


if __name__ == "__main__":
    unittest.main()
