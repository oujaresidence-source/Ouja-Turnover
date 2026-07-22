# -*- coding: utf-8 -*-
"""studio.internal — the v3 internal signal collectors, on SYNTHETIC data only.

No network. Every number a collector speaks on camera is asserted here against a
hand-built input: median booking lead time (incl. even counts + garbage dates),
weekend uplift %, tonight's occupancy, same-day turnover detection, review privacy,
empty/failing taps, and collect() resilience when one collector raises."""
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from studio import db as sdb, internal
from studio.host import HOST

TODAY = date(2026, 7, 23)


def _res(lid, arrival, departure, booked_on=None, rid=None, status="modified"):
    r = {"id": rid if rid is not None else "%s-%s" % (lid, arrival),
         "listingMapId": lid, "arrivalDate": arrival, "departureDate": departure,
         "status": status, "nights": 2, "totalPrice": 1200}
    if booked_on is not None:
        r["reservationDate"] = booked_on
    return r


def _day(iso, weekend=False, pace=50, total=50, price=600, events=None, boost=1.0):
    occ = int(round(total * pace / 100.0))
    return {"date": iso, "weekday": 3 if weekend else 0, "is_weekend": weekend,
            "occupied": occ, "available": total - occ, "total": total,
            "pace_pct": pace, "avg_price": price, "booked_value": occ * (price or 0),
            "events": events or [], "event_boost": boost}


# ---------------------------------------------------------------------------
# D1 — occupancy math
# ---------------------------------------------------------------------------

class TestLeadTime(unittest.TestCase):
    def test_odd_count_median(self):
        rows = [_res(1, "2026-07-24", "2026-07-26", "2026-07-23"),   # 1
                _res(2, "2026-07-25", "2026-07-27", "2026-07-23"),   # 2
                _res(3, "2026-07-26", "2026-07-28", "2026-07-23"),   # 3
                _res(4, "2026-07-30", "2026-08-01", "2026-07-20"),   # 10
                _res(5, "2026-07-24", "2026-07-25", "2026-07-24")]   # 0
        # sorted: 0,1,2,3,10 -> median 2
        self.assertEqual(internal.median_lead_days(rows), 2.0)

    def test_even_count_median_is_the_average_of_the_middle_two(self):
        rows = [_res(1, "2026-07-24", "2026-07-26", "2026-07-23"),   # 1
                _res(2, "2026-07-25", "2026-07-27", "2026-07-23"),   # 2
                _res(3, "2026-07-27", "2026-07-29", "2026-07-23"),   # 4
                _res(4, "2026-07-31", "2026-08-01", "2026-07-23"),   # 8
                _res(5, "2026-07-24", "2026-07-25", "2026-07-24"),   # 0
                _res(6, "2026-08-02", "2026-08-04", "2026-07-23")]   # 10
        # sorted: 0,1,2,4,8,10 -> (2+4)/2 = 3.0
        self.assertEqual(internal.median_lead_days(rows), 3.0)

    def test_insider_hero_fact_one_day(self):
        rows = [_res(i, "2026-07-24", "2026-07-26", "2026-07-23") for i in range(6)]
        self.assertEqual(internal.median_lead_days(rows), 1.0)

    def test_missing_or_garbage_dates_yield_no_signal_and_no_crash(self):
        rows = [_res(1, "2026-07-24", "2026-07-26"),                       # no booking date
                _res(2, "not-a-date", "2026-07-27", "2026-07-23"),
                _res(3, "2026-07-26", "2026-07-28", "غير معروف"),
                {"listingMapId": 4, "status": "modified"},
                _res(5, "2026-07-24", "2026-07-25", "2026-08-30")]         # booked AFTER arrival
        self.assertIsNone(internal.median_lead_days(rows))
        self.assertIsNone(internal.median_lead_days([]))
        self.assertIsNone(internal.median_lead_days(None))

    def test_cancelled_bookings_do_not_count(self):
        rows = [_res(i, "2026-07-24", "2026-07-26", "2026-07-23", status="cancelled")
                for i in range(8)]
        self.assertIsNone(internal.median_lead_days(rows))


