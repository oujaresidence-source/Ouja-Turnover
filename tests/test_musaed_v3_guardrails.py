# -*- coding: utf-8 -*-
"""MUSAED v3 guardrails — the rules that now live in CODE, not in the prompt.

Every test here pins a failure that actually reached a guest in production
between 27 May and 22 Aug 2026. Synthetic data only: no network, no API keys,
and send_guest_message is never called for real.
"""

import os
import unittest
from datetime import date
from unittest import mock

import bot
import eval_musaed as ev


# The firewall's WRONG_UNIT rule reads the live listings map. Every test that
# could reach it pins a synthetic catalogue instead.
FAKE_UNITS = {
    1: "Ouja | Qurtuba-B20", 2: "Ouja | DAMAC Towers", 3: "Ouja | HUE 202",
    4: "Ouja | C118", 5: "Ouja | العارض A11", 6: "Ouja | B14",
}


def _pin_units(names=None):
    m = names if names is not None else FAKE_UNITS
    bot._fw_units_cache["names"] = {str(v).strip() for v in m.values()}
    bot._fw_units_cache["ts"] = 9e18          # never expires during a test
    return mock.patch.object(bot, "get_listings_map", lambda: m)


def fw(body, item=None):
    return bot.outbound_firewall(body, item)


class TestFirewallCodeLeak(unittest.TestCase):
    """R1 — the rule the prompt called 'no exceptions'. It had four."""

    def setUp(self):
        self._p = _pin_units(); self._p.start()
        self.addCleanup(self._p.stop)

    def test_arabic_code_with_digits_is_blocked(self):
        ok, reason, _ = fw("كود الباب 4802 تفضل")
        self.assertFalse(ok); self.assertEqual(reason, "CODE_LEAK")

    def test_english_code_is_blocked(self):
        ok, reason, _ = fw("Your door code is 5282, welcome!")
        self.assertFalse(ok); self.assertEqual(reason, "CODE_LEAK")

    def test_arabic_indic_digits_are_normalised_before_the_check(self):
        """٤٨٠٢ must be caught exactly like 4802 — the digits differ, the leak doesn't."""
        ok, reason, _ = fw("الكود ٤٨٠٢ تفضل")
        self.assertFalse(ok); self.assertEqual(reason, "CODE_LEAK")

    def test_wifi_password_context_is_a_code_context(self):
        ok, reason, _ = fw("كلمة سر الواي فاي هي Ouja1234")
        self.assertFalse(ok); self.assertEqual(reason, "CODE_LEAK")

    def test_a_price_is_not_a_code(self):
        ok, reason, _ = fw("سعر الإقامة 1,480 ر.س قبل الضريبة، والكود يوصلك قبل موعدك")
        self.assertTrue(ok, f"blocked as {reason}")

    def test_a_clock_time_is_not_a_code(self):
        ok, reason, _ = fw("الكود يوصلك قبل الساعة 15:00 بإذن الله")
        self.assertTrue(ok, f"blocked as {reason}")

    def test_a_year_is_not_a_code(self):
        ok, reason, _ = fw("نظام الأكواد اشتغل عندنا من 2026 وكل شي تمام")
        self.assertTrue(ok, f"blocked as {reason}")

    def test_digits_without_a_code_context_are_left_alone(self):
        ok, reason, _ = fw("الوحدة فيها 3 غرف ومساحتها 180 متر")
        self.assertTrue(ok, f"blocked as {reason}")


class TestFirewallReadiness(unittest.TestCase):
    """R2 — 21 readiness claims shipped under an 'absolute' prompt rule."""

    def test_claim_about_this_unit_is_blocked(self):
        ok, reason, _ = fw("وحدتك جاهزة الحين تفضل")
        self.assertFalse(ok); self.assertEqual(reason, "READINESS_CLAIM")

    def test_negative_claim_is_also_a_claim(self):
        ok, reason, _ = fw("الشقة تحت التنظيف حالياً")
        self.assertFalse(ok); self.assertEqual(reason, "READINESS_CLAIM")

    def test_english_claim_is_blocked(self):
        ok, reason, _ = fw("Your apartment is not ready yet, sorry.")
        self.assertFalse(ok); self.assertEqual(reason, "READINESS_CLAIM")

    def test_general_turnover_explanation_is_ALLOWED(self):
        """The carve-out that keeps the rule usable: no unit referent, no block."""
        ok, reason, _ = fw(
            "عادةً يكون فيه ضيف قبلك، فنحتاج وقت للتجهيز بين الحجوزات")
        self.assertTrue(ok, f"blocked as {reason}")

    def test_general_english_turnover_explanation_is_ALLOWED(self):
        ok, reason, _ = fw(
            "There's normally a guest before you, so we need turnover time.")
        self.assertTrue(ok, f"blocked as {reason}")


