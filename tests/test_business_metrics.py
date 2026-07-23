# -*- coding: utf-8 -*-
"""
Unit + golden-regression tests for business.metrics.compute_metrics.

compute_metrics is a PURE function: normalized raw payload -> metrics dict.
The numbers it emits get quoted in negotiations, so a silent regression is a
commercial risk, not a UI bug (superprompt §3). This suite locks the definitions.

Run:  python3 -m unittest tests.test_business_metrics
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from business.metrics import compute_metrics  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return json.load(fh)


class GoldenRegression(unittest.TestCase):
    """Frozen raw payload -> frozen expected metric outputs (superprompt §3)."""

    def test_golden_fixture_exact(self):
        raw = _load("business_raw_fixture.json")
        expected = _load("business_metrics_expected.json")
        got = compute_metrics(raw)
        # Compare via JSON round-trip so int/float/key-type differences surface clearly.
        self.assertEqual(
            json.loads(json.dumps(got, sort_keys=True)),
            json.loads(json.dumps(expected, sort_keys=True)),
        )


class MetricDefinitions(unittest.TestCase):
    """Each metric's definition, isolated, so a failure names the culprit."""

    def setUp(self):
        self.raw = _load("business_raw_fixture.json")
        self.m = compute_metrics(self.raw)

    def test_reservations_total_is_a_count(self):
        self.assertEqual(self.m["reservations_total"], 6)

    def test_guest_nights_sum_checkout_minus_checkin(self):
        # 1 + 2 + 1 + 3 + 1 + 1
        self.assertEqual(self.m["guest_nights"], 9)

    def test_unique_guests_distinct_guest_key(self):
        self.assertEqual(self.m["unique_guests"], 4)

    def test_returning_guests_have_two_or_more_stays(self):
        # ali (2) and omar (2)
        self.assertEqual(self.m["returning_guests"], 2)

    def test_repeat_guest_share_is_stays_by_returning_over_total(self):
        # ali's 2 + omar's 2 = 4 of 6
        self.assertAlmostEqual(self.m["repeat_guest_share"], round(4 / 6, 4))

    def test_avg_los(self):
        self.assertEqual(self.m["avg_los"], 1.5)

    def test_single_night_share(self):
        self.assertAlmostEqual(self.m["single_night_share"], round(4 / 6, 4))

    def test_reviews_published_requires_text_and_public(self):
        # V5 has empty text and public=false -> excluded
        self.assertEqual(self.m["reviews_published"], 4)

    def test_rating_avg_5_is_mean_of_ten_scale_halved(self):
        # (10 + 8 + 10 + 10) / 4 / 2 = 4.75
        self.assertEqual(self.m["rating_avg_5"], 4.75)

    def test_perfect_share_is_share_at_ten_of_ten(self):
        # 3 of 4 published are 10/10
        self.assertEqual(self.m["perfect_share"], 0.75)

    def test_category_avgs_per_category_over_published(self):
        self.assertEqual(
            self.m["category_avgs"],
            {
                "communication": 9.5,
                "checkin": 9.75,
                "accuracy": 9.25,
                "location": 9.0,
                "cleanliness": 9.25,
                "value": 9.0,
            },
        )

    def test_review_rate_published_over_reservations(self):
        self.assertAlmostEqual(self.m["review_rate"], round(4 / 6, 4))

    def test_review_lang_split(self):
        self.assertEqual(self.m["review_lang_split"], {"ar": 0.5, "en": 0.5})

    def test_reviews_by_quarter_is_continuous_with_zero_fill(self):
        qs = [row["q"] for row in self.m["reviews_by_quarter"]]
        self.assertEqual(
            qs,
            ["Q3'24", "Q4'24", "Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26", "Q2'26", "Q3'26"],
        )
        by_q = {row["q"]: row for row in self.m["reviews_by_quarter"]}
        self.assertEqual(by_q["Q1'25"]["count"], 0)
        self.assertIsNone(by_q["Q1'25"]["rating_avg_5"])
        self.assertEqual(by_q["Q4'24"]["rating_avg_5"], 4.0)

    def test_listings_active(self):
        self.assertEqual(self.m["listings_active"], 2)

    def test_listings_by_year_is_cumulative_created(self):
        self.assertEqual(self.m["listings_by_year"], {"2024": 1, "2025": 2, "2026": 3})

    def test_districts_covered_distinct(self):
        self.assertEqual(self.m["districts_covered"], 2)

    def test_unit_type_mix_by_bedrooms(self):
        self.assertEqual(self.m["unit_type_mix"], {"1": 1, "2": 1, "3": 1})

    def test_rating_distribution_counts_published_by_ten_scale(self):
        # published rating10: 10, 8, 10, 10  -> three 10s and one 8
        self.assertEqual(self.m["rating_distribution"], {"10": 3, "8": 1})


class EdgeCases(unittest.TestCase):
    """Empty and lang-detection paths must not divide-by-zero or crash."""

    def test_empty_payload_yields_zeroed_metrics_not_a_crash(self):
        m = compute_metrics(
            {"as_of": "2026-07-23", "channel": "airbnb",
             "window": {"start": "2024-07-23", "end": "2026-07-23"},
             "listings": [], "reservations": [], "reviews": []}
        )
        self.assertEqual(m["reservations_total"], 0)
        self.assertEqual(m["guest_nights"], 0)
        self.assertEqual(m["repeat_guest_share"], 0.0)
        self.assertEqual(m["rating_avg_5"], 0.0)
        self.assertEqual(m["review_rate"], 0.0)
        self.assertEqual(m["reviews_by_quarter"], [])
        self.assertEqual(m["category_avgs"], {})
        self.assertEqual(m["rating_distribution"], {})

    def test_language_is_detected_when_absent(self):
        # No explicit lang: Arabic script -> ar, Latin -> en.
        raw = {
            "as_of": "2026-07-23", "channel": "airbnb",
            "window": {"start": "2024-07-23", "end": "2026-07-23"},
            "listings": [], "reservations": [],
            "reviews": [
                {"id": 1, "listing_id": 1, "rating10": 10, "categories": {},
                 "text": "ممتاز", "date": "2025-01-01", "public": True},
                {"id": 2, "listing_id": 1, "rating10": 10, "categories": {},
                 "text": "Excellent", "date": "2025-01-01", "public": True},
            ],
        }
        self.assertEqual(compute_metrics(raw)["review_lang_split"], {"ar": 0.5, "en": 0.5})


if __name__ == "__main__":
    unittest.main()
