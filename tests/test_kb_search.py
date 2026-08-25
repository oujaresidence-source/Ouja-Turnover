# -*- coding: utf-8 -*-
"""
Acceptance tests for «قاعدة المعرفة» — every query in the handoff brief §6, plus the
completeness rule, the audit trail and the conflict surface.

These are the contract. If a search change regresses one of these, the Arabic
normalisation in kb/engine.py has drifted — that is the first place to look.

No web server: the tests drive kb.db + kb.engine directly against a temp SQLite file.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb import db as kdb           # noqa: E402
from kb import engine as keng      # noqa: E402
from kb import seed as kseed       # noqa: E402


class KBBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        cls._tmp.close()
        kdb.set_db_path(cls._tmp.name)
        kdb.init()
        cls.seeded = kseed.seed(force=True)

    @classmethod
    def tearDownClass(cls):
        kdb.set_db_path(None)
        try:
            os.unlink(cls._tmp.name)
        except OSError:
            pass

    def names(self, q, **kw):
        return sorted(u["unit_name"] for u in kdb.search(q, **kw)["units"])

    def ids(self, q, **kw):
        return sorted(u["unit_id"] for u in kdb.search(q, **kw)["units"])


class TestSeed(KBBase):
    def test_counts(self):
        """56 units, 35 owners — the handoff's own totals."""
        self.assertEqual(self.seeded["units"], 56)
        self.assertEqual(self.seeded["owners"], 35)

    def test_seed_is_idempotent(self):
        again = kseed.seed(force=True)
        self.assertEqual(again["units"], 56)
        self.assertEqual(kdb.counts()["units"], 56)

    def test_ouja_owned_count(self):
        self.assertEqual(kdb.counts()["ouja_owned"], 8)


class TestAcceptanceQueries(KBBase):
    """Handoff brief §6 — the eight queries that must work."""

    def test_a11_by_name(self):
        r = kdb.search("A11")
        self.assertIn("A11", [u["unit_name"] for u in r["units"]])
        u = [x for x in r["units"] if x["unit_name"] == "A11"][0]
        self.assertEqual(u["owner_ar"], "هلا الصيخان")
        self.assertEqual(u["cleaning_policy"], "owner")
        self.assertEqual(u["cleaning_monthly_sar"], 1050.0)
        self.assertEqual(u["payment_cycle"], "biweekly_quarter_month")

    def test_a11_by_listing_code(self):
        self.assertIn("A11", self.names("483841"))

    def test_al_malqa_arabic_all_three_spellings(self):
        base = self.ids("الملقا")
        self.assertEqual(len(base), 9, "الملقا should return all 9 units")
        for variant in ("الملقى", "المقى"):
            self.assertEqual(self.ids(variant), base, "variant %s folded differently" % variant)

    def test_al_malqa_english(self):
        self.assertEqual(self.ids("Al Malqa"), self.ids("الملقا"))

    def test_owner_alharbi_and_his_four_units(self):
        r = kdb.search("الحربي")
        self.assertEqual(sorted(u["unit_name"] for u in r["units"]),
                         sorted(["C3", "B02", "B10", "B03"]))
        self.assertTrue(any(o["name_ar"] == "عبدالله الحربي" for o in r["owners"]),
                        "an owner with 4 units must surface his own card")

    def test_abu_fahad_eight_units(self):
        r = kdb.search("ابو فهد")
        self.assertEqual(len(r["units"]), 8)
        self.assertTrue(any(o["unit_count"] == 8 for o in r["owners"]))

    def test_hue(self):
        self.assertEqual(self.names("hue"), sorted(["HUE 9", "HUE 103", "HUE 202"]))

    def test_duplicate_code_returns_both_with_a_conflict(self):
        r = kdb.search("473607")
        self.assertEqual(sorted(u["unit_id"] for u in r["units"]),
                         sorted(["UNT-473607", "UNT-473607-B"]))
        for u in r["units"]:
            self.assertTrue(u["conflicts"], "a duplicate listing code must be visible on the card")
            self.assertEqual(u["conflicts"][0]["type"], "duplicate_listing_code")


