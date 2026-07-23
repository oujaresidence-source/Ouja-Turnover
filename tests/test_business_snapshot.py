# -*- coding: utf-8 -*-
"""
Tests for business.snapshot — nightly orchestration + 400-day archive retention.

Run:  python3 -m unittest tests.test_business_snapshot
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from business.snapshot import archives_to_prune, build_and_write, archive_name  # noqa: E402


class ArchiveNaming(unittest.TestCase):
    def test_archive_name_is_dated(self):
        self.assertEqual(archive_name(datetime.date(2026, 7, 23)),
                         "metrics_snapshot_2026-07-23.json")


class Retention(unittest.TestCase):
    def test_prunes_only_files_older_than_retain_days(self):
        today = datetime.date(2026, 7, 23)
        names = [
            "metrics_snapshot_2026-07-23.json",   # today -> keep
            "metrics_snapshot_2025-06-19.json",   # 399 days -> keep
            "metrics_snapshot_2025-06-18.json",   # 400 days -> keep (boundary)
            "metrics_snapshot_2025-06-17.json",   # 401 days -> prune
            "metrics_snapshot_2024-01-01.json",   # very old -> prune
        ]
        pruned = archives_to_prune(names, today=today, retain_days=400)
        self.assertEqual(
            sorted(pruned),
            ["metrics_snapshot_2024-01-01.json", "metrics_snapshot_2025-06-17.json"],
        )

    def test_ignores_non_archive_filenames(self):
        today = datetime.date(2026, 7, 23)
        names = ["metrics_snapshot.json", "readme.txt", "metrics_snapshot_not-a-date.json"]
        self.assertEqual(archives_to_prune(names, today=today, retain_days=400), [])


class Orchestration(unittest.TestCase):
    def test_build_and_write_saves_current_and_archive(self):
        saved = {}

        def fake_fetch(**_):
            return {"as_of": "2026-07-23", "channel": "airbnb",
                    "window": {"start": "2024-07-23", "end": "2026-07-23"},
                    "listings": [], "reservations": [], "reviews": []}

        def fake_save(name, obj):
            saved[name] = obj
            return True

        res = build_and_write(
            today=datetime.date(2026, 7, 23),
            fetch=fake_fetch, save_json=fake_save,
            list_archives=lambda: [], delete=lambda n: None,
        )
        self.assertIn("metrics_snapshot.json", saved)
        self.assertIn("metrics_snapshot_2026-07-23.json", saved)
        # both writes are the SAME computed dict (page and archive can't disagree)
        self.assertEqual(saved["metrics_snapshot.json"], saved["metrics_snapshot_2026-07-23.json"])
        self.assertEqual(saved["metrics_snapshot.json"]["reservations_total"], 0)
        self.assertEqual(res["ok"], True)

    def test_build_and_write_prunes_stale_archives(self):
        deleted = []
        build_and_write(
            today=datetime.date(2026, 7, 23),
            fetch=lambda **_: {"as_of": "2026-07-23", "channel": "airbnb",
                               "window": {"start": "2024-07-23", "end": "2026-07-23"},
                               "listings": [], "reservations": [], "reviews": []},
            save_json=lambda n, o: True,
            list_archives=lambda: ["metrics_snapshot_2024-01-01.json",
                                   "metrics_snapshot_2026-07-23.json"],
            delete=deleted.append,
        )
        self.assertEqual(deleted, ["metrics_snapshot_2024-01-01.json"])


if __name__ == "__main__":
    unittest.main()
