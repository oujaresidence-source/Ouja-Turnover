import copy
import json
import unittest
from unittest import mock


from tests.monthly_public_fixtures import valid_settings
from tests.test_monthly_catalog_profiles import (
    valid_profile,
    valid_settings as valid_settings_values,
)


class FakeCatalog:
    def __init__(self, approved=None):
        self.approved = approved or {}

    def approved_profiles(self):
        return copy.deepcopy(self.approved)

    def approved_settings_values(self):
        return valid_settings_values()

    def approved_places(self):
        return {
            "hospital": {
                "kind": "destination",
                "label_ar": "مستشفى معتمد",
                "label_en": "Approved Hospital",
                "lat": 24.70,
                "lng": 46.68,
                "verified": True,
                "source": "approved_catalog",
            }
        }


class MonthlyCatalogBotIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot

        cls.bot = bot

    def setUp(self):
        self.saved = {
            "gw_cache": self.bot._gw_cache,
            "gw_overrides": self.bot._gw_overrides,
            "gw_ratings_cache": self.bot._gw_ratings_cache,
            "reviews": self.bot._reviews,
            "has_monthly": self.bot._HAS_MONTHLY,
            "mcal": self.bot._mcal,
            "monthly_cfg": self.bot._monthly_cfg,
            "catalog_service": self.bot._monthly_catalog_service,
        }
        profile = valid_profile()
        self.bot._gw_cache = {
            "listings": [
                {
                    "id": 101,
                    "name": "Ouja | Source 101",
                    "active": True,
                    "bedrooms": 2,
                    "beds": 2,
                    "beds_count": 3,
                    "baths": 2,
                    "capacity": 4,
                    "lat": 24.802,
                    "lng": 46.623,
                    "images": [{"url": url} for url in profile["images"]],
                    "amenities": ["Wireless", "Kitchen"],
                }
            ],
            "synced_at": "2026-08-25T09:00:00+03:00",
        }
        self.bot._gw_overrides = {
            "101": {
                "title_ar": profile["name_ar"],
                "title_en": profile["name_en"],
                "short_ar": profile["short_ar"],
                "short_en": profile["short_en"],
                "structured": profile["structured"],
                "content_verified": False,
                "neighborhood": "al_malqa",
                "facts": profile["facts"],
                "wifi_pass": "secret-wifi",
                "door_code": "1234",
                "notes": "call 0500000000",
            }
        }
        self.bot._gw_ratings_cache = {"t": 999999999999.0, "map": {}}
        self.bot._reviews = {}
        self.bot._HAS_MONTHLY = False
        self.bot._mcal = {"units": {}, "unit_synced_at": {}}
        self.bot._monthly_cfg = {"hidden": []}

    def tearDown(self):
        self.bot._gw_cache = self.saved["gw_cache"]
        self.bot._gw_overrides = self.saved["gw_overrides"]
        self.bot._gw_ratings_cache = self.saved["gw_ratings_cache"]
        self.bot._reviews = self.saved["reviews"]
        self.bot._HAS_MONTHLY = self.saved["has_monthly"]
        self.bot._mcal = self.saved["mcal"]
        self.bot._monthly_cfg = self.saved["monthly_cfg"]
        self.bot._monthly_catalog_service = self.saved["catalog_service"]

    def test_only_approved_profile_reaches_public_source(self):
        self.bot._monthly_catalog_service = FakeCatalog()
        draft_source = self.bot._monthly_public_source_adapter()["listings"][0]
        self.assertFalse(draft_source["content_verified"])

        self.bot._monthly_catalog_service = FakeCatalog({"101": valid_profile()})
        approved_source = self.bot._monthly_public_source_adapter()["listings"][0]
        self.assertTrue(approved_source["content_verified"])
        self.assertEqual(approved_source["name_ar"], valid_profile()["name_ar"])
        self.assertEqual(approved_source["bedrooms"], 2)

    def test_approved_profile_never_replaces_engine_or_calendar_values(self):
        self.bot._monthly_catalog_service = FakeCatalog({"101": valid_profile()})
        official = {
            "2026-09": {
                "monthly_rate_sar": 12000,
                "currency": "SAR",
                "source": "engine_verified",
                "verified_at": "2026-08-25T09:30:00+03:00",
            }
        }
        calendar = {
            "synced_at": "2026-08-25T09:40:00+03:00",
            "from": "2026-08-25",
            "to": "2027-03-23",
            "blocked_dates": [],
        }
        with mock.patch.object(
            self.bot, "_monthly_public_engine_prices", return_value=official
        ), mock.patch.object(
            self.bot, "_monthly_public_calendar", return_value=calendar
        ):
            row = self.bot._monthly_public_source_adapter()["listings"][0]
        self.assertEqual(row["official_prices"], official)
        self.assertEqual(row["calendar"], calendar)

    def test_prefill_source_is_allowlisted_and_contains_same_id_coordinates(self):
        payload = self.bot._monthly_catalog_prefill_source()
        rendered = json.dumps(payload, ensure_ascii=False)
        row = payload["listings"][0]
        self.assertEqual(row["id"], "101")
        self.assertEqual(row["hostaway"]["lat"], 24.802)
        self.assertEqual(row["hostaway"]["lng"], 46.623)
        for forbidden in ("secret-wifi", "1234", "0500000000", "wifi_pass", "door_code", "notes"):
            self.assertNotIn(forbidden, rendered)

    def test_refresh_uses_approved_global_settings_and_places(self):
        class App:
            def __init__(self):
                self.replaced = None

            def replace_configuration(self, settings, places):
                self.replaced = (settings, places)

        class Snapshot:
            def __init__(self):
                self.values = None
                self.last_error = None

            def refresh(self, source, settings, now):
                self.values = (source, settings, now)
                return type("Outcome", (), {"accepted": True, "error": None})()

        app, snapshot = App(), Snapshot()
        source = {"refresh_ok": True, "catalog_complete": True, "listings": []}
        with mock.patch.object(self.bot, "_monthly_catalog_service", FakeCatalog()), mock.patch.object(
            self.bot, "_monthly_public_app", app
        ), mock.patch.object(
            self.bot, "_monthly_public_snapshot", snapshot
        ), mock.patch.object(
            self.bot, "_monthly_public_source_adapter", return_value=source
        ):
            result = self.bot._monthly_public_refresh_snapshot()

        self.assertTrue(result["accepted"])
        settings, places = app.replaced
        self.assertEqual(settings.whatsapp_number, "966500000000")
        self.assertIn("hospital", places)
        self.assertIs(snapshot.values[0], source)


if __name__ == "__main__":
    unittest.main()
