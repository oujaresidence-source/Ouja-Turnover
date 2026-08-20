"""guard.commit — a promise with nothing behind it is a lie with good manners.

17 of 62 of «مساعد»'s messages promised a follow-up with no ticket, no owner, no SLA.
"""

import unittest

from guard.commit import detect_commitment, is_backed


class DetectsRealPromisesTest(unittest.TestCase):

    FLAGGED = [
        ("T007 i13", "فريقنا المختص اتنبّه لموضوعك الحين وبيتواصل معك خلال دقائق", "callback"),
        ("raise it", "راح أرفع طلبك للفريق وبنشوف لك حل", "action"),
        ("follow",   "بتابع الموضوع معك وأرد عليك", "followup"),
        ("we will",  "بنتواصل معك قريب إن شاء الله", "callback"),
        ("escalate", "بصعّد الموضوع للمشرف", "action"),
        ("en pass",  "I'll pass this along to the team", "action"),
        ("en reach", "Someone will contact you shortly", "callback"),
        ("en check", "Let me check and get back to you", "followup"),
        ("en follow","The team will follow up with you", "followup"),
    ]

    def test_each_flagged_span_is_detected_with_the_right_kind(self):
        for name, text, kind in self.FLAGGED:
            with self.subTest(name):
                c = detect_commitment(text)
                self.assertIsNotNone(c, f"missed a promise: {text}")
                self.assertEqual(c["kind"], kind)

    def test_the_span_carries_enough_context_for_a_human(self):
        c = detect_commitment("شكراً لتواصلك. بيتواصل معك الفريق خلال دقائق. حياك الله")
        self.assertIn("بيتواصل معك", c["span"])


class DoesNotFlagOrdinaryWarmthTest(unittest.TestCase):
    """A guard that reads politeness as a debt escalates every friendly message, and then
    the team switches it off."""

    SAFE = [
        "حياك الله 🤍",
        "يعطيك العافية",
        "أبشر، الخروج الساعة ١٢",
        "ولا يهمك، الواي فاي اسمه Ouja والباسورد بالكرت",
        "هلا والله، نورتنا",
        "تسلم، وإذا احتجت شي أنا موجود",
        "Thanks for staying with us!",
        "Checkout is at 12:00, and the code arrives automatically.",
    ]

    def test_none_of_these_are_commitments(self):
        for text in self.SAFE:
            with self.subTest(text[:30]):
                self.assertIsNone(detect_commitment(text), f"false positive on: {text}")

    def test_empty_input(self):
        self.assertIsNone(detect_commitment(""))
        self.assertIsNone(detect_commitment(None))


class BackingTest(unittest.TestCase):

    def test_a_promise_needs_a_real_ticket(self):
        c = detect_commitment("بيتواصل معك الفريق")
        self.assertFalse(is_backed(c, None))
        self.assertFalse(is_backed(c, ""))
        self.assertFalse(is_backed(c, "   "))
        self.assertTrue(is_backed(c, "OJ-123"))

    def test_a_message_with_no_promise_needs_nothing(self):
        self.assertTrue(is_backed(None, None))


if __name__ == "__main__":
    unittest.main()
