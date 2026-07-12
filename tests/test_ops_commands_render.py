# -*- coding: utf-8 -*-
"""Pure renderers for /update and /guests — deterministic text, no I/O."""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-opscmd"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ.setdefault("STATE_DIR", _STATE)

import bot  # noqa: E402


class TestRenderUpdate(unittest.TestCase):
    def test_empty(self):
        out = bot.render_update([], "الاثنين")
        self.assertIn("ما فيه تسجيلات دخول اليوم", out)

    def test_rows_and_agreement_states(self):
        rows = [
            {"unit": "Ouja | A", "guest": "سعد", "time_label": "15:00",
             "cleaned": True, "code_sent": False, "agreement": "signed"},
            {"unit": "Ouja | B", "guest": "نورة", "time_label": "18:00",
             "cleaned": False, "code_sent": True, "agreement": "not_signed"},
            {"unit": "Ouja | C", "guest": "John", "time_label": "",
             "cleaned": True, "code_sent": True, "agreement": "not_required"},
        ]
        out = bot.render_update(rows, "")
        self.assertIn("Ouja | A", out)
        self.assertIn("سعد", out)
        self.assertIn("موقّع", out)          # signed
        self.assertIn("غير موقّع", out)      # not_signed
        self.assertIn("لا يحتاج", out)       # not_required
        self.assertIn("3", out)              # count in header

    def test_sorted_by_time(self):
        rows = [
            {"unit": "B", "guest": "b", "time_label": "20:00",
             "cleaned": True, "code_sent": True, "agreement": "signed"},
            {"unit": "A", "guest": "a", "time_label": "09:00",
             "cleaned": True, "code_sent": True, "agreement": "signed"},
        ]
        out = bot.render_update(rows, "")
        self.assertLess(out.index("09:00"), out.index("20:00"))


class TestRenderGuests(unittest.TestCase):
    def test_empty(self):
        self.assertIn("ما فيه ضيوف", bot.render_guests([], ""))

    def test_sad_card_has_all_fields(self):
        rows = [{"guest": "عبدالله", "unit": "Ouja | حطين", "mood": "sad",
                 "severity": "angry", "issue": "تأخر التسليم ساعتين",
                 "quote": "صار لي ساعتين أنتظر", "resolved": False,
                 "staff": "نورة", "phone": "0501234567"}]
        out = bot.render_guests(rows, "")
        self.assertIn("غاضب جداً", out)          # severity label
        self.assertIn("🔴", out)                  # severity emoji
        self.assertIn("تأخر التسليم", out)        # what happened
        self.assertIn("«صار لي ساعتين أنتظر»", out)  # verbatim quote in guillemets
        self.assertIn("نورة", out)                # team member who replied
        self.assertIn("لسه مفتوحة", out)          # open status
        self.assertIn("wa.me/966501234567", out)  # KSA-normalized contact link

    def test_sad_resolved_and_missing_fields(self):
        rows = [{"guest": "x", "unit": "y", "mood": "sad", "severity": "upset",
                 "issue": "i", "quote": "", "resolved": True, "staff": "", "phone": ""}]
        out = bot.render_guests(rows, "")
        self.assertIn("تم الحل", out)
        self.assertIn("غير معروف", out)   # unknown team member
        self.assertNotIn("wa.me", out)     # no phone → no contact line
        self.assertNotIn("«", out)          # no quote → no quote line

    def test_happy_and_normal_names_only(self):
        rows = [
            {"guest": "سعد", "unit": "u", "mood": "happy"},
            {"guest": "لمى", "unit": "u", "mood": "normal"},
        ]
        out = bot.render_guests(rows, "")
        self.assertIn("المبسوطين (1): سعد", out)
        self.assertIn("العاديين (1): لمى", out)
        self.assertNotIn("وش صار", out)          # no detail for happy/normal
        self.assertNotIn("درجة الانزعاج", out)

    def test_header_total_and_counts(self):
        rows = [
            {"guest": "a", "unit": "u", "mood": "happy"},
            {"guest": "b", "unit": "u", "mood": "normal"},
            {"guest": "c", "unit": "u", "mood": "sad", "severity": "upset",
             "issue": "i", "quote": "", "resolved": False, "staff": "ن", "phone": ""},
        ]
        out = bot.render_guests(rows, "")
        self.assertIn("عندك اليوم 3 ضيف", out)
        self.assertIn("مبسوطين: 1", out)
        self.assertIn("عاديين: 1", out)
        self.assertIn("يحتاجون انتباه: 1", out)

    def test_angriest_first(self):
        rows = [
            {"guest": "calm", "unit": "u", "mood": "sad", "severity": "annoyed",
             "issue": "i", "quote": "", "resolved": False, "staff": "", "phone": ""},
            {"guest": "furious", "unit": "u", "mood": "sad", "severity": "angry",
             "issue": "i", "quote": "", "resolved": False, "staff": "", "phone": ""},
        ]
        out = bot.render_guests(rows, "")
        self.assertLess(out.index("furious"), out.index("calm"))


if __name__ == "__main__":
    unittest.main()
