import os
import tempfile
import unittest
from dataclasses import replace

from monthly_public.analytics import AnalyticsStore
from monthly_public.contracts import parse_event
from monthly_public.leads import LeadStore
from monthly_public.routes import MonthlyPublicApp
from monthly_public.snapshot import SnapshotStore
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


SECRET = b"monthly-public-test-secret-that-is-long-enough"
PLACES = {
    "kafd": {
        "kind": "destination",
        "label_ar": "مركز الملك عبدالله المالي",
        "label_en": "King Abdullah Financial District",
        "lat": 24.767,
        "lng": 46.643,
        "verified": True,
        "source": "owner_approved_registry",
    }
}


class BrokenAnalytics:
    def record(self, *_args, **_kwargs):
        raise RuntimeError("private analytics failure")

    def record_lifecycle(self, *_args, **_kwargs):
        raise RuntimeError("private analytics failure")

    def health(self):
        raise RuntimeError("private analytics failure")

    def events(self):
        raise RuntimeError("private analytics failure")


def match_request(**overrides):
    value = {
        "purpose": "work",
        "place": {"kind": "destination", "id": "kafd", "label": "untrusted"},
        "residents": 2,
        "sleeping": "one_bedroom",
        "move_in": "2026-09-01",
        "duration_months": 1,
        "flexibility": "fixed",
    }
    value.update(overrides)
    return value


class MonthlyPublicRouteContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = lambda: NOW
        listing = valid_listing()
        second = valid_listing(
            id=1002,
            slug="ouja-al-malqa-1002",
            name_ar="عوجا | بيت بغرفة في الملقا",
            name_en="Ouja | One-bedroom home in Al Malqa",
            bedrooms=1,
            beds=1,
            beds_count=1,
            capacity=2,
            facts={},
            official_prices={
                "2026-09": {
                    "monthly_rate_sar": 9000,
                    "currency": "SAR",
                    "source": "official_rate",
                    "verified_at": "2026-08-25T09:30:00+03:00",
                }
            },
        )
        self.snapshot = SnapshotStore()
        outcome = self.snapshot.refresh(
            {
                "refresh_ok": True,
                "catalog_complete": True,
                "listings": [listing, second],
                "source_timestamps": {"calendar": "2026-08-25T09:40:00+03:00"},
            },
            valid_settings(),
            NOW,
        )
        self.assertTrue(outcome.accepted)
        self.leads = LeadStore(
            os.path.join(self.tmp.name, "leads.sqlite3"),
            clock=self.clock,
            reference_factory=lambda _now: "OJM-20260825-ROUTES",
        )
        self.analytics = AnalyticsStore(
            os.path.join(self.tmp.name, "analytics.sqlite3"), clock=self.clock
        )
        self.app = MonthlyPublicApp(
            snapshot_store=self.snapshot,
            settings=valid_settings(),
            lead_store=self.leads,
            analytics_store=self.analytics,
            approved_places=PLACES,
            session_secret=SECRET,
            clock=self.clock,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def session(self):
        return self.app.config()["session_id"]

    def test_config_issues_signed_session_and_safe_arabic_first_choices(self):
        result = self.app.config()
        self.assertTrue(result["ok"])
        self.assertEqual(result["default_lang"], "ar")
        self.assertEqual(result["eligible_count"], 2)
        self.assertEqual(result["places"][0]["id"], "kafd")
        self.assertNotIn("lat", result["places"][0])
        self.assertNotIn("lng", result["places"][0])
        self.assertNotIn("whatsapp", result)
        self.assertEqual(
            parse_event(
                {"event": "landing_view", "session_id": result["session_id"]},
                session_secret=SECRET,
            )["session_id"],
            result["session_id"],
        )

    def test_config_without_secret_is_explicitly_blocked_and_issues_no_session(self):
        app = MonthlyPublicApp(
            snapshot_store=self.snapshot,
            settings=valid_settings(),
            lead_store=self.leads,
            analytics_store=self.analytics,
            approved_places=PLACES,
            session_secret=None,
            clock=self.clock,
        )
        result = app.config()
        self.assertIsNone(result["session_id"])
        self.assertIn("session_secret_missing", {row["code"] for row in result["blockers"]})

    def test_config_reports_missing_snapshot_as_an_explicit_blocker(self):
        app = MonthlyPublicApp(
            snapshot_store=SnapshotStore(),
            settings=valid_settings(),
            lead_store=self.leads,
            analytics_store=self.analytics,
            approved_places=PLACES,
            session_secret=SECRET,
            clock=self.clock,
        )
        result = app.config()
        self.assertEqual(result["eligible_count"], 0)
        self.assertIn("snapshot_missing", {row["code"] for row in result["blockers"]})

    def test_browse_without_dates_has_all_cards_and_no_invented_price(self):
        result = self.app.browse({"lang": "en"})
        self.assertTrue(result["ok"])
        self.assertEqual([row["id"] for row in result["results"]], ["1001", "1002"])
        self.assertTrue(all("quote" not in row for row in result["results"]))
        self.assertEqual(self.app.search({"lang": "en"})["results"], result["results"])

    def test_dated_browse_filters_and_requires_exact_cached_quote(self):
        result = self.app.browse(
            {
                "move_in": "2026-09-01",
                "duration_months": 1,
                "residents": 3,
                "bedrooms": 2,
                "neighborhood": "al_malqa",
                "lang": "ar",
            }
        )
        self.assertEqual([row["id"] for row in result["results"]], ["1001"])
        self.assertEqual(result["results"][0]["quote"]["stay_total_sar"], 12000)

    def test_match_listing_and_quote_use_only_published_generation(self):
        matched = self.app.match(match_request(), lang="en")
        self.assertTrue(matched["ok"])
        self.assertEqual(matched["top"][0]["id"], "1001")
        detail = self.app.listing(
            {
                "listing_id": "1001",
                "move_in": "2026-09-01",
                "duration_months": 1,
                "lang": "en",
            }
        )
        self.assertEqual(detail["listing"]["id"], "1001")
        self.assertEqual(detail["quote_status"], "available")
        quote = self.app.quote(
            {"listing_id": "1001", "move_in": "2026-09-01", "duration_months": 1}
        )
        self.assertEqual(quote["quote"]["monthly_rate_sar"], 12000)
        missing = self.app.listing({"listing_id": "no-such-listing"})
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "listing_not_found")

    def test_stale_selected_month_is_an_honest_missing_price_state(self):
        result = self.app.quote(
            {"listing_id": "1001", "move_in": "2026-10-01", "duration_months": 1}
        )
        self.assertTrue(result["ok"])
        self.assertIsNone(result["quote"])
        self.assertEqual(result["quote_status"], "price_missing")

    def test_lead_recomputes_quote_and_rejects_client_price_message_and_reference(self):
        payload = {
            "session_id": self.session(),
            "listing_id": "1001",
            "request": match_request(),
            "lang": "ar",
        }
        made = self.app.lead(payload)
        self.assertTrue(made["ok"])
        self.assertIn("SAR 12,000", made["message"])
        self.assertTrue(made["url"].startswith("https://wa.me/966500000000?text="))
        self.assertEqual(self.leads.get(made["lead_reference"])["quote"]["stay_total_sar"], 12000)
        for field, value in (
            ("price", 1),
            ("message", "cheap please"),
            ("lead_reference", "OJM-FAKE"),
        ):
            rejected = self.app.lead({**payload, field: value})
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error"]["code"], "unknown_field")

    def test_analytics_failure_never_blocks_navigation_or_lead_creation(self):
        app = MonthlyPublicApp(
            snapshot_store=self.snapshot,
            settings=valid_settings(),
            lead_store=self.leads,
            analytics_store=BrokenAnalytics(),
            approved_places=PLACES,
            session_secret=SECRET,
            clock=self.clock,
        )
        self.assertTrue(app.browse({})["ok"])
        made = app.lead(
            {
                "session_id": app.config()["session_id"],
                "listing_id": "1001",
                "request": match_request(),
                "lang": "ar",
            }
        )
        self.assertTrue(made["ok"])
        self.assertFalse(made["analytics_recorded"])

    def test_missing_whatsapp_blocks_handoff_without_creating_a_lead(self):
        app = MonthlyPublicApp(
            snapshot_store=self.snapshot,
            settings=replace(valid_settings(), whatsapp_number=None),
            lead_store=self.leads,
            analytics_store=self.analytics,
            approved_places=PLACES,
            session_secret=SECRET,
            clock=self.clock,
        )
        made = app.lead(
            {
                "session_id": app.config()["session_id"],
                "listing_id": "1001",
                "request": match_request(),
                "lang": "ar",
            }
        )
        self.assertFalse(made["ok"])
        self.assertEqual(made["error"]["code"], "whatsapp_not_configured")
        self.assertEqual(self.leads.count(), 0)

    def test_event_and_malformed_input_are_safe_and_bilingual(self):
        event = self.app.event(
            {"event": "landing_view", "session_id": self.session(), "context": {"phone": "secret"}}
        )
        self.assertTrue(event["ok"])
        self.assertNotIn("phone", event["event"]["context"])
        bad = self.app.browse({"duration_months": "oops"})
        self.assertFalse(bad["ok"])
        self.assertIn("message_ar", bad["error"])
        self.assertIn("message_en", bad["error"])
        self.assertNotIn("Traceback", repr(bad))

    def test_verified_snapshot_neighborhood_is_valid_for_event_and_lead(self):
        session = self.session()
        event = self.app.event(
            {
                "event": "matcher_answer",
                "session_id": session,
                "context": {"question": "place", "answer": "al_malqa"},
            }
        )
        self.assertTrue(event["ok"])
        made = self.app.lead(
            {
                "session_id": session,
                "listing_id": "1001",
                "request": match_request(
                    place={"kind": "neighborhood", "id": "al_malqa", "label": "forged"}
                ),
                "lang": "ar",
            }
        )
        self.assertTrue(made["ok"])
        self.assertIn("الملقا / Al Malqa", made["message"])

    def test_ops_service_is_separate_and_tracks_response_and_outcome(self):
        self.assertFalse(hasattr(self.app, "mark_response"))
        made = self.app.lead(
            {
                "session_id": self.session(),
                "listing_id": "1001",
                "request": match_request(),
                "lang": "ar",
            }
        )
        health = self.app.ops.health()
        self.assertIn("ready", health)
        funnel = self.app.ops.funnel()
        self.assertEqual(funnel["leads"]["created"], 1)
        responded = self.app.ops.response({"lead_reference": made["lead_reference"]})
        self.assertTrue(responded["ok"])
        outcome = self.app.ops.outcome(
            {"lead_reference": made["lead_reference"], "outcome": "lost", "lost_reason": "price"}
        )
        self.assertTrue(outcome["ok"])
        self.assertEqual(self.leads.get(made["lead_reference"])["lost_reason"], "price")


if __name__ == "__main__":
    unittest.main()