class TestSearchBehaviour(KBBase):
    def test_every_token_must_match(self):
        """«ابو فهد 101» narrows to his 101 units, it does not widen to all eight."""
        wide = kdb.search("ابو فهد")["units"]
        narrow = kdb.search("ابو فهد 101")["units"]
        self.assertLess(len(narrow), len(wide))
        self.assertTrue(all("101" in u["unit_name"] for u in narrow))

    def test_substring_from_the_middle(self):
        """Not prefix matching — people type the fragment they remember."""
        self.assertTrue(kdb.search("ملقا")["units"])

    def test_space_stripped_name(self):
        self.assertIn("HUE 202", self.names("hue202"))

    def test_single_unit_owner_is_not_echoed_as_an_owner_card(self):
        for o in kdb.search("A11")["owners"]:
            self.assertGreater(o["unit_count"], 1)

    def test_empty_query_returns_everything(self):
        self.assertEqual(len(kdb.search("")["units"]), 56)

    def test_nonsense_returns_nothing_and_still_answers(self):
        r = kdb.search("زقزقزق")
        self.assertEqual(r["units"], [])
        self.assertEqual(r["count"], 0)


class TestFilters(KBBase):
    def test_gaps_filter_matches_the_completeness_rule(self):
        got = {u["unit_id"] for u in kdb.search("", gaps=True)["units"]}
        want = {u["unit_id"] for u in kdb.all_units() if not keng.is_complete(u)}
        self.assertEqual(got, want)
        self.assertTrue(want)

    def test_ouja_filter(self):
        for u in kdb.search("", owned="ouja")["units"]:
            self.assertTrue(u["ouja_owned"])
        for u in kdb.search("", owned="inv")["units"]:
            self.assertFalse(u["ouja_owned"])

    def test_district_filter(self):
        for u in kdb.search("", district="الملقا")["units"]:
            self.assertEqual(u["district"], "الملقا")


class TestCompletenessRule(KBBase):
    def test_ouja_owned_is_always_complete(self):
        self.assertTrue(keng.is_complete({"ouja_owned": 1}))

    def test_policy_owner_without_amount_is_a_gap(self):
        u = {"district": "الملقا", "payment_cycle": "monthly", "cleaning_policy": "owner"}
        self.assertIn(keng.GAP_CLEANING, keng.gaps(u))
        u["cleaning_monthly_sar"] = 1100
        self.assertEqual(keng.gaps(u), [])

    def test_policy_ouja_needs_no_amount(self):
        self.assertEqual(keng.gaps({"district": "حطين", "payment_cycle": "monthly",
                                    "cleaning_policy": "ouja"}), [])

    def test_missing_district_and_cycle_are_named_separately(self):
        self.assertEqual(sorted(keng.gaps({"cleaning_policy": "ouja"})),
                         sorted([keng.GAP_DISTRICT, keng.GAP_CYCLE]))


class TestFold(KBBase):
    def test_hamza_and_alef_forms_collapse(self):
        self.assertEqual(keng.fold("أحمد"), keng.fold("احمد"))
        self.assertEqual(keng.fold("إبراهيم"), keng.fold("ابراهيم"))

    def test_ta_marbuta_and_alef_maqsura(self):
        self.assertEqual(keng.fold("قرطبة"), keng.fold("قرطبه"))
        self.assertEqual(keng.fold("الملقى"), keng.fold("الملقي"))

    def test_case_and_whitespace(self):
        self.assertEqual(keng.fold("  Al   Malqa "), "al malqa")


