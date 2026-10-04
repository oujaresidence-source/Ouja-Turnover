# -*- coding: utf-8 -*-
"""
«العقود» — the pure rules: the survey catalogue, the owner grammar, the units table, the
single-pass render, the hash, and the state machine.

Fake ID numbers are built by concatenation so permits/tools_privacy_scan.py stays green.
Run: python3 -m unittest tests.test_aqd_engine
"""

import copy
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aqd import catalogue, engine, files                              # noqa: E402

TODAY = datetime.date(2026, 10, 4)
CREATED = datetime.datetime(2026, 10, 4, 10, 30)
NID = "1" + "23456" + "7890"
IQAMA = "2" + "23456" + "7891"
AGENT = "1" + "98765" + "4321"
CR = "1" + "01012" + "3456"


def unit(**over):
    u = {"city": "riyadh", "district": "الملقا", "unit_type": "apartment", "bedrooms": "2",
         "deed_no": "310112233", "licence_status": "issued", "licence_no": "50035533",
         "licence_expiry": "2027-05-01", "monthly_fee": "1050", "min_price": 450,
         "blocked": "none", "delivery_date": "2026-10-20"}
    u.update(over)
    return u


def individual(**over):
    a = {"client_kind": "individual", "gender": "m", "id_type": "nid",
         "full_name": "عبدالله بن محمد بن سعد الشمري", "id_number": NID, "signer": "self",
         "mobile": "0555123456", "email": "", "nat_address": "",
         "vat_registered": "no", "units_count": "1", "same_property": "no", "units": [unit()],
         "jamiya": "none", "furnishing": "ready", "airbnb_account": "owner_has",
         "op_pct": "23", "send_via": "whatsapp"}
    a.update(over)
    return a


def company(**over):
    a = individual(client_kind="company", company_name="شركة الأفق العقارية", cr_number=CR,
                   rep_name="سعد الدوسري", rep_capacity="manager")
    for k in ("gender", "id_type", "full_name", "id_number", "signer"):
        a.pop(k, None)
    a.update(over)
    return a


def ok(a):
    clean, errs = catalogue.validate(a, TODAY)
    assert not errs, errs
    return clean


SETTINGS = {"op_rep_name": "فيصل", "op_wakala_no": "445566", "op_wakala_date": "01/01/2026م",
            "op_fal_no": "x", "op_fal_expiry": "y", "op_cr_expiry": "z",
            "platform_proof": "p", "brand_name": "عوجا", "brand_reg": "r"}


def ctx(a, frozen=True, approved=False, ref="OUJA-CT-2026-0001"):
    return engine.build_context(a, ref=ref, created=CREATED, settings=SETTINGS,
                                font_css="/*fonts*/", contract_css="/*css*/",
                                template_version="2.1", approved=approved, frozen=frozen)


def render(a, **kw):
    return engine.render(files.template_text("operating_v2_1"), ctx(a, **kw))