class TestTonightOccupancy(unittest.TestCase):
    def test_count_and_percentage(self):
        rows = [_res(1, "2026-07-22", "2026-07-25"),
                _res(2, "2026-07-20", "2026-07-24"),
                _res(3, "2026-07-23", "2026-07-26"),
                _res(4, "2026-07-23", "2026-07-24", status="cancelled")]   # ignored
        occ = internal.tonight_occupancy(rows, 6)
        self.assertEqual(occ["occupied"], 3)
        self.assertEqual(occ["total"], 6)
        self.assertEqual(occ["pct"], 50)

    def test_same_unit_twice_counts_once(self):
        rows = [_res(7, "2026-07-20", "2026-07-23", rid="a"),
                _res(7, "2026-07-23", "2026-07-27", rid="b")]
        self.assertEqual(internal.tonight_occupancy(rows, 10)["occupied"], 1)

    def test_empty_is_zero_not_an_error(self):
        self.assertEqual(internal.tonight_occupancy([], 0),
                         {"occupied": 0, "total": 0, "pct": 0})


class TestBusiestUnit(unittest.TestCase):
    def test_clear_winner(self):
        rows = ([_res(11, (TODAY + timedelta(days=i)).isoformat(),
                      (TODAY + timedelta(days=i + 1)).isoformat(), rid="a%d" % i)
                 for i in range(5)]
                + [_res(12, (TODAY + timedelta(days=i)).isoformat(),
                        (TODAY + timedelta(days=i + 1)).isoformat(), rid="b%d" % i)
                   for i in range(2)])
        self.assertEqual(internal.busiest_unit(rows, TODAY), (11, 5))

    def test_a_tie_is_not_a_story(self):
        rows = ([_res(11, (TODAY + timedelta(days=i)).isoformat(),
                      (TODAY + timedelta(days=i + 1)).isoformat(), rid="a%d" % i)
                 for i in range(4)]
                + [_res(12, (TODAY + timedelta(days=i)).isoformat(),
                        (TODAY + timedelta(days=i + 1)).isoformat(), rid="b%d" % i)
                   for i in range(4)])
        self.assertIsNone(internal.busiest_unit(rows, TODAY))


# ---------------------------------------------------------------------------
# D2 — pricing math
# ---------------------------------------------------------------------------

class TestPricing(unittest.TestCase):
    def test_weekend_uplift_percent(self):
        cal = [_day("2026-07-23", weekend=True, price=1000),
               _day("2026-07-24", weekend=True, price=1200),
               _day("2026-07-25", price=800),
               _day("2026-07-26", price=800),
               _day("2026-07-27", price=800)]
        # weekend avg 1100, weekday avg 800 -> +37.5%
        self.assertEqual(internal.weekend_uplift_pct(cal), 37.5)

    def test_uplift_ignores_days_with_no_price(self):
        cal = [_day("2026-07-23", weekend=True, price=900),
               _day("2026-07-24", weekend=True, price=None),
               _day("2026-07-25", price=600),
               _day("2026-07-26", price=0)]
        self.assertEqual(internal.weekend_uplift_pct(cal), 50.0)

    def test_uplift_needs_both_sides(self):
        self.assertIsNone(internal.weekend_uplift_pct(
            [_day("2026-07-23", weekend=True, price=900)]))
        self.assertIsNone(internal.weekend_uplift_pct([]))

    def test_price_extremes(self):
        cal = [_day("2026-07-23", price=500), _day("2026-07-24", price=1500),
               _day("2026-07-25", price=None), _day("2026-07-26", price=900)]
        hi, lo = internal.price_extremes(cal)
        self.assertEqual(hi["avg_price"], 1500)
        self.assertEqual(lo["avg_price"], 500)
        self.assertEqual(internal.price_extremes([]), (None, None))

    def test_pace_outlier_needs_a_real_gap(self):
        flat = [_day("2026-07-%02d" % (23 + i), pace=60) for i in range(8)]
        self.assertIsNone(internal.pace_outlier(flat))
        spiky = flat[:7] + [_day("2026-07-31", pace=98)]
        got = internal.pace_outlier(spiky)
        self.assertIsNotNone(got)
        self.assertEqual(got["day"]["date"], "2026-07-31")


# ---------------------------------------------------------------------------
# D4 — ops: same-day turnovers
# ---------------------------------------------------------------------------

