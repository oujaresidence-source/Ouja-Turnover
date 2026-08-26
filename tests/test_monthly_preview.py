import copy
import os
import tempfile
import unittest


from monthly_public.catalog_service import CatalogService
from monthly_public.catalog_store import CatalogStore
from monthly_public.preview import build_preview_generation
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


if __name__ == "__main__":
    unittest.main()
