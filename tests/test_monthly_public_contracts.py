import unittest


from monthly_public.contracts import (
    ContractError,
    parse_browse_query,
    parse_event,
    parse_listing_request,
    parse_match_request,
    parse_outcome,
)


ANON_SESSION = "anon_A1b2C3d4E5f6G7h8"


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
        request.pop("duration_months")
        with self.assertRaises(ContractError) as caught:
            parse_match_request(request)
        self.assertEqual(caught.exception.field, "move_out")
        self.assertEqual(caught.exception.code, "invalid_range")

    def test_move_out_only_derives_an_exact_calendar_month_duration(self):
        request = valid_match_request(move_out="2026-11-01")
        request.pop("duration_months")

        parsed = parse_match_request(request)

        self.assertEqual(parsed["move_out"], "2026-11-01")
        self.assertEqual(parsed["duration_months"], 2)
        self.assertEqual(parsed["duration_days"], 61)

    def test_move_out_only_accepts_a_chosen_date_between_month_anniversaries(self):
        request = valid_match_request(move_out="2026-11-15")
        request.pop("duration_months")

        parsed = parse_match_request(request)

        self.assertEqual(parsed["move_out"], "2026-11-15")
        self.assertEqual(parsed["duration_days"], 75)
        self.assertNotIn("duration_months", parsed)

    def test_required_date_selection_rejects_duration_and_move_out_together(self):
        with self.assertRaises(ContractError) as caught:
            parse_match_request(valid_match_request(move_out="2026-11-01"))
        self.assertEqual(caught.exception.field, "move_out")
        self.assertEqual(caught.exception.code, "mutually_exclusive")

    def test_move_out_only_rejects_stays_under_one_or_over_six_months(self):
        for move_out in ("2026-09-30", "2027-03-02"):
            with self.subTest(move_out=move_out):
                request = valid_match_request(move_out=move_out)
                request.pop("duration_months")
                with self.assertRaises(ContractError) as caught:
                    parse_match_request(request)
                self.assertEqual(caught.exception.field, "move_out")
                self.assertEqual(caught.exception.code, "out_of_range")

    def test_year_9999_date_math_returns_a_contract_error(self):
        request = valid_match_request(move_in="9999-12-01", move_out="9999-12-31")
        request.pop("duration_months")

        with self.assertRaises(ContractError) as caught:
            parse_match_request(request)

        self.assertEqual(caught.exception.field, "move_out")
        self.assertEqual(caught.exception.code, "unsupported_date")

    def test_boolean_text_and_oversized_numeric_values_are_rejected(self):
        with self.assertRaises(ContractError) as caught:
            parse_match_request(valid_match_request(residents=True))
        self.assertEqual(caught.exception.field, "residents")

        with self.assertRaises(ContractError) as caught:
            parse_match_request(valid_match_request(residents="9" * 1_000))
        self.assertEqual(caught.exception.field, "residents")
        self.assertEqual(caught.exception.code, "too_long")

    def test_numeric_abuse_bounds_are_not_inventory_claims(self):
        # These are request-size protections. Publication data remains the source
        # of truth for each home's real capacity and bedroom count.
        with self.assertRaises(ContractError) as caught:
            parse_match_request(valid_match_request(residents=51))
        self.assertEqual(caught.exception.code, "out_of_range")

        with self.assertRaises(ContractError) as caught:
            parse_browse_query({"bedrooms": 21})
        self.assertEqual(caught.exception.code, "out_of_range")

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

        with self.assertRaises(ContractError) as caught:
            parse_listing_request({"listing_id": True})
        self.assertEqual(caught.exception.field, "listing_id")
        self.assertEqual(caught.exception.code, "invalid_type")

        with self.assertRaises(ContractError) as caught:
            parse_listing_request(
                {"listing_id": "536998", "session_id": "0500000000"}
            )
        self.assertEqual(caught.exception.field, "session_id")

    def test_event_keeps_only_minimal_anonymous_utm_free_context(self):
        parsed = parse_event(
            {
                "event": "listing_view",
                "session_id": ANON_SESSION,
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
            parse_event({"event": "raw_message", "session_id": ANON_SESSION})
        self.assertEqual(caught.exception.field, "event")
        self.assertEqual(caught.exception.code, "unsupported")

    def test_public_event_rejects_server_and_staff_lifecycle_names(self):
        for event in ("lead_created", "team_response", "booked", "lost"):
            with self.subTest(event=event):
                with self.assertRaises(ContractError) as caught:
                    parse_event({"event": event, "session_id": ANON_SESSION})
                self.assertEqual(caught.exception.field, "event")
                self.assertEqual(caught.exception.code, "unsupported")

    def test_public_event_rejects_a_client_supplied_lead_reference(self):
        with self.assertRaises(ContractError) as caught:
            parse_event(
                {
                    "event": "whatsapp_click",
                    "session_id": ANON_SESSION,
                    "context": {"lead_reference": "OJM-20260825-ABC123"},
                }
            )
        self.assertEqual(caught.exception.field, "context.lead_reference")
        self.assertEqual(caught.exception.code, "not_allowed")

    def test_session_id_requires_a_high_entropy_anonymous_token(self):
        self.assertEqual(
            parse_event({"event": "landing_view", "session_id": ANON_SESSION})[
                "session_id"
            ],
            ANON_SESSION,
        )
        for session_id in ("0500000000", "anon_0500000000", "anon_short"):
            with self.subTest(session_id=session_id):
                with self.assertRaises(ContractError) as caught:
                    parse_event({"event": "landing_view", "session_id": session_id})
                self.assertEqual(caught.exception.field, "session_id")
                self.assertEqual(caught.exception.code, "invalid_format")

    def test_event_rejects_unknown_top_level_fields(self):
        with self.assertRaises(ContractError) as caught:
            parse_event(
                {
                    "event": "landing_view",
                    "session_id": ANON_SESSION,
                    "customer_name": "Not allowed",
                }
            )
        self.assertEqual(caught.exception.field, "customer_name")

    def test_matcher_answer_uses_controlled_options_and_typed_numbers(self):
        purpose = parse_event(
            {
                "event": "matcher_answer",
                "session_id": ANON_SESSION,
                "context": {"question": "purpose", "answer": "work"},
            }
        )
        residents = parse_event(
            {
                "event": "matcher_answer",
                "session_id": ANON_SESSION,
                "context": {"question": "residents", "answer": "4"},
            }
        )

        self.assertEqual(purpose["context"]["answer"], "work")
        self.assertEqual(residents["context"]["answer"], 4)

    def test_matcher_answer_cannot_store_a_phone_like_arbitrary_value(self):
        for question in ("purpose", "residents", "sleeping", "place"):
            with self.subTest(question=question):
                with self.assertRaises(ContractError) as caught:
                    parse_event(
                        {
                            "event": "matcher_answer",
                            "session_id": ANON_SESSION,
                            "context": {
                                "question": question,
                                "answer": "0500000000",
                            },
                        }
                    )
                self.assertEqual(caught.exception.field, "context.answer")

    def test_matcher_question_is_a_controlled_key(self):
        with self.assertRaises(ContractError) as caught:
            parse_event(
                {
                    "event": "matcher_answer",
                    "session_id": ANON_SESSION,
                    "context": {"question": "phone", "answer": "work"},
                }
            )
        self.assertEqual(caught.exception.field, "context.question")
        self.assertEqual(caught.exception.code, "unsupported")

    def test_matcher_answer_rejects_oversized_numeric_text(self):
        with self.assertRaises(ContractError) as caught:
            parse_event(
                {
                    "event": "matcher_answer",
                    "session_id": ANON_SESSION,
                    "context": {
                        "question": "residents",
                        "answer": "9" * 1_000,
                    },
                }
            )
        self.assertEqual(caught.exception.field, "context.answer")
        self.assertEqual(caught.exception.code, "too_long")

    def test_matcher_place_answer_requires_a_server_allowlist(self):
        event = {
            "event": "matcher_answer",
            "session_id": ANON_SESSION,
            "context": {"question": "place", "answer": "kafd"},
        }
        parsed = parse_event(event, allowed_place_ids={"kafd", "king_fahad_medical"})
        self.assertEqual(parsed["context"]["answer"], "kafd")

        for allowed in (None, {"kafd"}):
            with self.subTest(allowed=allowed):
                event["context"]["answer"] = "faisal_profile"
                with self.assertRaises(ContractError) as caught:
                    parse_event(event, allowed_place_ids=allowed)
                self.assertEqual(caught.exception.field, "context.answer")
                self.assertEqual(caught.exception.code, "not_allowed")

    def test_context_place_id_cannot_bypass_the_server_allowlist(self):
        event = {
            "event": "results_view",
            "session_id": ANON_SESSION,
            "context": {"place_id": "faisal_profile"},
        }
        with self.assertRaises(ContractError) as caught:
            parse_event(event, allowed_place_ids={"kafd"})
        self.assertEqual(caught.exception.field, "context.place_id")
        self.assertEqual(caught.exception.code, "not_allowed")

    def test_duration_band_is_derived_and_contradictions_are_rejected(self):
        base = {
            "event": "results_view",
            "session_id": ANON_SESSION,
            "context": {"move_in": "2026-09-01", "move_out": "2026-11-15"},
        }
        parsed = parse_event(base)
        self.assertEqual(parsed["context"]["duration_band"], "2_3_months")

        base["context"]["duration_band"] = "4_6_months"
        with self.assertRaises(ContractError) as caught:
            parse_event(base)
        self.assertEqual(caught.exception.field, "context.duration_band")
        self.assertEqual(caught.exception.code, "mismatch")

    def test_duration_band_without_validated_duration_is_rejected(self):
        with self.assertRaises(ContractError) as caught:
            parse_event(
                {
                    "event": "results_view",
                    "session_id": ANON_SESSION,
                    "context": {"duration_band": "2_3_months"},
                }
            )
        self.assertEqual(caught.exception.field, "context.duration_band")
        self.assertEqual(caught.exception.code, "unverified")

    def test_event_rank_has_an_abuse_safety_bound(self):
        with self.assertRaises(ContractError) as caught:
            parse_event(
                {
                    "event": "result_impression",
                    "session_id": ANON_SESSION,
                    "context": {"rank": 1_001},
                }
            )
        self.assertEqual(caught.exception.field, "context.rank")
        self.assertEqual(caught.exception.code, "out_of_range")

    def test_event_retains_a_validated_move_out_date(self):
        parsed = parse_event(
            {
                "event": "listing_view",
                "session_id": ANON_SESSION,
                "context": {
                    "move_in": "2026-09-01",
                    "move_out": "2026-11-01",
                },
            }
        )
        self.assertEqual(parsed["context"]["move_out"], "2026-11-01")

        with self.assertRaises(ContractError) as caught:
            parse_event(
                {
                    "event": "listing_view",
                    "session_id": ANON_SESSION,
                    "context": {
                        "move_in": "2026-09-01",
                        "move_out": "2026-02-30",
                    },
                }
            )
        self.assertEqual(caught.exception.field, "context.move_out")

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
