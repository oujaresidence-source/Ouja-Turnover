import unittest
from match import poi


class TestHaversine(unittest.TestCase):
    def test_zero_distance_for_same_point(self):
        self.assertEqual(poi.haversine_km((24.7, 46.7), (24.7, 46.7)), 0.0)

    def test_known_riyadh_distance(self):
        # Kingdom Centre -> Boulevard City: correct haversine is ~8.13 km. A
        # naive flat-plane/equirectangular approximation gives ~8.49 km here —
        # tight enough bounds that a broken formula fails this.
        d = poi.haversine_km((24.7114, 46.6745), (24.7660, 46.6210))
        self.assertGreater(d, 7.9)
        self.assertLess(d, 8.4)

    def test_known_riyadh_distance_longer(self):
        # King Khalid Airport -> Diriyah: correct haversine is ~27.5 km. The
        # same naive approximation gives ~28.0 km here.
        airport = poi.POIS["airport"][2:]
        diriyah = poi.POIS["diriyah"][2:]
        d = poi.haversine_km(airport, diriyah)
        self.assertGreater(d, 27.0)
        self.assertLess(d, 27.9)

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

    def test_unit_not_a_dict_does_not_raise(self):
        self.assertIsNone(poi.resolve_point("not-a-dict", {}))
        self.assertIsNone(poi.resolve_point(["nope"], {}))
        self.assertIsNone(poi.resolve_point(None, {}))

    def test_unit_missing_id_falls_back_to_centroid(self):
        unit = {"neighborhood": "al_malqa"}
        self.assertEqual(poi.resolve_point(unit, {}), poi.NEIGHBOURHOOD_CENTROIDS["al_malqa"])

    def test_unit_missing_neighborhood_returns_none(self):
        unit = {"id": 9}
        self.assertIsNone(poi.resolve_point(unit, {}))

    def test_geo_is_none_falls_back_to_centroid(self):
        unit = {"id": 1, "neighborhood": "al_malqa"}
        self.assertEqual(poi.resolve_point(unit, None), poi.NEIGHBOURHOOD_CENTROIDS["al_malqa"])

    def test_geo_value_three_tuple_falls_back(self):
        unit = {"id": 1, "neighborhood": "al_malqa"}
        pt = poi.resolve_point(unit, {1: (24.7, 46.7, 99)})
        self.assertEqual(pt, poi.NEIGHBOURHOOD_CENTROIDS["al_malqa"])

    def test_geo_value_two_char_string_does_not_fabricate(self):
        # "24" has len 2 like a coordinate pair, but is NOT one — indexing it
        # would silently produce (2.0, 4.0), a bogus point in the Atlantic.
        unit = {"id": 1, "neighborhood": "al_malqa"}
        pt = poi.resolve_point(unit, {1: "24"})
        self.assertNotEqual(pt, (2.0, 4.0))
        self.assertEqual(pt, poi.NEIGHBOURHOOD_CENTROIDS["al_malqa"])

    def test_geo_value_two_tuple_of_non_numbers_falls_back(self):
        unit = {"id": 1, "neighborhood": "al_malqa"}
        pt = poi.resolve_point(unit, {1: ("a", "b")})
        self.assertEqual(pt, poi.NEIGHBOURHOOD_CENTROIDS["al_malqa"])

    def test_geo_value_none_falls_back(self):
        unit = {"id": 1, "neighborhood": "al_malqa"}
        pt = poi.resolve_point(unit, {1: None})
        self.assertEqual(pt, poi.NEIGHBOURHOOD_CENTROIDS["al_malqa"])


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

    def test_every_neighborhood_has_a_centroid(self):
        """A unit in ANY assignable neighborhood must be locatable, else it
        silently loses proximity scoring and ranks low for no stated reason."""
        import bot
        missing = [k for (k, _ar, _en) in bot.RIYADH_NEIGHBORHOODS
                   if k not in poi.NEIGHBOURHOOD_CENTROIDS]
        self.assertEqual(missing, [], f"neighborhoods with no centroid: {missing}")

    def test_every_centroid_is_inside_riyadh(self):
        """Same bounds bot.py:47417 uses to sanity-check guide coordinates."""
        for key, (lat, lng) in poi.NEIGHBOURHOOD_CENTROIDS.items():
            self.assertTrue(24.0 <= lat <= 25.6, f"{key} lat {lat} outside Riyadh")
            self.assertTrue(46.0 <= lng <= 47.6, f"{key} lng {lng} outside Riyadh")


if __name__ == "__main__":
    unittest.main()
