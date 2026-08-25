# -*- coding: utf-8 -*-
import unittest

from owner_report.assumptions import AssumptionStore
from owner_report.audit_log import AuditLog
from owner_report import questions as Q
from owner_report.errors import BuildError


class MemStore:
    """In-memory load/save pair matching the bot's state_path caps."""
    def __init__(self):
        self.data = {}

    def load(self, name, default=None):
        return self.data.get(name, default)

    def save(self, name, obj):
        self.data[name] = obj


class TestAssumptions(unittest.TestCase):
    def setUp(self):
        self.m = MemStore()
        self.s = AssumptionStore(self.m.load, self.m.save)

    def test_prefill_is_never_confirmed(self):
        self.s.record("101", {"purchase_price": 1_300_000}, "faisal", "2026-07-13T10:00:00")
        pf = self.s.prefill("101")
        self.assertEqual(pf["purchase_price"]["value"], 1_300_000)
        self.assertFalse(pf["purchase_price"]["confirmed"])  # pre-filled != confirmed
        self.assertEqual(pf["purchase_price"]["stored_at"], "2026-07-13T10:00:00")

    def test_all_confirmed_requires_every_field(self):
        run = {"a": {"value": 1, "confirmed": True}, "b": {"value": 2, "confirmed": False}}
        self.assertFalse(AssumptionStore.all_confirmed(run))
        self.assertEqual(AssumptionStore.unconfirmed_fields(run), ["b"])
        run["b"]["confirmed"] = True
        self.assertTrue(AssumptionStore.all_confirmed(run))

    def test_empty_run_is_not_all_confirmed(self):
        self.assertFalse(AssumptionStore.all_confirmed({}))

    def test_values_of(self):
        run = {"a": {"value": 1, "confirmed": True}, "b": {"value": 2, "confirmed": True}}
        self.assertEqual(AssumptionStore.values_of(run), {"a": 1, "b": 2})


class TestQuestions(unittest.TestCase):
    def test_all_sections_present(self):
        for s in "ABCDEFGH":
            self.assertIn(s, Q.SECTIONS)
            self.assertTrue(Q.BY_SECTION[s], f"section {s} has no questions")

    def test_vat_and_furnished_are_required_and_mapped(self):
        self.assertTrue(Q.BY_ID["vat_basis"].required)
        self.assertEqual(Q.BY_ID["vat_basis"].maps_to, "vat_resolved")
        self.assertEqual(Q.BY_ID["ejar_furnished"].maps_to, "ejar_unfurnished_no_uplift")

    def test_missing_required_detected(self):
        answers = {q.id: "x" for q in Q.QUESTIONS if q.required}
        self.assertEqual(Q.missing_required(answers), [])
        answers.pop("vat_basis")
        self.assertIn("vat_basis", Q.missing_required(answers))


class TestAuditLog(unittest.TestCase):
    def setUp(self):
        self.m = MemStore()
        self.log = AuditLog(self.m.load, self.m.save)

    def _issue(self, doc_ref="OJ-OPR-2026-H1-B207", **over):
        kw = dict(
            doc_ref=doc_ref, unit_ref="B-207", lid=101, period="H1 2026",
            generated_by="faisal", created_at="2026-07-13T10:00:00",
            inputs={"vat_basis": "net", "asset": {"purchase_price": 1_300_000}},
            cfg={"UNIT": {"unit_ref": "B-207"}},
            manifest=[{"path": "ASSET.purchase_price", "tag": "O", "value": 1_300_000, "note": ""}],
            meta={"reconciliation_signed": True}, disclosures=[],
            reconciliation={"gross": 95_285, "owner_net": 69_000},
            pdf_ref="/data/reports/OJ-OPR-2026-H1-B207.pdf", pdf_sha256="abc123",
        )
        kw.update(over)
        return self.log.issue(**kw)

    def test_issue_and_reproduce(self):
        self._issue()
        inp = self.log.reproduce_inputs("OJ-OPR-2026-H1-B207")
        self.assertEqual(inp["asset"]["purchase_price"], 1_300_000)

    def test_never_silently_regenerated(self):
        self._issue()
        with self.assertRaises(BuildError):
            self._issue()  # same doc_ref again

    def test_correction_supersedes_prior(self):
        self._issue()
        self._issue(doc_ref="OJ-OPR-2026-H1-B207-R2", supersedes="OJ-OPR-2026-H1-B207")
        old = self.log.get("OJ-OPR-2026-H1-B207")
        self.assertEqual(old["status"], "superseded")
        self.assertEqual(old["superseded_by"], "OJ-OPR-2026-H1-B207-R2")
        self.assertEqual(self.log.get("OJ-OPR-2026-H1-B207-R2")["status"], "issued")

    def test_integrity_hash(self):
        self._issue()
        self.assertTrue(self.log.verify_integrity("OJ-OPR-2026-H1-B207"))
        # tamper
        self.m.data["owner_report_audit.json"]["OJ-OPR-2026-H1-B207"]["reconciliation"]["owner_net"] = 999
        self.assertFalse(self.log.verify_integrity("OJ-OPR-2026-H1-B207"))


if __name__ == "__main__":
    unittest.main()
