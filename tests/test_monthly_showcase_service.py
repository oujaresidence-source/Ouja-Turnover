import json
import tempfile
import unittest
from pathlib import Path


from monthly_public.showcase_service import (
    ShowcaseNotFound,
    ShowcaseService,
    present_showcase,
)
from monthly_public.showcase_store import ShowcaseStore
from monthly_public.snapshot import build_generation
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings
from tests.test_monthly_public_snapshot import source_with
from tests.test_monthly_showcase_contracts import valid_group


SECRET = b"test-only-monthly-showcase-key-32b"


class ShowcaseServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw_listings = [
            valid_listing(id="101", slug="home-101"),
            valid_listing(id="102", slug="home-102", official_prices={}),
            valid_listing(id="103", slug="home-103", licence=None),
        ]
        self.source = source_with(self.raw_listings)
        self.generation = build_generation(self.source, valid_settings(), NOW)
        self.store = ShowcaseStore(Path(self.tmp.name) / "showcases.sqlite3")
        self.service = ShowcaseService(
            store=self.store,
            inventory_provider=lambda: self.source,
            snapshot_provider=lambda: self.generation,
            session_secret=SECRET,
            clock=lambda: NOW,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _approve(self, **overrides):
        value = valid_group(
            slug="one-building",
            listing_ids=["101", "102", "103"],
            **overrides,
        )
        saved = self.service.save_draft(
            "showcase_a1",
            value,
            0,
            "faisal",
        )
        return self.service.approve(
            "showcase_a1",
            saved["draft_revision"],
            "faisal",
        )

    def test_public_group_counts_only_current_eligible_members(self):
        self._approve(fixed_price_enabled=False)

        public = self.service.public_by_slug("one-building", "ar")

        self.assertEqual(public["configured_count"], 3)
        self.assertEqual(public["eligible_count"], 1)
        self.assertEqual(
            [row.listing["id"] for row in public["results"]],
            ["101"],
        )

    def test_active_group_price_satisfies_only_the_price_blocker(self):
        self._approve(fixed_price_enabled=True)

        public = self.service.public_by_slug("one-building", "ar")

        self.assertEqual(
            [row.listing["id"] for row in public["results"]],
            ["101", "102"],
        )
        self.assertIsNotNone(
            self.service.eligible_result(public["group"], "102")
        )
        self.assertIsNone(
            self.service.eligible_result(public["group"], "103")
        )

    def test_context_resolves_latest_approved_state_not_client_revision(self):
        approved = self._approve(fixed_price_enabled=True)
        token = self.service.context_for_slug("one-building")["context"]
        self.service.set_price_enabled(
            "showcase_a1",
            False,
            approved["approved_revision"],
            "faisal",
        )

        resolved = self.service.resolve_context(token)

        self.assertFalse(resolved["group"]["fixed_price_enabled"])
        self.assertGreater(resolved["revision"], approved["approved_revision"])

    def test_blocked_members_stay_in_staff_record_and_memberships(self):
        self._approve(fixed_price_enabled=False)

        staff = self.service.group("showcase_a1")
        memberships = self.service.memberships()

        self.assertEqual(staff["configured_count"], 3)
        self.assertEqual(staff["blocked_listing_ids"], ["102", "103"])
        self.assertEqual(memberships["102"][0]["group_id"], "showcase_a1")

    def test_create_draft_uses_server_id_and_validates_current_inventory(self):
        created = self.service.create_draft(
            valid_group(listing_ids=["101"]),
            "faisal",
        )

        self.assertRegex(created["group_id"], r"^showcase_[A-Za-z0-9_-]{16}$")
        with self.assertRaises(Exception) as caught:
            self.service.create_draft(
                valid_group(listing_ids=["999"]),
                "faisal",
            )
        self.assertEqual(getattr(caught.exception, "field", None), "listing_ids.0")

    def test_public_presentation_has_no_configured_ids_or_raw_price_history(self):
        self._approve(fixed_price_enabled=True)
        public = present_showcase(
            self.service.public_by_slug("one-building", "ar"),
            "ar",
        )

        payload = json.dumps(public, ensure_ascii=False)
        self.assertEqual(public["eligible_count"], 2)
        self.assertEqual(public["fixed_monthly_rate_sar"], 12500)
        self.assertNotIn("listing_ids", payload)
        self.assertNotIn("official_prices", payload)
        self.assertNotIn("discount", payload.casefold())

    def test_missing_or_unapproved_slug_is_not_public(self):
        self.service.save_draft(
            "showcase_a1",
            valid_group(slug="draft-only"),
            0,
            "faisal",
        )

        with self.assertRaises(ShowcaseNotFound):
            self.service.public_by_slug("draft-only")
        with self.assertRaises(ShowcaseNotFound):
            self.service.public_by_slug("missing")

    def test_health_reports_approved_enabled_and_blocked_counts(self):
        self._approve(fixed_price_enabled=True)

        health = self.service.health()

        self.assertEqual(health["received"], 1)
        self.assertEqual(health["approved"], 1)
        self.assertEqual(health["fixed_price_enabled"], 1)
        self.assertEqual(health["blocked_members"], 1)
        self.assertTrue(health["configured"])
        self.assertTrue(health["write_probe"])


if __name__ == "__main__":
    unittest.main()
