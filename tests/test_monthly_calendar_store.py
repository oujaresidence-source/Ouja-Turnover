# -*- coding: utf-8 -*-
"""The /monthly calendar store. Synthetic, no network — that is the whole point.

A dated search used to cost one Hostaway calendar call per apartment INSIDE the
customer's page load: measured at 69.7 seconds live on 2026-08-24. The calls moved
to a background pass and the search now reads this store.

What these lock, in order of how badly each would hurt a guest:
  * a night missing from the store is UNKNOWN — never free, never priced
  * a total is produced only when EVERY night of the window carries a price
  * one unavailable night makes the whole stay unavailable
  * booked vs blocked still requires a reservation, so Airbnb blocks are not demand
  * monthly_quote NEVER reaches the network, cold store included
  * a cold store degrades to a labelled estimate, it does not hang and does not lie
"""
import datetime
import unittest

import bot


def day(n):
    return (datetime.date(2026, 9, 1) + datetime.timedelta(days=n)).isoformat()


def store(unit_rows):
    """unit_rows: {lid: {date_iso: [available, price, has_reservation]}}"""
    return {"units": {str(k): v for k, v in unit_rows.items()},
            "synced_at": "2026-09-01T00:00:00", "from": day(0), "to": day(210)}


def month(price=700.0, avail=1, res=0, days=31, start=0):
    return {day(start + i): [avail, price, res] for i in range(days)}


class Quote(unittest.TestCase):
    def setUp(self):
        self._orig = bot._mcal
        bot._mcal = store({7: month()})

    def tearDown(self):
        bot._mcal = self._orig

    def q(self, lid=7, a=0, b=30):
        return bot._mcal_quote(lid, datetime.date(2026, 9, 1) + datetime.timedelta(days=a),
                               datetime.date(2026, 9, 1) + datetime.timedelta(days=b))

    def test_sums_every_night_in_the_window(self):
        r = self.q()
        self.assertEqual(r["nights"], 30)
        self.assertEqual(r["total"], 21000)          # 30 x 700
        self.assertEqual(r["avg"], 700)
        self.assertTrue(r["available"])

    def test_checkout_night_is_not_charged(self):
        # [1 Sep, 3 Sep) is two nights, not three
        self.assertEqual(self.q(a=0, b=2)["total"], 1400)

    def test_missing_night_is_unknown_not_a_cheaper_stay(self):
        bot._mcal["units"]["7"].pop(day(10))
        self.assertIsNone(self.q(), "a gap must refuse to answer, never quote 29 nights")

    def test_unit_absent_from_store_returns_none(self):
        self.assertIsNone(self.q(lid=999))

    def test_one_blocked_night_makes_the_stay_unavailable(self):
        bot._mcal["units"]["7"][day(10)] = [0, 700.0, 1]
        r = self.q()
        self.assertFalse(r["available"])
        self.assertEqual(r["total"], 21000, "still priced — availability and price are separate")

    def test_total_is_none_unless_every_night_is_priced(self):
        bot._mcal["units"]["7"][day(10)] = [1, None, 0]
        r = self.q()
        self.assertIsNone(r["total"], "a partial sum would undercharge by a night")
        self.assertIsNone(r["avg"])

    def test_window_past_the_end_of_the_store_returns_none(self):
        self.assertIsNone(self.q(a=0, b=90))

    def test_zero_night_window_refused(self):
        self.assertIsNone(self.q(a=5, b=5))


class Booked(unittest.TestCase):
    def setUp(self):
        self._orig = bot._mcal
        u = month(days=30)
        for i in range(6):                       # 6 reserved nights
            u[day(i)] = [0, 700.0, 1]
        for i in range(6, 14):                   # 8 blocked-but-unreserved nights
            u[day(i)] = [0, 700.0, 0]
        bot._mcal = store({7: u})

    def tearDown(self):
        bot._mcal = self._orig

    def test_blocks_are_not_counted_as_bookings(self):
        b, blk, days = bot._mcal_booked(7, datetime.date(2026, 9, 1), datetime.date(2026, 10, 1))
        self.assertEqual(b, 6)
        self.assertEqual(blk, 8)
        self.assertEqual(days, 30)

    def test_unknown_unit_returns_none(self):
        self.assertIsNone(bot._mcal_booked(999, datetime.date(2026, 9, 1),
                                           datetime.date(2026, 10, 1)))


