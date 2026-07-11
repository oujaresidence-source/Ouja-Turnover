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

    def test_sad_shows_issue_and_open_status(self):
        rows = [{"guest": "سعد", "unit": "Ouja | A", "mood": "sad",
                 "issue": "المكيف ما يبرد", "resolved": False}]
        out = bot.render_guests(rows, "")
        self.assertIn("☹️", out)
        self.assertIn("المكيف ما يبرد", out)
        self.assertIn("لسه مفتوحة", out)

    def test_sad_resolved_status(self):
        rows = [{"guest": "x", "unit": "y", "mood": "sad", "issue": "z", "resolved": True}]
        self.assertIn("تم الحل", bot.render_guests(rows, ""))

    def test_happy_hides_issue_line(self):
        rows = [{"guest": "نورة", "unit": "Ouja | B", "mood": "happy",
                 "issue": "", "resolved": True}]
        out = bot.render_guests(rows, "")
        self.assertIn("🙂", out)
        self.assertNotIn("المشكلة", out)

    def test_header_counts(self):
        rows = [
            {"guest": "a", "unit": "u", "mood": "happy", "issue": "", "resolved": True},
            {"guest": "b", "unit": "u", "mood": "normal", "issue": "", "resolved": True},
            {"guest": "c", "unit": "u", "mood": "sad", "issue": "i", "resolved": False},
        ]
        out = bot.render_guests(rows, "")
        self.assertIn("🙂 1", out)
        self.assertIn("😐 1", out)
        self.assertIn("☹️ 1", out)


if __name__ == "__main__":
    unittest.main()
