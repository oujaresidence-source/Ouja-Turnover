# -*- coding: utf-8 -*-
"""
Tests for schedule.coverage — the best-effort Hostaway-listing → covering-employee-emoji bridge
that stamps the OujaCT cleaning channel names. Pure matcher tests need no DB; the end-to-end
emoji lookup patches schedule.db with synthetic rows so it never touches a real brain.db.
"""
import datetime
import unittest

from schedule import coverage, engine, db


EMPLOYEES = [
    {"id": 1, "name": "ناصر", "off_day": 2, "emoji": "🟢", "sort_order": 0},   # off Tuesday
    {"id": 2, "name": "نورة", "off_day": 1, "emoji": "🟣", "sort_order": 1},   # off Monday
]
APARTMENTS = [
    {"id": 10, "name": "الملقا 1", "owner_id": 1, "listing_id": None, "sort_order": 0},
    {"id": 11, "name": "A5",       "owner_id": 1, "listing_id": 5011, "sort_order": 1},
    {"id": 12, "name": "F1",       "owner_id": 2, "listing_id": 5012, "sort_order": 0},
    {"id": 13, "name": "Jood12",   "owner_id": 1, "listing_id": None, "sort_order": 2},
    {"id": 14, "name": "Jood13",   "owner_id": 1, "listing_id": None, "sort_order": 3},
    {"id": 99, "name": "1",        "owner_id": 1, "listing_id": None, "sort_order": 9},   # non-distinctive: never matches
]
HOSTAWAY = [
    {"id": 5011, "name": "Ouja | A5 self entry"},
    {"id": 7001, "name": "Ouja | Jood12 Studio"},
    {"id": 7002, "name": "Ouja | Jood13 Penthouse"},
    {"id": 7003, "name": "Ouja | Riyadh Tower Z"},
]


def _date_for_weekday(target):
    """A real ISO date whose spec-weekday (0=Sun..6=Sat) equals `target`."""
    base = datetime.date(2026, 7, 1)
    for i in range(7):
        d = base + datetime.timedelta(days=i)
        if engine.to_weekday(d) == target:
            return d.isoformat()
    raise AssertionError("no date found")


class MatcherTests(unittest.TestCase):
    def test_exact_code_match(self):
        self.assertEqual(coverage.match_apartment("Ouja | A5 self entry", APARTMENTS)["id"], 11)

    def test_longest_match_wins(self):
        # «Jood13» must beat «Jood12» — and «Jood13» must not be shadowed by the shorter token.
        self.assertEqual(coverage.match_apartment("Ouja | Jood13 Penthouse", APARTMENTS)["id"], 14)
        self.assertEqual(coverage.match_apartment("Ouja | Jood12 Studio", APARTMENTS)["id"], 13)

    def test_arabic_token_match(self):
        self.assertEqual(coverage.match_apartment("عوجا | الملقا 1 دخول ذاتي", APARTMENTS)["id"], 10)

    def test_non_distinctive_never_matches(self):
        # The apartment literally named "1" must not be dragged in by any digit in the listing.
        m = coverage.match_apartment("Ouja | Penthouse 1", APARTMENTS)
        self.assertNotEqual((m or {}).get("id"), 99)

    def test_no_match_returns_none(self):
        self.assertIsNone(coverage.match_apartment("Ouja | Riyadh Tower Z", APARTMENTS))

    def test_best_listing_reverse_match(self):
        # Schedule apartment name -> Hostaway listing id (used by the one-time auto-link).
        self.assertEqual(coverage.best_listing("Jood13", HOSTAWAY), 7002)
        self.assertEqual(coverage.best_listing("Jood12", HOSTAWAY), 7001)
        self.assertEqual(coverage.best_listing("A5", HOSTAWAY), 5011)
        self.assertIsNone(coverage.best_listing("القيروان D7", HOSTAWAY))   # no Hostaway name matches
        self.assertIsNone(coverage.best_listing("1", HOSTAWAY))             # non-distinctive


class EmojiLookupTests(unittest.TestCase):
    def setUp(self):
        self._orig = (db.employees, db.apartments, db.overrides, db.absences_on)
        db.employees = lambda: list(EMPLOYEES)
        db.apartments = lambda: list(APARTMENTS)
        db.overrides = lambda: []
        db.absences_on = lambda d: []

    def tearDown(self):
        db.employees, db.apartments, db.overrides, db.absences_on = self._orig

    def test_owner_emoji_on_working_day(self):
        # On a day ناصر works, his A5 shows his own emoji.
        sun = _date_for_weekday(0)
        self.assertEqual(coverage.cover_emoji_for_listing("Ouja | A5", sun, "⚪"), "🟢")

    def test_cover_emoji_on_owner_day_off(self):
        # On ناصر's day off (Tuesday) A5 is covered by نورة → her emoji, not his. This is the
        # whole point: the channel reflects who actually cleans it that day.
        tue = _date_for_weekday(2)
        self.assertEqual(coverage.cover_emoji_for_listing("Ouja | A5", tue, "⚪"), "🟣")

    def test_placeholder_on_miss(self):
        sun = _date_for_weekday(0)
        self.assertEqual(coverage.cover_emoji_for_listing("Ouja | Unknown Unit", sun, "⚪"), "⚪")

    def test_cover_info_carries_name(self):
        sun = _date_for_weekday(0)
        info = coverage.cover_for_listing("Ouja | F1", sun)
        self.assertEqual(info["name"], "نورة")
        self.assertEqual(info["emoji"], "🟣")

    def test_exact_listing_id_lookup_owner_day(self):
        # A5 is linked to Hostaway listing 5011 -> exact lookup, no name guessing.
        sun = _date_for_weekday(0)
        self.assertEqual(coverage.cover_for_listing_id(5011, sun)["emoji"], "🟢")

    def test_exact_listing_id_lookup_on_day_off(self):
        # On ناصر's day off, the linked A5 returns the covering employee's emoji.
        tue = _date_for_weekday(2)
        self.assertEqual(coverage.cover_for_listing_id(5011, tue)["emoji"], "🟣")

    def test_exact_listing_id_unlinked_returns_none(self):
        sun = _date_for_weekday(0)
        self.assertIsNone(coverage.cover_for_listing_id(99999, sun))


if __name__ == "__main__":
    unittest.main()
