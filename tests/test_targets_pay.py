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

from targets import book, db, engine, pay, score           # noqa: E402
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
        self.assertAlmostEqual(pay_, 240.0)                  # 4000 x 20% fee x 30% share
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
    """A2 (نورة) and B1 (عهود) each made 9,000 a month in Jul-Sep 2026 -> target 11,700.
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
        self.assertAlmostEqual(self.tgt("102"), 9000 * 1.30, delta=1)
        self.assertAlmostEqual(self.tgt("201"), 9000 * 1.30, delta=1)
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
        self.sell("102", 7700.0)                       # 5,000 above 11,700
                                                        # B1 stays at 9,000: under its target
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        by = {e["employee"]: e for e in s["employees"]}
        self.assertAlmostEqual(by[NORA]["commission"], 5000 * 0.20 * 0.30, delta=0.5)   # 300
        self.assertEqual(by[AHOOD]["paid"], 0.0)
        line = next(u for u in s["units"] if u["unit"] == "102")
        self.assertAlmostEqual(line["over"], 5000.0, delta=1)
        self.assertTrue(s["ready"])

    def test_manager_gets_her_share_on_top(self):
        db.set_setting("manager", "أسيل")
        self.sell("102", 7700.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertAlmostEqual(s["manager"]["share"], 75.0, delta=0.1)
        self.assertAlmostEqual(s["total_paid"], 300.0 + 500.0 + 75.0 + 300.0, delta=0.6)   # commission + prize + her share + her team bonus

    def test_no_fee_on_record_pays_zero_and_is_flagged(self):
        self.fee.pop("102")
        self.sell("102", 7700.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual(s["total_paid"], 0.0)
        self.assertEqual(s["no_fee_units"], ["A2"])

    def test_ops_warnings_cut_it(self):
        HOST.ops_multiplier = lambda emp, mk: 0.75
        self.sell("102", 7700.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertAlmostEqual(s["employees"][0]["paid"] if s["employees"][0]["employee"] == NORA
                               else s["employees"][1]["commission"], 225.0, delta=0.5)

    def test_blocked_nights_lower_the_target(self):
        db.add_blocked([("201", "2026-10-%02d" % d) for d in range(1, 16)], "test")   # 15 of 31
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        line = next(u for u in s["units"] if u["unit"] == "201")
        self.assertAlmostEqual(line["target"], 11700 * 16 / 31.0, delta=2)
        self.assertGreater(line["over"], 0)

    def test_a_strong_month_never_raises_a_target(self):
        for u in ("101", "102", "201"):
            self.sell(u, 20000.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual(s["season"], 1.0)
        self.assertGreater(s["total_paid"], 0)

    def test_the_open_month_is_shown_but_not_ready(self):
        self.sell("102", 7700.0)
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
        self.assertLess(line["target"], 11700 * 0.6)
        self.assertGreater(line["target"], 0)


class Rating(PayCase):
    def test_low_rating_pays_nothing_for_that_apartment_only(self):
        self.sell("101", 30000.0)
        self.sell("102", 7700.0)
        self.ratings[("102", "2026-10")] = {"avg": 4.5, "n": 4}
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        l102 = next(u for u in s["units"] if u["unit"] == "102")
        self.assertTrue(l102["rating_blocked"])
        self.assertEqual(l102["raw"], 0.0)
        self.assertGreater(next(u for u in s["units"] if u["unit"] == "101")["raw"], 0)

    def test_supervisor_note_lifts_the_block(self):
        self.sell("102", 7700.0)
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
        self.assertAlmostEqual(s["total_paid"], 800.0, delta=0.6)        # 300 commission + the 500 prize
        self.assertTrue(s["ready"])

    def test_refused_note_keeps_the_block(self):
        self.sell("102", 7700.0)
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


class Prize(PayCase):
    """The month's prize: first place in the race, once the month has ended."""

    def test_first_place_takes_it_after_the_month_ends(self):
        self.sell("102", 7700.0)                                      # نورة: A2 well above target
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual(s["prize"]["winners"], [])                    # the month is still open
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual(s["prize"]["winners"], [NORA])
        by = {e["employee"]: e for e in s["employees"]}
        self.assertEqual((by[NORA]["rank"], by[NORA]["prize"]), (1, engine.MONTH_PRIZE))
        self.assertEqual(by[AHOOD]["prize"], 0.0)
        self.assertAlmostEqual(by[NORA]["paid"], 300.0 + engine.MONTH_PRIZE, delta=0.6)

    def test_the_manager_share_is_on_commission_not_on_the_prize(self):
        db.set_setting("manager", "أسيل")
        self.sell("102", 7700.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertAlmostEqual(s["manager"]["share"], 300.0 * engine.TARGET_MANAGER_SHARE, delta=0.1)

    def test_no_prize_when_nobody_earned(self):
        self.close()                                                   # an ordinary month: all under target
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual((s["prize"]["winners"], s["prize_paid"], s["total_paid"]), ([], 0.0, 0.0))

    def test_first_place_on_a_rating_stopped_apartment_wins_nothing(self):
        self.sell("102", 7700.0)
        self.ratings[("102", "2026-10")] = {"avg": 4.0, "n": 2}
        self.close()
        self.assertEqual(pay.month_sheet("2026-10", self.today())["prize"]["winners"], [])

    def test_it_passes_down_when_first_place_earned_nothing(self):
        # عهود's B1 sells a lot but its rating stops it: she is first in the race with no commission.
        self.sell("201", 20000.0)
        self.ratings[("201", "2026-10")] = {"avg": 4.0, "n": 2}
        self.sell("102", 7700.0)                                       # نورة earns, in second place
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        by = {e["employee"]: e for e in s["employees"]}
        self.assertEqual((by[AHOOD]["rank"], by[AHOOD]["commission"]), (1, 0.0))
        self.assertEqual(s["prize"]["winners"], [NORA])
        self.assertEqual((by[NORA]["prize"], by[AHOOD]["prize"]), (engine.MONTH_PRIZE, 0.0))

    def test_the_race_an_employee_sees_has_names_and_places_but_no_money(self):
        self.sell("102", 7700.0)
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        race = pay.my_day(AHOOD, "2026-10", self.today())["race"]
        self.assertEqual((race["place"], race["of"], race["prize"]), (2, 2, engine.MONTH_PRIZE))
        self.assertGreater(race["to_first"], 0)
        self.assertEqual([r["employee"] for r in race["board"]], [NORA, AHOOD])
        for r in race["board"]:
            self.assertEqual(set(r), {"employee", "place", "pct", "me"})


class ManagerBonus(PayCase):
    """Her own bonus: on how many apartments passed their target, once the month has ended."""

    def setUp(self):
        super().setUp()
        db.set_setting("manager", "أسيل")

    def test_steps(self):
        self.assertEqual(engine.manager_bonus(2, 10), (0.0, 0.2))
        self.assertEqual(engine.manager_bonus(3, 10)[0], 300.0)
        self.assertEqual(engine.manager_bonus(4, 10)[0], 700.0)
        self.assertEqual(engine.manager_bonus(0, 0), (0.0, 0.0))

    def test_one_of_three_apartments_above_is_the_first_step(self):
        self.sell("102", 7700.0)                                       # 1 of 3 = 33%
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual(s["manager"]["bonus"], 0.0)                   # not before the month ends
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertEqual((s["manager"]["bonus"], s["manager"]["share"]), (300.0, 75.0))
        self.assertAlmostEqual(s["manager"]["amount"], 375.0, delta=0.1)
        self.assertAlmostEqual(s["total_paid"], 300.0 + 500.0 + 375.0, delta=0.6)

    def test_two_of_three_is_the_top_step(self):
        self.sell("102", 7700.0)
        self.sell("201", 7700.0)
        self.close()
        self.assertEqual(pay.month_sheet("2026-10", self.today())["manager"]["bonus"], 700.0)

    def test_no_manager_named_no_manager_money(self):
        db.set_setting("manager", "")
        self.sell("102", 7700.0)
        self.close()
        s = pay.month_sheet("2026-10", self.today())
        self.assertIsNone(s["manager"])
        self.assertAlmostEqual(s["total_paid"], 800.0, delta=0.6)

    def test_her_view_says_how_many_apartments_are_left_to_each_step(self):
        self.sell("102", 7700.0)
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        v = pay.manager_view("2026-10", self.today())
        self.assertEqual((v["above"], v["units"]), (1, 3))
        self.assertEqual([(x["sar"], x["units"], x["left"]) for x in v["steps"]], [(300.0, 1, 0), (700.0, 2, 1)])
        self.assertEqual(v["share"], 75.0)
        self.assertFalse({"raw", "paid", "employees"} & set(v))


class Freeze(PayCase):
    def test_an_approved_month_does_not_move(self):
        self.sell("102", 7700.0)
        self.close()
        ok, err = pay.approve_month("2026-10", "owner")
        self.assertTrue(ok, err)
        self.sell("102", 99999.0, "2026-10-16", "2026-10-20")          # a late booking appears
        s = pay.month_sheet("2026-10", self.today())
        self.assertAlmostEqual(s["total_paid"], 800.0, delta=0.6)
        self.assertTrue(s["approval"])
        self.assertFalse(pay.approve_month("2026-10", "owner")[0])


class WhatAnEmployeeSees(PayCase):
    def test_own_amount_and_units_only(self):
        self.sell("102", 7700.0)
        self.sell("201", 30000.0)
        self.close()
        mine = pay.my_money(NORA, "2026-10", self.today())
        self.assertAlmostEqual(mine["amount"], 300.0, delta=0.5)          # عهود was first that month
        self.assertEqual({u["name"] for u in mine["units"]}, {"A1", "A2"})
        flat = repr(mine)
        for word in ("fee", "share", "raw", "paid", "manager", AHOOD):
            self.assertNotIn(word, flat)

    def test_team_view_has_no_money(self):
        self.sell("102", 7700.0)
        self.close()
        rows = pay.team_activity("2026-10", self.today())
        self.assertEqual(set(rows[0]), {"employee", "contacts", "today", "above", "units"})


if __name__ == "__main__":
    unittest.main()


class MyDay(PayCase):
    """«يومي»: the same sheet, said as "what do I do now and what is it worth to me"."""

    def test_money_now_and_what_is_reachable(self):
        self.sell("102", 7700.0)                                    # A2: 5,000 above its target
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)         # the month is still open
        d = pay.my_day(NORA, "2026-10", self.today())
        self.assertTrue(d["live"])
        self.assertAlmostEqual(d["amount"], 300.0, delta=0.6)
        self.assertGreaterEqual(d["potential"], d["amount"])
        a2 = next(u for u in d["units"] if u["unit"] == "102")
        self.assertAlmostEqual(a2["mine"], 300.0, delta=0.6)
        self.assertGreater(a2["night_value"], 0)                    # an extra night is worth riyals to her
        self.assertEqual(d["nearest"][0], "102")                    # already above target: pays today
        self.assertFalse({AHOOD} & {u["name"] for u in d["units"]})
        self.assertNotIn("201", [u["unit"] for u in d["units"]])

    def test_a_new_booking_shows_what_it_added_to_me(self):
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        self.res("102", "0557770001", "سارة محمد", "2026-10-05", "2026-10-15", channel="airbnb",
                 total=7700.0, created="2026-10-28")
        d = pay.my_day(NORA, "2026-10", self.today())
        win = d["wins"][0]
        self.assertEqual((win["unit_name"], win["guest"], win["nights"]), ("A2", "سارة", 10))
        self.assertAlmostEqual(win["mine"], 300.0, delta=0.6)
        self.assertAlmostEqual(sum(w["mine"] for w in d["wins"]), d["amount"], delta=0.6)   # they add up

    def test_a_low_rating_makes_the_unit_worth_nothing_to_chase(self):
        self.sell("102", 7700.0)
        self.ratings[("102", "2026-10")] = {"avg": 4.0, "n": 2}
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        d = pay.my_day(NORA, "2026-10", self.today())
        a2 = next(u for u in d["units"] if u["unit"] == "102")
        self.assertEqual((a2["mine"], a2["night_value"], a2["reachable"]), (0.0, 0.0, False))

    def test_mission_and_streak_count_logged_messages(self):
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        for i, day in enumerate(("2026-10-28", "2026-10-29", "2026-10-30", "2026-10-30")):
            db.insert_contact("k%d" % i, "ضيف", NORA, day + "T09:00:00", "2026-Q4", "102", day, 1, None)
        m = pay.my_day(NORA, "2026-10", self.today())["mission"]
        self.assertEqual((m["today"], m["streak"]), (2, 3))
        self.clock = datetime.datetime(2026, 10, 31, 8, 0)          # nothing yet today: not broken
        self.assertEqual(pay.my_day(NORA, "2026-10", self.today())["mission"]["streak"], 3)

    def test_record_keeps_past_months(self):
        self.sell("102", 7700.0)
        self.close()
        pay.approve_month("2026-10", "owner")
        rec = pay.my_day(NORA, "2026-11", self.today())["record"]
        octo = next(m for m in rec["months"] if m["month"] == "2026-10")
        self.assertTrue(octo["final"])
        self.assertAlmostEqual(octo["amount"], 800.0, delta=0.6)
        self.assertEqual(rec["best"]["month"], "2026-10")
        self.assertAlmostEqual(rec["earned"], sum(m["amount"] for m in rec["months"]), delta=0.01)

    def test_a_closed_month_has_no_mission(self):
        self.close()
        d = pay.my_day(NORA, "2026-10", self.today())
        self.assertFalse(d["live"])
        self.assertEqual(d["wins"], [])


