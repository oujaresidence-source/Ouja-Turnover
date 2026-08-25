import copy
import datetime as dt
import os
import tempfile
import unittest


from monthly_public.catalog_profiles import CatalogContractError
from monthly_public.catalog_service import CatalogService
from monthly_public.catalog_store import CatalogStore, RevisionConflict
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings
from tests.test_monthly_catalog_profiles import (
    valid_profile,
    valid_settings as valid_settings_values,
)


def source_listing(listing_id=101, **publication_overrides):
    profile = valid_profile()
    public = valid_listing(id=listing_id, **publication_overrides)
    return {
        "id": str(listing_id),
        "hostaway": {
            "id": listing_id,
            "name": "Ouja | Source %s" % listing_id,
            "active": True,
            "bedrooms": profile["bedrooms"],
            "beds_count": profile["beds_count"],
            "baths": profile["baths"],
            "capacity": profile["capacity"],
            "images": [{"url": url} for url in profile["images"]],
            "lat": profile["coordinates"]["lat"],
            "lng": profile["coordinates"]["lng"],
        },
        "stay": {
            "title_ar": profile["name_ar"],
            "title_en": profile["name_en"],
            "short_ar": profile["short_ar"],
            "short_en": profile["short_en"],
            "structured": profile["structured"],
            "content_verified": profile["content_verified"],
            "neighborhood": profile["neighborhood"],
            "neighborhood_ar": profile["neighborhood_ar"],
            "neighborhood_en": profile["neighborhood_en"],
            "neighborhood_verified": True,
            "facts": profile["facts"],
            "commercial_terms": profile["commercial_terms"],
        },
        "licence": profile["licence"],
        "rating": {"rating": 4.82, "count": 34},
        "publication": public,
    }


class CatalogServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = CatalogStore(
            os.path.join(self.tmp.name, "catalog.sqlite3"), clock=lambda: NOW
        )
        self.source = {
            "refresh_ok": True,
            "catalog_complete": True,
            "source_timestamps": {"listings": NOW.isoformat()},
            "listings": [source_listing()],
        }
        self.refresh_calls = []
        self.refresh_result = {"accepted": True, "generation_id": "gen-2"}

    def service(self):
        return CatalogService(
            self.store,
            source_provider=lambda: copy.deepcopy(self.source),
            settings_fallback=valid_settings_values,
            snapshot_refresh=self._refresh,
            clock=lambda: NOW,
        )

    def _refresh(self):
        self.refresh_calls.append(True)
        if isinstance(self.refresh_result, Exception):
            raise self.refresh_result
        return dict(self.refresh_result)

    def test_portfolio_has_one_truthful_row_per_listing(self):
        self.source["listings"].append(copy.deepcopy(self.source["listings"][0]))

        result = self.service().portfolio()

        self.assertEqual([row["id"] for row in result["listings"]], ["101"])
        self.assertEqual(result["counts"]["received"], 1)
        self.assertEqual(result["counts"]["duplicate_source_rows"], 1)
        self.assertIn("duplicate_listing_source", result["launch_blockers"])

    def test_listing_prefill_uses_draft_then_approved_then_source(self):
        self.store.save_profile_draft(
            "101", {"name_ar": "عنوان المسودة"}, 0, "ops"
        )
        result = self.service().listing("101")
        self.assertEqual(result["prefill"]["name_ar"], "عنوان المسودة")
        self.assertEqual(result["prefill"]["sources"]["name_ar"], "monthly_draft")

    def test_approval_keeps_background_blockers_separate(self):
        self.source["listings"][0]["publication"] = valid_listing(
            id=101, official_prices={}
        )
        service = self.service()
        saved = service.save_profile_draft("101", valid_profile(), 0, "ops")

        result = service.approve_profile("101", saved["draft_revision"], "ops")

        self.assertTrue(result["approved"])
        self.assertFalse(result["published"])
        self.assertIn("price_missing", result["background_blockers"])
        self.assertEqual(len(self.refresh_calls), 1)

    def test_incomplete_staff_profile_cannot_be_approved(self):
        service = self.service()
        saved = service.save_profile_draft(
            "101", {"name_ar": "عوجا | عنوان"}, 0, "ops"
        )
        with self.assertRaises(CatalogContractError) as caught:
            service.approve_profile("101", saved["draft_revision"], "ops")
        self.assertEqual(caught.exception.code, "profile_incomplete")
        self.assertIsNone(self.store.profile("101")["approved"])

    def test_save_rejects_unknown_listing_and_stale_revision(self):
        service = self.service()
        with self.assertRaises(CatalogContractError) as caught:
            service.save_profile_draft("999", valid_profile(), 0, "ops")
        self.assertEqual(caught.exception.code, "listing_not_found")

        service.save_profile_draft("101", valid_profile(), 0, "ops")
        with self.assertRaises(RevisionConflict):
            service.save_profile_draft("101", valid_profile(), 0, "ops")

    def test_global_settings_use_environment_until_an_approved_record_exists(self):
        service = self.service()
        before = service.settings()
        self.assertEqual(before["effective_source"], "environment_fallback")
        draft = service.save_settings_draft(valid_settings_values(), 0, "ops")
        service.approve_settings(draft["draft_revision"], "manager")

        after = service.settings()
        self.assertEqual(after["effective_source"], "catalog_approved")
        self.assertEqual(after["effective"]["whatsapp_number"], "966500000000")

    def test_only_active_approved_places_reach_the_customer_registry(self):
        service = self.service()
        value = {
            "label_ar": "مستشفى الملك فيصل",
            "label_en": "King Faisal Specialist Hospital",
            "purposes": ["treatment"],
            "coordinates": "24.672,46.680",
            "source_note": "Operations reviewed pin",
        }
        draft = service.save_place_draft("hospital", value, 0, "ops")
        service.approve_place("hospital", draft["draft_revision"], True, "manager")
        self.assertIn("hospital", service.approved_places())

        service.approve_place("hospital", draft["draft_revision"], False, "manager")
        self.assertNotIn("hospital", service.approved_places())
        self.assertIn("hospital", service.places()["places"])

    def test_refresh_failure_does_not_undo_the_approved_revision(self):
        self.refresh_result = RuntimeError("source unavailable")
        service = self.service()
        saved = service.save_profile_draft("101", valid_profile(), 0, "ops")

        result = service.approve_profile("101", saved["draft_revision"], "ops")

        self.assertTrue(result["approved"])
        self.assertFalse(result["refresh"]["accepted"])
        self.assertEqual(result["refresh"]["error"], "source_unavailable")
        self.assertIsNotNone(self.store.profile("101")["approved"])

    def test_source_failure_is_a_retryable_service_error(self):
        service = CatalogService(
            self.store,
            source_provider=lambda: (_ for _ in ()).throw(RuntimeError("cold cache")),
            settings_fallback=valid_settings_values,
            snapshot_refresh=self._refresh,
            clock=lambda: NOW,
        )
        with self.assertRaises(RuntimeError):
            service.portfolio()

    def test_approved_staff_profile_can_be_publishable_with_valid_background(self):
        service = self.service()
        saved = service.save_profile_draft("101", valid_profile(), 0, "ops")
        result = service.approve_profile("101", saved["draft_revision"], "ops")
        self.assertTrue(result["published"])
        self.assertEqual(result["background_blockers"], [])

    def test_approved_settings_values_are_valid_for_the_public_loader(self):
        service = self.service()
        draft = service.save_settings_draft(valid_settings_values(), 0, "ops")
        service.approve_settings(draft["draft_revision"], "manager")
        self.assertTrue(valid_settings().launch_ready)
        self.assertEqual(
            service.approved_settings_values()["long_stay_route"],
            "monthly_contract_review",
        )


if __name__ == "__main__":
    unittest.main()
