# -*- coding: utf-8 -*-
"""Same-day ladder (owner, 2026-11-01): tonight's price for every EMPTY unit drops to
-10% at 3 PM, -20% at 6 PM, -30% at 8 PM Riyadh — every day incl. Thu/Fri, each % off
tonight's ORIGINAL price (never compounding), never below the unit's floor.

Runs the real apply_discount_tier against a fake Hostaway calendar (no network).
Run: python3 -m unittest tests.test_lm_ladder -v
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="ouja-test-lm-"))

import bot  # noqa: E402

NIGHT = "2026-11-05"                      # a Thursday: weekend must use the same ladder
EMPTY, BOOKED = 457230, 437215


class FakeHostaway:
    """Tonight's calendar for two units; PUTs update the stored price like Hostaway does."""

    def __init__(self, price=431):
        self.days = {EMPTY: {"date": NIGHT, "isAvailable": 1, "price": price,
                             "reservationId": None, "note": ""},
                     BOOKED: {"date": NIGHT, "isAvailable": 0, "price": 618,
                              "reservationId": 99, "note": ""}}
        self.puts = []

    def get(self, path, params=None, **_kw):
        lid = int(path.split("/")[2])
        return {"result": [dict(self.days[lid])]}

    def put(self, path, body, _retry=0):
        lid = int(path.split("/")[2])
        self.puts.append((lid, body["price"]))
        self.days[lid]["price"] = body["price"]
        self.days[lid]["note"] = body.get("note", "")
        return {"status": "success"}


class LadderTest(unittest.TestCase):
    PATCHED = ("api_get", "api_put", "get_listings_map", "strategy_enabled",
               "is_unit_skipped", "_pending_lids_for_date", "_lm_floor_for",
               "log_price_change", "_load_discount_state", "_save_discount_state")

    def setUp(self):
        self._orig = {n: getattr(bot, n) for n in self.PATCHED}
        self.fake = FakeHostaway()
        self.floor = 0
        self.state = {}
        bot.api_get = self.fake.get
        bot.api_put = self.fake.put
        bot.get_listings_map = lambda: {EMPTY: "1 MLQ", BOOKED: "HUE 103"}
        bot.strategy_enabled = lambda *a, **k: True
        bot.is_unit_skipped = lambda lid: False
        bot._pending_lids_for_date = lambda d: set()
        bot._lm_floor_for = lambda lid, ctx: {"final_floor": self.floor}
        bot.log_price_change = lambda *a, **k: None
        bot._load_discount_state = lambda: self.state
        bot._save_discount_state = lambda s: self.state.update(s)

    def tearDown(self):
        for n, f in self._orig.items():
            setattr(bot, n, f)

    def _step(self, n):
        pct = {1: bot.DISCOUNT_TIER1_PERCENT, 2: bot.DISCOUNT_TIER2_PERCENT,
               3: bot.DISCOUNT_TIER3_PERCENT}[n]
        return bot.apply_discount_tier(pct, label=bot._lm_tier_label(n), trigger_source="test",
                                       preview_only=False, target_date=NIGHT)

    def test_schedule_is_3_6_8_pm_at_10_20_30(self):
        self.assertEqual((bot.DISCOUNT_TIER1_HOUR, bot.DISCOUNT_TIER2_HOUR,
                          bot.DISCOUNT_TIER3_HOUR), (15, 18, 20))
        self.assertEqual((bot.DISCOUNT_TIER1_PERCENT, bot.DISCOUNT_TIER2_PERCENT,
                          bot.DISCOUNT_TIER3_PERCENT), (10.0, 20.0, 30.0))

    def test_labels_name_the_real_hour(self):
        self.assertEqual([bot._lm_tier_label(n) for n in (1, 2, 3)],
                         ["Tier 1 (3 PM)", "Tier 2 (6 PM)", "Tier 3 (8 PM)"])

    def test_thursday_runs_same_ladder_and_no_extra_step(self):
        thu = datetime(2026, 11, 5, 21, 0, tzinfo=bot.TZ)
        self.assertTrue(bot.is_weekend_today(thu))
        steps = bot._lm_scheduled_steps_for(thu)
        self.assertEqual([(h, m, p) for h, m, p, _l, _s in steps],
                         [(15, 0, 10.0), (18, 0, 20.0), (20, 0, 30.0)])

    def test_steps_drop_from_original_without_compounding(self):
        for n in (1, 2, 3):
            self._step(n)
        self.assertEqual(self.fake.puts, [(EMPTY, 388), (EMPTY, 345), (EMPTY, 302)])

    def test_floor_stops_the_drop_and_never_raises(self):
        self.floor = 350
        for n in (1, 2, 3):
            self._step(n)
        # 388 → 350 (floor beats 345) → 8 PM wants 302, floor holds 350: no write
        self.assertEqual(self.fake.puts, [(EMPTY, 388), (EMPTY, 350)])
        self.assertEqual(self.fake.days[EMPTY]["price"], 350)

    def test_booked_unit_is_never_touched(self):
        for n in (1, 2, 3):
            self._step(n)
        self.assertNotIn(BOOKED, [lid for lid, _p in self.fake.puts])
        self.assertEqual(self.fake.days[BOOKED]["price"], 618)

    def test_late_deploy_never_raises_an_already_lower_price(self):
        self.fake.days[EMPTY]["price"] = 300          # something already dropped tonight
        self.fake.days[EMPTY]["note"] = "ouja-orig:431"
        self._step(2)                                  # -20% of 431 = 345 > 300
        self.assertEqual(self.fake.puts, [])


if __name__ == "__main__":
    unittest.main()
