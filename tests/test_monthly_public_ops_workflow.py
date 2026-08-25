import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from monthly_public.analytics import AnalyticsStore
from monthly_public.contracts import issue_anonymous_session
from monthly_public.leads import LeadStore
from monthly_public.routes import MonthlyPublicApp
from monthly_public.snapshot import SnapshotStore
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


SECRET = b"monthly-ops-workflow-secret-32bytes"
PLACES = {
    "kafd": {
        "kind": "destination",
        "label_ar": "مركز الملك عبدالله المالي",
        "label_en": "King Abdullah Financial District",
        "verified": True,
    }
}


def saved_request():
    return {
        "purpose": "work",
        "place": {"kind": "destination", "id": "kafd"},
        "residents": 2,
        "sleeping": "one_bedroom",
        "move_in": "2026-09-01",
        "duration_months": 1,
        "flexibility": "fixed",
        "lang": "ar",
    }


class LeadActionStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "leads.sqlite3"
        self.store = LeadStore(
            self.path,
            clock=lambda: NOW,
            reference_factory=lambda _now: "OJM-20260825-ACTION",
        )
        self.session = issue_anonymous_session(SECRET)
        self.lead = self.store.create(
            self.session,
            "1001",
            saved_request(),
            {
                "monthly_rate_sar": 12000,
                "stay_total_sar": 12000,
                "currency": "SAR",
                "move_in": "2026-09-01",
                "move_out": "2026-10-01",
                "months": 1,
            },
            approved_places=PLACES,
        )

    def test_actions_append_and_only_the_first_starts_team_response(self):
        first = self.store.add_action(
            self.lead["reference"], "confirm_request", now=NOW + dt.timedelta(minutes=2)
        )
        second = self.store.add_action(
            self.lead["reference"],
            "request_information",
            reason="dates",
            now=NOW + dt.timedelta(minutes=3),
        )

        self.assertTrue(first["response_started"])
        self.assertFalse(second["response_started"])
        self.assertIsNotNone(self.store.get(self.lead["reference"])["responded_at"])
        actions = self.store.actions_for(self.lead["reference"])
        self.assertEqual([row["action"] for row in actions], [
            "confirm_request", "request_information",
        ])
        self.assertEqual(actions[1]["reason"], "dates")
        self.assertNotEqual(actions[0]["id"], actions[1]["id"])
        self.assertFalse(hasattr(self.store, "update_action"))
        self.assertFalse(hasattr(self.store, "delete_action"))

    def test_action_contract_rejects_free_text_and_incomplete_combinations(self):
        reference = self.lead["reference"]
        invalid = (
            ("confirm_request", {"reason": "dates"}),
            ("request_information", {}),
            ("request_information", {"reason": "tell me their phone"}),
            ("prepare_alternative", {"reason": "lower_price"}),
            ("prepare_alternative", {"reason": "cheap", "alternative_listing_id": "1002", "quote": {"monthly_rate_sar": 1}}),
        )
        for action, values in invalid:
            with self.subTest(action=action, values=values), self.assertRaises(ValueError):
                self.store.add_action(reference, action, **values)

    def test_prepared_alternative_stores_only_controlled_fields_and_canonical_quote(self):
        result = self.store.add_action(
            self.lead["reference"],
            "prepare_alternative",
            reason="lower_price",
            alternative_listing_id="1002",
            quote={
                "monthly_rate_sar": 9000,
                "stay_total_sar": 9000,
                "currency": "SAR",
                "move_in": "2026-09-01",
                "move_out": "2026-10-01",
                "months": 1,
                "message": "do not persist this prepared message",
                "title": "do not persist title",
            },
        )

        action = result["action"]
        self.assertEqual(action["alternative_listing_id"], "1002")
        self.assertEqual(action["quote"]["monthly_rate_sar"], 9000)
        self.assertNotIn("message", action["quote"])
        self.assertNotIn("title", action["quote"])
        raw = self.path.read_bytes().decode("latin1")
        self.assertNotIn("prepared message", raw)
        self.assertNotIn("persist title", raw)
        with sqlite3.connect(str(self.path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM monthly_public_lead_actions"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_lead_store_health_includes_the_staff_action_journal(self):
        with sqlite3.connect(str(self.path)) as connection:
            connection.execute("DROP TABLE monthly_public_lead_actions")

        health = self.store.health()

        self.assertFalse(health["healthy"])
        self.assertFalse(health["write_probe"])


class OpsLeadWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.now = NOW
        self.clock = lambda: self.now
        self.first = valid_listing()
        self.second = valid_listing(
            id=1002,
            slug="ouja-al-malqa-1002",
            name_ar="عوجا | بيت بديل بغرفة في الملقا",
            name_en="Ouja | Alternative one-bedroom home in Al Malqa",
            bedrooms=1,
            beds=1,
            beds_count=1,
            capacity=2,
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
        self.refresh(self.first, self.second)
        self.leads = LeadStore(
            Path(self.folder.name) / "leads.sqlite3",
            clock=self.clock,
            reference_factory=lambda _now: "OJM-20260825-WORKFLOW",
        )
        self.analytics = AnalyticsStore(
            Path(self.folder.name) / "analytics.sqlite3", clock=self.clock
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
        self.session = issue_anonymous_session(SECRET)
        self.record_journey()
        self.lead = self.leads.create(
            self.session,
            "1001",
            saved_request(),
            {
                "monthly_rate_sar": 12000,
                "stay_total_sar": 12000,
                "currency": "SAR",
                "move_in": "2026-09-01",
                "move_out": "2026-10-01",
                "months": 1,
                "included": ["internet", "maintenance"],
                "utilities": {"mode": "variable", "label_ar": "حسب الاستهلاك", "label_en": "By use"},
                "cleaning": {"mode": "optional", "amount_sar": 300, "label_ar": "اختياري", "label_en": "Optional"},
                "deposit": {"amount_sar": 2000, "refund_ar": "حسب الشروط", "refund_en": "Under terms"},
                "payment_methods": [{"ar": "تحويل بنكي", "en": "Bank transfer"}],
            },
            approved_places=PLACES,
        )
        self.analytics.record_lead_creation(
            self.session, self.lead["reference"], listing_id="1001", now=NOW
        )

    def refresh(self, *listings):
        outcome = self.snapshot.refresh(
            {
                "refresh_ok": True,
                "catalog_complete": True,
                "listings": list(listings),
                "source_timestamps": {"calendar": "2026-08-25T09:40:00+03:00"},
            },
            valid_settings(),
            self.now,
        )
        self.assertTrue(outcome.accepted)

    def record_journey(self):
        for event, context in (
            ("entry_route_choice", {"entry_route": "guided", "phone": "0500000000"}),
            ("matcher_completion", {"purpose": "work", "place_id": "kafd", "duration_months": 1}),
            ("result_impression", {"listing_id": "1001", "rank": 1}),
            ("result_impression", {"listing_id": "1002", "rank": 2}),
            ("listing_view", {"listing_id": "1001"}),
        ):
            self.analytics.record(
                {"event": event, "session_id": self.session, "context": context},
                session_secret=SECRET,
                allowed_place_ids=("kafd",),
                now=NOW,
            )

    def test_exact_lookup_returns_minimal_safe_detail_and_filtered_journey(self):
        result = self.app.ops.lead({"lead_reference": self.lead["reference"]})

        self.assertTrue(result["ok"])
        lead = result["lead"]
        self.assertEqual(set(lead), {
            "reference", "listing_id", "title", "request", "quote",
            "created_at", "responded_at", "discount_requested", "outcome",
            "outcome_at", "lost_reason", "actions", "journey",
        })
        self.assertEqual(lead["title"], {
            "ar": "عوجا | بيت بغرفتين في الملقا",
            "en": "Ouja | Two-bedroom home in Al Malqa",
        })
        self.assertEqual(lead["request"]["place_id"], "kafd")
        self.assertNotIn("place", lead["request"])
        self.assertEqual(lead["quote"]["deposit"]["amount_sar"], 2000)
        self.assertEqual(
            [(row["event"], row.get("listing_id"), row.get("rank")) for row in lead["journey"]],
            [
                ("entry_route_choice", None, None),
                ("matcher_completion", None, None),
                ("result_impression", "1001", 1),
                ("result_impression", "1002", 2),
                ("listing_view", "1001", None),
                ("whatsapp_click", "1001", None),
            ],
        )
        serialized = json.dumps(result, ensure_ascii=False).lower()
        for forbidden in (
            "session_id", "0500000000", "whatsapp_number", "whatsapp_url",
            "message", "raw_context", "context\"",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_lookup_journey_stops_at_this_lead_conversion(self):
        self.analytics.record(
            {
                "event": "listing_view",
                "session_id": self.session,
                "context": {"listing_id": "1002"},
            },
            session_secret=SECRET,
            allowed_place_ids=("kafd",),
            now=NOW + dt.timedelta(minutes=10),
        )

        detail = self.app.ops.lead({"lead_reference": self.lead["reference"]})["lead"]

        listing_views = [
            row.get("listing_id") for row in detail["journey"]
            if row["event"] == "listing_view"
        ]
        self.assertEqual(listing_views, ["1001"])

    def test_general_help_and_removed_listing_are_described_honestly(self):
        general = self.leads.create_general(
            self.session,
            saved_request(),
            approved_places=PLACES,
            now=NOW + dt.timedelta(minutes=31),
        )
        general_detail = self.app.ops.lead({"lead_reference": general["reference"]})["lead"]
        self.assertIsNone(general_detail["listing_id"])
        self.assertIsNone(general_detail["title"])
        self.assertEqual(general_detail["quote"], {})

        self.refresh(self.second)
        removed = self.app.ops.lead({"lead_reference": self.lead["reference"]})["lead"]
        self.assertEqual(removed["listing_id"], "1001")
        self.assertIsNone(removed["title"])

    def test_funnel_maps_approved_place_labels_but_keeps_the_id(self):
        funnel = self.app.ops.funnel()
        self.assertEqual(funnel["requested_places"], [{
            "place_id": "kafd",
            "label_ar": "مركز الملك عبدالله المالي",
            "label_en": "King Abdullah Financial District",
            "count": 1,
        }])

    def test_first_staff_action_marks_one_response_and_actions_are_append_only(self):
        first = self.app.ops.action({
            "lead_reference": self.lead["reference"],
            "action": "confirm_request",
        })
        second = self.app.ops.action({
            "lead_reference": self.lead["reference"],
            "action": "request_information",
            "reason": "dates",
        })

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(len(self.leads.actions_for(self.lead["reference"])), 2)
        lifecycle = [
            row["event"] for row in self.analytics.events()
            if row["lead_reference"] == self.lead["reference"]
        ]
        self.assertEqual(lifecycle.count("team_response"), 1)
        detail = self.app.ops.lead({"lead_reference": self.lead["reference"]})["lead"]
        self.assertEqual([row["action"] for row in detail["actions"]], [
            "confirm_request", "request_information",
        ])

    def test_prepared_alternative_is_verified_repriced_and_never_sent_or_persisted_as_text(self):
        with mock.patch("socket.create_connection", side_effect=AssertionError("network reached")) as network:
            result = self.app.ops.action({
                "lead_reference": self.lead["reference"],
                "action": "prepare_alternative",
                "reason": "lower_price",
                "alternative_listing_id": "1002",
            })

        network.assert_not_called()
        self.assertTrue(result["ok"])
        prepared = result["prepared_alternative"]
        self.assertEqual(prepared["listing_id"], "1002")
        self.assertEqual(prepared["title"]["ar"], "عوجا | بيت بديل بغرفة في الملقا")
        self.assertEqual(prepared["quote"]["monthly_rate_sar"], 9000)
        self.assertIn("9,000", prepared["message_en"])
        self.assertIn("٩٬٠٠٠", prepared["message_ar"])
        self.assertNotIn("url", prepared)
        stored = self.leads.actions_for(self.lead["reference"])[0]
        self.assertEqual(stored["quote"]["monthly_rate_sar"], 9000)
        raw = (Path(self.folder.name) / "leads.sqlite3").read_bytes().decode("latin1")
        self.assertNotIn("Alternative one-bedroom", raw)
        self.assertNotIn("prepared alternative", raw.lower())

    def test_alternative_rejects_same_unpublished_stale_unavailable_and_missing_price(self):
        same = self.app.ops.action({
            "lead_reference": self.lead["reference"], "action": "prepare_alternative",
            "reason": "space", "alternative_listing_id": "1001",
        })
        self.assertEqual(same["error"]["code"], "alternative_same_listing")

        missing = self.app.ops.action({
            "lead_reference": self.lead["reference"], "action": "prepare_alternative",
            "reason": "space", "alternative_listing_id": "9999",
        })
        self.assertEqual(missing["error"]["code"], "alternative_not_published")

        expensive_listing = valid_listing(**{
            **self.second,
            "official_prices": {
                "2026-09": {
                    "monthly_rate_sar": 13000,
                    "currency": "SAR",
                    "source": "official_rate",
                    "verified_at": "2026-08-25T09:30:00+03:00",
                }
            },
        })
        self.refresh(self.first, expensive_listing)
        not_lower = self.app.ops.action({
            "lead_reference": self.lead["reference"], "action": "prepare_alternative",
            "reason": "lower_price", "alternative_listing_id": "1002",
        })
        self.assertEqual(not_lower["error"]["code"], "alternative_not_lower_price")

        self.refresh(self.first, self.second)

        self.now = NOW + dt.timedelta(minutes=61)
        stale = self.app.ops.action({
            "lead_reference": self.lead["reference"], "action": "prepare_alternative",
            "reason": "dates", "alternative_listing_id": "1002",
        })
        self.assertEqual(stale["error"]["code"], "alternative_availability_pending")

        self.now = NOW
        unavailable_listing = valid_listing(**{
            **self.second,
            "calendar": {**self.second["calendar"], "blocked_dates": ["2026-09-10"]},
        })
        self.refresh(self.first, unavailable_listing)
        unavailable = self.app.ops.action({
            "lead_reference": self.lead["reference"], "action": "prepare_alternative",
            "reason": "dates", "alternative_listing_id": "1002",
        })
        self.assertEqual(unavailable["error"]["code"], "alternative_unavailable")

        price_gap = valid_listing(**{
            **self.second,
            "official_prices": {
                "2026-10": {
                    "monthly_rate_sar": 9000,
                    "currency": "SAR",
                    "source": "official_rate",
                    "verified_at": "2026-08-25T09:30:00+03:00",
                }
            },
        })
        self.refresh(self.first, price_gap)
        no_price = self.app.ops.action({
            "lead_reference": self.lead["reference"], "action": "prepare_alternative",
            "reason": "lower_price", "alternative_listing_id": "1002",
        })
        self.assertEqual(no_price["error"]["code"], "alternative_price_missing")
        self.assertEqual(self.leads.actions_for(self.lead["reference"]), [])

    def test_lookup_and_action_reject_unknown_fields_and_unknown_reference(self):
        for call in (
            lambda: self.app.ops.lead({"lead_reference": self.lead["reference"], "phone": "0500000000"}),
            lambda: self.app.ops.action({"lead_reference": self.lead["reference"], "action": "confirm_request", "notes": "call them"}),
        ):
            result = call()
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "invalid_request")
        missing = self.app.ops.lead({"lead_reference": "OJM-20260825-MISSING"})
        self.assertEqual(missing["error"]["code"], "lead_not_found")


if __name__ == "__main__":
    unittest.main()
