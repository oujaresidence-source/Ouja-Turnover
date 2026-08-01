"""Deterministic apartment qualification and verified Hostaway matching."""

import unittest
from unittest import mock

import bot


class TestApartmentQualification(unittest.TestCase):
    def test_search_intent_does_not_confuse_wifi_availability(self):
        self.assertTrue(bot._is_apartment_search("عندكم شقة غرفتين؟"))
        self.assertTrue(bot._is_apartment_search("أبي شقة في الرياض"))
        self.assertTrue(bot._is_apartment_search("Do you have an apartment?"))
        self.assertTrue(bot._is_apartment_search("I need an apartment in Riyadh"))
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


if __name__ == "__main__":
    unittest.main()