class TestFirewallPlaceholderAndLanguage(unittest.TestCase):
    """R3 and R4 — an unfilled variable, and answering in the wrong language."""

    def test_placeholder_is_blocked(self):
        ok, reason, _ = fw("تم اعتماد دخولك الساعة الوقت المطلوب")
        self.assertFalse(ok); self.assertEqual(reason, "PLACEHOLDER")

    def test_english_placeholder_is_blocked(self):
        ok, reason, _ = fw("Approved for your requested time, see you then.")
        self.assertFalse(ok); self.assertEqual(reason, "PLACEHOLDER")

    def test_arabic_reply_to_an_english_guest_is_blocked(self):
        item = {"guest_text": "Could you please send me which floor and which apartment"}
        ok, reason, _ = fw("حياك الله، الوحدة في الدور الرابع وأنا معك", item)
        self.assertFalse(ok); self.assertEqual(reason, "LANG_MISMATCH")

    def test_a_very_short_reply_is_exempt_from_the_language_rule(self):
        """Under 8 characters carries no information to mismatch."""
        item = {"guest_text": "Could you please send me the floor number"}
        ok, reason, _ = fw("تم 🤍", item)
        self.assertTrue(ok, f"blocked as {reason}")

    def test_matching_language_passes(self):
        item = {"guest_text": "Could you please send me the floor number"}
        ok, reason, _ = fw("You're on the 4th floor 🤍", item)
        self.assertTrue(ok, f"blocked as {reason}")


class TestFirewallSignatureAndUnit(unittest.TestCase):
    """R5 strips, R6 blocks."""

    def setUp(self):
        self._p = _pin_units(); self._p.start()
        self.addCleanup(self._p.stop)

    def test_model_written_signature_is_stripped_not_blocked(self):
        ok, reason, cleaned = fw("تم الحجز بنجاح\n\nفريق عوجا")
        self.assertTrue(ok, f"blocked as {reason}")
        self.assertNotIn("فريق عوجا", cleaned)
        self.assertIn("تم الحجز", cleaned)

    def test_another_units_name_is_blocked(self):
        item = {"unit": "Ouja | Qurtuba-B20", "guest_text": "وين شقتي"}
        ok, reason, _ = fw("شقتك هي Ouja | DAMAC Towers في الدور الثاني", item)
        self.assertFalse(ok); self.assertEqual(reason, "WRONG_UNIT")

    def test_another_units_name_is_allowed_as_an_explicit_swap(self):
        item = {"unit": "Ouja | Qurtuba-B20", "guest_text": "ابي ادخل بدري"}
        ok, reason, _ = fw(
            "وحدتك ما تسمح بالدخول المبكر، لكن عندنا وحدة بديلة "
            "(Ouja | DAMAC Towers) ليلتها فاضية", item)
        self.assertTrue(ok, f"blocked as {reason}")

    def test_the_guests_own_unit_name_is_fine(self):
        item = {"unit": "Ouja | Qurtuba-B20", "guest_text": "وين شقتي"}
        ok, reason, _ = fw("شقتك Ouja | Qurtuba-B20 في الدور الثاني", item)
        self.assertTrue(ok, f"blocked as {reason}")


