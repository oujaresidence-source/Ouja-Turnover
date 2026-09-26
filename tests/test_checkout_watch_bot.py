# -*- coding: utf-8 -*-
"""
«متابعة الخروج» — the bot.py side: the REAL outbound firewall, the oujact «no_answer» state,
the channel sweep across overflow categories (and never the demo category), and the wiring.

Run: python3 -m unittest tests.test_checkout_watch_bot
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-cw")
os.makedirs("/tmp/ouja-test-state-cw", exist_ok=True)

import bot  # noqa: E402
sys.stdout.flush()
from checkout import flow, texts  # noqa: E402
from checkout.host import HOST  # noqa: E402


class FakeCategory:
    _n = 0

    def __init__(self, name):
        FakeCategory._n += 1
        self.id = FakeCategory._n
        self.name = name
        self.text_channels = []


class FakeChannel:
    _n = 5000

    def __init__(self, name, category, topic=None):
        FakeChannel._n += 1
        self.id = FakeChannel._n
        self.name = name
        self.category = category
        self.topic = topic
        category.text_channels.append(self)


class FakeGuild:
    def __init__(self):
        self.categories = []

    def cat(self, name):
        c = FakeCategory(name)
        self.categories.append(c)
        return c


class TestFirewall(unittest.TestCase):
    """The Airbnb body must pass the outbound firewall — called for real, not mocked."""

    def setUp(self):
        self._v3 = bot.MUSAED_V3
        bot.MUSAED_V3 = True

    def tearDown(self):
        bot.MUSAED_V3 = self._v3

    def test_both_bodies_pass_for_many_guest_names(self):
        for g in ("Sara Ahmed", "محمد 2231", "Guest 4455", "", "عبدالله بن فهد", "Lee"):
            for second in (False, True):
                body = texts.airbnb_body(g, second=second)
                ok, reason, _clean = bot.outbound_firewall(body)
                self.assertTrue(ok, (g, second, reason))
                self.assertFalse(any(c.isdigit() for c in body))

    def test_firewall_is_live_in_this_test(self):
        ok, reason, _ = bot.outbound_firewall("كود الباب 4471")      # positive control
        self.assertFalse(ok)
        self.assertEqual(reason, "CODE_LEAK")


class TestOujactState(unittest.TestCase):

    def test_no_answer_is_a_valid_checkout_state(self):
        self.assertIn("no_answer", bot.OUJACT_CHECKOUT_STATES)
        self.assertEqual(bot._OUJACT_REASON["no_answer"][0], "الضيف ما رد — لا تدخل قبل التأكيد")

    def test_priority_tier_90(self):
        now = datetime.datetime.now(bot.TZ)
        it = {"checkout": now - datetime.timedelta(hours=1), "checkin_today": True}
        self.assertEqual(bot._oujact_priority(it, "no_answer", False, now), (90, "no_answer"))
        self.assertEqual(bot._oujact_priority(it, "inside", False, now), (95, "inside"))
        self.assertEqual(bot._oujact_priority(it, "late_checkout", False, now)[0], 80)

    def test_every_state_the_watch_writes_is_accepted(self):
        from checkout import engine
        for ans, code in (("yes", None), ("noanswer", None), ("surprise", None),
                          ("no", "late_ok"), ("no", "packing")):
            self.assertIn(engine.oujact_state_for(ans, code), bot.OUJACT_CHECKOUT_STATES)


class TestChannelSweep(unittest.TestCase):

    def test_overflow_categories_scanned_demo_ignored(self):
        g = FakeGuild()
        base = g.cat(bot.CATEGORY_NAME)
        for i in range(50):                                      # a FULL base category
            FakeChannel("u%d" % i, base, "oujact:1 oujact-key:%d:2026-09-26 hostaway-res:%d"
                        % (1000 + i, 9000 + i))
        over = g.cat(bot.CATEGORY_NAME + " ٢")
        spilled = FakeChannel("spilled", over,
                              "oujact:1 oujact-key:77:2026-09-26 hostaway-res:1 cleaning-review:1")
        FakeChannel("no-key", over, "just a room")
        demo = g.cat(flow.demo_category_name())
        FakeChannel("تجربة-1-طلع", demo, "oujact-key:88:2026-09-26")   # must never be scanned
        got = bot._cw_channels_in(g)
        keys = {c["key"] for c in got}
        self.assertEqual(len(got), 51)
        self.assertIn("77:2026-09-26", keys)
        self.assertNotIn("88:2026-09-26", keys)
        sp = next(c for c in got if c["key"] == "77:2026-09-26")
        self.assertEqual(sp, {"channel_id": str(spilled.id), "key": "77:2026-09-26",
                              "review": True})

    def test_no_turnover_category_means_no_channels(self):
        self.assertEqual(bot._cw_channels_in(FakeGuild()), [])
        self.assertEqual(bot._cw_channels_in(None), [])


class TestTodayTurnovers(unittest.TestCase):
    """Synthetic reservations in, the numbers out — no Hostaway."""

    def setUp(self):
        self.saved = {k: getattr(bot, k) for k in ("_ha_reservations_window", "get_listings_map",
                                                    "_ls_get")}
        self.today = datetime.datetime.now(bot.TZ).date().isoformat()
        deps = [
            {"id": 1, "status": "new", "listingMapId": 11, "departureDate": self.today,
             "checkOutTime": 11, "guestName": "Sara", "phone": " 0501234567 ",
             "conversationId": 777, "channelName": "airbnbOfficial"},
            {"id": 1, "status": "new", "listingMapId": 11, "departureDate": self.today},  # dup
            {"id": 2, "status": "cancelled", "listingMapId": 12, "departureDate": self.today},
            {"id": 3, "status": "modified", "listingMapId": 13, "departureDate": self.today,
             "checkOutTime": None, "guestFirstName": "Omar"},
            {"id": 4, "status": "new", "listingMapId": 14, "departureDate": "2020-01-01"},
        ]
        arrs = [{"id": 9, "status": "new", "listingMapId": 11, "arrivalDate": self.today,
                 "checkInTime": 16},
                {"id": 10, "status": "new", "listingMapId": 11, "arrivalDate": self.today,
                 "checkInTime": 15},
                {"id": 11, "status": "cancelled", "listingMapId": 13, "arrivalDate": self.today,
                 "checkInTime": 14}]
        bot._ha_reservations_window = lambda ps, pe, s, e: deps if ps.startswith("departure") else arrs
        bot.get_listings_map = lambda: {11: "Ouja | الملقا 1"}
        bot._ls_get = lambda: {"listings": {"13": {"internal_name": "Ouja | النرجس", "clean_max": 55}}}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(bot, k, v)

    def test_confirmed_departures_today_only_with_times(self):
        rows = {r["lid"]: r for r in bot._cw_today_turnovers()}
        self.assertEqual(sorted(rows), [11, 13])
        a = rows[11]
        self.assertEqual(a["unit"], "Ouja | الملقا 1")
        self.assertEqual(a["checkout_at"][11:16], "11:00")
        self.assertEqual(a["checkin_at"][11:16], "15:00")        # the EARLIEST arrival
        self.assertEqual((a["phone"], a["conversation_id"], a["res_id"]),
                         ("0501234567", "777", "1"))
        self.assertEqual(a["clean_minutes"], bot.OUJACT_CLEAN_MAX)
        b = rows[13]
        self.assertEqual(b["unit"], "Ouja | النرجس")
        self.assertEqual(b["checkout_at"][11:16], "%02d:00" % bot.DEFAULT_CHECKOUT_HOUR)
        self.assertIsNone(b["checkin_at"])                        # cancelled arrival ignored
        self.assertEqual(b["clean_minutes"], 55)
        self.assertEqual(b["guest"], "Omar")


class TestCleaningStatus(unittest.TestCase):

    def setUp(self):
        self.saved = (bot._cleaning_reports, bot._cleanproof_report_id, bot._oujact_done)
        bot._cleanproof_report_id = lambda lid, day: "R-%s-%s" % (lid, day)
        bot._oujact_done = {}

    def tearDown(self):
        bot._cleaning_reports, bot._cleanproof_report_id, bot._oujact_done = self.saved

    def test_reads_the_existing_report_store(self):
        bot._cleaning_reports = {"R-5-2026-09-26": {"status": "manager_approved"},
                                 "R-6-2026-09-26": {"status": "pending_manager_review"}}
        self.assertEqual(bot._cw_cleaning_status(5, "2026-09-26"), "approved")
        self.assertEqual(bot._cw_cleaning_status(6, "2026-09-26"), "submitted")
        self.assertEqual(bot._cw_cleaning_status(7, "2026-09-26"), "none")
        bot._oujact_done = {"7:2026-09-26": "2026-09-26"}
        self.assertEqual(bot._cw_cleaning_status(7, "2026-09-26"), "submitted")


class TestWiring(unittest.TestCase):

    def test_wire_hands_over_the_real_helpers(self):
        self.assertTrue(bot._HAS_CHECKOUT)
        saved = {k: getattr(HOST, k) for k in ("wa_number", "set_oujact_state", "log_oujact",
                                                "early_hint", "today_turnovers", "channels")}
        try:
            self.assertTrue(bot._cw_wire())
            self.assertIs(HOST.wa_number, bot._wa_from_phone)
            self.assertIs(HOST.set_oujact_state, bot._oujact_set_checkout_state)
            self.assertIs(HOST.log_oujact, bot._oujact_log_status)
            self.assertIs(HOST.early_hint, bot._clean_early_departure_active)
            self.assertIs(HOST.today_turnovers, bot._cw_today_turnovers)
        finally:
            for k, v in saved.items():
                setattr(HOST, k, v)

    def test_wa_rules(self):
        self.assertEqual(bot._wa_from_phone("0501234567"), "wa.me/966501234567")
        self.assertEqual(bot._wa_from_phone("+966 50 123 4567"), "wa.me/966501234567")
        self.assertEqual(bot._wa_from_phone("00971501234567"), "wa.me/971501234567")
        self.assertEqual(bot._wa_from_phone(""), "")

    def test_button_ids_match_the_listener(self):
        v = bot._cw_view(list(flow.CARD_BUTTONS) + ["demo_ff"])
        ids = sorted(i.custom_id for i in v.children)
        self.assertEqual(ids, sorted(bot._CW_IDS))

    def test_commands_registered(self):
        names = {c.name for c in bot.bot.tree.get_commands()}
        for n in ("checkout-start", "checkout-stop", "checkout-risk", "checkout-demo",
                  "checkout-demo-end", "checkout-report"):
            self.assertIn(n, names)
        prefix = {c.name for c in bot.bot.commands}
        for n in ("تشغيل-الخروج", "ايقاف-الخروج", "خطر-اليوم", "تجربة-الخروج", "انهاء-التجربة",
                  "تقرير-الخروج"):
            self.assertIn(n, prefix)


def tearDownModule():
    # bot.py prints at import; flush before unittest writes its summary so the LAST line of
    # the run is the verdict (GATES.md G3 reads only that line).
    sys.stdout.flush()


if __name__ == "__main__":
    unittest.main()
