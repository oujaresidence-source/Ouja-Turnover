import copy
import json
import tempfile
import unittest
from pathlib import Path

from monthly_public.snapshot import SnapshotStore, build_generation
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


def source_with(listings, **overrides):
    source = {
        "refresh_ok": True,
        "catalog_complete": True,
        "listings": listings,
        "source_timestamps": {
            "catalog": "2026-08-25T09:45:00+03:00",
            "calendar": "2026-08-25T09:40:00+03:00",
            "pricing": "2026-08-25T09:30:00+03:00",
        },
    }
    source.update(overrides)
    return source


class GenerationTests(unittest.TestCase):
    def test_generation_reconciles_57_catalog_and_56_exact_calendars(self):
        listings = []
        for number in range(57):
            listing = valid_listing(
                id=1000 + number,
                slug="ouja-%d" % (1000 + number),
                name_ar="عوجا | بيت رقم %d بغرفتين" % (number + 1),
                name_en="Ouja | Home %d with 2BR" % (number + 1),
            )
            if number == 56:
                listing["calendar"] = None
            listings.append(listing)

        generation = build_generation(source_with(listings), valid_settings(), NOW)

        self.assertEqual(generation.counts["received"], 57)
        self.assertEqual(generation.counts["published"], 57)
        self.assertEqual(generation.counts["calendar_covered"], 56)
        self.assertEqual(generation.missing_calendar_ids, ("1056",))

    def test_blocked_homes_remain_available_for_staff_preview_only(self):
        generation = build_generation(
            source_with(
                [
                    valid_listing(id=1001),
                    valid_listing(id=1002, licence=None),
                    valid_listing(id=1003, official_prices={}),
                ]
            ),
            valid_settings(),
            NOW,
        )
        self.assertEqual(generation.counts["published"], 1)
        self.assertEqual(generation.counts["blocked"], 2)
        self.assertEqual(generation.counts["calendar_covered"], 3)
        self.assertEqual(set(generation.blocked_ids), {"1002", "1003"})
        self.assertEqual(generation.missing_price_ids, ("1003",))

    def test_invalid_calendar_is_not_counted_as_covered(self):
        invalid = valid_listing(id=1001)
        invalid["calendar"]["from"] = "not-a-date"

        generation = build_generation(
            source_with([invalid]), valid_settings(), NOW
        )

        self.assertEqual(generation.counts["calendar_covered"], 0)
        self.assertEqual(generation.stale_calendar_ids, ("1001",))

    def test_duplicate_or_empty_catalog_is_a_generation_error(self):
        with self.assertRaises(ValueError):
            build_generation(source_with([]), valid_settings(), NOW)
        with self.assertRaises(ValueError):
            build_generation(
                source_with([valid_listing(id=1001), valid_listing(id=1001)]),
                valid_settings(),
                NOW,
            )

    def test_build_does_not_mutate_source(self):
        source = source_with([valid_listing()])
        before = copy.deepcopy(source)
        build_generation(source, valid_settings(), NOW)
        self.assertEqual(source, before)


class SnapshotStoreTests(unittest.TestCase):
    def test_failed_refresh_cannot_replace_current_generation(self):
        store = SnapshotStore()
        accepted = store.refresh(source_with([valid_listing()]), valid_settings(), NOW)
        current = store.current
        rejected = store.refresh(
            source_with([valid_listing(id=2002)], refresh_ok=False),
            valid_settings(),
            NOW,
        )
        self.assertTrue(accepted.accepted)
        self.assertFalse(rejected.accepted)
        self.assertIs(store.current, current)
        self.assertEqual(store.current.published_ids, ("1001",))

    def test_incomplete_catalog_cannot_replace_current_generation(self):
        store = SnapshotStore()
        store.refresh(source_with([valid_listing()]), valid_settings(), NOW)
        current_id = store.current.generation_id
        outcome = store.refresh(
            source_with([valid_listing(id=2002)], catalog_complete=False),
            valid_settings(),
            NOW,
        )
        self.assertFalse(outcome.accepted)
        self.assertEqual(store.current.generation_id, current_id)

    def test_valid_refresh_replaces_current_in_one_generation(self):
        store = SnapshotStore()
        first = store.refresh(source_with([valid_listing()]), valid_settings(), NOW)
        second = store.refresh(
            source_with([valid_listing(id=2002, slug="ouja-2002")]),
            valid_settings(),
            NOW,
        )
        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertEqual(store.current.published_ids, ("2002",))
        self.assertNotEqual(first.generation.generation_id, second.generation.generation_id)

    def test_snapshot_persists_atomically_and_loads_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "monthly_public_snapshot.json"
            store = SnapshotStore(path)
            outcome = store.refresh(source_with([valid_listing()]), valid_settings(), NOW)
            self.assertTrue(outcome.accepted)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["counts"]["published"], 1)

            restored = SnapshotStore(path)
            self.assertEqual(restored.current.published_ids, ("1001",))
            self.assertEqual(restored.current.generation_id, store.current.generation_id)

    def test_corrupt_persisted_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            path.write_text("not-json", encoding="utf-8")
            store = SnapshotStore(path)
            self.assertIsNone(store.current)
            self.assertTrue(store.last_error)

    def test_tampered_persisted_counts_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "snapshot.json"
            store = SnapshotStore(path)
            store.refresh(source_with([valid_listing()]), valid_settings(), NOW)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["counts"]["published"] = 999
            path.write_text(json.dumps(payload), encoding="utf-8")
            restored = SnapshotStore(path)
            self.assertIsNone(restored.current)
            self.assertIn("integrity", restored.last_error)


if __name__ == "__main__":
    unittest.main()
