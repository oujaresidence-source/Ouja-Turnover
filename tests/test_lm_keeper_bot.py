# -*- coding: utf-8 -*-
"""Same-day price keeper — bot.py wiring (lm_keeper_tick, alerts, report) against a fake
Hostaway calendar. No network, no Discord.
Run: python3 -m unittest tests.test_lm_keeper_bot -v
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="ouja-test-lmk-"))

import bot  # noqa: E402

NIGHT = "2026-11-05"
EMPTY, BOOKED, OTHER = 457230, 437215, 457287


def at(h, m=0):
    return datetime(2026, 11, 5, h, m, tzinfo=bot.TZ)


class FakeHostaway:
    """Tonight's calendar per unit; PUTs update the stored price like Hostaway does."""

    def __init__(self):
        self.days = {EMPTY: {"date": NIGHT, "isAvailable": 1, "price": 431, "reservationId": None, "note": ""},
                     BOOKED: {"date": NIGHT, "isAvailable": 0, "price": 618, "reservationId": 99, "note": ""},
                     OTHER: {"date": NIGHT, "isAvailable": 1, "price": 500, "reservationId": None, "note": ""}}
        self.puts, self.gets = [], []
        self.fail_puts = 0          # next N PUTs raise
        self.ignore_puts = 0        # next N PUTs "succeed" but the price doesn't change

    def get(self, path, params=None, **_kw):
        lid = int(path.split("/")[2])
        self.gets.append(lid)
        return {"result": [dict(self.days[lid])]}

    def put(self, path, body, _retry=0):
        lid = int(path.split("/")[2])
        if self.fail_puts:
            self.fail_puts -= 1
            raise RuntimeError("Hostaway 500")
        self.puts.append((lid, body["price"]))
        if self.ignore_puts:
            self.ignore_puts -= 1
            return {"status": "success"}
        self.days[lid]["price"] = body["price"]
        self.days[lid]["note"] = body.get("note", "")
        return {"status": "success"}


class _Base(unittest.TestCase):
    PATCHED = ("api_get", "api_put", "get_listings_map", "_strategy_toggles", "is_unit_skipped",
               "_pending_lids_for_date", "lm_minimums", "log_price_change", "_pe_floor_overrides",
               "DISCOUNT_DRY_RUN", "DISCOUNT_FLOOR", "is_discount_paused")

    def setUp(self):
        self._orig = {n: getattr(bot, n) for n in self.PATCHED}
        self.fake = FakeHostaway()
        self.pending = set()
        self.mins = {}
        bot.api_get = self.fake.get
        bot.api_put = self.fake.put
        bot.get_listings_map = lambda: {EMPTY: "1 MLQ", BOOKED: "HUE 103", OTHER: "A5 MLQ"}
        bot._strategy_toggles = {"global": {}, "by_unit": {}}
        bot.is_unit_skipped = lambda lid: False
        bot._pending_lids_for_date = lambda d: set(self.pending)
        bot.lm_minimums = lambda now=None, refresh=False: self.mins
        bot.log_price_change = lambda *a, **k: None
        bot._pe_floor_overrides = {}
        bot.DISCOUNT_DRY_RUN = False
        bot.DISCOUNT_FLOOR = 0
        bot.is_discount_paused = lambda: False
        try:
            os.remove(bot._state_path(bot.LM_KEEPER_STATE_FILE))
        except FileNotFoundError:
            pass
        bot._save_hashes.clear()

    def tearDown(self):
        for n, f in self._orig.items():
            setattr(bot, n, f)

    def tick(self, h, m=0):
        rec, alerts = bot.lm_keeper_tick(at(h, m))
        return rec, alerts

    def price(self, lid):
        return self.fake.days[lid]["price"]


