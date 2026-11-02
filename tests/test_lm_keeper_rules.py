# -*- coding: utf-8 -*-
"""Same-day price keeper — PURE rules (lm_keeper.py). No bot import, no network.
Spec: docs/superpowers/specs/2026-11-02-lm-price-keeper-design.md
Run: python3 -m unittest tests.test_lm_keeper_rules -v
"""
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lm_keeper as k  # noqa: E402

RIY = timezone(timedelta(hours=3))
STEPS = [(15, 10.0), (18, 20.0), (20, 30.0)]


def at(h, m=0, d=1):
    return datetime(2026, 11, d, h, m, tzinfo=RIY)


def res(lid, arrival, booked_utc, total, nights=1, status="new", **fees):
    r = {"listingMapId": lid, "arrivalDate": arrival, "reservationDate": booked_utc,
         "totalPrice": total, "nights": nights, "status": status}
    r.update(fees)
    return r


class StepRules(unittest.TestCase):
    def test_step_boundaries(self):
        cases = {(14, 59): 0, (15, 0): 10, (17, 59): 10, (18, 0): 20,
                 (19, 59): 20, (20, 0): 30, (23, 59): 30}
        for (h, m), pct in cases.items():
            self.assertEqual(k.step_pct(at(h, m), STEPS), pct, (h, m))

    def test_step_started_at(self):
        self.assertIsNone(k.step_started_at(at(14, 59), STEPS))
        self.assertEqual(k.step_started_at(at(19, 12), STEPS), at(18, 0))

    def test_target_price(self):
        self.assertEqual(k.target_price(431, 10), 388)
        self.assertEqual(k.target_price(431, 30), 302)
        self.assertEqual(k.target_price(431, 30, 350), 350)


class Decide(unittest.TestCase):
    def day(self, price, available=1, rid=None):
        return {"price": price, "isAvailable": available, "reservationId": rid}

    def test_booked_or_blocked(self):
        self.assertEqual(k.decide(self.day(500, rid=7), 500, 10, 0, False)["action"], "booked")
        self.assertEqual(k.decide(self.day(500, available=0), 500, 10, 0, False)["action"], "booked")

    def test_no_step_yet_holds(self):
        self.assertEqual(k.decide(self.day(431), 431, 0, 0, False)["action"], "hold")

    def test_pending_guest_waits(self):
        self.assertEqual(k.decide(self.day(431), 431, 10, 0, True)["action"], "wait_pending")

    def test_write_to_target(self):
        d = k.decide(self.day(431), 431, 10, 0, False)
        self.assertEqual((d["action"], d["target"], d["current"]), ("write", 388, 431))

    def test_never_raises(self):
        d = k.decide(self.day(300), 431, 20, 0, False)
        self.assertEqual((d["action"], d["current"]), ("hold", 300))

    def test_minimum_blocks(self):
        d = k.decide(self.day(400), 431, 30, 400, False)
        self.assertEqual(d["action"], "hold")
        self.assertTrue(d["floor_blocked"])


class Minimums(unittest.TestCase):
    def test_booking_time_is_utc_plus_3(self):
        r = res(1, "2026-11-01", "2026-11-01 17:39:00", 608)
        self.assertEqual(k.booked_at_riyadh(r), datetime(2026, 11, 1, 20, 39, tzinfo=RIY))
        self.assertTrue(k.is_same_night(r))

    def test_after_midnight_riyadh_is_not_same_night(self):
        r = res(1, "2026-11-01", "2026-11-01 21:30:00", 608)       # 00:30 on 11-02 Riyadh
        self.assertFalse(k.is_same_night(r))

    def test_nightly_strips_fees(self):
        r = res(1, "2026-11-01", "2026-11-01 18:30:00", 774.18, nights=2, totalTax=100.98)
        self.assertAlmostEqual(k.nightly_price(r), 336.6, places=2)

    def test_lowest_that_sold_without_outliers(self):
        rows = [res(9, "2026-10-%02d" % d, "2026-10-%02d 16:00:00" % d, p)
                for d, p in zip(range(1, 8), (100, 400, 430, 450, 480, 500, 520))]
        rows.append(res(9, "2026-10-09", "2026-10-09 16:00:00", 380, status="cancelled"))
        rows.append(res(9, "2026-10-10", "2026-10-05 16:00:00", 300))   # booked days ahead
        m = k.build_minimums(rows, margin_pct=0)
        self.assertEqual(m["9"]["min"], 400)
        self.assertEqual(m["9"]["n"], 6)

    def test_minimum_sits_10_percent_under_the_lowest_sale(self):
        # owner 2026-11-02: F2's lowest sale was 908 but it sold at 608 after the drop —
        # "lowest that sold" alone would have blocked it and could never learn lower.
        rows = [res(9, "2026-10-%02d" % d, "2026-10-%02d 16:00:00" % d, p)
                for d, p in zip(range(1, 7), (400, 430, 450, 480, 500, 520))]
        m = k.build_minimums(rows)
        self.assertEqual((m["9"]["lowest"], m["9"]["min"]), (400, 360))

    def test_too_few_samples_means_no_minimum(self):
        rows = [res(5, "2026-10-%02d" % d, "2026-10-%02d 16:00:00" % d, 400) for d in range(1, 5)]
        self.assertNotIn("5", k.build_minimums(rows))


