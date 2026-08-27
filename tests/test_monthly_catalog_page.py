import asyncio
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CSS_FILE = ROOT / "monthly_public" / "static" / "monthly_catalog.css"
JS_FILE = ROOT / "monthly_public" / "static" / "monthly_catalog.js"
OPS_JS_FILE = ROOT / "monthly_public" / "static" / "monthly_ops.js"


def run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class FakeRequest:
    def __init__(self, path="/monthly/ops/listings", query=None):
        self.path = path
        self.method = "GET"
        self.query = query or {}
        self.headers = {}
        self.cookies = {}


class MonthlyCatalogPageContractTest(unittest.TestCase):
    def _javascript_result(self, expression):
        script = "const api=require(%s); process.stdout.write(JSON.stringify(%s));" % (
            json.dumps(str(JS_FILE)),
            expression,
        )
        checked = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        return json.loads(checked.stdout)

    def test_page_is_arabic_first_semantic_and_data_free(self):
        from monthly_public.catalog_page import render_monthly_catalog_page

        html = render_monthly_catalog_page()
        self.assertIn('<html lang="ar" dir="rtl">', html)
        self.assertIn('href="#catalog-main"', html)
        self.assertIn('id="catalog-language"', html)
        self.assertIn('id="catalog-summary"', html)
        self.assertIn('id="global-setup"', html)
        self.assertIn('id="portfolio-filters"', html)
        self.assertIn('id="listing-table"', html)
        self.assertIn('id="survey"', html)
        self.assertIn('id="places"', html)
        self.assertIn('id="places-summary"', html)
        self.assertIn('id="places-summary" class="places-summary" aria-live="polite"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('aria-labelledby="portfolio-title"', html)
        self.assertIn('autocomplete="off"', html)
        self.assertIn('meta name="robots" content="noindex,nofollow,noarchive"', html)
        for forbidden in (
            "wifi",
            "door_code",
            "owner_phone",
            "session_id",
            "token=",
            "wa.me",
        ):
            self.assertNotIn(forbidden, html.lower())

    def test_catalog_asset_version_changes_for_the_save_and_preview_flow(self):
        from monthly_public.catalog_page import ASSET_VERSION

        self.assertEqual(ASSET_VERSION, "v20260828a")

    def test_showcase_editor_uses_real_cover_choices_and_per_home_prices(self):
        js = JS_FILE.read_text("utf-8")
        css = CSS_FILE.read_text("utf-8")

        for required in (
            "approved_image_options",
            "image_listing_id",
            "listing_prices",
            "showcaseListingRate",
            "showcasePreviewLink",
            "renderShowcaseCoverPicker",
        ):
            self.assertIn(required, js)
        self.assertIn(".showcase-cover-gallery", css)
        self.assertIn(".showcase-listing-price", css)

    def test_showcase_list_labels_public_homes_with_optional_gaps(self):
        js = JS_FILE.read_text("utf-8")

        for required in (
            "eligible_with_gaps_count",
            "showcaseEligibleWithGaps",
            "تظهر مع بيانات ناقصة",
            "Published with missing details",
        ):
            self.assertIn(required, js)

    def test_portfolio_and_survey_expose_verified_review_readiness(self):
        js = JS_FILE.read_text("utf-8")

        for required in (
            "row.review_ready",
            "row.review_count",
            "source.reviews",
            "reviewsReady",
            "reviewsMissing",
            "status-stack",
        ):
            self.assertIn(required, js)
        self.assertIn(".status-stack", CSS_FILE.read_text("utf-8"))

    def test_styles_preserve_operations_tokens_and_accessibility(self):
        css = CSS_FILE.read_text("utf-8")
        for required in (
            "--palm-950",
            "--bronze-700",
            "--ivory",
            "min-width: 320px",
            "min-height: 44px",
            ":focus-visible",
            "prefers-reduced-motion: reduce",
            "overflow-x: clip",
            "@media (max-width: 720px)",
            "[dir=\"ltr\"]",
        ):
            self.assertIn(required, css)
        self.assertNotIn("border-radius: 32px", css)
        self.assertNotIn("background-clip: text", css)
        self.assertNotIn("repeating-linear-gradient", css)
        self.assertNotIn("border-left: 4px", css)

    def test_shell_asset_is_local_safe_and_valid_javascript(self):
        js = JS_FILE.read_text("utf-8")
        for forbidden in (
            "localStorage",
            "sessionStorage",
            "document.cookie",
            "innerHTML",
            "XMLHttpRequest",
            "WebSocket",
            "Hostaway",
            "hostaway",
            "wa.me",
        ):
            self.assertNotIn(forbidden, js)
        checked = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_javascript_exports_safe_payload_helpers(self):
        result = self._javascript_result("({"
            "auth:api.authPath('/api/monthly/ops/listings','?token=secret&ignored=1'),"
            "facts:['yes','no','unknown',''].map(api.buildFactValue),"
            "coords:[api.parseCoordinatePair('24.7136, 46.6753'),api.parseCoordinatePair('not a map')],"
            "percent:api.completionPercent({name_ar:'عوجا',name_en:'Ouja',short_ar:'وصف',short_en:'Description'})"
            "})")
        self.assertEqual(result["auth"], "/api/monthly/ops/listings?token=secret")
        self.assertEqual(result["facts"], [True, False, None, None])
        self.assertEqual(result["coords"][0], {"lat": 24.7136, "lng": 46.6753})
        self.assertIsNone(result["coords"][1])
        self.assertEqual(result["percent"], 31)

    def test_readiness_uses_current_values_and_catches_the_92_percent_language_error(self):
        result = self._javascript_result(
            "api.profileReadiness({"
            "active:true,name_ar:'English only',name_en:'Ouja home',"
            "short_ar:'وصف عربي',short_en:'English description',"
            "content_verified:true,bedrooms:2,baths:2,capacity:4,"
            "neighborhood:'malqa',neighborhood_ar:'الملقا',"
            "neighborhood_en:'Al Malqa',neighborhood_verified:true,"
            "images:['1','2','3'],licence:{licence_no:'LIC-1',expires:'2027-01-01'},"
            "commercial_terms:{utilities:{mode:'included',label_ar:'مشمولة',label_en:'Included'},"
            "cleaning:{mode:'optional',amount_sar:150,label_ar:'اختياري',label_en:'Optional'}}"
            "})"
        )

        self.assertEqual(result["percent"], 92)
        self.assertFalse(result["ready_for_approval"])
        self.assertEqual(
            result["staff_blockers"], ["arabic_title_language_mismatch"]
        )

    def test_all_listing_blockers_and_error_fields_have_bilingual_labels(self):
        codes = [
            "active_missing", "arabic_title_missing",
            "arabic_title_language_mismatch", "english_title_missing",
            "english_title_language_mismatch", "arabic_content_missing",
            "arabic_content_language_mismatch", "english_content_missing",
            "english_content_language_mismatch", "content_unverified",
            "bedrooms_missing", "bathrooms_missing", "capacity_missing",
            "neighbourhood_missing", "images_missing", "licence_missing",
            "commercial_terms_missing", "commercial_terms_language_mismatch",
            "price_missing", "calendar_missing", "calendar_stale",
            "calendar_future", "calendar_invalid", "rating_unverified",
            "rating_invalid", "source_refresh_failed", "catalog_incomplete",
            "licence_expiry_missing", "licence_expiry_invalid",
            "licence_expired", "title_bedroom_conflict",
            "untranslated_amenity", "coordinates_unverified",
        ]
        expression = (
            "({labels:%s.flatMap(function(code){return ["
            "api.translatedBlocker(code,'ar'),api.translatedBlocker(code,'en')]}),"
            "fields:[api.issueFieldLabel('name_ar','ar'),"
            "api.issueFieldLabel('structured.sections.0.body_en','en')],"
            "steps:[api.fieldStep('name_ar'),"
            "api.fieldStep('structured.sections.0.body_en'),"
            "api.fieldStep('commercial_terms.cleaning.label_ar')]})"
        ) % json.dumps(codes)
        result = self._javascript_result(expression)

        self.assertTrue(all(label and "_" not in label for label in result["labels"]))
        self.assertEqual(result["fields"], ["اسم الشقة بالعربي", "English section details"])
        self.assertEqual(result["steps"], ["identity", "content", "terms"])

    def test_survey_error_names_and_focuses_the_exact_api_field(self):
        js = JS_FILE.read_text("utf-8")
        for required in (
            "issue.field",
            "issueFieldLabel(issue.field, state.lang)",
            "fieldStep(issue.field)",
            "control.name === issue.field",
            'control.setAttribute("aria-invalid", "true")',
            "control.focus()",
        ):
            self.assertIn(required, js)

    def test_javascript_builds_only_approved_contract_fields(self):
        result = self._javascript_result("({"
            "profile:api.buildProfilePayload({active:true,name_ar:'عوجا',name_en:'Ouja',short_ar:'وصف',short_en:'Description',content_verified:true,neighborhood:'malqa',neighborhood_ar:'الملقا',neighborhood_en:'Al Malqa',neighborhood_verified:true,bedrooms:'2',beds_count:'3',baths:'2',capacity:'4',floor_area_sqm:'110.5',images:['https://images.example/1.jpg'],facts:{parking:'yes',pool:'unknown'},licence:{licence_no:'LIC-1',expires:'2027-01-01'},commercial_terms:{utilities:{mode:'included',label_ar:'مشمولة',label_en:'Included'},cleaning:{mode:'optional',amount_sar:'150',label_ar:'اختياري',label_en:'Optional'}},coordinates:'24.7136,46.6753',structured:{tagline_ar:'سكن هادئ',tagline_en:'Quiet stay',sections:[{title_ar:'المعيشة',title_en:'Living',body_ar:'مساحة مريحة',body_en:'Comfortable space'}]},official_prices:{'2026-09':9000},door_code:'1234'}),"
            "settings:api.buildSettingsPayload({whatsapp_number:'966500000000',timezone:'Asia/Riyadh',schedule:{monday:{enabled:true,start:'13:00',end:'21:00'},friday:{enabled:false,start:'13:00',end:'21:00'}},internet_included:true,maintenance_included:true,deposit_amount_sar:'1000',deposit_refund_ar:'يعاد بعد الفحص',deposit_refund_en:'Returned after inspection',payment_methods:[{ar:'تحويل بنكي',en:'Bank transfer'}],long_stay_route:'team_confirmation'}),"
            "partialSettings:api.buildSettingsPayload({internet_included:true,maintenance_included:false}),"
            "place:api.buildPlacePayload({label_ar:'مستشفى الملك فيصل',label_en:'King Faisal Hospital',purposes:['treatment','work','treatment'],coordinates:'24.7136,46.6753',source_note:'تم التحقق من الدبوس'})"
            "})")
        profile = result["profile"]
        self.assertNotIn("official_prices", profile)
        self.assertNotIn("door_code", profile)
        self.assertEqual(profile["bedrooms"], 2)
        self.assertEqual(profile["floor_area_sqm"], 110.5)
        self.assertEqual(profile["facts"], {"parking": True, "pool": None})
        self.assertEqual(profile["coordinates"]["source"], "staff_maps_pin")
        self.assertEqual(profile["commercial_terms"]["cleaning"]["amount_sar"], 150)
        self.assertEqual(result["settings"]["commercial_terms"]["included"], ["internet", "maintenance"])
        self.assertEqual(result["partialSettings"]["commercial_terms"]["included"], ["internet"])
        self.assertEqual(result["settings"]["working_hours"]["schedule"], {"monday": [["13:00", "21:00"]]})
        self.assertEqual(result["place"]["purposes"], ["treatment", "work"])
        self.assertEqual(result["place"]["coordinates"]["verified"], True)

    def test_javascript_omits_the_empty_structured_section_placeholder(self):
        result = self._javascript_result(
            "api.buildProfilePayload({structured:{"
            "tagline_ar:'سكن هادئ',tagline_en:'Quiet stay',"
            "sections:[{title_ar:'',title_en:'',body_ar:'',body_en:''}]"
            "}})"
        )

        self.assertEqual(
            result["structured"],
            {"tagline_ar": "سكن هادئ", "tagline_en": "Quiet stay"},
        )

    def test_javascript_filters_truthful_inventory_without_duplicate_rows(self):
        result = self._javascript_result("api.filterListings(["
            "{id:'101',source_title:'Ouja | Malqa',status:'needs_review',staff_blockers:['licence_missing'],background_blockers:[]},"
            "{id:'101',source_title:'duplicate',status:'published',staff_blockers:[],background_blockers:[]},"
            "{id:'202',source_title:'Ouja | Olaya',status:'source_blocked',staff_blockers:[],background_blockers:['price_missing']}"
            "],{search:'malqa',status:'needs_review',blocker:'licence'})")
        self.assertEqual([row["id"] for row in result], ["101"])

    def test_javascript_summarizes_only_active_approved_non_university_places(self):
        result = self._javascript_result(
            "api.summarizePlaces({"
            "biz:{active:true,approved:{category_id:'business_hubs'}},"
            "hospital:{active:true,approved:{category_id:'hospitals'}},"
            "inactive:{active:false,approved:{category_id:'events'}},"
            "draft:{active:true,draft:{category_id:'events'}},"
            "edu:{active:true,approved:{category_id:'universities'}}"
            "})"
        )

        self.assertEqual(result, {
            "total": 2,
            "categories": {"business_hubs": 1, "hospitals": 1},
        })

    def test_nearest_place_ui_is_evidence_based_and_link_safe(self):
        js = JS_FILE.read_text("utf-8")
        css = CSS_FILE.read_text("utf-8")
        for required in (
            "nearest_places",
            "distance_km",
            "category_ar",
            "category_en",
            "verified_at",
            "review_interval_ar",
            "review_interval_en",
            "map_url",
            "coordinate_source_url",
            "official_source_url",
            'link.target = "_blank"',
            'link.rel = "noopener noreferrer"',
            "nearbyNoPin",
            "nearbyEmpty",
            "straightLine",
        ):
            self.assertIn(required, js)
        for required in (
            ".places-summary",
            ".place-meta",
            ".nearest-places",
            ".nearest-place-row",
            ".nearest-place-links",
        ):
            self.assertIn(required, css)

        labels = self._javascript_result(
            "[api.formatDistance(1.24,'ar'),api.formatDistance(1.24,'en')]"
        )
        self.assertEqual(labels, ["1.2 كم بخط مستقيم", "1.2 km straight-line"])

    def test_javascript_localizes_working_days_and_explains_prefill_sources(self):
        result = self._javascript_result(
            "({"
            "days:[api.translatedDay('monday','ar'),api.translatedDay('friday','en')],"
            "sources:["
            "api.prefillSourceLabel({bedrooms:'hostaway_listing'},'bedrooms','ar'),"
            "api.prefillSourceLabel({facts:'monthly_approved'},'facts.pool','en'),"
            "api.prefillSourceLabel({},'capacity','ar')"
            "],"
            "conflict:api.retainConflictDraft({draft_revision:4,draft:{name_ar:'نسخة الخادم'},approved:{name_ar:'معتمد'}},{name_ar:'تعديل محلي'}),"
            "outcomes:["
            "api.approvalOutcome({published:true,refresh:{accepted:true}}),"
            "api.approvalOutcome({published:false,refresh:{accepted:true}}),"
            "api.approvalOutcome({published:false,refresh:{accepted:false,pending:true}}),"
            "api.approvalOutcome({published:false,refresh:{accepted:false,error:'down'}})"
            "]"
            "})"
        )
        self.assertEqual(result["days"], ["الاثنين", "Friday"])
        self.assertEqual(
            result["sources"],
            ["المصدر: بيانات الشقة المرتبطة", "Source: approved monthly data", ""],
        )
        self.assertEqual(result["conflict"]["draft_revision"], 4)
        self.assertEqual(result["conflict"]["draft"], {"name_ar": "تعديل محلي"})
        self.assertEqual(result["conflict"]["serverDraft"], {"name_ar": "نسخة الخادم"})
        self.assertEqual(result["conflict"]["approved"], {"name_ar": "معتمد"})
        self.assertEqual(
            result["outcomes"],
            ["approval_published", "approval_blocked", "approval_pending", "approval_failed"],
        )

    def test_conflict_handlers_reload_current_revisions_without_dropping_local_edits(self):
        js = JS_FILE.read_text("utf-8")
        for required in (
            "recoverProfileConflict",
            "recoverSettingsConflict",
            "recoverPlaceConflict",
            "renderConflictComparison",
            "serverDraft",
            "conflict-comparison",
            'error.status !== 409',
            'api("/api/monthly/ops/settings")',
            'api("/api/monthly/ops/places")',
        ):
            self.assertIn(required, js)

    def test_javascript_contains_seven_step_survey_and_clear_failure_states(self):
        js = JS_FILE.read_text("utf-8")
        for required in (
            "identity",
            "space",
            "location",
            "content",
            "terms",
            "sources",
            "approval",
            "revision_conflict",
            "401",
            "403",
            "409",
            "503",
            "api/monthly/ops/listings",
        ):
            self.assertIn(required, js)

    def test_deep_link_opens_the_named_listing_and_survey_section(self):
        js = JS_FILE.read_text("utf-8")
        self.assertIn('params.get("id")', js)
        self.assertIn('params.get("section")', js)
        self.assertIn("STEPS.includes", js)

    def test_operations_page_links_to_listing_readiness_with_token_helper(self):
        from monthly_public.ops_page import render_monthly_ops_page

        html = render_monthly_ops_page()
        js = OPS_JS_FILE.read_text("utf-8")
        self.assertIn('id="monthly-catalog-link"', html)
        self.assertIn('href="/monthly/ops/listings"', html)
        self.assertIn("monthly-catalog-link", js)
        self.assertIn('authPath("/monthly/ops/listings"', js)

    def test_readiness_page_links_to_safe_customer_preview(self):
        from monthly_public.catalog_page import render_monthly_catalog_page

        html = render_monthly_catalog_page()
        js = JS_FILE.read_text("utf-8")

        self.assertIn('id="preview-customer-journey"', html)
        self.assertIn("يعرض كل الشقق داخليًا ولا ينشر أي شقة", html)
        self.assertIn('authPath("/monthly/ops/preview"', js)

    def test_save_and_preview_opens_the_same_apartment_without_approving_it(self):
        from monthly_public.catalog_page import render_monthly_catalog_page

        html = render_monthly_catalog_page()
        js = JS_FILE.read_text("utf-8")
        self.assertIn("حفظ ومشاهدة كتجربة عميل", html)
        self.assertIn('data-copy="saveAndPreview"', html)
        self.assertIn('saveAndPreview: "حفظ ومشاهدة كتجربة عميل"', js)
        self.assertIn('saveAndPreview: "Save and view as a customer"', js)
        save_profile = js[
            js.index("async function saveProfile") : js.index(
                "async function approveProfile"
            )
        ]
        self.assertIn('"/monthly/ops/preview/id/"', save_profile)
        self.assertIn("encodeURIComponent(refreshed.id)", save_profile)
        self.assertIn("window.location.assign(authPath(", save_profile)
        self.assertNotIn('"/approve"', save_profile)

    def test_showcase_workspace_manages_a_permanent_link_without_deleting_price(self):
        from monthly_public.catalog_page import render_monthly_catalog_page

        html = render_monthly_catalog_page()
        js = JS_FILE.read_text("utf-8")

        for required in (
            'id="tab-showcases"',
            'id="showcases"',
            'id="showcase-form"',
            'id="showcase-listings"',
            'data-copy="showcasesTab"',
        ):
            self.assertIn(required, html)
        for endpoint in (
            '"/api/monthly/ops/showcases"',
            '"/api/monthly/ops/showcase"',
            '"/draft"',
            '"/approve"',
            '"/price"',
        ):
            self.assertIn(endpoint, js)
        self.assertIn("renderShowcases", js)
        self.assertIn("showcase-membership", CSS_FILE.read_text("utf-8"))
        self.assertIn('"/monthly/ops/preview/showcase/" + value.slug', js)
        self.assertNotIn('authPath(state.showcaseRecord.preview_url', js)

        payload = self._javascript_result(
            "api.buildShowcasePayload({"
            "name_ar:'مجموعة الملقا',name_en:'Al Malqa Collection',slug:'al-malqa',"
            "description_ar:'ثمان شقق في مبنى واحد',description_en:'Eight homes in one building',"
            "image_url:'https://images.example/building.jpg',listing_ids:['101','102'],"
            "fixed_monthly_rate_sar:'12500',fixed_price_enabled:false"
            "})"
        )
        self.assertEqual(payload["listing_ids"], ["101", "102"])
        self.assertEqual(payload["fixed_monthly_rate_sar"], 12500)
        self.assertFalse(payload["fixed_price_enabled"])


class MonthlyCatalogPageBotBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot

        cls.bot = bot

    def test_page_requires_admin_or_operations_access(self):
        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
        try:
            with mock.patch.object(self.bot, "_dash_auth", return_value=False):
                self.assertEqual(
                    run(self.bot._handle_monthly_catalog(FakeRequest())).status, 401
                )
            with mock.patch.object(self.bot, "_dash_auth", return_value=True), mock.patch.object(
                self.bot, "_req_role", return_value="viewer"
            ):
                self.assertEqual(
                    run(self.bot._handle_monthly_catalog(FakeRequest())).status, 403
                )
            with mock.patch.object(self.bot, "_dash_auth", return_value=True), mock.patch.object(
                self.bot, "_req_role", return_value="ops"
            ):
                response = run(
                    self.bot._handle_monthly_catalog(
                        FakeRequest(query={"token": "never-render-this"})
                    )
                )
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                self.assertNotIn("never-render-this", response.text)
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved

    def test_page_and_fingerprinted_assets_are_registered(self):
        from monthly_public.catalog_page import CSS_PATH, JS_PATH

        class Router:
            def __init__(self):
                self.routes = []

            def add_get(self, path, handler):
                self.routes.append(("GET", path, handler))

            def add_post(self, path, handler):
                self.routes.append(("POST", path, handler))

        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
        try:
            router = Router()
            self.bot._register_monthly_v2_only_routes(router)
            paths = {(method, path) for method, path, _handler in router.routes}
            self.assertIn(("GET", "/monthly/ops/listings"), paths)
            self.assertIn(("GET", CSS_PATH), paths)
            self.assertIn(("GET", JS_PATH), paths)
            css = run(self.bot._handle_monthly_catalog_css(FakeRequest(path=CSS_PATH)))
            js = run(self.bot._handle_monthly_catalog_js(FakeRequest(path=JS_PATH)))
            self.assertEqual(css.status, 200)
            self.assertEqual(js.status, 200)
            self.assertEqual(css.headers.get("Cache-Control"), "public, max-age=86400")
            self.assertEqual(js.headers.get("Cache-Control"), "public, max-age=86400")
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved


if __name__ == "__main__":
    unittest.main()
