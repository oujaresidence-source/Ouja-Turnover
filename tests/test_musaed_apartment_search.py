"""Deterministic apartment qualification and verified Hostaway matching."""

import contextlib
import datetime as _dt
import unittest
from unittest import mock

import bot


@contextlib.contextmanager
def _frozen_now(year, month, day):
    """Freeze the wall clock bot reads. Only bot.datetime is swapped — bot.date stays
    real, so the date(...) the parser builds is untouched. Without this, any test of a
    yearless month asserts a calendar date and dies the day that month passes."""
    class _Clock:
        @staticmethod
        def now(tz=None):
            return _dt.datetime(year, month, day, 12, 0)
    with mock.patch.object(bot, "datetime", _Clock):
        yield


class TestApartmentQualification(unittest.TestCase):
    def test_search_intent_does_not_confuse_wifi_availability(self):
        self.assertTrue(bot._is_apartment_search("عندكم شقة غرفتين؟"))
        self.assertTrue(bot._is_apartment_search("أبي شقة في الرياض"))
        self.assertTrue(bot._is_apartment_search("Do you have an apartment?"))
        self.assertTrue(bot._is_apartment_search("I need an apartment in Riyadh"))
        self.assertTrue(bot._is_apartment_search("أبحث عن سكن بالرياض"))
        self.assertFalse(bot._is_apartment_search("هل الواي فاي متاح في الشقة؟"))

    def test_all_missing_questions_are_asked_in_one_message(self):
        req = bot._apartment_requirements("Guest: عندكم شقة؟")
        missing = bot._missing_apartment_requirements(req)
        self.assertEqual(
            missing,
            ["dates", "guests", "bedrooms", "area", "budget", "must_haves"],
        )
        reply = bot._apartment_qualification_reply(req, missing, arabic=True)
        for phrase in ("الوصول والمغادرة", "عدد الضيوف", "غرف النوم", "الحي",
                       "الميزانية", "المتطلبات"):
            self.assertIn(phrase, reply)

    def test_host_question_examples_are_not_mistaken_for_guest_requirements(self):
        history = (
            "Guest: عندكم شقة؟\n"
            "Host: حتى أتحقق لك مباشرة، أرسل موقف أو واي فاي أو مسبح، والميزانية لليلة\n"
            "Guest: 2026-08-10 إلى 2026-08-13، 4 ضيوف، غرفتين، أي حي"
        )
        req = bot._apartment_requirements(history)
        self.assertEqual(req["must_haves"], [])
        self.assertIsNone(req["budget"])
        self.assertEqual(
            bot._missing_apartment_requirements(req), ["budget", "must_haves"])

    def test_complete_arabic_answer_is_extracted_from_full_history(self):
        history = (
            "Guest: عندكم شقة؟\n"
            "Host: حتى أتحقق لك مباشرة، أرسل التفاصيل\n"
            "Guest: من 2026-08-10 إلى 2026-08-13، ٤ ضيوف، غرفتين، "
            "الملقا، ٧٠٠ لليلة، لازم موقف وواي فاي"
        )
        req = bot._apartment_requirements(history)
        self.assertEqual(req["checkin"], "2026-08-10")
        self.assertEqual(req["checkout"], "2026-08-13")
        self.assertEqual(req["guests"], 4)
        self.assertEqual(req["bedrooms"], 2)
        self.assertEqual(req["area"], "الملقا")
        self.assertEqual(req["budget"], 700)
        self.assertEqual(set(req["must_haves"]), {"parking", "wifi"})
        self.assertEqual(bot._missing_apartment_requirements(req), [])

    def test_natural_month_names_are_understood(self):
        ar = bot._apartment_requirements(
            "Guest: من 10 أغسطس 2026 إلى 13 أغسطس 2026، 4 ضيوف، غرفتين، "
            "أي حي، 700 لليلة، بدون متطلبات")
        en = bot._apartment_requirements(
            "Guest: August 10, 2026 to August 13, 2026, 4 guests, two bedroom, "
            "any area, SAR 700 per night, no requirements")
        self.assertEqual((ar["checkin"], ar["checkout"]),
                         ("2026-08-10", "2026-08-13"))
        self.assertEqual((en["checkin"], en["checkout"]),
                         ("2026-08-10", "2026-08-13"))

    _YEARLESS_AUGUST = ("Guest: أبحث عن سكن من 5 إلى 8 أغسطس، 4 ضيوف، غرفتين، "
                        "أي حي، 700 لليلة، بدون متطلبات")

    def test_shared_month_yearless_range_is_understood(self):
        # «من 5 إلى 8 أغسطس» names no year: still-to-come this year means THIS year.
        with _frozen_now(2026, 7, 1):
            req = bot._apartment_requirements(self._YEARLESS_AUGUST)
        self.assertEqual((req["checkin"], req["checkout"]),
                         ("2026-08-05", "2026-08-08"))

    def test_shared_month_yearless_range_rolls_forward_once_it_has_passed(self):
        # Same sentence, asked after those days are gone: the guest means next August,
        # not a stay in the past. (Live-caught 2026-08-20 — the old test hard-coded the
        # year and started failing on 2026-08-09.)
        with _frozen_now(2026, 8, 20):
            req = bot._apartment_requirements(self._YEARLESS_AUGUST)
        self.assertEqual((req["checkin"], req["checkout"]),
                         ("2027-08-05", "2027-08-08"))

    def test_explicit_no_preferences_fulfils_optional_questions(self):
        history = (
            "Guest: 2026-08-10 إلى 2026-08-13، ضيفين، عدد الغرف ما يهم، "
            "أي حي، الميزانية مفتوحة، بدون متطلبات"
        )
        req = bot._apartment_requirements(history)
        self.assertEqual(bot._missing_apartment_requirements(req), [])
        self.assertTrue(req["bedrooms_any"])
        self.assertTrue(req["area_any"])
        self.assertTrue(req["budget_flexible"])
        self.assertTrue(req["must_haves_none"])


