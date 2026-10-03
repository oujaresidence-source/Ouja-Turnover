# -*- coding: utf-8 -*-
"""
ops «4 clean weeks retire the oldest warning» x «المناوبة»: a week in which somebody missed an
on-call night is NOT clean (owner-approved assumption 1 in the spec).

Run: python3 -m unittest tests.test_oncall_retirement
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import db as odb                     # noqa: E402
from tests.test_oncall_flow import Case       # noqa: E402


class Retirement(Case):
    def test_week_with_oncall_warning_is_not_clean(self):
        from ops import notify as onotify
        name = "ناصر"
        for wk in ("2026-W36", "2026-W37", "2026-W38", "2026-W39"):
            ob = odb.ensure_obligation("wr", name, "101", wk, "2026-10-01T23:59:00+03:00")
            odb.set_status(ob["id"], "done")
        oc = odb.ensure_obligation("oc", name, "101", "OC-2026-09-29", "2026-09-29T19:10:00+03:00")
        odb.set_status(oc["id"], "missed")
        odb.issue_warning(oc, "test")
        os.environ["OPS_WARN_DRYRUN"] = "0"
        try:
            from ops import switch as osw
            osw.invalidate()
            r = onotify._retirement(name)
        finally:
            os.environ.pop("OPS_WARN_DRYRUN", None)
        self.assertIsNone(r)                      # W40 (29 Sep) had the on-call warning
        self.assertEqual(len(odb.warnings_for(name, "active")), 1)




if __name__ == "__main__":
    unittest.main()
