import json
import os
import subprocess
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))
JS_PATH = os.path.join(ROOT, "monthly_public", "static", "monthly.js")
CSS_PATH = os.path.join(ROOT, "monthly_public", "static", "monthly.css")


def run_node(expression):
    script = "const ui=require(%s); const out=(%s); process.stdout.write(JSON.stringify(out));" % (
        json.dumps(JS_PATH),
        expression,
    )
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(completed.stdout)


class MonthlyPublicMatcherReducerTests(unittest.TestCase):
    def test_work_branch_adds_place_and_back_preserves_answers(self):
        state = run_node("(() => { let s=ui.initialMatcherState(); s=ui.answerStep(s,'purpose','work'); s=ui.answerStep(s,'place',{kind:'destination',id:'kafd',label:'KAFD'}); s=ui.answerStep(s,'residents',2); s=ui.goBack(s); return s; })()")

        self.assertEqual(state["steps"], ["purpose", "place", "residents", "sleeping", "dates", "flexibility"])
        self.assertEqual(state["current"], 2)
        self.assertEqual(state["answers"]["purpose"], "work")
        self.assertEqual(state["answers"]["place"]["id"], "kafd")
        self.assertEqual(state["answers"]["residents"], 2)

    def test_changed_purpose_rebranches_and_removes_hidden_answers(self):
        state = run_node("(() => { let s=ui.initialMatcherState(); s=ui.answerStep(s,'purpose','work'); s=ui.answerStep(s,'place',{kind:'destination',id:'kafd',label:'KAFD'}); s=ui.goBack(s); s=ui.goBack(s); s=ui.answerStep(s,'purpose','family'); return s; })()")

        self.assertEqual(state["steps"], ["purpose", "residents", "sleeping", "dates", "flexibility"])
        self.assertEqual(state["current"], 1)
        self.assertNotIn("place", state["answers"])

    def test_completed_matcher_state_survives_a_deep_link_reload(self):
        state = run_node("ui.initialMatcherState({current:5,answers:{purpose:'family',residents:3,sleeping:'two_bedrooms',move_in:'2026-09-01',duration_months:2,date_mode:'duration',flexibility:'fixed'}})")

        self.assertEqual(state["current"], len(state["steps"]))

    def test_public_included_labels_omit_unapproved_raw_terms(self):
        values = run_node("ui.approvedIncluded(['internet','raw provider value','maintenance'])")

        self.assertEqual(values, ["internet", "maintenance"])

    def test_api_request_contains_only_approved_match_contract(self):
        request = run_node("ui.buildMatchRequest({purpose:'family',residents:3,sleeping:'two_bedrooms',move_in:'2026-09-01',duration_months:2,flexibility:'plus_minus_7',date_mode:'duration',ui_note:'private'})")

        self.assertEqual(
            request,
            {
                "purpose": "family",
                "residents": 3,
                "sleeping": "two_bedrooms",
                "move_in": "2026-09-01",
                "duration_months": 2,
                "flexibility": "plus_minus_7",
            },
        )

    def test_image_url_allowlist_rejects_active_content(self):
        values = run_node("['https://images.example/a.jpg','http://images.example/b.webp','javascript:alert(1)','data:image/png;base64,AA','/local.jpg'].map(ui.safeImageUrl)")
        self.assertEqual(
            values,
            [
                "https://images.example/a.jpg",
                "http://images.example/b.webp",
                "",
                "",
                "",
            ],
        )

    def test_whatsapp_url_allowlist_accepts_only_the_server_handoff_origin(self):
        values = run_node("['https://wa.me/966500000000?text=ok','http://wa.me/1','https://example.com/wa','javascript:alert(1)'].map(ui.safeWhatsAppUrl)")

        self.assertEqual(values, ["https://wa.me/966500000000?text=ok", "", "", ""])


class MonthlyPublicStaticContentTests(unittest.TestCase):
    def setUp(self):
        with open(JS_PATH, encoding="utf-8") as handle:
            self.js = handle.read()
        with open(CSS_PATH, encoding="utf-8") as handle:
            self.css = handle.read()

    def test_every_interface_copy_has_arabic_and_english_locale_tables(self):
        self.assertIn("const COPY =", self.js)
        self.assertIn("ar:", self.js)
        self.assertIn("en:", self.js)
        for hook in ("setLanguage", "document.documentElement.lang", "document.documentElement.dir", "lang: runtime.lang", "sessionStorage"):
            self.assertIn(hook, self.js)

    def test_one_question_flow_and_same_origin_api_hooks_are_present(self):
        for hook in (
            'data-view="question"',
            "answerStep",
            "goBack",
            "focusQuestion",
            '"/api/monthly/config"',
            '"/api/monthly/search"',
            '"/api/monthly/match"',
            '"/api/monthly/lead"',
            '"/api/monthly/event"',
        ):
            self.assertIn(hook, self.js)

    def test_price_and_whatsapp_ui_use_server_contracts_without_auto_sending(self):
        for field in (
            "monthly_rate_sar",
            "stay_total_sar",
            "included",
            "utilities",
            "cleaning",
            "deposit",
            "payment_methods",
            "preliminary_label_ar",
            "preliminary_label_en",
            "lead_reference",
            "response_window",
        ):
            self.assertIn(field, self.js)
        self.assertIn("safeWhatsAppUrl(handoff.url)", self.js)
        self.assertIn("window.location.assign(handoffUrl)", self.js)
        self.assertNotIn("window.open(handoff.url", self.js)

    def test_listing_uses_real_gallery_photos_for_story_and_a_mobile_action(self):
        for hook in ("story-photo", "listing.highlights", "sticky-mobile-action"):
            self.assertIn(hook, self.js)

    def test_dom_rendering_avoids_unsafe_interpolation_and_browser_pii_storage(self):
        forbidden = (
            ".innerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "localStorage",
        )
        for token in forbidden:
            self.assertNotIn(token, self.js)
        self.assertIn("textContent", self.js)
        self.assertIn("safeImageUrl", self.js)

    def test_styles_enforce_touch_focus_motion_rtl_and_mobile_safety(self):
        for token in (
            "min-height: 44px",
            ":focus-visible",
            "prefers-reduced-motion: reduce",
            "padding-bottom: env(safe-area-inset-bottom)",
            "overflow-x: clip",
            "[dir=\"ltr\"]",
            "220ms",
            "aspect-ratio:",
            "@media (min-width: 768px)",
        ):
            self.assertIn(token, self.css)
        self.assertNotIn("gradient", self.css.casefold())

    def test_assets_do_not_depend_on_external_fonts_scripts_or_image_proxies(self):
        combined = self.js + "\n" + self.css
        for token in (
            "fonts.googleapis",
            "fonts.gstatic",
            "unpkg.com",
            "cdn.jsdelivr",
            "/monthly/img",
            "api.hostaway",
            "requests.get",
        ):
            self.assertNotIn(token, combined)

    def test_static_copy_contains_no_discounts_crossed_prices_or_placeholders(self):
        combined = (self.js + "\n" + self.css).casefold()
        for phrase in (
            "up to 30%",
            "30%",
            "maximum discount",
            "أقصى خصم",
            "خصم يصل",
            "text-decoration: line-through",
            "lorem ipsum",
            "placeholder",
        ):
            self.assertNotIn(phrase, combined)


if __name__ == "__main__":
    unittest.main()
