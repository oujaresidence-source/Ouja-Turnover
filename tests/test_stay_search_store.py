# -*- coding: utf-8 -*-
"""/apartments dated search reads the /monthly calendar store before Hostaway.

Measured live on 2026-10-14: ONE dated search took 274 seconds, because _gw_search
asked Hostaway for ~50 calendars inside the guest's request, on the same 11-per-10s
budget as every bot loop, and its pool threads dropped the guest's "user" priority.

What these lock:
  * a fresh store answers the search with ZERO Hostaway calls
  * a unit missing from the store, or stale, or with a gap, still gets asked live
  * an unavailable night in the store still hides the unit
  * the live fallback carries the caller's Hostaway priority into its threads
Synthetic, no network.
"""
import datetime
import unittest
from unittest import mock

import bot
from tests.test_match_api import _fake_snaps_for_search, _fake_gw_listing_public

CI, CO = "2026-11-01", "2026-11-04"


def nights(avail=1, price=500.0, start=CI, n=3):
    d0 = datetime.date.fromisoformat(start)
    return {(d0 + datetime.timedelta(days=i)).isoformat(): [avail, price, 0] for i in range(n)}


def synced(minutes_ago):
    return (datetime.datetime.now(bot.TZ) - datetime.timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")


class StoreFirst(unittest.TestCase):
    def setUp(self):
        self.snaps = _fake_snaps_for_search(5)
        self._orig = bot._mcal
        self.addCleanup(setattr, bot, "_mcal", self._orig)
        bot._mcal = {"units": {str(i): nights() for i in range(1, 6)},
                     "unit_synced_at": {str(i): synced(5) for i in range(1, 6)}}
        for p in (mock.patch.object(bot, "_gw_visible_snaps", return_value=self.snaps),
                  mock.patch.object(bot, "_gw_listing_public", side_effect=_fake_gw_listing_public)):
            p.start()
            self.addCleanup(p.stop)
        self.calls = []

    def live(self, lid, ci, co):
        self.calls.append(lid)
        return {"available": True, "nights": 3, "total": 999, "avg": 333}

    def search(self):
        with mock.patch.object(bot, "unit_availability_price", side_effect=self.live):
            return bot._gw_search(ci=CI, co=CO)

    def test_fresh_store_means_no_hostaway_calls(self):
        out = self.search()
        self.assertEqual(self.calls, [])
        self.assertEqual(len(out["results"]), 5)
        self.assertFalse(out["avail_error"])
        self.assertEqual(out["results"][0]["est_total"], 1500)   # 3 x 500 from the store

    def test_missing_unit_is_asked_live(self):
        del bot._mcal["units"]["4"]
        out = self.search()
        self.assertEqual(self.calls, [4])
        self.assertEqual(len(out["results"]), 5)

    def test_stale_unit_is_asked_live(self):
        bot._mcal["unit_synced_at"]["2"] = synced(bot.STAY_CAL_MAX_AGE_MIN + 30)
        self.search()
        self.assertEqual(self.calls, [2])

    def test_never_synced_unit_is_asked_live(self):
        del bot._mcal["unit_synced_at"]["3"]
        self.search()
        self.assertEqual(self.calls, [3])

    def test_gap_in_store_is_asked_live(self):
        bot._mcal["units"]["5"].pop("2026-11-02")
        self.search()
        self.assertEqual(self.calls, [5])

    def test_unavailable_night_in_store_hides_the_unit(self):
        bot._mcal["units"]["1"]["2026-11-02"][0] = 0
        out = self.search()
        self.assertEqual(self.calls, [])
        self.assertNotIn(1, [r["id"] for r in out["results"]])

    def test_browse_mode_reads_nothing(self):
        with mock.patch.object(bot, "unit_availability_price", side_effect=self.live), \
             mock.patch.object(bot, "_mcal_quote") as q:
            out = bot._gw_search()
        self.assertTrue(out["browse"])
        q.assert_not_called()
        self.assertEqual(self.calls, [])


class LiveFallbackKeepsGuestPriority(unittest.TestCase):
    def test_pool_threads_see_user_priority(self):
        snaps = _fake_snaps_for_search(6)
        seen = []

        def live(lid, ci, co):
            seen.append(bot.current_priority())
            return {"available": True, "nights": 3, "total": 900, "avg": 300}

        orig = bot._mcal
        self.addCleanup(setattr, bot, "_mcal", orig)
        bot._mcal = {"units": {}, "unit_synced_at": {}}

        def run():
            bot.set_priority("user")
            return bot._gw_search(ci=CI, co=CO)

        import contextvars
        with mock.patch.object(bot, "_gw_visible_snaps", return_value=snaps), \
             mock.patch.object(bot, "_gw_listing_public", side_effect=_fake_gw_listing_public), \
             mock.patch.object(bot, "unit_availability_price", side_effect=live):
            contextvars.copy_context().run(run)
        self.assertEqual(len(seen), 6)
        self.assertEqual(set(seen), {"user"})


if __name__ == "__main__":
    unittest.main()
