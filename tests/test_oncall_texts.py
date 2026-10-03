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

from oncall import texts   # noqa: E402


class SlotLabel(unittest.TestCase):
    def test_reads_in_order_inside_arabic(self):
        self.assertEqual(texts.slot_label({"start_min": 0, "end_min": 120}), "من 5:00 لين 7:00")

    def test_last_slot_ends_at_twelve(self):
        self.assertEqual(texts.slot_label({"start_min": 360, "end_min": 420}), "من 11:00 لين 12:00")


if __name__ == "__main__":
    unittest.main()
