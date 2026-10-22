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

    def test_late_columns_added(self):
        """R2: room_kind, room_close_pending, sent_by_bot reach a table built before them."""
        from contextlib import closing
        tmp = tempfile.mkdtemp(prefix="cgm_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        db.reset_init_cache()
        old = db.SCHEMA
        for col in ("room_kind", "room_close_pending", "sent_by_bot", "held_channel_id",
                    "delete_fail_count"):
            lines = [ln for ln in old.split("\n") if ln.strip().startswith(col + " ")]
            self.assertEqual(len(lines), 1, col)
            old = old.replace(lines[0] + "\n", "")
        with closing(bdb.connect()) as cx:
            cx.executescript(old)
            cx.execute("INSERT INTO codegate_items(res_id, day) VALUES ('old1', ?)", (DAY,))
            cx.commit()
        it = db.get("old1")
        self.assertIsNone(it["room_kind"])
        self.assertEqual(it["room_close_pending"], 0)
        self.assertEqual(it["sent_by_bot"], 0)
        self.assertIsNone(it["held_channel_id"])
        self.assertEqual(it["delete_fail_count"], 0)
        db.reset_init_cache()                            # second boot: idempotent
        self.assertIn("sent_by_bot", db.get("old1"))

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

    def test_set_room_clears_card(self):
        db.upsert_arrival(row())
        db.set_room("r1", "T1", "turnover")
        db.set_card("r1", "T1", "555", "h")
        db.set_room("r1", "T1", "turnover")              # same room: card kept
        it = db.get("r1")
        self.assertEqual((it["card_message_id"], it["card_hash"]), ("555", "h"))
        db.set_room("r1", "C9", "code")                  # new room: the old card is not here
        it = db.get("r1")
        self.assertEqual((it["channel_id"], it["room_kind"]), ("C9", "code"))
        self.assertIsNone(it["card_message_id"])
        self.assertIsNone(it["card_hash"])
        self.assertIsNone(db.item_by_message("555"))
        db.set_room("r1", None, None)                    # lost: placement starts over
        it = db.get("r1")
        self.assertIsNone(it["channel_id"])
        self.assertIsNone(it["room_kind"])

    def test_close_pending_and_sent_by_bot(self):
        db.upsert_arrival(row())
        db.set_close_pending("r1", True)
        self.assertEqual(db.get("r1")["room_close_pending"], 1)
        db.set_close_pending("r1", False)
        self.assertEqual(db.get("r1")["room_close_pending"], 0)
        db.release("r1", "نورة", "11", "t1")
        db.mark_sent_by_bot("r1")
        self.assertEqual(db.get("r1")["sent_by_bot"], 1)
        db.undo("r1", "system", "t2")                    # undo forgets the bot send too
        self.assertEqual(db.get("r1")["sent_by_bot"], 0)

    def test_code_room_items(self):
        db.upsert_arrival(row("r1"))
        db.upsert_arrival(row("r2", day="2026-10-20"))
        db.upsert_arrival(row("r3"))
        db.upsert_arrival(row("r4", day="2026-10-20"))
        db.set_room("r1", "C1", "code")
        db.set_room("r2", "C2", "code")
        db.set_room("r3", "T3", "turnover")
        self.assertEqual(sorted(r["res_id"] for r in db.code_room_items()), ["r1", "r2"])
        self.assertEqual([r["res_id"] for r in db.code_room_items(older_than_day=DAY)], ["r2"])

    def test_held_room_items(self):
        """A held close is tracked by the held room itself, whatever room the card is in."""
        db.upsert_arrival(row("r1", day="2026-10-20"))
        db.upsert_arrival(row("r2", day="2026-10-20"))
        db.upsert_arrival(row("r3"))
        db.upsert_arrival(row("r4"))
        db.set_room("r1", "T1", "turnover")
        db.set_room("r2", "T2", "turnover")
        db.set_room("r3", "C3", "code")                  # card in a code room, turnover held
        db.set_held("r1", "T1")
        db.set_held("r3", "T3")
        db.set_held("r4", None)                          # held, room to be looked up
        self.assertEqual(sorted(r["res_id"] for r in db.held_room_items()), ["r1", "r3", "r4"])
        self.assertEqual([r["res_id"] for r in db.held_room_items(older_than_day=DAY)], ["r1"])
        self.assertEqual((db.get("r3")["held_channel_id"], db.get("r3")["room_close_pending"]),
                         ("T3", 1))

    def test_room_closed_forgets_only_that_room(self):
        db.upsert_arrival(row())
        db.set_room("r1", "C1", "code")
        db.set_card("r1", "C1", "555", "h")
        db.set_held("r1", "T1")
        db.delete_failed("r1")
        db.room_closed("r1", "C1")                       # the code room: card goes, hold stays
        it = db.get("r1")
        self.assertEqual((it["channel_id"], it["room_kind"], it["card_message_id"]),
                         (None, None, None))
        self.assertEqual((it["held_channel_id"], it["room_close_pending"]), ("T1", 1))
        self.assertEqual(it["delete_fail_count"], 0)
        db.room_closed("r1", "T1", held=True)
        it = db.get("r1")
        self.assertEqual((it["held_channel_id"], it["room_close_pending"]), (None, 0))

    def test_room_closed_held_is_card_room(self):
        db.upsert_arrival(row())
        db.set_room("r1", "T1", "turnover")
        db.set_card("r1", "T1", "555", "h")
        db.set_held("r1", "T1")
        db.room_closed("r1", "T1", held=True)
        it = db.get("r1")
        self.assertEqual((it["channel_id"], it["card_message_id"], it["held_channel_id"],
                          it["room_close_pending"]), (None, None, None, 0))
        db.set_held("r1", None)                          # held room never resolved, then gone
        db.room_closed("r1", None, held=True)
        self.assertEqual(db.get("r1")["room_close_pending"], 0)

    def test_delete_failed_counts(self):
        db.upsert_arrival(row())
        self.assertEqual([db.delete_failed("r1") for _ in range(3)], [1, 2, 3])

    def test_items_for_unit_day(self):
        db.upsert_arrival(row("r1"))
        db.upsert_arrival(row("r2", lid=5))
        db.upsert_arrival(row("r3", day="2026-10-22"))
        self.assertEqual([r["res_id"] for r in db.items_for(461328, DAY)], ["r1"])
        self.assertEqual([r["res_id"] for r in db.items_for("461328", DAY)], ["r1"])

    def test_day_change_resets_room(self):
        db.upsert_arrival(row())
        db.set_room("r1", "C1", "code")
        db.set_close_pending("r1", True)
        db.release("r1", "نورة", "11", "t")
        db.mark_sent_by_bot("r1")
        db.set_held("r1", "T1")
        db.delete_failed("r1")
        db.upsert_arrival(row(day="2026-10-22", checkin_at="2026-10-22T16:00:00+03:00"))
        it = db.get("r1")
        for col in ("channel_id", "room_kind", "room_close_pending", "sent_by_bot",
                    "held_channel_id", "delete_fail_count"):
            self.assertFalse(it[col], col)
        db.set_room("r1", "C2", "code")
        db.set_close_pending("r1", True)
        db.upsert_arrival(row(day="2026-10-22", checkin_at="2026-10-22T16:00:00+03:00"))
        it = db.get("r1")                                # same day: kept
        self.assertEqual((it["channel_id"], it["room_kind"], it["room_close_pending"]),
                         ("C2", "code", 1))

    def test_unit_change_same_day_resets_room(self):
        """A guest moved to another unit the same day: the old unit's room is not his any more."""
        db.upsert_arrival(row())
        db.set_room("r1", "T1", "turnover")
        db.set_card("r1", "T1", "555", "h")
        db.set_held("r1", "T1")
        db.stamp("r1", "alert_2h_at", "t")
        db.upsert_arrival(row(lid=526697))
        it = db.get("r1")
        self.assertEqual(it["lid"], 526697)
        for col in ("channel_id", "card_message_id", "room_kind", "held_channel_id",
                    "room_close_pending", "alert_2h_at"):
            self.assertFalse(it[col], col)
        db.set_room("r1", "T2", "turnover")
        db.upsert_arrival(row(lid="526697"))             # same unit (as text): kept
        self.assertEqual(db.get("r1")["channel_id"], "T2")


if __name__ == "__main__":
    unittest.main()
