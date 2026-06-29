# -*- coding: utf-8 -*-
"""Elite v5 trigger calendar — synthetic, no clock/DB.

Asserts the explicit trigger table in brain.triggers: payday/end-of-month day windows (with the
27..1 month-wrap), seasonal months, the holiday windows + long-weekend look-ahead, the editable
Saudi holiday table + overrides, and that evergreen campaigns only fire midweek (never weekend).
"""
import unittest
from datetime import date

from brain import triggers


def codes(d, overrides=None):
    return [e["code"] for e in triggers.eligible_campaigns(d, overrides)]


class HolidayTable(unittest.TestCase):
    def test_fixed_holidays_resolve(self):
        hd = triggers.holiday_dates(2026)
        self.assertEqual(hd["NATIONAL-DAY"], date(2026, 9, 23))
        self.assertEqual(hd["FOUNDING-DAY"], date(2026, 2, 22))
        self.assertEqual(hd["GREG-NEW-YEAR"], date(2026, 1, 1))

    def test_override_changes_a_lunar_date(self):
        hd = triggers.holiday_dates(2026, {"EID-FITR": "2026-03-25"})
        self.assertEqual(hd["EID-FITR"], date(2026, 3, 25))

    def test_md_override_homes_to_year(self):
        hd = triggers.holiday_dates(2027, {"EID-ADHA": "05-16"})
        self.assertEqual(hd["EID-ADHA"], date(2027, 5, 16))


class DayWindows(unittest.TestCase):
    def test_payday_window_and_month_wrap(self):
        self.assertIn("PAYDAY-DROPPED", codes(date(2026, 4, 27)))   # day 27
        self.assertIn("PAYDAY-DROPPED", codes(date(2026, 5, 1)))    # day 1 (wrap)
        self.assertNotIn("PAYDAY-DROPPED", codes(date(2026, 4, 15)))

    def test_end_of_month_window(self):
        self.assertIn("END-OF-MONTH", codes(date(2026, 4, 23)))
        self.assertNotIn("END-OF-MONTH", codes(date(2026, 4, 27)))

    def test_results_sorted_by_priority_desc(self):
        elig = triggers.eligible_campaigns(date(2026, 4, 27))
        pr = [e["priority"] for e in elig]
        self.assertEqual(pr, sorted(pr, reverse=True))


class Seasons(unittest.TestCase):
    def test_heatwave_summer_perfect_winter(self):
        self.assertIn("HEATWAVE", codes(date(2026, 7, 13)))
        self.assertNotIn("HEATWAVE", codes(date(2026, 1, 13)))
        self.assertIn("PERFECT-WEATHER", codes(date(2026, 1, 13)))


class HolidaysAndLongWeekend(unittest.TestCase):
    def test_long_weekend_fires_4_days_before_a_holiday(self):
        self.assertIn("LONG-WEEKEND", codes(date(2026, 9, 19)))     # 4 days before National Day
        self.assertNotIn("LONG-WEEKEND", codes(date(2026, 9, 1)))   # too far out

    def test_national_day_window(self):
        self.assertIn("NATIONAL-DAY", codes(date(2026, 9, 22)))

    def test_eid_window_uses_override(self):
        ov = {"EID-ADHA": "2026-05-27"}
        self.assertIn("EID", codes(date(2026, 5, 25), ov))


class Evergreen(unittest.TestCase):
    def test_evergreen_only_midweek(self):
        self.assertIn("MIDWEEK-RESET", codes(date(2026, 6, 28)))    # Sunday
        self.assertNotIn("MIDWEEK-RESET", codes(date(2026, 7, 3)))  # Friday

    def test_segment_campaigns_are_calendar_always(self):
        # behavioral campaigns fire on any day (the audience gate decides, not the calendar)
        self.assertIn("LAST-MINUTE", codes(date(2026, 7, 3)))       # even a Friday


if __name__ == "__main__":
    unittest.main()