class KeeperTest(_Base):
    def test_nothing_before_3pm(self):
        self.tick(14, 55)
        self.assertEqual(self.fake.puts, [])
        self.assertEqual(self.fake.gets, [])

    def test_steps_from_original_without_compounding(self):
        self.tick(15, 0)
        self.assertEqual(self.price(EMPTY), 388)
        self.tick(18, 0)
        self.assertEqual(self.price(EMPTY), 345)
        self.tick(20, 0)
        self.assertEqual(self.price(EMPTY), 302)

    def test_restart_mid_evening_converges(self):
        self.tick(20, 30)                                  # first tick ever, already in the 8 PM step
        self.assertEqual(self.price(EMPTY), 302)
        self.assertEqual(self.price(OTHER), 350)

    def test_after_a_restart_the_original_comes_from_the_note(self):
        self.tick(15, 0)                                   # 431 → 388, note ouja-orig:431
        os.remove(bot._state_path(bot.LM_KEEPER_STATE_FILE))
        bot._save_hashes.clear()
        self.tick(18, 5)                                   # fresh state: original must still be 431
        self.assertEqual(self.price(EMPTY), 345)

    def test_failed_write_is_fixed_next_tick(self):
        self.fake.fail_puts = 1
        rec, _ = self.tick(15, 0)
        self.assertEqual(rec["units"][str(EMPTY)]["status"], "error")
        self.tick(15, 5)
        self.assertEqual(self.price(EMPTY), 388)

    def test_write_that_does_not_stick_is_retried(self):
        self.fake.ignore_puts = 1
        rec, _ = self.tick(15, 0)
        self.assertEqual(rec["units"][str(EMPTY)]["reason"], "not_stuck")
        self.tick(15, 5)
        self.assertEqual(self.price(EMPTY), 388)

    def test_pending_guest_waits_then_drops(self):
        self.pending = {EMPTY}
        rec, _ = self.tick(15, 0)
        self.assertEqual(self.price(EMPTY), 431)
        self.assertEqual(rec["units"][str(EMPTY)]["status"], "waiting")
        self.pending = set()
        self.tick(15, 5)
        self.assertEqual(self.price(EMPTY), 388)

    def test_minimum_stops_the_drop(self):
        self.mins = {str(EMPTY): {"min": 350, "n": 9, "median": 420}}
        self.tick(20, 0)
        self.assertEqual(self.price(EMPTY), 350)

    def test_manual_floor_wins_when_higher(self):
        self.mins = {str(EMPTY): {"min": 300, "n": 9, "median": 420}}
        bot._pe_floor_overrides = {EMPTY: 380}
        self.tick(20, 0)
        self.assertEqual(self.price(EMPTY), 380)

    def test_never_raises_a_lower_price(self):
        self.fake.days[EMPTY]["price"] = 300
        self.fake.days[EMPTY]["note"] = "ouja-orig:431"
        self.tick(18, 0)                                   # target 345 > 300
        self.assertNotIn(EMPTY, [lid for lid, _p in self.fake.puts])

    def test_booked_unit_untouched(self):
        self.tick(20, 0)
        self.assertNotIn(BOOKED, [lid for lid, _p in self.fake.puts])
        self.assertEqual(self.price(BOOKED), 618)

    def test_confirmed_unit_not_reread_in_same_step(self):
        self.tick(15, 0)
        n = self.fake.gets.count(EMPTY)
        self.tick(15, 5)
        self.tick(15, 10)
        self.assertEqual(self.fake.gets.count(EMPTY), n)

    def test_dry_run_never_writes_and_never_confirms(self):
        bot.DISCOUNT_DRY_RUN = True
        rec, _ = self.tick(15, 0)
        self.assertEqual(self.fake.puts, [])
        self.assertEqual(rec["units"][str(EMPTY)]["status"], "dry_run")
        bot.DISCOUNT_DRY_RUN = False
        self.tick(15, 5)                                   # leaving dry-run: drops on the next tick
        self.assertEqual(self.price(EMPTY), 388)

    def test_unit_switched_off_is_skipped(self):
        bot._strategy_toggles["by_unit"][str(EMPTY)] = {"last-minute": False}
        rec, _ = self.tick(15, 0)
        self.assertEqual(self.price(EMPTY), 431)
        self.assertEqual(rec["units"][str(EMPTY)]["status"], "skipped")

    def test_paused_does_nothing(self):
        bot.is_discount_paused = lambda: True
        self.tick(15, 0)
        self.assertEqual(self.fake.puts, [])

    def test_first_drop_time_is_recorded(self):
        rec, _ = self.tick(15, 0)
        self.assertTrue(rec["units"][str(EMPTY)]["first_drop_at"].startswith("2026-11-05T15:00"))
        self.assertTrue(rec["units"][str(EMPTY)]["seen_empty"])
        self.assertNotIn("seen_empty", rec["units"][str(BOOKED)])


