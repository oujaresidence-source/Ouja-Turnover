# -*- coding: utf-8 -*-
"""
The apartment target — what PAYS since 2026-11-15 (it replaced the commission on 10/10 reviews).

Locked here, each one a way Ouja or an employee loses money if it breaks:
    * an apartment pays only on revenue ABOVE its target, and only a share of OUJA'S FEE on it
    * under the target = zero, never a deduction
    * a blocked night lowers the target; a slow month for the whole company lowers every
      target; a strong month never raises one
    * a month rated under 4.75 pays nothing for that apartment — unless the supervisor accepted
      the employee's note that the cause was not theirs
    * a note is raised by the apartment's own employee, decided by the manager or the owner
    * no contract fee on record -> the apartment pays zero and is flagged
    * the operations manager's 15% is ON TOP of what the team earned
    * an approved month is frozen: later bookings do not move it
    * an employee's view carries no fee, no percentage and nobody else's number

Run: python3 -m unittest tests.test_targets_pay
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from targets import db, engine, pay, score                 # noqa: E402
from targets.host import HOST                              # noqa: E402
from tests.test_targets_flow import AHOOD, NORA, Case, D   # noqa: E402


class Rules(unittest.TestCase):
    def test_revenue_is_split_by_night_across_months(self):
        r = [{"status": "new", "arrival": "2026-10-30", "departure": "2026-11-03", "total": 4000}]
        self.assertEqual(engine.revenue_in_month(r, "2026-10"), 2000.0)
        self.assertEqual(engine.revenue_in_month(r, "2026-11"), 2000.0)
        r[0]["status"] = "cancelled"
        self.assertEqual(engine.revenue_in_month(r, "2026-11"), 0.0)

    def test_commission_is_a_share_of_the_fee_on_the_part_above(self):
        over, pay_ = engine.target_commission(15000, 11000, 0.20)
        self.assertEqual(over, 4000.0)
        self.assertAlmostEqual(pay_, 160.0)                  # 4000 x 20% fee x 20% share
        self.assertEqual(engine.target_commission(9000, 11000, 0.20), (0.0, 0.0))
        self.assertEqual(engine.target_commission(15000, 11000, None), (4000.0, 0.0))
        self.assertEqual(engine.target_commission(15000, 0, 0.20), (0.0, 0.0))   # no target, no pay

    def test_commission_never_exceeds_the_share_of_the_fee(self):
        for rev in range(0, 60000, 1700):
            for tgt in (1, 5000, 20000):
                over, p = engine.target_commission(rev, tgt, 0.25)
                self.assertLessEqual(p, max(0, rev - tgt) * 0.25 * engine.TARGET_SHARE + 1e-9)
                self.assertGreaterEqual(p, 0.0)

    def test_blocked_nights_and_a_slow_season_lower_the_target(self):
        self.assertEqual(engine.month_target(9000, 30), 9000.0)
        self.assertEqual(engine.month_target(9000, 30, blocked=10), 6000.0)
        self.assertEqual(engine.month_target(9000, 30, season=0.5), 4500.0)
        self.assertEqual(engine.month_target(9000, 30, blocked=30), 0.0)

    def test_season_only_moves_down(self):
        self.assertEqual(engine.season_factor(80, 100), 0.8)
        self.assertEqual(engine.season_factor(150, 100), 1.0)
        self.assertEqual(engine.season_factor(50, 0), 1.0)

    def test_rating_rule(self):
        self.assertFalse(engine.rating_blocks(None))
        self.assertFalse(engine.rating_blocks(4.75))
        self.assertTrue(engine.rating_blocks(4.74))
        self.assertFalse(engine.rating_blocks(3.0, waived=True))


class PayCase(Case):
    """A2 (نورة) and B1 (عهود) each made 9,000 a month in Jul-Sep 2026 -> target 10,800.
    October starts as an ordinary month (each unit at its base) so the season factor is 1."""
    ORDINARY_OCTOBER = True

    def setUp(self):
        super().setUp()
        self.ratings = {}
        HOST.unit_rating = lambda lid, mk: self.ratings.get((str(lid), mk))
        for unit in ("101", "102", "201"):
            for m in ("07", "08", "09"):
                self.res(unit, "0550000%s%s" % (unit[0], m), "قديم", "2026-%s-02" % m, "2026-%s-11" % m,
                         channel="airbnb", total=9000.0 - (1000.0 if unit == "101" else 0))
            if self.ORDINARY_OCTOBER:
                self.res(unit, "0550000%s10" % unit[0], "قديم", "2026-10-20", "2026-10-29",
                         channel="airbnb", total=9000.0 - (1000.0 if unit == "101" else 0))
        score.propose("2026-Q4", self.today())
        db.approve_targets("2026-Q4", "owner", "2026-10-01T00:00:00")

    def tgt(self, unit):
        return float(db.target("2026-Q4", unit)["rev_target"])

    def sell(self, unit, total, a="2026-10-05", b="2026-10-15"):
        return self.res(unit, "0559999%s" % unit, "جديد", a, b, channel="airbnb", total=total)

    def close(self):
        self.clock = datetime.datetime(2026, 11, 3, 10, 0)


class Targets(PayCase):
    def test_target_is_the_three_months_before_plus_the_step(self):
        self.assertAlmostEqual(self.tgt("102"), 9000 * 1.20, delta=1)
        self.assertAlmostEqual(self.tgt("201"), 9000 * 1.20, delta=1)
        row = db.target("2026-Q4", "102")
        self.assertAlmostEqual(float(row["rev_base"]), 9000.0, delta=1)

    def test_a_unit_with_no_history_takes_the_average_of_the_others(self):
        self.own.append({"listing_id": 301, "name": "C1", "employee": AHOOD})
        score.propose("2027-Q1", D("2026-12-20"))
        row = db.target("2027-Q1", "301")
        self.assertGreater(float(row["rev_target"]), 0)

    def test_owner_may_set_the_target_before_approval_only(self):
        score.propose("2027-Q1", D("2026-12-20"))
        self.assertEqual(db.edit_target("2027-Q1", "102", 0, 0, rev_target=12000), 1)
        self.assertEqual(float(db.target("2027-Q1", "102")["rev_target"]), 12000.0)
        self.assertEqual(db.edit_target("2026-Q4", "102", 0, 0, rev_target=1), 0)      # approved


class Sheet(PayCase):
    def test_pays_only_above_the_target(self):
        self.sell("102", 6800.0)                       # 5,000 above 10,800
                                                        # B1 stays at 9,000: under its target
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        by = {e["employee"]: e for e in s["employees"]}
        self.assertAlmostEqual(by[NORA]["paid"], 5000 * 0.20 * 0.20, delta=0.5)       # 200
        self.assertEqual(by[AHOOD]["paid"], 0.0)
        line = next(u for u in s["units"] if u["unit"] == "102")
        self.assertAlmostEqual(line["over"], 5000.0, delta=1)
        self.assertTrue(s["ready"])

    def test_manager_gets_15_percent_on_top(self):
        db.set_setting("manager", "أسيل")
        self.sell("102", 6800.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertAlmostEqual(s["manager"]["amount"], 30.0, delta=0.1)
        self.assertAlmostEqual(s["total_paid"], 230.0, delta=0.6)

    def test_no_fee_on_record_pays_zero_and_is_flagged(self):
        self.fee.pop("102")
        self.sell("102", 6800.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual(s["total_paid"], 0.0)
        self.assertEqual(s["no_fee_units"], ["A2"])

    def test_ops_warnings_cut_it(self):
        HOST.ops_multiplier = lambda emp, mk: 0.75
        self.sell("102", 6800.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertAlmostEqual(s["employees"][0]["paid"] if s["employees"][0]["employee"] == NORA
                               else s["employees"][1]["paid"], 150.0, delta=0.5)

    def test_blocked_nights_lower_the_target(self):
        db.add_blocked([("201", "2026-10-%02d" % d) for d in range(1, 16)], "test")   # 15 of 31
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        line = next(u for u in s["units"] if u["unit"] == "201")
        self.assertAlmostEqual(line["target"], 10800 * 16 / 31.0, delta=2)
        self.assertGreater(line["over"], 0)

    def test_a_strong_month_never_raises_a_target(self):
        for u in ("101", "102", "201"):
            self.sell(u, 20000.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual(s["season"], 1.0)
        self.assertGreater(s["total_paid"], 0)

    def test_the_open_month_is_shown_but_not_ready(self):
        self.sell("102", 6800.0)
        self.clock = datetime.datetime(2026, 10, 20, 10, 0)
        s = pay.month_sheet("2026-10", self.today())
        self.assertFalse(s["ready"])
        self.assertEqual(s["season"], 1.0)             # no season judgement on a half month
        self.assertFalse(pay.approve_month("2026-10", "owner")[0])

    def test_unapproved_quarter_pays_nothing(self):
        self.sell("102", 50000.0, "2027-01-05", "2027-01-15")
        score.propose("2027-Q1", D("2026-12-20"))
        self.clock = datetime.datetime(2027, 2, 3, 10, 0)
        s = pay.month_sheet("2027-01", self.today())
        self.assertEqual(s["total_paid"], 0.0)
        self.assertFalse(s["ready"])


class SlowSeason(PayCase):
    ORDINARY_OCTOBER = False

    def test_a_slow_month_for_everyone_lowers_every_target(self):
        for u in ("101", "102", "201"):
            self.sell(u, 4000.0)                       # everybody far below their base
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertLess(s["season"], 0.6)
        line = next(u for u in s["units"] if u["unit"] == "201")
        self.assertLess(line["target"], 10800 * 0.6)
        self.assertGreater(line["target"], 0)


class Rating(PayCase):
    def test_low_rating_pays_nothing_for_that_apartment_only(self):
        self.sell("101", 30000.0)
        self.sell("102", 6800.0)
        self.ratings[("102", "2026-10")] = {"avg": 4.5, "n": 4}
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        l102 = next(u for u in s["units"] if u["unit"] == "102")
        self.assertTrue(l102["rating_blocked"])
        self.assertEqual(l102["raw"], 0.0)
        self.assertGreater(next(u for u in s["units"] if u["unit"] == "101")["raw"], 0)

    def test_supervisor_note_lifts_the_block(self):
        self.sell("102", 6800.0)
        self.ratings[("102", "2026-10")] = {"avg": 4.0, "n": 2}
        self.close()
        ok, err, nid = pay.raise_note(NORA, "102", "2026-10", "تسريب من المطور")
        self.assertTrue(ok, err)
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual(s["total_paid"], 0.0)                         # raised is not accepted
        self.assertFalse(s["ready"])                                   # a note is waiting
        self.assertFalse(pay.approve_month("2026-10", "owner")[0])
        self.assertTrue(pay.decide_note(nid, True, "أسيل")[0])
        s = pay.month_sheet("2026-10", self.today())
        self.assertAlmostEqual(s["total_paid"], 200.0, delta=0.6)
        self.assertTrue(s["ready"])

    def test_refused_note_keeps_the_block(self):
        self.sell("102", 6800.0)
        self.ratings[("102", "2026-10")] = {"avg": 4.0, "n": 2}
        self.close()
        _, _, nid = pay.raise_note(NORA, "102", "2026-10", "سبب")
        self.assertTrue(pay.decide_note(nid, False, "أسيل")[0])
        self.assertEqual(pay.month_sheet("2026-10", self.today())["total_paid"], 0.0)
        self.assertFalse(pay.decide_note(nid, True, "أسيل")[0])        # decided once

    def test_note_rules(self):
        self.ratings[("102", "2026-10")] = {"avg": 4.0, "n": 2}
        self.assertFalse(pay.raise_note(AHOOD, "102", "2026-10", "مو شقتي")[0])       # not hers
        self.assertFalse(pay.raise_note(NORA, "102", "2026-10", "  ")[0])             # a reason is required
        self.assertFalse(pay.raise_note(NORA, "101", "2026-10", "ما فيه تقييم نازل")[0])
        self.assertTrue(pay.raise_note(NORA, "102", "2026-10", "عيب مطور")[0])
        self.assertFalse(pay.raise_note(NORA, "102", "2026-10", "مرة ثانية")[0])      # one per unit-month


class Freeze(PayCase):
    def test_an_approved_month_does_not_move(self):
        self.sell("102", 6800.0)
        self.close()
        ok, err = pay.approve_month("2026-10", "owner")
        self.assertTrue(ok, err)
        self.sell("102", 99999.0, "2026-10-16", "2026-10-20")          # a late booking appears
        s = pay.month_sheet("2026-10", self.today())
        self.assertAlmostEqual(s["total_paid"], 200.0, delta=0.6)
        self.assertTrue(s["approval"])
        self.assertFalse(pay.approve_month("2026-10", "owner")[0])


class WhatAnEmployeeSees(PayCase):
    def test_own_amount_and_units_only(self):
        self.sell("102", 6800.0)
        self.sell("201", 30000.0)
        self.close()
        mine = pay.my_money(NORA, "2026-10", self.today())
        self.assertAlmostEqual(mine["amount"], 200.0, delta=0.5)
        self.assertEqual({u["name"] for u in mine["units"]}, {"A1", "A2"})
        flat = repr(mine)
        for word in ("fee", "share", "raw", "paid", "manager", AHOOD):
            self.assertNotIn(word, flat)

    def test_team_view_has_no_money(self):
        self.sell("102", 6800.0)
        self.close()
        rows = pay.team_activity("2026-10", self.today())
        self.assertEqual(set(rows[0]), {"employee", "contacts", "above", "units"})


if __name__ == "__main__":
    unittest.main()
