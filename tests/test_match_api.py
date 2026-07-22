import unittest
from unittest import mock

import bot


def _fake_visible_snaps(n):
    return [({"id": i, "price_base": 300}, {}) for i in range(1, n + 1)]


def _fake_listing_public(s, ov):
    """Minimal-but-valid unit dict for match.score — every field the engine
    reads is accessed via .get() with a safe default, so this doesn't need to
    mirror the real _gw_listing_public output, just be a plain dict with an id."""
    return {"id": s["id"], "capacity": 4, "beds": 2, "price_base": 300,
            "rating": 4.7, "reviews_count": 10, "amenities": [], "tag_keys": [],
            "neighborhood": None, "images": [],
            "name_en": "unit-%s" % s["id"], "name_ar": "unit-%s" % s["id"]}


def _fake_snaps_for_search(n, neighborhoods=None):
    """(snap, override) pairs shaped like _gw_visible_snaps() output for
    _gw_search. `neighborhoods` optionally maps id -> neighborhood key on the
    override, for exercising the neighborhood filter."""
    neighborhoods = neighborhoods or {}
    out = []
    for i in range(1, n + 1):
        s = {"id": i, "price_base": 300, "capacity": 4, "tag_keys": []}
        ov = {"neighborhood": neighborhoods.get(i)}
        out.append((s, ov))
    return out


def _fake_gw_listing_public(s, ov):
    """Minimal-but-valid pub dict for _gw_search's sort_key, which reads
    has_airbnb / images / name_ar (plus s["capacity"] and ov["sort"] directly)."""
    return {"id": s["id"], "has_airbnb": False, "images": [],
            "name_ar": "unit-%s" % s["id"], "name_en": "unit-%s" % s["id"]}


def _fake_geo_listing_public(s, ov, with_airbnb=True):
    """Minimal pub dict for _match_geo_points, which reads id/lat/lng/name_en/name_ar.
    Accepts with_airbnb (_match_geo_points always calls with_airbnb=False) like the
    real _gw_listing_public does."""
    return {"id": s["id"], "lat": s.get("lat"), "lng": s.get("lng"),
            "name_en": s.get("name_en") or ("unit-%s" % s["id"]),
            "name_ar": s.get("name_ar") or ("unit-%s" % s["id"])}


class TestPriceBands(unittest.TestCase):
    def test_thin_sample_returns_none(self):
        self.assertIsNone(bot._gw_price_bands([100, 200]))

    def test_returns_ascending_percentiles(self):
        prices = [200, 300, 400, 500, 600, 700, 800, 900]
        b = bot._gw_price_bands(prices)
        self.assertIsNotNone(b)
        self.assertLessEqual(b["p25"], b["median"])
        self.assertLessEqual(b["median"], b["p75"])

    def test_ignores_non_positive_prices(self):
        prices = [0, -5, None, 400, 500, 600, 700, 800]
        b = bot._gw_price_bands(prices)
        self.assertIsNotNone(b)
        self.assertGreater(b["p25"], 0)

    def test_all_values_are_ints(self):
        b = bot._gw_price_bands([100, 200, 300, 400, 500, 600])
        for k in ("p25", "median", "p75"):
            self.assertIsInstance(b[k], int)


class TestMatchAnswers(unittest.TestCase):
    def test_parses_query_into_the_answers_contract(self):
        a = bot._match_answers({"party": "5", "sleep": "pairs", "purpose": "boulevard",
                                "budget": "900", "check_in": "2026-08-01",
                                "check_out": "2026-08-04"})
        self.assertEqual(a["party_size"], 5)
        self.assertEqual(a["sleep_pref"], "pairs")
        self.assertEqual(a["purpose"], "boulevard")
        self.assertEqual(a["budget_max"], 900)

    def test_defaults_are_safe_on_empty_query(self):
        a = bot._match_answers({})
        self.assertEqual(a["party_size"], 1)
        self.assertIsNone(a["budget_max"])
        self.assertIsNone(a["check_in"])

    def test_party_size_is_clamped(self):
        self.assertEqual(bot._match_answers({"party": "999"})["party_size"], 16)
        self.assertEqual(bot._match_answers({"party": "0"})["party_size"], 1)
        self.assertEqual(bot._match_answers({"party": "junk"})["party_size"], 1)

    def test_unknown_sleep_pref_becomes_none(self):
        self.assertIsNone(bot._match_answers({"sleep": "hammock"})["sleep_pref"])

    def test_unknown_purpose_falls_back_to_rest(self):
        self.assertEqual(bot._match_answers({"purpose": "spelunking"})["purpose"], "rest")

    def test_dates_only_kept_when_both_valid(self):
        a = bot._match_answers({"check_in": "2026-08-01"})
        self.assertIsNone(a["check_in"])
        b = bot._match_answers({"check_in": "2026-08-04", "check_out": "2026-08-01"})
        self.assertIsNone(b["check_in"])

    def test_malformed_budget_becomes_none(self):
        self.assertIsNone(bot._match_answers({"budget": "lots"})["budget_max"])


