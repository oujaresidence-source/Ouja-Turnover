# -*- coding: utf-8 -*-
"""
The duplicate lock, locked.

THE RULE THIS FILE EXISTS TO PROTECT:
    One apartment, one active subscription. Paying twice for the same unit must be
    structurally impossible — not a convention, not a code review habit. The partial
    unique index in wifi/db.py is the guarantee; the Arabic message is politeness.

Also locked here: an override is never silent and never erasable, a renewal is ONE
transaction, and a guess typed from memory during the backfill sweep never trains the
learning.

Run: python3 -m unittest tests.test_wifi_lock
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb          # noqa: E402
from wifi import db, engine, routes  # noqa: E402


class WifiDbCase(unittest.TestCase):
    """Every TEST gets its own throwaway brain.db.

    Per-test and not per-class on purpose: the learning tests below assert what the
    system has and has NOT learned, and a row left behind by an earlier method would
    quietly satisfy the minimum-observations rule. A test that passes because of its
    neighbours is worse than no test.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wifitest_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sub_payload(self, lid, **over):
        base = {"listing_id": lid, "apartment_name": "Ouja | Test " + str(lid),
                "provider": "mobily", "source_kind": "vendor", "source_name": "محل النور",
                "label_days": 30, "amount_sar": 300, "purchase_date": "2026-06-12",
                "activation_date": "2026-06-12", "pay_method": "cash", "paid_by": "ناصر"}
        base.update(over)
        return base


class TestTheIndexItself(WifiDbCase):
    """Not the application layer — the database."""

    def test_a_second_active_row_is_refused_by_sqlite(self):
        db.create_sub(self.sub_payload(9001))
        with self.assertRaises(sqlite3.IntegrityError):
            db.create_sub(self.sub_payload(9001))
        self.assertEqual(len(db.subs_for(9001)), 1)

    def test_the_index_exists_and_is_partial(self):
        """A future 'simplification' that drops the WHERE clause fails here."""
        rows = db.q("SELECT name, sql FROM sqlite_master WHERE type='index' "
                    "AND name='idx_wifi_one_active'")
        self.assertEqual(len(rows), 1, "the one-active-subscription index is GONE")
        sql = (rows[0]["sql"] or "").lower()
        self.assertIn("unique", sql)
        self.assertIn("where", sql)
        self.assertIn("active", sql)

    def test_closed_rows_do_not_count_against_the_unit(self):
        db.create_sub(self.sub_payload(9002))
        db.close_sub(db.active_sub(9002)["id"], status="dead", real_end="2026-07-01")
        db.create_sub(self.sub_payload(9002))       # must NOT raise
        self.assertEqual(len(db.subs_for(9002)), 2)
        self.assertEqual(len([s for s in db.subs_for(9002) if s["status"] == "active"]), 1)


class TestRenewIsOneTransaction(WifiDbCase):

    def test_renew_closes_the_old_and_opens_the_new_atomically(self):
        db.create_sub(self.sub_payload(9101))
        before = db.counts()
        old_id = db.active_sub(9101)["id"]
        new_id, closed_id = db.renew(9101, self.sub_payload(9101, purchase_date="2026-07-12",
                                                            activation_date="2026-07-12"))
        after = db.counts()
        self.assertEqual(closed_id, old_id)
        self.assertEqual(after["subs"] - before["subs"], 1)
        self.assertEqual(after["active"], before["active"])       # still exactly one
        self.assertEqual(db.sub(old_id)["status"], "replaced")
        self.assertEqual(db.active_sub(9101)["id"], new_id)

    def test_a_failing_renewal_leaves_the_old_subscription_alive(self):
        """All-or-nothing: if the new row is bad, the unit is NOT left uncovered."""
        db.create_sub(self.sub_payload(9102))
        old_id = db.active_sub(9102)["id"]
        before = db.counts()
        with self.assertRaises(Exception):
            # a value sqlite cannot bind -> the INSERT dies AFTER the UPDATE has run
            db.renew(9102, self.sub_payload(9102, amount_sar=object()))
        after = db.counts()
        self.assertEqual(after, before)
        self.assertEqual(db.sub(old_id)["status"], "active")
        self.assertIsNotNone(db.active_sub(9102))


