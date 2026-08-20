"""guard.outbound — the content guard on the real send path.

Deterministic: no network, no Anthropic key, no Hostaway. Every case below is a real
message from the 155-thread export, or a real message that must NOT be blocked.

The must-NOT-block list is as load-bearing as the must-block list. A guard that blocks
«الخروج الساعة 12:00» because it contains digits would push every checkout question to a
human, the team would switch it off within a day, and then nothing is guarded at all.
"""

import unittest

from guard.outbound import check_outbound, door_code_leak


class AccessCodeTest(unittest.TestCase):
    """⛔ 2.1 — codes reach guests through the automated system only, never from us."""

    def test_blocks_the_ten_digit_leak_that_started_all_this(self):
        # T085 i18. The detector inherited from eval_musaed capped digit runs at 4-6 and
        # let this through: ten digits has no 4-6 window bounded by non-digits.
        v = check_outbound("كود الدخول للشقة: 7256172263#")
        self.assertTrue(v.blocked)
        self.assertEqual(v.code, "ACCESS_CODE")

    def test_blocks_the_gate_code(self):
        v = check_outbound("رمز البوابة الخارجية: #2580#")
        self.assertTrue(v.blocked)
        self.assertEqual(v.code, "ACCESS_CODE")

    def test_blocks_a_plain_four_digit_code(self):
        self.assertEqual(check_outbound("كود الباب هو 4521").code, "ACCESS_CODE")

    def test_blocks_the_second_ai_labelled_code(self):
        self.assertEqual(check_outbound("الكود 9999#111111").code, "ACCESS_CODE")

    def test_a_code_needs_code_context(self):
        # Digits alone are not a code. Without a code word there is nothing to leak.
        self.assertFalse(check_outbound("وصلنا 4521 حجز هذا الشهر").blocked)


class MustNotBlockTest(unittest.TestCase):
    """False positives are how a guard gets switched off. These all stay sendable."""

    CASES = [
        ("checkout time",   "الخروج الساعة 12:00", "كود"),
        ("a price",         "السعر 1450 ريال", "كود"),
        ("a year",          "نشوفك سنة 2026", "كود"),
        ("a unit number",   "الوحدة رقم 202B بالدور الثاني", ""),
        ("a building slot", "B14 بالدور الأول", ""),
        ("a mobile",        "كلّمنا على 0551234567 عشان الكود", ""),
        ("+966 mobile",     "واتساب +966551234567 والكود يوصلك", ""),
        ("00966 mobile",    "اتصل 00966551234567 عن الكود", ""),
        ("bare 5xxxxxxxx",  "جوال 551234567 والكود", ""),
        ("a landline",      "اتصل 0112345678 عن كود الدخول", ""),
        ("the unified no.", "الموحد 9200012345 والكود بيوصل", ""),
        ("a room count",    "الشقة فيها 3 غرف", ""),
    ]

    def test_none_of_these_are_blocked(self):
        for name, body, ctx in self.CASES:
            with self.subTest(name):
                v = check_outbound(body, guest_text=ctx)
                self.assertFalse(v.blocked, f"{name} was blocked as {v.code}: {v.matched}")

    def test_empty_body_is_never_blocked(self):
        self.assertFalse(check_outbound("").blocked)
        self.assertFalse(check_outbound("   ").blocked)
        self.assertFalse(check_outbound(None).blocked)


class UnrenderedTest(unittest.TestCase):
    """A template that shipped with its variable empty. 14 of 26 door-code sends."""

    def test_blocks_the_empty_door_code_template(self):
        v = check_outbound("Your door code:  then #")
        self.assertTrue(v.blocked)
        self.assertEqual(v.code, "UNRENDERED")

    def test_blocks_the_midnight_to_midnight_offhours_template(self):
        v = check_outbound("We are available every day from 12:00 AM to 12:00 AM")
        self.assertEqual(v.code, "UNRENDERED")

    def test_blocks_an_unrendered_mustache(self):
        self.assertEqual(check_outbound("حياك الله {{guest_name}} 🤍").code, "UNRENDERED")

    def test_blocks_a_bare_colon_hash_with_no_value(self):
        self.assertEqual(check_outbound("الكود: #").code, "UNRENDERED")

    def test_a_colon_hash_WITH_digits_is_the_code_rule_not_this_one(self):
        # Both rules fire; ACCESS_CODE wins because that is the one that opens a door.
        self.assertEqual(check_outbound("الكود: 4821#").code, "ACCESS_CODE")


class MoneyTest(unittest.TestCase):
    """⛔ 2.2 — T011: «ما فيه خصم إضافي» at i8, a human granting it at i18."""

    def test_blocks_money_talk_without_a_ticket(self):
        v = check_outbound("ما فيه خصم إضافي")
        self.assertTrue(v.blocked)
        self.assertEqual(v.code, "MONEY")

    def test_allows_the_same_words_once_a_ticket_backs_them(self):
        self.assertFalse(check_outbound("ما فيه خصم إضافي", ticket_id="OJ-123").blocked)

    def test_denying_money_is_blocked_too_not_just_granting_it(self):
        # The assistant cannot see what the team offered five minutes ago in a channel
        # it has no access to, so "no" is as unsafe as "yes".
        self.assertEqual(check_outbound("للأسف ما نقدر نسوي استرداد").code, "MONEY")

    def test_english_money_words(self):
        self.assertEqual(check_outbound("I can offer you a discount").code, "MONEY")


class ResolutionClaimTest(unittest.TestCase):
    """⛔ 2.3 — T030 i26 «the water is fully restored», guest at i32: «no water»."""

    def test_blocks_a_resolution_claim_with_no_resolved_ticket(self):
        v = check_outbound("the issue is resolved and the water is fully restored")
        self.assertTrue(v.blocked)
        self.assertEqual(v.code, "RESOLUTION_CLAIM")

    def test_allows_it_when_a_resolved_ticket_proves_it(self):
        v = check_outbound("the water is fully restored",
                           ticket_id="OJ-9", resolved_ticket=True)
        self.assertFalse(v.blocked)

    def test_blocks_the_arabic_forms(self):
        self.assertEqual(check_outbound("تم الحل والمشكلة انتهت").code, "RESOLUTION_CLAIM")
        self.assertEqual(check_outbound("رجعت المياه الحين").code, "RESOLUTION_CLAIM")


class AiRevealTest(unittest.TestCase):
    """⛔ 2.5 — promoted from a non-blocking eval warning to a block."""

    def test_blocks_an_ai_reveal(self):
        self.assertEqual(check_outbound("أنا مساعد آلي وبساعدك").code, "AI_REVEAL")
        self.assertEqual(check_outbound("As an AI, I cannot do that").code, "AI_REVEAL")


class SharedWithEvalTest(unittest.TestCase):
    """One implementation, two consumers — the acceptance criterion, asserted."""

    def test_eval_imports_the_guard_detector_rather_than_redefining_it(self):
        import eval_musaed
        self.assertIs(eval_musaed.door_code_leak, door_code_leak)


if __name__ == "__main__":
    unittest.main()
