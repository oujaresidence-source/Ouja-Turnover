# -*- coding: utf-8 -*-
"""Slice 3 regression — دورة الشهر: status pipeline, auto-opened flip, anomalies.

Run: python3 tests/test_cycle_v21.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-s3"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)
JUNE = "2026-06"


class _Req:
    headers = {}
    query = {}


def _resv(rid, payout, checkin):
    return {"id": rid, "listingMapId": 31, "status": "new", "channelName": "Airbnb",
            "arrivalDate": checkin, "departureDate": checkin[:8] + "27", "nights": 2,
            "guestName": "G" + rid, "airbnbExpectedPayoutAmount": payout,
            "totalPrice": (payout or 900) + 200, "refundAmount": None}


class CycleBoardTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("C1")] = {
            "apartment": "C1", "owner": "مالك الدورة", "mgmt_pct": 20.0, "lid": 31,
            "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_links.clear()
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        # June has income; March/April/May had triple → deviation anomaly fires
        def fake_window(s, e, pad_days=45):
            mk = s.isoformat()[:7]
            if mk == "2026-06":
                return [_resv("c1", 1000.0, "2026-06-05"),
                        _resv("c2", None, "2026-06-12")]      # missing payout anomaly
            return [_resv("p" + mk, 3000.0, mk + "-05")]
        bot.fetch_reservations_window = fake_window
        bot.get_listings_map = lambda: {31: "Ouja | C1"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        self._actor_orig = fapi.actor
        fapi.actor = lambda r: "tester"

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        fapi.actor = self._actor_orig
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._owner_links.clear()
        bot._owner_portal_cache.clear()

    def test_board_flags_deviation_and_missing_payout(self):
        d = OW.cycle_board(JUNE)
        self.assertTrue(d["ok"])
        row = d["rows"][0]
        self.assertEqual(row["owner"], "مالك الدورة")
        keys = {a["key"] for a in row["anomalies"]}
        self.assertIn("net_deviation", keys)     # 800 vs 2400 avg = −67%
        self.assertIn("missing_payout", keys)
        self.assertTrue(row["flagged"])
        self.assertEqual(d["counts"]["flagged"], 1)

    def test_status_pipeline_and_bulk(self):
        r, code = OW.cycle_status_set(_Req(), {"owners": ["مالك الدورة"], "m": JUNE, "to": "ready"})
        self.assertEqual(code, 200)
        self.assertEqual(r["changed"], ["مالك الدورة"])
        rec = OW.stmt_rec("مالك الدورة", JUNE)
        self.assertEqual(rec["status"], "ready")
        self.assertEqual(rec["status_log"][-1]["to"], "ready")
        r2, _ = OW.cycle_status_set(_Req(), {"owners": ["مالك الدورة"], "m": JUNE, "to": "bogus"})
        self.assertEqual(r2["error"], "bad_status")

    def test_opened_flips_from_link_touch(self):
        OW.cycle_status_set(_Req(), {"owners": ["مالك الدورة"], "m": JUNE, "to": "sent"})
        bot._owner_link_get_or_create("مالك الدورة", "tester")
        bot._owner_link_touch("مالك الدورة")     # the owner opens the page
        d = OW.cycle_board(JUNE)
        self.assertEqual(d["rows"][0]["status"], "opened")
        self.assertEqual(d["counts"]["opened"], 1)

    def test_regen_all_and_copy_all(self):
        bot._owner_link_get_or_create("مالك الدورة", "tester")
        old = bot._owner_links["مالك الدورة"]["token"]
        r, _ = OW.cycle_links(_Req(), {"action": "regen_all"})
        self.assertEqual(r["regenerated"], 1)
        self.assertNotEqual(bot._owner_links["مالك الدورة"]["token"], old)
        r2, _ = OW.cycle_links(_Req(), {"action": "copy_all"})
        self.assertEqual(len(r2["links"]), 1)
        self.assertIn("/fin/o/", r2["links"][0]["url"])

    def test_wa_template_roundtrip(self):
        self.assertIn("{link}", OW.wa_template())
        OW.wa_template_set(_Req(), "هلا {owner} — كشف {month}: {net}\n{link}")
        self.assertTrue(OW.wa_template().startswith("هلا"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
