import unittest


from monthly_public.contracts import (
    ContractError,
    parse_browse_query,
    parse_event,
    parse_listing_request,
    parse_match_request,
    parse_outcome,
)


def valid_match_request(**overrides):
    request = {
        "purpose": "work",
        "place": {"kind": "destination", "id": "kafd", "label": "KAFD"},
        "residents": 2,
        "sleeping": "one_bedroom",
        "move_in": "2026-09-01",
        "duration_months": 2,
        "flexibility": "fixed",
    }
    request.update(overrides)
    return request


class MatchRequestContractTests(unittest.TestCase):
    def test_accepts_the_approved_request_shape(self):
        parsed = parse_match_request(valid_match_request())

        self.assertEqual(parsed["purpose"], "work")
        self.assertEqual(parsed["place"]["id"], "kafd")
        self.assertEqual(parsed["duration_months"], 2)
        self.assertNotIn("budget", parsed)

    def test_accepts_every_approved_purpose_branch(self):
        for purpose in ("work", "family", "treatment", "visit"):
            with self.subTest(purpose=purpose):
                request = valid_match_request(purpose=purpose)
                if purpose == "family":
                    request.pop("place")
                self.assertEqual(parse_match_request(request)["purpose"], purpose)

    def test_requires_a_place_for_destination_led_branches(self):
        for purpose in ("work", "treatment", "visit"):
            with self.subTest(purpose=purpose):
                request = valid_match_request(purpose=purpose)
                request.pop("place")
                with self.assertRaises(ContractError) as caught:
                    parse_match_request(request)
                self.assertEqual(caught.exception.field, "place")
                self.assertEqual(caught.exception.code, "required")

    def test_rejects_an_invalid_calendar_date_with_bilingual_error(self):
        with self.assertRaises(ContractError) as caught:
            parse_match_request(valid_match_request(move_in="2026-02-30"))

        error = caught.exception.as_dict()
        self.assertEqual(error["field"], "move_in")
        self.assertEqual(error["code"], "invalid_date")
        self.assertTrue(error["message_ar"])
        self.assertTrue(error["message_en"])

    def test_rejects_duration_outside_one_to_six_months(self):
        for duration in (0, 7):
            with self.subTest(duration=duration):
                with self.assertRaises(ContractError) as caught:
                    parse_match_request(valid_match_request(duration_months=duration))
                self.assertEqual(caught.exception.field, "duration_months")
                self.assertEqual(caught.exception.code, "out_of_range")

    def test_rejects_move_out_on_or_before_move_in(self):
        request = valid_match_request(move_out="2026-09-01")
        with self.assertRaises(ContractError) as caught:
            parse_match_request(request)
        self.assertEqual(caught.exception.field, "move_out")
        self.assertEqual(caught.exception.code, "invalid_range")

    def test_rejects_unknown_fields_that_can_change_business_behavior(self):
        with self.assertRaises(ContractError) as caught:
            parse_match_request(valid_match_request(budget_sar=8_000))
        self.assertEqual(caught.exception.field, "budget_sar")
        self.assertEqual(caught.exception.code, "unknown_field")

    def test_rejects_unknown_place_fields(self):
        request = valid_match_request(
            place={"kind": "destination", "id": "kafd", "label": "KAFD", "minutes": 9}
        )
        with self.assertRaises(ContractError) as caught:
            parse_match_request(request)
        self.assertEqual(caught.exception.field, "place.minutes")


class OtherPublicContractTests(unittest.TestCase):
    def test_browse_query_accepts_only_approved_filters(self):
        parsed = parse_browse_query(
            {
                "move_in": "2026-10-01",
                "duration_months": "3",
                "bedrooms": "2",
                "residents": "4",
                "neighborhood": "Al Nada",
                "place": {"kind": "destination", "id": "kafd", "label": "KAFD"},
                "flexibility": "plus_minus_7",
                "lang": "en",
            }
        )
        self.assertEqual(parsed["duration_months"], 3)
        self.assertEqual(parsed["bedrooms"], 2)
        self.assertEqual(parsed["lang"], "en")

        with self.assertRaises(ContractError) as caught:
            parse_browse_query({"sort": "highest_price"})
        self.assertEqual(caught.exception.code, "unknown_field")

    def test_listing_request_requires_a_listing_identifier(self):
        parsed = parse_listing_request(
            {
                "listing_id": 536998,
                "move_in": "2026-09-01",
                "duration_months": 2,
                "lang": "ar",
            }
        )
        self.assertEqual(parsed["listing_id"], "536998")

        with self.assertRaises(ContractError) as caught:
            parse_listing_request({"lang": "ar"})
        self.assertEqual(caught.exception.field, "listing_id")

    def test_event_keeps_only_minimal_anonymous_utm_free_context(self):
        parsed = parse_event(
            {
                "event": "listing_view",
                "session_id": "anon_12345678",
                "context": {
                    "language": "ar",
                    "device_class": "mobile",
                    "listing_id": "536998",
                    "purpose": "work",
                    "utm_source": "campaign",
                    "name": "Not stored",
                    "phone": "0500000000",
                    "message": "Not stored",
                },
            }
        )

        self.assertEqual(
            parsed["context"],
            {
                "language": "ar",
                "device_class": "mobile",
                "listing_id": "536998",
                "purpose": "work",
            },
        )

    def test_event_rejects_unapproved_event_names(self):
        with self.assertRaises(ContractError) as caught:
            parse_event({"event": "raw_message", "session_id": "anon_12345678"})
        self.assertEqual(caught.exception.field, "event")
        self.assertEqual(caught.exception.code, "unsupported")

    def test_event_rejects_unknown_top_level_fields(self):
        with self.assertRaises(ContractError) as caught:
            parse_event(
                {
                    "event": "landing_view",
                    "session_id": "anon_12345678",
                    "customer_name": "Not allowed",
                }
            )
        self.assertEqual(caught.exception.field, "customer_name")

    def test_outcome_uses_only_controlled_lost_reasons(self):
        parsed = parse_outcome(
            {
                "lead_reference": "OJM-20260825-ABC123",
                "outcome": "lost",
                "lost_reason": "unavailable_dates",
            }
        )
        self.assertEqual(parsed["lost_reason"], "unavailable_dates")

        with self.assertRaises(ContractError) as caught:
            parse_outcome(
                {
                    "lead_reference": "OJM-20260825-ABC123",
                    "outcome": "lost",
                    "lost_reason": "customer said something else",
                }
            )
        self.assertEqual(caught.exception.field, "lost_reason")
        self.assertEqual(caught.exception.code, "unsupported")

    def test_booked_outcome_cannot_carry_a_lost_reason(self):
        with self.assertRaises(ContractError) as caught:
            parse_outcome(
                {
                    "lead_reference": "OJM-20260825-ABC123",
                    "outcome": "booked",
                    "lost_reason": "price",
                }
            )
        self.assertEqual(caught.exception.field, "lost_reason")
        self.assertEqual(caught.exception.code, "not_allowed")


if __name__ == "__main__":
    unittest.main()