class NeverTouchesTheNetwork(unittest.TestCase):
    """The regression that matters. If any of these calls Hostaway, the guest page can
    hang again — so the network is replaced by a landmine for the duration."""

    def setUp(self):
        self._orig_cal, self._orig_get = bot._mcal, bot.api_get
        self._orig_avail = bot.unit_availability_price

        def boom(*a, **k):
            raise AssertionError("the guest price path reached Hostaway — that is the bug")

        bot.api_get = boom
        bot.unit_availability_price = boom
        bot._mcal = store({7: month()})

    def tearDown(self):
        bot._mcal, bot.api_get = self._orig_cal, self._orig_get
        bot.unit_availability_price = self._orig_avail

    def test_monthly_quote_prices_from_the_store(self):
        q = bot.monthly_quote(7, "2026-09-01", 1, {"price_base": 900})
        self.assertEqual(q["before"], 21000)         # 30 nights x 700, not 30 x 900
        self.assertFalse(q["estimated"])
        self.assertTrue(q["available"])

    def test_cold_store_degrades_to_a_labelled_estimate(self):
        bot._mcal = {"units": {}, "synced_at": None}
        q = bot.monthly_quote(7, "2026-09-01", 1, {"price_base": 900})
        self.assertTrue(q["estimated"], "an estimate must announce itself")
        self.assertEqual(q["before"], 27000)         # 30 x 900 price_base
        self.assertIsNone(q["available"], "unknown availability is None, never False")

    def test_cold_store_and_no_price_base_answers_nothing(self):
        bot._mcal = {"units": {}, "synced_at": None}
        self.assertIsNone(bot.monthly_quote(7, "2026-09-01", 1, {}))

    def test_booked_unit_is_dropped_from_search_results(self):
        u = month()
        u[day(3)] = [0, 700.0, 1]
        bot._mcal = store({7: month(), 8: u})
        snaps = [({"id": 7, "price_base": 900}, {"sort": 1}),
                 ({"id": 8, "price_base": 900}, {"sort": 2})]
        orig_filter, orig_card = bot._monthly_filter, bot._monthly_card
        try:
            bot._monthly_filter = lambda *a, **k: snaps
            bot._monthly_card = lambda s, ov, **k: {"id": s["id"], "images": [], "name_ar": ""}
            out = bot._monthly_search_sync("2026-09-01", 1)
        finally:
            bot._monthly_filter, bot._monthly_card = orig_filter, orig_card
        self.assertEqual([r["id"] for r in out["results"]], [7],
                         "unit 8 has a reserved night inside the stay")
        self.assertFalse(out["avail_error"])


class FetchShape(unittest.TestCase):
    """_mcal_window is the one place Hostaway's JSON becomes our rows."""

    def setUp(self):
        self._orig = bot.api_get

    def tearDown(self):
        bot.api_get = self._orig

    def test_maps_availability_price_and_reservation(self):
        bot.api_get = lambda *a, **k: {"result": [
            {"date": "2026-09-01", "isAvailable": 1, "price": 700},
            {"date": "2026-09-02", "isAvailable": 0, "price": 700, "reservationId": 55},
            {"date": "2026-09-03", "isAvailable": 0, "price": 0},
        ]}
        got = bot._mcal_window(7, datetime.date(2026, 9, 1), datetime.date(2026, 9, 3))
        self.assertEqual(got["2026-09-01"], [1, 700.0, 0])
        self.assertEqual(got["2026-09-02"], [0, 700.0, 1])
        self.assertEqual(got["2026-09-03"], [0, None, 0], "price 0 is no price, not free")

    def test_a_failed_pull_returns_none_rather_than_an_empty_calendar(self):
        def boom(*a, **k):
            raise RuntimeError("Hostaway down")
        bot.api_get = boom
        self.assertIsNone(bot._mcal_window(7, datetime.date(2026, 9, 1),
                                           datetime.date(2026, 9, 3)))

    def test_empty_result_is_also_none(self):
        bot.api_get = lambda *a, **k: {"result": []}
        self.assertIsNone(bot._mcal_window(7, datetime.date(2026, 9, 1),
                                           datetime.date(2026, 9, 3)),
                          "an empty calendar must not overwrite a good copy")


