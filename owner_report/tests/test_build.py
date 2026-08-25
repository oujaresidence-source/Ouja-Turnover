# -*- coding: utf-8 -*-
import pathlib
import tempfile
import unittest

from owner_report.build import reconciliation
from owner_report.model import build_cfg
from owner_report.audit_log import AuditLog
from owner_report.errors import ValidationError
from owner_report.tests.fixtures import valid_inp, valid_meta
from owner_report.tests.test_stores import MemStore

try:
    from owner_report import renderer_api
    _CAN_RENDER = renderer_api.verify_schema_matches()
except Exception:
    _CAN_RENDER = False


class TestReconciliationMath(unittest.TestCase):
    def test_reference_chain(self):
        cfg, _, _ = build_cfg(valid_inp())
        r = reconciliation(cfg)
        self.assertEqual(r["gross"], 95_285)
        self.assertEqual(r["channel_fees"], 3_240)
        self.assertEqual(r["net_rental"], 92_045)
        self.assertEqual(r["mgmt_fee"], 18_409)   # round(92045*0.20)
        self.assertEqual(r["opex_total"], 7_120)
        self.assertEqual(r["owner_net"], 66_516)  # 92045-18409-7120
        self.assertEqual(r["nights_booked"], 138)
        self.assertEqual(r["nights_available"], 181)


@unittest.skipUnless(_CAN_RENDER, "renderer not importable on this interpreter")
class TestOrchestrator(unittest.TestCase):
    def _run(self, tmp, audit=None, meta_over=None):
        from owner_report.build import build_report
        meta = valid_meta()
        if meta_over:
            meta.update(meta_over)
        return build_report(
            valid_inp(), meta, pathlib.Path(tmp) / "r.pdf",
            generated_by="faisal", created_at="2026-07-13T10:00:00", audit_log=audit,
        )

    def test_full_build_passes_all_gates_and_snapshots(self):
        m = MemStore()
        log = AuditLog(m.load, m.save)
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(tmp, audit=log)
            self.assertTrue(res["pdf"].exists())
            self.assertEqual(res["doc_ref"], "OJ-OPR-2026-H1-B207")
            self.assertEqual(res["reconciliation"]["owner_net"], 66_516)
            # snapshot written + integrity holds
            self.assertTrue(log.verify_integrity("OJ-OPR-2026-H1-B207"))

    def test_report_is_reproducible_from_snapshot(self):
        m = MemStore()
        log = AuditLog(m.load, m.save)
        with tempfile.TemporaryDirectory() as tmp:
            res = self._run(tmp, audit=log)
            inp2 = log.reproduce_inputs("OJ-OPR-2026-H1-B207")
            cfg2, _, _ = build_cfg(inp2)
            self.assertEqual(cfg2, res["cfg"])  # exact reconstruction

    def test_unsigned_reconciliation_blocks_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValidationError):
                self._run(tmp, meta_over={"reconciliation_signed": False})

    def test_reissue_same_docref_refused(self):
        from owner_report.errors import BuildError
        m = MemStore()
        log = AuditLog(m.load, m.save)
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, audit=log)
            with self.assertRaises(BuildError):
                self._run(tmp, audit=log)  # same doc_ref -> immutable refusal


if __name__ == "__main__":
    unittest.main()
