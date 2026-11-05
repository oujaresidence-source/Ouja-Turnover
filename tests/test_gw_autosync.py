# -*- coding: utf-8 -*-
"""The guest site's unit list refreshes itself once a day.

2026-11-05: 29 units deleted from Hostaway on 2026-10-21 were still on /apartments two weeks
later, because the list only changed when someone pressed the sync button. Every dated search
asked about them, got a 403, and showed «تعذر تحديث التوفر». A daily sync closes that gap; a
safety check keeps a broken Hostaway reply from emptying the site.
Synthetic, no network. Run: python3 -m unittest tests.test_gw_autosync
"""
import asyncio
import re
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import bot

ROOT = Path(__file__).resolve().parents[1]
BOT_SRC = (ROOT / "bot.py").read_text(encoding="utf-8")


def listing(i):
    return {"id": i, "name": "Ouja | %d" % i, "status": "available", "listingImages": [], "price": 300}


class Base(unittest.TestCase):
    def setUp(self):
        saved = dict(bot._gw_cache)
        self.addCleanup(lambda: (bot._gw_cache.clear(), bot._gw_cache.update(saved)))
        bot._gw_cache.clear()
        bot._gw_cache.update({"listings": [{"id": i} for i in range(84)],
                              "synced_at": "2026-10-01T00:00:00+03:00"})
        for p in (mock.patch.object(bot, "_gw_save_cache"), mock.patch.object(bot, "_gw_discover_tags"),
                  mock.patch("builtins.print")):
            p.start()
            self.addCleanup(p.stop)

    def sync(self, n, **kw):
        with mock.patch.object(bot, "_ha_fetch_all_listings", return_value=[listing(i) for i in range(1, n + 1)]):
            return bot._gw_sync(**kw)


class SafetyCheck(Base):
    def test_the_real_cleanup_84_to_55_goes_through(self):
        res = self.sync(55)
        self.assertTrue(res["ok"])
        self.assertEqual(len(bot._gw_cache["listings"]), 55)

    def test_a_short_reply_keeps_the_current_list(self):
        res = self.sync(30)
        self.assertFalse(res["ok"])
        self.assertEqual(len(bot._gw_cache["listings"]), 84, "a short reply must not empty the site")
        self.assertEqual(bot._gw_cache["synced_at"], "2026-10-01T00:00:00+03:00")

    def test_an_empty_reply_keeps_the_current_list(self):
        self.assertFalse(self.sync(0)["ok"])
        self.assertEqual(len(bot._gw_cache["listings"]), 84)

    def test_the_button_is_not_limited_by_the_safety_check(self):
        self.assertTrue(self.sync(30, force=True)["ok"])
        self.assertEqual(len(bot._gw_cache["listings"]), 30)

    def test_a_first_fill_has_nothing_to_protect(self):
        bot._gw_cache["listings"] = []
        self.assertTrue(self.sync(5)["ok"])
        self.assertEqual(len(bot._gw_cache["listings"]), 5)


class DailySchedule(Base):
    def test_due_after_a_day_not_before(self):
        now = datetime.now(bot.TZ)
        bot._gw_cache["synced_at"] = (now - timedelta(hours=25)).isoformat()
        self.assertTrue(bot._gw_autosync_due(now))
        bot._gw_cache["synced_at"] = (now - timedelta(hours=23)).isoformat()
        self.assertFalse(bot._gw_autosync_due(now))

    def test_due_when_the_stored_time_is_missing_or_broken(self):
        now = datetime.now(bot.TZ)
        for bad in (None, "", "not a date", "2026-10-01T00:00:00"):
            bot._gw_cache["synced_at"] = bad
            self.assertTrue(bot._gw_autosync_due(now), bad)

    def run_loop(self, res):
        fake = mock.Mock(return_value=res)
        refresh = mock.Mock()
        with mock.patch.object(bot, "_gw_sync", fake), \
             mock.patch.object(bot, "_monthly_public_request_refresh", refresh, create=True), \
             mock.patch.object(bot, "_HAS_MONTHLY_PUBLIC", True), \
             mock.patch.object(bot, "MONTHLY_ENABLED", True):
            asyncio.run(bot.gw_autosync_loop.coro())
        return fake, refresh

    def test_runs_when_due_with_the_safety_check_on_and_tells_monthly(self):
        fake, refresh = self.run_loop({"ok": True, "count": 55})
        fake.assert_called_once_with()              # no force=True: the safety check applies
        refresh.assert_called_once_with("listing_cache")

    def test_a_refused_reply_does_not_tell_monthly(self):
        fake, refresh = self.run_loop({"ok": False, "error": "short_reply"})
        fake.assert_called_once_with()
        refresh.assert_not_called()

    def test_stays_quiet_when_fresh(self):
        bot._gw_cache["synced_at"] = datetime.now(bot.TZ).isoformat()
        fake, _ = self.run_loop({"ok": True})
        fake.assert_not_called()

    def test_the_switch_turns_it_off(self):
        with mock.patch.object(bot, "GW_AUTOSYNC_ENABLED", False):
            fake, _ = self.run_loop({"ok": True})
        fake.assert_not_called()

    def test_a_crash_inside_does_not_kill_the_loop(self):
        fake = mock.Mock(side_effect=RuntimeError("boom"))
        with mock.patch.object(bot, "_gw_sync", fake):
            asyncio.run(bot.gw_autosync_loop.coro())
        fake.assert_called_once_with()

    def test_the_loop_is_started_at_boot(self):
        self.assertRegex(BOT_SRC, r"gw_autosync_loop\.is_running\(\)")
        self.assertIn("_pending.append(gw_autosync_loop)", BOT_SRC)


if __name__ == "__main__":
    unittest.main()
