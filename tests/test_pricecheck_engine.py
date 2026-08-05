# -*- coding: utf-8 -*-
"""
Tests for pricecheck.engine — the price-disagreement examiner.

The owner's rule, 2026-08-05: THE CALENDAR IS THE TRUTH. An employee creates a manual
direct booking in the Hostaway mobile app, edits the price, and afterwards the calendar
and Financial Reporting → Rental Activity → «Rental Revenue» disagree.

These tests lock the two things that must never be guessed:
  1. A night is only counted when the calendar says it belongs to THIS reservation.
     Partial data produces "uncertain", never a difference. A wrong difference sends a
     human to change a price that was already correct.
  2. We do not hardcode which Hostaway field is «Rental Revenue». The engine measures
     which field agrees with the calendar across the whole portfolio and reports it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pricecheck import engine


def _cal(lid_days):
    """[(date, price, reservationId)] -> Hostaway-shaped calendar rows."""
    return [{"date": d, "price": p, "reservationId": r, "isAvailable": 0}
            for (d, p, r) in lid_days]


def _res(**kw):
    base = {"id": 900, "listingMapId": 11, "arrivalDate": "2026-07-01",
            "departureDate": "2026-07-03", "status": "new", "channelName": "direct",
            "guestName": "Salem", "totalPrice": 1416.0}
    base.update(kw)
    return base


class TestCalendarSlice(unittest.TestCase):

    def test_sums_only_this_reservations_nights_and_excludes_checkout_night(self):
        cal = _cal([("2026-06-30", 500, None), ("2026-07-01", 708, 900),
                    ("2026-07-02", 708, 900), ("2026-07-03", 999, 901)])
        s = engine.calendar_slice(cal, 900, "2026-07-01", "2026-07-03")
        self.assertEqual(s["nights_expected"], 2)
        self.assertEqual(s["nights_matched"], 2)
        self.assertAlmostEqual(s["total"], 1416.0)
        self.assertTrue(s["complete"])

    def test_missing_night_is_uncertain_never_a_partial_total(self):
        cal = _cal([("2026-07-01", 708, 900)])           # night 2 absent from the payload
        s = engine.calendar_slice(cal, 900, "2026-07-01", "2026-07-03")
        self.assertEqual(s["nights_expected"], 2)
        self.assertEqual(s["nights_matched"], 1)
        self.assertFalse(s["complete"])

    def test_night_owned_by_another_reservation_is_not_counted(self):
        cal = _cal([("2026-07-01", 708, 900), ("2026-07-02", 708, 777)])
        s = engine.calendar_slice(cal, 900, "2026-07-01", "2026-07-03")
        self.assertEqual(s["nights_matched"], 1)
        self.assertFalse(s["complete"])

    def test_reservation_id_compared_as_text_so_900_matches_string_900(self):
        cal = _cal([("2026-07-01", 708, "900"), ("2026-07-02", 708, "900")])
        s = engine.calendar_slice(cal, 900, "2026-07-01", "2026-07-03")
        self.assertEqual(s["nights_matched"], 2)
        self.assertAlmostEqual(s["total"], 1416.0)

    def test_zero_priced_night_is_a_real_night_not_a_missing_one(self):
        cal = _cal([("2026-07-01", 0, 900), ("2026-07-02", 708, 900)])
        s = engine.calendar_slice(cal, 900, "2026-07-01", "2026-07-03")
        self.assertEqual(s["nights_matched"], 2)
        self.assertTrue(s["complete"])
        self.assertAlmostEqual(s["total"], 708.0)


class TestHarvestMoney(unittest.TestCase):

    def test_picks_money_fields_and_skips_ids_and_counts(self):
        m = engine.harvest_money(_res(totalPrice=1416.0, cleaningFee=100.0,
                                      numberOfGuests=3, listingMapId=11, id=900,
                                      channelId=2000, nights=2))
        self.assertIn("totalPrice", m)
        self.assertIn("cleaningFee", m)
        for junk in ("numberOfGuests", "listingMapId", "id", "channelId", "nights"):
            self.assertNotIn(junk, m)

    def test_paid_fields_survive_the_id_filter(self):
        # 'totalPaid' and 'alreadyPaid' end in the letters i-d. Only a capital 'Id'
        # suffix means an identifier — this guard is why they are not silently dropped.
        m = engine.harvest_money(_res(totalPaid=1416.0, alreadyPaid=700.0))
        self.assertIn("totalPaid", m)
        self.assertIn("alreadyPaid", m)

    def test_flattens_the_finance_field_breakdown(self):
        r = _res(financeField=[{"name": "baseRate", "amount": 1416.0},
                               {"name": "cleaningFee", "value": 100.0}])
        m = engine.harvest_money(r)
        self.assertAlmostEqual(m["financeField.baseRate"], 1416.0)
        self.assertAlmostEqual(m["financeField.cleaningFee"], 100.0)

    def test_booleans_and_percentages_are_not_money(self):
        m = engine.harvest_money(_res(isPaid=True, channelCommissionPercent=3.0))
        self.assertNotIn("isPaid", m)
        self.assertNotIn("channelCommissionPercent", m)


class TestCompareRow(unittest.TestCase):

    def test_agreeing_field_is_reported_and_row_matches(self):
        cal = _cal([("2026-07-01", 708, 900), ("2026-07-02", 708, 900)])
        row = engine.compare_row(_res(totalPrice=1416.0, cleaningFee=100.0), cal)
        self.assertEqual(row["status"], "ok")
        self.assertIn("totalPrice", row["agree"])
        self.assertNotIn("cleaningFee", row["agree"])
        self.assertAlmostEqual(row["calendar_total"], 1416.0)

    def test_edited_price_shows_up_as_a_difference(self):
        cal = _cal([("2026-07-01", 708, 900), ("2026-07-02", 708, 900)])
        row = engine.compare_row(_res(totalPrice=1000.0), cal)
        self.assertEqual(row["status"], "differs")
        self.assertEqual(row["agree"], [])
        self.assertAlmostEqual(row["money"]["totalPrice"] - row["calendar_total"], -416.0)

    def test_incomplete_calendar_never_produces_a_difference(self):
        cal = _cal([("2026-07-01", 708, 900)])
        row = engine.compare_row(_res(totalPrice=1000.0), cal)
        self.assertEqual(row["status"], "uncertain")
        self.assertIsNone(row["calendar_total"])

    def test_half_riyal_rounding_is_not_a_disagreement(self):
        cal = _cal([("2026-07-01", 708.0, 900), ("2026-07-02", 708.0, 900)])
        row = engine.compare_row(_res(totalPrice=1416.30), cal)
        self.assertEqual(row["status"], "ok")


class TestFieldAgreement(unittest.TestCase):

    def test_the_field_that_tracks_the_calendar_is_identified_from_the_data(self):
        # Three bookings. 'baseRate' follows the calendar every time; 'totalPrice'
        # carries a cleaning fee so it never does. Nobody told the engine this.
        rows = []
        for i, nightly in enumerate((700.0, 800.0, 900.0)):
            cal = _cal([("2026-07-0%d" % (i + 1), nightly, 900 + i)])
            r = _res(id=900 + i, arrivalDate="2026-07-0%d" % (i + 1),
                     departureDate="2026-07-0%d" % (i + 2),
                     totalPrice=nightly + 100.0, baseRate=nightly)
            rows.append(engine.compare_row(r, cal))
        rank = engine.field_agreement(rows)
        self.assertEqual(rank[0]["field"], "baseRate")
        self.assertEqual(rank[0]["agrees"], 3)
        tp = [x for x in rank if x["field"] == "totalPrice"][0]
        self.assertEqual(tp["agrees"], 0)

    def test_uncertain_rows_are_excluded_from_the_scoring(self):
        cal = _cal([("2026-07-01", 708, 900)])           # one of two nights only
        rows = [engine.compare_row(_res(totalPrice=708.0), cal)]
        rank = engine.field_agreement(rows)
        self.assertTrue(all(x["compared"] == 0 for x in rank))


class TestVerdict(unittest.TestCase):

    def test_verdict_splits_rows_against_the_chosen_field(self):
        good = _cal([("2026-07-01", 708, 900), ("2026-07-02", 708, 900)])
        bad = _cal([("2026-07-05", 708, 901), ("2026-07-06", 708, 901)])
        rows = [
            engine.compare_row(_res(id=900, totalPrice=1416.0), good),
            engine.compare_row(_res(id=901, arrivalDate="2026-07-05",
                                    departureDate="2026-07-07",
                                    totalPrice=900.0), bad),
        ]
        v = engine.verdict(rows, "totalPrice")
        self.assertEqual(v["field"], "totalPrice")
        self.assertEqual(v["ok"], 1)
        self.assertEqual(len(v["wrong"]), 1)
        self.assertEqual(v["wrong"][0]["id"], 901)
        self.assertAlmostEqual(v["wrong"][0]["gap"], -516.0)
        self.assertAlmostEqual(v["total_gap"], -516.0)

    def test_a_row_missing_the_chosen_field_is_flagged_not_scored_as_zero(self):
        cal = _cal([("2026-07-01", 708, 900), ("2026-07-02", 708, 900)])
        rows = [engine.compare_row(_res(totalPrice=1416.0), cal)]
        v = engine.verdict(rows, "baseRate")
        self.assertEqual(v["ok"], 0)
        self.assertEqual(len(v["wrong"]), 0)
        self.assertEqual(len(v["unknown"]), 1)


if __name__ == "__main__":
    unittest.main()
