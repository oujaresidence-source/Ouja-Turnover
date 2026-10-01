# -*- coding: utf-8 -*-
"""
permits.dates — every way a permit date reaches us, read one way.

The seed is Hijri (DD/MM/YYYY, Umm al-Qura). Future imports may be Gregorian, typed with
Arabic-Indic digits, or arrive as Excel serial numbers. Whatever arrives, the stored value
is ISO Gregorian, and anything we could not read with certainty is FLAGGED, never guessed
silently — a wrong expiry date is how a permit gets missed.

Run: python3 -m unittest tests.test_permits_dates
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from permits import dates  # noqa: E402

HAS_HIJRI = dates.hijri_available()


class TestGregorian(unittest.TestCase):

    def test_iso(self):
        self.assertEqual(dates.parse_date("2026-10-11")["iso"], "2026-10-11")

    def test_iso_with_time_keeps_the_day(self):
        self.assertEqual(dates.parse_date("2026-10-11T09:30:00")["iso"], "2026-10-11")

    def test_day_first_slash(self):
        p = dates.parse_date("11/10/2026")
        self.assertEqual(p["iso"], "2026-10-11")
        self.assertEqual(p["calendar"], "gregorian")

    def test_both_parts_could_be_a_month_is_flagged_not_guessed_silently(self):
        p = dates.parse_date("5/3/2027")
        self.assertEqual(p["iso"], "2027-03-05")          # day-first, as the team writes it
        self.assertEqual(p["issue"], "ambiguous_day_month")

    def test_a_day_above_12_is_not_ambiguous(self):
        self.assertEqual(dates.parse_date("25/3/2027")["issue"], "")

    def test_same_day_and_month_is_not_ambiguous(self):
        self.assertEqual(dates.parse_date("5/5/2027")["issue"], "")

    def test_arabic_indic_digits_year_first(self):
        self.assertEqual(dates.parse_date("٢٠٢٦/١٠/١١")["iso"], "2026-10-11")

    def test_persian_digits(self):
        self.assertEqual(dates.parse_date("۱۱/۱۰/۲۰۲۶")["iso"], "2026-10-11")

    def test_excel_serial(self):
        self.assertEqual(dates.parse_date(46306)["iso"], "2026-10-11")
        self.assertEqual(dates.parse_date(46306.0)["iso"], "2026-10-11")
        self.assertEqual(dates.parse_date("46306")["iso"], "2026-10-11")

    def test_openpyxl_datetime(self):
        self.assertEqual(dates.parse_date(datetime.datetime(2026, 10, 11, 0, 0))["iso"], "2026-10-11")
        self.assertEqual(dates.parse_date(datetime.date(2026, 10, 11))["iso"], "2026-10-11")

    def test_impossible_day_is_invalid(self):
        p = dates.parse_date("30/02/2026")
        self.assertIsNone(p["iso"])
        self.assertEqual(p["issue"], "invalid")

    def test_rubbish_is_invalid(self):
        p = dates.parse_date("قريب")
        self.assertIsNone(p["iso"])
        self.assertEqual(p["issue"], "invalid")

    def test_empty_is_none_with_no_issue(self):
        for v in (None, "", "   "):
            p = dates.parse_date(v)
            self.assertIsNone(p["iso"])
            self.assertEqual(p["issue"], "")

    def test_month_name_in_words(self):
        self.assertEqual(dates.parse_date("11 أكتوبر 2026")["iso"], "2026-10-11")
        self.assertEqual(dates.parse_date("11 October 2026")["iso"], "2026-10-11")

    def test_bidi_marks_are_ignored(self):
        self.assertEqual(dates.parse_date("\u200e2026-10-11\u2069")["iso"], "2026-10-11")


@unittest.skipUnless(HAS_HIJRI, "hijridate not installed (F22): Hijri parsing reports hijri_unavailable")
class TestHijri(unittest.TestCase):

    def test_year_first_with_marker(self):
        p = dates.parse_date("1448/03/15هـ")
        self.assertEqual(p["iso"], "2026-08-28")
        self.assertEqual(p["calendar"], "hijri")

    def test_seed_style_day_first(self):
        # F2 — the first permit due after go-live: 01/05/1448 → 2026-10-12
        self.assertEqual(dates.parse_date("01/05/1448")["iso"], "2026-10-12")

    def test_hijri_is_never_flagged_ambiguous(self):
        """The ministry format is fixed DD/MM/YYYY — 07/07/1448 is one date, not two."""
        self.assertEqual(dates.parse_date("07/07/1448")["issue"], "")

    def test_the_column_hint_decides_the_calendar(self):
        self.assertEqual(dates.parse_date("01/05/1448", calendar_hint="hijri")["iso"], "2026-10-12")

    def test_invalid_hijri_month(self):
        p = dates.parse_date("15/13/1448")
        self.assertIsNone(p["iso"])
        self.assertEqual(p["issue"], "invalid")

    def test_to_hijri_str(self):
        self.assertEqual(dates.to_hijri_str("2026-10-11"), "٣٠ ربيع الآخر ١٤٤٨هـ")

    def test_round_trip_the_whole_seed_span(self):
        d = datetime.date(2025, 10, 1)
        while d < datetime.date(2027, 9, 1):
            h = dates.to_hijri_parts(d.isoformat())
            self.assertEqual(dates.parse_date("%02d/%02d/%d" % (h[2], h[1], h[0]))["iso"], d.isoformat())
            d += datetime.timedelta(days=17)


class TestWithoutHijridate(unittest.TestCase):
    """F22: a missing optional library must flag, never crash."""

    def test_unavailable_is_flagged(self):
        saved = dates._HIJRI
        try:
            dates._HIJRI = None
            p = dates.parse_date("01/05/1448")
            self.assertIsNone(p["iso"])
            self.assertEqual(p["issue"], "hijri_unavailable")
            self.assertEqual(dates.to_hijri_str("2026-10-11"), "")
        finally:
            dates._HIJRI = saved


class TestWords(unittest.TestCase):

    def test_words_ar(self):
        self.assertEqual(dates.words_ar("2026-10-11"), "١١ أكتوبر ٢٠٢٦")

    def test_words_ar_blank(self):
        self.assertEqual(dates.words_ar(None), "")

    def test_ar_digits(self):
        self.assertEqual(dates.ar_digits(375), "٣٧٥")

    def test_weekday_ar(self):
        self.assertEqual(dates.weekday_ar("2026-10-01"), "الخميس")


if __name__ == "__main__":
    unittest.main()
