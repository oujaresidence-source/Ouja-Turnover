# tests/test_finchat_routes.py
# -*- coding: utf-8 -*-
"""finchat.routes — service-level behavior: escalate creates row + fires notify;
inbox answer appends owner msg to the asker's thread + optional learn-loop KB row."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from finchat import db as fdb
from finchat import routes as frt


class TestEscalateService(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="fcrt_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        fdb.reset_init_cache()
        self.fired = []
        frt.HOST.update({"notify": lambda payload: self.fired.append(payload)})

    def test_escalate_creates_and_notifies(self):
        r = frt.svc_escalate("acc1", "الاكسبورت واقف")
        self.assertTrue(r["ok"])
        self.assertEqual(len(self.fired), 1)
        self.assertEqual(self.fired[0]["esc_id"], r["esc_id"])
        self.assertIn("acc1", self.fired[0]["username"])
        self.assertIn(r["esc_id"], [x["id"] for x in fdb.esc_open_list()])

    def test_notify_failure_does_not_lose_escalation(self):
        def boom(p):
            raise RuntimeError("discord down")
        frt.HOST.update({"notify": boom})
        r = frt.svc_escalate("acc1", "سؤال")
        self.assertTrue(r["ok"])  # row saved even if the ping failed
        self.assertTrue(fdb.esc_open_list())

    def test_inbox_answer_appends_owner_msg_and_learns(self):
        e = frt.svc_escalate("acc2", "وين كشف مالك ابو فهد؟")["esc_id"]
        kb_before = len(fdb.kb_all(enabled_only=False))
        r = frt.svc_inbox_answer(e, "من #owners اختر ابو فهد", save_kb=True, kb_tags="ملاك")
        self.assertTrue(r["ok"])
        msgs = fdb.msgs_for("acc2")
        self.assertEqual(msgs[-1]["role"], "owner")
        self.assertIn("ابو فهد", msgs[-1]["text"])
        self.assertEqual(len(fdb.kb_all(enabled_only=False)), kb_before + 1)
        new = fdb.kb_all(enabled_only=False)[-1]
        self.assertEqual(new["source"], "learned")
        # double answer refused
        r2 = frt.svc_inbox_answer(e, "ثاني", save_kb=False, kb_tags="")
        self.assertEqual(r2.get("error"), "already_answered")


if __name__ == "__main__":
    unittest.main()
