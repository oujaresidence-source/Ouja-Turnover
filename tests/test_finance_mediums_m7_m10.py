# -*- coding: utf-8 -*-
"""M7–M10 regressions (finance package + owner registry helpers).

M7  — _fb_journal_post must never strand entries in 'posting' with no rollback.
M8  — owners_payload must expose the FULL apartment list for the range-report
      picker (the [:12] cut made units 13+ unpickable).
M9  — _save_json returns False on write failure (a swallowed disk error let
      ERP edits report ok:true then evaporate on restart).
M10 — _owner_lids matches owner names stripped (a trailing space silently
      dropped every unit of that owner).

Run: python3 tests/test_finance_mediums_m7_m10.py
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-m710")
os.makedirs("/tmp/ouja-test-state-m710", exist_ok=True)

import bot  # noqa: E402
from finance import api as fapi  # noqa: E402

fapi.attach(bot)


class JournalPostNoStrandingM7(unittest.TestCase):
    def test_failed_post_leaves_entries_approved(self):
        self._ledger = dict(bot._fb_ledger)
        self._enabled = bot.DAFTRA_POST_ENABLED
        self._conf = bot._daftra_configured
        self._maps = dict(bot._fb_mappings)
        try:
            bot.DAFTRA_POST_ENABLED = True
            bot._daftra_configured = lambda: True
            bot._fb_ledger.clear()
            bot._fb_ledger["e1"] = {"id": "e1", "status": "approved", "amount": 100,
                                    "direction": "expense", "category": "cat1",
                                    "description": "test"}
            bot._fb_mappings["cat1"] = {"daftra_account_name": "acc", "daftra_account_id": "7"}
            out = bot._fb_journal_post(["e1"], actor="test")
            self.assertFalse(out.get("ok"))
            self.assertEqual(bot._fb_ledger["e1"]["status"], "approved",
                             "a failed post must never strand the entry in 'posting'")
        finally:
            bot._fb_ledger.clear(); bot._fb_ledger.update(self._ledger)
            bot.DAFTRA_POST_ENABLED = self._enabled
            bot._daftra_configured = self._conf
            bot._fb_mappings.clear(); bot._fb_mappings.update(self._maps)


class OwnersPayloadFullListM8(unittest.TestCase):
    def test_apartments_all_is_complete(self):
        self._rows = fapi._registry_rows
        try:
            fapi._registry_rows = lambda: [
                {"owner": "أبو فهد", "apartment": "U%02d" % i, "mgmt_pct": 18}
                for i in range(1, 16)]                     # 15 units
            payload = fapi.owners_payload()
            row = payload["rows"][0]
            self.assertEqual(len(row["apartments"]), 12)   # card display cut
            self.assertEqual(len(row["apartments_all"]), 15,
                             "the range-report picker needs EVERY unit")
        finally:
            fapi._registry_rows = self._rows


class SaveJsonHonestM9(unittest.TestCase):
    def test_returns_true_on_success_false_on_failure(self):
        self.assertTrue(bot._save_json("m9_probe.json", {"x": 1}))
        before = bot._save_failures["count"]
        # an unserializable object forces a write failure
        self.assertFalse(bot._save_json("m9_bad.json", {"x": object()}))
        self.assertEqual(bot._save_failures["count"], before + 1)
        self.assertIn("m9_bad.json", bot._save_failures["last"])


class OwnerLidsStrippedM10(unittest.TestCase):
    def test_trailing_space_still_matches(self):
        self._reg = dict(bot._owner_registry)
        self._resolve = bot._owner_resolve_lid
        try:
            bot._owner_registry.clear()
            bot._owner_registry["k1"] = {"owner": "ابو فهد ", "apartment": "101A"}  # trailing space
            bot._owner_resolve_lid = lambda rec, listings: 7
            self.assertEqual(bot._owner_lids("ابو فهد", {}), [7])
            self.assertEqual(bot._owner_lids("ابو فهد ", {}), [7])
        finally:
            bot._owner_registry.clear(); bot._owner_registry.update(self._reg)
            bot._owner_resolve_lid = self._resolve


if __name__ == "__main__":
    unittest.main()