class TestCatalogueRules(unittest.TestCase):

    def test_id_number_rules_per_id_type(self):
        cases = [("nid", NID, True), ("nid", IQAMA, False), ("nid", NID[:9], False),
                 ("iqama", IQAMA, True), ("iqama", NID, False),
                 ("other", "P1234567", True), ("other", "A12", False), ("other", "AB_12345", False), ("other", "AB-12345", True)]
        for idt, val, good in cases:
            _c, errs = catalogue.validate(individual(id_type=idt, id_number=val), TODAY)
            self.assertEqual("id_number" not in errs, good, (idt, val, errs))

    def test_arabic_indic_digits_are_accepted(self):
        ar = NID.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
        c = ok(individual(id_number=ar))
        self.assertEqual(c["id_number"], NID)

    def test_vat_must_be_15_digits_starting_and_ending_with_3(self):
        good = "3" + "0" * 13 + "3"
        self.assertEqual(ok(individual(vat_registered="yes", vat_number=good))["vat_number"], good)
        for bad in ("3" + "0" * 13 + "4", "2" + "0" * 13 + "3", "3" + "0" * 12 + "3"):
            _c, errs = catalogue.validate(individual(vat_registered="yes", vat_number=bad), TODAY)
            self.assertIn("vat_number", errs, bad)
        # hidden when not registered: no error even when blank
        self.assertNotIn("vat_number", ok(individual()))

    def test_mobile_is_normalised(self):
        for raw in ("0555123456", "+966555123456", "966555123456", "00966555123456", "055 512 3456"):
            self.assertEqual(ok(individual(mobile=raw))["mobile"], "+966555123456", raw)
        _c, errs = catalogue.validate(individual(mobile="0455123456"), TODAY)
        self.assertIn("mobile", errs)

    def test_optional_fields_validate_only_when_filled(self):
        self.assertEqual(ok(individual(nat_address="rrrd 2929"))["nat_address"], "RRRD2929")
        _c, errs = catalogue.validate(individual(nat_address="RR2929"), TODAY)
        self.assertIn("nat_address", errs)
        _c, errs = catalogue.validate(individual(email="not-an-email"), TODAY)
        self.assertIn("email", errs)

    def test_full_name_needs_three_words(self):
        _c, errs = catalogue.validate(individual(full_name="عبدالله الشمري"), TODAY)
        self.assertIn("full_name", errs)

    def test_company_fields_and_cr(self):
        c = ok(company())
        self.assertNotIn("full_name", c)
        _c, errs = catalogue.validate(company(cr_number="12345"), TODAY)
        self.assertIn("cr_number", errs)
        _c, errs = catalogue.validate(company(rep_capacity="authorized"), TODAY)
        self.assertIn("auth_ref", errs)

    def test_agent_fields_required_only_for_agent(self):
        _c, errs = catalogue.validate(individual(signer="agent"), TODAY)
        for k in ("agent_name", "agent_id", "wakala_no", "wakala_date"):
            self.assertIn(k, errs)

    def test_unit_rules(self):
        _c, errs = catalogue.validate(individual(units=[unit(delivery_date="2026-10-01")]), TODAY)
        self.assertIn("units.0.delivery_date", errs)
        _c, errs = catalogue.validate(individual(units=[unit(min_price=50)]), TODAY)
        self.assertIn("units.0.min_price", errs)
        _c, errs = catalogue.validate(individual(units=[unit(monthly_fee="other", monthly_fee_other=200)]), TODAY)
        self.assertIn("units.0.monthly_fee_other", errs)
        _c, errs = catalogue.validate(individual(units_count="2", units=[unit()]), TODAY)
        self.assertIn("units.1.district", errs)

    def test_op_pct_other_takes_half_steps(self):
        self.assertEqual(catalogue.op_pct_value(ok(individual(op_pct="other", op_pct_other=22.5))), 22.5)
        _c, errs = catalogue.validate(individual(op_pct="other", op_pct_other=22.3), TODAY)
        self.assertIn("op_pct_other", errs)
        _c, errs = catalogue.validate(individual(op_pct="other", op_pct_other=45), TODAY)
        self.assertIn("op_pct_other", errs)

    def test_more_than_three_in_one_property_needs_the_tick_and_warns(self):
        four = individual(units_count="4", same_property="yes", units=[unit() for _ in range(4)])
        _c, errs = catalogue.validate(four, TODAY)
        self.assertIn("same_property_ack", errs)
        c = ok(dict(four, same_property_ack=True))
        self.assertTrue(any("المادة 4/2" in w for w in catalogue.warnings(c)))
        # three units in one property: no tick, no warning
        three = ok(individual(units_count="3", same_property="yes", units=[unit() for _ in range(3)]))
        self.assertFalse(any("المادة 4/2" in w for w in catalogue.warnings(three)))

    def test_jamiya_unknown_saves_but_blocks_send(self):
        c = ok(individual(jamiya="unknown"))
        self.assertEqual(catalogue.send_blockers(c), ["لازم نتأكد من جمعية الملاك قبل إرسال العقد"])
        self.assertEqual(catalogue.send_blockers(ok(individual())), [])

    def test_junk_input_never_raises(self):
        for junk in (None, [], "x", {"units": "nope"}, {"units_count": "more", "units_more": "abc"}):
            catalogue.validate(junk, TODAY)


