# -*- coding: utf-8 -*-
"""MUSAED v3.1 — the second pass.

Every test here pins a defect found by reviewing v3 against production shapes:
the escape hatch that took the firewall down with the gate, R6 substring-matching
unit names into ordinary sentences, the debounce delaying emergencies, the quality
sample that could only ever harvest greetings, and the two parser corrections that
were right but unproven.

Synthetic data only: no network, no API keys, nothing is ever sent.
"""

import unittest
from unittest import mock

import bot


PROD_UNITS = {
    1: "F1", 2: "F2", 3: "101b", 4: "22", 5: "4511",
    6: "Ouja | HUE 202", 7: "Ouja | DAMAC Towers", 8: "HUE 202",
    9: "Ouja | Qurtuba-B20", 10: "MS (113)", 11: "C118", 12: "Ouja | العارض A11",
}


def _pin_units(units=PROD_UNITS):
    bot._fw_units_cache.update({"names": [], "ts": 0, "degraded": False})
    return mock.patch.object(bot, "get_listings_map", lambda: units)


class TestEscapeHatchIsSplit(unittest.TestCase):
    """MUSAED_V3=0 used to take the door-code block down with the review gate."""

    def test_the_gate_has_its_own_switch(self):
        with mock.patch.object(bot, "MUSAED_V3", True), \
                mock.patch.object(bot, "MUSAED_V3_GATE", False):
            self.assertFalse(bot._v3_gate_on())

    def test_killing_the_gate_leaves_the_firewall_up(self):
        with mock.patch.object(bot, "MUSAED_V3", True), \
                mock.patch.object(bot, "MUSAED_V3_GATE", False):
            ok, reason, _ = bot.outbound_firewall("كود الباب 4802")
        self.assertFalse(ok, "the firewall must survive MUSAED_V3_GATE=0")
        self.assertEqual(reason, "CODE_LEAK")

    def test_killing_the_master_switch_takes_everything_down(self):
        with mock.patch.object(bot, "MUSAED_V3", False):
            ok, _reason, _ = bot.outbound_firewall("كود الباب 4802")
            self.assertTrue(ok)
            self.assertFalse(bot._v3_gate_on())


class TestPosture(unittest.TestCase):
    """The owner must never have to open Railway to know what is switched on."""

    def _posture(self, auto, v3, gate):
        with mock.patch.object(bot, "ASSISTANT_AUTO", auto), \
                mock.patch.object(bot, "MUSAED_V3", v3), \
                mock.patch.object(bot, "MUSAED_V3_GATE", gate):
            return bot.musaed_posture()

    def test_the_flags_line_names_all_three_switches(self):
        flags, _ar, _en = self._posture(True, True, True)
        for token in ("MUSAED_V3=", "MUSAED_V3_GATE=", "ASSISTANT_AUTO="):
            self.assertIn(token, flags)

    def test_assistant_auto_off_is_stated_not_implied(self):
        """If nothing auto-sends at all, that has to be readable, not inferred."""
        _f, ar, en = self._posture(False, True, True)
        self.assertIn("NOTHING auto-sends", en)
        self.assertIn("لا شيء يُرسل تلقائياً", ar)

    def test_gate_on_says_only_greetings_auto_send(self):
        _f, _ar, en = self._posture(True, True, True)
        self.assertIn("Only greetings and thanks", en)

    def test_gate_off_is_flagged_as_v2_behaviour(self):
        _f, _ar, en = self._posture(True, True, False)
        self.assertIn("v2 behaviour", en)

    def test_the_posture_never_claims_a_dead_firewall_is_alive(self):
        """The whole point of the line is that it cannot mislead."""
        _f, ar, en = self._posture(True, False, False)
        self.assertIn("firewall is OFF", en)
        self.assertNotIn("firewall IS running", en)
        self.assertIn("MUSAED_V3_GATE=0", en, "it must name the correct lever")
        self.assertIn("مطفي", ar)

    def test_firewall_up_is_stated_when_it_is_up(self):
        _f, _ar, en = self._posture(True, True, False)
        self.assertIn("firewall IS running", en)


class TestSurgeGuard(unittest.TestCase):
    def setUp(self):
        bot._card_times.clear()
        bot._surge_last_alert[0] = 0.0

    def test_normal_volume_raises_nothing(self):
        for _ in range(10):
            self.assertIsNone(bot._note_approval_card())

    def test_a_surge_fires_once_and_reports_the_count(self):
        fired = [bot._note_approval_card() for _ in range(bot.MUSAED_SURGE_CARDS + 5)]
        hits = [f for f in fired if f]
        self.assertEqual(len(hits), 1, "the alert must not repeat inside the window")
        self.assertGreaterEqual(hits[0], bot.MUSAED_SURGE_CARDS)

    def test_the_volume_line_counts_what_it_says(self):
        bot._daily_metrics.clear()
        bot.metric_bump("approval_cards", 3)
        bot.metric_bump("auto_sent", 2)
        bot.metric_bump("fw_block_code_leak", 1)
        bot.metric_bump("fw_block_placeholder", 2)
        bot.metric_bump("escalations_created", 4)
        cards, auto, fw, esc = bot.musaed_volume_today()
        self.assertEqual((cards, auto, fw, esc), (3, 2, 3, 4))


