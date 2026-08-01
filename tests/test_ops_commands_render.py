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
    @staticmethod
    def scored(score=8, **overrides):
        row = {"guest": "عبدالله", "unit": "Ouja | حطين", "score": score,
               "reason": "تأخر التسليم ساعتين", "quote": "صار لي ساعتين أنتظر",
               "resolved": False, "staff": "نورة", "phone": "0501234567",
               "evidence_state": "known"}
        row.update(overrides)
        return row

    def test_empty(self):
        self.assertIn("ما فيه ضيوف", bot.render_guests([], ""))

    def test_lowest_score_is_first(self):
        text = bot.render_guests([
            {"guest": "Perfect", "unit": "A", "score": 10,
             "evidence_state": "known"},
            self.scored(3, guest="Needs help", unit="B"),
        ], "اليوم")
        self.assertLess(text.index("Needs help"), text.index("Perfect"))

    def test_below_ten_has_reason_evidence_status_and_contact(self):
        text = bot.render_guests([self.scored(8)], "اليوم")
        self.assertIn("8/10", text)
        self.assertIn("ليش", text)
        self.assertIn("تأخر التسليم", text)
        self.assertIn("«صار لي ساعتين أنتظر»", text)
        self.assertIn("لسه مفتوحة", text)
        self.assertIn("نورة", text)
        self.assertIn("wa.me/966501234567", text)

    def test_ten_is_compact_and_unknown_is_explicit(self):
        text = bot.render_guests([
            {"guest": "Perfect", "unit": "A", "score": 10,
             "evidence_state": "known"},
            {"guest": "Unknown", "unit": "B", "score": None,
             "evidence_state": "unknown", "reason": "تعذر التحليل"},
        ], "")
        self.assertIn("10/10 · Perfect — A", text)
        self.assertIn("أدلة غير كافية", text)

    def test_header_has_score_bands(self):
        text = bot.render_guests([
            self.scored(2, guest="a"), self.scored(5, guest="b"),
            self.scored(8, guest="c"), self.scored(10, guest="d"),
        ], "")
        self.assertIn("الإجمالي: 4 ضيف", text)
        self.assertIn("0–3: 1", text)
        self.assertIn("4–6: 1", text)
        self.assertIn("7–9: 1", text)
        self.assertIn("10: 1", text)


if __name__ == "__main__":
    unittest.main()
