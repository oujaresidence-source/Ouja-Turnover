# -*- coding: utf-8 -*-
"""
«المناوبة» engine invariants — pure functions, no database, no Discord.

Run: python3 -m unittest tests.test_oncall_engine
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oncall import engine as E   # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))
FIVE = ["ناصر", "مآثر", "نورة", "محمد اليامي", "عهود"]
OFF = {"ناصر": 2, "مآثر": 0, "نورة": 1, "محمد اليامي": 3, "عهود": 6}   # the real seed
D0 = datetime.date(2026, 10, 4)                                        # a Sunday


def hours(slots):
    return sorted((s["end_min"] - s["start_min"]) // 60 for s in slots)


def simulate(nights, available_fn):
    hist = []
    for i in range(nights):
        d = D0 + datetime.timedelta(days=i)
        slots = E.build_night(d, available_fn(d), hist[-7:])
        hist.append({"date": d.isoformat(), "slots": slots})
    return hist


def totals(hist):
    t = {}
    for h in hist:
        for s in h["slots"]:
            t[s["employee"]] = t.get(s["employee"], 0) + (s["end_min"] - s["start_min"]) // 60
    return t


class Rotation(unittest.TestCase):
    def test_five_people_split_2_2_1_1_1(self):
        self.assertEqual(hours(E.build_night(D0, FIVE, [])), [1, 1, 1, 2, 2])

    def test_lengths_for_every_headcount(self):
        want = {1: [7], 2: [3, 4], 3: [2, 2, 3], 4: [1, 2, 2, 2], 5: [1, 1, 1, 2, 2]}
        for n, exp in want.items():
            self.assertEqual(hours(E.build_night(D0, FIVE[:n], [])), exp, n)

    def test_contiguous_17_to_24_no_gaps(self):
        for n in range(1, 6):
            s = E.build_night(D0, FIVE[:n], [])
            self.assertEqual(s[0]["start_min"], 0)
            self.assertEqual(s[-1]["end_min"], 420)
            for a, b in zip(s, s[1:]):
                self.assertEqual(a["end_min"], b["start_min"])

    def test_nobody_available_means_uncovered(self):
        self.assertEqual(E.build_night(D0, [], []), [])

    def test_deterministic(self):
        h = simulate(3, lambda d: FIVE)
        self.assertEqual(E.build_night(D0 + datetime.timedelta(days=3), FIVE, h),
                         E.build_night(D0 + datetime.timedelta(days=3), FIVE, h))

    def test_first_week_fair_within_one_hour(self):
        t = totals(simulate(7, lambda d: FIVE))
        self.assertLessEqual(max(t.values()) - min(t.values()), 1, t)

    def test_four_weeks_with_real_days_off_fair_within_one_hour(self):
        t = totals(simulate(28, lambda d: [p for p in FIVE if OFF[p] != E.sun_weekday(d)]))
        self.assertLessEqual(max(t.values()) - min(t.values()), 1, t)

    def test_last_slot_never_twice_running(self):
        h = simulate(28, lambda d: [p for p in FIVE if OFF[p] != E.sun_weekday(d)])
        for a, b in zip(h, h[1:]):
            self.assertNotEqual(a["slots"][-1]["employee"], b["slots"][-1]["employee"], b["date"])

    def test_start_time_rotates_when_everyone_works(self):
        h = simulate(14, lambda d: FIVE)
        for a, b in zip(h, h[1:]):
            prev = {s["employee"]: s["start_min"] for s in a["slots"]}
            for s in b["slots"]:
                self.assertNotEqual(prev[s["employee"]], s["start_min"], (b["date"], s))

    def test_unavailable_never_scheduled(self):
        s = E.build_night(D0, ["ناصر", "نورة"], [])
        self.assertEqual({x["employee"] for x in s}, {"ناصر", "نورة"})

    def test_owner_at_boundaries(self):
        s = E.build_night(D0, FIVE, [])
        self.assertIsNone(E.owner_at(s, None))
        self.assertEqual(E.owner_at(s, 0)["employee"], s[0]["employee"])
        self.assertEqual(E.owner_at(s, 419)["employee"], s[-1]["employee"])
        self.assertEqual(E.owner_at(s, s[0]["end_min"])["employee"], s[1]["employee"])
        self.assertIsNone(E.owner_at(s, 420))

    def test_night_minute(self):
        self.assertEqual(E.night_minute(datetime.datetime(2026, 10, 4, 16, 59, tzinfo=TZ)),
                         (None, None))
        self.assertEqual(E.night_minute(datetime.datetime(2026, 10, 4, 17, 0, tzinfo=TZ)),
                         (D0, 0))
        self.assertEqual(E.night_minute(datetime.datetime(2026, 10, 4, 23, 59, tzinfo=TZ)),
                         (D0, 419))
        self.assertEqual(E.night_minute(datetime.datetime(2026, 10, 5, 0, 0, tzinfo=TZ)),
                         (None, None))

    def test_sun_weekday(self):
        self.assertEqual(E.sun_weekday(D0), 0)                       # Sunday
        self.assertEqual(E.sun_weekday(D0 + datetime.timedelta(days=6)), 6)


class Checks(unittest.TestCase):
    def test_two_hour_slot_has_eight_checks(self):
        self.assertEqual(E.check_minutes(0, 120), [0, 15, 30, 45, 60, 75, 90, 105])

    def test_one_hour_slot_has_four_checks(self):
        self.assertEqual(E.check_minutes(360, 420), [360, 375, 390, 405])

    def _v(self, **kw):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        args = dict(due_at=due, now=due + datetime.timedelta(minutes=11), delivered=True,
                    answered_at=None, downtimes=[])
        args.update(kw)
        return E.check_verdict(**args)

    def test_answered_in_window(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        self.assertEqual(self._v(answered_at=due + datetime.timedelta(minutes=10))[0], "answered")

    def test_pending_inside_window(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        self.assertEqual(self._v(now=due + datetime.timedelta(minutes=9))[0], "pending")

    def test_missed_after_window(self):
        self.assertEqual(self._v()[0], "missed")

    def test_late_answer_is_still_a_miss(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        self.assertEqual(self._v(answered_at=due + datetime.timedelta(minutes=11))[0], "missed")

    def test_not_delivered_is_void_never_a_miss(self):
        self.assertEqual(self._v(delivered=False), ("voided", "not_delivered"))

    def test_downtime_inside_window_is_void(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        dt = [(due + datetime.timedelta(minutes=3), due + datetime.timedelta(minutes=6))]
        self.assertEqual(self._v(downtimes=dt), ("voided", "bot_down"))

    def test_downtime_elsewhere_does_not_void(self):
        due = datetime.datetime(2026, 10, 4, 19, 0, tzinfo=TZ)
        dt = [(due - datetime.timedelta(minutes=30), due - datetime.timedelta(minutes=20))]
        self.assertEqual(self._v(downtimes=dt)[0], "missed")

    def test_miss_ladder(self):
        self.assertEqual(E.miss_decision(1), E.MISS_ALERT)
        self.assertEqual(E.miss_decision(2), E.MISS_WARN)
        self.assertEqual(E.miss_decision(3), E.MISS_ALERT_AGAIN)
        self.assertEqual(E.miss_decision(7), E.MISS_ALERT_AGAIN)


class Issues(unittest.TestCase):
    T0 = datetime.datetime(2026, 10, 4, 18, 0, tzinfo=TZ)

    def test_claim_overdue_after_ten_minutes_once(self):
        t = self.T0
        self.assertFalse(E.claim_overdue(t, None, t + datetime.timedelta(minutes=9), False))
        self.assertTrue(E.claim_overdue(t, None, t + datetime.timedelta(minutes=10), False))
        self.assertFalse(E.claim_overdue(t, None, t + datetime.timedelta(minutes=30), True))
        self.assertFalse(E.claim_overdue(t, t, t + datetime.timedelta(minutes=30), False))

    def test_stale_only_after_slot_end(self):
        end = self.T0 + datetime.timedelta(hours=1)
        upd = self.T0
        self.assertFalse(E.stale_due(end, upd, end - datetime.timedelta(minutes=1), False))
        self.assertTrue(E.stale_due(end, upd, end, False))

    def test_stale_needs_thirty_quiet_minutes(self):
        end = self.T0
        upd = end + datetime.timedelta(minutes=10)
        self.assertFalse(E.stale_due(end, upd, upd + datetime.timedelta(minutes=29), False))
        self.assertTrue(E.stale_due(end, upd, upd + datetime.timedelta(minutes=30), False))

    def test_stale_once_per_night_and_never_after_midnight(self):
        end, upd = self.T0, self.T0
        self.assertFalse(E.stale_due(end, upd, end + datetime.timedelta(hours=2), True))
        after_midnight = datetime.datetime(2026, 10, 5, 0, 30, tzinfo=TZ)
        self.assertFalse(E.stale_due(end, upd, after_midnight, False))


class Swaps(unittest.TestCase):
    SLOT = {"id": 1, "employee": "نورة", "start_min": 0, "end_min": 120}

    def test_exchange_and_takeover(self):
        ok, kind, _ = E.swap_decision("published", "ناصر", self.SLOT, {"id": 2}, True, True, False)
        self.assertEqual((ok, kind), (True, "exchange"))
        ok, kind, _ = E.swap_decision("published", "ناصر", self.SLOT, None, True, True, False)
        self.assertEqual((ok, kind), (True, "takeover"))

    def test_refusals(self):
        cases = [("locked", "ناصر", True, True, False),
                 ("published", "نوره", True, True, False),          # own slot, other spelling
                 ("published", "ناصر", False, True, False),
                 ("published", "ناصر", True, False, False),
                 ("published", "ناصر", True, True, True)]
        for st, who, rok, tok, pend in cases:
            ok, _k, why = E.swap_decision(st, who, self.SLOT, None, rok, tok, pend)
            self.assertFalse(ok, (st, who))
            self.assertTrue(why)


class Names(unittest.TestCase):
    def test_claim_picker_names_match_calendar(self):
        self.assertTrue(E.same_person("نوره", "نورة"))
        self.assertTrue(E.same_person("ماثر", "مآثر"))
        self.assertTrue(E.same_person("محمد", "محمد اليامي"))
        self.assertFalse(E.same_person("ناصر", "نورة"))
        self.assertFalse(E.same_person("", "نورة"))

    def test_hm(self):
        self.assertEqual(E.hm(0), "5:00")
        self.assertEqual(E.hm(420), "12:00")
        self.assertEqual(E.hm(135), "7:15")


if __name__ == "__main__":
    unittest.main()
