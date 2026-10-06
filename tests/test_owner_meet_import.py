# -*- coding: utf-8 -*-
"""The Airbnb «Host Opportunity Report v5 — Promotions» importer (gate G10).

Every fixture fact is checked twice: against the brief's stated number AND against a figure this test
computes itself from the raw TSV with the csv module — so a parser that agrees with itself cannot
pass by accident.

Run: python3 -m unittest tests.test_owner_meet_import
"""
import csv
import io
import os
import statistics
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain import db as bdb  # noqa: E402
from owner_meet import abnb, airbnb_import, db  # noqa: E402
from owner_meet.host import HOST  # noqa: E402

TSV = ROOT / "tests" / "fixtures" / "owner_meet" / "host_opportunity_2026-10-04.tsv"
DATA = TSV.read_bytes()


def _raw():
    """Independent read of the same file — plain csv, positions found by name."""
    rows = list(csv.reader(io.StringIO(DATA.decode("utf-8")), delimiter="\t"))
    h = [c.strip() for c in rows[4]]
    body = [r for r in rows[5:] if any(c.strip() for c in r)]
    col = lambda name: h.index(name)
    num = lambda s: float(s.replace("$", "").replace(",", "").replace("★", "").strip()) if s.strip() else None
    return {
        "n": len(body),
        "gbv": sum(num(r[col("Gross Booking Value YTD (USD)")]) or 0 for r in body),
        "ratings": [num(r[col("Lifetime Overall Rating")]) for r in body],
        "ranks": sorted(int(r[col("Opportunity Rank")]) for r in body),
        "avail_blank": sum(1 for r in body if len(r) <= col("Your Available Nights Next 14 Days")
                           or not r[col("Your Available Nights Next 14 Days")].strip()),
    }


class ParseTheRealFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = airbnb_import.parse(DATA, TSV.name)
        cls.raw = _raw()

    def test_42_rows_and_data_as_of(self):
        self.assertEqual(len(self.p["rows"]), 42)
        self.assertEqual(len(self.p["rows"]), self.raw["n"])
        self.assertEqual(self.p["data_as_of"], "2026-10-04")
        self.assertEqual(self.p["missing"], [])

    def test_rank_8_is_absent_and_nothing_crashes(self):
        ranks = sorted(r["rank"] for r in self.p["rows"])
        self.assertNotIn(8, ranks)
        self.assertEqual(ranks, self.raw["ranks"])

    def test_blank_availability_is_none_not_zero(self):
        blanks = [r for r in self.p["rows"] if r["avail_14"] is None]
        self.assertEqual(len(blanks), 8)
        self.assertEqual(len(blanks), self.raw["avail_blank"])

    def test_gbv_total(self):
        self.assertEqual(round(sum(r["gbv_usd"] or 0 for r in self.p["rows"])), 896734)
        self.assertEqual(round(sum(r["gbv_usd"] or 0 for r in self.p["rows"])), round(self.raw["gbv"]))

    def test_ratings_median_and_below_target(self):
        rs = [r["rating"] for r in self.p["rows"] if r["rating"] is not None]
        self.assertAlmostEqual(statistics.median(rs), 4.815, places=6)
        self.assertEqual(sum(1 for x in rs if x < 4.75), 15)
        self.assertEqual(rs, [x for x in self.raw["ratings"] if x is not None])

    def test_duplicate_header_names_are_told_apart_by_group(self):
        r = next(x for x in self.p["rows"] if x["rank"] == 1)
        self.assertEqual(r["weekly_similar"], {"lo": 0.10, "hi": 0.15})
        self.assertEqual(r["monthly_similar"], {"lo": 0.20, "hi": 0.25})
        self.assertEqual(r["airbnb_id"], "1769664657811048817")
        self.assertEqual(r["search_to_booking"], 0.0007)

    def test_xlsx_round_trip_gives_identical_rows(self):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        for row in csv.reader(io.StringIO(DATA.decode("utf-8")), delimiter="\t"):
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        px = airbnb_import.parse(buf.getvalue(), "report.xlsx")
        self.assertEqual(px["rows"], self.p["rows"])
        self.assertEqual(px["data_as_of"], "2026-10-04")

    def test_a_malformed_file_is_refused_in_arabic(self):
        for bad in (b"just,some,csv" + bytes([10]) + b"1,2,3", b"", "عربي فقط".encode("utf-8")):
            with self.assertRaises(ValueError) as cm:
                airbnb_import.parse(bad, "x.csv")
            self.assertTrue(any(ord(ch) > 0x600 for ch in str(cm.exception)), str(cm.exception))


class StoreAndMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db._inited.clear()
        self.saved = (HOST.airbnb_room_ids, HOST.listing_titles, HOST.state_dir)
        HOST.state_dir = self.tmp

    def tearDown(self):
        HOST.airbnb_room_ids, HOST.listing_titles, HOST.state_dir = self.saved

    def test_an_import_is_a_dated_snapshot_never_overwritten(self):
        first = abnb.import_file(DATA, "a.tsv", "t")
        again = abnb.import_file(DATA, "a.tsv", "t")
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["import_id"], first["import_id"])
        older = DATA.replace(b"2026-10-04", b"2026-09-01")
        second = abnb.import_file(older, "b.tsv", "t")
        self.assertNotEqual(second["import_id"], first["import_id"])
        self.assertEqual(len(abnb.imports()), 2)
        imp, rows = abnb.latest("2026-10-05")
        self.assertEqual(imp["data_as_of"], "2026-10-04")
        imp, rows = abnb.latest("2026-09-15")
        self.assertEqual(imp["data_as_of"], "2026-09-01", "a meeting reads the newest report AT OR BEFORE its date")
        self.assertEqual(len(rows), 42)

    def test_mapping_trusts_hostaway_then_confirmations_and_lists_the_rest(self):
        abnb.import_file(DATA, "a.tsv", "t")
        _imp, rows = abnb.latest()
        ids = sorted(rows, key=lambda a: rows[a]["rank"])
        HOST.airbnb_room_ids = lambda: {501: ids[0]}
        HOST.listing_titles = lambda: {501: "x", 502: rows[ids[1]]["title_clean"], 503: "Completely different"}
        mp = abnb.mapping(rows)
        self.assertEqual(mp["by_airbnb"][ids[0]], {"lid": 501, "method": "payload"})
        self.assertEqual(len(mp["by_airbnb"]) + len(mp["unmapped"]), 42, "unmapped rows are listed, never dropped")
        sug = next(u for u in mp["unmapped"] if u["airbnb_id"] == ids[1])["suggest"]
        self.assertEqual(sug["lid"], 502)
        self.assertNotIn(ids[1], mp["by_airbnb"], "a suggestion is never used until somebody confirms it")
        lids_suggested = [u["suggest"]["lid"] for u in mp["unmapped"] if u["suggest"]]
        self.assertEqual(len(lids_suggested), len(set(lids_suggested)), "one unit is suggested for one row at most")
        abnb.confirm(ids[1], 502, "Faisal")
        mp = abnb.mapping(rows)
        self.assertEqual(mp["by_airbnb"][ids[1]], {"lid": 502, "method": "manual"})
        self.assertEqual(mp["by_lid"][502], ids[1])


if __name__ == "__main__":
    unittest.main()
