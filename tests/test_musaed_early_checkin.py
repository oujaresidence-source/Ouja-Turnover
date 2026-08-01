"""MUSAED early-check-in decisions, with synthetic Hostaway facts only."""

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


class TestWorkingHours(unittest.TestCase):
    def test_midnight_is_outside_working_hours(self):
        after_midnight = datetime(2026, 8, 2, 0, 1, tzinfo=bot.TZ)
        before_midnight = datetime(2026, 8, 1, 23, 59, tzinfo=bot.TZ)
        self.assertFalse(bot.is_within_working_hours(after_midnight))
        self.assertTrue(bot.is_within_working_hours(before_midnight))

    def test_next_shift_starts_at_eleven(self):
        got = bot.next_work_start(datetime(2026, 8, 2, 0, 1, tzinfo=bot.TZ))
        self.assertEqual((got.hour, got.minute), (11, 0))


if __name__ == "__main__":
    unittest.main()
