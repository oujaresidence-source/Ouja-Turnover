"""MUSAED early-check-in decisions, with synthetic Hostaway facts only."""

import tempfile
import unittest
from datetime import date, datetime
from unittest import mock

import bot


class TestEarlyCheckinIntent(unittest.TestCase):
    def test_natural_time_requests_are_detected(self):
        cases = {
            "أقدر أدخل الساعة 10 الصبح بدل 3؟": 600,
            "هل أقدر أدخل الساعة 12؟": 720,
            "ممكن التشيك ان الساعة ١٢ الظهر؟": 720,
            "Can I check in at 12 pm?": 720,
            "Can I arrive at noon?": 720,
        }
        for text, minutes in cases.items():
            with self.subTest(text=text):
                self.assertEqual(
                    bot._early_checkin_request(text)["requested_minutes"], minutes)

    def test_explicit_early_request_without_time_is_detected(self):
        got = bot._early_checkin_request("ابي ادخل بدري")
        self.assertIsNotNone(got)
        self.assertIsNone(got["requested_minutes"])

    def test_latest_guest_message_scopes_the_intent(self):
        history = (
            "Guest: Can I check in early?\n"
            "Host: Official time is 3 PM\n"
            "Guest: Thanks"
        )
        self.assertIsNone(
            bot._early_checkin_request(bot._latest_guest_line(history)))

    def test_regular_three_pm_checkin_is_not_early(self):
        self.assertIsNone(bot._early_checkin_request("Can I check in at 3 pm?"))


class TestCalendarNightState(unittest.TestCase):
    def test_states_do_not_conflate_failure_with_occupancy(self):
        samples = [
            ({"result": [{"isAvailable": 1}]}, "free"),
            ({"result": [{"isAvailable": 0, "reservationId": 99}]}, "occupied"),
            ({"result": [{"isAvailable": 0}]}, "blocked"),
            ({"result": []}, "unknown"),
        ]
        for payload, expected in samples:
            with self.subTest(expected=expected), mock.patch.object(
                    bot, "api_get", return_value=payload):
                self.assertEqual(
                    bot._calendar_night_state(7, date(2026, 8, 4)), expected)

    def test_api_error_is_unknown(self):
        with mock.patch.object(bot, "api_get", side_effect=RuntimeError("down")):
            self.assertEqual(
                bot._calendar_night_state(7, date(2026, 8, 4)), "unknown")


