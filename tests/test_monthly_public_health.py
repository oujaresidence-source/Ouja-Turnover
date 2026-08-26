import datetime as dt
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from monthly_public.analytics import AnalyticsStore
from monthly_public.health import build_health
from monthly_public.leads import LeadStore
from monthly_public.settings import load_settings
from monthly_public.snapshot import build_generation
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


def source(listings):
    return {
        "refresh_ok": True,
        "catalog_complete": True,
        "listings": listings,
        "source_timestamps": {"catalog": "2026-08-25T09:45:00+03:00"},
    }


class HealthTests(unittest.TestCase):
    def test_health_names_catalog_readiness_and_safe_action_links(self):
        listing = valid_listing(content_verified=False)
        generation = build_generation(source([listing]), valid_settings(), NOW)
        catalog = {
            "configured": True,
            "approved_profiles": 12,
            "drafts_waiting": 3,
            "published_profiles": 9,
            "profile_completion_average": 84.5,
            "settings_source": "catalog_approved",
            "settings_ready": True,
            "active_destinations": 4,
            "write_probe": True,
            "journal_mode": "delete",
        }

        report = build_health(
            generation, valid_settings(), catalog=catalog, now=NOW
        )

        self.assertEqual(report["catalog"]["approved_profiles"], 12)
        self.assertEqual(report["catalog"]["drafts_waiting"], 3)
        self.assertTrue(report["catalog"]["write_probe"])
        issue = report["content_conflicts"]["1001"][0]
        self.assertEqual(
            issue["action_url"],
            "/monthly/ops/listings?id=1001&section=content",
        )

    def test_unwritable_catalog_store_is_a_red_launch_blocker(self):
        generation = build_generation(source([valid_listing()]), valid_settings(), NOW)
        report = build_health(
            generation,
            valid_settings(),
            catalog={"configured": True, "write_probe": False},
            now=NOW,
        )
        self.assertIn(
            "catalog_store_unhealthy",
            {issue["code"] for issue in report["red_blockers"]},
        )
        self.assertFalse(report["ready"])

    def test_exact_counts_and_zero_red_blockers_are_ready(self):
        generation = build_generation(source([valid_listing(id=1001), valid_listing(id=1002, slug="ouja-1002")]), valid_settings(), NOW)
        with tempfile.TemporaryDirectory() as folder:
            analytics = AnalyticsStore(Path(folder) / "analytics.sqlite3", clock=lambda: NOW)
            leads = LeadStore(Path(folder) / "leads.sqlite3", clock=lambda: NOW)
            report = build_health(
                generation,
                valid_settings(),
                analytics=analytics,
                lead_store=leads,
                now=NOW,
            )
            analytics_rows = analytics.events()
            lead_count = leads.count()

        self.assertEqual(report["refresh_time"], generation.generated_at)
        self.assertEqual(report["counts"], {"received": 2, "valid": 2, "blocked": 0, "published": 2})
        self.assertEqual(report["coverage"], {"calendar": 2, "price": 2, "review": 0})
        self.assertTrue(report["configuration"]["whatsapp"])
        self.assertTrue(report["configuration"]["working_hours"])
        self.assertTrue(report["contract_4_6_months"]["ready"])
        self.assertTrue(report["analytics"]["healthy"])
        self.assertTrue(report["leads"]["healthy"])
        self.assertTrue(report["analytics"]["write_probe"])
        self.assertTrue(report["leads"]["write_probe"])
        self.assertEqual(analytics_rows, [])
        self.assertEqual(lead_count, 0)
        self.assertEqual(report["red_blockers"], [])
        self.assertTrue(report["ready"])
        self.assertEqual(report["generation_id"], generation.generation_id)
        self.assertEqual(report["source_timestamps"], {"catalog": "2026-08-25T09:45:00+03:00"})
        self.assertEqual(report["coverage_details"]["calendar"]["missing_ids"], [])
        self.assertEqual(report["coverage_details"]["price"]["missing_ids"], [])
        self.assertEqual(report["coverage_details"]["review"]["missing_ids"], ["1001", "1002"])

    def test_review_coverage_counts_only_listing_specific_public_projections(self):
        reviewed = valid_listing(id=1001)
        reviewed["public_reviews"] = {
            "rating_value": 4.8,
            "rating_scale": 5,
            "rating_count": 5,
            "text_review_count": 0,
            "source_label": "approved_public_reviews",
            "topic_mentions": [],
            "category_scores": [],
            "latest_reviews": [],
        }
        generation = build_generation(
            source([reviewed, valid_listing(id=1002, slug="ouja-1002")]),
            valid_settings(),
            NOW,
        )

        report = build_health(generation, valid_settings(), now=NOW)

        self.assertEqual(report["coverage"]["review"], 1)
        self.assertEqual(report["coverage_details"]["review"]["missing_ids"], ["1002"])

    def test_publication_blockers_include_licence_and_content_details(self):
        content = valid_listing(id=1001, content_verified=False)
        licence = valid_listing(id=1002, slug="ouja-1002")
        licence["licence"]["expires"] = "2026-08-24"
        generation = build_generation(source([content, licence]), valid_settings(), NOW)

        report = build_health(generation, valid_settings(), now=NOW)

        self.assertEqual(report["counts"], {"received": 2, "valid": 2, "blocked": 2, "published": 0})
        self.assertIn("1001", report["content_conflicts"])
        self.assertIn("1002", report["licence_expiry"])
        codes = {item["code"] for item in report["red_blockers"]}
        self.assertIn("content_unverified", codes)
        self.assertIn("licence_expired", codes)
        self.assertFalse(report["ready"])

    def test_settings_and_contract_blockers_are_explicit(self):
        settings = load_settings({})
        generation = build_generation(source([valid_listing()]), settings, NOW)

        report = build_health(generation, settings, now=NOW)

        self.assertFalse(report["configuration"]["whatsapp"])
        self.assertFalse(report["configuration"]["working_hours"])
        self.assertFalse(report["contract_4_6_months"]["ready"])
        codes = {item["code"] for item in report["red_blockers"]}
        self.assertIn("whatsapp_missing", codes)
        self.assertIn("working_hours_missing", codes)
        self.assertIn("long_stay_route_missing", codes)

    def test_expiring_licence_is_reported_as_an_issue_without_fabricating_blocker(self):
        listing = valid_listing()
        listing["licence"]["expires"] = "2026-09-01"
        generation = build_generation(source([listing]), valid_settings(), NOW)
        with tempfile.TemporaryDirectory() as folder:
            report = build_health(
                generation,
                valid_settings(),
                analytics=AnalyticsStore(Path(folder) / "analytics.sqlite3", clock=lambda: NOW),
                lead_store=LeadStore(Path(folder) / "leads.sqlite3", clock=lambda: NOW),
                now=NOW,
            )
        self.assertIn("1001", report["licence_expiry"])
        self.assertEqual(report["licence_expiry"]["1001"][0]["code"], "licence_expiring")
        self.assertTrue(report["ready"])

    def test_request_time_stale_calendar_is_not_reported_ready(self):
        generation = build_generation(source([valid_listing()]), valid_settings(), NOW)
        checked = NOW + dt.timedelta(minutes=61)
        with tempfile.TemporaryDirectory() as folder:
            report = build_health(
                generation,
                valid_settings(),
                analytics=AnalyticsStore(Path(folder) / "analytics.sqlite3", clock=lambda: checked),
                lead_store=LeadStore(Path(folder) / "leads.sqlite3", clock=lambda: checked),
                now=checked,
            )

        self.assertFalse(report["ready"])
        self.assertEqual(report["coverage"]["calendar"], 0)
        self.assertEqual(report["coverage_details"]["calendar"]["stale_ids"], ["1001"])
        self.assertIn(
            "calendar_stale", {row["code"] for row in report["red_blockers"]}
        )

    def test_missing_conversion_stores_are_red_launch_blockers(self):
        generation = build_generation(source([valid_listing()]), valid_settings(), NOW)
        report = build_health(generation, valid_settings(), now=NOW)

        self.assertFalse(report["ready"])
        self.assertFalse(report["analytics"]["configured"])
        self.assertFalse(report["leads"]["configured"])
        codes = {item["code"] for item in report["red_blockers"]}
        self.assertIn("analytics_missing", codes)
        self.assertIn("lead_store_missing", codes)

    def test_locked_conversion_store_fails_write_probe_quickly_without_rows(self):
        generation = build_generation(source([valid_listing()]), valid_settings(), NOW)
        with tempfile.TemporaryDirectory() as folder:
            analytics = AnalyticsStore(Path(folder) / "analytics.sqlite3", clock=lambda: NOW)
            leads = LeadStore(Path(folder) / "leads.sqlite3", clock=lambda: NOW)
            for name, store, other in (
                ("analytics", analytics, leads),
                ("leads", leads, analytics),
            ):
                with self.subTest(name=name):
                    locker = sqlite3.connect(str(store.path))
                    locker.execute("BEGIN EXCLUSIVE")
                    try:
                        started = time.monotonic()
                        report = build_health(
                            generation,
                            valid_settings(),
                            analytics=analytics,
                            lead_store=leads,
                            now=NOW,
                        )
                        elapsed = time.monotonic() - started
                    finally:
                        locker.rollback()
                        locker.close()
                    self.assertFalse(report[name]["healthy"])
                    self.assertFalse(report["ready"])
                    self.assertLess(elapsed, 1.0)
            self.assertEqual(analytics.events(), [])
            self.assertEqual(leads.count(), 0)

    def test_all_content_issues_are_classified(self):
        listing = valid_listing(name_en="", amenities=["Wireless", "Unknown private amenity"])
        generation = build_generation(source([listing]), valid_settings(), NOW)
        report = build_health(generation, valid_settings(), now=NOW)
        codes = {item["code"] for item in report["content_conflicts"]["1001"]}
        self.assertIn("english_title_missing", codes)
        self.assertIn("untranslated_amenity", codes)

    def test_analytics_health_exception_becomes_a_red_blocker(self):
        class BrokenHealth:
            def health(self):
                raise RuntimeError("unavailable")

        generation = build_generation(source([valid_listing()]), valid_settings(), NOW)
        report = build_health(generation, valid_settings(), analytics=BrokenHealth(), now=NOW)
        self.assertFalse(report["analytics"]["healthy"])
        self.assertIn("analytics_unhealthy", {item["code"] for item in report["red_blockers"]})


if __name__ == "__main__":
    unittest.main()
