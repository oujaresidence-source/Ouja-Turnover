import copy
import os
import tempfile
import unittest


from monthly_public.catalog_service import CatalogService
from monthly_public.catalog_store import CatalogStore
from monthly_public.preview import build_preview_app, build_preview_generation
from monthly_public.showcase_service import ShowcaseService
from monthly_public.showcase_store import ShowcaseStore
from tests.monthly_public_fixtures import NOW, valid_settings
from tests.test_monthly_catalog_profiles import valid_settings as valid_settings_values
from tests.test_monthly_catalog_service import source_listing


class MonthlyPreviewGenerationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = CatalogStore(
            os.path.join(self.tmp.name, "catalog.sqlite3"), clock=lambda: NOW
        )
        incomplete = source_listing(202)
        incomplete["stay"].pop("title_ar")
        incomplete["stay"].pop("title_en")
        incomplete["stay"].pop("short_ar")
        incomplete["stay"].pop("structured")
        incomplete["licence"] = None
        incomplete["publication"]["licence"] = None
        self.source = {
            "refresh_ok": True,
            "catalog_complete": True,
            "source_timestamps": {"listings": NOW.isoformat()},
            "listings": [source_listing(101), incomplete],
        }
        self.refresh_calls = []
        self.service = CatalogService(
            self.store,
            source_provider=lambda: copy.deepcopy(self.source),
            settings_fallback=valid_settings_values,
            snapshot_refresh=lambda: self.refresh_calls.append(True),
            clock=lambda: NOW,
        )

    def store_state(self):
        return {
            "profiles": {
                listing_id: self.store.profile(listing_id)
                for listing_id in ("101", "202")
            },
            "settings": self.store.settings(),
            "places": self.store.places(),
            "audit": self.store.audit(),
        }

    def test_preview_includes_incomplete_inventory_without_mutating_store(self):
        before = self.store_state()
        source_before = copy.deepcopy(self.source)

        generation = build_preview_generation(
            self.service.preview_inventory(), valid_settings(), NOW
        )

        self.assertEqual(
            [row.listing["id"] for row in generation.published], ["101", "202"]
        )
        incomplete = generation.by_id["202"]
        self.assertIn("arabic_title_missing", incomplete.listing["preview_missing"])
        self.assertIn("arabic_content_missing", incomplete.listing["preview_missing"])
        self.assertIn("licence_missing", incomplete.listing["preview_missing"])
        self.assertTrue(incomplete.listing["preview"])
        self.assertFalse(incomplete.exact_match_eligible)
        self.assertEqual(self.store_state(), before)
        self.assertEqual(self.source, source_before)
        self.assertEqual(self.refresh_calls, [])

    def test_preview_fallback_labels_make_no_unverified_listing_claim(self):
        generation = build_preview_generation(
            self.service.preview_inventory(), valid_settings(), NOW
        )

        listing = generation.by_id["202"].listing
        self.assertEqual(listing["name_ar"], "شقة 202 · بيانات قيد الإكمال")
        self.assertEqual(listing["name_en"], "Ouja | Apartment 202")
        self.assertEqual(listing["licence"], {})


class MonthlyPreviewAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = CatalogStore(
            os.path.join(self.tmp.name, "catalog.sqlite3"), clock=lambda: NOW
        )
        incomplete = source_listing(202)
        incomplete["stay"].pop("title_ar")
        incomplete["stay"].pop("title_en")
        incomplete["stay"].pop("short_ar")
        incomplete["stay"].pop("structured")
        incomplete["licence"] = None
        incomplete["publication"]["licence"] = None
        self.source = {
            "refresh_ok": True,
            "catalog_complete": True,
            "source_timestamps": {"listings": NOW.isoformat()},
            "listings": [source_listing(101), incomplete],
        }
        self.service = CatalogService(
            self.store,
            source_provider=lambda: copy.deepcopy(self.source),
            settings_fallback=valid_settings_values,
            snapshot_refresh=lambda: {"accepted": True},
            clock=lambda: NOW,
        )
        self.showcase_store = ShowcaseStore(
            os.path.join(self.tmp.name, "showcases.sqlite3")
        )
        self.showcases = ShowcaseService(
            store=self.showcase_store,
            inventory_provider=self.service.preview_inventory,
            snapshot_provider=lambda: build_preview_generation(
                self.service.preview_inventory(), valid_settings(), NOW
            ),
            session_secret=b"preview-showcase-secret-is-32-bytes",
            clock=lambda: NOW,
        )
        saved = self.showcases.save_draft(
            "showcase_preview",
            {
                "name_ar": "عمارة النزهة",
                "name_en": "Nuzha Building",
                "slug": "nuzha",
                "description_ar": "مجموعة شقق عوجا في مبنى واحد.",
                "description_en": "Ouja homes in one building.",
                "image_url": None,
                "image_listing_id": None,
                "listing_ids": ["101", "202"],
                "listing_prices": {},
                "fixed_monthly_rate_sar": None,
                "fixed_price_enabled": False,
            },
            0,
            "ops",
        )
        self.showcases.approve(
            "showcase_preview", saved["draft_revision"], "ops"
        )
        self.app = build_preview_app(
            self.service, clock=lambda: NOW, showcase_service=self.showcases
        )

    def test_preview_config_uses_daily_ten_to_ten_and_blocks_contact(self):
        config = self.app.config("ar")

        self.assertTrue(config["ok"])
        self.assertTrue(config["preview"])
        self.assertEqual(config["eligible_count"], 2)
        self.assertEqual(
            config["deposit_range_sar"], {"minimum": 500, "maximum": 2500}
        )
        self.assertTrue(config["response_window"]["is_open"])
        self.assertEqual(config["response_window"]["response_minutes"], 30)
        self.assertTrue(
            any(row["code"] == "whatsapp_missing" for row in config["blockers"])
        )
        self.assertIsNone(config["session_id"])

    def test_preview_config_never_exposes_an_unlabelled_neighborhood_choice(self):
        row = self.source["listings"][0]
        row["stay"]["neighborhood"] = "source_only_neighborhood"
        row["stay"]["neighborhood_ar"] = None
        row["stay"]["neighborhood_en"] = None
        row["stay"]["neighborhood_verified"] = False
        app = build_preview_app(self.service, clock=lambda: NOW)

        config = app.config("ar")

        self.assertFalse(any(
            place.get("id") == "source_only_neighborhood"
            for place in config["neighborhoods"]
        ))
        self.assertTrue(all(
            place.get("label_ar") and place.get("label_en")
            for place in config["neighborhoods"]
        ))

    def test_preview_config_reports_the_next_window_after_ten_at_night(self):
        late = NOW.replace(hour=23, minute=0)
        app = build_preview_app(self.service, clock=lambda: late)

        response = app.config("ar")["response_window"]

        self.assertFalse(response["is_open"])
        self.assertIsNone(response["response_minutes"])
        self.assertIn("10:00", response["message_en"])

    def test_preview_match_keeps_every_home_in_complete_catalog(self):
        result = self.app.match(
            {
                "purpose": "family",
                "residents": 2,
                "sleeping": "one_bedroom",
                "move_in": "2026-09-01",
                "duration_months": 1,
                "flexibility": "fixed",
            },
            "ar",
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("202", [row["id"] for row in result["top"]])
        self.assertTrue(all(row["availability_status"] == "available" for row in result["top"]))
        self.assertEqual(len(result["catalog"]), 2)
        self.assertTrue(all(row["preview"] for row in result["catalog"]))
        incomplete = next(row for row in result["catalog"] if row["id"] == "202")
        self.assertIn("licence_missing", incomplete["preview_missing"])
        self.assertFalse(incomplete["preview_complete"])

    def test_preview_listing_labels_missing_evidence_and_disables_leads(self):
        detail = self.app.listing({"listing_id": "202", "lang": "en"})

        self.assertTrue(detail["ok"])
        self.assertTrue(detail["listing"]["preview"])
        self.assertIn("arabic_title_missing", detail["listing"]["preview_missing"])
        blocked = self.app.lead({})
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["error"]["code"], "preview_contact_disabled")

    def test_latest_draft_is_reflected_without_approval_or_source_refresh(self):
        source_before = copy.deepcopy(self.source)
        self.service.save_profile_draft(
            "101", {"name_ar": "عوجا | اسم مسودة الفريق"}, 0, "ops"
        )

        preview = build_preview_app(self.service, clock=lambda: NOW)
        detail = preview.listing({"listing_id": "101", "lang": "ar"})

        self.assertTrue(detail["ok"])
        self.assertEqual(detail["listing"]["title"], "عوجا | اسم مسودة الفريق")
        self.assertIsNone(self.store.profile("101")["approved"])
        self.assertEqual(self.source, source_before)

    def test_showcase_preview_includes_every_selected_real_home(self):
        result = self.app.showcase({"slug": "nuzha", "lang": "ar"})

        self.assertTrue(result["ok"])
        self.assertTrue(result["preview"])
        self.assertEqual(result["showcase"]["eligible_count"], 2)
        self.assertEqual(
            [str(home["id"]) for home in result["showcase"]["homes"]],
            ["101", "202"],
        )
        incomplete = next(
            home for home in result["showcase"]["homes"] if str(home["id"]) == "202"
        )
        self.assertIn("licence_missing", incomplete["preview_missing"])


if __name__ == "__main__":
    unittest.main()
