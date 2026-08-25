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

    def test_operations_page_links_to_listing_readiness_with_token_helper(self):
        from monthly_public.ops_page import render_monthly_ops_page

        html = render_monthly_ops_page()
        js = OPS_JS_FILE.read_text("utf-8")
        self.assertIn('id="monthly-catalog-link"', html)
        self.assertIn('href="/monthly/ops/listings"', html)
        self.assertIn("monthly-catalog-link", js)
        self.assertIn('authPath("/monthly/ops/listings"', js)


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
