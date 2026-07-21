import unittest
from match import poi


class TestHaversine(unittest.TestCase):
    def test_zero_distance_for_same_point(self):
        self.assertEqual(poi.haversine_km((24.7, 46.7), (24.7, 46.7)), 0.0)

    def test_known_riyadh_distance(self):
        # Kingdom Centre -> Boulevard City, roughly 11 km apart.
        d = poi.haversine_km((24.7114, 46.6745), (24.7660, 46.6210))
        self.assertGreater(d, 7.0)
        self.assertLess(d, 15.0)

    def test_symmetric(self):
        a, b = (24.71, 46.67), (24.80, 46.60)
        self.assertAlmostEqual(poi.haversine_km(a, b), poi.haversine_km(b, a), places=6)


class TestResolvePoint(unittest.TestCase):
    def test_prefers_exact_coords(self):
        unit = {"id": 1, "neighborhood": "al_malqa"}
        pt = poi.resolve_point(unit, {1: (24.80, 46.60)})
        self.assertEqual(pt, (24.80, 46.60))

    def test_falls_back_to_neighborhood_centroid(self):
        unit = {"id": 2, "neighborhood": "al_malqa"}
        pt = poi.resolve_point(unit, {})
        self.assertIsNotNone(pt)
        self.assertEqual(pt, poi.NEIGHBOURHOOD_CENTROIDS["al_malqa"])

    def test_returns_none_when_nothing_known(self):
        self.assertIsNone(poi.resolve_point({"id": 3, "neighborhood": ""}, {}))


class TestMinutes(unittest.TestCase):
    def test_minutes_scale_with_distance(self):
        self.assertLess(poi.minutes_to(2.0), poi.minutes_to(20.0))

    def test_minutes_is_positive_int(self):
        m = poi.minutes_to(5.0)
        self.assertIsInstance(m, int)
        self.assertGreater(m, 0)


class TestPurposeMapping(unittest.TestCase):
    def test_boulevard_purpose_maps_to_a_poi(self):
        self.assertIn("boulevard", poi.PURPOSE_POI)
        key = poi.PURPOSE_POI["boulevard"]
        self.assertIn(key, poi.POIS)

    def test_rest_purpose_has_no_poi(self):
        self.assertIsNone(poi.PURPOSE_POI.get("rest"))

    def test_every_mapped_poi_exists(self):
        for purpose, key in poi.PURPOSE_POI.items():
            if key is not None:
                self.assertIn(key, poi.POIS, f"{purpose} -> {key} missing from POIS")

    def test_every_centroid_key_is_a_real_neighborhood(self):
        import bot
        valid = {k for (k, _ar, _en) in bot.RIYADH_NEIGHBORHOODS}
        for key in poi.NEIGHBOURHOOD_CENTROIDS:
            self.assertIn(key, valid, f"{key} is not in RIYADH_NEIGHBORHOODS")


if __name__ == "__main__":
    unittest.main()
