# -*- coding: utf-8 -*-
"""
«نسبة التنظيف» — a contract-wide alternative to the per-unit monthly operating fee (owner ruling
2026-10-26). The monthly path must stay byte-identical; the pct path routes to its own two
templates, which ship unapproved and carry the approved Article 12 text verbatim.

Run: python3 -m unittest tests.test_aqd_clean_pct
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aqd import catalogue, config, engine, files                      # noqa: E402
from test_aqd_engine import TODAY, ctx, individual, model_b, ok, unit  # noqa: E402
from test_aqd_routes import Base, _Req, answers, body, mb, run         # noqa: E402
from aqd import db, routes                                             # noqa: E402

ART12 = ("<h2 class=\"art\">المادة الثانية عشرة: نسبة التنظيف</h2>\n<ol class=\"p\">\n"
         "<li>يستحق المشغّل نسبة التنظيف المبيّنة في صدر العقد من صافي إيرادات كل حجز يدخل في فترة "
         "المحاسبة، وتقابل: أعمال التنظيف بين الإقامات، واستقبال السياح ومغادرتهم، والتنظيف العميق الدوري "
         "كل (45) يوماً، دون أي مقابل إضافي. ولا تشمل ما تقابله رسوم التنظيف وفق الفقرة (2) من المادة "
         "العاشرة.</li>\n"
         "<li>تُحتسب نسبة التنظيف مع نسبة التشغيل في كشف فترة المحاسبة وتُفوتر معها، ولا تُستحق عن الوحدات "
         "رسوم تشغيل شهرية.</li>\n</ol>")
PCT_T = {"owner": "operating_pct_v2_2", "ouja": "operating_ouja_pct_v2_2"}

# sha256 of the monthly renders BEFORE this feature (fixed answers + fixed date) — any byte that
# moves in a monthly contract fails here.
MONTHLY_SHA = {"operating_v2_2": "8a71d9fae722470e19d84402c4c8922539443f61bb1642aa60bec0ed98a7876b",
               "operating_ouja_v2_2": "0a0bf68599764c68575427ebda11082bbafcc7e3561e7b8880d93d6039306ee6"}


def pct(a_fn=individual, **over):
    return a_fn(fee_model="pct", **over)


def rendered(name, a):
    return engine.render(files.template_text(name), ctx(a))


class TestMonthlyUnchanged(unittest.TestCase):

    def test_monthly_renders_are_byte_identical(self):
        for name, a in (("operating_v2_2", ok(individual())), ("operating_ouja_v2_2", ok(model_b()))):
            out = rendered(name, a)
            self.assertEqual(hashlib.sha256(out.encode()).hexdigest(), MONTHLY_SHA[name], name)

    def test_an_old_draft_without_fee_model_is_monthly(self):
        c = ok(individual())
        self.assertEqual(c["fee_model"], "monthly")
        self.assertEqual(c["units"][0]["monthly_fee"], "1050")
        self.assertNotIn("clean_pct", c)
        self.assertEqual(engine.template_for(c), ("operating_v2_2", None))


class TestPctSurvey(unittest.TestCase):

    def test_unit_fees_are_dropped_and_not_validated(self):
        c = ok(pct(units=[unit(monthly_fee="other", monthly_fee_other=5)]))
        self.assertNotIn("monthly_fee", c["units"][0])
        self.assertNotIn("monthly_fee_other", c["units"][0])
        self.assertEqual(c["clean_pct"], "5")            # the default
        self.assertEqual(catalogue.clean_pct_value(c), 5)

    def test_clean_pct_choices_and_other_bounds(self):
        for v in ("3", "5", "7"):
            self.assertEqual(catalogue.clean_pct_value(ok(pct(clean_pct=v))), int(v))
        self.assertEqual(catalogue.clean_pct_value(ok(pct(clean_pct="other", clean_pct_other=2.5))), 2.5)
        for bad in (0, 16, 2.3, "abc"):
            _c, errs = catalogue.validate(pct(clean_pct="other", clean_pct_other=bad), TODAY)
            self.assertIn("clean_pct_other", errs, bad)
        _c, errs = catalogue.validate(pct(clean_pct="9"), TODAY)
        self.assertIn("clean_pct", errs)

    def test_clean_pct_is_hidden_on_monthly(self):
        c = ok(individual(clean_pct="7"))
        self.assertNotIn("clean_pct", c)
        self.assertIsNone(catalogue.clean_pct_value(c))


class TestPctRouting(unittest.TestCase):

    def test_routes_to_the_pct_templates(self):
        self.assertEqual(engine.template_for(ok(pct())), (PCT_T["owner"], None))
        self.assertEqual(engine.template_for(ok(pct(model_b))), (PCT_T["ouja"], None))

    def test_template_override_never_touches_the_pct_route(self):
        os.environ["AQD_TEMPLATE"] = "operating_v2_1"
        try:
            self.assertEqual(engine.template_for(ok(pct())), (PCT_T["owner"], None))
        finally:
            del os.environ["AQD_TEMPLATE"]

    def test_fits_only_within_one_fee_model(self):
        self.assertTrue(engine.template_fits(ok(pct()), PCT_T["owner"]))
        self.assertFalse(engine.template_fits(ok(pct()), "operating_v2_2"))
        self.assertFalse(engine.template_fits(ok(individual()), PCT_T["owner"]))
        self.assertFalse(engine.template_fits(ok(pct(model_b)), PCT_T["owner"]))
        self.assertTrue(engine.template_fits(ok(individual()), "operating_v2_1"))

    def test_config_knows_the_two_templates(self):
        for model, name in PCT_T.items():
            self.assertIn(name, config.known_templates())
            self.assertIn(name, config.active_templates())
            self.assertEqual(config.template_model(name), model)
            self.assertEqual(config.template_fee_model(name), "pct")
            self.assertEqual(config.template_version(name), "2.2")
        self.assertEqual(config.template_fee_model("operating_v2_2"), "monthly")
        self.assertEqual(config.template_label(PCT_T["owner"]), "نموذج (أ) — حساب المالك 2.2 — نسبة تنظيف")
        self.assertEqual(config.template_label(PCT_T["ouja"]), "نموذج (ب) — حساب عوجا 2.2 — نسبة تنظيف")


class TestPctRender(unittest.TestCase):

    def test_text_edits_in_both_templates(self):
        for model, a_fn in (("owner", individual), ("ouja", model_b)):
            out = rendered(PCT_T[model], ok(pct(a_fn)))
            self.assertNotIn("{{", out)
            self.assertIn("23% ثابتة من صافي الإيرادات + نسبة التنظيف 5% من صافي الإيرادات", out)
            self.assertIn(ART12, out)
            self.assertIn("وهي غير ما تقابله نسبة التنظيف وفق الفقرة (1) من المادة الثانية عشرة", out)
            self.assertIn("تستحق للمشغّل نسبة التنظيف المبيّنة في صدر العقد من صافي إيرادات كل حجز "
                          "وفق المادة الثانية عشرة", out)
            self.assertIn("ونسبة التشغيل، ونسبة التنظيف، ورسوم التنظيف،", out)
            self.assertIn("(نسبة التشغيل ونسبة التنظيف) عن كل يوم متبقٍ", out)
            self.assertIn("(صافي الإيرادات بعد نسبة التشغيل ونسبة التنظيف) عن كل يوم متبقٍ", out)
            self.assertIn("<tr><td>نسبة التنظيف (5%)</td><td></td><td>—</td></tr>", out)
            self.assertNotIn("رسوم التشغيل الشهرية", out, model)
            self.assertEqual(out.count("رسوم تشغيل شهرية"), 1)
            # D4: the personal-use overage clause is untouched — operating share only
            self.assertIn("يستحق عنه للمشغّل نسبة التشغيل محسوبة على الحد الأدنى لسعر الليلة", out)
            # D3: the guest's cleaning fee still belongs to the operator
            self.assertIn("تستحق للمشغّل رسوم التنظيف التي يدفعها السائح عبر منصة الحجز", out)
        b = rendered(PCT_T["ouja"], ok(pct(model_b)))
        self.assertIn("وفق المادة الثانية عشرة، والمصروفات المؤيدة بفواتيرها وفق المادة الثالثة عشرة.", b)

    def test_units_table_has_eight_columns(self):
        a = ok(pct(units_count="2", units=[unit(), unit()]))
        rows = engine.unit_rows(a)
        self.assertEqual(rows.count("<td>"), 16)
        self.assertNotIn("ريال</td><td>450", rows)
        out = rendered(PCT_T["owner"], a)
        head = out[out.index("<thead><tr><th>الوحدة"):]
        head = head[:head.index("</thead>")]
        self.assertEqual(head.count("<th>"), 8)

    def test_only_the_clean_pct_placeholder_is_new(self):
        a = set(engine.PLACEHOLDER.findall(files.template_text(PCT_T["owner"])))
        b = set(engine.PLACEHOLDER.findall(files.template_text(PCT_T["ouja"])))
        self.assertEqual(a, set(engine.KEYS) | {"clean_pct"})
        self.assertEqual(b, a | {"payout_period"})

    def test_other_pct_prints_half_steps(self):
        out = rendered(PCT_T["owner"], ok(pct(clean_pct="other", clean_pct_other=4.5)))
        self.assertIn("نسبة التنظيف 4.5% من صافي الإيرادات", out)


class TestPctRoutes(Base):

    def test_send_freezes_on_the_pct_template_and_signing_waits_for_its_approval(self):
        cid = self.save(answers(fee_model="pct", clean_pct="7"))
        self.send(cid)
        c = db.get(cid)
        self.assertEqual((c["template_name"], c["template_version"]), (PCT_T["owner"], "2.2"))
        self.assertIn("نسبة التنظيف 7%", files.read_text(cid, "frozen.html"))
        self.approve("operating_v2_2")            # approving the monthly text does not open pct
        self.assertFalse(routes.is_approved(PCT_T["owner"]))
        tok = self.token(cid)
        v = self.verify(tok)
        r = self.sign(tok, v["view_key"])
        self.assertFalse(r["ok"])
        self.assertIn("قيد المراجعة القانونية", r["error"])
        self.approve(PCT_T["owner"])
        self.assertTrue(self.sign(tok, v["view_key"])["ok"])

    def test_model_b_pct_sends_on_its_own_template(self):
        cid = self.save(mb(fee_model="pct"))
        self.send(cid)
        self.assertEqual(db.get(cid)["template_name"], PCT_T["ouja"])

    def test_preview_and_summary_carry_the_clean_pct(self):
        r = body(run(routes.api_preview(_Req({"answers": answers(fee_model="pct")}))))
        self.assertEqual(r["blockers"], [])
        self.assertIn("نسبة التنظيف 5%", r["html"])
        cid = self.save(answers(fee_model="pct", clean_pct="3"))
        self.send(cid)
        _st, g = routes.core_public_get(self.token(cid))
        self.assertEqual(g["clean_pct"], 3)

    def test_monthly_summary_has_no_clean_pct(self):
        cid = self.save()
        self.send(cid)
        _st, g = routes.core_public_get(self.token(cid))
        self.assertIsNone(g["clean_pct"])


if __name__ == "__main__":
    unittest.main()
