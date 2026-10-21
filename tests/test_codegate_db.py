# tests/test_codegate_db.py
# -*- coding: utf-8 -*-
"""«تسليم الرموز» storage. Run: python3 -m unittest tests.test_codegate_db"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain import db as bdb  # noqa: E402
from codegate import db  # noqa: E402

DAY = "2026-10-21"


def row(res_id="r1", **kw):
    r = {"res_id": res_id, "lid": 461328, "day": DAY, "unit": "C2 NFL", "guest": "Sara",
         "conversation_id": "c1", "checkin_at": DAY + "T16:00:00+03:00", "cover_name": "نورة",
         "cover_did": "11", "cover_role_id": "", "owner_did": "22"}
    r.update(kw)
    return r


class TestDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cg_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()

    def test_upsert_is_one_row_and_keeps_release(self):
        db.upsert_arrival(row())
        self.assertTrue(db.release("r1", "نورة", "11", DAY + "T14:00:00+03:00"))
        db.upsert_arrival(row(guest="Sara A."))
        it = db.get("r1")
        self.assertEqual(it["guest"], "Sara A.")
        self.assertEqual(it["released_by"], "نورة")
        self.assertEqual(len(db.day_items(DAY)), 1)

    def test_release_first_wins_and_undo_reopens(self):
        db.upsert_arrival(row())
        self.assertTrue(db.release("r1", "نورة", "11", "t1"))
        self.assertFalse(db.release("r1", "ناصر", "33", "t2"))
        self.assertEqual(db.get("r1")["released_by"], "نورة")
        self.assertTrue(db.undo("r1", "admin", "t3"))
        self.assertIsNone(db.get("r1")["released_at"])
        self.assertTrue(db.release("r1", "ناصر", "33", "t4"))

    def test_card_lookup_by_message(self):
        db.upsert_arrival(row())
        db.set_card("r1", "900", "555", "h")
        self.assertEqual(db.item_by_message("555")["res_id"], "r1")
        self.assertIsNone(db.item_by_message("556"))

    def test_replies_roundtrip(self):
        db.upsert_arrival(row())
        db.set_replies("r1", DAY + "T10:00:00+03:00",
                       [{"at": DAY + "T10:05:00+03:00", "text": "I agree"}])
        it = db.get("r1")
        self.assertEqual(it["replies"][0]["text"], "I agree")
        self.assertEqual(it["rules_at"], DAY + "T10:00:00+03:00")

    def test_stamp_whitelist(self):
        db.upsert_arrival(row())
        db.stamp("r1", "alert_2h_at", "t")
        self.assertEqual(db.get("r1")["alert_2h_at"], "t")
        with self.assertRaises(ValueError):
            db.stamp("r1", "released_by", "evil")

    def test_mark_cancelled_and_revive(self):
        db.upsert_arrival(row("r1"))
        db.upsert_arrival(row("r2"))
        self.assertEqual(db.mark_cancelled(DAY, {"r1"}), ["r2"])
        self.assertEqual(db.get("r2")["cancelled"], 1)
        db.upsert_arrival(row("r2"))
        self.assertEqual(db.get("r2")["cancelled"], 0)

    def test_header_latch(self):
        self.assertFalse(db.header_posted(DAY, "11"))
        db.mark_header(DAY, "11", "777")
        self.assertTrue(db.header_posted(DAY, "11"))
        db.reset_init_cache()                      # a "restart"
        self.assertTrue(db.header_posted(DAY, "11"))


if __name__ == "__main__":
    unittest.main()
