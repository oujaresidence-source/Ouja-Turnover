# -*- coding: utf-8 -*-
"""
TDD lock for recovery.db — the two guarantees the SCHEMA makes, not the code.

Both invariants below are enforced by UNIQUE constraints precisely so a future refactor
cannot quietly break them. These tests fail the moment somebody drops a constraint.
"""

import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as _bdb  # noqa: E402
from recovery import db, engine  # noqa: E402


class RecoveryDBCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        _bdb.set_db_path_for_tests(self.tmp.name)
        db.reset_init_cache()
        db._ensure()

    def tearDown(self):
        _bdb.set_db_path_for_tests(None)
        db.reset_init_cache()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _ticket(self, reservation_id="R1", **kw):
        cols = {"id": "rc_%s" % reservation_id, "reservation_id": reservation_id,
                "created_at": db.now_iso(), "month_key": "2026-08"}
        cols.update(kw)
        keys = ",".join(cols)
        marks = ",".join("?" * len(cols))
        return db.execute("INSERT INTO recovery_tickets(%s) VALUES(%s)" % (keys, marks),
                          tuple(cols.values()))


class TestStructuralGuarantees(RecoveryDBCase):

    def test_one_reservation_can_never_produce_two_tickets(self):
        """§15.1 — a guest scored 6.2 produces exactly ONE ticket. Enforced by the
        database, so an overlapping 16:00 batch and in-house immediate path cannot
        both win."""
        self._ticket("R1")
        with self.assertRaises(sqlite3.IntegrityError):
            self._ticket("R1", id="rc_second")

    def test_two_different_reservations_are_fine(self):
        self._ticket("R1")
        self._ticket("R2")
        self.assertIsNotNone(db.open_ticket_for("R1"))
        self.assertIsNotNone(db.open_ticket_for("R2"))

    def test_a_call_token_cannot_be_reused(self):
        self._ticket("R1", call_token="tok-abc")
        with self.assertRaises(sqlite3.IntegrityError):
            self._ticket("R2", id="rc_2", call_token="tok-abc")


class TestAnalysisCache(RecoveryDBCase):
    """§3.1 — one call per reservation, ever."""

    META = {"model": "claude-haiku-4-5", "input_tokens": 500, "output_tokens": 300,
            "calls": 1, "escalated": False, "cost_sar": 0.0075}

    def test_a_miss_then_a_hit(self):
        h = engine.content_hash("الضيف: المكيف ما يشتغل")
        self.assertIsNone(db.cached_analysis("R1", h))
        db.save_analysis("R1", h, {"headline_ar": "x"}, self.META)
        hit = db.cached_analysis("R1", h)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["output"], {"headline_ar": "x"})
        self.assertEqual(hit["input_tokens"], 500)

    def test_a_different_conversation_is_a_different_key(self):
        db.save_analysis("R1", engine.content_hash("a"), {"h": 1}, self.META)
        self.assertIsNone(db.cached_analysis("R1", engine.content_hash("b")))

    def test_the_same_key_never_stores_two_rows(self):
        h = engine.content_hash("same")
        db.save_analysis("R1", h, {"v": 1}, self.META)
        db.save_analysis("R1", h, {"v": 2}, self.META)
        rows = db.q("SELECT * FROM recovery_analysis_cache WHERE reservation_id=?", ("R1",))
        self.assertEqual(len(rows), 1)

    def test_the_month_bill_adds_up(self):
        db.save_analysis("R1", "h1", {}, self.META)
        db.save_analysis("R2", "h2", {}, dict(self.META, cost_sar=0.01, input_tokens=100))
        mk = db.month_key()
        row = db.month_cost(mk)
        self.assertEqual(row["n"], 2)
        self.assertEqual(row["itok"], 600)
        self.assertAlmostEqual(row["sar"], 0.0175, places=4)

    def test_a_month_with_no_tickets_bills_zero_not_none(self):
        row = db.month_cost("2019-01")
        self.assertEqual(row["n"], 0)
        self.assertEqual(row["sar"], 0)


class TestAgentStats(RecoveryDBCase):

    MK = "2026-08"

    def test_assignment_counts_and_stamps(self):
        db.bump_assigned("111", self.MK, "2026-08-06T16:00:00+03:00", "محمد اليامي")
        s = db.agent_stats(self.MK)["111"]
        self.assertEqual(s["assigned_count"], 1)
        self.assertEqual(s["last_assigned_at"], "2026-08-06T16:00:00+03:00")

    def test_receiving_a_ticket_pays_down_conflict_debt(self):
        db.bump_conflict_debt("111", self.MK)
        db.bump_conflict_debt("111", self.MK)
        self.assertEqual(db.agent_stats(self.MK)["111"]["conflict_debt"], 2)
        db.bump_assigned("111", self.MK, "t")
        self.assertEqual(db.agent_stats(self.MK)["111"]["conflict_debt"], 1)

    def test_debt_never_goes_negative(self):
        db.bump_assigned("111", self.MK, "t")
        db.bump_assigned("111", self.MK, "t")
        self.assertEqual(db.agent_stats(self.MK)["111"]["conflict_debt"], 0)

    def test_stats_map_is_the_shape_the_engine_expects(self):
        db.bump_assigned("111", self.MK, "t", "محمد اليامي")
        pick = engine.choose_agent(
            [{"id": "111", "name": "محمد اليامي"}, {"id": "222", "name": "عهود"}],
            db.stats_map(self.MK))
        self.assertEqual(pick["agent_id"], "222")      # 111 already has one, 222 has none

    def test_months_do_not_bleed_into_each_other(self):
        db.bump_assigned("111", "2026-07", "t")
        self.assertEqual(db.agent_stats("2026-08"), {})

    def test_bump_counter_refuses_an_unknown_column(self):
        # The column name is interpolated into SQL; the whitelist is the injection guard.
        db.bump_counter("111", self.MK, "contacted_count")
        self.assertEqual(db.agent_stats(self.MK)["111"]["contacted_count"], 1)
        with self.assertRaises(ValueError):
            db.bump_counter("111", self.MK, "assigned_count=99--")


class TestRepeatUnitAndSkips(RecoveryDBCase):

    def test_repeat_unit_counts_only_inside_the_window(self):
        """§9 — the highest-value output of the whole system."""
        self._ticket("R1", listing_id=42, created_at="2026-08-01T10:00:00+03:00")
        self._ticket("R2", listing_id=42, created_at="2026-08-05T10:00:00+03:00")
        self._ticket("R3", listing_id=42, created_at="2026-06-01T10:00:00+03:00")  # old
        self._ticket("R4", listing_id=99, created_at="2026-08-05T10:00:00+03:00")  # other
        self.assertEqual(db.unit_ticket_count(42, "2026-07-07T00:00:00+03:00"), 2)
        self.assertEqual(db.unit_ticket_count(99, "2026-07-07T00:00:00+03:00"), 1)

    def test_every_skip_records_why(self):
        db.log_skip({"reservation_id": "R9", "guest_name": "ضيف", "score": 8.5}, "score_ok")
        rows = db.q("SELECT * FROM recovery_skips")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "score_ok")
        self.assertEqual(rows[0]["reservation_id"], "R9")


if __name__ == "__main__":
    unittest.main(verbosity=2)