class RescueByRevenue(PayCase):
    """The manager's rescue list is on the measure that pays: revenue against the target.
    (2026-11-15: on the old weighted occupancy every row read 0% and «واقفة بسبب السعر».)"""

    def test_worst_first_and_only_units_under_their_target(self):
        self.sell("102", 7700.0)                                       # A2 is above: not on the list
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        rows = score.rescue("2026-10", self.today())
        self.assertEqual({r["name"] for r in rows}, {"A1", "B1"})
        self.assertEqual(rows, sorted(rows, key=lambda r: r["pct"]))
        for r in rows:
            self.assertEqual(set(r), {"unit", "name", "employee", "revenue", "target", "gap", "pct", "empty"})
            self.assertEqual(r["gap"], r["target"] - r["revenue"])
            self.assertLess(r["pct"], 1.0)

    def test_a_unit_with_no_revenue_target_is_not_listed(self):
        db.execute("UPDATE tg_targets SET rev_target=0 WHERE quarter='2026-Q4' AND unit='201'")
        self.clock = datetime.datetime(2026, 10, 30, 10, 0)
        self.assertNotIn("B1", [r["name"] for r in score.rescue("2026-10", self.today())])


class LastBooking(PayCase):
    """Each guest on the list carries the booking they last had with us, so the employee can
    open it in Hostaway and read the conversation before writing."""

    def test_the_last_finished_stay_and_its_number(self):
        self.clock = datetime.datetime(2026, 11, 15, 10, 0)
        rid = self.res("102", self.phone(3), "ضيف3 فلان", "2026-09-10", "2026-09-13", channel="airbnb")
        items = book.call_list(NORA, self.today(), limit=0)["items"]
        it = next(i for i in items if i["_key"] == engine.phone_key(self.phone(3)))
        self.assertEqual(it["last"], {"booking": rid, "arrival": "2026-09-10", "departure": "2026-09-13",
                                      "nights": 3, "channel": "airbnb", "unit_name": "A2"})
        pub = book.public_items({"items": [it]})["items"][0]
        self.assertNotIn("_key", pub)
        self.assertFalse({"phone", "phone_key", "res_id"} & set(pub["last"]))

    def test_no_past_stay_no_booking(self):
        self.assertIsNone(book.last_stay([]))


