import datetime as dt
import tempfile
import unittest
from pathlib import Path


from monthly_public.showcase_store import (
    DuplicateShowcaseSlug,
    ImmutableShowcaseSlug,
    RevisionConflict,
    ShowcaseStore,
)
from tests.test_monthly_showcase_contracts import valid_group


NOW = dt.datetime(2026, 8, 27, 12, 0, tzinfo=dt.timezone.utc)


class ShowcaseStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "showcases.sqlite3"
        self.store = ShowcaseStore(self.path, clock=lambda: NOW)

    def tearDown(self):
        self.tmp.cleanup()

    def _approve(self, group_id, value):
        draft = self.store.save_draft(group_id, value, 0, "faisal")
        return self.store.approve(
            group_id,
            draft["draft_revision"],
            "faisal",
        )

    def test_draft_approval_and_toggle_preserve_price_and_members(self):
        group = valid_group(listing_ids=["101", "102"])
        draft = self.store.save_draft("showcase_a1", group, 0, "faisal")
        approved = self.store.approve(
            "showcase_a1",
            draft["draft_revision"],
            "faisal",
        )
        toggled = self.store.set_price_enabled(
            "showcase_a1",
            False,
            approved["approved_revision"],
            "faisal",
        )

        self.assertFalse(toggled["approved"]["fixed_price_enabled"])
        self.assertEqual(toggled["approved"]["fixed_monthly_rate_sar"], 12500)
        self.assertEqual(toggled["approved"]["listing_ids"], group["listing_ids"])
        self.assertGreater(
            toggled["approved_revision"],
            approved["approved_revision"],
        )

    def test_first_approved_slug_is_immutable_and_unique(self):
        self._approve("showcase_a1", valid_group(slug="one-building"))

        with self.assertRaises(ImmutableShowcaseSlug):
            self.store.save_draft(
                "showcase_a1",
                valid_group(slug="renamed"),
                1,
                "faisal",
            )
        with self.assertRaises(DuplicateShowcaseSlug):
            self._approve("showcase_b2", valid_group(slug="one-building"))

    def test_store_has_no_delete_method_and_audit_is_append_only(self):
        approved = self._approve("showcase_a1", valid_group())
        self.store.set_price_enabled(
            "showcase_a1",
            False,
            approved["approved_revision"],
            "faisal",
        )

        self.assertFalse(hasattr(self.store, "delete"))
        self.assertEqual(
            [row["action"] for row in self.store.audit("showcase_a1")],
            ["price_disabled", "approved", "draft_saved"],
        )

    def test_stale_edits_and_price_toggles_are_rejected(self):
        draft = self.store.save_draft(
            "showcase_a1",
            valid_group(),
            0,
            "faisal",
        )
        with self.assertRaises(RevisionConflict):
            self.store.save_draft(
                "showcase_a1",
                valid_group(description_en="Changed"),
                0,
                "faisal",
            )
        approved = self.store.approve(
            "showcase_a1",
            draft["draft_revision"],
            "faisal",
        )
        with self.assertRaises(RevisionConflict):
            self.store.set_price_enabled("showcase_a1", False, 0, "faisal")
        self.assertTrue(approved["approved"]["fixed_price_enabled"])

    def test_records_survive_restart_and_lookup_by_approved_slug(self):
        expected = self._approve(
            "showcase_a1",
            valid_group(slug="one-building", listing_ids=["101", "102"]),
        )

        restarted = ShowcaseStore(self.path, clock=lambda: NOW)

        self.assertEqual(restarted.record("showcase_a1"), expected)
        self.assertEqual(
            restarted.by_approved_slug("one-building")["group_id"],
            "showcase_a1",
        )
        self.assertEqual(len(restarted.list_records()), 1)

    def test_record_for_unknown_group_is_non_destructive_empty_state(self):
        self.assertEqual(
            self.store.record("showcase_missing"),
            {
                "group_id": "showcase_missing",
                "draft": None,
                "approved": None,
                "draft_revision": 0,
                "approved_revision": 0,
                "draft_updated_at": None,
                "draft_updated_by": None,
                "approved_at": None,
                "approved_by": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
