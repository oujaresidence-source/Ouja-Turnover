# -*- coding: utf-8 -*-
"""M2 regression — apply_price_changes must never write blind.

The bug: when the pre-write calendar re-verify failed, every change was
applied anyway — and each PUT carries isAvailable:1, which re-opens the night
for sale (can silently unblock a manually-blocked night).

Run: python3 tests/test_apply_price_changes_m2.py
"""
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-m2")
os.makedirs("/tmp/ouja-test-state-m2", exist_ok=True)

import bot  # noqa: E402

D1 = (date.today() + timedelta(days=3)).isoformat()
D2 = (date.today() + timedelta(days=4)).isoformat()
CHANGES = [{"date": D1, "price": 450, "kind": "raise"},
           {"date": D2, "price": 380, "kind": "drop"}]


class ApplyPriceChangesM2Test(unittest.TestCase):
    def setUp(self):
        self._api_get, self._api_put = bot.api_get, bot.api_put
        self._dry = bot.PRICE_APPLY_DRYRUN
        bot.PRICE_APPLY_DRYRUN = False
        self.puts = []

        def fake_put(path, body, _retry=0):
            self.puts.append(body)
            return {"status": "success"}
        bot.api_put = fake_put

    def tearDown(self):
        bot.api_get, bot.api_put = self._api_get, self._api_put
        bot.PRICE_APPLY_DRYRUN = self._dry

    def test_verify_failure_skips_everything(self):
        def boom(path, params=None):
            raise RuntimeError("hostaway 503")
        bot.api_get = boom
        applied, skipped, results = bot.apply_price_changes(1, CHANGES)
        self.assertEqual(applied, 0)
        self.assertEqual(skipped, 2)
        self.assertEqual({r["status"] for r in results}, {"verify_failed"})
        self.assertEqual(self.puts, [], "verify failure must mean ZERO writes")

    def test_blocked_night_is_never_reopened(self):
        def cal(path, params=None):
            return {"status": "success", "result": [
                {"date": D1, "isAvailable": 0, "reservationId": None, "price": 400, "note": None},
                {"date": D2, "isAvailable": 1, "reservationId": None, "price": 400, "note": None}]}
        bot.api_get = cal
        applied, skipped, results = bot.apply_price_changes(1, CHANGES)
        self.assertEqual(applied, 1)
        self.assertEqual(skipped, 1)
        by_date = {r["date"]: r["status"] for r in results}
        self.assertEqual(by_date[D1], "booked", "a blocked night is skipped, not re-opened")
        self.assertEqual(by_date[D2], "applied")
        self.assertEqual(len(self.puts), 1)
        self.assertEqual(self.puts[0]["startDate"], D2)


if __name__ == "__main__":
    unittest.main()
