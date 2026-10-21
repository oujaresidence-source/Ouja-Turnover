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


class TestMigration(unittest.TestCase):
    def test_prelive_column_added_to_an_old_table(self):
        from contextlib import closing
        tmp = tempfile.mkdtemp(prefix="cgm_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        db.reset_init_cache()
        old = db.SCHEMA.replace("    prelive_checked_at TEXT,\n", "")
        self.assertNotEqual(old, db.SCHEMA)
        with closing(bdb.connect()) as cx:
            cx.executescript(old)
            cx.execute("INSERT INTO codegate_items(res_id, day) VALUES ('old1', ?)", (DAY,))
            cx.commit()
            have = {r[1] for r in cx.execute("PRAGMA table_info(codegate_items)")}
        self.assertNotIn("prelive_checked_at", have)
        it = db.get("old1")                              # first call runs _ensure
        self.assertEqual(it["day"], DAY)
        self.assertIn("prelive_checked_at", it)
        self.assertIsNone(it["prelive_checked_at"])
        db.reset_init_cache()                            # second boot: idempotent
        self.assertIn("prelive_checked_at", db.get("old1"))

    def test_fresh_table_has_the_column(self):
        tmp = tempfile.mkdtemp(prefix="cgm_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        db.reset_init_cache()
        db.upsert_arrival(row())
        self.assertIn("prelive_checked_at", db.get("r1"))


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

    def test_settings_roundtrip_and_default(self):
        self.assertEqual(db.get_setting("live", "0"), "0")
        db.set_setting("live", "1", "Faisal")
        self.assertEqual(db.get_setting("live", "0"), "1")
        db.reset_init_cache()                      # a "restart"
        self.assertEqual(db.get_setting("live"), "1")
        db.set_setting("live", "0", "Faisal")
        self.assertEqual(db.get_setting("live"), "0")

    def test_moved_date_resets_card_alerts_and_release(self):
        db.upsert_arrival(row())
        db.set_card("r1", "900", "555", "h")
        db.stamp("r1", "alert_2h_at", "t")
        db.stamp("r1", "alert_late_at", "t")
        db.stamp("r1", "code_warned_at", "t")
        db.set_code_seen("r1", False)
        db.release("r1", "نورة", "11", "t")
        db.upsert_arrival(row(day="2026-10-22", checkin_at="2026-10-22T16:00:00+03:00"))
        it = db.get("r1")
        self.assertEqual(it["day"], "2026-10-22")
        for col in ("channel_id", "card_message_id", "card_hash", "alert_2h_at", "alert_late_at",
                    "code_seen", "code_check_at", "code_warned_at", "released_by",
                    "released_by_did", "released_at"):
            self.assertIsNone(it[col], col)
        self.assertIsNone(db.item_by_message("555"))

    def test_same_day_upsert_keeps_card_and_stamps(self):
        db.upsert_arrival(row())
        db.set_card("r1", "900", "555", "h")
        db.stamp("r1", "alert_2h_at", "t")
        db.upsert_arrival(row(guest="Sara A."))
        it = db.get("r1")
        self.assertEqual((it["card_message_id"], it["alert_2h_at"]), ("555", "t"))


if __name__ == "__main__":
    unittest.main()
