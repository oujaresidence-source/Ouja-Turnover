# -*- coding: utf-8 -*-
"""Weekday-Gap detection — synthetic, no network, no wiring.

Feeds a hand-built calendar grid into brain.gaps.detect_gaps and asserts the hard rules:
weekends never surface, the run classes (TONIGHT/TOMORROW/ORPHAN/MIDWEEK-2/LONG-GAP/THIS-WEEK)
are correct, weekend nights split a run, and premium/protected units get the +1 priority bump.
"""
import unittest

from brain import gaps

# Fixed week starting on a Sunday so the weekday ints are explicit and stable:
#   idx 0 Sun(6) 1 Mon(0) 2 Tue(1) 3 Wed(2) | 4 Thu(3) 5 Fri(4) 6 Sat(5) | 7 Sun(6)
_WEEKDAYS = [6, 0, 1, 2, 3, 4, 5, 6]
_WEEKEND = {3, 4, 5}
_DATES = ["2026-06-28", "2026-06-29", "2026-06-30", "2026-07-01",
          "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05"]


def _days():
    return [{"date": _DATES[i], "weekday": _WEEKDAYS[i], "weekend": _WEEKDAYS[i] in _WEEKEND}
            for i in range(len(_DATES))]


def _cell(status, price=None, orphan=False):
    c = {"status": status, "price": price}
    if orphan:
        c["orphan"] = 1
    return c


def _E(price=450):
    return _cell("empty", price)


def _B():
    return _cell("booked")


def _grid(units):
    return {"start": _DATES[0], "days_count": len(_DATES), "days": _days(), "units": units}


def _by_unit(result):
    return {g["unit"]: g for g in result}


class GapDetection(unittest.TestCase):
    def setUp(self):
        # One unit per scenario; lid == name so protected_lids is readable.
        self.units = [
            # F1 (protected): only tonight (idx0) is open -> TONIGHT, single.
            {"lid": "F1", "name": "F1",
             "cells": [_E(500), _B(), _B(), _B(), _B(), _B(), _B(), _B()]},
            # 9B: Mon+Tue open between bookings -> MIDWEEK-2, days_out 1.
            {"lid": "9B", "name": "9B",
             "cells": [_B(), _E(600), _E(600), _B(), _B(), _B(), _B(), _B()]},
            # ORPH: single Tue night wedged between two bookings (grid set orphan) -> ORPHAN.
            {"lid": "ORPH", "name": "ORPH",
             "cells": [_B(), _B(), _cell("empty", 480, orphan=True), _B(), _B(), _B(), _B(), _B()]},
            # LONG: Sun+Mon+Tue open -> LONG-GAP (3 nights), always P3.
            {"lid": "LONG", "name": "LONG",
             "cells": [_E(400), _E(400), _E(400), _B(), _B(), _B(), _B(), _B()]},
            # SPLIT: Wed open, weekend open (ineligible), next Sun open -> TWO single gaps.
            {"lid": "SPLIT", "name": "SPLIT",
             "cells": [_B(), _B(), _B(), _E(450), _E(450), _E(450), _E(450), _E(450)]},
            # PROT2 (protected): Mon+Tue midweek pair -> base P2, bumped to P1 by protection.
            {"lid": "PROT2", "name": "PROT2",
             "cells": [_B(), _E(700), _E(700), _B(), _B(), _B(), _B(), _B()]},
        ]
        self.protected = {"F1", "PROT2"}
        self.res = gaps.detect_gaps(_grid(self.units), protected_lids=self.protected, horizon_days=7)

    def test_no_weekend_night_ever_appears(self):
        for g in self.res:
            for wd in g["weekdays"]:
                self.assertNotIn(wd, _WEEKEND, "weekend weekday %s surfaced in %s" % (wd, g["unit"]))
            for d in g["gap_dates"]:
                # Thu/Fri/Sat of this fixed week
                self.assertNotIn(d, {"2026-07-02", "2026-07-03", "2026-07-04"})

    def test_tonight_single_protected(self):
        g = _by_unit(self.res)["F1"]
        self.assertEqual(g["gap_class"], gaps.TONIGHT)
        self.assertEqual(g["priority"], 1)
        self.assertTrue(g["protected"])
        self.assertEqual(g["nights"], 1)

    def test_midweek2_pair(self):
        g = _by_unit(self.res)["9B"]
        self.assertEqual(g["gap_class"], gaps.MIDWEEK2)
        self.assertEqual(g["nights"], 2)
        self.assertEqual(g["priority"], 2)            # not protected, days_out<=3
        self.assertEqual(g["days_out"], 1)
        self.assertEqual(g["gap_labels"], ["Mon 29 Jun", "Tue 30 Jun"])
        self.assertEqual(g["at_risk"], 1200)

    def test_orphan_single(self):
        g = _by_unit(self.res)["ORPH"]
        self.assertEqual(g["gap_class"], gaps.ORPHAN)
        self.assertEqual(g["priority"], 1)
        self.assertEqual(g["nights"], 1)

    def test_long_gap_three(self):
        g = _by_unit(self.res)["LONG"]
        self.assertEqual(g["gap_class"], gaps.LONGGAP)
        self.assertEqual(g["nights"], 3)
        self.assertEqual(g["priority"], 3)

    def test_weekend_splits_into_two_single_gaps(self):
        # Horizon 8 so the post-weekend Sun (idx7) is in range; the weekend empties
        # (idx4 Thu / idx5 Fri / idx6 Sat) must still be excluded, splitting the run in two.
        res8 = gaps.detect_gaps(_grid(self.units), protected_lids=self.protected, horizon_days=8)
        splits = [g for g in res8 if g["unit"] == "SPLIT"]
        self.assertEqual(len(splits), 2)
        for g in splits:
            self.assertEqual(g["nights"], 1)
        weekdays = sorted(g["weekdays"][0] for g in splits)
        self.assertEqual(weekdays, [2, 6])            # Wed and the next Sun only

    def test_protected_bumps_midweek2_to_p1(self):
        g = _by_unit(self.res)["PROT2"]
        self.assertEqual(g["gap_class"], gaps.MIDWEEK2)
        self.assertTrue(g["protected"])
        self.assertEqual(g["priority"], 1)            # P2 -> P1 via protection

    def test_sorted_p1_before_p3(self):
        priorities = [g["priority"] for g in self.res]
        self.assertEqual(priorities, sorted(priorities))

    def test_horizon_clips(self):
        # With a 3-day horizon, the next-Sun split (idx7) cannot appear.
        short = gaps.detect_gaps(_grid(self.units), protected_lids=self.protected, horizon_days=3)
        for g in short:
            self.assertTrue(all(d <= "2026-06-30" for d in g["gap_dates"]))


if __name__ == "__main__":
    unittest.main()
