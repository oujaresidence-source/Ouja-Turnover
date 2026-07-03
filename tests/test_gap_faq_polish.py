# -*- coding: utf-8 -*-
"""Smarter gap loop — inquiry filtering, in-house guide grounding, and the
AI-polished bilingual FAQ that replaces the guest's raw wording.

Run: python3 -m unittest tests.test_gap_faq_polish
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-gapfaq")
os.makedirs("/tmp/ouja-test-state-gapfaq", exist_ok=True)

from brain import db as bdb        # noqa: E402
from guide import db as gdb        # noqa: E402
import bot  # noqa: E402


class InquiryFilterTest(unittest.TestCase):
    def test_pricing_and_booking_are_never_gaps(self):
        for q in ("كم سعر الليلة؟", "بكم الشقة بالويكند", "فيه خصم للأسبوع؟",
                  "هل الشقة متاحة بكرة", "أبغى أمدد الحجز", "How much is it per night?",
                  "is it available next week", "can I book directly", "طريقة الدفع؟"):
            self.assertTrue(bot._wm_gap_is_inquiry(q, ""), q)

    def test_real_guide_questions_pass(self):
        for q in ("وين الموقف؟", "كيف أشغل المكيف", "وش باسورد الواي فاي",
                  "where do I throw the trash", "متى وقت تسجيل الخروج"):
            self.assertFalse(bot._wm_gap_is_inquiry(q, ""), q)


class FaqPolishTest(unittest.TestCase):
    def setUp(self):
        self._cj = bot.claude_json

    def tearDown(self):
        bot.claude_json = self._cj

    def test_polish_returns_clean_bilingual_faq(self):
        bot.claude_json = lambda s, u, max_tokens=900, model=None: {
            "title_ar": "أين يقع موقف السيارة؟", "title_en": "Where is the parking spot?",
            "body_ar": "الموقف المخصص رقم ١٢ في القبو.", "body_en": "Your spot is #12 in the basement."}
        out = bot._wm_gap_polish({"apartment": "Ouja | 101A",
                                  "guest_question": "wen alparking؟؟",
                                  "our_answer": "الموقف رقم 12 بالقبو تحت"})
        self.assertEqual(out["title_ar"], "أين يقع موقف السيارة؟")
        self.assertEqual(out["body_en"], "Your spot is #12 in the basement.")

    def test_polish_fails_safe(self):
        bot.claude_json = lambda s, u, max_tokens=900, model=None: None
        self.assertIsNone(bot._wm_gap_polish({"guest_question": "q", "our_answer": "a"}))
        bot.claude_json = lambda s, u, max_tokens=900, model=None: {"title_ar": "بس عنوان"}
        self.assertIsNone(bot._wm_gap_polish({}), "no body → unusable → None")
        bot.claude_json = lambda s, u, max_tokens=900, model=None: {"junk": 1}
        self.assertIsNone(bot._wm_gap_polish({}))

    def test_polish_truncates(self):
        bot.claude_json = lambda s, u, max_tokens=900, model=None: {
            "title_ar": "ع" * 500, "body_ar": "ب" * 500, "title_en": "", "body_en": ""}
        out = bot._wm_gap_polish({})
        self.assertLessEqual(len(out["title_ar"]), 300)


class GuideGroundingTest(unittest.TestCase):
    """The scan must read the IN-HOUSE guide (incl. published FAQ entries) as
    the 'already visible to the guest' text — with no HTTP when linked."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="gapfaq_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        gdb.reset_init_cache()
        gdb.upsert_unit("g1", listing_name="Ouja | G1", listing_id=9101,
                        wifi_name="Ouja_G1", wifi_pass="pass123",
                        notes="الموقف رقم ١٢ في القبو")
        gdb.add_entry("g1", "faq", "أين المصعد؟", "", "المصعد يمين المدخل", "",
                      None, 0, "published", "gap", "t")

    def setUp(self):
        self._flag = bot.GUIDE_ENABLED
        self._get = bot.requests.get
        bot.GUIDE_ENABLED = True
        bot._wm_guide_cache.clear()

        def _no_http(*a, **k):
            raise AssertionError("linked unit must not be scraped over HTTP")
        bot.requests.get = _no_http

    def tearDown(self):
        bot.GUIDE_ENABLED = self._flag
        bot.requests.get = self._get
        bot._wm_guide_cache.clear()

    def test_linked_unit_reads_db_including_faq(self):
        text = bot._wm_guide_text(9101)
        self.assertIn("pass123", text)
        self.assertIn("الموقف رقم ١٢", text)
        self.assertIn("المصعد يمين المدخل", text, "gap-added FAQs must count as 'already in guide'")

    def test_new_faq_visible_after_cache_expiry(self):
        bot._wm_guide_text(9101)
        gdb.add_entry("g1", "faq", "وين الغسالة؟", "", "الغسالة في المطبخ", "",
                      None, 0, "published", "gap", "t")
        bot._wm_guide_cache.clear()      # 15-min TTL stands in for time passing
        self.assertIn("الغسالة في المطبخ", bot._wm_guide_text(9101))


if __name__ == "__main__":
    unittest.main()
