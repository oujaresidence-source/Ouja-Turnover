import asyncio
import inspect
import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
CSS_FILE = ROOT / "monthly_public" / "static" / "monthly_ops.css"
JS_FILE = ROOT / "monthly_public" / "static" / "monthly_ops.js"


def run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class FakeRequest:
    def __init__(self, path="/monthly/ops", method="GET", query=None):
        self.path = path
        self.method = method
        self.query = query or {}
        self.headers = {}
        self.cookies = {}


class MonthlyOpsPageContractTests(unittest.TestCase):
    def _module(self):
        try:
            from monthly_public import ops_page
        except (ImportError, ModuleNotFoundError):
            self.fail("monthly operations page module is missing")
        return ops_page

    def test_arabic_first_shell_contains_no_auth_token_or_operational_data(self):
        module = self._module()
        html = module.render_monthly_ops_page()

        self.assertIn('<html lang="ar" dir="rtl">', html)
        self.assertIn('id="monthly-ops-main"', html)
        self.assertIn('id="ops-language"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('autocomplete="off"', html)
        self.assertIn('name="lead_reference"', html)
        self.assertIn('name="discount_requested"', html)
        self.assertIn('name="outcome"', html)
        self.assertIn('name="lost_reason"', html)
        self.assertIn(module.CSS_PATH, html)
        self.assertIn(module.JS_PATH, html)
        self.assertNotIn("token=", html)
        self.assertNotIn("session_id", html)
        self.assertNotIn("lead_reference\":", html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)

    def test_page_and_assets_define_every_required_operations_surface(self):
        module = self._module()
        source = module.render_monthly_ops_page() + JS_FILE.read_text(encoding="utf-8")
        required = (
            "health", "funnel", "launch", "refresh", "received", "valid",
            "blocked", "published", "calendar", "price", "whatsapp",
            "working_hours", "content_conflicts", "licence_expiry",
            "contract_4_6_months", "analytics", "leads", "red_blockers",
            "landing_view", "entry_route_choice", "matcher_start",
            "matcher_answer", "matcher_completion", "results_view",
            "result_impression", "listing_view", "whatsapp_click",
            "lead_created", "team_response", "booked", "lost",
            "response_time_minutes", "discount_request_rate",
            "common_purposes", "requested_places", "duration_bands",
            "lost_reasons",
        )
        for name in required:
            with self.subTest(name=name):
                self.assertIn(name, source)

    def test_static_assets_are_local_accessible_and_privacy_minimising(self):
        self.assertTrue(CSS_FILE.exists())
        self.assertTrue(JS_FILE.exists())
        css = CSS_FILE.read_text(encoding="utf-8")
        js = JS_FILE.read_text(encoding="utf-8")

        for token in ("http://", "https://", "@import", "url("):
            self.assertNotIn(token, css)
        for token in (
            "http://", "https://", "localStorage", "sessionStorage",
            "document.cookie", "session_id", ".sessions", "innerHTML",
            "WebSocket", "XMLHttpRequest", "sendBeacon", "api_get(",
            "Hostaway", "hostaway",
        ):
            self.assertNotIn(token, js)
        self.assertIn(":focus-visible", css)
        self.assertIn("min-height: 44px", css)
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("overflow-x: clip", css)
        self.assertIn("@media (max-width: 540px)", css)
        self.assertIn("credentials: \"same-origin\"", js)
        self.assertIn("60000", js)

        checked = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_js_helpers_preserve_query_auth_and_validate_outcome_payloads(self):
        script = """
const ui = require(%s);
const output = {
  auth: ui.authPath('/api/monthly/ops/health', 'https://ouja.test/monthly/ops?token=abc%%2B123'),
  cookie: ui.authPath('/api/monthly/ops/health', 'https://ouja.test/monthly/ops'),
  ratioZero: ui.safeRatio(3, 0),
  ratio: ui.safeRatio(1, 4),
  nullTracked: ui.isTrackedNumber(null),
  zeroTracked: ui.isTrackedNumber(0),
  responseYes: ui.buildResponsePayload('ojm-20260825-abc', 'yes'),
  responseNo: ui.buildResponsePayload('OJM-20260825-ABC', 'no'),
  responseUnknown: ui.buildResponsePayload('OJM-20260825-ABC', 'unknown'),
  booked: ui.buildOutcomePayload('OJM-20260825-ABC', 'booked', ''),
  lost: ui.buildOutcomePayload('OJM-20260825-ABC', 'lost', 'price')
};
try { ui.buildOutcomePayload('OJM-20260825-ABC', 'lost', ''); }
catch (error) { output.lostError = error.message; }
try { ui.buildOutcomePayload('bad ref', 'booked', ''); }
catch (error) { output.refError = error.message; }
process.stdout.write(JSON.stringify(output));
""" % json.dumps(str(JS_FILE))
        result = subprocess.run(
            ["node", "-e", script], cwd=ROOT, capture_output=True, check=True, text=True
        )
        value = json.loads(result.stdout)

        self.assertEqual(value["auth"], "/api/monthly/ops/health?token=abc%2B123")
        self.assertEqual(value["cookie"], "/api/monthly/ops/health")
        self.assertIsNone(value["ratioZero"])
        self.assertEqual(value["ratio"], 0.25)
        self.assertFalse(value["nullTracked"])
        self.assertTrue(value["zeroTracked"])
        self.assertEqual(value["responseYes"], {
            "lead_reference": "OJM-20260825-ABC", "discount_requested": True,
        })
        self.assertEqual(value["responseNo"], {
            "lead_reference": "OJM-20260825-ABC", "discount_requested": False,
        })
        self.assertEqual(value["responseUnknown"], {
            "lead_reference": "OJM-20260825-ABC",
        })
        self.assertEqual(value["booked"], {
            "lead_reference": "OJM-20260825-ABC", "outcome": "booked",
        })
        self.assertEqual(value["lost"], {
            "lead_reference": "OJM-20260825-ABC", "outcome": "lost",
            "lost_reason": "price",
        })
        self.assertTrue(value["lostError"])
        self.assertTrue(value["refError"])

    def test_javascript_uses_controlled_options_and_never_auto_refreshes_dirty_form(self):
        js = JS_FILE.read_text(encoding="utf-8")
        for value in (
            "work", "family", "treatment", "visit", "price",
            "unavailable_dates", "location", "space", "contract_terms",
            "no_response", "booked_elsewhere", "other", "yes", "no",
            "unknown",
        ):
            self.assertIn('"%s"' % value, js)
        self.assertIn("formDirty", js)
        self.assertIn("if (!state.formDirty)", js)
        self.assertIn("refreshAll", js)
        self.assertIn("disabled", js)


class MonthlyOpsBotBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot
        cls.bot = bot

    def test_ops_page_requires_v2_auth_and_admin_or_ops_role(self):
        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
        try:
            with mock.patch.object(self.bot, "_dash_auth", return_value=False):
                response = run(self.bot._handle_monthly_ops(FakeRequest()))
                self.assertEqual(response.status, 401)
            with mock.patch.object(self.bot, "_dash_auth", return_value=True), mock.patch.object(
                self.bot, "_req_role", return_value="viewer"
            ):
                response = run(self.bot._handle_monthly_ops(FakeRequest()))
                self.assertEqual(response.status, 403)
            for role in ("admin", "ops"):
                with self.subTest(role=role), mock.patch.object(
                    self.bot, "_dash_auth", return_value=True
                ), mock.patch.object(self.bot, "_req_role", return_value=role):
                    response = run(self.bot._handle_monthly_ops(FakeRequest(query={"token": "do-not-render"})))
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                    self.assertNotIn("do-not-render", response.text)
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved

    def test_disabled_v2_closes_page_and_assets_and_does_not_register_them(self):
        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        try:
            for enabled, v2 in ((False, True), (True, False), (False, False)):
                self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = enabled, v2
                self.assertEqual(run(self.bot._handle_monthly_ops(FakeRequest())).status, 404)
                self.assertEqual(run(self.bot._handle_monthly_ops_css(FakeRequest())).status, 404)
                self.assertEqual(run(self.bot._handle_monthly_ops_js(FakeRequest())).status, 404)

                class Router:
                    def __init__(self):
                        self.routes = []

                    def add_get(self, path, handler):
                        self.routes.append(("GET", path, handler))

                    def add_post(self, path, handler):
                        self.routes.append(("POST", path, handler))

                router = Router()
                self.bot._register_monthly_v2_only_routes(router)
                self.assertNotIn("/monthly/ops", [row[1] for row in router.routes])
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved

    def test_v2_registration_includes_page_and_cacheable_data_free_assets(self):
        from monthly_public.ops_page import CSS_PATH, JS_PATH

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
            self.assertIn(("GET", "/monthly/ops"), paths)
            self.assertIn(("GET", CSS_PATH), paths)
            self.assertIn(("GET", JS_PATH), paths)
            css = run(self.bot._handle_monthly_ops_css(FakeRequest(path=CSS_PATH)))
            js = run(self.bot._handle_monthly_ops_js(FakeRequest(path=JS_PATH)))
            self.assertEqual(css.headers.get("Cache-Control"), "public, max-age=86400")
            self.assertEqual(js.headers.get("Cache-Control"), "public, max-age=86400")
            self.assertNotIn("token", css.text.lower())
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved

    def test_ops_handlers_and_page_never_call_customer_or_provider_sources(self):
        source = inspect.getsource(self.bot._handle_monthly_ops)
        source += inspect.getsource(self.bot._handle_monthly_ops_css)
        source += inspect.getsource(self.bot._handle_monthly_ops_js)
        for token in (
            "api_get(", "api_post(", "requests.", "_gw_sync(",
            "_mcal_refresh_sync(", "_mengine_refresh_sync(",
        ):
            self.assertNotIn(token, source)

    def test_dashboard_monthly_block_links_to_ops_and_has_no_discount_pitch(self):
        html = self.bot.DASHBOARD_HTML
        start = html.index("function gwOverview()")
        end = html.index("async function gwListings()", start)
        monthly = html[start:end]
        self.assertIn("/monthly/ops", monthly)
        self.assertIn("mOpenMonthlyOps", monthly)
        for phrase in (
            "before/after price", "السعر قبل وبعد الخصم", "Discount settings",
            "إعدادات الخصم", "Standard discount", "الخصم القياسي",
            "Max teaser", "أقصى خصم", "up to 30% off", "خصم يصل ٣٠٪",
        ):
            self.assertNotIn(phrase, monthly)


if __name__ == "__main__":
    unittest.main()
