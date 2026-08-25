# -*- coding: utf-8 -*-
"""
TDD lock for recovery.status — the dashboard tab's payload.

Two properties matter most here:
  1. A missing bot.py capability DEGRADES the section; it never blanks the page or raises
     into the web server. The tab is read by the owner on a phone — a 500 is worse than a
     dash.
  2. «مغادرو اليوم» is CONTEXT, not a work queue. It must not imply a ticket is owed, and
     it must show an existing ticket beside the guest when one exists.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as _bdb  # noqa: E402
from recovery import config, db, host, status  # noqa: E402

CHECKOUTS = [
    {"reservation_id": "111", "guest": "سعود", "unit": "Ouja | Turaif", "listing_id": 9,
     "checkin": "2026-08-05", "checkout": "2026-08-08", "nights": 3,
     "channel": "Airbnb", "has_phone": True},
    {"reservation_id": "222", "guest": "Sarah", "unit": "Ouja | Hittin", "listing_id": 7,
     "checkin": "2026-08-06", "checkout": "2026-08-08", "nights": 2,
     "channel": "Direct", "has_phone": False},
]


class StatusCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        _bdb.set_db_path_for_tests(self.tmp.name)
        db.reset_init_cache()
        db._ensure()
        self._saved = dict(host.HOST.__dict__)

    def tearDown(self):
        host.HOST.__dict__.clear()
        host.HOST.__dict__.update(self._saved)
        _bdb.set_db_path_for_tests(None)
        db.reset_init_cache()
        try:
            os.unlink(self.tmp.name)
        except OSError:
            pass

    def _ticket(self, reservation_id, **kw):
        cols = {"id": "rc_" + reservation_id, "reservation_id": reservation_id,
                "created_at": db.now_iso(), "month_key": db.month_key()}
        cols.update(kw)
        keys = ",".join(cols)
        db.execute("INSERT INTO recovery_tickets(%s) VALUES(%s)"
                   % (keys, ",".join("?" * len(cols))), tuple(cols.values()))


class TestTodayBlock(StatusCase):

    def test_it_lists_todays_checkouts(self):
        host.wire({"todays_checkouts": lambda: CHECKOUTS, "inhouse_count": lambda: 31})
        t = status.today_block()
        self.assertEqual(t["checkouts_count"], 2)
        self.assertEqual(t["inhouse_count"], 31)
        self.assertEqual([r["guest"] for r in t["checkouts"]], ["سعود", "Sarah"])

    def test_it_counts_guests_we_cannot_phone(self):
        # §13 — a guest with no number needs a different route, so the count is surfaced.
        host.wire({"todays_checkouts": lambda: CHECKOUTS, "inhouse_count": lambda: 0})
        self.assertEqual(status.today_block()["no_phone"], 1)

    def test_an_existing_ticket_shows_beside_the_guest(self):
        self._ticket("111", status="CONTACTED", score=5.5, assigned_agent_name="عهود")
        host.wire({"todays_checkouts": lambda: CHECKOUTS, "inhouse_count": lambda: 0})
        t = status.today_block()
        by = {r["reservation_id"]: r for r in t["checkouts"]}
        self.assertEqual(by["111"]["ticket_status"], "CONTACTED")
        self.assertEqual(by["111"]["ticket_agent"], "عهود")
        self.assertEqual(t["with_ticket"], 1)
        self.assertIsNone(by["222"]["ticket_status"])   # no ticket = no invented one

    def test_no_checkouts_today_is_not_an_error(self):
        host.wire({"todays_checkouts": lambda: [], "inhouse_count": lambda: 12})
        t = status.today_block()
        self.assertEqual(t["checkouts_count"], 0)
        self.assertEqual(t["checkouts"], [])

    def test_a_missing_capability_degrades_instead_of_raising(self):
        """bot.py may not have injected these (old deploy, wiring failure). The tab must
        still render."""
        host.wire({"todays_checkouts": None, "inhouse_count": None})
        t = status.today_block()
        self.assertEqual(t["checkouts_count"], 0)
        self.assertIsNone(t["inhouse_count"])


class TestPayloadIsResilient(StatusCase):

    def test_every_section_is_present(self):
        host.wire({"todays_checkouts": lambda: CHECKOUTS, "inhouse_count": lambda: 5})
        p = status.payload()
        for key in ("state", "today", "agents", "tickets", "month", "repeat_units", "skips"):
            self.assertIn(key, p)
        self.assertTrue(p["ok"])

    def test_one_broken_section_does_not_blank_the_page(self):
        def boom():
            raise RuntimeError("hostaway is down")
        host.wire({"todays_checkouts": boom, "inhouse_count": lambda: 5})
        p = status.payload()
        self.assertFalse(p["ok"])                     # honestly flagged
        self.assertIn("error", p["today"])            # only this section failed
        self.assertIn("rows", p["agents"])            # the rest still rendered
        self.assertIn("mode", p["state"])

    def test_the_mode_is_reported_honestly(self):
        host.wire({"todays_checkouts": lambda: [], "inhouse_count": lambda: 0})
        st = status.payload()["state"]
        self.assertEqual(st["mode"], "dryrun")        # ships off
        self.assertIn("يحسب", st["mode_ar"])

    def test_agent_numbers_come_from_the_engine_not_a_second_calculation(self):
        db.bump_assigned(config.AGENTS[0]["id"], db.month_key(), "t")
        host.wire({"todays_checkouts": lambda: [], "inhouse_count": lambda: 0})
        ag = status.payload()["agents"]
        self.assertEqual(ag["gap"], 1)
        self.assertTrue(ag["balanced"])               # 1 is within the ±2 target


if __name__ == "__main__":
    unittest.main(verbosity=2)
