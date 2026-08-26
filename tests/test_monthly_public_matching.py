import json
import unittest

from monthly_public.matching import catalog_claim, rank
from monthly_public.snapshot import build_generation
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


def listing(listing_id, *, rate=12000, facts=None, coordinates=None, **overrides):
    source = valid_listing(
        id=listing_id,
        slug="ouja-%s" % listing_id,
        name_ar="عوجا | بيت %s بغرفتين" % listing_id,
        name_en="Ouja | 2BR home %s" % listing_id,
        facts=facts or {},
        coordinates=coordinates
        or {
            "lat": 24.80,
            "lng": 46.62,
            "verified": True,
            "source": "approved_listing_coordinates",
        },
        official_prices={
            "2026-09": {
                "monthly_rate_sar": rate,
                "currency": "SAR",
                "source": "engine_verified",
                "verified_at": "2026-08-25T09:30:00+03:00",
            }
        },
    )
    source.update(overrides)
    return source


def generation(*listings):
    return build_generation(
        {
            "refresh_ok": True,
            "catalog_complete": True,
            "listings": list(listings),
            "source_timestamps": {},
        },
        valid_settings(),
        NOW,
    )


def request(**overrides):
    value = {
        "purpose": "work",
        "place": {"kind": "neighborhood", "id": "al_malqa", "label": "الملقا"},
        "residents": 2,
        "sleeping": "one_bedroom",
        "price_priority": "experience",
        "move_in": "2026-09-01",
        "duration_months": 1,
        "flexibility": "fixed",
    }
    value.update(overrides)
    return value


class MatchingEligibilityTests(unittest.TestCase):
    def test_capacity_sleeping_and_price_are_hard_gates(self):
        result = rank(
            generation(
                listing(1001, capacity=1),
                listing(1002, bedrooms=1, beds=1, beds_count=1),
                listing(1003, official_prices={}),
                listing(1004, bedrooms=2, beds=2, beds_count=3, capacity=4),
            ),
            request(residents=3, sleeping="two_bedrooms"),
            "ar",
            now=NOW,
        )
        self.assertEqual([item["id"] for item in result["top"]], ["1004"])

    def test_blocked_dates_never_become_exact_matches(self):
        blocked = listing(1001)
        blocked["calendar"]["blocked_dates"] = ["2026-09-10"]
        result = rank(
            generation(blocked, listing(1002)), request(), "en", now=NOW
        )
        self.assertEqual([item["id"] for item in result["top"]], ["1002"])
        self.assertEqual([item["id"] for item in result["catalog"]], ["1002"])
        self.assertEqual(result["unavailable_count"], 1)

    def test_stale_calendar_is_pending_and_not_an_exact_claim(self):
        stale = listing(1001)
        stale["calendar"]["synced_at"] = "2026-08-25T08:00:00+03:00"
        result = rank(generation(stale), request(), "ar", now=NOW)
        self.assertEqual(result["top"], ())
        self.assertEqual(result["catalog"], ())
        self.assertEqual(result["pending_count"], 1)
        self.assertEqual(result["empty_state"]["code"], "availability_pending")

    def test_irrelevant_pending_home_does_not_mask_a_real_no_match_state(self):
        stale = listing(1001, capacity=1)
        stale["calendar"]["synced_at"] = "2026-08-25T08:00:00+03:00"

        result = rank(generation(stale), request(residents=5), "en", now=NOW)

        self.assertEqual(result["empty_state"]["code"], "no_exact_match")

    def test_plus_minus_seven_days_returns_a_named_near_match(self):
        flexible = listing(1001)
        flexible["calendar"]["blocked_dates"] = ["2026-09-01"]
        result = rank(
            generation(flexible),
            request(flexibility="plus_minus_7"),
            "en",
            now=NOW,
        )
        self.assertEqual(result["top"], ())
        self.assertEqual(len(result["near_matches"]), 1)
        near = result["near_matches"][0]
        self.assertEqual(near["changed_condition"], "dates")
        self.assertNotEqual(near["adjusted_move_in"], "2026-09-01")
        self.assertEqual(near["reason_codes"][0], "date_adjusted_available")
        self.assertIn("adjusted", near["reasons"][0].lower())

    def test_flexible_dates_can_move_into_verified_calendar_coverage(self):
        flexible = listing(1001)
        flexible["calendar"]["from"] = "2026-09-02"

        result = rank(
            generation(flexible),
            request(flexibility="plus_minus_7"),
            "en",
            now=NOW,
        )

        self.assertEqual(result["top"], ())
        self.assertEqual(result["near_matches"][0]["adjusted_move_in"], "2026-09-02")
        self.assertEqual(result["empty_state"]["code"], "near_matches")