class TestEarlyCheckinContext(unittest.TestCase):
    ROWS = [
        {"id": 10, "listingMapId": 7, "status": "new", "guestName": "Previous",
         "arrivalDate": "2026-08-01", "departureDate": "2026-08-05"},
        {"id": 11, "listingMapId": 7, "status": "new", "guestName": "Current",
         "arrivalDate": "2026-08-05", "departureDate": "2026-08-08"},
        {"id": 12, "listingMapId": 7, "status": "modified", "guestName": "Next",
         "arrivalDate": "2026-08-08", "departureDate": "2026-08-10"},
        {"id": 13, "listingMapId": 8, "status": "new", "guestName": "Other unit",
         "arrivalDate": "2026-08-04", "departureDate": "2026-08-09"},
        {"id": 14, "listingMapId": 7, "status": "cancelled", "guestName": "Cancelled",
         "arrivalDate": "2026-08-04", "departureDate": "2026-08-05"},
    ]

    def test_neighbor_summary_uses_same_listing_and_realized_stays(self):
        got = bot._early_checkin_context_from_rows(
            7, 11, date(2026, 8, 5), date(2026, 8, 8), self.ROWS)
        self.assertEqual(got["previous"]["guest"], "Previous")
        self.assertEqual(got["next"]["guest"], "Next")

    def test_unknown_calendar_remains_unknown(self):
        reservation = {"result": {"id": 11, "listingMapId": 7,
                                   "arrivalDate": "2026-08-05",
                                   "departureDate": "2026-08-08"}}
        with mock.patch.object(bot, "api_get", return_value=reservation), \
             mock.patch.object(bot, "_calendar_night_state", return_value="unknown"), \
             mock.patch.object(bot, "fetch_reservations_window", return_value=self.ROWS):
            got = bot.early_checkin_context(11, 7)
        self.assertEqual(got["previous_night_state"], "unknown")
        self.assertIsNone(got["prev_occupied"])
        self.assertEqual(got["alternatives"], [])

    def test_alternative_needs_free_previous_night_and_full_stay(self):
        reservation = {"result": {"id": 11, "listingMapId": 7,
                                   "arrivalDate": "2026-08-05",
                                   "departureDate": "2026-08-08"}}
        units = [
            {"id": 8, "name": "Free and available", "beds": 2, "area": "الملقا"},
            {"id": 9, "name": "Previous night blocked", "beds": 2, "area": "الملقا"},
            {"id": 10, "name": "Stay unavailable", "beds": 2, "area": "الملقا"},
        ]

        def night_state(lid, _day):
            return "blocked" if lid == 9 else ("occupied" if lid == 7 else "free")

        def availability(lid, _arrival, _departure):
            return {"available": lid != 10, "nights": 3, "total": 1800, "avg": 600}

        with mock.patch.object(bot, "api_get", return_value=reservation), \
             mock.patch.object(bot, "_catalog_units", units), \
             mock.patch.object(bot, "_calendar_night_state", side_effect=night_state), \
             mock.patch.object(bot, "unit_availability_price", side_effect=availability), \
             mock.patch.object(bot, "fetch_reservations_window", return_value=self.ROWS):
            got = bot.early_checkin_context(11, 7)
        self.assertEqual([row["id"] for row in got["alternatives"]], [8])
        self.assertEqual(got["alternatives"][0]["total"], 1800)

    def test_alternative_never_offers_a_unit_too_small_for_the_booking(self):
        reservation = {"result": {"id": 11, "listingMapId": 7,
                                   "arrivalDate": "2026-08-05",
                                   "departureDate": "2026-08-08",
                                   "numberOfGuests": 4}}
        units = [
            {"id": 8, "name": "Too small", "beds": 1, "capacity": 2},
            {"id": 9, "name": "Fits", "beds": 2, "capacity": 4},
            {"id": 10, "name": "Capacity unknown", "beds": 2},
        ]
        with mock.patch.object(bot, "api_get", return_value=reservation), \
             mock.patch.object(bot, "_catalog_units", units), \
             mock.patch.object(bot, "_catalog_ts", 1.0), \
             mock.patch.object(bot, "_calendar_night_state", side_effect=lambda lid, _d: (
                 "occupied" if lid == 7 else "free")), \
             mock.patch.object(bot, "unit_availability_price", return_value={
                 "available": True, "nights": 3, "total": 1800, "avg": 600}), \
             mock.patch.object(bot, "fetch_reservations_window", return_value=self.ROWS):
            got = bot.early_checkin_context(11, 7)
        self.assertEqual([row["id"] for row in got["alternatives"]], [9])
        self.assertEqual(got["guests"], 4)

    def test_empty_listing_response_does_not_replace_a_known_catalog(self):
        old_units = [{"id": 99, "name": "Known"}]
        with mock.patch.object(bot, "_catalog_units", old_units), \
             mock.patch.object(bot, "_catalog_text", "Known"), \
             mock.patch.object(bot, "_catalog_ts", 123.0), \
             mock.patch.object(bot, "api_get", return_value={"result": []}):
            bot.load_catalog(force=True)
            self.assertEqual(bot._catalog_units, old_units)
            self.assertEqual(bot._catalog_text, "Known")
            self.assertEqual(bot._catalog_ts, 123.0)


class TestWorkingHours(unittest.TestCase):
    def test_midnight_is_outside_working_hours(self):
        after_midnight = datetime(2026, 8, 2, 0, 1, tzinfo=bot.TZ)
        before_midnight = datetime(2026, 8, 1, 23, 59, tzinfo=bot.TZ)
        self.assertFalse(bot.is_within_working_hours(after_midnight))
        self.assertTrue(bot.is_within_working_hours(before_midnight))

    def test_next_shift_starts_at_eleven(self):
        got = bot.next_work_start(datetime(2026, 8, 2, 0, 1, tzinfo=bot.TZ))
        self.assertEqual((got.hour, got.minute), (11, 0))


