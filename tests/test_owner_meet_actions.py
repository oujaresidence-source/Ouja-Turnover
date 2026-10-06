# -*- coding: utf-8 -*-
"""The action engine, the forecast and the discount-stack warning (gate G9, spec §8).

Run: python3 -m unittest tests.test_owner_meet_actions
"""
import datetime
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from owner_meet import engine  # noqa: E402

RULES = json.loads((ROOT / "owner_meet" / "rules.seed.json").read_text(encoding="utf-8"))
TODAY = datetime.date(2026, 10, 6)
CLEAN = {"rating": 4.9, "bookings_365": 80, "funnel": None, "peer_funnel": None, "income_tone": "top",
         "open14": 3, "maint_open": 0, "rr_open": [], "permit": {"days_left": 200, "end_date": "2027-04-24"},
         "min_price": 450, "in_test_group": False}


def keys(**kw):
    ctx = dict(CLEAN, **kw)
    return [a["key"] for a in engine.actions(ctx, RULES, TODAY)]


class Triggers(unittest.TestCase):
    def test_a_healthy_unit_gets_no_action(self):
        self.assertEqual(keys(), [])

    def test_each_trigger_alone(self):
        f, pf = {"ctr100": 5.0, "conv": 1.0}, {"ctr100": 11.0, "conv": 1.5, "ctr_p25": 7.0, "conv_p25": 1.2}
        self.assertEqual(keys(rating=4.74), ["rate"])
        self.assertEqual(keys(rating=4.75), [], "4.75 exactly is not below the target")
        self.assertEqual(keys(bookings_365=24), ["new"])
        self.assertEqual(keys(funnel=dict(f, conv=1.6), peer_funnel=pf), ["ctr"])
        self.assertEqual(keys(funnel=dict(f, ctr100=12.0), peer_funnel=pf, income_tone="low"), ["page"])
        self.assertEqual(keys(funnel=dict(f, ctr100=12.0), peer_funnel=pf, income_tone="top"), [],
                         "page needs income below the peer median too")
        self.assertEqual(keys(open14=13), ["pace"])
        self.assertEqual(keys(open14=12), [])
        self.assertEqual(keys(maint_open=2), ["maint_open"])
        self.assertEqual(keys(rr_open=[{"deadline": {"date": "2026-10-11"}}]), ["rr_open"])
        self.assertEqual(keys(permit=None), ["permit"])
        self.assertEqual(keys(permit={"days_left": 90, "end_date": "2027-01-04"}), ["permit"])
        self.assertEqual(keys(permit={"days_left": 91, "end_date": "2027-01-05"}), [])
        self.assertEqual(keys(min_price=None), ["floor"])
        self.assertEqual(keys(in_test_group=True), ["test"])

    def test_order_roles_and_owner_side(self):
        acts = engine.actions(dict(CLEAN, rating=4.5, open14=14, permit=None, min_price=None, in_test_group=True),
                              RULES, TODAY)
        self.assertEqual([a["key"] for a in acts], ["rate", "pace", "permit", "floor", "test"])
        self.assertEqual({a["key"]: a["side"] for a in acts}["permit"], "owner")
        self.assertEqual({a["key"]: a["role"] for a in acts}["rate"], "مدير الحساب")
        self.assertTrue(all(a["evidence"] and a["due"] for a in acts))

    def test_the_rr_due_is_the_earliest_aircover_deadline(self):
        acts = engine.actions(dict(CLEAN, rr_open=[{"deadline": {"date": "2026-10-20"}}, {"deadline": {"date": "2026-10-11"}}]),
                              RULES, TODAY)
        self.assertEqual(acts[0]["due"], "2026-10-11")

    def test_group_b_is_never_mentioned_to_the_owner(self):
        acts = engine.actions(dict(CLEAN, in_test_group=True), RULES, TODAY)
        self.assertNotIn("B", acts[0]["owner_text"] + acts[0]["evidence"])
        self.assertIn("B", acts[0]["internal_note"])


