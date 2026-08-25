import datetime as dt
import os
import sqlite3
import tempfile
import unittest


from monthly_public.catalog_store import CatalogStore, RevisionConflict


NOW = dt.datetime(2026, 8, 25, 9, 30, tzinfo=dt.timezone.utc)


class CatalogStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "monthly_catalog.sqlite3")
        self.store = CatalogStore(self.path, clock=lambda: NOW)

    def test_empty_records_have_zero_revisions(self):
        profile = self.store.profile("101")
        self.assertEqual(profile["listing_id"], "101")
        self.assertEqual(profile["draft_revision"], 0)
        self.assertEqual(profile["approved_revision"], 0)
        self.assertIsNone(profile["draft"])
        self.assertIsNone(profile["approved"])

        settings = self.store.settings()
        self.assertEqual(settings["draft_revision"], 0)
        self.assertIsNone(settings["approved"])

    def test_draft_does_not_change_approved_profile(self):
        saved = self.store.save_profile_draft(
            "101", {"name_ar": "شقة عوجا"}, expected_revision=0, actor="ops"
        )

        self.assertEqual(saved["draft_revision"], 1)
        self.assertEqual(saved["draft"], {"name_ar": "شقة عوجا"})
        self.assertIsNone(saved["approved"])

    def test_profile_revisions_are_monotonic_and_reject_stale_writes(self):
        self.store.save_profile_draft("101", {"name_ar": "أ"}, 0, "ops-a")
        second = self.store.save_profile_draft(
            "101", {"name_ar": "ب"}, 1, "ops-b"
        )
        self.assertEqual(second["draft_revision"], 2)

        with self.assertRaises(RevisionConflict):
            self.store.save_profile_draft("101", {"name_ar": "ج"}, 1, "ops-c")

    def test_approval_copies_only_the_requested_current_draft(self):
        self.store.save_profile_draft("101", {"name_ar": "أ"}, 0, "ops-a")
        approved = self.store.approve_profile("101", revision=1, actor="manager")
        self.assertEqual(approved["approved"], {"name_ar": "أ"})
        self.assertEqual(approved["approved_revision"], 1)
        self.assertEqual(approved["approved_by"], "manager")

        self.store.save_profile_draft("101", {"name_ar": "ب"}, 1, "ops-a")
        current = self.store.profile("101")
        self.assertEqual(current["draft"], {"name_ar": "ب"})
        self.assertEqual(current["approved"], {"name_ar": "أ"})

        with self.assertRaises(RevisionConflict):
            self.store.approve_profile("101", revision=1, actor="manager")

    def test_settings_and_places_use_the_same_revision_guards(self):
        settings = self.store.save_settings_draft(
            {"whatsapp_number": "966500000000"}, 0, "ops"
        )
        approved_settings = self.store.approve_settings(
            settings["draft_revision"], "manager"
        )
        self.assertEqual(
            approved_settings["approved"], {"whatsapp_number": "966500000000"}
        )

        place = self.store.save_place_draft(
            "king-faisal-hospital",
            {"label_ar": "مستشفى الملك فيصل"},
            0,
            "ops",
        )
        approved_place = self.store.approve_place(
            "king-faisal-hospital", place["draft_revision"], True, "manager"
        )
        self.assertTrue(approved_place["active"])
        self.assertIn("king-faisal-hospital", self.store.places())

        inactive = self.store.approve_place(
            "king-faisal-hospital", place["draft_revision"], False, "manager"
        )
        self.assertFalse(inactive["active"])

    def test_approved_profiles_are_isolated_copies(self):
        self.store.save_profile_draft("101", {"facts": {"parking": True}}, 0, "ops")
        self.store.approve_profile("101", 1, "manager")

        values = self.store.approved_profiles()
        values["101"]["facts"]["parking"] = False

        self.assertTrue(self.store.approved_profiles()["101"]["facts"]["parking"])

    def test_audit_records_field_names_without_values(self):
        self.store.save_profile_draft(
            "101", {"name_ar": "سري", "nested": {"field": "value"}}, 0, "ops"
        )
        rows = self.store.audit("listing:101")
        self.assertEqual(rows[0]["action"], "profile_draft_saved")
        self.assertEqual(rows[0]["actor"], "ops")
        self.assertEqual(rows[0]["changed_fields"], ["name_ar", "nested"])
        self.assertNotIn("سري", repr(rows))
        self.assertNotIn("value", repr(rows))

    def test_database_survives_restart(self):
        self.store.save_profile_draft("101", {"name_ar": "أ"}, 0, "ops")
        self.store.approve_profile("101", 1, "manager")

        reopened = CatalogStore(self.path, clock=lambda: NOW)
        self.assertEqual(reopened.profile("101")["approved"], {"name_ar": "أ"})

    def test_sqlite_uses_delete_journal_mode_and_write_probe_rolls_back(self):
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(
                connection.execute("PRAGMA journal_mode").fetchone()[0], "delete"
            )

        before = len(self.store.audit())
        probe = self.store.probe()
        self.assertTrue(probe["ok"])
        self.assertEqual(probe["journal_mode"], "delete")
        self.assertEqual(len(self.store.audit()), before)

    def test_invalid_ids_and_actor_are_rejected_before_write(self):
        for listing_id in ("", "../101", "a b", "x" * 81):
            with self.subTest(listing_id=listing_id):
                with self.assertRaises(ValueError):
                    self.store.save_profile_draft(listing_id, {}, 0, "ops")
        with self.assertRaises(ValueError):
            self.store.save_place_draft("bad place", {}, 0, "ops")
        with self.assertRaises(ValueError):
            self.store.save_profile_draft("101", {}, 0, "")

    def test_seed_approved_places_once_is_atomic_and_idempotent(self):
        places = [
            {
                "id": "biz_kafd",
                "kind": "destination",
                "label_ar": "مركز الملك عبدالله المالي",
                "label_en": "King Abdullah Financial District",
                "purposes": ["work"],
                "lat": 24.7672,
                "lng": 46.6431,
                "source": "priority_places_2026_08_25",
                "verified": True,
            },
            {
                "id": "health_kfshrc",
                "kind": "destination",
                "label_ar": "مستشفى الملك فيصل التخصصي",
                "label_en": "King Faisal Specialist Hospital",
                "purposes": ["treatment", "family"],
                "lat": 24.6717,
                "lng": 46.6758,
                "source": "priority_places_2026_08_25",
                "verified": True,
            },
        ]

        seeded = self.store.seed_approved_places_once(
            "priority_places_2026_08_25_v1", places, "system:priority_places"
        )
        self.assertEqual(seeded["imported"], 2)
        self.assertEqual(seeded["skipped_existing"], 0)
        self.assertFalse(seeded["already_applied"])
        rows = self.store.places()
        self.assertEqual(set(rows), {"biz_kafd", "health_kfshrc"})
        self.assertTrue(all(row["active"] for row in rows.values()))
        self.assertTrue(
            all(row["draft"] == row["approved"] for row in rows.values())
        )
        self.assertTrue(
            all(row["approved_revision"] == 1 for row in rows.values())
        )

        again = self.store.seed_approved_places_once(
            "priority_places_2026_08_25_v1", places, "system:priority_places"
        )
        self.assertTrue(again["already_applied"])
        self.assertEqual(again["imported"], 2)
        self.assertEqual(len(self.store.audit()), 2)

        reopened = CatalogStore(self.path, clock=lambda: NOW)
        after_restart = reopened.seed_approved_places_once(
            "priority_places_2026_08_25_v1", places, "system:priority_places"
        )
        self.assertTrue(after_restart["already_applied"])
        self.assertEqual(len(reopened.audit()), 2)

    def test_seed_approved_places_preserves_existing_staff_record(self):
        existing = {
            "label_ar": "اسم اعتمده الفريق",
            "label_en": "Staff-approved name",
        }
        self.store.save_place_draft("biz_kafd", existing, 0, "ops")
        self.store.approve_place("biz_kafd", 1, True, "manager")

        seeded = self.store.seed_approved_places_once(
            "priority_places_2026_08_25_v1",
            [
                {
                    "id": "biz_kafd",
                    "label_ar": "اسم الملف",
                    "label_en": "Workbook name",
                },
                {
                    "id": "events_ricec",
                    "label_ar": "واجهة الرياض للمعارض",
                    "label_en": "Riyadh Front Exhibition Center",
                },
            ],
            "system:priority_places",
        )

        self.assertEqual(seeded["imported"], 1)
        self.assertEqual(seeded["skipped_existing"], 1)
        self.assertEqual(self.store.places()["biz_kafd"]["approved"], existing)

    def test_seed_approved_places_rolls_back_invalid_batch(self):
        with self.assertRaises(ValueError):
            self.store.seed_approved_places_once(
                "priority_places_2026_08_25_v1",
                [
                    {"id": "biz_kafd", "label_ar": "كافد"},
                    {"id": "bad place", "label_ar": "غير صالح"},
                ],
                "system:priority_places",
            )
        self.assertEqual(self.store.places(), {})

        corrected = self.store.seed_approved_places_once(
            "priority_places_2026_08_25_v1",
            [{"id": "biz_kafd", "label_ar": "كافد"}],
            "system:priority_places",
        )
        self.assertEqual(corrected["imported"], 1)
        self.assertFalse(corrected["already_applied"])


if __name__ == "__main__":
    unittest.main()