class TestTheLockRule(WifiDbCase):
    """routes.core_log is the one door every new subscription comes through."""

    TODAY = "2026-06-24"      # 12 days after the 2026-06-12 activation above

    def test_a_free_unit_just_takes_the_order(self):
        st, body = routes.core_log(self.sub_payload(9201), actor="ناصر", today=self.TODAY)
        self.assertEqual(st, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["kind"], "free")

    def test_blocked_while_the_existing_one_still_has_real_life_left(self):
        routes.core_log(self.sub_payload(9202), actor="ناصر", today=self.TODAY)
        st, body = routes.core_log(self.sub_payload(9202), actor="فهد", today=self.TODAY)
        self.assertEqual(st, 409)
        self.assertFalse(body["ok"])
        self.assertTrue(body["blocked"])
        self.assertEqual(body["needs"], "override_reason")
        self.assertEqual(len(db.subs_for(9202)), 1, "the blocked order was written anyway")

    def test_the_block_message_says_what_and_who_and_how_much(self):
        routes.core_log(self.sub_payload(9203), actor="ناصر", today=self.TODAY)
        _st, body = routes.core_log(self.sub_payload(9203), actor="فهد", today=self.TODAY)
        msg = body["message_ar"]
        for piece in ("موبايلي", "18", "ناصر", "300"):
            self.assertIn(piece, msg, "the refusal does not tell them %s" % piece)
        self.assertEqual(body["existing"]["days_left"], 18)

    def test_allowed_without_a_reason_once_it_is_about_to_die(self):
        """days_left <= 5 is a renewal, not a duplicate. Blocking there is the system
        being annoying for no reason."""
        routes.core_log(self.sub_payload(9204), actor="ناصر", today=self.TODAY)
        st, body = routes.core_log(self.sub_payload(9204, purchase_date="2026-07-09",
                                                   activation_date="2026-07-09"),
                                   actor="فهد", today="2026-07-09")   # 3 days left
        self.assertEqual(st, 200)
        self.assertEqual(body["kind"], "renewal")
        self.assertEqual(len([s for s in db.subs_for(9204) if s["status"] == "active"]), 1)

    def test_the_grace_boundary_is_exactly_five_days(self):
        self.assertEqual(engine.LOCK_GRACE_DAYS, 5)
        allowed, kind = engine.lock_decision({"days_left": 5}, None)
        self.assertTrue(allowed)
        self.assertEqual(kind, "renewal")
        allowed, kind = engine.lock_decision({"days_left": 6}, None)
        self.assertFalse(allowed)
        self.assertEqual(kind, "blocked")

    def test_an_undated_subscription_never_blocks(self):
        """«ما أعرف» on the backfill leaves no date. We do not know it is alive, so we
        do not stand in the way of a real order."""
        db.create_sub(self.sub_payload(9205, purchase_date=None, activation_date=None,
                                       is_backfill=1))
        st, body = routes.core_log(self.sub_payload(9205), actor="فهد", today=self.TODAY)
        self.assertEqual(st, 200)
        self.assertEqual(body["kind"], "renewal")


class TestTheOverrideIsPermanent(WifiDbCase):

    TODAY = "2026-06-24"

    def test_an_override_with_a_reason_succeeds_and_the_reason_persists(self):
        routes.core_log(self.sub_payload(9301), actor="ناصر", today=self.TODAY)
        st, body = routes.core_log(
            self.sub_payload(9301, override_reason="الاشتراك القديم مات فجأة والضيف داخل"),
            actor="فهد", today=self.TODAY)
        self.assertEqual(st, 200)
        self.assertEqual(body["kind"], "override")
        row = db.active_sub(9301)
        self.assertEqual(row["override_reason"], "الاشتراك القديم مات فجأة والضيف داخل")
        self.assertEqual(row["override_by"], "فهد")

    def test_an_empty_or_blank_reason_is_not_a_reason(self):
        routes.core_log(self.sub_payload(9302), actor="ناصر", today=self.TODAY)
        for blank in ("", "   ", "\t\n"):
            st, body = routes.core_log(self.sub_payload(9302, override_reason=blank),
                                       actor="فهد", today=self.TODAY)
            self.assertEqual(st, 409, "a blank reason was accepted as an override")
            self.assertTrue(body["blocked"])
        self.assertEqual(len(db.subs_for(9302)), 1)

    def test_the_stamp_cannot_be_edited_away(self):
        """update_sub may fix a typo in a date; it must never launder the stamp."""
        routes.core_log(self.sub_payload(9303), actor="ناصر", today=self.TODAY)
        routes.core_log(self.sub_payload(9303, override_reason="غلط بالتسجيل الأول"),
                        actor="فهد", today=self.TODAY)
        sid = db.active_sub(9303)["id"]
        routes.core_edit(sid, {"override_reason": "", "override_by": "",
                               "stated_end": "2026-08-01"}, actor="فهد")
        row = db.sub(sid)
        self.assertEqual(row["override_reason"], "غلط بالتسجيل الأول")
        self.assertEqual(row["override_by"], "فهد")
        self.assertEqual(row["stated_end"], "2026-08-01")     # the honest edit went through


