# -*- coding: utf-8 -*-
"""Elite v5 campaign catalogue — the 20 link-driven WhatsApp templates in brain.playbook.

Validates the SHAPE Meta/Karzoun requires (no network, no DB): every campaign carries non-empty
bilingual copy within WhatsApp's length limits, the ONLY variable is {{1}} (no unit/date/extra
variable ever), every CTA is the same /elite URL, and the template-export CSV has the exact v5
columns with the variable left intact (40 rows).
"""
import csv
import io
import re
import unittest

from brain import playbook

VAR1 = re.compile(r"\{\{1\}\}")
BAD_TOKEN = re.compile(r"\{\{[2-9]\}\}|\{unit\}|\{dates?\}|\{date_in\}|\{date_out\}|\{wd\}|\{name\}")


def _body(c, lang):
    return ((c.get(lang) or {}).get("body")) or ""


class CatalogueShape(unittest.TestCase):
    def test_exactly_twenty_campaigns(self):
        self.assertEqual(len(playbook.CAMPAIGNS), 20)

    def test_every_campaign_nonempty_bilingual(self):
        for code, c in playbook.CAMPAIGNS.items():
            self.assertTrue(_body(c, "ar").strip(), "%s empty ar.body" % code)
            self.assertTrue(_body(c, "en").strip(), "%s empty en.body" % code)
            self.assertTrue(c.get("template_name"), "%s no template_name" % code)
            self.assertEqual(c.get("category"), "MARKETING")
            self.assertTrue(c.get("trigger"), "%s no trigger text" % code)

    def test_bodies_never_start_or_end_on_a_variable(self):
        for code, c in playbook.CAMPAIGNS.items():
            for lang in ("ar", "en"):
                b = _body(c, lang).strip()
                self.assertFalse(b.startswith("{{"), "%s/%s starts on a variable" % (code, lang))
                self.assertFalse(b.endswith("}}"), "%s/%s ends on a variable" % (code, lang))

    def test_meta_length_limits(self):
        for code, c in playbook.CAMPAIGNS.items():
            btn = c.get("button") or {}
            for lang in ("ar", "en"):
                blk = c.get(lang) or {}
                self.assertLessEqual(len(blk.get("body") or ""), 1024, "%s/%s body too long" % (code, lang))
                self.assertLessEqual(len(blk.get("header") or ""), 60, "%s/%s header too long" % (code, lang))
                self.assertLessEqual(len(c.get("footer_%s" % lang) or ""), 60, "%s/%s footer too long" % (code, lang))
                self.assertLessEqual(len(btn.get("text_%s" % lang) or ""), 20, "%s/%s button too long" % (code, lang))


class LinkDrivenAndVagueOnly(unittest.TestCase):
    def test_only_variable_is_first_name(self):
        for code, c in playbook.CAMPAIGNS.items():
            for lang in ("ar", "en"):
                b = _body(c, lang)
                self.assertTrue(VAR1.search(b), "%s/%s missing {{1}}" % (code, lang))
                self.assertIsNone(BAD_TOKEN.search(b),
                                  "%s/%s names a unit/date or an extra variable" % (code, lang))

    def test_every_cta_is_the_elite_url(self):
        for code, c in playbook.CAMPAIGNS.items():
            self.assertEqual(playbook.button_url(code), playbook.ELITE_URL, "%s CTA != /elite" % code)
            self.assertEqual((c.get("button") or {}).get("type"), "URL", "%s button not URL" % code)

    def test_assembled_message_keeps_name_var_and_elite_link(self):
        for code in playbook.CODES:
            for lang in ("ar", "en"):
                msg = playbook.assembled_message(code, lang)
                self.assertIn("{{1}}", msg)
                self.assertIn(playbook.ELITE_URL, msg)
                self.assertIsNone(BAD_TOKEN.search(msg), "%s/%s assembled names unit/date" % (code, lang))


class TemplateExportCsv(unittest.TestCase):
    def _rows(self):
        fn, text = playbook.build_templates_csv()
        self.assertEqual(fn, "ouja_elite_templates.csv")
        return list(csv.reader(io.StringIO(text)))

    def test_columns_exact(self):
        rows = self._rows()
        self.assertEqual(rows[0], playbook.TEMPLATE_CSV_COLUMNS)
        self.assertEqual(rows[0], ["template_name", "category", "language", "header", "body",
                                   "footer", "button_text", "button_url", "trigger"])

    def test_forty_rows_both_languages(self):
        body = self._rows()[1:]
        self.assertEqual(len(body), 40)                      # 20 campaigns × 2 languages
        langs = sorted(set(r[2] for r in body))
        self.assertEqual(langs, ["ar", "en"])

    def test_variable_intact_and_url_present(self):
        for r in self._rows()[1:]:
            self.assertTrue(VAR1.search(r[4]), "exported body lost {{1}}: %s" % r[:3])
            self.assertEqual(r[7], playbook.ELITE_URL)       # button_url column


if __name__ == "__main__":
    unittest.main()
