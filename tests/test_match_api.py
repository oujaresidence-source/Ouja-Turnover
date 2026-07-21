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


class TestMatchEventKeys(unittest.TestCase):
    def test_event_whitelist_carries_match_fields(self):
        src = open("bot.py", encoding="utf-8").read()
        i = src.index("async def _api_stay_event")
        block = src[i:i + 1200]
        for key in ('"type"', '"guests"', '"count"', '"weak"'):
            self.assertIn(key, block, f"{key} missing from the event whitelist")


if __name__ == "__main__":
    unittest.main()
