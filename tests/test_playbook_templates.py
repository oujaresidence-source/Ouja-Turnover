# -*- coding: utf-8 -*-
"""Meta/Karzoun template catalogue — the 20 owner-approved WhatsApp templates in brain.playbook.

Validates the SHAPE Meta/Karzoun requires (no network, no DB): every campaign carries non-empty
bilingual copy within WhatsApp's length limits, bodies never start/end on a bare variable, the two
F1/F2 protected campaigns carry zero price-cut wording, and the template-export CSV has the exact
columns + both utility variants (~44 rows).
"""
import csv
import io
import re
import unittest

from brain import playbook

VAR = re.compile(r"\{\{[1-5]\}\}")            # a Karzoun variable token


def _bodies(block):
    return (block or {}).get("body", "")


class CatalogueShape(unittest.TestCase):
    def test_exactly_twenty_campaigns(self):
        self.assertEqual(len(playbook.CAMPAIGNS), 20)

    def test_every_campaign_has_nonempty_bilingual_copy(self):
        for code, c in playbook.CAMPAIGNS.items():
            ar, en = c.get("ar") or {}, c.get("en") or {}
            self.assertTrue(_bodies(ar).strip(), "%s: empty ar.body" % code)
            self.assertTrue(_bodies(en).strip(), "%s: empty en.body" % code)
            self.assertTrue(c.get("template_name"), "%s: no template_name" % code)
            self.assertIn(c.get("category"), ("MARKETING", "UTILITY"))

    def test_bodies_never_start_or_end_on_a_variable(self):
        for code, c in playbook.CAMPAIGNS.items():
            for lang in ("ar", "en"):
                body = _bodies(c.get(lang)).strip()
                self.assertFalse(body.startswith("{{"), "%s/%s body starts on a variable" % (code, lang))
                self.assertFalse(body.endswith("}}"), "%s/%s body ends on a variable" % (code, lang))

    def test_meta_length_limits(self):
        # WhatsApp/Meta caps: body ≤1024, header ≤60, footer ≤60, button ≤20.
        for code, c in playbook.CAMPAIGNS.items():
            for lang in ("ar", "en"):
                b = c.get(lang) or {}
                self.assertLessEqual(len(b.get("body") or ""), 1024, "%s/%s body too long" % (code, lang))
                self.assertLessEqual(len(b.get("header") or ""), 60, "%s/%s header too long" % (code, lang))
                self.assertLessEqual(len(b.get("footer") or ""), 60, "%s/%s footer too long" % (code, lang))
                self.assertLessEqual(len(b.get("button") or ""), 20, "%s/%s button too long" % (code, lang))

    def test_at_least_one_variable_per_body(self):
        for code, c in playbook.CAMPAIGNS.items():
            for lang in ("ar", "en"):
                self.assertTrue(VAR.search(_bodies(c.get(lang))), "%s/%s has no variable" % (code, lang))


class ProtectedNoPriceCut(unittest.TestCase):
    # F1/F2 protected templates: access/upgrade ONLY — never a discount.
    FORBIDDEN_AR = ["خصم", "تخفيض", "نسبة", "أرخص", "تنزيل", "٪", "%"]
    FORBIDDEN_EN = ["discount", "cheaper", "price cut", "% off", "percent off", "sale", "%"]

    def test_upgrade_and_turaif_have_no_discount_words(self):
        for code in ("UPGRADE-MIDWEEK", "TURAIF-MIDWEEK"):
            c = playbook.CAMPAIGNS[code]
            self.assertTrue(c.get("protected"), "%s should be protected=True" % code)
            ar = _bodies(c.get("ar"))
            en = _bodies(c.get("en")).lower()
            for w in self.FORBIDDEN_AR:
                self.assertNotIn(w, ar, "%s AR body contains forbidden '%s'" % (code, w))
            for w in self.FORBIDDEN_EN:
                self.assertNotIn(w, en, "%s EN body contains forbidden '%s'" % (code, w))


class TemplateExportCsv(unittest.TestCase):
    def _rows(self):
        fn, text = playbook.build_templates_csv()
        self.assertEqual(fn, "ouja_meta_templates.csv")
        return list(csv.reader(io.StringIO(text)))

    def test_columns_exact(self):
        rows = self._rows()
        self.assertEqual(rows[0], playbook.TEMPLATE_CSV_COLUMNS)
        self.assertEqual(rows[0], ["template_name", "category", "language", "header", "body",
                                   "footer", "button", "sample_values", "approval_note"])

    def test_row_count_includes_both_languages_and_both_utility_variants(self):
        body = self._rows()[1:]
        # 20 campaigns × 2 langs (Marketing) + 2 utility campaigns × 2 langs = 44
        self.assertEqual(len(body), 44)
        util = [r for r in body if r[1] == "UTILITY"]
        names = {r[0] for r in util}
        self.assertEqual(names, {"post_checkout_thanks", "review_specific_stay"})
        self.assertEqual(len(util), 4)                       # both langs of both utility variants
        langs = sorted(r[2] for r in util)
        self.assertEqual(langs, ["ar", "ar", "en", "en"])

    def test_variables_left_intact_in_export(self):
        # the export is the ONE-TIME submission text — variables must stay {{n}}, never merged
        for r in self._rows()[1:]:
            self.assertTrue(VAR.search(r[4]), "exported body has no variable: %s" % r[:3])


if __name__ == "__main__":
    unittest.main()
