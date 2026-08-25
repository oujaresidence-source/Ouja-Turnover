# -*- coding: utf-8 -*-
"""
The clock, and the two lookups the Discord buttons depend on.

A late cake and a late decoration are DIFFERENT failures: they are decided separately,
warned separately, and silenced separately. And every button in Discord carries no id — it
finds its work from the thread it was clicked in, or the message it hangs on — so those two
lookups are what keep the buttons alive across a redeploy.

Run: python3 -m unittest tests.test_decor_warnings
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb            # noqa: E402
from decor import db, engine, packs    # noqa: E402

DEADLINE = datetime.datetime(2026, 8, 10, 15, 0)     # decoration must be finished by 3 PM


def order(**kw):
    base = {"id": "dec_x", "state": "awaiting_guest", "deadline_at": DEADLINE.isoformat(),
            "work_start_at": (DEADLINE - datetime.timedelta(minutes=150)).isoformat(),
            "escalated": 0}
    base.update(kw)
    return base


def cake(**kw):
    base = {"id": "cake_x", "state": "pending", "escalated": 0,
            "due_at": (DEADLINE - datetime.timedelta(hours=24)).isoformat()}
    base.update(kw)
    return base


class TestWarnDue(unittest.TestCase):

    def test_nothing_warns_while_there_is_time(self):
        now = DEADLINE - datetime.timedelta(days=2)
        self.assertEqual(engine.warn_due(order(), cake(), now), [])

    def test_the_cake_warns_on_its_own_clock_hours_before_the_decoration(self):
        """The cake is due 24h earlier, so it warns 24h earlier — a separate failure."""
        now = DEADLINE - datetime.timedelta(hours=28)          # 4h before the cake deadline
        kinds = [w["kind"] for w in engine.warn_due(order(), cake(), now)]
        self.assertEqual(kinds, ["cake"])

    def test_the_decoration_warns_three_hours_before_work_must_start(self):
        start = DEADLINE - datetime.timedelta(minutes=150)
        now = start - datetime.timedelta(hours=2)
        kinds = [w["kind"] for w in engine.warn_due(order(), None, now)]
        self.assertEqual(kinds, ["decor"])

    def test_an_overdue_warning_says_so(self):
        now = DEADLINE + datetime.timedelta(hours=1)
        w = engine.warn_due(order(), None, now)[0]
        self.assertTrue(w["overdue"])

    def test_each_warning_fires_once(self):
        now = DEADLINE
        self.assertEqual(engine.warn_due(order(escalated=1), cake(escalated=1), now), [])
        # ...and silencing one does not silence the other
        kinds = [w["kind"] for w in engine.warn_due(order(escalated=1), cake(), now)]
        self.assertEqual(kinds, ["cake"])

    def test_work_already_sent_or_finished_is_never_late(self):
        now = DEADLINE
        self.assertEqual([w["kind"] for w in engine.warn_due(order(state="dispatched"), None, now)], [])
        for state in ("done", "cancelled"):
            self.assertEqual(engine.warn_due(order(state=state), cake(), now), [])

    def test_an_ordered_cake_stops_nagging(self):
        now = DEADLINE - datetime.timedelta(hours=25)
        self.assertEqual(engine.warn_due(order(), cake(state="ordered"), now), [])
        self.assertEqual(engine.warn_due(order(), cake(state="delivered"), now), [])

    def test_an_order_with_no_deadline_cannot_be_late(self):
        self.assertEqual(engine.warn_due(order(deadline_at=None, work_start_at=None),
                                         None, DEADLINE), [])


class TestButtonLookups(unittest.TestCase):
    """No button stores an id. These two lookups are why they survive a redeploy."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="decorwarn_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        db.reset_init_cache()

    def test_a_thread_finds_its_order(self):
        lead = db.create_lead("h8-vlg", "diamond")
        o = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "ناصر")
        db.update_order(o["id"], thread_id="998877")
        found = db.order_by_thread("998877")
        self.assertEqual(found["id"], o["id"])
        self.assertEqual(found["inputs"], {})              # decoded, not raw JSON
        self.assertIsNone(db.order_by_thread("nope"))

    def test_a_message_finds_its_interest(self):
        lead = db.create_lead("c2-nfl", "silver")
        db.set_lead_msg(lead["id"], 123456789)
        found = db.lead_by_msg(123456789)
        self.assertEqual(found["id"], lead["id"])
        self.assertEqual(db.lead_by_msg("123456789")["id"], lead["id"])   # int or str
        self.assertIsNone(db.lead_by_msg("0"))

    def test_the_clock_only_walks_orders_that_can_still_be_late(self):
        lead = db.create_lead("live-unit", "bronze")
        live = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "ناصر",
                             deadline_at=DEADLINE.isoformat())
        lead2 = db.create_lead("done-unit", "bronze")
        finished = db.open_order(lead2["id"], lead2["slug"], lead2["pack_id"], "ناصر",
                                 deadline_at=DEADLINE.isoformat())
        db.update_order(finished["id"], state="done")
        lead3 = db.create_lead("nodate-unit", "bronze")
        db.open_order(lead3["id"], lead3["slug"], lead3["pack_id"], "ناصر")   # no deadline
        ids = [o["id"] for o in db.live_orders()]
        self.assertIn(live["id"], ids)
        self.assertNotIn(finished["id"], ids)
        self.assertEqual(len(ids), 1)

    def test_the_escalated_flag_persists_so_a_restart_does_not_re_nag(self):
        lead = db.create_lead("nag-unit", "diamond")
        o = db.open_order(lead["id"], lead["slug"], lead["pack_id"], "ناصر",
                          deadline_at=DEADLINE.isoformat())
        db.update_order(o["id"], escalated=1)
        self.assertEqual(db.order(o["id"])["escalated"], 1)
        c = db.create_cake_task(o["id"], (DEADLINE - datetime.timedelta(hours=24)).isoformat())
        db.update_cake(c["id"], escalated=1)
        self.assertEqual(db.cake_for_order(o["id"])["escalated"], 1)


class TestWarningWording(unittest.TestCase):

    def test_the_warning_names_the_apartment_and_pings_the_role(self):
        from decor import notify
        o = {"apartment": "B14", "state": "awaiting_guest"}
        pack = packs.get("diamond")
        txt = notify.late_warning(o, pack, "decor", "<@&42>", False, "2026-08-10T12:30")
        self.assertIn("<@&42>", txt)
        self.assertIn("B14", txt)
        self.assertIn("الباقة الماسية", txt)
        cake_txt = notify.late_warning(o, pack, "cake", "<@&42>", True, "2026-08-09T15:00")
        self.assertIn("فات موعده", cake_txt)
        self.assertIn("🍰", cake_txt)


if __name__ == "__main__":
    unittest.main()
