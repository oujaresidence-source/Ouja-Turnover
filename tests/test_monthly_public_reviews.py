import json
import unittest


from monthly_public.reviews import build_review_projections, sanitize_review_projection


def review(
    review_id,
    listing_id,
    date,
    text,
    guest="Guest Name",
    *,
    rating=5,
    is_public=True,
    **overrides
):
    row = {
        "id": review_id,
        "listing_id": listing_id,
        "rating": rating,
        "guest_name": guest,
        "public_review": text,
        "private_review": "internal private note",
        "channel": "Airbnb",
        "date": date,
        "is_public": is_public,
        "reservation_id": "reservation-%s" % review_id,
        "raw": {"secret": "provider payload"},
    }
    row.update(overrides)
    return row


class ReviewProjectionTests(unittest.TestCase):
    def test_projection_is_listing_specific_latest_and_private_safe(self):
        projections = build_review_projections(
            [
                review("r1", "1001", "2026-05-01", "نظيف وواسع", "Faisal Nassar"),
                review("r2", "1001", "2026-05-02", "ممتاز", "Sara Ahmed"),
                review("r3", "1002", "2026-05-03", "different home", "Other Guest"),
            ]
        )

        projection = projections["1001"]
        self.assertEqual(
            [row["id"] for row in projection["latest_reviews"]],
            ["r2", "r1"],
        )
        self.assertEqual(projection["latest_reviews"][0]["guest_name"], "Sara A.")
        self.assertEqual(projection["rating_value"], 5.0)
        self.assertEqual(projection["rating_count"], 2)
        payload = json.dumps(projection, ensure_ascii=False)
        for forbidden in (
            "private_review",
            "reservation_id",
            "provider payload",
            "different home",
            "Sara Ahmed",
        ):
            self.assertNotIn(forbidden, payload)

    def test_private_invalid_and_malformed_reviews_are_omitted(self):
        projections = build_review_projections(
            [
                review("private", "1001", "2026-05-01", "hidden", is_public=False),
                review("zero", "1001", "2026-05-01", "bad rating", rating=0),
                review("date", "1001", "not-a-date", "bad date"),
                review("listing", "bad listing!", "2026-05-01", "bad listing"),
            ]
        )

        self.assertEqual(projections, {})

    def test_ratings_without_text_count_in_aggregate_but_not_latest_ten(self):
        projection = build_review_projections(
            [
                review("r1", "1001", "2026-05-01", "نظيف", rating=5),
                review("r2", "1001", "2026-05-02", "", rating=4),
            ]
        )["1001"]

        self.assertEqual(projection["rating_value"], 4.5)
        self.assertEqual(projection["rating_count"], 2)
        self.assertEqual(projection["text_review_count"], 1)
        self.assertEqual(len(projection["latest_reviews"]), 1)

    def test_public_review_text_preserves_authored_line_breaks(self):
        original = "نظيف جدًا\nوالمضيف سريع الاستجابة"

        projected = build_review_projections(
            [review("r1", "1001", "2026-05-01", original)]
        )["1001"]["latest_reviews"][0]["text"]

        self.assertEqual(projected, original)

    def test_latest_reviews_are_capped_at_ten_with_stable_order(self):
        rows = [
            review(str(index), "1001", "2026-05-%02d" % index, "ممتاز")
            for index in range(1, 13)
        ]

        latest = build_review_projections(rows)["1001"]["latest_reviews"]

        self.assertEqual(len(latest), 10)
        self.assertEqual([row["id"] for row in latest[:3]], ["12", "11", "10"])

    def test_topic_mentions_are_counts_not_generated_claims(self):
        projection = build_review_projections(
            [
                review("r1", "1001", "2026-05-01", "الشقة نظيفة وواسعة"),
                review("r2", "1001", "2026-05-02", "Clean and spacious"),
                review("r3", "1001", "2026-05-03", "المضيف متعاون وسريع الاستجابة"),
            ]
        )["1001"]
        mentions = {row["key"]: row for row in projection["topic_mentions"]}

        self.assertEqual(mentions["cleanliness"], {"key": "cleanliness", "count": 2, "total": 3})
        self.assertEqual(mentions["space"], {"key": "space", "count": 2, "total": 3})
        self.assertEqual(mentions["service"], {"key": "service", "count": 1, "total": 3})

    def test_category_scores_require_matching_verified_insight_count(self):
        rows = [
            review("r1", "1001", "2026-05-01", "نظيف"),
            review("r2", "1001", "2026-05-02", "ممتاز"),
        ]
        matching = {
            "apartments": {
                "Unit 1001": {
                    "listing_id": "1001",
                    "count": 2,
                    "cats": {"cleanliness": 9.8, "location": 9.2},
                }
            }
        }
        conflict = {
            "apartments": {
                "Unit 1001": {
                    "listing_id": "1001",
                    "count": 3,
                    "cats": {"cleanliness": 10.0},
                }
            }
        }

        accepted = build_review_projections(rows, matching)["1001"]
        rejected = build_review_projections(rows, conflict)["1001"]

        self.assertEqual(
            accepted["category_scores"],
            (
                {"key": "cleanliness", "rating": 4.9, "scale": 5},
                {"key": "location", "rating": 4.6, "scale": 5},
            ),
        )
        self.assertEqual(rejected["category_scores"], ())

    def test_sanitizer_skips_a_malformed_row_without_hiding_later_reviews(self):
        projection = build_review_projections(
            [review("r1", "1001", "2026-08-24", "نظيف جدًا")]
        )["1001"]
        projection["latest_reviews"] = ("malformed",) + projection["latest_reviews"]

        sanitized = sanitize_review_projection(projection)

        self.assertEqual([row["id"] for row in sanitized["latest_reviews"]], ["r1"])
        self.assertNotIn("malformed", str(sanitized))


if __name__ == "__main__":
    unittest.main()
