import asyncio
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class FakeRequest:
    def __init__(self, path):
        self.path = path


class MonthlyFontContractTests(unittest.TestCase):
    def test_every_monthly_shell_loads_one_shared_versioned_font_stylesheet(self):
        from monthly_public.catalog_page import render_monthly_catalog_page
        from monthly_public.fonts import FONT_CSS_PATH, PRELOAD_FONT_PATH
        from monthly_public.ops_page import render_monthly_ops_page
        from monthly_public.page import render_monthly_page

        self.assertRegex(
            FONT_CSS_PATH,
            r"^/monthly/static/monthly_fonts\.[a-z0-9]+\.css$",
        )
        for page in (
            render_monthly_page("home"),
            render_monthly_ops_page(),
            render_monthly_catalog_page(),
        ):
            with self.subTest(title=page[page.index("<title>"):page.index("</title>")]):
                self.assertEqual(page.count('href="%s"' % FONT_CSS_PATH), 1)

        public = render_monthly_page("home")
        self.assertIn('rel="preload"', public)
        self.assertIn('href="%s"' % PRELOAD_FONT_PATH, public)
        self.assertIn('as="font" type="font/woff2" crossorigin', public)

    def test_font_manifest_is_allowlisted_and_every_asset_is_woff2(self):
        from monthly_public.fonts import FONT_ASSETS, PRELOAD_FONT_PATH

        expected = {
            "thmanyah-sans-regular",
            "thmanyah-sans-medium",
            "thmanyah-sans-bold",
            "thmanyah-sans-black",
            "thmanyah-serif-display-bold",
            "thmanyah-serif-display-black",
        }
        self.assertEqual(set(FONT_ASSETS.values()), expected)
        self.assertIn(PRELOAD_FONT_PATH, FONT_ASSETS)
        for route, stem in FONT_ASSETS.items():
            with self.subTest(route=route):
                self.assertRegex(
                    route,
                    r"^/monthly/static/fonts/[a-z-]+\.[a-z0-9]+\.woff2$",
                )
                path = ROOT / "monthly_public" / "static" / "fonts" / (
                    route.rsplit("/", 1)[-1]
                )
                self.assertTrue(path.is_file(), stem)
                self.assertEqual(path.read_bytes()[:4], b"wOF2")

    def test_font_css_maps_existing_weights_without_synthetic_bold(self):
        from monthly_public.fonts import FONT_ASSETS, FONT_CSS_FILE

        css = FONT_CSS_FILE.read_text(encoding="utf-8")
        self.assertEqual(css.count("font-display: swap"), 10)
        for route in FONT_ASSETS:
            self.assertIn('url("%s") format("woff2")' % route, css)
        for weight in (400, 500, 600, 650, 700, 750, 800):
            self.assertIn("font-weight: %s;" % weight, css)
        self.assertIn('font-family: "Thmanyah Sans";', css)
        self.assertIn('font-family: "Thmanyah Serif Display";', css)

    def test_customer_uses_display_headings_and_staff_tools_stay_sans(self):
        public = (ROOT / "monthly_public" / "static" / "monthly.css").read_text(
            encoding="utf-8"
        )
        ops = (ROOT / "monthly_public" / "static" / "monthly_ops.css").read_text(
            encoding="utf-8"
        )
        catalog = (
            ROOT / "monthly_public" / "static" / "monthly_catalog.css"
        ).read_text(encoding="utf-8")

        self.assertIn('--font-sans: "Thmanyah Sans"', public)
        self.assertIn('--font-display: "Thmanyah Serif Display"', public)
        self.assertRegex(public, r"(?s)h1,\s*h2,\s*h3\s*\{.*?var\(--font-display\)")
        for stylesheet in (ops, catalog):
            self.assertIn('--font-sans: "Thmanyah Sans"', stylesheet)
            self.assertIn("font-family: var(--font-sans)", stylesheet)
            self.assertNotIn("var(--font-display)", stylesheet)
        for stylesheet in (public, ops, catalog):
            self.assertNotIn("-apple-system", stylesheet)
            self.assertNotIn("BlinkMacSystemFont", stylesheet)


class MonthlyFontBotBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot

        cls.bot = bot

    def test_font_routes_are_registered_and_return_immutable_woff2(self):
        from monthly_public.fonts import FONT_ASSETS, FONT_CSS_PATH

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
            paths = {path for method, path, _handler in router.routes if method == "GET"}
            self.assertIn(FONT_CSS_PATH, paths)
            self.assertTrue(set(FONT_ASSETS).issubset(paths))

            css = run(self.bot._handle_monthly_font_css(FakeRequest(FONT_CSS_PATH)))
            self.assertEqual(css.status, 200)
            self.assertEqual(css.content_type, "text/css")
            self.assertIn("max-age=31536000", css.headers["Cache-Control"])
            self.assertIn("immutable", css.headers["Cache-Control"])

            route = next(iter(FONT_ASSETS))
            font = run(self.bot._handle_monthly_font(FakeRequest(route)))
            self.assertEqual(font.status, 200)
            self.assertEqual(font.content_type, "font/woff2")
            self.assertEqual(font.body[:4], b"wOF2")
            self.assertIn("max-age=31536000", font.headers["Cache-Control"])
            self.assertIn("immutable", font.headers["Cache-Control"])
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved

    def test_unknown_or_disabled_font_routes_are_closed(self):
        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        try:
            self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
            unknown = run(
                self.bot._handle_monthly_font(
                    FakeRequest("/monthly/static/fonts/not-allowlisted.woff2")
                )
            )
            self.assertEqual(unknown.status, 404)

            self.bot.MONTHLY_PUBLIC_V2 = False
            disabled = run(
                self.bot._handle_monthly_font(
                    FakeRequest("/monthly/static/fonts/disabled.woff2")
                )
            )
            self.assertEqual(disabled.status, 404)
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved


if __name__ == "__main__":
    unittest.main()
