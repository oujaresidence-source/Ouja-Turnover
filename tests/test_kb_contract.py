# -*- coding: utf-8 -*-
"""
Contract test — the KB tab's JavaScript must read the SHAPE kb/routes.py returns.

This exists because of a real outage class in this repo: the ERP expense chips rendered
`[object Object]` in front of the owner because the JS read a scalar where the server had
started sending {count, sar}. Nothing in Python or in the browser catches that — only a
test that asserts, key by key, what the front-end dereferences.

If you change a response shape in kb/routes.py, this test fails and points at the exact
line of erp-style drift BEFORE it reaches a screen.
"""

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb import db as kdb        # noqa: E402
from kb import routes as krt    # noqa: E402
from kb import seed as kseed    # noqa: E402


class KBContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        cls._tmp.close()
        kdb.set_db_path(cls._tmp.name)
        kdb.init()
        kseed.seed(force=True)

    @classmethod
    def tearDownClass(cls):
        kdb.set_db_path(None)
        try:
            os.unlink(cls._tmp.name)
        except OSError:
            pass

    def keys(self, d, *names):
        for n in names:
            self.assertIn(n, d, "response is missing '%s' — the tab reads it" % n)

    def test_search_response_shape(self):
        status, r = krt.core_search("الملقا", who="tester")
        self.assertEqual(status, 200)
        self.keys(r, "ok", "count", "units", "owners", "faqs", "counts", "districts")
        self.keys(r["counts"], "units", "owners", "ouja_owned", "gaps", "faqs")
        for d in r["districts"]:
            self.keys(d, "district", "count")
            self.assertIsInstance(d["count"], int)

    def test_unit_card_fields_the_js_dereferences(self):
        _, r = krt.core_search("A11")
        u = r["units"][0]
        self.keys(u, "unit_id", "unit_name", "listing_code", "owner_ar", "district",
                  "district_en", "cleaning_policy", "cleaning_monthly_sar",
                  "payment_cycle", "cycle_ar", "policy_ar", "ouja_owned", "note",
                  "gaps", "is_complete", "conflicts", "updated_by", "last_reviewed")
        # These four are rendered directly into text — an object here prints
        # "[object Object]" on the card.
        for scalar in ("unit_name", "listing_code", "owner_ar", "district"):
            self.assertNotIsInstance(u[scalar], (dict, list))
        self.assertIsInstance(u["gaps"], list)
        self.assertIsInstance(u["conflicts"], list)
        self.assertIsInstance(u["ouja_owned"], bool)

    def test_conflict_shape(self):
        _, r = krt.core_search("473607")
        c = r["units"][0]["conflicts"][0]
        # The card prints c.code and joins c.with_names — both must be renderable as text.
        self.keys(c, "type", "code", "with", "with_names")
        self.assertIsInstance(c["with"], list)
        self.assertTrue(all(isinstance(x, str) for x in c["with"]))
        # The warning must name the unit the way the team says it out loud, not by the
        # internal id: «202B», not «UNT-473607-B».
        self.assertEqual(c["with_names"], ["202B"])

    def test_owner_card_shape(self):
        _, r = krt.core_search("الحربي")
        o = r["owners"][0]
        self.keys(o, "owner_id", "name_ar", "unit_count", "units")
        self.assertIsInstance(o["unit_count"], int)
        for u in o["units"]:
            self.keys(u, "unit_id", "unit_name")

    def test_save_response_shape(self):
        _, r = krt.core_save_unit({"unit_id": "UNT-483841",
                                   "cleaning_monthly_sar": "1075"}, actor="tester")
        self.keys(r, "ok", "changed", "unit", "message")
        self.assertTrue(r["ok"])
        self.assertEqual(r["unit"]["cleaning_monthly_sar"], 1075.0)

    def test_refusal_carries_an_arabic_reason_not_just_false(self):
        """A silent no-op is the worst outcome: the user believes it saved."""
        _, r = krt.core_save_unit({"unit_id": "UNT-483841",
                                   "payment_cycle": "ربع سنوي"}, actor="tester")
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("message"))
        self.assertRegex(r["message"], r"[؀-ۿ]")

    def test_create_response_shape(self):
        _, r = krt.core_save_unit({"unit_name": "CONTRACT-1"}, actor="tester")
        self.keys(r, "ok", "created", "unit", "message")
        self.assertTrue(r["unit"]["unit_id"])
        krt.core_delete_unit({"unit_id": r["unit"]["unit_id"]}, actor="tester")

    def test_unit_detail_and_audit_shape(self):
        krt.core_save_unit({"unit_id": "UNT-483841", "note": "عقد"}, actor="tester")
        status, r = krt.core_unit("UNT-483841")
        self.assertEqual(status, 200)
        self.keys(r, "ok", "unit", "audit")
        a = r["audit"][0]
        self.keys(a, "field", "old_value", "new_value", "changed_by", "changed_at")

    def test_quality_response_shape(self):
        _, r = krt.core_quality()
        self.keys(r, "ok", "quality", "stats")
        q, s = r["quality"], r["stats"]
        self.keys(q, "counts", "missing", "gap_units", "duplicate_codes", "district_variants")
        self.keys(q["missing"], "cleaning", "cycle", "district")
        for k in ("cleaning", "cycle", "district"):
            self.assertIsInstance(q["missing"][k], int)
        for d in q["duplicate_codes"]:
            self.keys(d, "code", "units", "names")
        for g in q["gap_units"]:
            self.keys(g, "unit_id", "unit_name", "gaps")
        self.keys(s, "units_complete_pct", "zero_queries", "top_queries_30d",
                  "searches_7d", "zero_result_searches_7d", "open_questions", "faq_count")
        for z in s["zero_queries"]:
            self.keys(z, "q", "n")

    def test_question_response_shape(self):
        _, r = krt.core_log_question({"text": "مين يدفع نت C3؟"}, actor="tester")
        self.keys(r, "ok", "question_id", "message")

    def test_404s_carry_a_message(self):
        status, r = krt.core_unit("UNT-NOPE")
        self.assertEqual(status, 404)
        self.assertFalse(r["ok"])
        self.assertTrue(r["message"])


