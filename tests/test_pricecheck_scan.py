# -*- coding: utf-8 -*-
"""
Synthetic end-to-end test of pricecheck.scan — fake Hostaway, real logic.

Proves on made-up data that the scan finds a price an employee edited, before it is ever
trusted against live money (CLAUDE.md: "run a quick synthetic-data logic test for any new
computation"). Also pins the two promises the owner was given:
  • the scan reads the window, never the truncating history cache
  • the scan performs no write of any kind
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pricecheck import engine, scan
from pricecheck.host import HOST


LISTINGS = {11: "Ouja | 11B Royal", 12: "Ouja | 12A Royal"}

# Three direct bookings on one unit. #2 is the one an employee edited in the phone app:
# the calendar says 1416, the reservation says 1000.
RES = [
    {"id": 900, "listingMapId": 11, "arrivalDate": "2026-07-01",
     "departureDate": "2026-07-03", "status": "new", "channelName": "direct",
     "guestName": "Salem M Alzahrani", "totalPrice": 1416.0, "cleaningFee": 0.0},
    {"id": 901, "listingMapId": 11, "arrivalDate": "2026-07-05",
     "departureDate": "2026-07-07", "status": "modified", "channelName": "direct",
     "guestName": "Reem Ali", "totalPrice": 1000.0, "cleaningFee": 0.0},
    {"id": 902, "listingMapId": 12, "arrivalDate": "2026-07-09",
     "departureDate": "2026-07-10", "status": "new", "channelName": "direct",
     "guestName": "Rsa Alshehri", "totalPrice": 708.0, "cleaningFee": 0.0},
    # Airbnb — excluded by the default channel filter
    {"id": 903, "listingMapId": 11, "arrivalDate": "2026-07-11",
     "departureDate": "2026-07-12", "status": "new", "channelName": "Airbnb",
     "guestName": "Mishal", "totalPrice": 920.0},
    # Cancelled — excluded unless asked for
    {"id": 904, "listingMapId": 11, "arrivalDate": "2026-07-13",
     "departureDate": "2026-07-14", "status": "cancelled", "channelName": "direct",
     "guestName": "Mohmad", "totalPrice": 0.0},
]

CAL = {
    11: [{"date": "2026-07-01", "price": 708, "reservationId": 900},
         {"date": "2026-07-02", "price": 708, "reservationId": 900},
         {"date": "2026-07-05", "price": 708, "reservationId": 901},
         {"date": "2026-07-06", "price": 708, "reservationId": 901},
         {"date": "2026-07-11", "price": 920, "reservationId": 903},
         {"date": "2026-07-13", "price": 700, "reservationId": None}],
    12: [{"date": "2026-07-09", "price": 708, "reservationId": 902}],
}


class _Fake:
    """Records every call, so 'read-only' is proven rather than asserted."""

    def __init__(self):
        self.window_calls, self.cal_calls, self.get_calls = [], [], []

    def window(self, start, end, pad_days=45):
        self.window_calls.append((start, end))
        return [dict(r) for r in RES]

    def calendar(self, lid, start, end):
        self.cal_calls.append((lid, start, end))
        return [dict(d) for d in CAL.get(lid, [])]

    def api_get(self, path, params=None):
        self.get_calls.append(path)
        rid = int(str(path).rsplit("/", 1)[-1])
        for r in RES:
            if r["id"] == rid:
                return {"result": dict(r, financeField=[
                    {"name": "baseRate", "amount": r["totalPrice"]}])}
        return {}


class PriceCheckScanTest(unittest.TestCase):

    def setUp(self):
        self.fake = _Fake()
        HOST.__dict__.clear()
        scan.HOST.dash_auth = lambda r: True
        scan.HOST.fetch_reservations_window = self.fake.window
        scan.HOST.fetch_calendar_days = self.fake.calendar
        scan.HOST.api_get = self.fake.api_get
        scan.HOST.get_listings_map = lambda: LISTINGS

    def _scan(self, **kw):
        return scan.scan(date(2026, 7, 1), date(2026, 8, 1), **kw)

    def test_finds_the_edited_booking_and_leaves_the_healthy_ones_alone(self):
        out = self._scan()
        by_id = {r["id"]: r for r in out["rows"]}
        self.assertEqual(by_id[900]["status"], "ok")
        self.assertEqual(by_id[902]["status"], "ok")
        self.assertEqual(by_id[901]["status"], "differs")
        self.assertAlmostEqual(by_id[901]["calendar_total"], 1416.0)
        self.assertAlmostEqual(by_id[901]["money"]["totalPrice"], 1000.0)

    def test_the_field_that_matches_the_calendar_is_named_from_the_data(self):
        out = self._scan()
        top = out["ranking"][0]
        self.assertEqual(top["field"], "totalPrice")
        self.assertEqual(top["agrees"], 2)      # 900 and 902
        self.assertEqual(top["compared"], 3)

    def test_verdict_totals_the_money_at_stake(self):
        out = self._scan()
        v = engine.verdict(out["rows"], "totalPrice")
        self.assertEqual(v["counts"]["wrong"], 1)
        self.assertAlmostEqual(v["total_gap"], -416.0)   # Hostaway UNDER the calendar

    def test_default_channel_is_direct_and_cancelled_stay_out(self):
        ids = {r["id"] for r in self._scan()["rows"]}
        self.assertEqual(ids, {900, 901, 902})
        ids_all = {r["id"] for r in self._scan(channel="all")["rows"]}
        self.assertIn(903, ids_all)
        ids_c = {r["id"] for r in self._scan(include_cancelled=True)["rows"]}
        self.assertIn(904, ids_c)

    def test_one_calendar_call_per_listing_not_per_booking(self):
        self._scan()
        self.assertEqual(len(self.fake.cal_calls), 2)
        self.assertEqual(sorted(c[0] for c in self.fake.cal_calls), [11, 12])

    def test_uses_the_window_fetch_never_the_truncating_history_cache(self):
        self._scan()
        self.assertEqual(len(self.fake.window_calls), 1)
        self.assertEqual(self.fake.window_calls[0][0], date(2026, 7, 1))

    def test_deep_mode_reads_details_and_exposes_the_finance_breakdown(self):
        out = self._scan(deep=True)
        by_id = {r["id"]: r for r in out["rows"]}
        self.assertIn("financeField.baseRate", by_id[901]["money"])
        self.assertEqual(out["meta"]["deep_fetched"], 3)
        self.assertTrue(all(p.startswith("/reservations/") for p in self.fake.get_calls))

    def test_shallow_mode_makes_no_per_reservation_calls(self):
        self._scan()
        self.assertEqual(self.fake.get_calls, [])

    def test_a_broken_calendar_never_becomes_a_price_accusation(self):
        scan.HOST.fetch_calendar_days = lambda lid, s, e: (_ for _ in ()).throw(
            RuntimeError("429 rate limited"))
        out = self._scan()
        self.assertTrue(all(r["status"] == "uncertain" for r in out["rows"]))
        self.assertEqual(engine.verdict(out["rows"], "totalPrice")["counts"]["wrong"], 0)
        self.assertEqual(len(out["meta"]["calendar_errors"]), 2)

    def test_the_package_contains_no_write_call_at_all(self):
        import pathlib
        here = pathlib.Path(__file__).resolve().parent.parent / "pricecheck"
        for f in here.glob("*.py"):
            src = f.read_text(encoding="utf-8")
            for banned in ("api_put", "api_post", "add_post", "add_put", "add_delete"):
                self.assertNotIn(banned, src,
                                 "%s must stay read-only but mentions %s" % (f.name, banned))


if __name__ == "__main__":
    unittest.main()
