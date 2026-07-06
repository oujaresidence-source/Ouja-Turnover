# -*- coding: utf-8 -*-
"""_owner_resolve_lid digit-boundary regression — the الملقا 1 / الملقا 11 bug.

Registry unit «ملقا 1» must resolve to the Hostaway listing «الملقا 1», never
«الملقا 11»: the old raw-substring match saw «ملقا1» inside BOTH normalized names
with the same score (len of the registry code), so whichever listing Hostaway
returned FIRST won. _owner_info (the reverse direction) was already boundary-safe
('MLQ1 can't steal MLQ11'); this locks the lid direction too, in both dict orders.
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-lidb"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ.setdefault("STATE_DIR", _STATE)

import bot  # noqa: E402


class TestOwnerLidBoundary(unittest.TestCase):
    def test_malqa1_never_matches_malqa11_either_order(self):
        rec = {"apartment": "ملقا 1"}
        order_a = {111: "Ouja | الملقا 11 - دخول ذاتي", 110: "Ouja | الملقا 1 - دخول ذاتي"}
        order_b = {110: "Ouja | الملقا 1 - دخول ذاتي", 111: "Ouja | الملقا 11 - دخول ذاتي"}
        self.assertEqual(bot._owner_resolve_lid(rec, order_a), 110)
        self.assertEqual(bot._owner_resolve_lid(rec, order_b), 110)

    def test_registry_with_al_prefix_also_safe(self):
        rec = {"apartment": "الملقا 1"}
        listings = {111: "Ouja | الملقا 11", 110: "Ouja | الملقا 1"}
        self.assertEqual(bot._owner_resolve_lid(rec, listings), 110)

    def test_malqa11_still_resolves_to_malqa11(self):
        rec = {"apartment": "ملقا 11"}
        listings = {110: "Ouja | الملقا 1", 111: "Ouja | الملقا 11"}
        self.assertEqual(bot._owner_resolve_lid(rec, listings), 111)

    def test_latin_family_codes(self):
        # A-1 vs A-11 — same collision family in Latin codes.
        listings = {21: "Ouja | A 11 Hittin", 20: "Ouja | A 1 Hittin"}
        self.assertEqual(bot._owner_resolve_lid({"apartment": "A-1"}, listings), 20)
        self.assertEqual(bot._owner_resolve_lid({"apartment": "A-11"}, listings), 21)

    def test_letter_adjacent_match_still_works(self):
        # Digit-boundary only: letters around the code stay legal («ملقا1» inside
        # «الملقا1» — the ال prefix glues letters, not digits).
        rec = {"apartment": "L-07"}
        listings = {7: "Ouja | L07 Yasmin"}
        self.assertEqual(bot._owner_resolve_lid(rec, listings), 7)

    def test_explicit_lid_override_always_wins(self):
        rec = {"apartment": "ملقا 1", "lid": 999}
        listings = {110: "Ouja | الملقا 1", 111: "Ouja | الملقا 11"}
        self.assertEqual(bot._owner_resolve_lid(rec, listings), 999)

    def test_no_match_returns_none(self):
        self.assertIsNone(bot._owner_resolve_lid({"apartment": "زيزفون 9"},
                                                 {110: "Ouja | الملقا 1"}))


if __name__ == "__main__":
    unittest.main()