class AlertTest(_Base):
    def test_one_alert_after_30_minutes(self):
        self.fake.fail_puts = 99
        _, alerts = self.tick(15, 0)
        self.assertEqual(alerts, [])
        _, alerts = self.tick(15, 25)
        self.assertEqual(alerts, [])
        _, alerts = self.tick(15, 30)
        self.assertEqual([a["lid"] for a in alerts], [str(EMPTY), str(OTHER)])
        _, alerts = self.tick(15, 35)
        self.assertEqual(alerts, [])                       # never twice in one night
        _, alerts = self.tick(18, 30)
        self.assertEqual(alerts, [])

    def test_no_alert_when_fine(self):
        self.tick(15, 0)
        _, alerts = self.tick(15, 40)
        self.assertEqual(alerts, [])


class ReportTest(_Base):
    def test_report_text_counts_bookings_after_the_drop(self):
        self.tick(20, 0)                                   # EMPTY 431 → 302 at 20:00
        rows = [{"listingMapId": EMPTY, "arrivalDate": NIGHT, "reservationDate": "2026-11-05 17:45:00",
                 "totalPrice": 302, "nights": 1, "status": "new"}]
        orig_fetch = bot.fetch_reservations_window
        bot.fetch_reservations_window = lambda s, e, pad_days=45: rows
        try:
            txt = bot.lm_report_text(NIGHT)
        finally:
            bot.fetch_reservations_window = orig_fetch
        self.assertIn("انحجزت بعد النزول: 1", txt)
        self.assertIn("1 MLQ", txt)
        self.assertIn("A5 MLQ", txt)                      # still empty


SAT, SUN, MON = "2026-11-07", "2026-11-08", "2026-11-09"


def on(day, h, m=0):
    return datetime(2026, 11, day, h, m, tzinfo=bot.TZ)


class DatedHostaway(FakeHostaway):
    """Like FakeHostaway, but every (unit, date) has its own calendar day."""

    def __init__(self):
        super().__init__()
        self.cal = {}

    def day(self, lid, d):
        if (lid, d) not in self.cal:
            self.cal[(lid, d)] = dict(self.days[lid], date=d)
        return self.cal[(lid, d)]

    def get(self, path, params=None, **_kw):
        lid, d = int(path.split("/")[2]), params["startDate"]
        self.gets.append((lid, d))
        return {"result": [dict(self.day(lid, d))]}

    def put(self, path, body, _retry=0):
        lid, d = int(path.split("/")[2]), body["startDate"]
        if self.fail_puts:
            self.fail_puts -= 1
            raise RuntimeError("Hostaway 500")
        self.puts.append((lid, d, body["price"]))
        self.day(lid, d).update(price=body["price"], note=body.get("note", ""))
        return {"status": "success"}


