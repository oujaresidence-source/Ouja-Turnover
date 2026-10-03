# -*- coding: utf-8 -*-
"""
«المناوبة» wording that must survive right-to-left rendering.

A bare «5:00 – 7:00» inside an Arabic Discord line is laid out right-to-left and READS
«7:00 – 5:00» (seen in the first screenshots). Words around the times fix the order.

Run: python3 -m unittest tests.test_oncall_texts
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oncall import roster, texts   # noqa: E402


class SlotLabel(unittest.TestCase):
    def test_reads_in_order_inside_arabic(self):
        self.assertEqual(texts.slot_label({"start_min": 0, "end_min": 120}), "من 5:00 لين 7:00")

    def test_last_slot_ends_at_twelve(self):
        self.assertEqual(texts.slot_label({"start_min": 360, "end_min": 420}), "من 11:00 لين 12:00")



class Neutral(unittest.TestCase):
    """Three of the five on-call people are women (نورة، عهود، مآثر) and the editor is not
    always اسيل. Every line that NAMES a third person must not guess their gender."""

    SLOT = {"start_min": 0, "end_min": 120, "employee": "نورة", "employee_did": ""}
    NXT = {"start_min": 120, "end_min": 180, "employee": "عهود", "employee_did": ""}
    ISSUE = {"title": "تسريب", "owner": "نورة"}
    GENDERED = ("ما ردّ", "يرجع", "إجازته", "حسابه", "باسمه", "وافق —", " رفض ", "وهو ",
                "حطّتك", "شالتك", " خلّص", "يبي ", "ياخذ", "سلوته", "ردّ ")

    def lines(self):
        return [texts.supervisor_miss("نورة", 1, self.SLOT),
                texts.swap_ask("عهود", self.SLOT, self.NXT, "exchange"),
                texts.swap_ask("عهود", self.SLOT, None, "takeover"),
                texts.swap_result(True, "نورة", self.SLOT),
                texts.swap_result(False, "نورة", self.SLOT),
                texts.swap_fyi("عهود", "نورة", self.SLOT, "exchange"),
                texts.swap_fyi("عهود", "نورة", self.SLOT, "takeover"),
                texts.slot_edited_new(self.SLOT, "فيصل"),
                texts.slot_edited_old(self.SLOT, "فيصل"),
                texts.issue_note("maint", "", "نورة"),
                texts.issue_note("escalation", "", "نورة"),
                texts.stale(self.ISSUE),
                texts.handover(self.SLOT, self.NXT, []),
                texts.night_summary(__import__("datetime").date(2026, 10, 4),
                                    [{"name": "نورة", "answered": 5, "total": 8, "missed": 1}], [], []),
                roster.WHY_OFF_DAY, roster.WHY_NO_DISCORD]

    def test_no_gendered_third_person(self):
        for line in self.lines():
            for w in self.GENDERED:
                self.assertNotIn(w, line, line)


if __name__ == "__main__":
    unittest.main()