class Report(unittest.TestCase):
    def setUp(self):
        drop = at(20, 0).isoformat()
        self.units = {
            "441826": {"name": "F2", "seen_empty": True, "orig": 910, "first_drop_at": drop},
            "500593": {"name": "E5MLQ", "seen_empty": True, "orig": 469, "first_drop_at": drop},
            "482978": {"name": "HUE 202", "seen_empty": True, "orig": 425, "first_drop_at": drop},
            "457230": {"name": "1 MLQ", "seen_empty": True, "orig": 431, "first_drop_at": drop},
            "485203": {"name": "13 JOOD", "seen_empty": True, "orig": 600},
            "457287": {"name": "A5 MLQ", "seen_empty": True, "orig": 492, "first_drop_at": drop,
                       "final": 418, "minimum": 400},
            "437215": {"name": "HUE 103", "seen_empty": True, "orig": 547, "final": 547,
                       "minimum": 547, "reason": "minimum"},
        }
        self.rows = [
            res(441826, "2026-11-01", "2026-11-01 17:39:00", 608),
            res(500593, "2026-11-01", "2026-11-01 17:50:00", 394),
            res(482978, "2026-11-01", "2026-11-01 17:50:00", 304),
            res(457230, "2026-11-01", "2026-11-01 18:30:00", 673.2, nights=2),
            res(485203, "2026-11-01", "2026-11-01 14:22:00", 450),
            res(437215, "2026-11-01", "2026-10-28 10:00:00", 500),          # not same-night
        ]

    def test_attribution(self):
        b = k.night_bookings(self.rows, "2026-11-01", self.units, STEPS)
        ours = [x["name"] for x in b if x["from_drop"]]
        self.assertEqual(ours, ["F2", "E5MLQ", "HUE 202", "1 MLQ"])
        jood = [x for x in b if x["name"] == "13 JOOD"][0]
        self.assertFalse(jood["from_drop"])
        self.assertEqual(jood["pct"], 10)                    # booked 17:22 = during the 3 PM step

    def test_week(self):
        self.assertEqual(k.week_start(date(2026, 11, 2)), date(2026, 11, 1))
        self.assertEqual(k.week_start(date(2026, 11, 1)), date(2026, 11, 1))
        self.assertEqual(k.week_count(self.rows, "2026-11-01", "2026-11-01"), 5)

    def test_render(self):
        b = k.night_bookings(self.rows, "2026-11-01", self.units, STEPS)
        txt = k.render_report("2026-11-01", self.units, b, 5)
        self.assertIn("انحجزت بعد النزول: 4", txt)
        self.assertIn("A5 MLQ", txt)                         # still empty at midnight
        self.assertIn("HUE 103", txt)                        # didn't drop — minimum
        self.assertIn("الحد الأدنى", txt)
        self.assertIn("43", txt)

    def test_chunk(self):
        text = "\n".join("line %d %s" % (i, "x" * 50) for i in range(200))
        parts = k.chunk(text, 500)
        self.assertTrue(all(len(p) <= 500 for p in parts))
        self.assertEqual("\n".join(parts), text)


if __name__ == "__main__":
    unittest.main()
