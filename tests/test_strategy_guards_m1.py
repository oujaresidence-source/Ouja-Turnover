# -*- coding: utf-8 -*-
"""M1 regression — the strategy loop must never write an unguarded price.

The bug: _run_strategy_unit raw-api_put prices with no zero guard, no floor
check and no read-back. _strategy_price(0, …) == 0 is reachable (base resolves
to 0 on a cold cache) → a 0-SAR night could be PUT to Hostaway.

Run: python3 tests/test_strategy_guards_m1.py
"""
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-m1")
os.makedirs("/tmp/ouja-test-state-m1", exist_ok=True)

import bot  # noqa: E402

LID = 4242
TOMORROW = (date.today() + timedelta(days=1)).isoformat()

FACTORS = {"month_index": {}, "dom_index": {}, "dow_index": {},
           "overall_adr": 0, "unit_adr": {}}


def _calendar_get(price=400):
    def api_get(path, params=None):
        return {"status": "success",
                "result": [{"date": TOMORROW, "isAvailable": 1,
                            "reservationId": None, "price": price, "note": None}]}
    return api_get


class StrategyGuardsM1Test(unittest.TestCase):
    def setUp(self):
        self._api_get, self._api_put = bot.api_get, bot.api_put
        self._dry = bot.PRICE_APPLY_DRYRUN
        self._floor = dict(bot._pe_floor_overrides)
        self._enabled = bot.strategy_enabled
        bot.strategy_enabled = lambda name, lid=None: True
        bot.PRICE_APPLY_DRYRUN = False
        bot._pe_floor_overrides.clear()
        self.puts = []

        def fake_put(path, body, _retry=0):
            self.puts.append(body)
            return {"status": "success"}
        bot.api_put = fake_put

    def tearDown(self):
        bot.api_get, bot.api_put = self._api_get, self._api_put
        bot.PRICE_APPLY_DRYRUN = self._dry
        bot._pe_floor_overrides.clear(); bot._pe_floor_overrides.update(self._floor)
        bot.strategy_enabled = self._enabled

    def _strat(self, base, cur=400):
        return {"name": "T", "base": base, "active": True, "changes_total": 0,
                "dates": {TOMORROW: {"start": cur, "cur": cur, "booked": False, "changes": 0,
                                     "last": ""}}}

    def test_zero_base_never_writes_a_zero_price(self):
        bot.api_get = _calendar_get()
        strat = self._strat(base=0)          # cold cache → _strategy_price → 0
        bot._run_strategy_unit(LID, strat, FACTORS, date.today())
        self.assertEqual(self.puts, [], "a 0-SAR price must NEVER reach Hostaway")

    def test_below_floor_never_writes(self):
        bot.api_get = _calendar_get()
        bot._pe_floor_overrides[LID] = 500
        strat = self._strat(base=300)        # want ≈ 240–300 < floor 500
        bot._run_strategy_unit(LID, strat, FACTORS, date.today())
        self.assertEqual(self.puts, [], "below-floor writes must be skipped")

    def test_legit_price_writes_with_orig_note_and_readback(self):
        # calendar GET returns live price 400; want will be ~588 (base 600 stepped)
        bot.api_get = _calendar_get(price=400)
        strat = self._strat(base=600, cur=400)
        bot._run_strategy_unit(LID, strat, FACTORS, date.today())
        self.assertEqual(len(self.puts), 1)
        body = self.puts[0]
        self.assertGreater(body["price"], 0)
        self.assertTrue(str(body.get("note", "")).startswith("ouja-orig:"),
                        "the revert note must be preserved through _pe_apply_night")

    def test_dry_run_changes_nothing_but_still_tracks(self):
        bot.PRICE_APPLY_DRYRUN = True
        bot.api_get = _calendar_get(price=400)
        strat = self._strat(base=600, cur=400)
        bot._run_strategy_unit(LID, strat, FACTORS, date.today())
        self.assertEqual(self.puts, [], "dry-run must not write")
        self.assertEqual(strat["changes_total"], 1, "dry-run still simulates the move")


if __name__ == "__main__":
    unittest.main()