class PeopleIMessaged(PayCase):
    """An employee can go back to everyone they messaged — not only the fresh ones."""

    def test_old_and_new_contacts_with_the_guests_last_booking(self):
        self.clock = datetime.datetime(2026, 11, 15, 10, 0)
        rid = self.res("102", self.phone(3), "ضيف3 فلان", "2026-09-10", "2026-09-13", channel="airbnb")
        k = engine.phone_key(self.phone(3))
        old = db.insert_contact(k, "ضيف3 فلان", NORA, "2026-09-20T09:00:00", "2026-Q3", "102", "2026-09-25", 1, None)
        self.assertTrue(book.set_outcome(NORA, old, "declined")[0])
        new = db.insert_contact(engine.phone_key(self.phone(4)), "ضيف4 فلان", NORA, "2026-11-14T09:00:00", "2026-Q4", "102", "2026-11-20", 1, None)
        rows = book.open_contacts(NORA, self.today())
        self.assertEqual([(r["id"], r["open"]) for r in rows], [(new, True), (old, False)])
        self.assertEqual(rows[1]["last"]["booking"], rid)
        self.assertEqual((rows[1]["unit_name"], rows[1]["night"], rows[1]["outcome"]), ("A2", "2026-09-25", "declined"))
        self.assertFalse({"phone", "phone_key", "_key"} & set(rows[1]))

    def test_only_my_own(self):
        self.clock = datetime.datetime(2026, 11, 15, 10, 0)
        db.insert_contact("kx", "ضيف", AHOOD, "2026-11-14T09:00:00", "2026-Q4", "201", "2026-11-20", 1, None)
        self.assertEqual(book.open_contacts(NORA, self.today()), [])