class TestFirewallFailsClosed(unittest.TestCase):
    def test_empty_body_is_refused(self):
        ok, reason, _ = fw("   ")
        self.assertFalse(ok); self.assertEqual(reason, "EMPTY")

    def test_an_internal_error_blocks_the_send(self):
        """Any unexpected exception must fail CLOSED, never send-anyway."""
        with mock.patch.object(bot, "_fw_norm_digits", side_effect=RuntimeError("boom")):
            ok, reason, _ = fw("رسالة عادية تماماً")
        self.assertFalse(ok); self.assertEqual(reason, "FIREWALL_ERROR")

    def test_disabling_v3_bypasses_the_firewall(self):
        with mock.patch.object(bot, "MUSAED_V3", False):
            ok, reason, body = fw("كود الباب 4802")
        self.assertTrue(ok); self.assertEqual(body, "كود الباب 4802")

    def test_send_guest_message_returns_the_blocked_sentinel(self):
        """The guard sits BEFORE the dedup claim, so a block never burns the key."""
        before = len(bot._fw_blocked_queue)
        with mock.patch.object(bot, "api_post", side_effect=AssertionError("must not send")):
            out = bot.send_guest_message(999, "كود الباب 4802", "email",
                                         {"guest": "G", "unit": "Ouja | B14"})
        self.assertEqual(out, bot.SEND_FIREWALL_BLOCKED)
        self.assertEqual(len(bot._fw_blocked_queue), before + 1)
        self.assertEqual(bot._fw_blocked_queue[-1]["reason"], "CODE_LEAK")


class TestSignatureLanguage(unittest.TestCase):
    def test_english_reply_naming_an_arabic_unit_gets_an_english_signature(self):
        """F15: _has_arabic() saw one Arabic unit name and signed the whole English
        reply in Arabic. Signatures rotate, so assert the LANGUAGE, not a string."""
        body = "You're in apartment العارض A11 on the 4th floor"
        sig = bot.with_signature(body)[len(body):]
        self.assertEqual(bot._fw_reply_language(sig), "en", f"signature was: {sig!r}")

    def test_arabic_reply_still_gets_an_arabic_signature(self):
        body = "وحدتك في الدور الرابع وأنا معك لو تحتاج أي شي"
        sig = bot.with_signature(body)[len(body):]
        self.assertEqual(bot._fw_reply_language(sig), "ar", f"signature was: {sig!r}")

    def test_language_is_decided_by_majority_not_by_presence(self):
        self.assertEqual(bot._fw_reply_language("You're in العارض A11"), "en")
        self.assertEqual(bot._fw_reply_language("وحدتك في الدور الرابع"), "ar")
        self.assertEqual(bot._fw_reply_language("🤍🤍"), "?")


class TestRiskGate(unittest.TestCase):
    """Autonomy is gated on blast radius. 83.8% of replies used to auto-send."""

    def test_safe_intents_are_an_allow_list(self):
        self.assertTrue(bot._intent_is_auto_safe("ترحيب"))
        self.assertTrue(bot._intent_is_auto_safe("شكر"))
        self.assertTrue(bot._intent_is_auto_safe("greeting"))

    def test_never_intents_are_refused_however_they_are_phrased(self):
        for intent in ("كود الدخول", "جاهزية الشقة", "شكوى", "تسعير",
                       "early_checkin", "صيانة"):
            with self.subTest(intent=intent):
                self.assertFalse(bot._intent_is_auto_safe(intent))

    def test_an_unknown_intent_fails_CLOSED(self):
        """A deny-list would fail open on anything nobody thought of."""
        self.assertFalse(bot._intent_is_auto_safe("سؤال جديد ما شفناه قبل"))
        self.assertFalse(bot._intent_is_auto_safe(""))

    def test_risk_text_is_detected_regardless_of_the_intent_label(self):
        """The model mislabelling its own intent is the failure being defended against."""
        self.assertTrue(bot._is_risk_class("المكيف ما يشتغل", "ترحيب"))
        self.assertTrue(bot._is_risk_class("ابي استرجاع", "شكر"))
        self.assertTrue(bot._is_risk_class("لا ترد علي رد آلي", "ترحيب"))
        self.assertTrue(bot._is_risk_class("Is the unit ready?", "greeting"))

    def test_a_plain_thank_you_is_not_risk_class(self):
        self.assertFalse(bot._is_risk_class("شكرا جزيلا", "شكر"))

    def test_bot_detection_phrases_are_risk_class(self):
        for t in ("لا ترد علي رد آلي", "ماعليكم أمر إذا ممكن شخص يكلمني مو رد آلي"):
            with self.subTest(t=t):
                self.assertTrue(bot._is_risk_class(t))