class TestOwnerGrammar(unittest.TestCase):

    def test_male_female_company_refer(self):
        self.assertIn("إليه في", engine.owner_refer(ok(individual())))
        self.assertIn("إليها في", engine.owner_refer(ok(individual(gender="f"))))
        self.assertIn("إليها في", engine.owner_refer(ok(company())))

    def test_capacity_and_vat_grammar(self):
        m = engine.owner_rows(ok(individual()))
        f = engine.owner_rows(ok(individual(gender="f")))
        self.assertIn("مالك أصلي", m)
        self.assertIn("غير مسجل<", m)
        self.assertIn("مالكة أصلية", f)
        self.assertIn("غير مسجلة<", f)

    def test_id_label_follows_id_type_and_prints_full_number(self):
        self.assertIn("رقم الهوية الوطنية", engine.owner_rows(ok(individual())))
        self.assertIn(NID, engine.owner_rows(ok(individual())))
        self.assertIn("رقم الإقامة", engine.owner_rows(ok(individual(id_type="iqama", id_number=IQAMA))))
        self.assertIn("رقم الهوية / الجواز", engine.owner_rows(ok(individual(id_type="other", id_number="P1234567"))))

    def test_agent_row(self):
        a = ok(individual(gender="f", signer="agent", agent_name="خالد العتيبي", agent_id=AGENT,
                          wakala_no="4455", wakala_date="2026-01-02"))
        rows = engine.owner_rows(a)
        self.assertIn("يمثلها في التوقيع", rows)
        self.assertIn("خالد العتيبي، هوية رقم %s، بموجب الوكالة رقم 4455 وتاريخ 02/01/2026م" % AGENT, rows)
        self.assertEqual(engine.signer(a)["secret"], AGENT)

    def test_company_rows(self):
        rows = engine.owner_rows(ok(company(rep_capacity="authorized", auth_ref="تفويض 77")))
        for s in ("الاسم النظامي", "شركة الأفق العقارية", "السجل التجاري / الرقم الموحد", CR,
                  "الممثل وصفته", "سعد الدوسري — مفوّض بالتوقيع بموجب تفويض 77", "غير مسجلة"):
            self.assertIn(s, rows)
        self.assertIn("سعد الدوسري — مدير الشركة", engine.owner_rows(ok(company())))

    def test_mobile_is_ltr(self):
        self.assertIn('<span dir="ltr">+966555123456</span>', engine.owner_rows(ok(individual())))


class TestUnitRows(unittest.TestCase):

    def test_one_three_seven_units(self):
        for n in (1, 3, 7):
            cnt = str(n) if n <= 5 else "more"
            a = ok(individual(units_count=cnt, units_more=n, units=[unit() for _ in range(n)]))
            rows = engine.unit_rows(a)
            self.assertEqual(rows.count("<tr>"), n)
            self.assertEqual(rows.count("<td>"), 9 * n)
            self.assertIn("A%d" % n, rows)

    def test_cells(self):
        a = ok(individual(units=[unit(blocked="set", blocked_text="1–10 ذو الحجة سنوياً")]))
        rows = engine.unit_rows(a)
        for s in ("1,050 ريال", "450 ريال", "1–10 ذو الحجة سنوياً", "20/10/2026م", "50035533 — ينتهي 01/05/2027م",
                  "الرياض — حي الملقا", "شقة / غرفتان"):
            self.assertIn(s, rows)
        p = engine.unit_rows(ok(individual(units=[unit(licence_status="pending")])))
        self.assertIn("قيد الإصدار — لا يبدأ التشغيل قبل صدوره", p)
        self.assertIn("لا يوجد", p)


