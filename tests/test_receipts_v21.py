# -*- coding: utf-8 -*-
"""Slice 4 regression — receipt links end-to-end.

Pins:
  • the Sheets ingest maps the «رفع الفاتوره | Upload Invoice» column to the
    `receipt_link` field on _expenses (THE verified field name)
  • statement_payload rewrites expense receipt links to the owner-scoped proxy
    (/fin/receipt/{id}?t=<token>) when the owner holds an active link
  • the proxy scope primitive (owner_apartments) keeps another owner's
    expense OUT of reach (the 403 path)

Run: python3 tests/test_receipts_v21.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-s4"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)
JUNE = "2026-06"
DRIVE = "https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz0123456"


class IngestFieldTest(unittest.TestCase):
    def test_sheet_row_maps_invoice_column_to_receipt_link(self):
        idx = {"timestamp": 0, "submitter": 1, "apartment": 2, "amount": 3,
               "expense_date": 4, "receipt_link": 5, "description": 6}
        row = ["2026-06-08 10:00", "أحمد", "101A", "350", "2026-06-08", DRIVE, "سباكة"]
        sub = bot._exp_sheet_row_to_sub(idx, row)
        self.assertEqual(sub["receipt_link"], DRIVE)         # THE field name, pinned
        self.assertEqual(sub["no_receipt_reason"], "")


class ProxyRewriteTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("R1")] = {
            "apartment": "R1", "owner": "مالك الفواتير", "mgmt_pct": 20.0, "lid": 41,
            "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_links.clear()
        bot._expenses.clear()
        bot._expenses["E100"] = {"id": "E100", "apartment": "Ouja | R1", "listing_id": 41,
                                 "amount": 200.0, "expense_date": "2026-06-07",
                                 "status": "verified", "approval_status": "approved",
                                 "hostaway_verified": True, "receipt_link": DRIVE,
                                 "category": "صيانة", "note": "تصليح مكيف"}
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: [{
            "id": "rr1", "listingMapId": 41, "status": "new", "channelName": "Airbnb",
            "arrivalDate": "2026-06-04", "departureDate": "2026-06-07", "nights": 3,
            "guestName": "ضيف", "airbnbExpectedPayoutAmount": 900.0,
            "totalPrice": 1100.0, "refundAmount": None}]
        bot.get_listings_map = lambda: {41: "Ouja | R1"}
        bot._owner_portal_cache.clear()

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        bot._owner_links.clear()
        bot._expenses.clear()
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None

    def test_editor_payload_uses_proxy_when_link_active(self):
        rec = bot._owner_link_get_or_create("مالك الفواتير", "tester")
        d = OW.statement_payload("مالك الفواتير", JUNE)
        exp = d["statement"]["exp_lines"][0]
        self.assertEqual(exp["receipt_url"], "/fin/receipt/E100?t=" + rec["token"])

    def test_editor_payload_keeps_raw_link_without_active_token(self):
        d = OW.statement_payload("مالك الفواتير", JUNE)
        self.assertEqual(d["statement"]["exp_lines"][0]["receipt_url"], DRIVE)

    def test_proxy_scope_blocks_other_owners(self):
        # the 403 path inside /fin/receipt: expense apartment ∉ token-owner scope
        bot._owner_registry[bot._owner_key("Z9")] = {
            "apartment": "Z9", "owner": "مالك ثاني", "mgmt_pct": 20.0, "lid": 99,
            "cleaning": {"type": "ours", "amount": 0}}
        apts_other, lids_other = fapi.owner_apartments("مالك ثاني")
        ex = bot._expenses["E100"]
        in_scope = (((ex.get("apartment") or "").strip() in apts_other)
                    or (str(ex.get("listing_id") or "") in lids_other))
        self.assertFalse(in_scope)                            # → proxy returns 403
        apts_own, lids_own = fapi.owner_apartments("مالك الفواتير")
        self.assertIn("41", lids_own)                         # the rightful owner passes


if __name__ == "__main__":
    unittest.main(verbosity=2)
