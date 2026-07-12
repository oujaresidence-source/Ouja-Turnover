# -*- coding: utf-8 -*-
"""Deep-clean unblock safety: _deep_clean_block_eligible must return True ONLY for
our own 'deep-clean' calendar blocks — never a guest booking or a manual hold."""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-deepclean"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ.setdefault("STATE_DIR", _STATE)

import bot  # noqa: E402


class TestBlockEligible(unittest.TestCase):
    def test_true_for_deep_clean_block(self):
        self.assertTrue(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": None, "note": "deep-clean"}))

    def test_false_for_guest_reservation(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": 12345, "note": "deep-clean"}))

    def test_false_for_manual_block_other_note(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": None, "note": "owner hold"}))

    def test_false_for_available_day(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": 1, "reservationId": None, "note": "deep-clean"}))

    def test_false_for_empty_note(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": None, "note": ""}))

    def test_handles_string_isavailable_and_empty_resid(self):
        self.assertTrue(bot._deep_clean_block_eligible(
            {"isAvailable": "0", "reservationId": "", "note": "deep-clean"}))

    def test_false_for_non_dict(self):
        self.assertFalse(bot._deep_clean_block_eligible(None))

    def test_true_for_note_case_and_whitespace_variants(self):
        self.assertTrue(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": None, "note": "  Deep-Clean  "}))
        self.assertTrue(bot._deep_clean_block_eligible(
            {"isAvailable": 0, "reservationId": None, "note": "DEEP-CLEAN"}))

    def test_false_for_none_availability(self):
        self.assertFalse(bot._deep_clean_block_eligible(
            {"isAvailable": None, "reservationId": None, "note": "deep-clean"}))


class TestUnblockSweep(unittest.TestCase):
    """Synthetic-data test for the live-write sweep: it must free ONLY our own
    deep-clean blocks (verified against a re-read of the calendar), leave guest
    bookings and manual holds alone, ignore non-blocked units, and be idempotent."""

    def setUp(self):
        import re as _re
        self._orig = (bot.api_get, bot.api_put, bot.get_listings_map,
                      dict(bot._deep_clean_state))
        self.puts = []
        self._cal = {
            101: {"isAvailable": 0, "reservationId": None, "note": "deep-clean"},   # ours -> free
            102: {"isAvailable": 0, "reservationId": 99999, "note": "deep-clean"},  # guest booked -> skip
            103: {"isAvailable": 0, "reservationId": None, "note": "owner hold"},   # manual hold -> skip
        }

        def fake_get(path, params=None):
            m = _re.search(r"/listings/(\d+)/calendar", path)
            lid = int(m.group(1)) if m else None
            day = self._cal.get(lid)
            return {"result": [day] if day else []}

        def fake_put(path, body):
            self.puts.append((path, body))
            m = _re.search(r"/listings/(\d+)/calendar", path)
            lid = int(m.group(1)) if m else None
            if lid in self._cal:   # reflect the freeing write so a 2nd sweep is a no-op
                self._cal[lid] = {"isAvailable": 1, "reservationId": None, "note": "deep-clean"}
            return {"result": []}

        bot.api_get = fake_get
        bot.api_put = fake_put
        bot.get_listings_map = lambda: {101: "Ouja | A", 102: "Ouja | B",
                                        103: "Ouja | C", 104: "Ouja | D"}
        bot._deep_clean_state = {
            101: {"next_status": "blocked", "next_scheduled": "2026-07-13"},
            102: {"next_status": "blocked", "next_scheduled": "2026-07-14"},
            103: {"next_status": "blocked", "next_scheduled": "2026-07-15"},
            104: {"next_status": "scheduled", "next_scheduled": "2026-07-20"},  # not blocked -> ignored
        }

    def tearDown(self):
        (bot.api_get, bot.api_put, bot.get_listings_map, state) = self._orig
        bot._deep_clean_state = state

    def test_frees_only_our_block(self):
        rep = bot.unblock_all_deep_clean_dates()
        self.assertEqual(rep["count"], 1)
        self.assertEqual([f["lid"] for f in rep["freed"]], [101])
        # exactly one write, to listing 101, setting it available
        self.assertEqual(len(self.puts), 1)
        self.assertIn("/listings/101/calendar", self.puts[0][0])
        self.assertEqual(self.puts[0][1]["isAvailable"], 1)
        # 101 state cleared; guest-booked + manual-hold stay blocked
        self.assertEqual(bot._deep_clean_state[101]["next_status"], "unscheduled")
        self.assertIsNone(bot._deep_clean_state[101]["next_scheduled"])
        self.assertEqual(bot._deep_clean_state[102]["next_status"], "blocked")
        self.assertEqual(bot._deep_clean_state[103]["next_status"], "blocked")
        # non-blocked unit 104 was never touched (not read, not written, not skipped)
        self.assertNotIn(104, [s.get("lid") for s in rep["skipped"]])
        self.assertEqual(sorted(s.get("lid") for s in rep["skipped"]), [102, 103])

    def test_idempotent_second_run_is_noop(self):
        bot.unblock_all_deep_clean_dates()
        self.puts.clear()
        rep2 = bot.unblock_all_deep_clean_dates()
        self.assertEqual(rep2["count"], 0)
        self.assertEqual(len(self.puts), 0)


if __name__ == "__main__":
    unittest.main()