class TestSameDayTurnover(unittest.TestCase):
    def test_finds_a_real_turnover(self):
        rows = [_res(21, "2026-07-20", "2026-07-25", rid="out"),
                _res(21, "2026-07-25", "2026-07-28", rid="in")]
        got = internal.same_day_turnovers(rows, TODAY)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["lid"], 21)
        self.assertEqual(got[0]["date"], "2026-07-25")

    def test_no_false_positive_across_different_units(self):
        rows = [_res(21, "2026-07-20", "2026-07-25", rid="out"),
                _res(22, "2026-07-25", "2026-07-28", rid="in")]
        self.assertEqual(internal.same_day_turnovers(rows, TODAY), [])

    def test_no_false_positive_on_a_gap_day(self):
        rows = [_res(21, "2026-07-20", "2026-07-25", rid="out"),
                _res(21, "2026-07-26", "2026-07-28", rid="in")]
        self.assertEqual(internal.same_day_turnovers(rows, TODAY), [])

    def test_past_and_far_future_turnovers_are_out_of_scope(self):
        rows = [_res(21, "2026-07-01", "2026-07-05", rid="o1"),
                _res(21, "2026-07-05", "2026-07-08", rid="i1"),         # past
                _res(21, "2026-08-20", "2026-08-25", rid="o2"),
                _res(21, "2026-08-25", "2026-08-28", rid="i2")]         # beyond horizon
        self.assertEqual(internal.same_day_turnovers(rows, TODAY), [])

    def test_cancelled_leg_is_not_a_turnover(self):
        rows = [_res(21, "2026-07-20", "2026-07-25", rid="out"),
                _res(21, "2026-07-25", "2026-07-28", rid="in", status="cancelled")]
        self.assertEqual(internal.same_day_turnovers(rows, TODAY), [])


# ---------------------------------------------------------------------------
# D3 — reviews
# ---------------------------------------------------------------------------

def _rev(rid, rating, text, guest="", d="2026-07-01"):
    return {"id": rid, "listing_id": 1, "rating": rating, "public_review": text,
            "guest_name": guest, "channel": "Airbnb", "date": d}


class TestReviews(unittest.TestCase):
    def test_stats(self):
        revs = [_rev(1, 5, "ممتاز"), _rev(2, 5, "حلو"), _rev(3, 4, "زين"),
                _rev(4, 0, "بدون تقييم")]
        st = internal.review_stats(revs)
        self.assertEqual(st["count"], 3)
        self.assertEqual(st["avg"], 4.67)
        self.assertEqual(st["five_pct"], 67)
        self.assertEqual(internal.review_stats([])["count"], 0)

    def test_top_theme_counts_the_repeated_compliment(self):
        revs = ([_rev(i, 5, "الشقة نظيفة جداً والمكان مرتب") for i in range(5)]
                + [_rev(50 + i, 5, "الموقع ممتاز وقريب من كل شي") for i in range(2)])
        name, hits, share = internal.top_theme(revs)
        self.assertEqual(name, "النظافة")
        self.assertEqual(hits, 5)
        self.assertEqual(share, 71)

    def test_top_theme_needs_a_winner(self):
        self.assertIsNone(internal.top_theme([]))
        tied = ([_rev(i, 5, "نظيفة") for i in range(3)]
                + [_rev(10 + i, 5, "الموقع حلو") for i in range(3)])
        self.assertIsNone(internal.top_theme(tied))

    def test_quote_is_scrubbed_of_the_guest_name(self):
        revs = [_rev(1, 5, "تجربة سعد الدوسري كانت ممتازة والشقة نظيفة والاستقبال سريع",
                     guest="سعد الدوسري", d="2026-07-10")]
        q = internal.pick_quote(revs)
        self.assertIsNotNone(q)
        self.assertNotIn("سعد", q["text"])
        self.assertNotIn("الدوسري", q["text"])
        self.assertIn("الضيف", q["text"])

    def test_quote_signal_never_contains_the_guest_name(self):
        ctx = _ctx(reviews=[_rev(1, 5,
                                 "تجربة سعد الدوسري كانت ممتازة والشقة نظيفة والرد سريع",
                                 guest="سعد الدوسري", d="2026-07-10")])
        sigs = internal.collect_reviews(ctx)
        quote = [s for s in sigs if s["ref"] == "rev_quote"]
        self.assertEqual(len(quote), 1)
        blob = quote[0]["fact"] + quote[0]["detail"] + quote[0]["title"]
        self.assertNotIn("سعد", blob)
        self.assertNotIn("الدوسري", blob)

    def test_short_or_linky_reviews_are_not_quotable(self):
        self.assertIsNone(internal.pick_quote([_rev(1, 5, "ممتاز")]))
        self.assertIsNone(internal.pick_quote(
            [_rev(1, 5, "شقة رائعة جداً وننصح فيها بشدة https://x.co/abc")]))
        self.assertIsNone(internal.pick_quote(
            [_rev(1, 3, "شقة رائعة جداً وننصح فيها بشدة لكل من يزور الرياض")]))


# ---------------------------------------------------------------------------
# D5 — season
# ---------------------------------------------------------------------------