class WideCallThenRepair(unittest.TestCase):
    """One call for the whole horizon, then stitch anything it did not cover.

    Hostaway does serve a 210-day range — measured live, 56 of 57 units, one pull
    each. An empty store was once misread as a rejected range; it was congestion.
    So the wide call is the normal path (57 calls a cycle, not 228) and the narrow
    windows are the repair, for a day when a pull comes back short."""

    def setUp(self):
        self._orig = bot.api_get
        self.calls = []

    def tearDown(self):
        bot.api_get = self._orig

    def _serve(self, max_span_days=60):
        """A Hostaway that REFUSES windows wider than it supports — the behaviour the
        first version assumed away."""
        def fake(path, params=None):
            p = params or {}
            a = datetime.date.fromisoformat(p["startDate"])
            b = datetime.date.fromisoformat(p["endDate"])
            self.calls.append((a, b))
            if (b - a).days + 1 > max_span_days:
                raise RuntimeError("range too wide")
            days, d = [], a
            while d <= b:
                days.append({"date": d.isoformat(), "isAvailable": 1, "price": 700})
                d += datetime.timedelta(days=1)
            return {"result": days}
        bot.api_get = fake

    def test_a_wide_window_costs_exactly_one_call(self):
        """The normal path, and the reason chunking-by-default was wrong."""
        self._serve(max_span_days=400)
        got = bot._mcal_fetch_unit(7, datetime.date(2026, 9, 1), datetime.date(2027, 2, 28))
        self.assertEqual(len(self.calls), 1, "one call per unit when the range is served")
        self.assertEqual(len(got), 181)

    def test_a_refused_wide_window_falls_back_to_narrow_ones(self):
        self._serve(max_span_days=60)
        got = bot._mcal_fetch_unit(7, datetime.date(2026, 9, 1), datetime.date(2027, 2, 28))
        self.assertEqual(len(self.calls), 5, "one refused wide call, then four windows")
        self.assertEqual(len(got), 181, "the full horizon still gets covered")
        self.assertIn("2026-09-01", got)
        self.assertIn("2027-02-28", got)

    def test_a_short_answer_is_repaired_from_where_it_stopped(self):
        """Hostaway answers, but only for part of what was asked. The rest is
        stitched on from the day after the last one it gave — no gap, no overlap."""
        state = {"n": 0}
        def fake(path, params=None):
            state["n"] += 1
            a = datetime.date.fromisoformat(params["startDate"])
            b = datetime.date.fromisoformat(params["endDate"])
            if state["n"] == 1:
                b = a + datetime.timedelta(days=29)      # only 30 days of 181
            self.calls.append((a, b))
            days, d = [], a
            while d <= b:
                days.append({"date": d.isoformat(), "isAvailable": 1, "price": 700})
                d += datetime.timedelta(days=1)
            return {"result": days}
        bot.api_get = fake
        got = bot._mcal_fetch_unit(7, datetime.date(2026, 9, 1), datetime.date(2027, 2, 28))
        self.assertEqual(len(got), 181)
        self.assertEqual(self.calls[1][0], datetime.date(2026, 10, 1),
                         "repair starts the day after the last day actually returned")

    def test_a_partial_horizon_is_kept_not_thrown_away(self):
        """Near dates keep exact prices even when a later window fails."""
        calls = {"n": 0}
        def flaky(path, params=None):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("Hostaway down")
            params = dict(params)
            params["endDate"] = (datetime.date.fromisoformat(params["startDate"])
                                 + datetime.timedelta(days=59)).isoformat()
            a = datetime.date.fromisoformat(params["startDate"])
            b = datetime.date.fromisoformat(params["endDate"])
            days, d = [], a
            while d <= b:
                days.append({"date": d.isoformat(), "isAvailable": 1, "price": 700})
                d += datetime.timedelta(days=1)
            return {"result": days}
        bot.api_get = flaky
        got = bot._mcal_fetch_unit(7, datetime.date(2026, 9, 1), datetime.date(2027, 2, 28))
        self.assertEqual(len(got), 60, "the days we did get survive")

    def test_total_failure_is_none_so_the_old_copy_survives(self):
        def boom(*a, **k):
            raise RuntimeError("down")
        bot.api_get = boom
        self.assertIsNone(bot._mcal_fetch_unit(7, datetime.date(2026, 9, 1),
                                               datetime.date(2027, 2, 28)))