class TestMatchRouteOrder(unittest.TestCase):
    def test_match_route_is_registered_before_the_slug_catchall(self):
        """/stay/{slug} is a catch-all. Registered after it, /stay/match 404s."""
        with open("bot.py", encoding="utf-8") as f:
            src = f.read()
        i_match = src.index('add_get("/stay/match"')
        i_slug = src.index('add_get("/stay/{slug}"')
        self.assertLess(i_match, i_slug,
                        "/stay/match must be registered before /stay/{slug}")


class TestMatchRunParallelAvailability(unittest.TestCase):
    """_match_run fans the unit_availability_price calls out across a
    ThreadPoolExecutor (see bot.py, same pool pattern as
    enrich_catalog_for_dates). These tests are hermetic: _gw_visible_snaps,
    _gw_listing_public, _elite_geo_refresh and _match_geo_points are all
    stubbed, so nothing here touches the network or the live gw cache."""

    def setUp(self):
        self.snaps = _fake_visible_snaps(53)
        self.patches = [
            mock.patch.object(bot, "_gw_visible_snaps", return_value=self.snaps),
            mock.patch.object(bot, "_gw_listing_public", side_effect=_fake_listing_public),
            mock.patch.object(bot, "_elite_geo_refresh", return_value=None),
            mock.patch.object(bot, "_match_geo_points", return_value={}),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_every_visible_unit_checked_exactly_once(self):
        calls = []

        def stub_avail(lid, ci, co):
            calls.append(lid)
            return {"available": True, "nights": 3, "total": 900, "avg": 300}

        with mock.patch.object(bot, "unit_availability_price", side_effect=stub_avail):
            out = bot._match_run({"check_in": "2026-08-01", "check_out": "2026-08-04"})

        self.assertEqual(sorted(calls), [s["id"] for s, _ov in self.snaps])
        self.assertEqual(len(calls), len(set(calls)), "a unit was fetched more than once")
        self.assertIsInstance(out, dict)

    def test_one_unit_raising_does_not_fail_the_request(self):
        def stub_avail(lid, ci, co):
            if lid == 7:
                raise RuntimeError("simulated Hostaway failure for unit 7")
            return {"available": True, "nights": 3, "total": 900, "avg": 300}

        with mock.patch.object(bot, "unit_availability_price", side_effect=stub_avail):
            out = bot._match_run({"check_in": "2026-08-01", "check_out": "2026-08-04"})

        self.assertIsInstance(out, dict)
        self.assertIn("top", out)
        self.assertFalse(out.get("impossible"))


class TestGwSearchParallelAvailability(unittest.TestCase):
    """_gw_search fans the unit_availability_price calls, for units that
    survive the cheap guests/type/area/neighborhood/tags filters, out across
    a ThreadPoolExecutor (see bot.py, same pool pattern as
    enrich_catalog_for_dates and _match_run). Hermetic: _gw_visible_snaps and
    _gw_listing_public are stubbed, so nothing here touches the network or
    the live gw cache."""

    def setUp(self):
        self.snaps = _fake_snaps_for_search(53)
        self.patches = [
            mock.patch.object(bot, "_gw_visible_snaps", return_value=self.snaps),
            mock.patch.object(bot, "_gw_listing_public", side_effect=_fake_gw_listing_public),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_identical_results_regardless_of_completion_order(self):
        """Result ids + order are driven by sort_key data (availability first,
        then name_ar), never by which ThreadPoolExecutor future completes
        first -- the parallelisation must not change the returned list."""
        def stub_avail(lid, ci, co):
            if lid == 3:
                return {"available": False, "nights": 3, "total": 0, "avg": 0}
            return {"available": True, "nights": 3, "total": 900, "avg": 300}

        with mock.patch.object(bot, "unit_availability_price", side_effect=stub_avail):
            out = bot._gw_search(ci="2026-08-01", co="2026-08-04")

        # unit 3 is unavailable -> excluded; every survivor is available so
        # sort_key falls through to name_ar ascending. name_ar is a plain
        # string ("unit-1", "unit-2", ...) so this is lexicographic, not
        # numeric, sort -- computed independently here rather than assumed.
        expected = sorted((i for i in range(1, 54) if i != 3), key=lambda i: "unit-%s" % i)
        self.assertEqual([r["id"] for r in out["results"]], expected)

    def test_every_surviving_unit_checked_exactly_once(self):
        calls = []

        def stub_avail(lid, ci, co):
            calls.append(lid)
            return {"available": True, "nights": 3, "total": 900, "avg": 300}

        with mock.patch.object(bot, "unit_availability_price", side_effect=stub_avail):
            out = bot._gw_search(ci="2026-08-01", co="2026-08-04")

        self.assertEqual(sorted(calls), [s["id"] for s, _ov in self.snaps])
        self.assertEqual(len(calls), len(set(calls)), "a unit was fetched more than once")
        self.assertEqual(len(out["results"]), 53)

    def test_filters_shortcut_the_availability_work(self):
        """A neighborhood filter that excludes most units must shrink the
        set BEFORE availability is checked -- unit_availability_price should
        only be called for the units that survive filtering."""
        neighborhoods = {i: ("olaya" if i == 1 else "other") for i in range(1, 54)}
        snaps = _fake_snaps_for_search(53, neighborhoods=neighborhoods)
        calls = []

        def stub_avail(lid, ci, co):
            calls.append(lid)
            return {"available": True, "nights": 3, "total": 900, "avg": 300}

        with mock.patch.object(bot, "_gw_visible_snaps", return_value=snaps), \
             mock.patch.object(bot, "unit_availability_price", side_effect=stub_avail):
            out = bot._gw_search(ci="2026-08-01", co="2026-08-04", neighborhood="olaya")

        self.assertEqual(calls, [1])
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(out["results"][0]["id"], 1)

    def test_one_unit_raising_does_not_fail_the_request(self):
        def stub_avail(lid, ci, co):
            if lid == 7:
                raise RuntimeError("simulated Hostaway failure for unit 7")
            return {"available": True, "nights": 3, "total": 900, "avg": 300}

        with mock.patch.object(bot, "unit_availability_price", side_effect=stub_avail):
            out = bot._gw_search(ci="2026-08-01", co="2026-08-04")

        # unit 7's failed lookup keeps avail=None -> avail_error, but the
        # unit still comes back (unpriced) and every other unit is unaffected.
        self.assertTrue(out["avail_error"])
        self.assertEqual(len(out["results"]), 53)


class TestMatchEventKeys(unittest.TestCase):
    def test_event_whitelist_carries_match_fields(self):
        src = open("bot.py", encoding="utf-8").read()
        i = src.index("async def _api_stay_event")
        block = src[i:i + 1200]
        for key in ('"type"', '"guests"', '"count"', '"weak"'):
            self.assertIn(key, block, f"{key} missing from the event whitelist")


class TestMatchStats(unittest.TestCase):
    def test_empty_store_returns_zeros_not_crash(self):
        out = bot._match_stats(30)
        self.assertIn("funnel", out)
        self.assertIn("unmet", out)
        self.assertEqual(out["completion"], 0.0)

    def test_funnel_and_unmet_demand_from_synthetic_events(self):
        now = bot.datetime.now(bot.TZ).isoformat(timespec="seconds")
        events = (
            [{"event": "match_start", "ts": now}] * 4
            + [{"event": "match_answer", "type": "who", "ts": now}] * 3
            + [{"event": "match_answer", "type": "purpose", "ts": now}] * 2
            + [{"event": "match_abandon", "type": "sleep", "ts": now}]
            + [{"event": "match_results", "ts": now, "guests": 4, "type": "family",
                "count": 0, "weak": 1}] * 3
            + [{"event": "match_results", "ts": now, "guests": 2, "type": "rest",
                "count": 5, "weak": 0}]
        )
        with mock.patch.object(bot, "_gw_analytics", {"events": events}):
            out = bot._match_stats(30)
        self.assertEqual(out["funnel"]["start"], 4)
        self.assertEqual(out["funnel"]["who"], 3)
        self.assertEqual(out["funnel"]["purpose"], 2)
        self.assertEqual(out["funnel"]["abandon"], 1)
        self.assertEqual(out["funnel"]["results"], 4)
        self.assertEqual(out["completion"], 100.0)
        self.assertEqual(len(out["unmet"]), 1)
        row = out["unmet"][0]
        self.assertEqual((row["purpose"], row["party"]), ("family", 4))
        self.assertEqual(row["asked"], 3)
        self.assertEqual(row["weak"], 3)
        self.assertEqual(row["weak_pct"], 100.0)

    def test_stats_endpoint_is_registered_behind_auth(self):
        src = open("bot.py", encoding="utf-8").read()
        i = src.index("async def _api_stay_match_stats")
        self.assertIn("_dash_auth", src[i:i + 400],
                      "match-stats must be behind _dash_auth")


class TestGwParseCoords(unittest.TestCase):
    """_gw_parse_coords: raw Hostaway listing -> (lat, lng) or (None, None).
    Pure function, no network -- hermetic by construction."""

    def test_lat_lng_fields_parsed(self):
        lat, lng = bot._gw_parse_coords({"lat": 24.7136, "lng": 46.6753})
        self.assertEqual((lat, lng), (24.7136, 46.6753))

    def test_falls_back_to_latitude_longitude_spelling(self):
        lat, lng = bot._gw_parse_coords({"latitude": 24.7136, "longitude": 46.6753})
        self.assertEqual((lat, lng), (24.7136, 46.6753))

    def test_lat_lng_preferred_over_latitude_longitude(self):
        lat, lng = bot._gw_parse_coords({"lat": 24.7, "lng": 46.6,
                                          "latitude": 25.5, "longitude": 47.5})
        self.assertEqual((lat, lng), (24.7, 46.6))

    def test_out_of_riyadh_coordinates_rejected(self):
        # New York City -- nowhere near Riyadh's bounding box.
        lat, lng = bot._gw_parse_coords({"lat": 40.7128, "lng": -74.0060})
        self.assertIsNone(lat)
        self.assertIsNone(lng)

    def test_malformed_values_never_raise(self):
        for L in ({"lat": "abc", "lng": "xyz"}, {"lat": None, "lng": None},
                  {"lat": {}, "lng": []}, {"lat": [1, 2], "lng": {"x": 1}}, {}):
            lat, lng = bot._gw_parse_coords(L)
            self.assertIsNone(lat)
            self.assertIsNone(lng)


class TestMatchGeoPoints(unittest.TestCase):
    """_match_geo_points: Hostaway lat/lng (preferred) -> guide-cache coords
    (fallback) -> no entry (engine's centroid fallback engages). Hermetic:
    _gw_visible_snaps, _gw_listing_public and _elite_geo_cache are all stubbed."""

    def _patch(self, snaps, gmap=None):
        patches = [
            mock.patch.object(bot, "_gw_visible_snaps", return_value=snaps),
            mock.patch.object(bot, "_gw_listing_public", side_effect=_fake_geo_listing_public),
            mock.patch.object(bot, "_elite_geo_cache", {"map": gmap or {}, "ts": 0.0}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_hostaway_coords_preferred_when_both_exist(self):
        snaps = [({"id": 1, "lat": 24.70, "lng": 46.60, "name_en": "Ouja A"}, {})]
        self._patch(snaps, gmap={"ouja a": (24.90, 46.90)})
        pts = bot._match_geo_points()
        self.assertEqual(pts[1], (24.70, 46.60))

    def test_guide_coords_used_when_hostaway_has_none(self):
        snaps = [({"id": 2, "lat": None, "lng": None, "name_en": "Ouja B"}, {})]
        self._patch(snaps, gmap={"ouja b": (24.80, 46.70)})
        pts = bot._match_geo_points()
        self.assertEqual(pts[2], (24.80, 46.70))

    def test_unit_with_neither_source_yields_no_entry(self):
        snaps = [({"id": 3, "lat": None, "lng": None, "name_en": "Ouja C"}, {})]
        self._patch(snaps, gmap={})
        pts = bot._match_geo_points()
        self.assertNotIn(3, pts)
        self.assertEqual(pts, {})

    def test_detail_breakdown_counts_each_source_separately(self):
        snaps = [
            ({"id": 1, "lat": 24.70, "lng": 46.60, "name_en": "A"}, {}),
            ({"id": 2, "lat": None, "lng": None, "name_en": "B"}, {}),
            ({"id": 3, "lat": None, "lng": None, "name_en": "C"}, {}),
        ]
        self._patch(snaps, gmap={"b": (24.80, 46.70)})
        pts, src = bot._match_geo_points(detail=True)
        self.assertEqual(len(pts), 2)
        self.assertEqual(src, {"from_hostaway": 1, "from_guide": 1})


if __name__ == "__main__":
    unittest.main()