class TestSeason(unittest.TestCase):
    def test_only_near_events(self):
        cal = [_day("2026-07-25", events=[{"name": "موسم الرياض", "kind": "season",
                                           "boost": 1.3}], boost=1.3),
               _day("2026-12-01", events=[{"name": "حدث بعيد", "kind": "season",
                                           "boost": 1.2}], boost=1.2)]
        got = internal.near_events(cal, TODAY)
        self.assertEqual([e["name"] for e in got], ["موسم الرياض"])
        self.assertEqual(got[0]["in_days"], 2)

    def test_no_events_no_signal(self):
        self.assertEqual(internal.near_events([_day("2026-07-25")], TODAY), [])

    def test_salary_cycle_only_near_month_end(self):
        self.assertIsNone(internal.salary_cycle_days(date(2026, 7, 12)))
        self.assertEqual(internal.salary_cycle_days(date(2026, 7, 27)), 5)
        self.assertEqual(internal.salary_cycle_days(date(2026, 7, 1)), 0)

    def test_fixed_saudi_day_fires_when_near(self):
        ctx = _ctx(today=date(2026, 9, 10))
        refs = [s["ref"] for s in internal.collect_season(ctx)]
        self.assertIn("season_fixed_2026-09-23", refs)

    def test_generic_summer_is_never_emitted(self):
        ctx = _ctx(today=date(2026, 7, 12))       # nothing near, no salary window
        self.assertEqual(internal.collect_season(ctx), [])


# ---------------------------------------------------------------------------
# collectors + collect()
# ---------------------------------------------------------------------------

def _ctx(**kw):
    today = kw.pop("today", TODAY)
    ctx = {"today": today, "as_of": today.isoformat(), "listings": {},
           "inhouse": [], "res": [], "cal": [], "reviews": []}
    ctx.update(kw)
    return ctx


def _full_ctx(today=TODAY):
    listings = {100 + i: "Ouja | وحدة %d" % i for i in range(53)}
    inhouse = [_res(100 + i, "2026-07-21", "2026-07-26", rid="h%d" % i) for i in range(45)]
    res = ([_res(100 + i, (today + timedelta(days=i % 10)).isoformat(),
                 (today + timedelta(days=(i % 10) + 2)).isoformat(),
                 (today - timedelta(days=1)).isoformat(), rid="r%d" % i)
            for i in range(30)]
           + [_res(101, "2026-07-24", "2026-07-28", "2026-07-23", rid="t-in"),
              _res(101, "2026-07-19", "2026-07-24", "2026-07-18", rid="t-out")])
    cal = []
    for i in range(CAL_LEN):
        d = today + timedelta(days=i)
        wknd = d.weekday() in (3, 4)
        cal.append(_day(d.isoformat(), weekend=wknd, pace=70 if wknd else 55,
                        price=1100 if wknd else 800))
    reviews = ([_rev(i, 5, "الشقة نظيفة جداً والموقع ممتاز والتعامل راقي", d="2026-07-0%d" % (i + 1))
                for i in range(9)]
               + [_rev(90, 5, "من أنظف الشقق اللي نزلنا فيها في الرياض والرد كان سريع",
                       guest="نورة", d="2026-07-15")])
    return {"today": today, "as_of": today.isoformat(), "listings": listings,
            "inhouse": inhouse, "res": res, "cal": cal, "reviews": reviews}


CAL_LEN = 45


class TestCollectors(unittest.TestCase):
    def test_every_signal_is_internal_and_carries_a_number(self):
        ctx = _full_ctx()
        sigs, errors = internal.build_signals(ctx)
        self.assertEqual(errors, {})
        self.assertTrue(sigs)
        for s in sigs:
            self.assertEqual(s["family"], "internal")
            self.assertIn(s["source"], internal.SOURCES)
            self.assertEqual(s["as_of"], TODAY.isoformat())
            self.assertTrue(s["fact"].strip())
            if s["ref"] == "rev_quote":
                continue          # a verbatim guest quote is the fact; it needs no number
            self.assertTrue(any(ch.isdigit() for ch in s["fact"]),
                            "fact has no number: %s" % s["fact"])

    def test_occupancy_signal_speaks_the_real_numbers(self):
        ctx = _full_ctx()
        sigs = internal.collect_occupancy(ctx)
        tonight = [s for s in sigs if s["ref"] == "occ_tonight"][0]
        self.assertIn("45", tonight["fact"])
        self.assertIn("53", tonight["fact"])
        self.assertIn("85", tonight["fact"])        # 45/53 = 84.9 -> 85%
        lead = [s for s in sigs if s["ref"] == "occ_lead"][0]
        # synthetic bookings are made 1 day before arrivals spread over 10 days -> median 5
        self.assertEqual(internal.median_lead_days(ctx["res"]), 5.0)
        self.assertIn("5 يوم", lead["fact"])

    def test_ops_signal_reports_the_turnover(self):
        sigs = internal.collect_ops(_full_ctx())
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0]["source"], "ops")
        self.assertIn("2026-07-24", sigs[0]["detail"])

    def test_empty_context_yields_zero_signals_and_raises_nothing(self):
        ctx = _ctx()
        sigs, errors = internal.build_signals(ctx)
        self.assertEqual(errors, {})
        self.assertEqual(sigs, [])

    def test_source_filter(self):
        sigs, _ = internal.build_signals(_full_ctx(), sources=["reviews"])
        self.assertTrue(sigs)
        self.assertEqual({s["source"] for s in sigs}, {"reviews"})