class MatchingRankingTests(unittest.TestCase):
    def test_each_purpose_uses_only_verified_need_facts(self):
        cases = (
            ("work", {"workspace": True}),
            ("family", {"kids_ok": True, "full_kitchen": True, "washer": True}),
            ("treatment", {"elderly_friendly": True, "elevator": True}),
            ("visit", {"parking": True, "private_entrance": True}),
        )
        for purpose, facts in cases:
            with self.subTest(purpose=purpose):
                place = None if purpose == "family" else request()["place"]
                ranked = rank(
                    generation(listing(1001), listing(1002, facts=facts)),
                    request(purpose=purpose, place=place),
                    "en",
                    now=NOW,
                )
                self.assertEqual(ranked["top"][0]["id"], "1002")

    def test_verified_proximity_affects_fit_without_travel_time(self):
        places = {
            "kafd": {
                "lat": 24.7649,
                "lng": 46.6408,
                "verified": True,
                "source": "approved_destination_registry",
                "label_ar": "كافد",
                "label_en": "KAFD",
            }
        }
        ranked = rank(
            generation(
                listing(1001, coordinates={"lat": 24.765, "lng": 46.641, "verified": True, "source": "approved_listing_coordinates"}),
                listing(1002, coordinates={"lat": 24.90, "lng": 46.80, "verified": True, "source": "approved_listing_coordinates"}),
            ),
            request(place={"kind": "destination", "id": "kafd", "label": "KAFD"}),
            "en",
            now=NOW,
            places=places,
        )
        self.assertEqual(ranked["top"][0]["id"], "1001")
        payload = json.dumps(ranked).lower()
        self.assertNotIn("minutes", payload)
        self.assertNotIn("travel_time", payload)

    def test_proximity_claim_uses_the_approved_registry_label(self):
        ranked = rank(
            generation(listing(1001)),
            request(
                place={
                    "kind": "destination",
                    "id": "kafd",
                    "label": "Unapproved customer label",
                }
            ),
            "en",
            now=NOW,
            places={
                "kafd": {
                    "lat": 24.7649,
                    "lng": 46.6408,
                    "verified": True,
                    "source": "approved_destination_registry",
                    "label_ar": "كافد",
                    "label_en": "KAFD",
                }
            },
        )
        reasons = " ".join(ranked["top"][0]["reasons"])
        self.assertIn("KAFD", reasons)
        self.assertNotIn("Unapproved customer label", reasons)

    def test_verified_neighborhood_affects_fit(self):
        ranked = rank(
            generation(
                listing(1001, neighborhood="al_nada", neighborhood_ar="الندى", neighborhood_en="Al Nada"),
                listing(1002),
            ),
            request(),
            "en",
            now=NOW,
        )
        self.assertEqual(ranked["top"][0]["id"], "1002")

    def test_verified_quality_breaks_equal_fit_before_price(self):
        ranked = rank(
            generation(
                listing(1001, rate=14000, rating=4.95, reviews_count=80),
                listing(1002, rate=10000, rating=4.10, reviews_count=8),
            ),
            request(),
            "en",
            now=NOW,
        )
        self.assertEqual(ranked["top"][0]["id"], "1001")

    def test_unverified_destination_has_no_place_score_or_claim(self):
        ranked = rank(
            generation(listing(1002), listing(1001)),
            request(place={"kind": "destination", "id": "kafd", "label": "KAFD"}),
            "en",
            now=NOW,
            places={"kafd": {"lat": 24.7, "lng": 46.6, "verified": False}},
        )
        self.assertEqual(ranked["top"][0]["id"], "1001")
        self.assertNotIn("KAFD", " ".join(ranked["top"][0]["reasons"]))

    def test_price_breaks_equal_fit_only_and_cannot_buy_rank(self):
        stronger = listing(1001, rate=18000, facts={"workspace": True})
        weaker = listing(1002, rate=9000)
        ranked = rank(
            generation(stronger, weaker), request(), "en", now=NOW
        )
        self.assertEqual(ranked["top"][0]["id"], "1001")

        equal = rank(
            generation(listing(1003, rate=14000), listing(1004, rate=10000)),
            request(),
            "en",
            now=NOW,
        )
        self.assertEqual(equal["top"][0]["id"], "1004")

    def test_lowest_suitable_orders_verified_matches_by_total_price(self):
        ranked = rank(
            generation(
                listing(1001, rate=18000, facts={"workspace": True}),
                listing(1002, rate=9000),
            ),
            request(price_priority="lowest_suitable"),
            "en",
            now=NOW,
        )

        self.assertEqual(ranked["top"][0]["id"], "1002")
        self.assertEqual(ranked["price_priority"], "lowest_suitable")

    def test_value_priority_balances_fit_and_total_price(self):
        ranked = rank(
            generation(
                listing(1001, rate=30000, facts={"workspace": True}),
                listing(1002, rate=9000),
            ),
            request(price_priority="value"),
            "en",
            now=NOW,
        )

        self.assertEqual(ranked["top"][0]["id"], "1002")
        self.assertEqual(ranked["price_priority"], "value")

    def test_experience_priority_keeps_verified_fit_ahead_of_price(self):
        ranked = rank(
            generation(
                listing(1001, rate=30000, facts={"workspace": True}),
                listing(1002, rate=9000),
            ),
            request(price_priority="experience"),
            "en",
            now=NOW,
        )

        self.assertEqual(ranked["top"][0]["id"], "1001")

    def test_top_three_alternatives_and_catalog_partition_is_truthful(self):
        ranked = rank(
            generation(*(listing(1000 + number, rate=10000 + number) for number in range(1, 7))),
            request(),
            "ar",
            now=NOW,
        )
        self.assertEqual(len(ranked["top"]), 3)
        self.assertEqual(len(ranked["alternatives"]), 3)
        self.assertEqual(len(ranked["catalog"]), 6)
        self.assertEqual(ranked["exact_count"], 6)
        self.assertEqual(
            {item["id"] for item in ranked["top"] + ranked["alternatives"]},
            {item["id"] for item in ranked["catalog"]},
        )

    def test_reasons_and_tradeoff_come_from_known_facts_and_prices(self):
        ranked = rank(
            generation(
                listing(1001, rate=15000, facts={"workspace": True, "parking": True}),
                listing(1002, rate=12000, facts={"workspace": True}),
            ),
            request(),
            "en",
            now=NOW,
        )
        first = next(item for item in ranked["top"] if item["id"] == "1001")
        self.assertTrue(any("workspace" in reason.lower() for reason in first["reasons"]))
        self.assertGreaterEqual(len(first["reasons"]), 2)
        self.assertLessEqual(len(first["reasons"]), 4)
        self.assertIn("purpose_workspace", first["reason_codes"])
        self.assertIn("SAR 3,000", first["tradeoff"])


class EmptyAndCountTests(unittest.TestCase):
    def test_no_legitimate_alternative_returns_honest_empty_state(self):
        result = rank(
            generation(listing(1001, capacity=1)),
            request(residents=5),
            "ar",
            now=NOW,
        )
        self.assertEqual(result["top"], ())
        self.assertEqual(result["near_matches"], ())
        self.assertEqual(result["empty_state"]["code"], "no_exact_match")

    def test_catalog_claim_uses_the_computed_eligible_count(self):
        self.assertEqual(catalog_claim(49, "en"), "49 furnished homes")
        self.assertEqual(catalog_claim(50, "ar"), "50 بيتًا مفروشًا")
        self.assertEqual(catalog_claim(57, "ar"), "أكثر من 50 بيتًا مفروشًا")
        self.assertEqual(catalog_claim(57, "en"), "50+ furnished homes")


if __name__ == "__main__":
    unittest.main()
