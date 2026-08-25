import datetime as dt
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from monthly_public.analytics import AnalyticsStore
from monthly_public.contracts import ContractError, issue_anonymous_session
from monthly_public.leads import HandoffValidationError, LeadStore, build_whatsapp_handoff
from monthly_public.pricing import quote_for
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


SECRET = b"lead-tests-session-secret-key-32b"
APPROVED_PLACES = {
    "kafd": {
        "kind": "destination",
        "label_ar": "مركز الملك عبدالله المالي",
        "label_en": "KAFD",
    }
}


class BrokenAnalytics:
    def record_lifecycle(self, *args, **kwargs):
        raise sqlite3.OperationalError("disk unavailable")


class LeadTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "leads.sqlite3"
        self.session = issue_anonymous_session(SECRET)
        self.store = LeadStore(self.path, clock=lambda: NOW, reference_factory=lambda now: "OJM-20260825-ABC123")

    def complete_handoff(self):
        from monthly_public.publication import validate_listing

        listing = validate_listing(valid_listing(), valid_settings(), NOW).listing
        request = {
            "purpose": "family",
            "residents": 2,
            "sleeping": "one_bedroom",
            "move_in": "2026-09-01",
            "duration_months": 2,
            "flexibility": "fixed",
        }
        return listing, request, quote_for(listing, request, NOW)

    def test_reference_is_unique_and_same_request_dedupes_for_thirty_minutes(self):
        request = {"purpose": "work", "move_in": "2026-09-01", "duration_months": 2, "residents": 2}
        quote = {"monthly_rate_sar": 12000, "stay_total_sar": 24000, "currency": "SAR"}
        first = self.store.create(self.session, "1001", request, quote)
        duplicate = self.store.create(self.session, "1001", request, quote, now=NOW + dt.timedelta(minutes=29, seconds=59))
        later_store = LeadStore(self.path, clock=lambda: NOW + dt.timedelta(minutes=31), reference_factory=lambda now: "OJM-20260825-ABC123")
        later = later_store.create(self.session, "1001", request, quote)

        self.assertEqual(first["reference"], duplicate["reference"])
        self.assertNotEqual(first["reference"], later["reference"])
        self.assertEqual(later_store.count(), 2)

    def test_team_response_records_only_an_explicit_discount_request_boolean(self):
        first = self.store.create(
            self.session,
            "1001",
            {"purpose": "work"},
            {"monthly_rate_sar": 12000},
        )
        second = self.store.create(
            self.session,
            "1002",
            {"purpose": "family"},
            {"monthly_rate_sar": 9000},
        )

        requested = self.store.mark_response(
            first["reference"], discount_requested=True
        )
        not_requested = self.store.mark_response(
            second["reference"], discount_requested=False
        )

        self.assertIs(requested["discount_requested"], True)
        self.assertIs(not_requested["discount_requested"], False)
        with self.assertRaises(ValueError):
            self.store.mark_response(first["reference"], discount_requested=1)

    def test_existing_database_migrates_discount_request_as_unknown(self):
        legacy_path = Path(self.folder.name) / "legacy-leads.sqlite3"
        with sqlite3.connect(str(legacy_path)) as connection:
            connection.execute(
                """
                CREATE TABLE monthly_public_leads (
                    reference TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    listing_id TEXT NOT NULL,
                    request_key TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    quote_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    responded_at TEXT,
                    outcome TEXT CHECK (outcome IS NULL OR outcome IN ('booked', 'lost')),
                    outcome_at TEXT,
                    lost_reason TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO monthly_public_leads(
                    reference, session_id, listing_id, request_key,
                    request_json, quote_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "OJM-20260825-LEGACY",
                    self.session,
                    "1001",
                    "legacy-key",
                    '{"purpose":"work"}',
                    '{"monthly_rate_sar":12000}',
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )

        migrated = LeadStore(legacy_path, clock=lambda: NOW)

        with sqlite3.connect(str(legacy_path)) as connection:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(monthly_public_leads)"
                ).fetchall()
            }
        self.assertIn("discount_requested", columns)
        self.assertIsNone(
            migrated.get("OJM-20260825-LEGACY")["discount_requested"]
        )
        updated = migrated.mark_response(
            "OJM-20260825-LEGACY", discount_requested=False
        )
        self.assertIs(updated["discount_requested"], False)

    def test_nested_unapproved_quote_fields_are_not_stored(self):
        lead = self.store.create(
            self.session,
            "1001",
            {"purpose": "work"},
            {
                "monthly_rate_sar": 12000,
                "utilities": {
                    "mode": "variable",
                    "label_ar": "حسب الاستهلاك",
                    "label_en": "By use",
                    "phone": "0500000000",
                    "notes": "private",
                },
                "deposit": {
                    "amount_sar": 2000,
                    "refund_ar": "حسب العقد",
                    "refund_en": "Per contract",
                    "identity": "secret",
                },
            },
        )

        stored = json.dumps(lead, ensure_ascii=False)
        for forbidden in ("0500000000", "private", "secret", "phone", "notes", "identity"):
            self.assertNotIn(forbidden, stored)

    def test_place_is_allowlisted_and_labels_are_server_derived(self):
        request = {
            "purpose": "work",
            "place": {
                "kind": "destination",
                "id": "kafd",
                "label": "Client supplied 0500000000",
            },
        }
        lead = self.store.create(
            self.session,
            "1001",
            request,
            {"monthly_rate_sar": 12000},
            approved_places=APPROVED_PLACES,
        )
        self.assertEqual(
            lead["request"]["place"],
            {
                "kind": "destination",
                "id": "kafd",
                "label_ar": "مركز الملك عبدالله المالي",
                "label_en": "KAFD",
            },
        )
        self.assertNotIn("0500000000", json.dumps(lead, ensure_ascii=False))
        with self.assertRaises(ValueError):
            self.store.create(
                self.session,
                "1002",
                {"purpose": "work", "place": {"kind": "destination", "id": "unknown", "label": "Unknown"}},
                {"monthly_rate_sar": 12000},
                approved_places=APPROVED_PLACES,
            )

    def test_family_request_without_place_remains_allowed(self):
        lead = self.store.create(
            self.session,
            "1001",
            {"purpose": "family"},
            {"monthly_rate_sar": 12000},
            approved_places=APPROVED_PLACES,
        )
        self.assertNotIn("place", lead["request"])

    def test_complete_family_handoff_omits_absent_optional_fields_without_placeholders(self):
        listing, request, quote = self.complete_handoff()
        request.pop("sleeping")
        request.pop("flexibility")

        result = build_whatsapp_handoff(
            self.store,
            valid_settings(),
            self.session,
            listing,
            request,
            quote,
            now=NOW,
        )

        self.assertTrue(result["ok"])
        self.assertNotIn("—", result["message"])
        self.assertNotIn("Sleeping:", result["message"])
        self.assertNotIn("Date flexibility:", result["message"])

    def test_approved_fields_are_type_checked_before_storage(self):
        with self.assertRaises(ValueError):
            self.store.create(
                self.session,
                "1001",
                {"purpose": {"phone": "0500000000"}},
                {"monthly_rate_sar": 12000},
            )
        with self.assertRaises(ValueError):
            self.store.create(
                self.session,
                "1001",
                {"purpose": "work"},
                {"monthly_rate_sar": "0500000000"},
            )
        self.assertEqual(self.store.count(), 0)

    def test_deduped_handoff_uses_the_original_stored_quote(self):
        listing, request, first_quote = self.complete_handoff()
        changed_quote = dict(first_quote)
        changed_quote.update({"monthly_rate_sar": 19000, "stay_total_sar": 38000})
        first = build_whatsapp_handoff(self.store, valid_settings(), self.session, listing, request, first_quote, now=NOW)
        duplicate = build_whatsapp_handoff(self.store, valid_settings(), self.session, listing, request, changed_quote, now=NOW + dt.timedelta(minutes=10))

        self.assertEqual(first["lead_reference"], duplicate["lead_reference"])
        self.assertIn("12,000", duplicate["message"])
        self.assertNotIn("19,000", duplicate["message"])

    def test_handoff_contains_every_approved_field_and_does_not_store_message_or_pii(self):
        listing = valid_listing()
        from monthly_public.publication import validate_listing
        public_listing = validate_listing(listing, valid_settings(), NOW).listing
        request = {
            "purpose": "work",
            "place": {"kind": "destination", "id": "kafd", "label": "KAFD"},
            "residents": 2,
            "sleeping": "one_bedroom",
            "move_in": "2026-09-01",
            "duration_months": 2,
            "flexibility": "fixed",
            "name": "Must not persist",
            "phone": "0500000000",
            "notes": "private",
        }
        quote = quote_for(public_listing, request, NOW)

        result = build_whatsapp_handoff(
            self.store,
            valid_settings(),
            self.session,
            public_listing,
            request,
            quote,
            approved_places=APPROVED_PLACES,
            now=NOW,
        )

        self.assertTrue(result["ok"])
        message = result["message"]
        for value in (
            "1001", "عوجا | بيت بغرفتين في الملقا", "Ouja | Two-bedroom home in Al Malqa",
            "2026-09-01", "2026-11-01", "2", "work", "KAFD", "مركز الملك عبدالله المالي", "12,000", "24,000",
            "internet", "maintenance", "الكهرباء والماء حسب الاستهلاك", result["lead_reference"],
            "availability", "deposit", "contract terms",
            "one_bedroom", "fixed", "2,000", "Bank transfer",
        ):
            self.assertIn(value, message)
        self.assertIn("عادة نرد خلال 30 دقيقة", result["response_window"]["message_ar"])
        self.assertEqual(parse_qs(urlsplit(result["url"]).query)["text"], [message])
        stored = json.dumps(self.store.get(result["lead_reference"]), ensure_ascii=False)
        for forbidden in ("Must not persist", "0500000000", "private", message, "message"):
            self.assertNotIn(forbidden, stored)

    def test_incomplete_handoff_fails_closed_before_creating_a_lead(self):
        complete_listing = {
            "id": "1001",
            "name_ar": "عوجا | الملقا",
            "name_en": "Ouja | Al Malqa",
            "neighborhood_ar": "الملقا",
            "neighborhood_en": "Al Malqa",
        }
        complete_request = {
            "purpose": "family",
            "residents": 2,
            "move_in": "2026-09-01",
            "duration_months": 2,
        }
        complete_quote = {
            "monthly_rate_sar": 12000,
            "stay_total_sar": 24000,
            "currency": "SAR",
            "move_in": "2026-09-01",
            "move_out": "2026-11-01",
            "months": 2,
            "included": ["internet", "maintenance"],
            "utilities": {"mode": "variable", "label_ar": "حسب الاستهلاك", "label_en": "By use"},
            "cleaning": {"mode": "optional", "amount_sar": 300, "label_ar": "اختياري", "label_en": "Optional"},
            "deposit": {"amount_sar": 2000, "refund_ar": "حسب العقد", "refund_en": "Per contract"},
            "payment_methods": [{"ar": "تحويل بنكي", "en": "Bank transfer"}],
            "preliminary_contract": False,
            "preliminary_label_ar": "",
            "preliminary_label_en": "",
        }
        cases = (
            ({**complete_listing, "name_ar": ""}, complete_request, complete_quote),
            (complete_listing, {key: value for key, value in complete_request.items() if key != "residents"}, complete_quote),
            (complete_listing, complete_request, {key: value for key, value in complete_quote.items() if key != "stay_total_sar"}),
            (complete_listing, complete_request, {**complete_quote, "included": ["internet"]}),
            (complete_listing, complete_request, {**complete_quote, "payment_methods": []}),
            (complete_listing, complete_request, {key: value for key, value in complete_quote.items() if key != "preliminary_contract"}),
            (complete_listing, complete_request, {**complete_quote, "months": 3}),
            (complete_listing, complete_request, {**complete_quote, "move_out": "2026-12-01"}),
        )
        for listing, request, quote in cases:
            with self.subTest(listing=listing, request=request, quote=quote):
                with self.assertRaises(HandoffValidationError):
                    build_whatsapp_handoff(
                        self.store,
                        valid_settings(),
                        self.session,
                        listing,
                        request,
                        quote,
                        approved_places=APPROVED_PLACES,
                        now=NOW,
                    )
        self.assertEqual(self.store.count(), 0)

    def test_unsafe_listing_id_is_a_handoff_error_before_store_create(self):
        listing, request, quote = self.complete_handoff()
        listing = dict(listing)
        listing["id"] = "bad/listing id"

        with self.assertRaises(HandoffValidationError) as caught:
            build_whatsapp_handoff(
                self.store,
                valid_settings(),
                self.session,
                listing,
                request,
                quote,
                now=NOW,
            )

        self.assertEqual(caught.exception.code, "listing_incomplete")
        self.assertEqual(self.store.count(), 0)
        with self.assertRaises(ValueError):
            self.store.create(
                self.session,
                "bad/listing id",
                {"purpose": "family"},
                {"monthly_rate_sar": 12000},
            )

    def test_missing_whatsapp_blocks_without_creating_a_lead(self):
        from monthly_public.settings import load_settings
        settings = load_settings({})
        result = build_whatsapp_handoff(
            self.store, settings, self.session, {"id": "1001"}, {"purpose": "work"}, {"monthly_rate_sar": 1}, now=NOW
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "whatsapp_not_configured")
        self.assertEqual(self.store.count(), 0)

    def test_analytics_failure_does_not_block_created_handoff(self):
        listing, request, quote = self.complete_handoff()
        result = build_whatsapp_handoff(self.store, valid_settings(), self.session, listing, request, quote, analytics=BrokenAnalytics(), now=NOW)
        self.assertTrue(result["ok"])
        self.assertFalse(result["analytics_recorded"])
        self.assertEqual(self.store.count(), 1)

    def test_locked_analytics_fails_fast_without_delaying_handoff(self):
        analytics_path = Path(self.folder.name) / "analytics.sqlite3"
        analytics = AnalyticsStore(analytics_path, clock=lambda: NOW)
        locker = sqlite3.connect(str(analytics_path))
        locker.execute("BEGIN EXCLUSIVE")
        try:
            started = time.monotonic()
            listing, request, quote = self.complete_handoff()
            result = build_whatsapp_handoff(
                self.store,
                valid_settings(),
                self.session,
                listing,
                request,
                quote,
                analytics=analytics,
                now=NOW,
            )
            elapsed = time.monotonic() - started
        finally:
            locker.rollback()
            locker.close()
        self.assertTrue(result["ok"])
        self.assertFalse(result["analytics_recorded"])
        self.assertLess(elapsed, 1.0)

    def test_response_and_outcome_lifecycle_is_valid_and_idempotent(self):
        lead = self.store.create(self.session, "1001", {"purpose": "work"}, {"monthly_rate_sar": 1})
        responded = self.store.mark_response(lead["reference"], now=NOW + dt.timedelta(minutes=7))
        again = self.store.mark_response(lead["reference"], now=NOW + dt.timedelta(minutes=9))
        self.assertEqual(responded["responded_at"], again["responded_at"])
        booked = self.store.set_outcome(
            {"lead_reference": lead["reference"], "outcome": "booked"},
            now=NOW + dt.timedelta(minutes=8),
        )
        self.assertEqual(booked["outcome"], "booked")
        self.assertEqual(self.store.set_outcome({"lead_reference": lead["reference"], "outcome": "booked"})["outcome"], "booked")
        with self.assertRaises(ValueError):
            self.store.set_outcome({"lead_reference": lead["reference"], "outcome": "lost", "lost_reason": "price"})

    def test_outcome_requires_response_and_controlled_reason(self):
        lead = self.store.create(self.session, "1001", {"purpose": "work"}, {"monthly_rate_sar": 1})
        with self.assertRaises(ValueError):
            self.store.set_outcome({"lead_reference": lead["reference"], "outcome": "booked"})
        self.store.mark_response(lead["reference"])
        with self.assertRaises(ContractError):
            self.store.set_outcome({"lead_reference": lead["reference"], "outcome": "lost", "lost_reason": "customer said too expensive"})

    def test_lifecycle_timestamps_cannot_move_backwards(self):
        lead = self.store.create(self.session, "1001", {"purpose": "work"}, {"monthly_rate_sar": 1})
        with self.assertRaises(ValueError):
            self.store.mark_response(lead["reference"], now=NOW - dt.timedelta(seconds=1))
        self.store.mark_response(lead["reference"], now=NOW + dt.timedelta(minutes=5))
        with self.assertRaises(ValueError):
            self.store.set_outcome(
                {"lead_reference": lead["reference"], "outcome": "booked"},
                now=NOW + dt.timedelta(minutes=4),
            )


if __name__ == "__main__":
    unittest.main()
