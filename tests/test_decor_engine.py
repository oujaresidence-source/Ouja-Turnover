# -*- coding: utf-8 -*-
"""
The decoration rulebook, locked. Every owner rule from 2026-07-26 has a test here, so a
future refactor that quietly loosens one fails the suite instead of the guest's evening.

Run: python3 -m unittest tests.test_decor_engine
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decor import engine, packs  # noqa: E402


def P(pid):
    p = packs.get(pid)
    assert p, "pack %s missing from decor_packs.json" % pid
    return p


class TestCapabilityGate(unittest.TestCase):
    """«الشقة ما تسمح» — stop the supervisor, never surprise the guest."""

    def test_diamond_without_pool_is_refused_and_names_the_feature(self):
        cap = engine.capability_check(P("diamond"), ["jacuzzi"])
        self.assertEqual(cap["verdict"], "missing")
        self.assertEqual(cap["missing"], ["pool"])
        self.assertIn("مسبح", cap["missing_ar"][0])
        # and opening without an override is refused
        res = engine.open_check(P("diamond"), ["jacuzzi"])
        self.assertFalse(res["allowed"])
        self.assertEqual(res["error"], "capability")

    def test_diamond_with_pool_passes(self):
        self.assertEqual(engine.capability_check(P("diamond"), ["pool", "jacuzzi"])["verdict"], "ok")

    def test_unknown_unit_blocks_but_says_unknown_not_missing(self):
        """Not knowing and knowing-it's-absent are different answers to the supervisor."""
        cap = engine.capability_check(P("diamond"), None)
        self.assertEqual(cap["verdict"], "unknown")
        self.assertEqual(cap["missing"], ["pool"])
        self.assertFalse(engine.open_check(P("diamond"), None)["allowed"])

    def test_silver_accepts_a_bathtub_or_a_jacuzzi_but_not_neither(self):
        self.assertEqual(engine.capability_check(P("silver"), ["bathtub"])["verdict"], "ok")
        self.assertEqual(engine.capability_check(P("silver"), ["jacuzzi"])["verdict"], "ok")
        self.assertEqual(engine.capability_check(P("silver"), ["pool"])["verdict"], "missing")

    def test_packs_with_no_requirement_never_block(self):
        for pid in ("bronze", "table_styling"):
            self.assertEqual(engine.capability_check(P(pid), None)["verdict"], "ok")
            self.assertTrue(engine.open_check(P(pid), None)["allowed"])


class TestOverride(unittest.TestCase):
    """The supervisor may push it through — but it is recorded and it is stamped."""

    def test_accept_gap_creates_the_order_and_stamps_it(self):
        res = engine.open_check(P("diamond"), ["jacuzzi"], override_kind="accept_gap",
                                overridden_by="ناصر", reason="الضيف موافق بدون تنسيق مسبح")
        self.assertTrue(res["allowed"])
        self.assertEqual(res["verdict"], "accepted_gap")
        self.assertIn("مسبح", res["stamp"])
        self.assertIn("الباقة الماسية", res["stamp"])

    def test_the_stamp_names_the_exact_affected_checklist_lines(self):
        items = engine.affected_checklist_items(P("diamond"), ["pool"])
        self.assertEqual(len(items), 2)
        self.assertTrue(all("مسبح" in i for i in items))
        stamp = engine.capability_stamp(P("diamond"), ["pool"], "ناصر", "2026-07-26 14:00")
        for i in items:
            self.assertIn(i, stamp)
        self.assertIn("ناصر", stamp)

    def test_correction_creates_a_clean_order_and_teaches_the_sheet(self):
        res = engine.open_check(P("diamond"), ["jacuzzi"], override_kind="correction",
                                overridden_by="ناصر", reason="القائمة غلط، فيها مسبح")
        self.assertTrue(res["allowed"])
        self.assertEqual(res["stamp"], "")           # nothing is missing, so nothing is stamped
        self.assertEqual(res["learn_features"], ["pool"])

    def test_override_without_a_name_or_a_reason_is_refused(self):
        for kw in ({"overridden_by": "", "reason": "لأن"}, {"overridden_by": "ناصر", "reason": ""}):
            res = engine.open_check(P("diamond"), ["jacuzzi"], override_kind="accept_gap", **kw)
            self.assertFalse(res["allowed"])
            self.assertEqual(res["error"], "override_needs_who_and_why")

    def test_an_unrecognised_override_kind_is_refused(self):
        res = engine.open_check(P("diamond"), ["jacuzzi"], override_kind="whatever",
                                overridden_by="ناصر", reason="x")
        self.assertFalse(res["allowed"])
        self.assertEqual(res["error"], "bad_override")


