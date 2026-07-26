# -*- coding: utf-8 -*-
"""
The OWNER RULE, locked at the storage layer:

    A guest tapping «أنا مهتم» creates NOTHING — no order, no thread, no task, no cake job,
    no assignment. Only a supervisor opens a request.

These tests count every other table before and after a guest tap, so any future change that
quietly re-wires intake into an order fails here instead of on the ops floor.

Run: python3 -m unittest tests.test_decor_flow
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb            # noqa: E402
from decor import db, engine, packs    # noqa: E402


class DecorDbCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="decortest_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        db.reset_init_cache()


class TestAGuestTapCreatesNoWork(DecorDbCase):

    def test_ten_taps_produce_leads_and_nothing_else(self):
        before = db.counts()
        for _ in range(10):
            db.create_lead("h8-vlg", "diamond", lang="ar", source="guide")
        after = db.counts()
        self.assertEqual(after["leads_total"] - before["leads_total"], 10)
        for key in ("orders", "awaiting_guest", "ready", "dispatched", "cakes", "cakes_pending"):
            self.assertEqual(after[key], before[key],
                             "a guest tap changed %s — the owner rule is broken" % key)

    def test_a_lead_has_nowhere_to_store_work(self):
        """Not a convention — the columns do not exist. A future bug cannot assign a lead."""
        lead = db.create_lead("c2-nfl", "silver")
        for forbidden in ("assignee", "deadline_at", "thread_id", "due_at", "cake_id"):
            self.assertNotIn(forbidden, lead,
                             "decor_leads grew a %s column — work can now attach to a tap" % forbidden)

    def test_the_public_endpoint_has_no_path_to_an_order(self):
        """Guards the structure itself: routes.inquire must not reach db.open_order."""
        import inspect
        from decor import routes
        src = inspect.getsource(routes.inquire)
        for forbidden in ("open_order", "create_cake_task", "update_order"):
            self.assertNotIn(forbidden, src,
                             "the public inquire endpoint now calls %s" % forbidden)


class TestOnlyTheSupervisorOpens(DecorDbCase):

    def _lead(self, slug="b14", pack="diamond"):
        return db.create_lead(slug, pack)

    def test_opening_marks_the_lead_and_creates_exactly_one_order(self):
        lead = self._lead()
        before = db.counts()["orders"]
        o = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "ناصر",
                          apartment="B14", state="awaiting_guest")
        self.assertEqual(db.counts()["orders"], before + 1)
        self.assertEqual(db.lead(lead["id"])["status"], "opened")
        self.assertEqual(db.lead(lead["id"])["order_id"], o["id"])
        self.assertEqual(o["opened_by"], "ناصر")

    def test_a_dismissed_lead_stays_dismissed(self):
        lead = self._lead(slug="f1", pack="bronze")
        db.dismiss_lead(lead["id"], "نورة", "الضيف غيّر رأيه")
        self.assertEqual(db.lead(lead["id"])["status"], "dismissed")
        db.dismiss_lead(lead["id"], "someone else", "")
        self.assertEqual(db.lead(lead["id"])["dismissed_by"], "نورة")

    def test_dedupe_window_finds_the_recent_tap(self):
        db.create_lead("jood12", "table_styling")
        since = (datetime.datetime.utcnow() - datetime.timedelta(minutes=30)).isoformat(timespec="seconds")
        self.assertIsNotNone(db.recent_lead("jood12", "table_styling", since))
        self.assertIsNone(db.recent_lead("jood12", "bronze", since))


class TestUnitFeaturesSheet(DecorDbCase):

    def test_unknown_unit_is_none_not_empty(self):
        """'we don't know' and 'we know it has nothing' must stay different answers."""
        self.assertIsNone(db.unit_features("never-seen-unit"))
        db.set_unit_features("known-empty", [], by="ناصر")
        self.assertEqual(db.unit_features("known-empty"), [])
        self.assertEqual(engine.capability_check(packs.get("diamond"), None)["verdict"], "unknown")
        self.assertEqual(engine.capability_check(packs.get("diamond"), [])["verdict"], "missing")

    def test_a_correction_override_teaches_the_sheet_once(self):
        db.set_unit_features("a5-mlq", ["jacuzzi"], by="ناصر")
        chk = engine.open_check(packs.get("diamond"), db.unit_features("a5-mlq"),
                                override_kind="correction", overridden_by="ناصر",
                                reason="القائمة غلط")
        db.add_unit_features("a5-mlq", chk["learn_features"], by="ناصر")
        self.assertEqual(sorted(db.unit_features("a5-mlq")), ["jacuzzi", "pool"])
        # the same apartment never asks again
        self.assertEqual(engine.capability_check(packs.get("diamond"),
                                                 db.unit_features("a5-mlq"))["verdict"], "ok")

    def test_an_accept_gap_override_does_not_rewrite_the_sheet(self):
        db.set_unit_features("c204", ["jacuzzi"], by="ناصر")
        engine.open_check(packs.get("diamond"), db.unit_features("c204"),
                          override_kind="accept_gap", overridden_by="ناصر", reason="الضيف موافق")
        self.assertEqual(db.unit_features("c204"), ["jacuzzi"])   # unchanged — we still know it has no pool