class TestRender(unittest.TestCase):

    def test_render_leaves_no_placeholder_and_has_all_22_keys(self):
        self.assertEqual(sorted(ctx(ok(individual())).keys()), sorted(engine.KEYS))
        self.assertEqual(len(engine.KEYS), 22)
        out = render(ok(individual()))
        self.assertNotIn("{{", out)
        self.assertIn("23% ثابتة", out)

    def test_template_has_exactly_the_22_placeholders(self):
        t = files.template_text("operating_v2_1")
        self.assertEqual(sorted(set(engine.PLACEHOLDER.findall(t))), sorted(engine.KEYS))

    def test_missing_key_raises(self):
        c = ctx(ok(individual()))
        del c["jamiya"]
        with self.assertRaises(KeyError):
            engine.render(files.template_text("operating_v2_1"), c)

    def test_a_value_containing_a_placeholder_is_printed_literally(self):
        out = render(ok(individual(full_name="{{op_pct}} بن {{jamiya}} الشمري")))
        self.assertNotIn("{{", out)
        self.assertIn("&#123;&#123;op_pct&#125;&#125; بن", out)

    def test_html_is_escaped(self):
        out = render(ok(individual(full_name='<script>alert(1)</script> بن سعد', email="a@b.co")))
        self.assertNotIn("<script>alert", out)
        self.assertIn("&lt;script&gt;", out)

    def test_a_value_cannot_forge_a_slot_marker(self):
        out = render(ok(individual(full_name="<!--aqd:sig_owner--> بن سعد الشمري")))
        self.assertEqual(out.count(engine.SLOT["sig_owner"]), 1)

    def test_frozen_has_slots_and_fill_replaces_them(self):
        out = render(ok(individual()))
        for m in engine.SLOT.values():
            self.assertEqual(out.count(m), 1)
        filled = engine.fill_slots(out, version_banner=engine.banner_html(False),
                                   sig_owner="OWNER", sig_operator="OP")
        self.assertIn("نموذج غير معتمد للتوقيع", filled)
        self.assertNotIn("<!--aqd:", filled)

    def test_preview_banner_follows_approval(self):
        self.assertIn("نموذج غير معتمد", render(ok(individual()), frozen=False, approved=False))
        self.assertNotIn("نموذج غير معتمد", render(ok(individual()), frozen=False, approved=True))

    def test_hash_is_stable_for_same_answers_and_date(self):
        a = ok(individual())
        h1 = engine.doc_hash(render(a))
        h2 = engine.doc_hash(render(copy.deepcopy(a)))
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, engine.doc_hash(render(ok(individual(op_pct="25")))))

    def test_dates_hijri_and_weekday(self):
        self.assertEqual(engine.date_g(CREATED), "04/10/2026م")
        self.assertEqual(engine.weekday_ar(CREATED), "الأحد")
        self.assertRegex(engine.date_h(CREATED), r"^\d\d/\d\d/14\d\dهـ$")

    def test_evidence_page_is_appended_before_body_end(self):
        doc = engine.append_evidence("<html><body>X</body></html>", {"ref": "R1", "doc_sha256": "ab"})
        self.assertIn("سجل التوقيع الإلكتروني", doc)
        self.assertTrue(doc.endswith("</body></html>"))


class TestStateMachine(unittest.TestCase):
    ALL = ("draft", "sent", "opened", "verified", "signed_owner", "completed", "expired", "void")
    ALLOWED = {
        "edit": {"draft"}, "send": {"draft"}, "open": {"sent"}, "verify": {"sent", "opened"},
        "sign": {"verified"}, "countersign": {"signed_owner"},
        "void": {"draft", "sent", "opened", "verified"},
        "expire": {"sent", "opened", "verified"}, "resend": {"expired"},
    }

    def test_only_the_spec_transitions_are_allowed(self):
        for tr, allowed in self.ALLOWED.items():
            for st in self.ALL:
                good, reason = engine.can(tr, {"status": st})
                self.assertEqual(good, st in allowed, (tr, st))
                if not good:
                    self.assertTrue(reason)

    def test_signed_and_completed_cannot_be_voided(self):
        for st in ("signed_owner", "completed"):
            good, reason = engine.can("void", {"status": st})
            self.assertFalse(good)
            self.assertIn("موقّع", reason)

    def test_expiry_is_computed(self):
        c = {"status": "opened", "expires_at": "2026-10-10T00:00:00"}
        self.assertEqual(engine.effective_status(c, "2026-10-09T23:00:00"), "opened")
        self.assertEqual(engine.effective_status(c, "2026-10-10T00:00:01"), "expired")
        self.assertFalse(engine.can("sign", dict(c, status="verified"), "2026-10-11T00:00:00")[0])
        self.assertEqual(engine.effective_status(dict(c, status="signed_owner"), "2030-01-01T00:00:00"),
                         "signed_owner")


class TestNamesAndPrivacy(unittest.TestCase):

    def test_name_similarity_normalises_arabic(self):
        self.assertGreaterEqual(engine.name_similarity("عبدالله بن محمد بن سعد الشمري", "عبدالله محمد الشمري"), 0.6)
        self.assertGreaterEqual(engine.name_similarity("أحمد إبراهيم آل فاطمة", "احمد ابراهيم ال فاطمه"), 0.99)
        self.assertGreaterEqual(engine.name_similarity("مُحَمَّد  ـالعلي", "محمد العلي"), 0.95)
        self.assertLess(engine.name_similarity("عبدالله الشمري", "Mickey Mouse"), 0.6)

    def test_masked_answers_keep_last4_only(self):
        m = engine.masked_answers(ok(individual(signer="agent", agent_name="خالد العتيبي", agent_id=AGENT,
                                                wakala_no="4455", wakala_date="2026-01-02")))
        self.assertEqual(m["id_number"], "••••••" + NID[-4:])
        self.assertEqual(m["agent_id"], "••••••" + AGENT[-4:])
        self.assertNotIn(NID, repr(m))


if __name__ == "__main__":
    unittest.main()