class KBWiring(unittest.TestCase):
    """The tab is dead if any one of these is missing, and none of them fail loudly."""

    @classmethod
    def setUpClass(cls):
        import bot
        cls.bot = bot
        cls.html = bot.DASHBOARD_HTML

    def test_nav_item_has_labels_in_both_languages(self):
        nav = self.bot.NAV_DEF
        self.assertIn("kb", [i["id"] for i in nav["items"]])
        self.assertIn("kb", nav["labels"]["ar"])
        self.assertIn("kb", nav["labels"]["en"])

    def test_nav_item_lives_in_a_category(self):
        ids = set()
        for c in self.bot.NAV_DEF["cats"]:
            ids |= set(c["ids"])
        self.assertIn("kb", ids)

    def test_view_section_and_dispatch_exist(self):
        self.assertIn('id="view_kb"', self.html)
        self.assertIn("if(id==='kb') loadKB();", self.html)

    def test_permission_key_is_registered(self):
        self.assertIn("kb", self.bot._USER_TABS)

    def test_reads_and_writes_are_both_gated(self):
        self.assertIn(("/api/kb/", "kb"), self.bot._ROLE_READ_RULES)
        self.assertIn(("/api/kb/", "kb"), self.bot._ROLE_WRITE_RULES)

    def test_no_kb_endpoint_is_write_exempt(self):
        """kb has no public door — nothing may bypass the role middleware."""
        for p in self.bot._ROLE_EXEMPT_WRITES:
            self.assertFalse(p.startswith("/api/kb/"), p)

    def test_embedded_js_has_no_backslash_escapes(self):
        """DASHBOARD_HTML is a normal triple-quoted string: a backslash in the JS is eaten
        by Python and kills the login. Assert the KB block never grew one."""
        m = re.search(r"var KB = \{.*?\nfunction openDrawer\(", self.html, re.S)
        self.assertTrue(m, "the KB javascript block moved — update this test")
        self.assertNotIn("\\", m.group(0))

    def test_every_data_act_the_html_emits_is_handled(self):
        m = re.search(r"var KB = \{.*?\nfunction openDrawer\(", self.html, re.S)
        block = m.group(0)
        emitted = set(re.findall(r"data-act=\"([a-z]+)\"", block))
        # Two listeners: clicks go through kbClick's act ladder, and the district
        # <select> is a change handler. Both count as handled.
        handled = set(re.findall(r"act === '([a-z]+)'", block))
        handled |= set(re.findall(r"data-act'\) === '([a-z]+)'", block))
        self.assertTrue(emitted, "no data-act attributes found")
        self.assertEqual(emitted - handled, set(),
                         "these buttons render but do nothing when clicked")


if __name__ == "__main__":
    unittest.main()
