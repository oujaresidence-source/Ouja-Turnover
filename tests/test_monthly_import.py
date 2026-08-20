# -*- coding: utf-8 -*-
"""
The Hostaway CSV import. Checked against the SHAPE of the owner's real export
(20260613_reservations_filtered), including its quoted commas, its Arabic
listing names and its eight status values.

Run: python3 -m unittest tests.test_monthly_import
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import importer                              # noqa: E402

HEADER = ('"Guest name","Check-in date","Check-out date",Channel,"Total price",'
          'Currency,"Number of nights",Status,Listing,"Hostaway reservation ID"')


def row(ci, co, total, status="new", listing="F1", rid="1", guest="Ali"):
    return '"%s",%s,%s,airbnbOfficial,%s,SAR,1,%s,"%s",%s' % (
        guest, ci, co, total, status, listing, rid)


def csv(*rows):
    return "\n".join([HEADER] + list(rows))


class HeaderMatchingTest(unittest.TestCase):
    def test_it_reads_the_real_export_header(self):
        rows, rep = importer.parse(csv(row("2026-08-01", "2026-08-11", "6200")))
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["kept"], 1)

    def test_a_missing_column_is_named_rather_than_guessed(self):
        rows, rep = importer.parse("Guest name,Check-in date\nAli,2026-08-01")
        self.assertFalse(rep["ok"])
        self.assertIn("checkout", rep["missing"])
        self.assertIn("total", rep["missing"])

    def test_alternative_column_names_are_accepted(self):
        alt = "arrivalDate,departureDate,totalPrice,status,listingName\n" \
              "2026-08-01,2026-08-11,6200,new,F1"
        rows, rep = importer.parse(alt)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["kept"], 1)


class RowsTest(unittest.TestCase):
    def test_it_produces_the_same_field_names_the_live_path_produces(self):
        rows, _ = importer.parse(csv(row("2026-08-01", "2026-08-11", "6200")))
        r = rows[0]
        for k in ("arrivalDate", "departureDate", "totalPrice", "status", "id"):
            self.assertIn(k, r)
        self.assertEqual(r["arrivalDate"], "2026-08-01")
        self.assertEqual(r["totalPrice"], 6200.0)

    def test_a_quoted_comma_in_a_name_does_not_shift_the_columns(self):
        r = row("2026-08-01", "2026-08-11", "6200", guest="Ali, Jr")
        rows, rep = importer.parse(csv(r))
        self.assertEqual(rep["kept"], 1)
        self.assertEqual(rows[0]["totalPrice"], 6200.0)

    def test_arabic_listing_names_survive(self):
        rows, _ = importer.parse(csv(row("2026-08-01", "2026-08-11", "6200",
                                         listing="B02 - الغدير")))
        self.assertEqual(rows[0]["listingName"], "B02 - الغدير")

    def test_every_status_in_the_real_export_is_counted(self):
        rs = [row("2026-08-0%d" % (i + 1), "2026-08-11", "6200", st, rid=str(i))
              for i, st in enumerate(("new", "inquiry", "cancelled", "modified",
                                      "declined", "expired", "ownerStay",
                                      "inquiryPreapproved"))]
        _rows, rep = importer.parse(csv(*rs))
        self.assertEqual(rep["confirmed"], 2)            # new + modified only
        self.assertEqual(len(rep["statuses"]), 8)

    def test_duplicate_reservation_ids_are_counted_not_silently_merged(self):
        _rows, rep = importer.parse(csv(row("2026-08-01", "2026-08-11", "6200", rid="9"),
                                        row("2026-08-01", "2026-08-11", "6200", rid="9")))
        self.assertEqual(rep["kept"], 1)
        self.assertEqual(rep["duplicates"], 1)

    def test_every_dropped_row_is_counted_with_a_reason(self):
        rows, rep = importer.parse(csv(
            row("2026-08-01", "2026-08-11", "6200", rid="1"),
            row("2026-08-01", "2026-08-11", "0", rid="2"),
            row("bad-date", "2026-08-11", "6200", rid="3"),
            row("2026-08-11", "2026-08-01", "6200", rid="4")))
        self.assertEqual(rep["kept"], 1)
        self.assertEqual(rep["dropped_no_price"], 1)
        self.assertEqual(rep["dropped_bad_dates"], 2)
        total = (rep["kept"] + rep["dropped_no_price"] + rep["dropped_bad_dates"]
                 + rep["dropped_no_listing"] + rep["duplicates"])
        self.assertEqual(total, rep["read"], "a row vanished without a reason")

    def test_the_date_range_is_reported(self):
        _rows, rep = importer.parse(csv(
            row("2025-01-05", "2025-01-11", "6200", rid="1"),
            row("2026-08-01", "2026-08-11", "6200", rid="2")))
        self.assertEqual(rep["first"], "2025-01-05")
        self.assertEqual(rep["last"], "2026-08-01")


class JoinTest(unittest.TestCase):
    META = {461328: {"name": "C2 NFL", "public_name": "Biggest 2BR"},
            479967: {"name": "F1", "public_name": "F1 public"}}

    def test_it_joins_on_the_internal_name_the_export_uses(self):
        rows, _ = importer.parse(csv(row("2026-08-01", "2026-08-11", "6200",
                                         listing="C2 NFL")))
        out, unmatched = importer.attach_listing_ids(rows, self.META)
        self.assertEqual(out[0]["listingMapId"], 461328)
        self.assertEqual(unmatched, {})

    def test_the_public_name_also_matches(self):
        rows, _ = importer.parse(csv(row("2026-08-01", "2026-08-11", "6200",
                                         listing="Biggest 2BR")))
        out, _u = importer.attach_listing_ids(rows, self.META)
        self.assertEqual(out[0]["listingMapId"], 461328)

    def test_an_unmatched_name_is_reported_not_dropped_quietly(self):
        rows, _ = importer.parse(csv(row("2026-08-01", "2026-08-11", "6200",
                                         listing="A Unit We Renamed")))
        out, unmatched = importer.attach_listing_ids(rows, self.META)
        self.assertEqual(out, [])
        self.assertEqual(unmatched, {"A Unit We Renamed": 1})


if __name__ == "__main__":
    unittest.main()
