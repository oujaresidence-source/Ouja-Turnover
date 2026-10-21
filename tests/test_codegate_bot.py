# -*- coding: utf-8 -*-
"""«تسليم الرموز» — bot.py side. Run: python3 -m unittest tests.test_codegate_bot"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-cg")
os.makedirs("/tmp/ouja-test-state-cg", exist_ok=True)

import bot  # noqa: E402
sys.stdout.flush()


class TestWiring(unittest.TestCase):
    def setUp(self):
        # Sibling codegate tests leave HOST wired to their own temp STATE_DIR (a unit list that
        # outranks the repo seed). Re-wire to this process's real wiring so order can't matter.
        self.assertTrue(bot._cg_wire())

    def test_package_imported_and_wired(self):
        self.assertTrue(bot._HAS_CODEGATE)
        self.assertTrue(bot._cg_wire())
        self.assertIsNotNone(bot._codegate.HOST.today_arrivals)
        self.assertIsNotNone(bot._codegate.HOST.escalate)

    def test_view_custom_ids_are_persistent(self):
        v = bot.CodegateView()
        ids = sorted(c.custom_id for c in v.children)
        self.assertEqual(ids, ["cg_release", "cg_undo"])
        self.assertIsNone(v.timeout)

    def test_gated_helpers(self):
        self.assertTrue(bot._cg_gated(461328))       # C2 NFL
        self.assertTrue(bot._cg_gated("526697"))     # 103 NRJS (owner decision)
        self.assertFalse(bot._cg_gated(999999))
        self.assertFalse(bot._cg_gated(None))

    def test_messages_shape(self):
        orig = bot.api_get
        bot.api_get = lambda path, params=None: {"result": [
            {"isIncoming": 1, "body": "I agree", "date": "2026-10-21 10:05:00"},
            {"isIncoming": 0, "body": "rules", "date": "2026-10-21 10:00:00"}]}
        try:
            rows = bot._cg_messages("c1")
        finally:
            bot.api_get = orig
        self.assertEqual(rows[0]["inbound"], True)
        self.assertEqual(rows[0]["at"].hour, 10)
        self.assertEqual(rows[1]["inbound"], False)

    def test_today_arrivals_filters_and_shapes(self):
        orig_ci, orig_lm = bot.unit_checkin_minutes, bot.get_listings_map
        bot.unit_checkin_minutes = lambda lid: 15 * 60
        bot.get_listings_map = lambda: {461328: "C2 NFL"}
        self.addCleanup(lambda: setattr(bot, "unit_checkin_minutes", orig_ci))
        self.addCleanup(lambda: setattr(bot, "get_listings_map", orig_lm))
        orig = bot._ha_reservations_window
        bot._ha_reservations_window = lambda *a: [
            {"id": 1, "status": "new", "arrivalDate": bot.now_riyadh().date().isoformat(),
             "listingMapId": 461328, "guestName": "Sara", "conversationId": 7, "checkInTime": 16},
            {"id": 2, "status": "cancelled", "arrivalDate": bot.now_riyadh().date().isoformat(),
             "listingMapId": 461328}]
        try:
            rows = bot._cg_today_arrivals()
        finally:
            bot._ha_reservations_window = orig
        self.assertEqual([r["res_id"] for r in rows], ["1"])
        self.assertTrue(rows[0]["checkin_at"].endswith("16:00:00+03:00"))
        self.assertEqual(rows[0]["conversation_id"], "7")


if __name__ == "__main__":
    unittest.main()
