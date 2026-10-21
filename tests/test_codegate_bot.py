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


    def test_card_view_has_real_callbacks(self):
        # discord.py dispatches a click on a card to the view stored for THAT message id before
        # the bot.add_view() one, so a card's view must itself carry the callbacks.
        v = bot._cg_view(["release"])
        self.assertIsInstance(v, bot.CodegateView)
        self.assertEqual([c.custom_id for c in v.children], ["cg_release"])
        # decorator buttons carry an INSTANCE callback; a bare Button keeps the base no-op
        self.assertIn("callback", vars(v.children[0]))
        self.assertEqual(v.children[0].callback.callback.__name__, "release")
        self.assertIsNone(v.timeout)
        u = bot._cg_view(["undo"])
        self.assertEqual([c.custom_id for c in u.children], ["cg_undo"])
        self.assertEqual(sorted(c.custom_id for c in bot._cg_view(["release", "undo"]).children),
                         ["cg_release", "cg_undo"])
        self.assertEqual(list(bot._cg_view([]).children), [])

    def test_click_dispatches_to_real_callback(self):
        import asyncio
        import discord
        from types import SimpleNamespace as NS
        from discord.ui.view import ViewStore

        async def go():
            store = ViewStore(NS())
            store.add_view(bot.CodegateView(), None)        # bot.add_view at boot
            store.add_view(bot._cg_view(["release"]), 111)  # what ch.send(view=) does
            key = (discord.ComponentType.button.value, "cg_release")
            item = store._views.get(111, {}).get(key) or store._views.get(None, {}).get(key)
            return item

        item = asyncio.new_event_loop().run_until_complete(go())
        self.assertIsNotNone(item)
        self.assertIsInstance(item.view, bot.CodegateView)
        self.assertIn("callback", vars(item))
        self.assertEqual(item.callback.callback.__name__, "release")

    def test_button_labels_match_engine(self):
        v = bot.CodegateView()
        labels = {c.custom_id: c.label for c in v.children}
        self.assertEqual(labels["cg_release"], bot._codegate.engine.LABEL_RELEASE)
        self.assertEqual(labels["cg_undo"], bot._codegate.engine.LABEL_UNDO)

    def test_tick_minutes_survives_garbage(self):
        old = os.environ.get("CODEGATE_TICK_MIN")
        self.addCleanup(lambda: os.environ.pop("CODEGATE_TICK_MIN", None) if old is None
                        else os.environ.__setitem__("CODEGATE_TICK_MIN", old))
        for raw, want in (("abc", 10), ("", 10), ("0", 1), ("5", 5)):
            os.environ["CODEGATE_TICK_MIN"] = raw
            self.assertEqual(bot._cg_tick_minutes(), want, raw)

    def test_ungated_arrival_skipped_without_checkin_lookup(self):
        calls = []
        orig_ci, orig_lm = bot.unit_checkin_minutes, bot.get_listings_map
        bot.unit_checkin_minutes = lambda lid: calls.append(lid) or 15 * 60
        bot.get_listings_map = lambda: {461328: "C2 NFL", 999999: "Other"}
        self.addCleanup(lambda: setattr(bot, "unit_checkin_minutes", orig_ci))
        self.addCleanup(lambda: setattr(bot, "get_listings_map", orig_lm))
        orig = bot._ha_reservations_window
        today = bot.now_riyadh().date().isoformat()
        bot._ha_reservations_window = lambda *a: [
            {"id": 1, "status": "new", "arrivalDate": today, "listingMapId": 999999},
            {"id": 2, "status": "new", "arrivalDate": today, "listingMapId": 461328}]
        try:
            rows = bot._cg_today_arrivals()
        finally:
            bot._ha_reservations_window = orig
        self.assertEqual([r["res_id"] for r in rows], ["2"])
        self.assertEqual(calls, [461328])


if __name__ == "__main__":
    unittest.main()