class RefreshKeepsLastGoodCopy(unittest.TestCase):
    def setUp(self):
        self._orig_cal, self._orig_snaps = bot._mcal, bot._monthly_visible_snaps
        self._orig_save, self._orig_fetch = bot._save_json, bot._mcal_fetch_unit
        bot._save_json = lambda *a, **k: True
        bot._monthly_visible_snaps = lambda: [({"id": 7}, {}), ({"id": 8}, {})]
        bot._mcal = store({7: month(), 8: month(price=500.0)})

    def tearDown(self):
        bot._mcal, bot._monthly_visible_snaps = self._orig_cal, self._orig_snaps
        bot._save_json, bot._mcal_fetch_unit = self._orig_save, self._orig_fetch

    def test_a_unit_that_fails_keeps_yesterdays_calendar(self):
        bot._mcal_fetch_unit = lambda lid, a, b: ({"x": [1, 1.0, 0]} if str(lid) == "7" else None)
        res = bot._mcal_refresh_sync()
        self.assertEqual((res["ok"], res["err"]), (1, 1))
        self.assertEqual(bot._mcal["units"]["7"], {"x": [1, 1.0, 0]}, "unit 7 refreshed")
        self.assertEqual(bot._mcal["units"]["8"][day(0)], [1, 500.0, 0],
                         "unit 8 failed — it must keep its last good copy, not vanish")


if __name__ == "__main__":
    unittest.main()


class EnginePrecompute(unittest.TestCase):
    """The engine store. It sat empty for 22 minutes after the owner flipped the
    switch, because _mengine_refresh_sync reached for `monthly.collect` — an
    attribute the package does not have, since routes.py imports collect lazily
    inside its handlers. AttributeError, swallowed by a broad except, reported to a
    log nobody was reading, retried every three hours forever.

    So: one test that the refresh actually reaches units_report, and one that a
    failure is VISIBLE rather than merely logged."""

    def setUp(self):
        self._cal, self._eng = bot._mcal, dict(bot._mengine)
        bot._mcal = store({7: month()})
        bot._mengine.update({"month": None, "units": {}, "at": None, "err": "",
                             "coverage": None, "tries": 0})

    def tearDown(self):
        bot._mcal = self._cal
        bot._mengine.clear()
        bot._mengine.update(self._eng)

    def _stub_report(self, rep):
        import monthly.collect as collect
        real = collect.units_report
        collect.units_report = lambda m, force=False, today=None: rep
        return collect, real

    def test_a_refresh_fills_the_store_and_the_lookup_answers(self):
        collect, real = self._stub_report({
            "rows": [{"lid": 7, "price": 15000.0, "basis": "own_history"},
                     {"lid": 8, "price": None, "basis": "insufficient"}],
            "pct_own_history": 0.42})
        try:
            res = bot._mengine_refresh_sync()
        finally:
            collect.units_report = real
        self.assertTrue(res["ok"])
        self.assertEqual(res["n"], 1, "a unit with no price is not stored")
        self.assertEqual(bot._mengine_state(), "ok")
        month = bot.datetime.now(bot.TZ).date().strftime("%Y-%m")
        self.assertEqual(bot.monthly_engine_price(7, month),
                         {"price": 15000.0, "basis": "own_history"})
        self.assertIsNone(bot.monthly_engine_price(8, month))
        self.assertIsNone(bot.monthly_engine_price(7, "1999-01"),
                          "a price from another month must never be published")

    def test_a_failure_is_visible_not_just_logged(self):
        collect, real = self._stub_report(None)
        def boom(*_a, **_k):
            raise AttributeError("module 'monthly' has no attribute 'collect'")
        collect.units_report = boom
        try:
            res = bot._mengine_refresh_sync()
        finally:
            collect.units_report = real
        self.assertFalse(res["ok"])
        self.assertEqual(bot._mengine_state(), "failed",
                         "the exact silence that cost 22 minutes")
        self.assertTrue(bot._mengine["err"])
        self.assertEqual(bot._mengine["tries"], 1)

    def test_a_run_that_prices_nothing_is_distinguishable_from_never_running(self):
        self.assertEqual(bot._mengine_state(), "idle")
        collect, real = self._stub_report({"rows": [], "pct_own_history": 0.0})
        try:
            bot._mengine_refresh_sync()
        finally:
            collect.units_report = real
        self.assertEqual(bot._mengine_state(), "empty")

    def test_a_cold_calendar_reads_as_waiting_not_broken(self):
        bot._mcal = {"units": {}}
        self.assertEqual(bot._mengine_state(), "waiting")
