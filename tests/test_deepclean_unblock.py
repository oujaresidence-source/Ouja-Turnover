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


if __name__ == "__main__":
    unittest.main()
