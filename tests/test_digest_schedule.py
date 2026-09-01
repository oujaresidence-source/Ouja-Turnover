# -*- coding: utf-8 -*-
"""digest.schedule.should_fire — the pure decision behind bot.py's digest_loop.
Written BEFORE the loop (brief §2.3 / §11): the loop is a 30-minute tick, so this
function must say yes only on the configured weekday + hour and only once per week
(the persisted latch = an issue row for this week already exists)."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import schedule

TZ = ZoneInfo("Asia/Riyadh")


class ShouldFire(unittest.TestCase):
    def test_fires_only_on_wednesday_13_riyadh(self):
        start = datetime(2026, 8, 31, 0, 0, tzinfo=TZ)     # Monday
        yes = []
        for step in range(7 * 24 * 2):                       # every half hour for a week
            now = start + timedelta(minutes=30 * step)
            if schedule.should_fire(now):
                yes.append(now)
        self.assertEqual([n.strftime("%a %H:%M") for n in yes], ["Wed 13:00", "Wed 13:30"])
        self.assertTrue(all(n.weekday() == 2 for n in yes))

    def test_latch_blocks_a_second_run_in_the_same_week(self):
        now = datetime(2026, 9, 2, 13, 25, tzinfo=TZ)
        self.assertTrue(schedule.should_fire(now, existing_week_of=None))
        self.assertTrue(schedule.should_fire(now, existing_week_of=""))
        self.assertFalse(schedule.should_fire(now, existing_week_of="2026-09-03"))
        self.assertTrue(schedule.should_fire(now, existing_week_of="2026-08-27"))

    def test_env_day_and_hour_are_respected(self):
        thu_15 = datetime(2026, 9, 3, 15, 5, tzinfo=TZ)
        self.assertTrue(schedule.should_fire(thu_15, day=3, hour=15))
        self.assertFalse(schedule.should_fire(thu_15, day=2, hour=13))
        self.assertFalse(schedule.should_fire(thu_15, day=3, hour=13))

    def test_never_before_one_pm_even_if_misconfigured(self):
        # Owner's standing rule: nothing scheduled before 13:00. hour<13 is clamped to 13.
        wed_9 = datetime(2026, 9, 2, 9, 0, tzinfo=TZ)
        wed_13 = datetime(2026, 9, 2, 13, 0, tzinfo=TZ)
        self.assertFalse(schedule.should_fire(wed_9, hour=9))
        self.assertTrue(schedule.should_fire(wed_13, hour=9))

    def test_a_utc_clock_is_converted_to_riyadh_first(self):
        # Wed 13:10 Riyadh == Wed 10:10 UTC.
        utc = datetime(2026, 9, 2, 10, 10, tzinfo=ZoneInfo("UTC"))
        self.assertTrue(schedule.should_fire(utc))
        self.assertFalse(schedule.should_fire(datetime(2026, 9, 2, 13, 10, tzinfo=ZoneInfo("UTC"))))

    def test_naive_clock_refused(self):
        with self.assertRaises(ValueError):
            schedule.should_fire(datetime(2026, 9, 2, 13, 0))


if __name__ == "__main__":
    unittest.main()
