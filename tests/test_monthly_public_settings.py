import datetime as dt
import json
import unittest
from zoneinfo import ZoneInfo


from monthly_public.settings import load_settings, response_window


def complete_config(**overrides):
    config = {
        "whatsapp_number": "966500000000",
        "working_hours": {
            "timezone": "Asia/Riyadh",
            "schedule": {
                "sunday": [["09:00", "18:00"]],
                "monday": [["09:00", "18:00"]],
                "tuesday": [["09:00", "18:00"]],
                "wednesday": [["09:00", "18:00"]],
                "thursday": [["09:00", "18:00"]],
            },
        },
        "commercial_terms": {
            "included": ["internet", "maintenance"],
            "deposit": {
                "amount_sar": 2_000,
                "refund_ar": "يُسترد بعد فحص الشقة حسب الشروط المؤكدة.",
                "refund_en": "Refunded after checkout inspection under the confirmed terms.",
            },
            "payment_methods": [
                {"ar": "تحويل بنكي", "en": "Bank transfer"},
                {"ar": "بطاقة", "en": "Card"},
            ],
        },
        "long_stay_route": "monthly_contract_review",
    }
    config.update(overrides)
    return config


class SettingsValidationTests(unittest.TestCase):
    def test_complete_configuration_is_launch_ready(self):
        settings = load_settings(complete_config())

        self.assertTrue(settings.launch_ready)
        self.assertEqual(settings.whatsapp_number, "966500000000")
        self.assertEqual(settings.blockers, ())

    def test_whatsapp_requires_e164_like_digits(self):
        for value in ("+966500000000", "05 0000 0000", "01234567", "1" * 16):
            with self.subTest(value=value):
                settings = load_settings(complete_config(whatsapp_number=value))
                self.assertIn("whatsapp_invalid", {item.code for item in settings.blockers})

    def test_missing_whatsapp_is_a_launch_blocker(self):
        config = complete_config()
        config.pop("whatsapp_number")
        settings = load_settings(config)

        blocker = next(item for item in settings.blockers if item.code == "whatsapp_missing")
        self.assertEqual(blocker.field, "whatsapp_number")
        self.assertTrue(blocker.message_ar)
        self.assertTrue(blocker.message_en)

    def test_missing_working_hours_is_a_launch_blocker(self):
        config = complete_config()
        config.pop("working_hours")
        settings = load_settings(config)
        self.assertIn("working_hours_missing", {item.code for item in settings.blockers})

    def test_empty_or_invalid_working_hours_are_launch_blockers(self):
        for working_hours in (
            {"timezone": "Asia/Riyadh", "schedule": {}},
            {"timezone": "Asia/Riyadh", "schedule": {"sunday": [["18:00", "09:00"]]}},
            {"timezone": "Not/AZone", "schedule": {"sunday": [["09:00", "18:00"]]}},
        ):
            with self.subTest(working_hours=working_hours):
                settings = load_settings(complete_config(working_hours=working_hours))
                self.assertIn("working_hours_invalid", {item.code for item in settings.blockers})

    def test_missing_commercial_terms_are_launch_blockers(self):
        config = complete_config()
        config.pop("commercial_terms")
        settings = load_settings(config)
        self.assertIn("commercial_terms_missing", {item.code for item in settings.blockers})

    def test_required_commercial_terms_are_checked_individually(self):
        variants = (
            ({"included": ["internet"], "deposit": complete_config()["commercial_terms"]["deposit"], "payment_methods": complete_config()["commercial_terms"]["payment_methods"]}, "maintenance_not_included"),
            ({"included": ["internet", "maintenance"], "payment_methods": complete_config()["commercial_terms"]["payment_methods"]}, "deposit_missing"),
            ({"included": ["internet", "maintenance"], "deposit": complete_config()["commercial_terms"]["deposit"], "payment_methods": []}, "payment_methods_missing"),
        )
        for terms, code in variants:
            with self.subTest(code=code):
                settings = load_settings(complete_config(commercial_terms=terms))
                self.assertIn(code, {item.code for item in settings.blockers})

    def test_missing_long_stay_route_is_a_launch_blocker(self):
        config = complete_config()
        config.pop("long_stay_route")
        settings = load_settings(config)
        self.assertIn("long_stay_route_missing", {item.code for item in settings.blockers})

    def test_environment_style_json_values_are_supported(self):
        config = complete_config()
        settings = load_settings(
            {
                "MONTHLY_WHATSAPP": config["whatsapp_number"],
                "MONTHLY_WORKING_HOURS": json.dumps(config["working_hours"]),
                "MONTHLY_COMMERCIAL_TERMS": json.dumps(config["commercial_terms"]),
                "MONTHLY_LONG_STAY_ROUTE": config["long_stay_route"],
            }
        )
        self.assertTrue(settings.launch_ready)


class ResponseWindowTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(complete_config())
        self.riyadh = ZoneInfo("Asia/Riyadh")

    def test_in_hours_uses_the_approved_thirty_minute_promise(self):
        result = response_window(
            self.settings,
            dt.datetime(2026, 8, 25, 10, 30, tzinfo=self.riyadh),  # Tuesday
        )

        self.assertTrue(result["is_open"])
        self.assertEqual(result["response_minutes"], 30)
        self.assertEqual(result["message_ar"], "عادة نرد خلال 30 دقيقة في أوقات العمل")
        self.assertEqual(
            result["message_en"],
            "We usually reply within 30 minutes during working hours.",
        )
        self.assertIsNone(result["next_opens_at"])

    def test_outside_hours_names_the_next_response_window(self):
        result = response_window(
            self.settings,
            dt.datetime(2026, 8, 29, 20, 0, tzinfo=self.riyadh),  # Saturday
        )

        self.assertFalse(result["is_open"])
        self.assertIsNone(result["response_minutes"])
        self.assertEqual(result["next_opens_at"], "2026-08-30T09:00:00+03:00")
        self.assertIn("الأحد", result["message_ar"])
        self.assertIn("9:00", result["message_ar"])
        self.assertIn("Sunday", result["message_en"])
        self.assertIn("9:00 AM", result["message_en"])

    def test_timezone_is_applied_before_checking_the_schedule(self):
        result = response_window(
            self.settings,
            dt.datetime(2026, 8, 25, 7, 0, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(result["is_open"])


if __name__ == "__main__":
    unittest.main()