class Headline(unittest.TestCase):
    def test_weakness_order_rating_then_funnel_then_bands(self):
        u = {"rating": {"value": 4.6}, "actions": [{"key": "ctr"}], "peers": {"occupancy": {"tone": "low"}}}
        self.assertEqual(engine.weakness(u)[0], "rating")
        u["rating"]["value"] = 4.9
        self.assertEqual(engine.weakness(u)[0], "ctr")
        u["actions"] = []
        self.assertEqual(engine.weakness(u)[0], "occupancy")

    def test_headline_tones(self):
        top = {"peers": {"income": {"tone": "top", "pct10": 80, "scope": "peers"}}, "rating": {"value": 4.6}}
        self.assertIn("أعلى من 80٪", "".join(t for t, _ in engine.headline(top)))
        self.assertIn("التقييم", "".join(t for t, _ in engine.headline(top)))
        low = {"peers": {"income": {"tone": "low", "scope": "portfolio"}}, "rating": {"value": 4.9}}
        self.assertIn("أقل من أغلب شققنا", "".join(t for t, _ in engine.headline(low)))
        self.assertIsNone(engine.headline(top, degraded=True))


class Forecast(unittest.TestCase):
    def test_fewer_than_three_full_months_means_no_forecast(self):
        self.assertIsNone(engine.forecast([1000.0, 2000.0], None, None, set(), RULES, False))
        self.assertIsNone(engine.forecast([1000.0, None, 2000.0], None, None, set(), RULES, False))

    def test_pace_base_is_the_sum_of_the_last_three_full_months(self):
        fc = engine.forecast([1000.0, 2000.0, 3000.0], None, None, set(), RULES, False)
        self.assertEqual((fc["base"], fc["target"], fc["method"]), (6000.0, 6000.0, "pace"))

    def test_seasonal_base_scales_last_years_quarter_by_this_years_pace(self):
        fc = engine.forecast([1000.0, 1000.0, 1000.0], [500.0, 500.0, 500.0], [800.0, 900.0, 1000.0], set(), RULES, False)
        self.assertEqual((fc["base"], fc["method"]), (5400.0, "seasonal"))

    def test_uplifts_add_and_are_capped(self):
        fc = engine.forecast([1000.0] * 3, None, None, {"rate", "ctr"}, RULES, True)
        self.assertEqual([i["key"] for i in fc["uplifts"]], ["rate", "ctr", "season"])
        self.assertEqual((fc["total_pct"], fc["target"]), (9.0, 3270.0))
        fc = engine.forecast([1000.0] * 3, None, None, {"rate", "ctr", "page", "pace", "test"}, RULES, True)
        self.assertEqual((fc["total_pct"], fc["capped"], fc["target"]), (15.0, True, 3450.0))
        self.assertEqual(engine.forecast([1000.0] * 3, None, None, {"maint_open", "floor"}, RULES, False)["total_pct"], 0)


class DiscountStack(unittest.TestCase):
    def test_worst_case_stacks_one_of_with_trg_and_nonref(self):
        st = engine.discount_stack({"weekly_current": 0.10, "early_bird_current": 0.10, "last_minute_current": 0.01,
                                    "trg_eligible": True, "nonref_eligible": True}, RULES)
        self.assertEqual(st["one_of"], 0.10)
        self.assertAlmostEqual(st["combined"], 1 - 0.9 * 0.85 * 0.9, places=4)
        self.assertTrue(st["warn"])
        st = engine.discount_stack({"weekly_current": 0.10, "trg_eligible": False, "nonref_eligible": False}, RULES)
        self.assertFalse(st["warn"])


class Funnel(unittest.TestCase):
    def test_per_ten_thousand(self):
        f = engine.funnel({"search_to_booking": 0.0023, "view_to_booking": 0.0182})
        self.assertEqual((f["views"], f["bookings"], f["ctr100"], f["conv"]), (1264, 23.0, 12.6, 1.82))
        self.assertIsNone(engine.funnel({"search_to_booking": None, "view_to_booking": 0.01}))

    def test_peer_funnel_has_no_count_and_falls_back(self):
        rows = [{"airbnb_id": str(i), "bedrooms": 2, "search_to_booking": 0.001 * i, "view_to_booking": 0.01} for i in range(1, 9)]
        pf, inn = engine.funnel_peers(rows, rows[0])
        self.assertEqual(pf["scope"], "peers")
        self.assertNotIn("n", pf)
        self.assertEqual(inn["n"], 7)
        pf, inn = engine.funnel_peers(rows, dict(rows[0], bedrooms=3, airbnb_id="x"))
        self.assertEqual(pf["scope"], "portfolio")


if __name__ == "__main__":
    unittest.main()
