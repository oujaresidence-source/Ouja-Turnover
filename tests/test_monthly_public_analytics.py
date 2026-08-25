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


if __name__ == "__main__":
    unittest.main()