class TestUnitTimes(unittest.TestCase):
    """One source of truth: guests were told 4 PM 138 times and 3 PM 69 times."""

    def setUp(self):
        bot._unit_times_cache.clear()

    def test_checkin_time_is_read_from_the_listing(self):
        with mock.patch.object(bot, "api_get",
                               return_value={"result": {"checkInTimeStart": "16:00"}}):
            h, m, src = bot.unit_checkin_time(101)
        self.assertEqual((h, m), (16, 0))
        self.assertEqual(src, "checkInTimeStart")

    def test_checkout_time_is_read_from_the_listing(self):
        with mock.patch.object(bot, "api_get",
                               return_value={"result": {"checkOutTime": "11:00"}}):
            h, m, src = bot.unit_checkout_time(102)
        self.assertEqual((h, m), (11, 0))

    def test_a_missing_field_falls_back_AND_says_so(self):
        with mock.patch.object(bot, "api_get", return_value={"result": {}}), \
                mock.patch.object(bot, "log_event") as logged:
            h, m, src = bot.unit_checkin_time(103)
        self.assertEqual((h, m), (15, 0))
        self.assertEqual(src, "fallback")
        self.assertTrue(logged.called, "a fallback must be findable in the ops log")

    def test_the_result_is_cached(self):
        with mock.patch.object(bot, "api_get",
                               return_value={"result": {"checkInTime": "14:00"}}) as api:
            bot.unit_checkin_time(104)
            bot.unit_checkin_time(104)
        self.assertEqual(api.call_count, 1)

    def test_the_hardcoded_constant_is_gone_from_the_source(self):
        with open(bot.__file__.replace(".pyc", ".py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("_OFFICIAL_CHECKIN_MINUTES", src)

    def test_no_hardcoded_official_time_strings_remain(self):
        with open(bot.__file__.replace(".pyc", ".py"), encoding="utf-8") as f:
            src = f.read()
        for literal in ('"3:00 PM"', "الساعة 3 مساءً", "11:00 صباحاً"):
            with self.subTest(literal=literal):
                self.assertNotIn(literal, src)


class TestEarlyCheckin(unittest.TestCase):
    """F7: 'Early check-in at 3:00 AM appears possible' — the worst reply we sent."""

    def test_arabic_dawn_arrival_is_a_late_night_arrival(self):
        got = bot._early_checkin_request("هل اقدر ادخلهم ٣ الفجر؟")
        self.assertEqual(got["kind"], "late_night_arrival")
        self.assertEqual(got["requested_minutes"], 180)

    def test_english_am_arrival_is_a_late_night_arrival(self):
        got = bot._early_checkin_request("My flight lands at 2 am")
        self.assertEqual(got["kind"], "late_night_arrival")

    def test_a_guest_quoting_our_own_3pm_policy_is_not_a_3am_request(self):
        """v2 parsed HER OWN QUOTE of our policy as a 3 AM early-entry request."""
        self.assertIsNone(bot._early_checkin_request("You told me check in is at 3"))

    def test_a_real_noon_request_is_still_an_early_checkin(self):
        got = bot._early_checkin_request("أبي أدخل الساعة ١٢ الظهر")
        self.assertEqual(got["kind"], "early_checkin")
        self.assertEqual(got["requested_minutes"], 720)

    def test_explicit_intent_without_a_time_yields_no_time(self):
        got = bot._early_checkin_request("ابي ادخل بدري")
        self.assertIsNotNone(got)
        self.assertIsNone(got["requested_minutes"])

    def test_the_official_time_is_injectable_per_unit(self):
        """A 14:00 unit must treat 14:30 as NOT early."""
        self.assertIsNone(
            bot._early_checkin_request("أقدر أدخل الساعة 2:30 مساء؟", 14 * 60))

    def test_a_missing_time_never_becomes_a_placeholder(self):
        self.assertIsNone(bot._early_pending_reply(
            {"guest_text": "ابي ادخل بدري", "requested_label": ""}))

    def test_the_ask_for_time_reply_matches_the_guest_language(self):
        self.assertIn("الساعة", bot._early_ask_for_time({"guest_text": "ابي ادخل بدري"}))
        self.assertIn("exact hour",
                      bot._early_ask_for_time({"guest_text": "Can I check in early?"}))

    def test_an_alternative_unit_is_framed_as_an_explicit_swap(self):
        rec = {"guest_text": "ابي ادخل بدري", "requested_label": "12:00 PM",
               "original_unit": "Ouja | Qurtuba-B20", "proposed_unit": "Ouja | HUE 202",
               "offhours": False}
        out = bot._early_pending_reply(rec)
        self.assertIn("وحدة بديلة", out)
        self.assertIn("Ouja | HUE 202", out)

    def test_no_unit_is_named_when_there_is_no_swap(self):
        rec = {"guest_text": "ابي ادخل بدري", "requested_label": "12:00 PM",
               "original_unit": "Ouja | Qurtuba-B20", "proposed_unit": "", "offhours": False}
        out = bot._early_pending_reply(rec)
        self.assertNotIn("Ouja |", out)


class TestDatesFromText(unittest.TestCase):
    """753 booking-intent threads produced 13 quotes because dates came from a
    reservation an inquiry does not have."""

    T = date(2026, 8, 23)          # a Sunday

    def _d(self, text):
        return bot._dates_from_text(text, today=self.T)

    def test_today_until_saturday(self):
        self.assertEqual(self._d("من اليوم إلى السبت")[:2], ("2026-08-23", "2026-08-29"))

    def test_bare_arabic_indic_range(self):
        self.assertEqual(self._d("من ٥ إلى ٧")[:2], ("2026-09-05", "2026-09-07"))

    def test_the_weekend_is_thursday_to_saturday(self):
        """Saudi weekend is Thu–Fri, so «نهاية الأسبوع» is Thu -> Sat."""
        s, e, _ = self._d("نهاية الأسبوع")
        self.assertEqual((s, e), ("2026-08-27", "2026-08-29"))

    def test_tomorrow(self):
        self.assertEqual(self._d("بكرة")[:2], ("2026-08-24", "2026-08-25"))

    def test_explicit_month_range(self):
        self.assertEqual(self._d("20-22 Sep")[:2], ("2026-09-20", "2026-09-22"))

    def test_n_nights_from_a_weekday(self):
        self.assertEqual(self._d("3 nights from Friday")[:2], ("2026-08-28", "2026-08-31"))

    def test_a_start_date_is_never_in_the_past(self):
        s, _e, _c = self._d("من 1 إلى 3")
        self.assertGreaterEqual(s, self.T.isoformat())

    def test_an_unparseable_phrase_yields_nothing_and_low_confidence(self):
        """We ask instead of guessing. A guessed date is a wrong price."""
        self.assertEqual(self._d("كم السعر؟"), (None, None, "low"))

    def test_a_real_production_booking_message_parses(self):
        s, e, _ = self._d("السلام عليكم مساء الخير هل الشقه متاحه للدخول الان "
                          "احتاج احجز من اليوم الى السبت الله يسعدك شكرا")
        self.assertEqual((s, e), ("2026-08-23", "2026-08-29"))

    def test_booking_intent_is_detected(self):
        self.assertTrue(bot._is_booking_intent("هل الشقه متاحه؟"))
        self.assertTrue(bot._is_booking_intent("I want to book"))
        self.assertFalse(bot._is_booking_intent("شكرا جزيلا"))


class TestPromises(unittest.TestCase):
    """518 promises, 95 never kept — because auto-sends never reached the ledger."""

    def setUp(self):
        bot._promise_recent = {}

    def test_a_fresh_conversation_has_no_open_promise(self):
        has, _m, _w = bot._promise_open_recently("conv-new")
        self.assertFalse(has)

    def test_marking_a_promise_opens_the_cooldown(self):
        with mock.patch.object(bot, "_save_json", return_value=True):
            bot._promise_mark("conv-1")
        has, mins, when = bot._promise_open_recently("conv-1")
        self.assertTrue(has)
        self.assertLess(mins, 2)
        self.assertTrue(when)

    def test_the_open_promise_is_injected_into_the_prompt(self):
        with mock.patch.object(bot, "_save_json", return_value=True):
            bot._promise_mark("conv-2")
        line = bot._promise_state_line("conv-2")
        self.assertIn("وعد مفتوح", line)
        self.assertIn("ممنوع تكرر وعد التواصل", line)

    def test_no_open_promise_injects_nothing(self):
        self.assertEqual(bot._promise_state_line("conv-quiet"), "")

    def test_an_expired_cooldown_reopens_the_conversation(self):
        import time as _t
        bot._promise_recent = {"conv-3": _t.time() - (bot.MUSAED_PROMISE_COOLDOWN_H + 1) * 3600}
        has, _m, _w = bot._promise_open_recently("conv-3")
        self.assertFalse(has)

    def test_an_auto_promise_is_tagged_and_rate_limited(self):
        """Tracked, not ignored — and never twice inside the cooldown."""
        rows = []
        fake_pk = mock.MagicMock()
        fake_pk.db.upsert.side_effect = lambda rec: (rows.append(rec), len(rows))[1]
        fake_pk.engine.due_from_hint.return_value = "2026-08-23T15:00:00"
        item = {"conversation_id": "conv-9", "guest": "G", "unit": "Ouja | B14"}
        found = [{"promise_text_ar": "بنتواصل معك", "promise_text_en": "",
                  "category": "callback", "due_hint": ""}]
        with mock.patch.object(bot, "_pk_enabled", return_value=True), \
                mock.patch.object(bot, "_pk", fake_pk), \
                mock.patch.object(bot, "_pk_extract_promises", return_value=found), \
                mock.patch.object(bot, "_save_json", return_value=True), \
                mock.patch.object(bot, "log_event"):
            first = bot._pk_record_send(item, "بنتواصل معك", bot.MUSAED_AUTO_PROMISER, "")
            second = bot._pk_record_send(item, "بنتواصل معك", bot.MUSAED_AUTO_PROMISER, "")
        self.assertEqual(len(first), 1, "the first auto promise must be recorded")
        self.assertEqual(second, [], "a second promise inside the cooldown is suppressed")
        self.assertEqual(rows[0]["source"], "musaed_auto")
        self.assertEqual(rows[0]["promised_by"], bot.MUSAED_AUTO_PROMISER)

    def test_a_human_promise_keeps_the_original_source(self):
        rows = []
        fake_pk = mock.MagicMock()
        fake_pk.db.upsert.side_effect = lambda rec: (rows.append(rec), 1)[1]
        fake_pk.engine.due_from_hint.return_value = "2026-08-23T15:00:00"
        found = [{"promise_text_ar": "بنرجع لك", "promise_text_en": "",
                  "category": "callback", "due_hint": "today"}]
        with mock.patch.object(bot, "_pk_enabled", return_value=True), \
                mock.patch.object(bot, "_pk", fake_pk), \
                mock.patch.object(bot, "_pk_extract_promises", return_value=found), \
                mock.patch.object(bot, "log_event"):
            bot._pk_record_send({"conversation_id": "c-h", "guest": "G", "unit": "U"},
                                "بنرجع لك", "فيصل", "42")
        self.assertEqual(rows[0]["source"], "assistant")


class TestExtras(unittest.TestCase):
    def setUp(self):
        bot._extras_offered = {}

    def test_a_trigger_word_surfaces_exactly_one_extra(self):
        hits = bot.relevant_extras("ابي سائق للمطار", "x1")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["key"], "chauffeur")

    def test_nothing_is_offered_to_an_upset_guest(self):
        self.assertEqual(bot.relevant_extras("ابي سائق للمطار", "x2", sentiment="upset"), [])

    def test_nothing_is_offered_on_a_complaint(self):
        self.assertEqual(bot.relevant_extras("الشقة وسخة وابي تنظيف", "x3"), [])

    def test_an_offer_is_not_repeated_inside_24h(self):
        with mock.patch.object(bot, "_save_json", return_value=True):
            first = bot._extras_block("ابي سائق للمطار", "x4")
            second = bot._extras_block("ابي سائق للمطار", "x4")
        self.assertTrue(first.strip())
        self.assertEqual(second, "")

    def test_the_offer_always_carries_the_fee_note_and_no_invented_number(self):
        with mock.patch.object(bot, "_save_json", return_value=True):
            block = bot._extras_block("ابي سائق للمطار", "x5")
        self.assertIn("الفريق يأكد", block)
        for ex in bot.OUJA_EXTRAS:
            self.assertNotIn("price_sar", ex, "public prices are not set — never invent one")


class TestPrompt(unittest.TestCase):
    ORIGINAL_LEN = 19373          # the length recorded in the v3 build order

    def test_the_identity_matches_the_signature(self):
        self.assertIn("مساعد", bot.ASSISTANT_RULES)
        self.assertNotIn('You are "فيصل"', bot.ASSISTANT_RULES)

    def test_the_prompt_stays_below_its_original_length(self):
        """v3.1 lowered the floor from -3,000 to -1,000 so ~2,000 characters could
        go back into multi-part questions, stay-state and anti-loop. The prompt
        must still be meaningfully shorter than the 19,373 it started at."""
        self.assertLessEqual(
            len(bot.ASSISTANT_RULES), self.ORIGINAL_LEN - 1000,
            f"ASSISTANT_RULES is {len(bot.ASSISTANT_RULES)} chars")

    def test_the_reclaimed_budget_went_to_the_three_weak_sections(self):
        for section in ("ANSWER EVERY PART", "READ THE STAY-STATE FIRST",
                        "NEVER LOOP — expanded"):
            with self.subTest(section=section):
                self.assertIn(section, bot.ASSISTANT_RULES)

    def test_no_dialect_word_lists_came_back(self):
        """The 12-token ban line is kept; the 2,871-character tables are not."""
        for gone in ("إزيك", "بتاعك", "منيح", "كرمالك", "بزاف", "كيفاش", "هواية"):
            with self.subTest(gone=gone):
                self.assertNotIn(gone, bot.ASSISTANT_RULES)

    def test_the_language_lock_is_present(self):
        self.assertIn("LANGUAGE LOCK", bot.ASSISTANT_RULES)
        self.assertIn("MOST RECENT", bot.ASSISTANT_RULES)

    def test_the_bare_greeting_rule_is_present(self):
        self.assertIn("ممنوع ترد بتحية", bot.ASSISTANT_RULES)

    def test_the_dialect_lock_is_short(self):
        self.assertLessEqual(len(bot._DIALECT_LOCK), 300)

    def test_choosing_reply_is_stated_to_be_free(self):
        self.assertIn("never a failure", bot.ASSISTANT_RULES)


class TestDetectorParity(unittest.TestCase):
    """bot's firewall and eval_musaed's gates must agree, or a rule can pass the
    eval and be blocked in production (or the reverse)."""

    FIXTURES = [
        "كود الباب 4802 تفضل",
        "Your door code is 5282",
        "الكود ٤٨٠٢",
        "سعر الإقامة 1,480 ر.س",
        "الكود يوصلك قبل الساعة 15:00",
        "نظام الأكواد من 2026",
        "وحدتك جاهزة الحين",
        "الشقة تحت التنظيف",
        "Your apartment is not ready yet",
        "عادةً يكون فيه ضيف قبلك فنحتاج وقت للتجهيز بين الحجوزات",
        "There's normally a guest before you, so we need turnover time.",
        "تم اعتماد دخولك الساعة الوقت المطلوب",
        "Approved for your requested time",
        "حياك الله ونورت المكان",
        "You're on the 4th floor",
        "الوحدة فيها 3 غرف",
        "شكرا جزيلا على تعاملك الراقي",
        "تسجيل الخروج الساعة 12:00",
        "أبشر، الفريق بيرسل لك كود الدخول قبل موعدك",
        "The team will send your entry details before arrival",
    ]

    def test_code_leak_detectors_agree(self):
        for text in self.FIXTURES:
            with self.subTest(text=text):
                bot_blocked = (fw(text)[1] == "CODE_LEAK")
                ev_blocked = ev.door_code_leak(text)[0]
                self.assertEqual(bot_blocked, ev_blocked, text)

    def test_readiness_detectors_agree(self):
        for text in self.FIXTURES:
            with self.subTest(text=text):
                self.assertEqual(fw(text)[1] == "READINESS_CLAIM",
                                 ev.readiness_claim(text), text)

    def test_placeholder_detectors_agree(self):
        for text in self.FIXTURES:
            with self.subTest(text=text):
                self.assertEqual(fw(text)[1] == "PLACEHOLDER",
                                 bool(ev.placeholder_leak(text)), text)

    def test_language_detectors_agree(self):
        self.assertEqual(bot._fw_reply_language("You're in العارض A11"),
                         ev.reply_language("You're in العارض A11"))
        self.assertEqual(bot._fw_reply_language("وحدتك في الدور الرابع"),
                         ev.reply_language("وحدتك في الدور الرابع"))


if __name__ == "__main__":
    unittest.main()