class TestCakeIsItsOwnJob(DecorDbCase):

    def test_a_diamond_order_gets_a_cake_due_24h_earlier(self):
        lead = db.create_lead("hue-9", "diamond")
        deadline = datetime.datetime(2026, 8, 10, 15, 0)
        o = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "ناصر",
                          deadline_at=deadline.isoformat(timespec="minutes"))
        task = engine.cake_task_for(packs.get("diamond"), deadline, packs.cake_lead_hours())
        cake = db.create_cake_task(o["id"], task["due_at"].isoformat(timespec="minutes"))
        self.assertEqual(cake["due_at"], "2026-08-09T15:00")
        self.assertEqual(cake["state"], "pending")
        self.assertEqual(db.cake_for_order(o["id"])["id"], cake["id"])

    def test_a_bronze_order_creates_no_cake_subtask(self):
        lead = db.create_lead("6b-htn", "bronze")
        deadline = datetime.datetime(2026, 8, 10, 15, 0)
        o = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "ناصر",
                          deadline_at=deadline.isoformat(timespec="minutes"))
        self.assertIsNone(engine.cake_task_for(packs.get("bronze"), deadline))
        self.assertIsNone(db.cake_for_order(o["id"]))

    def test_the_cake_state_moves_independently_of_the_decoration(self):
        lead = db.create_lead("d7", "silver")
        o = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "نورة",
                          deadline_at="2026-08-10T15:00")
        cake = db.create_cake_task(o["id"], "2026-08-09T15:00")
        db.update_cake(cake["id"], state="ordered", ordered_by="نورة")
        self.assertEqual(db.cake_for_order(o["id"])["state"], "ordered")
        self.assertEqual(db.order(o["id"])["state"], "awaiting_guest")   # untouched


class TestOrderProgress(DecorDbCase):

    def test_inputs_merge_and_unlock_dispatch(self):
        lead = db.create_lead("e15", "bronze")
        o = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "ناصر", final_price_sar=650)
        pack = packs.get("bronze")
        self.assertFalse(engine.dispatch_check(pack, o)["ok"])
        db.set_inputs(o["id"], {"phrases": "٥ عبارات"})
        db.set_inputs(o["id"], {"bed_letters": "ن", "occasion": "زواج"})
        o = db.order(o["id"])
        self.assertEqual(o["inputs"]["phrases"], "٥ عبارات")          # first write not lost
        self.assertTrue(engine.dispatch_check(pack, o)["ok"])

    def test_the_stamp_is_stored_on_the_order_and_survives_a_reload(self):
        lead = db.create_lead("c2", "diamond")
        stamp = engine.capability_stamp(packs.get("diamond"), ["pool"], "ناصر", "2026-07-26 14:00")
        o = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "ناصر",
                          capability_verdict="accepted_gap", capability_stamp=stamp,
                          override_kind="accept_gap", overridden_by="ناصر",
                          override_reason="الضيف موافق")
        again = db.order(o["id"])
        self.assertEqual(again["capability_stamp"], stamp)
        self.assertIn("مسبح", again["capability_stamp"])
        self.assertEqual(again["overridden_by"], "ناصر")


if __name__ == "__main__":
    unittest.main()
