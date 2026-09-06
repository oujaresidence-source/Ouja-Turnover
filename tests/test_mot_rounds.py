# -*- coding: utf-8 -*-
"""
Rounds, locked.

    one OPEN round per apartment — the partial unique index refuses the second
    a CLOSED round refuses every result write — a correction opens a NEW round
    a token opens only an OPEN round; closing the round kills the token

Run: python3 -m unittest tests.test_mot_rounds
"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb   # noqa: E402
from mot import db            # noqa: E402


class MotDbCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mottest_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def open(self, lid=501, pool=False):
        return db.open_round(lid, "Ouja | Test %d" % lid, "2026-09", pool, "decor",
                             67 if pool else 61, by="فيصل")


class TestOneOpenRound(MotDbCase):
    def test_sqlite_refuses_the_second_open_round(self):
        self.open()
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("""INSERT INTO mot_inspection(listing_id, catalogue_version, has_pool,
                          denominator, opened_at) VALUES(501,'2026-09',0,61,'x')""")

    def test_application_layer_names_it(self):
        self.open()
        with self.assertRaises(db.RoundAlreadyOpen):
            self.open()

    def test_a_closed_round_frees_the_slot(self):
        rid = self.open()
        db.close_round(rid, 100.0, 100.0, "2026-09-20", None, "{}")
        rid2 = self.open()
        self.assertNotEqual(rid, rid2)
        self.assertEqual(len(db.rounds_for(501)), 2)

    def test_two_apartments_are_independent(self):
        self.open(501)
        self.open(502)
        self.assertEqual(db.counts()["open"], 2)


class TestImmutability(MotDbCase):
    def test_closed_round_rejects_result_writes(self):
        rid = self.open()
        db.set_result(rid, "c10.iron", "missing", by="x")
        db.close_round(rid, 0.0, 100.0, None, None, "{}")
        with self.assertRaises(db.RoundClosed):
            db.set_result(rid, "c10.iron", "available", by="x")
        with self.assertRaises(db.RoundClosed):
            db.add_photo(rid, "c10.iron", "mot_photos/1/a.jpg")
        with self.assertRaises(db.RoundClosed):
            db.close_round(rid, 1.0, 1.0, None, None, "{}")
        self.assertEqual(db.results(rid)["c10.iron"]["state"], "missing")

    def test_correction_is_a_new_round(self):
        rid = self.open()
        db.close_round(rid, 50.0, 100.0, None, None, "{}")
        rid2 = self.open()
        db.set_result(rid2, "c10.iron", "available", by="x")
        self.assertEqual(db.round_(rid)["compliance_pct"], 50.0)
        self.assertEqual(db.results(rid), {})

    def test_result_upsert_keeps_qty_and_billed(self):
        rid = self.open()
        db.set_result(rid, "c21.mattress", "missing", qty=3, billed_to="ouja", by="x")
        r = db.set_result(rid, "c21.mattress", "missing", note="مهترئة", by="y")
        self.assertEqual((r["qty"], r["billed_to"], r["note"]), (3, "ouja", "مهترئة"))

    def test_abandon_scores_nothing(self):
        rid = self.open()
        db.abandon_round(rid)
        r = db.round_(rid)
        self.assertEqual(r["note"], "abandoned")
        self.assertIsNone(r["compliance_pct"])
        self.assertNotIn(501, db.latest_closed_by_listing())


class TestTokens(MotDbCase):
    def test_token_reads_only_the_open_round(self):
        rid = self.open()
        tok = db.mint_token(rid, by="x")
        self.assertEqual(db.round_by_token(tok)["id"], rid)
        db.close_round(rid, 0.0, 100.0, None, None, "{}")
        self.assertIsNone(db.round_by_token(tok))
        self.assertIsNone(db.round_by_token("nope"))

    def test_expired_token_is_dead(self):
        rid = self.open()
        tok = db.mint_token(rid, by="x", days=-1)
        self.assertIsNone(db.round_by_token(tok))


class TestPrices(MotDbCase):
    def test_price_is_stamped(self):
        p = db.set_price("c10.iron", 150, by="فيصل")
        self.assertEqual((p["price_sar"], p["set_by"]), (150.0, "فيصل"))
        self.assertTrue(p["set_at"])


if __name__ == "__main__":
    unittest.main()
