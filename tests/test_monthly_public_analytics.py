import datetime as dt
import tempfile
import unittest
from pathlib import Path

from monthly_public.analytics import AnalyticsStore, EventStore, funnel_summary
from monthly_public.contracts import ContractError, issue_anonymous_session
from monthly_public.leads import LeadStore


NOW = dt.datetime(2026, 8, 25, 10, 0, tzinfo=dt.timezone(dt.timedelta(hours=3)))
SECRET = b"analytics-test-session-secret-32b"


class AnalyticsStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "analytics.sqlite3"
        self.session = issue_anonymous_session(SECRET)
        self.store = AnalyticsStore(self.path, clock=lambda: NOW)

    def test_event_store_is_the_stable_public_name(self):
        self.assertIs(EventStore, AnalyticsStore)

    def test_public_events_use_contract_validation_and_drop_pii(self):
        event = self.store.record(
            {
                "event": "listing_view",
                "session_id": self.session,
                "context": {
                    "listing_id": "1001",
                    "place_id": "kafd",
                    "phone": "0500000000",
                    "utm_source": "paid",
                },
            },
            session_secret=SECRET,
            allowed_place_ids=("kafd",),
        )

        self.assertEqual(event["context"], {"listing_id": "1001", "place_id": "kafd"})
        self.assertNotIn("0500000000", self.path.read_bytes().decode("latin1"))
        with self.assertRaises(ContractError):
            self.store.record(
                {"event": "booked", "session_id": self.session},
                session_secret=SECRET,
            )

    def test_every_public_funnel_event_can_be_recorded(self):
        names = (
            "landing_view", "entry_route_choice", "matcher_start", "matcher_answer",
            "matcher_completion", "results_view", "result_impression", "listing_view",
            "whatsapp_click",
        )
        for name in names:
            with self.subTest(name=name):
                self.store.record(
                    {"event": name, "session_id": self.session},
                    session_secret=SECRET,
                )
        self.assertEqual([event["event"] for event in self.store.events()], list(names))

    def test_funnel_links_anonymous_session_to_lead_and_counts_outcomes(self):
        for name in ("landing_view", "matcher_start", "matcher_completion", "results_view", "listing_view", "whatsapp_click"):
            self.store.record(
                {"event": name, "session_id": self.session, "context": {"listing_id": "1001"}},
                session_secret=SECRET,
            )
        leads = LeadStore(Path(self.folder.name) / "leads.sqlite3", clock=lambda: NOW)
        lead = leads.create(
            self.session,
            "1001",
            {"purpose": "work", "move_in": "2026-09-01", "duration_months": 2, "residents": 2},
            {"monthly_rate_sar": 12000, "stay_total_sar": 24000, "currency": "SAR"},
        )
        self.store.record_lifecycle("lead_created", self.session, lead["reference"])
        leads.mark_response(lead["reference"], now=NOW + dt.timedelta(minutes=12))
        self.store.record_lifecycle("team_response", self.session, lead["reference"], now=NOW + dt.timedelta(minutes=12))
        leads.set_outcome(
            {"lead_reference": lead["reference"], "outcome": "booked"},
            now=NOW + dt.timedelta(minutes=13),
        )
        self.store.record_lifecycle(
            "booked", self.session, lead["reference"], now=NOW + dt.timedelta(minutes=13)
        )

        summary = funnel_summary(self.store, leads)

        self.assertEqual(summary["stages"]["landing_view"], 1)
        self.assertEqual(summary["stages"]["lead_created"], 1)
        self.assertEqual(summary["leads"]["responded"], 1)
        self.assertEqual(summary["leads"]["booked"], 1)
        self.assertEqual(summary["leads"]["lost"], 0)
        self.assertEqual(summary["response_time_minutes"]["average"], 12.0)
        self.assertEqual(summary["sessions"][self.session]["lead_references"], [lead["reference"]])
        self.assertNotIn("message", str(summary).lower())

    def test_funnel_reports_only_controlled_lost_reasons(self):
        leads = LeadStore(Path(self.folder.name) / "leads.sqlite3", clock=lambda: NOW)
        lead = leads.create(self.session, "1001", {"purpose": "work"}, {"monthly_rate_sar": 1})
        leads.mark_response(lead["reference"])
        leads.set_outcome({"lead_reference": lead["reference"], "outcome": "lost", "lost_reason": "price"})

        summary = funnel_summary(self.store, leads)

        self.assertEqual(summary["lost_reasons"]["price"], 1)
        self.assertEqual(sum(summary["lost_reasons"].values()), 1)

    def test_funnel_reports_demand_dimensions_and_conversion_rates_without_discount_pii(self):
        second_session = issue_anonymous_session(SECRET)
        places = {
            "kafd": {
                "kind": "destination",
                "label_ar": "مركز الملك عبدالله المالي",
                "label_en": "King Abdullah Financial District",
            }
        }
        for session, context in (
            (
                self.session,
                {
                    "purpose": "work",
                    "place_id": "kafd",
                    "move_in": "2026-09-01",
                    "duration_months": 2,
                    "discount_requested": True,
                },
            ),
            (
                second_session,
                {
                    "purpose": "family",
                    "move_in": "2026-09-01",
                    "duration_months": 1,
                },
            ),
        ):
            self.store.record(
                {"event": "matcher_completion", "session_id": session, "context": context},
                session_secret=SECRET,
                allowed_place_ids=places,
            )
        leads = LeadStore(Path(self.folder.name) / "leads.sqlite3", clock=lambda: NOW)
        work = leads.create(
            self.session,
            "1001",
            {
                "purpose": "work",
                "place": {"kind": "destination", "id": "kafd"},
                "move_in": "2026-09-01",
                "duration_months": 2,
                "residents": 2,
            },
            {"monthly_rate_sar": 12000},
            approved_places=places,
        )
        leads.create(
            second_session,
            "1002",
            {
                "purpose": "family",
                "move_in": "2026-09-01",
                "duration_months": 1,
                "residents": 3,
            },
            {"monthly_rate_sar": 9000},
        )
        leads.mark_response(work["reference"], now=NOW + dt.timedelta(minutes=10))
        leads.set_outcome(
            {"lead_reference": work["reference"], "outcome": "booked"},
            now=NOW + dt.timedelta(minutes=11),
        )

        summary = funnel_summary(self.store, leads)

        self.assertNotIn("discount_requested", self.store.events()[0]["context"])
        self.assertEqual(
            summary["common_purposes"],
            [{"purpose": "family", "count": 1}, {"purpose": "work", "count": 1}],
        )
        self.assertEqual(
            summary["requested_places"], [{"place_id": "kafd", "count": 1}]
        )
        self.assertEqual(
            summary["duration_bands"],
            {"1_month": 1, "2_3_months": 1, "4_6_months": 0},
        )
        self.assertEqual(summary["conversion_rates"]["matcher_to_lead"], 1.0)
        self.assertEqual(summary["conversion_rates"]["lead_to_response"], 0.5)
        self.assertEqual(summary["conversion_rates"]["lead_to_booking"], 0.5)
        self.assertEqual(
            summary["discount_request_rate"],
            {
                "status": "not_tracked",
                "count": 0,
                "numerator": 0,
                "denominator": 0,
                "rate": None,
            },
        )
        self.assertNotIn("discount", repr(summary["sessions"]).lower())

    def test_discount_request_rate_uses_only_staff_classified_leads(self):
        second_session = issue_anonymous_session(SECRET)
        leads = LeadStore(Path(self.folder.name) / "leads.sqlite3", clock=lambda: NOW)
        requested = leads.create(
            self.session,
            "1001",
            {"purpose": "work"},
            {"monthly_rate_sar": 12000},
        )
        not_requested = leads.create(
            second_session,
            "1002",
            {"purpose": "family"},
            {"monthly_rate_sar": 9000},
        )
        leads.mark_response(requested["reference"], discount_requested=True)
        leads.mark_response(not_requested["reference"], discount_requested=False)

        summary = funnel_summary(self.store, leads)

        self.assertEqual(
            summary["discount_request_rate"],
            {
                "status": "tracked",
                "count": 1,
                "numerator": 1,
                "denominator": 2,
                "rate": 0.5,
            },
        )
        self.assertNotIn("discount", repr(summary["sessions"]).lower())

    def test_session_to_lead_link_survives_a_missing_lifecycle_event(self):
        self.store.record(
            {"event": "landing_view", "session_id": self.session},
            session_secret=SECRET,
        )
        leads = LeadStore(Path(self.folder.name) / "leads.sqlite3", clock=lambda: NOW)
        lead = leads.create(self.session, "1001", {"purpose": "work"}, {"monthly_rate_sar": 1})

        summary = funnel_summary(self.store, leads)

        self.assertEqual(summary["sessions"][self.session]["lead_references"], [lead["reference"]])

    def test_trusted_lifecycle_enforces_order_and_returns_persisted_retry_time(self):
        reference = "OJM-20260825-ABC123"
        with self.assertRaises(ValueError):
            self.store.record_lifecycle("team_response", self.session, reference)
        created = self.store.record_lifecycle("lead_created", self.session, reference, now=NOW)
        retried = self.store.record_lifecycle(
            "lead_created", self.session, reference, now=NOW + dt.timedelta(minutes=2)
        )
        self.assertEqual(created["occurred_at"], retried["occurred_at"])
        with self.assertRaises(ValueError):
            self.store.record_lifecycle(
                "team_response", self.session, reference, now=NOW - dt.timedelta(seconds=1)
            )
        self.store.record_lifecycle(
            "team_response", self.session, reference, now=NOW + dt.timedelta(minutes=3)
        )
        self.store.record_lifecycle(
            "lost", self.session, reference, context={"lost_reason": "price"}, now=NOW + dt.timedelta(minutes=4)
        )
        with self.assertRaises(ValueError):
            self.store.record_lifecycle(
                "booked", self.session, reference, now=NOW + dt.timedelta(minutes=5)
            )

    def test_lead_creation_atomically_records_one_durable_whatsapp_click(self):
        reference = "OJM-20260825-ABC123"

        first = self.store.record_lead_creation(
            self.session, reference, listing_id="1001", now=NOW
        )
        retried = self.store.record_lead_creation(
            self.session,
            reference,
            listing_id="1001",
            now=NOW + dt.timedelta(minutes=2),
        )

        self.assertEqual(first, retried)
        linked = [
            event for event in self.store.events()
            if event["lead_reference"] == reference
        ]
        self.assertEqual(
            [event["event"] for event in linked],
            ["whatsapp_click", "lead_created"],
        )
        self.assertTrue(all(event["trusted"] for event in linked))
        self.assertEqual(linked[0]["context"], {"listing_id": "1001"})
        self.assertEqual(linked[1]["context"], {})

    def test_lead_journeys_use_explicit_correlation_when_tabs_interleave(self):
        first_journey = "journey_AAAAAAAAAAAAAAAAAAAAAA"
        second_journey = "journey_BBBBBBBBBBBBBBBBBBBBBB"
        for journey_id, listing_id in (
            (first_journey, "1001"),
            (second_journey, "1002"),
        ):
            self.store.record(
                {
                    "event": "entry_route_choice",
                    "session_id": self.session,
                    "context": {"entry_route": "guided", "journey_id": journey_id},
                },
                session_secret=SECRET,
                now=NOW,
            )
            self.store.record(
                {
                    "event": "listing_view",
                    "session_id": self.session,
                    "context": {"listing_id": listing_id, "journey_id": journey_id},
                },
                session_secret=SECRET,
                now=NOW,
            )

        self.store.record_lead_creation(
            self.session,
            "OJM-20260825-FIRST",
            listing_id="1001",
            journey_id=first_journey,
            now=NOW,
        )
        self.store.record_lead_creation(
            self.session,
            "OJM-20260825-SECOND",
            listing_id="1002",
            journey_id=second_journey,
            now=NOW,
        )

        first = self.store.lead_journey(self.session, "OJM-20260825-FIRST")
        second = self.store.lead_journey(self.session, "OJM-20260825-SECOND")
        self.assertEqual(
            [row.get("listing_id") for row in first if row["event"] == "listing_view"],
            ["1001"],
        )
        self.assertEqual(
            [row.get("listing_id") for row in second if row["event"] == "listing_view"],
            ["1002"],
        )
        self.assertNotIn("journey_id", repr(first))
        self.assertNotIn("journey_id", repr(second))

    def test_two_leads_in_one_journey_keep_their_trusted_conversion_separate(self):
        journey_id = "journey_AAAAAAAAAAAAAAAAAAAAAA"
        first_reference = "OJM-20260825-FIRST"
        second_reference = "OJM-20260825-SECOND"
        self.store.record(
            {
                "event": "listing_view",
                "session_id": self.session,
                "context": {"listing_id": "1001", "journey_id": journey_id},
            },
            session_secret=SECRET,
            now=NOW,
        )
        self.store.record_lead_creation(
            self.session,
            first_reference,
            listing_id="1001",
            journey_id=journey_id,
            now=NOW,
        )
        self.store.record(
            {
                "event": "listing_view",
                "session_id": self.session,
                "context": {"listing_id": "1002", "journey_id": journey_id},
            },
            session_secret=SECRET,
            now=NOW,
        )
        self.store.record_lead_creation(
            self.session,
            second_reference,
            listing_id="1002",
            journey_id=journey_id,
            now=NOW,
        )

        second = self.store.lead_journey(self.session, second_reference)

        clicks = [row.get("listing_id") for row in second if row["event"] == "whatsapp_click"]
        self.assertEqual(clicks, ["1002"])

    def test_lost_requires_controlled_reason_and_other_lifecycle_rejects_it(self):
        reference = "OJM-20260825-ABC123"
        with self.assertRaises(ValueError):
            self.store.record_lifecycle(
                "lead_created",
                self.session,
                reference,
                context={"lost_reason": "price"},
                now=NOW,
            )
        self.store.record_lifecycle("lead_created", self.session, reference, now=NOW)
        with self.assertRaises(ValueError):
            self.store.record_lifecycle(
                "team_response",
                self.session,
                reference,
                context={"lost_reason": "price"},
                now=NOW + dt.timedelta(minutes=1),
            )
        self.store.record_lifecycle(
            "team_response", self.session, reference, now=NOW + dt.timedelta(minutes=1)
        )
        for context in (None, {}, {"lost_reason": "free form"}):
            with self.subTest(context=context):
                with self.assertRaises(ValueError):
                    self.store.record_lifecycle(
                        "lost",
                        self.session,
                        reference,
                        context=context,
                        now=NOW + dt.timedelta(minutes=2),
                    )


if __name__ == "__main__":
    unittest.main()