class TestBackfillNeverTrainsTheLearning(WifiDbCase):

    def _finished(self, lid, activation, died, backfill=0):
        sid = db.create_sub(self.sub_payload(lid, activation_date=activation,
                                             purchase_date=activation, label_days=90,
                                             is_backfill=backfill))
        db.add_check(sid, "died", observed_on=died, end_date=died, actor="test")
        db.close_sub(sid, status="dead", real_end=died)
        return sid

    def test_three_remembered_guesses_do_not_move_the_countdown(self):
        self._finished(9401, "2026-01-01", "2026-03-12", backfill=1)   # 70
        self._finished(9402, "2026-02-01", "2026-04-14", backfill=1)   # 72
        self._finished(9403, "2026-03-01", "2026-05-15", backfill=1)   # 75
        key = engine.learning_key(self.sub_payload(9404, label_days=90))
        self.assertIsNone(db.learned_map().get(key),
                          "backfill guesses trained the model")
        self.assertEqual(db.observations_for_key(key), [])

    def test_three_real_observations_do(self):
        self._finished(9411, "2026-01-01", "2026-03-12")   # 70
        self._finished(9412, "2026-02-01", "2026-04-14")   # 72
        self._finished(9413, "2026-03-01", "2026-05-15")   # 75
        key = engine.learning_key(self.sub_payload(9414, label_days=90))
        self.assertEqual(db.observations_for_key(key), [70, 72, 75])
        self.assertEqual(db.learned_map().get(key), 72)

    def test_a_backfill_row_mixed_in_is_dropped_not_averaged(self):
        self._finished(9421, "2026-01-01", "2026-03-12")               # 70   real
        self._finished(9422, "2026-02-01", "2026-04-14")               # 72   real
        self._finished(9423, "2026-03-01", "2026-05-15")               # 75   real
        self._finished(9424, "2026-03-01", "2026-03-05", backfill=1)   #  4   remembered
        key = engine.learning_key(self.sub_payload(9425, label_days=90))
        self.assertEqual(db.observations_for_key(key), [70, 72, 75])
        self.assertEqual(db.learned_map().get(key), 72)


class TestTheBackfillDoorOnlyOpensOneWay(WifiDbCase):
    """/api/wifi/fill-save is public — no login, no token. It may only ADD a remembered
    subscription. It must not be able to delete, close, or overwrite anything."""

    def test_a_public_save_is_always_stamped_as_backfill(self):
        st, body = routes.core_fill_save({"listing_id": 9501, "provider": "stc",
                                          "source_kind": "first_party", "label_days": 30,
                                          "amount_sar": 250, "purchase_date": "2026-06-01"},
                                         who="ناصر", today="2026-06-24")
        self.assertEqual(st, 200)
        self.assertEqual(db.active_sub(9501)["is_backfill"], 1)
        self.assertEqual(db.active_sub(9501)["created_by"], "ناصر")

    def test_i_do_not_know_writes_a_blank_date_not_a_guess(self):
        st, _b = routes.core_fill_save({"listing_id": 9502, "provider": "zain",
                                        "source_kind": "vendor", "source_name": "محل",
                                        "label_days": 30, "purchase_date": None},
                                       who="ناصر", today="2026-06-24")
        self.assertEqual(st, 200)
        row = db.active_sub(9502)
        self.assertIsNone(row["purchase_date"])
        self.assertIsNone(row["activation_date"])
        d = engine.describe(row, learned=None, today="2026-06-24")
        self.assertEqual(d["band"], "unknown")

    def test_the_public_door_cannot_close_or_delete_anything(self):
        import inspect
        src = inspect.getsource(routes.core_fill_save)
        for forbidden in ("close_sub", "update_sub", "DELETE", "renew("):
            self.assertNotIn(forbidden, src,
                             "the public backfill endpoint can now %s" % forbidden)

    def test_a_second_public_save_for_a_covered_unit_does_not_duplicate(self):
        routes.core_fill_save({"listing_id": 9503, "provider": "stc",
                               "source_kind": "first_party", "label_days": 90,
                               "purchase_date": "2026-06-01"}, who="ناصر", today="2026-06-24")
        routes.core_fill_save({"listing_id": 9503, "provider": "stc",
                               "source_kind": "first_party", "label_days": 90,
                               "purchase_date": "2026-06-01"}, who="فهد", today="2026-06-24")
        self.assertEqual(len([s for s in db.subs_for(9503) if s["status"] == "active"]), 1)


if __name__ == "__main__":
    unittest.main()
