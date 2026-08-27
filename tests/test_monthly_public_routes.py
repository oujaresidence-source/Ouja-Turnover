import datetime as dt
import json
import os
import subprocess
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
ROOT = os.path.dirname(os.path.dirname(__file__))
JS_PATH = os.path.join(ROOT, "monthly_public", "static", "monthly.js")
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
        self.now = NOW
        self.clock = lambda: self.now
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

    def test_config_exposes_purpose_scope_but_not_destination_coordinates(self):
        replacement = dict(
            PLACES["kafd"], purposes=["work", "visit"]
        )
        self.app.replace_configuration(valid_settings(), {"kafd": replacement})

        result = self.app.config()

        self.assertEqual(result["places"][0]["purposes"], ["work", "visit"])
        self.assertNotIn("lat", result["places"][0])
        self.assertNotIn("lng", result["places"][0])

    def test_destination_cannot_be_submitted_for_an_unapproved_purpose(self):
        replacement = dict(PLACES["kafd"], purposes=["treatment"])
        self.app.replace_configuration(valid_settings(), {"kafd": replacement})

        result = self.app.match(match_request(purpose="work"), "ar")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "place_purpose_not_allowed")
        self.assertEqual(result["error"]["field"], "place.id")

    def test_replace_configuration_updates_settings_and_places_together(self):
        replacement = {
            "hospital": {
                "kind": "destination",
                "label_ar": "مستشفى معتمد",
                "label_en": "Approved Hospital",
                "lat": 24.71,
                "lng": 46.68,
                "verified": True,
                "source": "approved_catalog",
            }
        }
        new_settings = replace(valid_settings(), whatsapp_number="966500000001")

        self.app.replace_configuration(new_settings, replacement)
        result = self.app.config("ar")

        self.assertEqual([row["id"] for row in result["places"]], ["hospital"])
        made = self.app.lead(
            {
                "session_id": result["session_id"],
                "listing_id": "1001",
                "request": match_request(
                    place={"kind": "destination", "id": "hospital", "label": "x"}
                ),
                "lang": "ar",
            }
        )
        self.assertTrue(made["ok"])
        self.assertTrue(made["url"].startswith("https://wa.me/966500000001?text="))

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
        matched = self.app.match(
            match_request(price_priority="experience"), lang="en"
        )
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

    def test_flexible_duration_match_card_opens_a_monthly_rate_quote(self):
        flexible = valid_listing()
        flexible["calendar"]["blocked_dates"] = ["2026-09-01"]
        snapshot = SnapshotStore()
        self.assertTrue(snapshot.refresh(
            {
                "refresh_ok": True,
                "catalog_complete": True,
                "listings": [flexible],
                "source_timestamps": {"calendar": "2026-08-25T09:40:00+03:00"},
            },
            valid_settings(),
            NOW,
        ).accepted)
        app = MonthlyPublicApp(
            snapshot_store=snapshot,
            settings=valid_settings(),
            lead_store=self.leads,
            analytics_store=self.analytics,
            approved_places=PLACES,
            session_secret=SECRET,
            clock=self.clock,
        )
        request = match_request(flexibility="plus_minus_7")
        near = app.match(request, lang="en")["near_matches"][0]
        script = (
            "const ui=require(%s);const canonical=ui.canonicalListingRequest(%s,%s);"
            "process.stdout.write(JSON.stringify(typeof ui.listingQuoteRequest==='function'"
            "?{canonical:canonical,quote:ui.listingQuoteRequest(canonical)}:{missing:true}));"
            % (json.dumps(JS_PATH), json.dumps(request), json.dumps(near))
        )
        browser_flow = json.loads(subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout)

        self.assertNotIn("missing", browser_flow)
        listing_request = browser_flow["canonical"]
        self.assertEqual(listing_request["move_in"], near["adjusted_move_in"])
        self.assertEqual(listing_request.get("duration_months"), 1)
        self.assertNotIn("move_out", listing_request)
        detail = app.listing({
            "listing_id": near["id"],
            "lang": "en",
            **browser_flow["quote"],
        })
        self.assertEqual(detail["quote_status"], "available")
        self.assertEqual(detail["quote"]["monthly_rate_sar"], 12000)
        self.assertEqual(detail["quote"]["months"], 1)

    def test_stale_selected_month_is_an_honest_missing_price_state(self):
        result = self.app.quote(
            {"listing_id": "1001", "move_in": "2026-10-01", "duration_months": 1}
        )
        self.assertTrue(result["ok"])
        self.assertIsNone(result["quote"])
        self.assertEqual(result["quote_status"], "price_missing")

    def test_customer_reads_recheck_calendar_freshness_at_request_time(self):
        self.now = NOW + dt.timedelta(minutes=61)
        dated = {"move_in": "2026-09-01", "duration_months": 1}

        undated = self.app.browse({"lang": "en"})
        self.assertTrue(undated["results"])
        self.assertTrue(all(
            row["availability_status"] == "pending" for row in undated["results"]
        ))
        browsed = self.app.browse(dated)
        self.assertEqual(browsed["results"], [])
        self.assertEqual(browsed["counts"]["pending"], 2)
        matched = self.app.match(match_request(), lang="en")
        self.assertEqual(matched["top"], ())
        self.assertEqual(matched["pending_count"], 2)
        detail = self.app.listing({"listing_id": "1001", **dated})
        self.assertEqual(detail["quote_status"], "pending")
        made = self.app.lead(
            {
                "session_id": self.session(),
                "listing_id": "1001",
                "request": match_request(),
                "lang": "ar",
            }
        )
        self.assertFalse(made["ok"])
        self.assertEqual(made["error"]["code"], "availability_pending")
        self.assertEqual(self.leads.count(), 0)

    def test_expired_licence_is_removed_and_makes_health_not_ready(self):
        expiring = valid_listing()
        expiring["licence"]["expires"] = NOW.date().isoformat()
        refreshed = self.snapshot.refresh(
            {
                "refresh_ok": True,
                "catalog_complete": True,
                "listings": [expiring],
            },
            valid_settings(),
            NOW,
        )
        self.assertTrue(refreshed.accepted)
        self.now = NOW + dt.timedelta(days=1)

        self.assertEqual(self.app.config()["eligible_count"], 0)
        self.assertEqual(self.app.browse({"lang": "en"})["results"], [])
        self.assertEqual(
            self.app.listing({"listing_id": "1001"})["error"]["code"],
            "listing_not_found",
        )
        health = self.app.ops.health()
        self.assertFalse(health["ready"])
        self.assertIn(
            "licence_expired", {row["code"] for row in health["red_blockers"]}
        )

    def test_lead_recomputes_quote_and_rejects_client_price_message_and_reference(self):
        payload = {
            "session_id": self.session(),
            "journey_id": "journey_AAAAAAAAAAAAAAAAAAAAAA",
            "listing_id": "1001",
            "request": match_request(),
            "lang": "ar",
        }
        made = self.app.lead(payload)
        self.assertTrue(made["ok"])
        self.assertIn("SAR 12,000", made["message"])
        self.assertTrue(made["url"].startswith("https://wa.me/966500000000?text="))
        stored = self.leads.get(made["lead_reference"])
        self.assertEqual(stored["quote"]["stay_total_sar"], 12000)
        self.assertEqual(stored["journey_id"], payload["journey_id"])
        linked = [
            event for event in self.analytics.events()
            if event["lead_reference"] == made["lead_reference"]
        ]
        self.assertEqual(
            [event["event"] for event in linked],
            ["whatsapp_click", "lead_created"],
        )
        self.assertTrue(
            all(event["context"]["journey_id"] == payload["journey_id"] for event in linked)
        )
        for field, value in (
            ("price", 1),
            ("message", "cheap please"),
            ("lead_reference", "OJM-FAKE"),
        ):
            rejected = self.app.lead({**payload, field: value})
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error"]["code"], "unknown_field")

    def test_lead_rejects_a_listing_that_fails_capacity_or_sleeping_gates(self):
        session = self.session()
        for changes in (
            {"residents": 5},
            {"sleeping": "three_bedrooms"},
            {"residents": 4, "sleeping": "separate_beds"},
        ):
            with self.subTest(changes=changes):
                made = self.app.lead(
                    {
                        "session_id": session,
                        "listing_id": "1001",
                        "request": match_request(**changes),
                        "lang": "ar",
                    }
                )
                self.assertFalse(made["ok"])
                self.assertEqual(
                    made["error"]["code"], "listing_request_mismatch"
                )
        self.assertEqual(self.leads.count(), 0)

    def test_public_request_pins_generation_during_an_atomic_swap(self):
        first = SnapshotStore()
        second = SnapshotStore()
        self.assertTrue(first.refresh(
            {"refresh_ok": True, "catalog_complete": True,
             "listings": [valid_listing()]},
            valid_settings(), NOW,
        ).accepted)
        self.assertTrue(second.refresh(
            {"refresh_ok": True, "catalog_complete": True, "listings": [
                valid_listing(id=2001, slug="ouja-2001"),
                valid_listing(id=2002, slug="ouja-2002"),
            ]},
            valid_settings(), NOW,
        ).accepted)

        class SwappingStore:
            def __init__(self, old, new):
                self.old = old
                self.new = new
                self.reads = 0

            @property
            def current(self):
                self.reads += 1
                return self.old if self.reads == 1 else self.new

        swapping = SwappingStore(first.current, second.current)
        app = MonthlyPublicApp(
            snapshot_store=swapping,
            settings=valid_settings(),
            lead_store=self.leads,
            analytics_store=self.analytics,
            approved_places=PLACES,
            session_secret=SECRET,
            clock=self.clock,
        )

        config = app.config()

        self.assertEqual(config["eligible_count"], 1)
        self.assertEqual(swapping.reads, 1)

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

    def test_general_help_lead_is_allowed_only_for_a_verified_empty_match(self):
        session = self.session()
        empty_request = match_request(residents=50, sleeping="four_plus_bedrooms")

        made = self.app.lead(
            {
                "session_id": session,
                "general_help": True,
                "request": empty_request,
                "lang": "en",
            }
        )

        self.assertTrue(made["ok"])
        stored = self.leads.get(made["lead_reference"])
        self.assertEqual(stored["lead_kind"], "general_help")
        linked = [
            event for event in self.analytics.events()
            if event["lead_reference"] == made["lead_reference"]
        ]
        self.assertEqual(
            [event["event"] for event in linked],
            ["whatsapp_click", "lead_created"],
        )
        rejected = self.app.lead(
            {
                "session_id": session,
                "general_help": True,
                "request": match_request(),
                "lang": "en",
            }
        )
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "general_help_not_allowed")

    def test_general_help_does_not_bypass_pending_availability(self):
        self.now = NOW + dt.timedelta(minutes=61)

        made = self.app.lead(
            {
                "session_id": self.session(),
                "general_help": True,
                "request": match_request(),
                "lang": "ar",
            }
        )

        self.assertFalse(made["ok"])
        self.assertEqual(made["error"]["code"], "availability_pending")
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
        responded = self.app.ops.response(
            {
                "lead_reference": made["lead_reference"],
                "discount_requested": True,
            }
        )
        self.assertTrue(responded["ok"])
        self.assertIs(responded["lead"]["discount_requested"], True)
        outcome = self.app.ops.outcome(
            {"lead_reference": made["lead_reference"], "outcome": "lost", "lost_reason": "price"}
        )
        self.assertTrue(outcome["ok"])
        self.assertEqual(self.leads.get(made["lead_reference"])["lost_reason"], "price")

    def test_ops_health_reads_showcase_service_health_without_exposing_records(self):
        class HealthyShowcase:
            @staticmethod
            def health():
                return {
                    "configured": True,
                    "write_probe": True,
                    "received": 2,
                    "approved": 1,
                    "fixed_price_enabled": 1,
                    "blocked_members": 4,
                }

        self.app.showcase_service = HealthyShowcase()

        health = self.app.ops.health()

        self.assertEqual(health["showcase"]["received"], 2)
        self.assertEqual(health["showcase"]["approved"], 1)
        self.assertNotIn("records", health["showcase"])


if __name__ == "__main__":
    unittest.main()