class TestR6TokenMatching(unittest.TestCase):
    """Substring matching blocked real replies against the owner's real names."""

    def setUp(self):
        self._p = _pin_units(); self._p.start()
        self.addCleanup(self._p.stop)

    def _blocked(self, reply, own):
        _ok, reason, _ = bot.outbound_firewall(reply, {"unit": own, "guest_text": reply})
        return reason == "WRONG_UNIT"

    def test_a_duration_is_not_a_unit(self):
        self.assertFalse(self._blocked("عندك 22 دقيقة على الوصول", "Ouja | HUE 202"))

    def test_a_price_is_not_a_unit(self):
        self.assertFalse(self._blocked("المبلغ 4511 ريال شامل", "Ouja | HUE 202"))

    def test_a_short_name_inside_a_word_is_not_a_unit(self):
        """F2 must not match inside 'floor' or any other word."""
        self.assertFalse(self._blocked("Wifi is on the 2nd floor", "Ouja | HUE 202"))

    def test_a_bare_number_WITH_a_unit_cue_still_blocks(self):
        self.assertTrue(self._blocked("شقتك رقم 4511 في الدور الخامس", "Ouja | HUE 202"))

    def test_a_real_foreign_unit_still_blocks(self):
        self.assertTrue(self._blocked("شقتك هي Ouja | DAMAC Towers",
                                      "Ouja | Qurtuba-B20"))

    def test_a_shorter_form_of_the_guests_own_unit_is_not_foreign(self):
        """«HUE 202» inside «Ouja | HUE 202» is their own apartment."""
        self.assertFalse(self._blocked("وحدتك HUE 202 في الدور الثاني", "Ouja | HUE 202"))

    def test_swap_framing_still_permits_the_name(self):
        self.assertFalse(self._blocked(
            "عندنا وحدة بديلة (Ouja | DAMAC Towers) ليلتها فاضية", "Ouja | Qurtuba-B20"))

    def test_names_are_tried_longest_first(self):
        names = bot._fw_known_unit_names()
        self.assertEqual(names, sorted(names, key=len, reverse=True))

    def test_names_shorter_than_four_characters_are_dropped(self):
        for n in bot._fw_known_unit_names():
            self.assertGreaterEqual(len(n), 4)


class TestR6DegradesToCache(unittest.TestCase):
    """A transient API blip must not silently switch R6 off for an hour."""

    def test_it_falls_back_to_the_persisted_copy_and_says_so(self):
        bot._fw_units_cache.update({"names": [], "ts": 0, "degraded": False})
        bot._daily_metrics.clear()
        stored = {"names": ["Ouja | DAMAC Towers", "Ouja | Qurtuba-B20"]}
        def boom():
            raise RuntimeError("Hostaway down")
        with mock.patch.object(bot, "get_listings_map", boom), \
                mock.patch.object(bot, "_load_json", lambda n, d=None: stored), \
                mock.patch.object(bot, "log_event") as logged:
            names = bot._fw_known_unit_names()
        self.assertEqual(len(names), 2, "R6 must keep running on the last good copy")
        self.assertTrue(bot._fw_units_cache["degraded"])
        self.assertTrue(logged.called, "a degraded catalogue must be visible")
        self.assertEqual(bot._day_row().get("fw_units_degraded"), 1)

    def test_a_successful_fetch_persists_the_names(self):
        bot._fw_units_cache.update({"names": [], "ts": 0, "degraded": False})
        with mock.patch.object(bot, "get_listings_map", lambda: PROD_UNITS), \
                mock.patch.object(bot, "_save_json", return_value=True) as saved:
            bot._fw_known_unit_names()
        self.assertTrue(saved.called, "the catalogue must survive a restart")


class TestEmergencyBypassesDebounce(unittest.TestCase):
    """A fire must not wait 12 seconds for a follow-up message."""

    URGENT = ["فيه حريق بالشقة", "في دخان طالع من المطبخ", "صار عندي إصابة",
              "نحتاج إسعاف", "أنا محبوس بالحمام", "مقفول علي الباب",
              "there is a fire", "smoke in the kitchen", "my son is injured",
              "I'm locked out", "this is an emergency"]
    CALM = ["كم وقت الخروج؟", "شكرا جزيلا", "وين المدخل؟", "Thank you so much"]

    def test_every_emergency_word_trips_the_risk_filter(self):
        for t in self.URGENT:
            with self.subTest(t=t):
                self.assertTrue(bot._is_risk_class(t))

    def test_ordinary_messages_do_not(self):
        for t in self.CALM:
            with self.subTest(t=t):
                self.assertFalse(bot._is_risk_class(t))

    def test_emergencies_also_stay_off_the_auto_path(self):
        """Faster to a human AND still not answerable by the bot alone."""
        for t in self.URGENT:
            with self.subTest(t=t):
                self.assertTrue(bot._is_risk_class(t, "ترحيب"))