class EarlyNightTest(_Base):
    """Owner 2026-11-08, option B: Sunday and Monday nights drop −10% from 3 PM the day before,
    held overnight, then the normal ladder on the night itself."""
    EARLY_PATCHED = ("LM_EARLY_NIGHTS", "LM_EARLY_PERCENT", "LM_EARLY_HOUR", "LM_EARLY_RECHECK_MIN")

    def setUp(self):
        super().setUp()
        self._orig.update({n: getattr(bot, n) for n in self.EARLY_PATCHED})
        bot.LM_EARLY_NIGHTS = frozenset({6, 0})
        bot.LM_EARLY_PERCENT, bot.LM_EARLY_HOUR, bot.LM_EARLY_RECHECK_MIN = 10.0, 15, 60
        self.fake = DatedHostaway()
        bot.api_get, bot.api_put = self.fake.get, self.fake.put

    def p(self, lid, d):
        return self.fake.day(lid, d)["price"]

    def test_saturday_3pm_drops_sunday_night_too(self):
        bot.lm_keeper_tick(on(7, 15, 0))
        self.assertEqual(self.p(EMPTY, SAT), 388)
        self.assertEqual(self.p(EMPTY, SUN), 388)
        self.assertEqual(self.p(OTHER, SUN), 450)
        self.assertEqual(self.p(BOOKED, SUN), 618)

    def test_nothing_for_sunday_before_saturday_3pm(self):
        bot.lm_keeper_tick(on(7, 14, 55))
        self.assertEqual(self.fake.gets, [])

    def test_overnight_bounce_is_fixed_in_the_morning(self):
        bot.lm_keeper_tick(on(7, 15, 0))
        self.fake.day(EMPTY, SUN).update(price=431, note="")      # someone pushed it back up
        bot.lm_keeper_tick(on(8, 9, 0))
        self.assertEqual(self.p(EMPTY, SUN), 388)                 # original still 431

    def test_morning_recheck_is_hourly_not_every_tick(self):
        bot.lm_keeper_tick(on(8, 9, 0))
        n = self.fake.gets.count((EMPTY, SUN))
        bot.lm_keeper_tick(on(8, 9, 5))
        bot.lm_keeper_tick(on(8, 9, 30))
        self.assertEqual(self.fake.gets.count((EMPTY, SUN)), n)
        bot.lm_keeper_tick(on(8, 10, 5))
        self.assertEqual(self.fake.gets.count((EMPTY, SUN)), n + 1)

    def test_sunday_night_then_runs_the_normal_ladder(self):
        bot.lm_keeper_tick(on(7, 15, 0))
        bot.lm_keeper_tick(on(8, 15, 0))
        self.assertEqual(self.p(EMPTY, SUN), 388)
        bot.lm_keeper_tick(on(8, 18, 0))
        self.assertEqual(self.p(EMPTY, SUN), 345)
        bot.lm_keeper_tick(on(8, 20, 0))
        self.assertEqual(self.p(EMPTY, SUN), 302)
        self.assertEqual(self.p(EMPTY, MON), 388)                 # Monday night began at 3 PM Sunday

    def test_monday_evening_leaves_tuesday_alone(self):
        bot.lm_keeper_tick(on(9, 16, 0))
        self.assertEqual({d for _l, d in self.fake.gets}, {MON})

    def test_switched_off(self):
        bot.LM_EARLY_NIGHTS = frozenset()
        bot.lm_keeper_tick(on(7, 16, 0))
        bot.lm_keeper_tick(on(8, 9, 0))
        self.assertEqual({d for _l, d in self.fake.gets}, {SAT})

    def test_alerts_only_for_tonight(self):
        self.fake.fail_puts = 99
        bot.lm_keeper_tick(on(7, 15, 0))
        _rec, alerts = bot.lm_keeper_tick(on(7, 15, 30))
        self.assertEqual(sorted(a["lid"] for a in alerts), sorted([str(EMPTY), str(OTHER)]))

    def test_morning_ticks_only_on_early_nights(self):
        self.assertTrue(bot.lm_keeper_should_tick(on(8, 9, 0)))     # Sunday
        self.assertTrue(bot.lm_keeper_should_tick(on(9, 3, 0)))     # Monday
        self.assertFalse(bot.lm_keeper_should_tick(on(10, 9, 0)))   # Tuesday
        self.assertFalse(bot.lm_keeper_should_tick(on(8, 2, 0)))    # report hours
        self.assertTrue(bot.lm_keeper_should_tick(on(10, 15, 0)))
        bot.LM_EARLY_NIGHTS = frozenset()
        self.assertFalse(bot.lm_keeper_should_tick(on(8, 9, 0)))

    def test_sunday_report_counts_saturday_bookings(self):
        bot.lm_keeper_tick(on(7, 15, 0))
        rows = [{"listingMapId": EMPTY, "arrivalDate": SUN, "reservationDate": "2026-11-07 13:30:00",
                 "totalPrice": 388, "nights": 1, "status": "new"}]
        orig_fetch = bot.fetch_reservations_window
        bot.fetch_reservations_window = lambda s, e, pad_days=45: rows
        try:
            txt = bot.lm_report_text(SUN)
        finally:
            bot.fetch_reservations_window = orig_fetch
        self.assertIn("انحجزت بعد النزول: 1", txt)
        self.assertIn("أمس 16:30", txt)
        self.assertIn("خصم مبكر", txt)


if __name__ == "__main__":
    unittest.main()
