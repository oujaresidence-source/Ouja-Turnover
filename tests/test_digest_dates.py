# -*- coding: utf-8 -*-
"""digest.dates — the digest always covers the next Thursday–Saturday, computed in
Asia/Riyadh from a frozen clock. Every weekday is tested, including when today IS
Thursday/Friday/Saturday (the weekend already in progress is the one we cover)."""
import os
import sys
import unittest
from datetime import datetime, date
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import dates

TZ = ZoneInfo("Asia/Riyadh")


def _at(iso, hour=13):
    return datetime.fromisoformat(iso + "T%02d:00:00" % hour).replace(tzinfo=TZ)


class WeekFor(unittest.TestCase):
    def test_every_weekday_maps_to_the_right_thursday(self):
        # 2026-09-03 is a Thursday.
        cases = {
            "2026-08-30": "2026-09-03",   # Sun
            "2026-08-31": "2026-09-03",   # Mon
            "2026-09-01": "2026-09-03",   # Tue
            "2026-09-02": "2026-09-03",   # Wed  ← the scheduled build day
            "2026-09-03": "2026-09-03",   # Thu  (today is Thursday → this weekend)
            "2026-09-04": "2026-09-03",   # Fri
            "2026-09-05": "2026-09-03",   # Sat
            "2026-09-06": "2026-09-10",   # Sun  → next weekend
        }
        for today, thu in cases.items():
            with self.subTest(today=today):
                w = dates.week_for(_at(today))
                self.assertEqual(w.iso, thu)
                self.assertEqual(w.thu.weekday(), 3)
                self.assertEqual((w.fri - w.thu).days, 1)
                self.assertEqual((w.sat - w.thu).days, 2)

    def test_late_night_wednesday_in_riyadh_is_still_wednesday(self):
        # 23:30 Riyadh on Wed is 20:30 UTC; a UTC clock would already be wrong.
        w = dates.week_for(_at("2026-09-02", 23).replace(minute=30))
        self.assertEqual(w.iso, "2026-09-03")

    def test_a_utc_clock_is_converted_not_trusted(self):
        # Thu 2026-09-10 00:30 Riyadh == Wed 2026-09-09 21:30 UTC → must still say 09-10.
        utc = datetime(2026, 9, 9, 21, 30, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(dates.week_for(utc).iso, "2026-09-10")

    def test_naive_datetime_is_refused(self):
        with self.assertRaises(ValueError):
            dates.week_for(datetime(2026, 9, 2, 13))

    def test_days_of_week(self):
        w = dates.week_for(_at("2026-09-02"))
        self.assertEqual(dates.day_key(w, date(2026, 9, 3)), "thu")
        self.assertEqual(dates.day_key(w, date(2026, 9, 4)), "fri")
        self.assertEqual(dates.day_key(w, date(2026, 9, 5)), "sat")
        self.assertIsNone(dates.day_key(w, date(2026, 9, 6)))
        self.assertTrue(dates.in_week(w, date(2026, 9, 5)))
        self.assertFalse(dates.in_week(w, date(2026, 9, 2)))


class Labels(unittest.TestCase):
    def test_same_month(self):
        self.assertEqual(dates.week_for(_at("2026-09-02")).label_ar, "٣–٥ سبتمبر")

    def test_crossing_month(self):
        # Thu 2026-10-29 .. Sat 10-31 stays in October; Thu 12-31 .. Sat 01-02 crosses.
        self.assertEqual(dates.week_for(_at("2026-10-28")).label_ar, "٢٩–٣١ أكتوبر")
        self.assertEqual(dates.week_for(_at("2026-12-30")).label_ar, "٣١ ديسمبر – ٢ يناير")

    def test_arabic_indic_helpers(self):
        self.assertEqual(dates.ar_digits("9:00"), "٩:٠٠")
        self.assertEqual(dates.ar_date(date(2026, 9, 3)), "٣ سبتمبر")
        self.assertEqual(dates.ar_time(21, 0), "٩:٠٠م")
        self.assertEqual(dates.ar_time(9, 30), "٩:٣٠ص")
        self.assertEqual(dates.ar_time(0, 15), "١٢:١٥ص")
        self.assertEqual(dates.ar_time(12, 0), "١٢:٠٠م")
        self.assertEqual(dates.AR_DAY["thu"], "الخميس")
        self.assertEqual(dates.AR_DAY["fri"], "الجمعة")
        self.assertEqual(dates.AR_DAY["sat"], "السبت")


if __name__ == "__main__":
    unittest.main()
