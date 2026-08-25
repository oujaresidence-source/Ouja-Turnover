# -*- coding: utf-8 -*-
"""«مشتريات الفريق» Team Purchases + عهدة float engine — synthetic, no network.

Locks the invariants that keep the owner's money math honest:
  * float balance is ledger-derived (original/spent/remaining) and auto-deducts;
  * delete/edit of a float purchase REVERSES/ADJUSTS the balance exactly;
  * top-up and settlement restore the float and appear in the statement with a running balance;
  * the transfer lifecycle is a strict state machine (pending→approved→transferred; reject needs a reason);
  * finance-only transitions refuse from the wrong state (no silent no-ops);
  * edit/delete is gated on the backend (pending-only for transfer; own-or-finance);
  * float-balance visibility is finance-all / holder-own / nobody-else.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from finance import purchases as tp


def _fresh_db():
    bdb.set_db_path_for_tests(os.path.join(tempfile.mkdtemp(prefix="tptest_"), "brain.db"))
    tp.reset_init_cache()


def _holder(name):
    return [h for h in tp.holders() if h["name"] == name][0]


class Seed(unittest.TestCase):
    def setUp(self):
        _fresh_db()

    def test_name_lists_seeded_from_one_place(self):
        self.assertEqual(tp.submitters(),
                         ["أسيل", "محمد", "نورة", "مآثر", "ناصر", "عهود", "تقي", "أبو أمين"])
        self.assertEqual(tp.buyers(), ["تقي", "أبو أمين"])
        self.assertEqual(sorted(tp.holder_names()), sorted(["أسيل", "محمد", "تقي", "أبو أمين"]))

    def test_buyers_are_subset_of_submitters(self):
        self.assertTrue(set(tp.buyers()).issubset(set(tp.submitters())))


class ReceiptGate(unittest.TestCase):
    def setUp(self):
        _fresh_db()

    def test_neither_image_nor_reason_is_refused(self):
        with self.assertRaises(tp.TPError) as c:
            tp.create_purchase({"item": "x", "amount": 10, "submitted_by": "نورة",
                                "buyer": "تقي", "pay_source": "transfer"}, actor="u")
        self.assertEqual(c.exception.code, "no_receipt")

    def test_no_receipt_reason_alone_is_allowed(self):
        p = tp.create_purchase({"item": "x", "amount": 10, "submitted_by": "نورة", "buyer": "تقي",
                                "pay_source": "transfer", "no_receipt_reason": "نسي الفاتورة"}, actor="u")
        self.assertEqual(p["status"], tp.ST_PENDING)

    def test_image_alone_is_allowed(self):
        p = tp.create_purchase({"item": "x", "amount": 10, "submitted_by": "نورة", "buyer": "تقي",
                                "pay_source": "transfer", "receipt_path": "/data/team_purchases/1/r.jpg"},
                               actor="u")
        self.assertEqual(p["status"], tp.ST_PENDING)


class TransferLifecycle(unittest.TestCase):
    def setUp(self):
        _fresh_db()
        self.p = tp.create_purchase({"item": "دهان", "amount": 300, "submitted_by": "نورة",
                                     "buyer": "أبو أمين", "pay_source": "transfer",
                                     "no_receipt_reason": "y"}, actor="nora")

    def test_flow_pending_approved_transferred(self):
        self.assertEqual(self.p["status"], tp.ST_PENDING)
        tp.approve(self.p["id"], by="admin")
        self.assertEqual(tp.get_purchase(self.p["id"])["status"], tp.ST_APPROVED)
        tp.mark_transferred(self.p["id"], by="admin")
        self.assertEqual(tp.get_purchase(self.p["id"])["status"], tp.ST_TRANSFERRED)

    def test_cannot_transfer_before_approve(self):
        with self.assertRaises(tp.TPError) as c:
            tp.mark_transferred(self.p["id"], by="admin")
        self.assertEqual(c.exception.code, "bad_state")

    def test_reject_requires_reason(self):
        with self.assertRaises(tp.TPError) as c:
            tp.reject(self.p["id"], by="admin", reason="  ")
        self.assertEqual(c.exception.code, "no_reason")

    def test_reject_sets_reason(self):
        tp.reject(self.p["id"], by="admin", reason="مبلغ غير مبرر")
        r = tp.get_purchase(self.p["id"])
        self.assertEqual(r["status"], tp.ST_REJECTED)
        self.assertEqual(r["reject_reason"], "مبلغ غير مبرر")

    def test_double_approve_is_refused(self):
        tp.approve(self.p["id"], by="admin")
        with self.assertRaises(tp.TPError):
            tp.approve(self.p["id"], by="admin")

    def test_locked_after_finance_acts(self):
        tp.approve(self.p["id"], by="admin")
        # submitter can no longer edit/delete once Finance has acted
        with self.assertRaises(tp.TPError) as c:
            tp.edit_purchase(self.p["id"], {"amount": 999}, actor="nora", is_finance=False)
        self.assertEqual(c.exception.code, "locked")
        with self.assertRaises(tp.TPError):
            tp.delete_purchase(self.p["id"], actor="nora", is_finance=False)

    def test_pending_editable_by_submitter_only(self):
        # a different, non-finance user can't touch it
        with self.assertRaises(tp.TPError) as c:
            tp.edit_purchase(self.p["id"], {"amount": 500}, actor="someone_else", is_finance=False)
        self.assertEqual(c.exception.code, "forbidden")
        # the creator can
        tp.edit_purchase(self.p["id"], {"amount": 500}, actor="nora", is_finance=False)
        self.assertEqual(tp.get_purchase(self.p["id"])["amount"], 500.0)


class FloatBalances(unittest.TestCase):
    def setUp(self):
        _fresh_db()
        self.h = _holder("تقي")
        tp.save_holder("تقي", start_balance=5000, low_threshold=500, holder_id=self.h["id"])

    def _buy(self, amount, **kw):
        base = {"item": "بند", "amount": amount, "submitted_by": "تقي", "buyer": "تقي",
                "pay_source": "float", "holder_id": self.h["id"], "no_receipt_reason": "n"}
        base.update(kw)
        return tp.create_purchase(base, actor="admin")

    def test_float_purchase_needs_holder(self):
        with self.assertRaises(tp.TPError) as c:
            tp.create_purchase({"item": "x", "amount": 10, "submitted_by": "تقي", "buyer": "تقي",
                                "pay_source": "float", "no_receipt_reason": "n"}, actor="admin")
        self.assertEqual(c.exception.code, "bad_holder")

    def test_float_status_and_deduction(self):
        p = self._buy(1200)
        self.assertEqual(p["status"], tp.ST_FLOAT)
        b = tp.holder_balance(self.h["id"])
        self.assertEqual((b["original"], b["spent"], b["remaining"]), (5000.0, 1200.0, 3800.0))

    def test_delete_reverses_deduction(self):
        p = self._buy(1200)
        tp.delete_purchase(p["id"], actor="admin", is_finance=True)
        b = tp.holder_balance(self.h["id"])
        self.assertEqual(b["remaining"], 5000.0)
        self.assertEqual(b["spent"], 0.0)

    def test_edit_amount_adjusts_balance(self):
        p = self._buy(1000)
        self.assertEqual(tp.holder_balance(self.h["id"])["remaining"], 4000.0)
        tp.edit_purchase(p["id"], {"amount": 1500}, actor="admin", is_finance=True)
        self.assertEqual(tp.holder_balance(self.h["id"])["remaining"], 3500.0)
        tp.edit_purchase(p["id"], {"amount": 200}, actor="admin", is_finance=True)
        self.assertEqual(tp.holder_balance(self.h["id"])["remaining"], 4800.0)

    def test_edit_moves_between_holders(self):
        other = _holder("محمد")
        tp.save_holder("محمد", start_balance=2000, holder_id=other["id"])
        p = self._buy(600)
        self.assertEqual(tp.holder_balance(self.h["id"])["remaining"], 4400.0)
        tp.edit_purchase(p["id"], {"holder_id": other["id"]}, actor="admin", is_finance=True)
        self.assertEqual(tp.holder_balance(self.h["id"])["remaining"], 5000.0)   # tقي made whole
        self.assertEqual(tp.holder_balance(other["id"])["remaining"], 1400.0)    # محمد now carries it

    def test_low_balance_flag(self):
        self.assertFalse(tp.holder_balance(self.h["id"])["low"])
        self._buy(4600)   # remaining 400 <= 500
        self.assertTrue(tp.holder_balance(self.h["id"])["low"])

    def test_topup_and_settle(self):
        self._buy(800)                                   # remaining 4200
        tp.topup(self.h["id"], 300, by="admin")          # remaining 4500, spent 500
        b = tp.holder_balance(self.h["id"])
        self.assertEqual((b["remaining"], b["spent"]), (4500.0, 500.0))
        tp.settle(self.h["id"], by="admin")              # back to original
        b = tp.holder_balance(self.h["id"])
        self.assertEqual((b["remaining"], b["spent"]), (5000.0, 0.0))

    def test_settle_noop_refused(self):
        with self.assertRaises(tp.TPError) as c:
            tp.settle(self.h["id"], by="admin")
        self.assertEqual(c.exception.code, "nothing_to_settle")

    def test_statement_running_balance(self):
        self._buy(800)
        tp.topup(self.h["id"], 300, by="admin")
        tp.settle(self.h["id"], by="admin")
        st = tp.statement(self.h["id"])
        self.assertEqual([e["kind"] for e in st["entries"]], ["purchase", "topup", "settlement"])
        self.assertEqual(st["entries"][0]["balance"], 4200.0)
        self.assertEqual(st["entries"][1]["balance"], 4500.0)
        self.assertEqual(st["entries"][2]["balance"], 5000.0)


class Visibility(unittest.TestCase):
    def setUp(self):
        _fresh_db()
        self.tagy = _holder("تقي")
        tp.save_holder("تقي", start_balance=1000, user_key="تقي", holder_id=self.tagy["id"])

    def test_finance_sees_all(self):
        self.assertEqual(tp.visible_holder_ids(actor="whoever", is_finance=True),
                         {h["id"] for h in tp.holders()})

    def test_holder_sees_only_own(self):
        self.assertEqual(tp.visible_holder_ids(actor="تقي", is_finance=False), {self.tagy["id"]})

    def test_unlinked_user_sees_nothing(self):
        self.assertEqual(tp.visible_holder_ids(actor="نورة", is_finance=False), set())

    def test_empty_actor_sees_nothing(self):
        self.assertEqual(tp.visible_holder_ids(actor="", is_finance=False), set())


class Summary(unittest.TestCase):
    def setUp(self):
        _fresh_db()
        self.h = _holder("تقي")
        tp.save_holder("تقي", start_balance=9000, holder_id=self.h["id"])

    def test_totals_by_bucket(self):
        a = tp.create_purchase({"item": "a", "amount": 100, "submitted_by": "نورة", "buyer": "تقي",
                                "pay_source": "transfer", "no_receipt_reason": "n"}, actor="u")
        tp.create_purchase({"item": "b", "amount": 200, "submitted_by": "نورة", "buyer": "تقي",
                            "pay_source": "transfer", "no_receipt_reason": "n"}, actor="u")
        c = tp.create_purchase({"item": "c", "amount": 500, "submitted_by": "نورة", "buyer": "تقي",
                                "pay_source": "transfer", "no_receipt_reason": "n"}, actor="u")
        tp.create_purchase({"item": "d", "amount": 700, "submitted_by": "تقي", "buyer": "تقي",
                            "pay_source": "float", "holder_id": self.h["id"], "no_receipt_reason": "n"}, actor="u")
        tp.approve(c["id"], by="admin")   # awaiting transfer
        tp.approve(a["id"], by="admin")
        tp.mark_transferred(a["id"], by="admin")
        s = tp.summary()
        self.assertEqual(s["pending"]["count"], 1)          # only b
        self.assertEqual(s["pending"]["sar"], 200.0)
        self.assertEqual(s["approved"]["count"], 1)         # c
        self.assertEqual(s["approved"]["sar"], 500.0)
        self.assertEqual(s["transferred"]["count"], 1)      # a
        self.assertEqual(s["transferred"]["sar"], 100.0)
        self.assertEqual(s["float"]["count"], 1)            # d
        self.assertEqual(s["float"]["sar"], 700.0)

    def test_filters_and_search(self):
        tp.create_purchase({"item": "مكيف سبليت", "amount": 100, "submitted_by": "نورة", "buyer": "تقي",
                            "pay_source": "transfer", "no_receipt_reason": "n"}, actor="u")
        tp.create_purchase({"item": "دهان", "amount": 200, "submitted_by": "محمد", "buyer": "أبو أمين",
                            "pay_source": "transfer", "no_receipt_reason": "n"}, actor="u")
        self.assertEqual(len(tp.list_purchases({"q": "مكيف"})), 1)
        self.assertEqual(len(tp.list_purchases({"submitted_by": "محمد"})), 1)
        self.assertEqual(len(tp.list_purchases({"buyer": "تقي"})), 1)
        self.assertEqual(len(tp.list_purchases({})), 2)

    def test_deleted_excluded_by_default(self):
        p = tp.create_purchase({"item": "x", "amount": 100, "submitted_by": "نورة", "buyer": "تقي",
                                "pay_source": "transfer", "no_receipt_reason": "n"}, actor="u")
        tp.delete_purchase(p["id"], actor="u", is_finance=False)
        self.assertEqual(len(tp.list_purchases({})), 0)
        self.assertEqual(len(tp.list_purchases({}, include_deleted=True)), 1)


class FrontendContract(unittest.TestCase):
    """Guard the JS<->backend wiring: every /erp/api/tp path the SPA calls must be a registered
    route, the workspace + i18n keys must exist, and T.ar/T.en must stay at parity for tp_*."""

    @classmethod
    def setUpClass(cls):
        import pathlib
        cls.JS = pathlib.Path("finance/static/erp.js").read_text("utf-8")
        cls.INIT = pathlib.Path("finance/__init__.py").read_text("utf-8")

    def test_every_tp_api_called_is_registered(self):
        import re
        routes = set(re.findall(r'add_(?:get|post)\s*\(\s*"([^"]+)"', self.INIT))
        called = set(re.findall(r"""api\(\s*['"](/erp/api/tp[^'"?]*)""", self.JS))
        self.assertTrue(called, "expected the SPA to call /erp/api/tp endpoints")
        for c in called:
            c = c.rstrip("/")
            self.assertIn(c, routes, "JS calls an unregistered route: " + c)

    def test_workspace_registered(self):
        self.assertIn("{ id: 'teampur', built: true }", self.JS)
        self.assertIn("teampur:", self.JS)          # VIEWS entry + CORE_WS

    def test_i18n_parity_for_tp_keys(self):
        import re
        ar = self.JS[self.JS.index("ar: {"):self.JS.index("en: {")]
        en = self.JS[self.JS.index("en: {"):]
        ar_keys = set(re.findall(r"\b(tp_[a-z_]+|ws_teampur)\s*:", ar))
        en_keys = set(re.findall(r"\b(tp_[a-z_]+|ws_teampur)\s*:", en))
        self.assertIn("ws_teampur", ar_keys)
        self.assertEqual(ar_keys, en_keys, "T.ar and T.en tp_* keys are out of parity: "
                         + repr(ar_keys.symmetric_difference(en_keys)))


if __name__ == "__main__":
    unittest.main()
