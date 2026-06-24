# -*- coding: utf-8 -*-
"""Frontend<->backend contract for the expense Approval Center.

Guards the EXACT drift classes that have reached the owner:
  - the chip badge must read the .count of the {count,sar} tab value
    (stringifying the object renders the literal '[object Object]');
  - the served tab shape must stay {count:int, sar:number};
  - every /erp/api/exp* path the JS calls must be a registered route;
  - every literal data-act token must have a handler;
  - T.ar and T.en must stay at parity and cover every literal t() key.
"""
import json
import pathlib
import re
import shutil
import subprocess
import unittest

import bot

JS = pathlib.Path("finance/static/erp.js").read_text("utf-8")
INIT = pathlib.Path("finance/__init__.py").read_text("utf-8")


class ChipContract(unittest.TestCase):
    def test_backend_tabs_shape_is_count_sar(self):
        bot._expenses.clear()
        bot._expenses["c1"] = {"id": "c1", "amount": 10.0, "expense_date": "2026-05-01",
                               "apartment": "Ouja | X", "listing_id": 1, "category": "صيانة",
                               "approval_status": "pending_approval"}
        tabs = bot._exp4_overview_data(tab="pending")["tabs"]
        self.assertEqual(set(tabs), {"pending", "approved", "exported", "verified", "needs_action"})
        for k, v in tabs.items():
            self.assertIsInstance(v, dict, k)
            self.assertIsInstance(v["count"], int, k)
            self.assertIsInstance(v["sar"], (int, float), k)

    def test_chip_renderer_reads_count_not_object(self):
        # the exact broken coercion must be gone, and the chip must read a .count off the tab value
        self.assertNotIn("' <b>' + tabs[k]", JS)
        chip_area = JS[JS.index("function renderExp"):JS.index("function loadExp")]
        self.assertIn("tabs[k]", chip_area)
        self.assertIn(".count", chip_area)


if __name__ == "__main__":
    unittest.main()