class TestWrites(KBBase):
    def test_edit_writes_audit_and_reindexes(self):
        before = len(kdb.audit_for("unit", "UNT-483841"))
        ok, err = kdb.update_unit("UNT-483841", {"cleaning_monthly_sar": 1234},
                                  actor="tester")
        self.assertIsNone(err)
        self.assertTrue(ok)
        rows = kdb.audit_for("unit", "UNT-483841")
        self.assertEqual(len(rows), before + 1)
        self.assertEqual(rows[0]["field"], "cleaning_monthly_sar")
        self.assertEqual(rows[0]["new_value"], "1234.0")
        self.assertEqual(rows[0]["changed_by"], "tester")
        self.assertEqual(kdb.unit("UNT-483841")["cleaning_monthly_sar"], 1234.0)
        kdb.update_unit("UNT-483841", {"cleaning_monthly_sar": 1050}, actor="tester")

    def test_edit_reindexes_the_haystack(self):
        kdb.update_unit("UNT-483841", {"note": "زقزقة"}, actor="tester")
        self.assertIn("A11", [u["unit_name"] for u in kdb.search("زقزقة")["units"]])
        kdb.update_unit("UNT-483841", {"note": None}, actor="tester")
        self.assertEqual(kdb.search("زقزقة")["units"], [])

    def test_free_text_payment_cycle_is_refused(self):
        ok, err = kdb.update_unit("UNT-483841", {"payment_cycle": "ربع شهري"}, actor="t")
        self.assertFalse(ok)
        self.assertTrue(err)
        self.assertEqual(kdb.unit("UNT-483841")["payment_cycle"], "biweekly_quarter_month")

    def test_amount_against_ouja_policy_is_refused(self):
        ok, err = kdb.update_unit("UNT-407535", {"cleaning_monthly_sar": 900}, actor="t")
        self.assertFalse(ok)
        self.assertTrue(err)

    def test_owner_policy_without_amount_saves_as_a_visible_gap(self):
        ok, err = kdb.update_unit("UNT-483841", {"cleaning_policy": "owner",
                                                 "cleaning_monthly_sar": None}, actor="t")
        self.assertIsNone(err)
        self.assertIn(keng.GAP_CLEANING, kdb.unit("UNT-483841")["gaps"])
        kdb.update_unit("UNT-483841", {"cleaning_monthly_sar": 1050}, actor="t")

    def test_unchanged_value_writes_no_audit_row(self):
        before = len(kdb.audit_for("unit", "UNT-483841"))
        kdb.update_unit("UNT-483841", {"cleaning_monthly_sar": 1050}, actor="t")
        self.assertEqual(len(kdb.audit_for("unit", "UNT-483841")), before)

    def test_create_unit_is_searchable_immediately(self):
        uid, err = kdb.create_unit({"unit_name": "TEST-99", "district": "الملقا",
                                    "payment_cycle": "monthly", "cleaning_policy": "ouja"},
                                   actor="tester")
        self.assertIsNone(err)
        self.assertIn("TEST-99", [u["unit_name"] for u in kdb.search("TEST-99")["units"]])
        self.assertTrue(kdb.audit_for("unit", uid))
        kdb.soft_delete_unit(uid, actor="tester")
        self.assertEqual(kdb.search("TEST-99")["units"], [])

    def test_create_requires_a_name(self):
        uid, err = kdb.create_unit({"unit_name": "  "}, actor="t")
        self.assertIsNone(uid)
        self.assertTrue(err)

    def test_delete_is_soft_and_reversible(self):
        uid, _ = kdb.create_unit({"unit_name": "TEST-SOFT"}, actor="t")
        kdb.soft_delete_unit(uid, actor="t")
        self.assertEqual(kdb.unit(uid)["is_active"], 0)
        self.assertTrue(kdb.audit_for("unit", uid))


class TestQuestions(KBBase):
    def test_logged_question_lands_in_the_open_queue(self):
        qid = kdb.log_question("مين يدفع نت شقة C3؟", asked_by="aseel")
        openq = [q for q in kdb.questions("open") if q["question_id"] == qid]
        self.assertEqual(len(openq), 1)
        self.assertEqual(openq[0]["status"], "open")

    def test_resolving_a_question_removes_it_from_open(self):
        qid = kdb.log_question("سؤال ثاني", asked_by="t")
        kdb.resolve_question(qid, status="answered", actor="t")
        self.assertNotIn(qid, [q["question_id"] for q in kdb.questions("open")])


class TestQualityAndStats(KBBase):
    def test_quality_is_computed_live_not_cached(self):
        q = kdb.quality()
        self.assertEqual(len(q["duplicate_codes"]), 2)
        codes = sorted(d["code"] for d in q["duplicate_codes"])
        self.assertEqual(codes, ["367749", "473607"])
        before = q["missing"]["cleaning"]
        target = [u for u in kdb.all_units()
                  if keng.GAP_CLEANING in keng.gaps(u) and not u["ouja_owned"]][0]
        kdb.update_unit(target["unit_id"], {"cleaning_policy": "ouja"}, actor="t")
        self.assertEqual(kdb.quality()["missing"]["cleaning"], before - 1)
        kdb.update_unit(target["unit_id"], {"cleaning_policy": None}, actor="t")

    def test_search_is_logged_and_zero_results_are_findable(self):
        kdb.search("زقزقزقزق", log_as="tester")
        zeros = [z["q"] for z in kdb.stats()["zero_queries"]]
        self.assertIn("زقزقزقزق", zeros)

    def test_stats_shape(self):
        s = kdb.stats()
        for k in ("searches_7d", "zero_result_searches_7d", "open_questions",
                  "units_complete_pct", "faq_count", "top_queries_30d"):
            self.assertIn(k, s)


class TestFaqs(KBBase):
    def test_faq_is_searchable_and_soft_deletes(self):
        fid, err = kdb.create_faq({"q_ar": "كيف نتعامل مع ضريبة رسوم الإدارة؟",
                                   "a_ar": "الرسوم عليها ١٥٪ ضريبة قيمة مضافة."},
                                  actor="t")
        self.assertIsNone(err)
        self.assertTrue(kdb.search("ضريبة")["faqs"])
        kdb.soft_delete_faq(fid, actor="t")
        self.assertEqual(kdb.search("ضريبة")["faqs"], [])


if __name__ == "__main__":
    unittest.main()