class TestVerifiedApartmentMatches(unittest.TestCase):
    UNITS = [
        {"id": 1, "name": "Exact", "beds": 2, "capacity": 4,
         "area": "Riyadh", "neighbourhood": "الملقا", "tags": ["wifi", "parking"]},
        {"id": 2, "name": "Unavailable", "beds": 2, "capacity": 4,
         "area": "Riyadh", "neighbourhood": "الملقا", "tags": ["wifi", "parking"]},
        {"id": 3, "name": "Closest", "beds": 1, "capacity": 4,
         "area": "Riyadh", "neighbourhood": "النرجس", "tags": ["wifi"]},
        {"id": 4, "name": "Unknown", "beds": 2, "capacity": 4,
         "area": "Riyadh", "neighbourhood": "الملقا", "tags": ["wifi", "parking"]},
    ]

    def test_only_live_available_units_are_returned_and_fit_is_explained(self):
        req = {
            "checkin": "2026-08-10", "checkout": "2026-08-13", "guests": 4,
            "bedrooms": 2, "bedrooms_any": False, "area": "الملقا", "area_any": False,
            "budget": 700, "budget_flexible": False,
            "must_haves": ["wifi", "parking"], "must_haves_none": False,
        }

        def availability(lid, _ci, _co):
            if lid == 2:
                return {"available": False, "nights": 3, "total": 1500, "avg": 500}
            if lid == 4:
                return None
            if lid == 1:
                return {"available": True, "nights": 3, "total": 1800, "avg": 600}
            return {"available": True, "nights": 3, "total": 2250, "avg": 750}

        with mock.patch.object(bot, "unit_availability_price", side_effect=availability):
            rows = bot._verified_apartment_matches(req, self.UNITS)
        self.assertEqual([r["name"] for r in rows], ["Exact", "Closest"])
        self.assertEqual(rows[0]["mismatches"], [])
        self.assertIn("bedrooms", rows[1]["mismatches"])
        self.assertIn("area", rows[1]["mismatches"])
        self.assertIn("budget", rows[1]["mismatches"])
        self.assertIn("parking", rows[1]["mismatches"])
        reply = bot._apartment_matches_reply(req, rows, arabic=False)
        self.assertIn("SAR 1800", reply)
        self.assertIn("matches all", reply.lower())
        self.assertIn("does not fully match", reply.lower())

    def test_partial_calendar_is_unknown_not_available(self):
        partial = {"result": [{"isAvailable": 1, "price": 500}]}
        key = (91, "2026-08-10", "2026-08-13")
        bot._avail_cache.pop(key, None)
        with mock.patch.object(bot, "api_get", return_value=partial):
            got = bot.unit_availability_price(91, "2026-08-10", "2026-08-13")
        self.assertIsNone(got)

    def test_one_unknown_lookup_makes_the_whole_guest_scan_inconclusive(self):
        req = {
            "checkin": "2026-08-10", "checkout": "2026-08-13", "guests": 4,
            "bedrooms": 2, "area": "الملقا", "budget": 700,
            "must_haves": ["wifi"],
        }

        def availability(lid, _ci, _co):
            if lid == 4:
                return None
            return {"available": lid == 1, "nights": 3, "total": 1800, "avg": 600}

        with mock.patch.object(bot, "unit_availability_price", side_effect=availability):
            rows, conclusive = bot._verified_apartment_matches(
                req, self.UNITS, include_meta=True)
        self.assertEqual([row["id"] for row in rows], [1])
        self.assertFalse(conclusive)


class TestOffhoursAcknowledgement(unittest.TestCase):
    def setUp(self):
        bot._offhours_acked_convos.clear()

    def test_only_one_offhours_ack_can_be_claimed_per_conversation(self):
        self.assertTrue(bot._claim_offhours_ack("conv-7", True))
        self.assertFalse(bot._claim_offhours_ack("conv-7", True))
        bot._release_offhours_ack("conv-7", True)
        self.assertTrue(bot._claim_offhours_ack("conv-7", True))

    def test_inhours_ack_is_not_limited_by_offhours_set(self):
        self.assertTrue(bot._claim_offhours_ack("conv-7", False))
        self.assertTrue(bot._claim_offhours_ack("conv-7", False))


if __name__ == "__main__":
    unittest.main()