class TestGuestInputGate(unittest.TestCase):
    """No vendor is ever sent a half-finished order."""

    def test_dispatch_blocked_while_any_required_input_is_empty(self):
        pack = P("diamond")
        order = {"final_price_sar": 1600, "inputs": {"phrases": "٨ عبارات", "occasion": "تخرج",
                                                     "cake_flavor": "شوكولاتة"}}   # cake_writing missing
        chk = engine.dispatch_check(pack, order)
        self.assertFalse(chk["ok"])
        self.assertEqual([m["key"] for m in chk["missing_inputs"]], ["cake_writing"])

    def test_dispatch_allowed_once_everything_is_in(self):
        pack = P("diamond")
        order = {"final_price_sar": 1600,
                 "inputs": {"phrases": "٨", "occasion": "تخرج", "cake_flavor": "شوكولاتة",
                            "cake_writing": "مبروك التخرج"}}
        self.assertTrue(engine.dispatch_check(pack, order)["ok"])

    def test_dispatch_blocked_until_the_final_price_is_set(self):
        pack = P("bronze")
        order = {"inputs": {"phrases": "٥", "bed_letters": "ن م", "occasion": "زواج"}}
        chk = engine.dispatch_check(pack, order)
        self.assertFalse(chk["ok"])
        self.assertTrue(chk["needs_price"])
        order["final_price_sar"] = 650
        self.assertTrue(engine.dispatch_check(pack, order)["ok"])

    def test_the_ask_message_names_exactly_what_is_missing(self):
        pack = P("bronze")
        miss = engine.missing_inputs(pack, {"occasion": "زواج"})
        self.assertEqual([m["key"] for m in miss], ["phrases", "bed_letters"])
        msg = engine.ask_guest_message(pack, miss)
        self.assertIn("٥ عبارات حسب المناسبة", msg)
        self.assertIn("الأحرف على السرير", msg)
        # `occasion` was already answered, so it is never asked again — but «٥ عبارات حسب
        # المناسبة» legitimately contains the word, so match the bullet, not the substring.
        self.assertNotIn("• المناسبة", msg)

    def test_accept_gap_marks_feature_bound_questions_not_applicable(self):
        """Signature Silver on a unit with no jacuzzi would otherwise wait forever for
        «عبارة الجاكوزي» — a question nobody can answer — and never dispatch."""
        pack = P("signature_silver")
        res = engine.open_check(pack, ["bathtub"], override_kind="accept_gap",
                                overridden_by="نورة", reason="الضيف موافق")
        self.assertIn("jacuzzi_text", res["na_input_keys"])
        order = {"final_price_sar": 1100, "na_input_keys": res["na_input_keys"],
                 "inputs": {"phrases": "٦", "occasion": "عيد ميلاد",
                            "cake_flavor": "فانيلا", "cake_writing": "كل عام وأنت بخير"}}
        self.assertTrue(engine.dispatch_check(pack, order)["ok"])


class TestCake(unittest.TestCase):
    """A late cake and a late decoration are different failures."""

    def test_cake_deadline_is_exactly_24h_before_the_decoration_deadline(self):
        deadline = datetime.datetime(2026, 8, 1, 15, 0)
        task = engine.cake_task_for(P("diamond"), deadline, packs.cake_lead_hours())
        self.assertIsNotNone(task)
        self.assertEqual(task["due_at"], datetime.datetime(2026, 7, 31, 15, 0))
        self.assertEqual(deadline - task["due_at"], datetime.timedelta(hours=24))
        self.assertEqual(engine.deadlines(P("diamond"), deadline)["cake_due"], task["due_at"])

    def test_a_bronze_order_creates_no_cake_subtask(self):
        deadline = datetime.datetime(2026, 8, 1, 15, 0)
        self.assertIsNone(engine.cake_task_for(P("bronze"), deadline))
        self.assertNotIn("cake_due", engine.deadlines(P("bronze"), deadline))
        self.assertFalse(engine.cake_ready(P("bronze"), {"inputs": {}})["applies"])

    def test_every_other_pack_does_create_one(self):
        deadline = datetime.datetime(2026, 8, 1, 15, 0)
        for pid in ("diamond", "signature_silver", "silver", "table_styling"):
            self.assertIsNotNone(engine.cake_task_for(P(pid), deadline), pid)

    def test_the_cake_cannot_be_ordered_before_flavour_and_writing(self):
        pack = P("diamond")
        self.assertEqual(engine.cake_ready(pack, {"inputs": {"cake_flavor": "شوكولاتة"}})["missing"],
                         ["cake_writing"])
        self.assertTrue(engine.cake_ready(
            pack, {"inputs": {"cake_flavor": "شوكولاتة", "cake_writing": "مبروك"}})["ok"])

    def test_work_starts_earlier_by_the_packs_own_setup_time(self):
        deadline = datetime.datetime(2026, 8, 1, 15, 0)
        self.assertEqual(engine.deadlines(P("diamond"), deadline)["work_start"],
                         datetime.datetime(2026, 8, 1, 12, 30))     # 150 minutes
        self.assertEqual(engine.deadlines(P("bronze"), deadline)["work_start"],
                         datetime.datetime(2026, 8, 1, 14, 0))      # 60 minutes


class TestMoney(unittest.TestCase):
    def test_the_starting_from_price_is_never_revenue(self):
        pack = P("diamond")
        m = engine.order_money(pack, {})
        self.assertEqual(m["from_sar"], 1450)
        self.assertEqual(m["final_sar"], 0)
        self.assertFalse(m["counts_as_revenue"])
        m2 = engine.order_money(pack, {"final_price_sar": 1200, "vendor_cost_sar": 700})
        self.assertTrue(m2["counts_as_revenue"])
        self.assertEqual(m2["margin_sar"], 500)


class TestPackFile(unittest.TestCase):
    def test_the_real_file_loads_and_matches_the_guide(self):
        self.assertEqual(len(packs.all_packs()), 5)
        self.assertEqual(packs.cake_lead_hours(), 24)
        self.assertEqual(P("diamond")["price_from_sar"], 1450)
        self.assertFalse(P("bronze")["includes_cake"])
        # the documentation keys in unit_features must never be read as apartments
        self.assertNotIn("_example", packs.seed_unit_features())


if __name__ == "__main__":
    unittest.main()
