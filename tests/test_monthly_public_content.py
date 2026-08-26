import json
import os
import subprocess
import unittest
import re


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


def run_node_async(expression):
    script = "const ui=require(%s); Promise.resolve(%s).then(out=>process.stdout.write(JSON.stringify(out))).catch(error=>{process.stderr.write(String(error && error.stack || error));process.exit(1)});" % (
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

    def test_location_search_accepts_v2_and_legacy_aliases_and_rejects_bad_values(self):
        values = run_node("({v2:ui.parseLocationSearch('?move_in=2026-09-01&duration_months=2&residents=3&bedrooms=2','listing'),legacy:ui.parseLocationSearch('?move_in=2026-09-01&months=4&guests=5&beds=studio','browse'),bad:ui.parseLocationSearch('?move_in=not-a-date&months=99&guests=phone&beds=all&neighborhood=../../etc','browse')})")

        self.assertEqual(values["v2"], {"move_in": "2026-09-01", "duration_months": 2, "residents": 3, "bedrooms": 2})
        self.assertEqual(values["legacy"], {"move_in": "2026-09-01", "duration_months": 4, "residents": 5, "bedrooms": 0})
        self.assertEqual(values["bad"], {})

    def test_studio_url_filter_keeps_zero_as_the_selected_value(self):
        values = run_node("({studio:ui.optionIsSelected(0,0),blank:ui.optionIsSelected(0,''),unset:ui.optionIsSelected(null,'')})")

        self.assertEqual(values, {"studio": True, "blank": False, "unset": True})

    def test_existing_valid_session_token_wins_over_new_config_token(self):
        existing = "anon_" + "A" * 32 + "." + "b" * 43
        issued = "anon_" + "C" * 32 + "." + "d" * 43
        values = run_node("({kept:ui.chooseSessionToken(%s,%s),replaced:ui.chooseSessionToken('forged',%s),rejected:ui.chooseSessionToken('bad','also-bad')})" % (json.dumps(existing), json.dumps(issued), json.dumps(issued)))

        self.assertEqual(values["kept"], existing)
        self.assertEqual(values["replaced"], issued)
        self.assertIsNone(values["rejected"])

    def test_contact_state_explains_blockers_and_localizes_response_window(self):
        session = "anon_" + "A" * 32 + "." + "b" * 43
        values = run_node(
            "({missingNumber:ui.contactState({session_id:%s,blockers:[{field:'whatsapp_number'}],response_window:{message_ar:'رد عربي',message_en:'English reply'}},'ar'),"
            "missingSession:ui.contactState({blockers:[],response_window:{message_ar:'رد عربي',message_en:'English reply'}},'en'),"
            "enabled:ui.contactState({session_id:%s,blockers:[],response_window:{message_ar:'رد عربي',message_en:'English reply'}},'en'),"
            "handoff:ui.responseWindowMessage({response_window:{message_ar:'رد الحوالة',message_en:'Handoff reply'}},'ar')})"
            % (json.dumps(session), json.dumps(session))
        )

        self.assertTrue(values["missingNumber"]["disabled"])
        self.assertIn("واتساب", values["missingNumber"]["message"])
        self.assertEqual(values["missingNumber"]["response_message"], "")
        self.assertTrue(values["missingSession"]["disabled"])
        self.assertIn("secure request session", values["missingSession"]["message"].lower())
        self.assertEqual(values["missingSession"]["response_message"], "")
        self.assertEqual(
            values["enabled"],
            {"disabled": False, "message": "", "response_message": "English reply"},
        )
        self.assertEqual(values["handoff"], "رد الحوالة")

    def test_public_availability_hides_undated_confirmed_state(self):
        values = run_node("({undated:['confirmed','available','pending','unavailable'].map(v=>ui.publicAvailabilityStatus(v,false)),dated:['confirmed','available','pending','unavailable','invented'].map(v=>ui.publicAvailabilityStatus(v,true))})")

        self.assertEqual(values["undated"], ["", "", "", ""])
        self.assertEqual(values["dated"], ["", "available", "pending", "unavailable", ""])

    def test_ranked_impressions_include_near_matches_once(self):
        values = run_node("ui.rankedImpressionIds({top:[{id:'1'},{id:'2'}],near_matches:[{id:'3'},{id:'2'}],alternatives:[{id:'4'},{id:'3'}],catalog:[{id:'5'}]})")

        self.assertEqual(values, ["1", "2", "3", "4"])

    def test_recommendation_context_is_bounded_and_listing_specific(self):
        value = run_node("ui.safeRecommendationContext({id:'1001',reasons:['Verified fit','',7,'A'.repeat(400)],tradeoff:'Useful tradeoff'},'en')")

        self.assertEqual(value["listing_id"], "1001")
        self.assertEqual(value["lang"], "en")
        self.assertEqual(value["reasons"], ["Verified fit"])
        self.assertEqual(value["tradeoff"], "Useful tradeoff")

    def test_near_match_adjusted_dates_become_the_canonical_listing_request(self):
        values = run_node(
            "({near:ui.canonicalListingRequest({purpose:'work',residents:2,sleeping:'one_bedroom',move_in:'2026-09-01',duration_months:2,flexibility:'plus_minus_7'},{changed_condition:'dates',adjusted_move_in:'2026-09-03',adjusted_move_out:'2026-11-03'}),"
            "exactDates:ui.canonicalListingRequest({move_in:'2026-09-01',move_out:'2026-11-01'},{changed_condition:'dates',adjusted_move_in:'2026-09-03',adjusted_move_out:'2026-11-03'}),"
            "exact:ui.canonicalListingRequest({move_in:'2026-09-01',duration_months:2},{changed_condition:''}),"
            "label:ui.adjustedDateWindow({changed_condition:'dates',adjusted_move_in:'2026-09-03',adjusted_move_out:'2026-11-03'})})"
        )

        self.assertEqual(
            values["near"],
            {
                "purpose": "work",
                "residents": 2,
                "sleeping": "one_bedroom",
                "move_in": "2026-09-03",
                "duration_months": 2,
                "flexibility": "plus_minus_7",
            },
        )
        self.assertEqual(
            values["exactDates"],
            {"move_in": "2026-09-03", "move_out": "2026-11-03"},
        )
        self.assertEqual(values["exact"], {"move_in": "2026-09-01", "duration_months": 2})
        self.assertEqual(values["label"], {"move_in": "2026-09-03", "move_out": "2026-11-03"})

    def test_non_signature_failure_does_not_refresh_or_retry(self):
        current = "anon_" + "A" * 32 + "." + "b" * 43
        cached = "anon_" + "E" * 32 + "." + "f" * 43
        minted = "anon_" + "C" * 32 + "." + "d" * 43
        values = run_node_async(
            "(async()=>{let calls=0;let refreshes=0;let rotated='';const failed=await ui.retrySessionOperation(async()=>{calls+=1;const error=new Error('network');error.code='request_failed';throw error;},%s,%s,async()=>{refreshes+=1;return %s;},token=>{rotated=token;}).then(()=>null,error=>error.code);return {calls:calls,refreshes:refreshes,rotated:rotated,failed:failed};})()"
            % (json.dumps(current), json.dumps(cached), json.dumps(minted))
        )

        self.assertEqual(values["calls"], 1)
        self.assertEqual(values["refreshes"], 0)
        self.assertEqual(values["rotated"], "")
        self.assertEqual(values["failed"], "request_failed")

    def test_open_tab_rotation_mints_one_token_when_both_saved_tokens_are_stale(self):
        stale = "anon_" + "A" * 32 + "." + "b" * 43
        minted = "anon_" + "C" * 32 + "." + "d" * 43
        values = run_node_async(
            "(async()=>{if(typeof ui.retrySessionOperation!=='function')return {missing:true};let calls=[];let refreshes=0;let rotated='';const ok=await ui.retrySessionOperation(async token=>{calls.push(token);if(calls.length===1){const error=new Error('rotated');error.code='invalid_signature';throw error;}return 'ok';},%s,%s,async()=>{refreshes+=1;return %s;},token=>{rotated=token;});let failedCalls=0;let failedRefreshes=0;const failed=await ui.retrySessionOperation(async()=>{failedCalls+=1;const error=new Error('still invalid');error.code='invalid_signature';throw error;},%s,%s,async()=>{failedRefreshes+=1;return %s;},()=>{}).then(()=>null,error=>error.code);return {ok:ok,calls:calls,refreshes:refreshes,rotated:rotated,failed_calls:failedCalls,failed_refreshes:failedRefreshes,failed:failed};})()"
            % (
                json.dumps(stale),
                json.dumps(stale),
                json.dumps(minted),
                json.dumps(stale),
                json.dumps(stale),
                json.dumps(minted),
            )
        )

        self.assertNotIn("missing", values)
        self.assertEqual(values["ok"], "ok")
        self.assertEqual(values["calls"], [stale, minted])
        self.assertEqual(values["refreshes"], 1)
        self.assertEqual(values["rotated"], minted)
        self.assertEqual(values["failed_calls"], 2)
        self.assertEqual(values["failed_refreshes"], 1)
        self.assertEqual(values["failed"], "invalid_signature")

    def test_rotation_ignores_a_distinct_cached_token_signed_before_rotation(self):
        current = "anon_" + "A" * 32 + "." + "b" * 43
        cached = "anon_" + "E" * 32 + "." + "f" * 43
        minted = "anon_" + "C" * 32 + "." + "d" * 43
        values = run_node_async(
            "(async()=>{let calls=[];let refreshes=0;let rotated='';const ok=await ui.retrySessionOperation(async token=>{calls.push(token);if(calls.length===1){const error=new Error('rotated');error.code='invalid_signature';throw error;}return 'ok';},%s,%s,async()=>{refreshes+=1;return %s;},token=>{rotated=token;});return {ok:ok,calls:calls,refreshes:refreshes,rotated:rotated};})()"
            % (json.dumps(current), json.dumps(cached), json.dumps(minted))
        )

        self.assertEqual(values["ok"], "ok")
        self.assertEqual(values["calls"], [current, minted])
        self.assertEqual(values["refreshes"], 1)
        self.assertEqual(values["rotated"], minted)


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

    def test_boot_and_popstate_apply_validated_url_state_before_route_loading(self):
        self.assertGreaterEqual(self.js.count("applyLocationSearch()"), 2)
        self.assertIn("runtime.listingRequest", self.js)
        self.assertIn("parseLocationSearch", self.js)

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
        self.assertIn("general_help: true", self.js)

    def test_four_to_six_month_caveat_survives_a_missing_price(self):
        self.assertIn(
            "سعر مبدئي. يؤكد فريق عوجا نوع العقد والشروط قبل الالتزام.",
            self.js,
        )
        self.assertIn(
            "Preliminary price. Ouja confirms the contract route and terms before commitment.",
            self.js,
        )
        no_quote = self.js[
            self.js.index("if (!quote) {"):
            self.js.index("const total = element", self.js.index("if (!quote) {"))
        ]
        self.assertIn("duration_months", no_quote)
        self.assertIn('copy("preliminaryFallback")', no_quote)

    def test_empty_result_help_renders_a_visible_blocker_or_response_window(self):
        self.assertIn("contactState", self.js)
        self.assertIn('"contact-blocked"', self.js)
        self.assertIn('"contact-note"', self.js)
        self.assertIn('data-response-window', self.js)
        general_handoff = self.js[
            self.js.index("async function prepareGeneralHelp"):
            self.js.index("function renderListingPage")
        ]
        self.assertIn("responseWindowMessage(handoff", general_handoff)

    def test_one_canonical_listing_request_drives_quote_form_url_and_lead(self):
        for hook in (
            "runtime.listingRequest",
            "canonicalListingRequest",
            "adjustedDateWindow",
            "copy(\"adjustedDates\"",
        ):
            self.assertIn(hook, self.js)
        self.assertNotIn("runtime.request || runtime.listingQuery", self.js)
        self.assertIn("request: runtime.listingRequest", self.js)
        self.assertIn("queryString(runtime.listingRequest)", self.js)

    def test_browse_entry_clears_guided_state_without_clearing_browse_filters(self):
        navigate = self.js[self.js.index("function navigate") : self.js.index("function stateMessage")]
        for hook in (
            "runtime.request = null",
            "runtime.matcher = initialMatcherState()",
            "runtime.results = null",
            "runtime.recommendationContext = null",
            "runtime.listingRequest = {}",
        ):
            self.assertIn(hook, navigate)
        self.assertNotIn("runtime.browseQuery = {}", navigate)

    def test_browse_card_does_not_create_guided_recommendation_context(self):
        open_listing = self.js[
            self.js.index("function openListing") : self.js.index("function createCard")
        ]
        self.assertIn('const guided = runtime.page.route !== "browse"', open_listing)
        self.assertIn(
            "runtime.recommendationContext = guided ? safeRecommendationContext(item, runtime.lang) : null",
            open_listing,
        )
        self.assertIn("const sourceRequest = guided ? runtime.request : runtime.browseQuery", open_listing)

    def test_contact_state_is_shared_by_home_results_and_listing(self):
        self.assertIn("function contactState", self.js)
        self.assertNotIn("function generalHelpContactState", self.js)
        for function_name in ("responseProof", "renderResults", "quoteCard", "renderListingPage"):
            start = self.js.index("function " + function_name)
            next_function = self.js.find("\n  function ", start + 12)
            if next_function < 0:
                next_function = len(self.js)
            self.assertIn("contactState(", self.js[start:next_function])
        self.assertNotIn('track("whatsapp_click"', self.js)

    def test_config_keeps_a_fresh_rotation_token_and_retries_event_and_lead(self):
        self.assertIn("runtime.config.fresh_session_id = issued", self.js)
        self.assertNotIn("function retryOnceForInvalidSignature", self.js)
        self.assertNotIn("function recoverySessionToken", self.js)
        self.assertIn("getJSON(ENDPOINTS.config", self.js)
        self.assertIn(
            "retrySessionOperation(operation, current, fresh, mintFreshSessionToken",
            self.js,
        )
        self.assertGreaterEqual(self.js.count("withSessionRetry("), 3)

    def test_browser_correlates_each_funnel_journey_with_its_created_lead(self):
        self.assertIn("function createJourneyId", self.js)
        self.assertIn("journey_id: runtime.journeyId", self.js)
        self.assertIn("journey_id: runtime.journeyId", self.js[self.js.index("function safeEventContext"):])

    def test_listing_uses_real_gallery_photos_for_story_and_a_mobile_action(self):
        for hook in ("story-photo", "listing.highlights", "sticky-mobile-action", "sizes"):
            self.assertIn(hook, self.js)

    def test_customer_shell_stays_within_a_small_uncompressed_asset_budget(self):
        self.assertLess(len(self.js.encode("utf-8")), 110_000)
        self.assertLess(len(self.css.encode("utf-8")), 30_000)

    def test_ranked_clicks_do_not_duplicate_visible_impressions(self):
        self.assertIn("rankedImpressionIds", self.js)
        self.assertNotIn('if (rank) track("result_impression"', self.js)

    def test_guided_listing_context_and_short_verified_inclusions_are_rendered(self):
        for hook in ("recommendationContext", "whyRecommended", "approvedIncluded(item.quote.included", "tradeoff"):
            self.assertIn(hook, self.js)

    def test_mobile_dom_order_puts_price_before_licence_and_gallery_does_not_force_crop(self):
        price_position = self.js.index("price.appendChild(quoteCard")
        licence_position = self.js.index("wrap.appendChild(licenceDetails")
        self.assertLess(price_position, licence_position)
        gallery_css = self.css[self.css.index(".gallery img {"):self.css.index(".listing-layout {")]
        self.assertIn("height: auto", gallery_css)
        self.assertNotIn("object-fit: cover", gallery_css)

    def test_english_headings_use_local_serif_while_controls_remain_sans(self):
        self.assertRegex(self.css, r'(?s)\[dir="ltr"\]\s+:is\(h1, h2, h3\).*?Georgia')
        self.assertIn('[dir="ltr"] body', self.css)

    def test_primary_button_meets_wcag_aa_contrast(self):
        def rgb(value):
            return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))

        def luminance(value):
            channels = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in rgb(value)]
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        variables = dict(re.findall(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})", self.css))
        block = self.css[self.css.index(".button-primary {"):self.css.index(".button-primary:hover")]
        background_name = re.search(r"background:\s*var\((--[\w-]+)\)", block).group(1)
        color_name = re.search(r"color:\s*var\((--[\w-]+)\)", block).group(1)
        first, second = luminance(variables[background_name]), luminance(variables[color_name])
        contrast = (max(first, second) + 0.05) / (min(first, second) + 0.05)
        self.assertGreaterEqual(contrast, 4.5)

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