class TestGatherResilience(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(HOST, k, None)
                       for k in ("listings", "inhouse", "res_window",
                                 "forward_calendar", "reviews", "now", "save_json")}

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(HOST, k, v)

    def _boom(self, *a, **kw):
        raise RuntimeError("Hostaway down")

    def test_every_tap_failing_still_returns_an_empty_context(self):
        HOST.now = lambda: datetime(2026, 7, 23, 9, 0, 0)
        HOST.listings = self._boom
        HOST.inhouse = self._boom
        HOST.res_window = self._boom
        HOST.forward_calendar = self._boom
        HOST.reviews = self._boom
        ctx = internal.gather()
        self.assertEqual(ctx["today"], TODAY)
        self.assertEqual(ctx["listings"], {})
        self.assertEqual(ctx["inhouse"], [])
        self.assertEqual(ctx["res"], [])
        self.assertEqual(ctx["cal"], [])
        self.assertEqual(ctx["reviews"], [])
        sigs, errors = internal.build_signals(ctx)
        self.assertEqual(sigs, [])
        self.assertEqual(errors, {})

    def test_one_failing_tap_does_not_kill_the_others(self):
        HOST.now = lambda: datetime(2026, 7, 23, 9, 0, 0)
        full = _full_ctx()
        HOST.listings = lambda: full["listings"]
        HOST.inhouse = lambda d: full["inhouse"]
        HOST.res_window = self._boom                       # only this one dies
        HOST.forward_calendar = lambda n: full["cal"]
        HOST.reviews = lambda: full["reviews"]
        ctx = internal.gather()
        self.assertEqual(ctx["res"], [])
        self.assertTrue(ctx["cal"])
        sigs, _ = internal.build_signals(ctx)
        self.assertIn("pricing", {s["source"] for s in sigs})
        self.assertIn("reviews", {s["source"] for s in sigs})


class TestCollectPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="studiointernal_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        sdb.reset_init_cache()
        self._saved = {k: getattr(HOST, k, None)
                       for k in ("listings", "inhouse", "res_window",
                                 "forward_calendar", "reviews", "now", "save_json")}
        full = _full_ctx()
        HOST.now = lambda: datetime(2026, 7, 23, 9, 0, 0)
        HOST.save_json = None
        HOST.listings = lambda: full["listings"]
        HOST.inhouse = lambda d: full["inhouse"]
        HOST.res_window = lambda a, b: full["res"]
        HOST.forward_calendar = lambda n: full["cal"]
        HOST.reviews = lambda: full["reviews"]
        internal.PROGRESS.clear()
        internal.PROGRESS["running"] = False

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(HOST, k, v)

    def test_collect_persists_then_dedups_on_rerun(self):
        fresh = internal.collect()
        self.assertTrue(fresh)
        stored = sdb.signals(family="internal", limit=200)
        self.assertEqual(len(stored), len(fresh))
        for row in stored:
            self.assertTrue(row["nkey"])
            self.assertEqual(row["as_of"], TODAY.isoformat())
        again = internal.collect()
        self.assertEqual(again, [])                 # nothing new — novelty gate held
        self.assertEqual(len(sdb.signals(family="internal", limit=200)), len(fresh))
        snap = internal.snapshot()
        self.assertTrue(snap["done"])
        self.assertFalse(snap["running"])

    def test_one_raising_collector_still_returns_the_others(self):
        original = internal.COLLECTORS

        def _explode(ctx):
            raise ValueError("collector blew up")

        internal.COLLECTORS = tuple(
            (name, _explode if name == "occupancy" else fn) for name, fn in original)
        try:
            fresh = internal.collect()
        finally:
            internal.COLLECTORS = original
        self.assertTrue(fresh)
        sources = {s["source"] for s in fresh}
        self.assertNotIn("occupancy", sources)
        self.assertTrue(sources & {"pricing", "reviews", "ops", "insider"})
        self.assertIn("occupancy", internal.snapshot()["errors"])


if __name__ == "__main__":
    unittest.main()
