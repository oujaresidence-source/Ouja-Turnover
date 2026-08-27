import json
import tempfile
import unittest
from pathlib import Path


from monthly_public.analytics import AnalyticsStore
from monthly_public.leads import LeadStore
from monthly_public.routes import MonthlyPublicApp
from monthly_public.showcase_service import ShowcaseService
from monthly_public.showcase_store import ShowcaseStore
from monthly_public.snapshot import SnapshotStore
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings
from tests.test_monthly_public_routes import PLACES, SECRET, match_request
from tests.test_monthly_showcase_contracts import valid_group


class ShowcaseRouteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        second = valid_listing(
            id="102",
            slug="home-102",
            name_ar="عوجا | بيت 102 بغرفتين في الملقا",
            name_en="Ouja | Home 102 with 2BR in Al Malqa",
            official_prices={},
        )
        third = valid_listing(
            id="103",
            slug="home-103",
            name_ar="عوجا | بيت 103 بغرفتين في الملقا",
            name_en="Ouja | Home 103 with 2BR in Al Malqa",
        )
        self.source = {
            "refresh_ok": True,
            "catalog_complete": True,
            "listings": [valid_listing(id="101", slug="home-101"), second, third],
            "source_timestamps": {"calendar": "2026-08-25T09:40:00+03:00"},
        }
        self.snapshot = SnapshotStore()
        self.assertTrue(
            self.snapshot.refresh(
                self.source,
                valid_settings(),
                NOW,
            ).accepted
        )
        self.showcase_store = ShowcaseStore(Path(self.tmp.name) / "showcases.sqlite3")
        self.showcases = ShowcaseService(
            store=self.showcase_store,
            inventory_provider=lambda: self.source,
            snapshot_provider=lambda: self.snapshot.current,
            session_secret=SECRET,
            clock=lambda: NOW,
        )
        draft = self.showcases.save_draft(
            "showcase_a1",
            valid_group(
                slug="one-building",
                listing_ids=["101", "102"],
                fixed_monthly_rate_sar=12500,
                fixed_price_enabled=True,
            ),
            0,
            "faisal",
        )
        self.approved = self.showcases.approve(
            "showcase_a1",
            draft["draft_revision"],
            "faisal",
        )
        self.leads = LeadStore(
            Path(self.tmp.name) / "leads.sqlite3",
            clock=lambda: NOW,
            reference_factory=lambda _now: "OJM-20260825-SHOWCASE",
        )
        self.analytics = AnalyticsStore(
            Path(self.tmp.name) / "analytics.sqlite3",
            clock=lambda: NOW,
        )
        self.app = MonthlyPublicApp(
            snapshot_store=self.snapshot,
            settings=valid_settings(),
            lead_store=self.leads,
            analytics_store=self.analytics,
            approved_places=PLACES,
            session_secret=SECRET,
            clock=lambda: NOW,
            showcase_service=self.showcases,
        )
        self.token = self.showcases.context_for_slug("one-building")["context"]

    def tearDown(self):
        self.tmp.cleanup()

    def listing_request(self, listing_id, **overrides):
        value = {
            "listing_id": listing_id,
            "move_in": "2026-09-01",
            "duration_months": 1,
            "lang": "ar",
            "showcase_context": self.token,
        }
        value.update(overrides)
        return value

    def test_showcase_endpoint_returns_only_approved_eligible_members(self):
        result = self.app.showcase({"slug": "one-building", "lang": "ar"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["showcase"]["eligible_count"], 2)
        self.assertEqual(
            [home["id"] for home in result["showcase"]["homes"]],
            ["101", "102"],
        )
        self.assertNotIn("configured_listing_ids", result["showcase"])
        self.assertNotIn("listing_ids", json.dumps(result["showcase"]))

    def test_listing_uses_server_price_and_rejects_tampered_context(self):
        good = self.app.listing(self.listing_request("101"))
        bad = self.app.listing(
            self.listing_request("101", showcase_context=self.token + "x")
        )

        self.assertEqual(good["quote"]["monthly_rate_sar"], 12500)
        self.assertEqual(good["showcase"]["price_mode"], "fixed")
        self.assertEqual(bad["error"]["code"], "invalid_showcase_context")

    def test_group_price_can_publish_a_price_only_blocked_member(self):
        result = self.app.listing(self.listing_request("102"))

        self.assertTrue(result["ok"])
        self.assertEqual(result["listing"]["id"], "102")
        self.assertEqual(result["quote"]["monthly_rate_sar"], 12500)

    def test_context_cannot_price_a_non_member(self):
        result = self.app.listing(self.listing_request("103"))

        self.assertEqual(result["error"]["code"], "showcase_listing_mismatch")

    def test_disabled_price_returns_to_original_and_keeps_url_alive(self):
        self.showcases.set_price_enabled(
            "showcase_a1",
            False,
            self.approved["approved_revision"],
            "faisal",
        )

        public = self.app.showcase({"slug": "one-building", "lang": "ar"})
        original = self.app.listing(self.listing_request("101"))
        missing = self.app.listing(self.listing_request("102"))

        self.assertTrue(public["ok"])
        self.assertEqual(public["showcase"]["price_mode"], "listing")
        self.assertEqual(public["showcase"]["eligible_count"], 1)
        self.assertEqual(original["quote"]["monthly_rate_sar"], 12000)
        self.assertEqual(missing["error"]["code"], "listing_not_found")

    def test_lead_stores_group_reference_not_message_and_prepares_group_handoff(self):
        session = self.app.config()["session_id"]

        result = self.app.lead(
            {
                "session_id": session,
                "journey_id": "journey_AAAAAAAAAAAAAAAAAAAAAA",
                "listing_id": "102",
                "showcase_context": self.token,
                "request": match_request(),
                "lang": "ar",
            }
        )

        self.assertTrue(result["ok"])
        self.assertIn("one-building", result["message"])
        stored = self.leads.get(result["lead_reference"])
        self.assertEqual(stored["showcase"]["group_id"], "showcase_a1")
        self.assertEqual(stored["showcase"]["price_mode"], "fixed")
        stored_json = json.dumps(stored, ensure_ascii=False)
        self.assertNotIn(result["message"], stored_json)
        staff = self.app.ops.lead({"lead_reference": result["lead_reference"]})
        self.assertEqual(staff["lead"]["showcase"]["group_id"], "showcase_a1")
        event_names = [
            row["event"]
            for row in self.analytics.events()
            if row["lead_reference"] == result["lead_reference"]
        ]
        self.assertEqual(
            event_names,
            [
                "whatsapp_click",
                "lead_created",
                "showcase_whatsapp_click",
                "showcase_lead_created",
            ],
        )

    def test_normal_catalog_price_is_unchanged_without_showcase_context(self):
        result = self.app.listing(
            {
                "listing_id": "101",
                "move_in": "2026-09-01",
                "duration_months": 1,
            }
        )

        self.assertEqual(result["quote"]["monthly_rate_sar"], 12000)
        self.assertNotIn("showcase", result)


if __name__ == "__main__":
    unittest.main()
