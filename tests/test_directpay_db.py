# -*- coding: utf-8 -*-
"""directpay.db — the ledger inside brain.db.

  * UNIQUE(reservation_id): a second open for the same reservation is swallowed to ONE row
    (the database is the anti-duplicate guarantee, not a promise about a loop)
  * events append and never overwrite
  * by_channel / by_reservation round-trip
  * an additive migration on an already-created table adds the column without data loss

Run: python3 -m unittest tests.test_directpay_db
"""
import os
import sys
import tempfile
import unittest
from contextlib import closing

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb          # noqa: E402
from directpay import db             # noqa: E402


def fields(rid="5001", **kw):
    f = {"reservation_id": rid, "confirmation_code": "ABC123", "listing_id": 900,
         "unit_name": "Ouja | B14", "guest_name": "أبو خالد", "guest_phone": "+9665",
         "channel_raw": "Direct", "arrival": "2026-10-01", "departure": "2026-10-04",
         "nights": 3, "total_sar": 1200.0, "booked_at": "2026-09-10 09:00:00",
         "created_at": "2026-09-10T09:05:00"}
    f.update(kw)
    return f


class DbCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="dpdb_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        db.reset_init_cache()


class TestLedger(DbCase):
    def test_same_reservation_twice_is_one_row(self):
        a = db.open_ticket(**fields(rid="7001"))
        self.assertIsNotNone(a)
        self.assertTrue(a["id"].startswith("dp_"))
        self.assertEqual(a["status"], "open")
        b = db.open_ticket(**fields(rid="7001", guest_name="آخر"))
        self.assertIsNone(b)                      # swallowed, not raised, not duplicated
        rows = db.q("SELECT * FROM directpay_tickets WHERE reservation_id='7001'")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["guest_name"], "أبو خالد")    # the first write stands

    def test_reservation_id_is_normalised_to_text(self):
        db.open_ticket(**fields(rid=7002))
        self.assertIsNone(db.open_ticket(**fields(rid="7002")))
        self.assertIsNotNone(db.by_reservation(7002))
        self.assertIsNotNone(db.by_reservation("7002"))

    def test_by_channel_and_by_reservation_round_trip(self):
        t = db.open_ticket(**fields(rid="7003"))
        self.assertIsNone(db.by_channel("123456"))
        db.update(t["id"], channel_id="123456", card_msg_id="999")
        self.assertEqual(db.by_channel(123456)["id"], t["id"])
        self.assertEqual(db.by_channel("123456")["card_msg_id"], "999")
        self.assertEqual(db.by_reservation("7003")["channel_id"], "123456")

    def test_update_ignores_unknown_columns_and_the_key_columns(self):
        t = db.open_ticket(**fields(rid="7004"))
        db.update(t["id"], status="verified", not_a_column=1, reservation_id="HACK", id="HACK")
        row = db.ticket(t["id"])
        self.assertEqual(row["status"], "verified")
        self.assertEqual(row["reservation_id"], "7004")

    def test_events_append_and_never_overwrite(self):
        t = db.open_ticket(**fields(rid="7005"))
        db.add_event(t["id"], "opened", actor="bot", detail="a")
        db.add_event(t["id"], "refused", actor="ناصر", actor_id="42", detail="b")
        db.add_event(t["id"], "refused", actor="ناصر", actor_id="42", detail="c")
        ev = db.events(t["id"])
        self.assertEqual([e["kind"] for e in ev], ["opened", "refused", "refused"])
        self.assertEqual([e["detail"] for e in ev], ["a", "b", "c"])
        self.assertEqual(ev[1]["actor"], "ناصر")
        self.assertEqual(ev[1]["actor_id"], "42")
        # no UPDATE / DELETE helper exists for events — the API is append-only
        self.assertFalse(hasattr(db, "update_event"))
        self.assertFalse(hasattr(db, "delete_event"))

    def test_known_ids_and_open_listing(self):
        db.open_ticket(**fields(rid="7006"))
        db.open_ticket(**fields(rid="7007"))
        known = db.known_reservation_ids()
        self.assertIn("7006", known)
        self.assertIn("7007", known)
        self.assertTrue(all(isinstance(k, str) for k in known))
        opens = {r["reservation_id"] for r in db.open_tickets()}
        self.assertIn("7006", opens)

    def test_settings_round_trip(self):
        self.assertIsNone(db.setting_get("nope"))
        self.assertEqual(db.setting_get("nope", "d"), "d")
        db.setting_set("start_date", "2026-09-10")
        self.assertEqual(db.setting_get("start_date"), "2026-09-10")
        db.setting_set("start_date", "2026-09-11")
        self.assertEqual(db.setting_get("start_date"), "2026-09-11")

    def test_seq_is_stored_when_given(self):
        t = db.open_ticket(**fields(rid="7008", seq=17))
        self.assertEqual(t["seq"], 17)


class TestMigration(unittest.TestCase):
    def test_additive_column_migration_keeps_rows(self):
        tmp = tempfile.mkdtemp(prefix="dpmig_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        db.reset_init_cache()
        # An OLD copy of the table: every column except the last two in the current list.
        old_cols = [c for c in db.TICKET_COLS[:-2]]
        with closing(bdb.connect()) as cx:
            cx.execute("CREATE TABLE directpay_tickets (%s)" %
                       ", ".join("%s %s" % (n, t) for n, t in old_cols))
            cx.execute("INSERT INTO directpay_tickets(id, reservation_id, status) VALUES('dp_old','1','open')")
            cx.commit()
        db.reset_init_cache()
        db._ensure()                               # runs _migrate on the existing table
        row = db.ticket("dp_old")
        self.assertIsNotNone(row)
        self.assertEqual(row["reservation_id"], "1")
        for name, _ in db.TICKET_COLS[-2:]:
            self.assertIn(name, row)               # the new columns exist
        self.assertIsNone(row[db.TICKET_COLS[-1][0]])
        # and the migration is idempotent
        db.reset_init_cache()
        db._ensure()
        self.assertEqual(len(db.q("SELECT * FROM directpay_tickets")), 1)


if __name__ == "__main__":
    unittest.main()