class TestEarlyDecision(unittest.TestCase):
    def setUp(self):
        bot._early_checkin_decisions.clear()

    def test_first_decision_wins(self):
        bot._early_checkin_decisions[44] = {"status": "pending"}
        first = bot._decide_early_checkin(44, "approve", "Faisal")
        second = bot._decide_early_checkin(
            44, "reject", "Noura", "staff unavailable")
        self.assertEqual(first["status"], "approved")
        self.assertEqual(second["status"], "approved")
        self.assertEqual(second["decided_by"], "Faisal")

    def test_permanent_decision_claim_never_expires_and_can_release_after_failure(self):
        with tempfile.TemporaryDirectory() as state_dir, \
             mock.patch.object(bot, "STATE_DIR", state_dir):
            self.assertTrue(bot._permanent_once_claim("early-decision:44"))
            self.assertFalse(bot._permanent_once_claim("early-decision:44"))
            self.assertTrue(bot._permanent_once_release("early-decision:44"))
            self.assertTrue(bot._permanent_once_claim("early-decision:44"))

    def test_permanent_decision_claim_fails_closed_when_storage_is_unavailable(self):
        with mock.patch.object(bot.os, "makedirs", side_effect=OSError("readonly")):
            self.assertFalse(bot._permanent_once_claim("early-decision:45"))

    def test_rejection_requires_reason(self):
        bot._early_checkin_decisions[45] = {"status": "pending"}
        self.assertIsNone(
            bot._decide_early_checkin(45, "reject", "Faisal", ""))
        self.assertEqual(bot._early_checkin_decisions[45]["status"], "pending")

    def test_approval_reply_never_contains_neighbor_name(self):
        record = {
            "guest": "A", "unit": "Ouja | Test", "requested_label": "12:00 PM",
            "previous": {"guest": "PRIVATE PREVIOUS"},
            "next": {"guest": "PRIVATE NEXT"},
            "guest_text": "Can I check in at noon?",
        }
        reply = bot._early_guest_reply(record, "approve")
        self.assertIn("12:00 PM", reply)
        self.assertNotIn("PRIVATE PREVIOUS", reply)
        self.assertNotIn("PRIVATE NEXT", reply)

    def test_rejection_reply_includes_selected_reason(self):
        record = {"guest": "A", "unit": "Ouja | Test",
                  "requested_label": "12:00 PM", "guest_text": "دخول 12"}
        reply = bot._early_guest_reply(
            record, "reject", "جدول التنظيف ما يسمح بالدخول في هذا الوقت")
        self.assertIn("جدول التنظيف", reply)
        self.assertIn("3", reply)

    def test_custom_rejection_reason_redacts_neighbor_names(self):
        record = {
            "guest_text": "Can I check in at noon?",
            "previous": {"guest": "PRIVATE PREVIOUS"},
            "next": {"guest": "PRIVATE NEXT"},
        }
        reply = bot._early_guest_reply(
            record, "reject", "PRIVATE PREVIOUS needs more time")
        self.assertNotIn("PRIVATE PREVIOUS", reply)
        self.assertNotIn("PRIVATE NEXT", reply)

    def test_verified_alternatives_are_guest_safe_and_require_manager(self):
        record = {
            "guest_text": "Can I check in at noon?",
            "previous": {"guest": "PRIVATE PREVIOUS"},
            "alternatives": [
                {"id": 8, "name": "Ouja | Malqa", "beds": 2,
                 "area": "Malqa", "total": 1800, "avg": 600,
                 "link": "https://example.com/8"},
            ],
        }
        reply = bot._early_alternatives_reply(record)
        self.assertIn("Ouja | Malqa", reply)
        self.assertIn("1800", reply)
        self.assertIn("manager", reply.lower())
        self.assertNotIn("PRIVATE PREVIOUS", reply)

    def test_guest_can_select_an_offered_option_by_number(self):
        offer = {"alternatives": [
            {"id": 8, "name": "First"},
            {"id": 9, "name": "Second"},
        ]}
        self.assertEqual(
            bot._match_early_offer_selection("الخيار ٢", offer)["id"], 9)

    def test_internal_summary_contains_neighbors(self):
        record = {
            "previous_night_state": "free",
            "previous": {"guest": "Previous", "arrival": "2026-08-01",
                         "departure": "2026-08-05"},
            "next": {"guest": "Next", "arrival": "2026-08-08",
                     "departure": "2026-08-10"},
        }
        summary = bot._early_internal_summary(record)
        self.assertIn("Previous", summary)
        self.assertIn("Next", summary)

    def test_pending_reply_says_possible_not_confirmed(self):
        record = {
            "guest_text": "Can I check in at noon?",
            "requested_label": "12:00 PM",
        }
        reply = bot._early_pending_reply(record)
        self.assertIn("possible", reply.lower())
        self.assertIn("manager", reply.lower())
        self.assertNotIn("confirmed", reply.lower())

    def test_offhours_pending_reply_apologizes_and_names_return_time(self):
        record = {
            "guest_text": "Can I check in at noon?",
            "requested_label": "12:00 PM",
            "offhours": True,
        }
        reply = bot._early_pending_reply(record)
        self.assertIn("sorry", reply.lower())
        self.assertIn("11:00", reply)

    def test_unavailable_reply_is_direct_and_privacy_safe(self):
        record = {
            "guest_text": "هل أقدر أدخل الساعة 12؟",
            "previous": {"guest": "PRIVATE PREVIOUS"},
        }
        reply = bot._early_unavailable_reply(record)
        self.assertIn("غير ممكن", reply)
        self.assertIn("3", reply)
        self.assertNotIn("PRIVATE PREVIOUS", reply)


if __name__ == "__main__":
    unittest.main()