class TestQualitySampleHarvestsSomethingUseful(unittest.TestCase):
    def setUp(self):
        bot._daily_metrics.clear()

    def test_an_edited_sample_is_counted(self):
        item = {"conversation_id": "c1", "unit": "U", "guest": "G",
                "guest_text": "q", "_v3_sample": True}
        bot.record_learning(item, "مسودة الرد الأصلية كما كتبها المساعد",
                            "رد بشري مختلف تماماً بعد التعديل",
                            via="discord_edit", approver="Faisal")
        self.assertEqual(bot._day_row().get("v3_quality_sample_edited"), 1)

    def test_a_rubber_stamp_is_NOT_counted_as_learning(self):
        item = {"conversation_id": "c2", "unit": "U", "guest": "G",
                "guest_text": "q", "_v3_sample": True}
        bot.record_learning(item, "نفس النص تماماً", "نفس النص تماماً",
                            via="discord_send", approver="Faisal")
        self.assertIsNone(bot._day_row().get("v3_quality_sample_edited"))

    def test_an_unsampled_edit_is_not_miscounted(self):
        item = {"conversation_id": "c3", "unit": "U", "guest": "G", "guest_text": "q"}
        bot.record_learning(item, "مسودة", "رد مختلف تماماً عن المسودة",
                            via="discord_edit", approver="Faisal")
        self.assertIsNone(bot._day_row().get("v3_quality_sample_edited"))


class TestSwapDetectionAgainstProduction(unittest.TestCase):
    """The six real wrong-unit pairs from the 90-day audit, plus the two
    degenerate cases that must name nothing at all."""

    PAIRS = [
        ("Qurtuba-B20", "DAMAC Towers", True),
        ("الغدير-B10", "HUE 202", True),
        ("HUE 9", "العارض A11", True),
        ("4101", "MS (113)", True),
        ("C08 MJ", "C118", True),
        ("Jood12", "C118", True),
        ("HUE 202", "HUE 202", False),      # same unit — not a swap
        (None, "HUE 202", False),           # unknown own unit — name nothing
    ]

    def _reply(self, own, proposed):
        return bot._early_pending_reply({
            "guest_text": "ابي ادخل بدري", "requested_label": "12:00 PM",
            "original_unit": own, "proposed_unit": proposed, "offhours": False})

    def test_every_production_pair(self):
        for own, proposed, should_name in self.PAIRS:
            with self.subTest(own=own, proposed=proposed):
                out = self._reply(own, proposed) or ""
                self.assertEqual(proposed in out, should_name)

    def test_a_named_swap_is_always_framed_as_one(self):
        for own, proposed, should_name in self.PAIRS:
            if not should_name:
                continue
            with self.subTest(own=own, proposed=proposed):
                out = self._reply(own, proposed) or ""
                self.assertIn("وحدة بديلة", out)

    def test_a_missing_own_unit_names_nothing_rather_than_guessing(self):
        out = self._reply(None, "HUE 202") or ""
        self.assertNotIn("HUE 202", out)
        self.assertNotIn("وحدة بديلة", out)


class TestArrivalSurface(unittest.TestCase):
    """The flagship 3 AM fix would have silently never fired: «وصولي ٣ الفجر»
    contains no check-in word at all."""

    LATE_NIGHT = ["وصولي ٣ الفجر", "واصل ٤ الفجر", "بوصل ٢ بعد منتصف الليل",
                  "رحلتي تنزل ٣ الصبح", "my flight lands at 3am", "arriving 2:30 AM"]
    EARLY = ["الساعة ١٢ الظهر", "١٠ الصبح", "أبي أدخل الساعة ١٢ الظهر",
             "أقدر أدخل الساعة 10 الصبح بدل 3؟"]
    NOT_A_REQUEST = ["You told me check in is at 3", "Can I check in at 3 pm?",
                     "شكرا جزيلا"]

    def test_late_night_arrivals(self):
        for t in self.LATE_NIGHT:
            with self.subTest(t=t):
                got = bot._early_checkin_request(t)
                self.assertIsNotNone(got, f"not detected at all: {t}")
                self.assertEqual(got["kind"], "late_night_arrival")

    def test_real_early_checkins(self):
        for t in self.EARLY:
            with self.subTest(t=t):
                got = bot._early_checkin_request(t)
                self.assertIsNotNone(got, f"not detected at all: {t}")
                self.assertEqual(got["kind"], "early_checkin")

    def test_non_requests(self):
        for t in self.NOT_A_REQUEST:
            with self.subTest(t=t):
                self.assertIsNone(bot._early_checkin_request(t))

    def test_midnight_marker_is_am_not_pm(self):
        """«منتصف الليل» must beat «الليل» in the marker alternation."""
        got = bot._early_checkin_request("بوصل ٢ بعد منتصف الليل")
        self.assertEqual(got["requested_minutes"], 120)


if __name__ == "__main__":
    unittest.main()
