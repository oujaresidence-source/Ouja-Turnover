import asyncio
import html.parser
import json
import os
import re
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(__file__))


def run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class AssetParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []
        self.start_tags = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        self.start_tags.append((tag, values))
        if tag == "link" and values.get("href"):
            self.assets.append(values["href"])
        if tag == "script" and values.get("src"):
            self.assets.append(values["src"])


class MonthlyPublicPageTests(unittest.TestCase):
    def test_arabic_first_shell_has_landmarks_focus_and_live_regions(self):
        from monthly_public.page import render_monthly_page

        page = render_monthly_page("home")

        self.assertIn('<html lang="ar" dir="rtl">', page)
        self.assertIn('href="#monthly-main"', page)
        self.assertRegex(page, r"<header\b")
        self.assertRegex(page, r"<nav\b[^>]*aria-label=")
        self.assertRegex(page, r'<main\b[^>]*id="monthly-main"')
        self.assertRegex(page, r"<footer\b")
        self.assertIn("OUJA MONTHLY · RIYADH", page)
        self.assertIn("بيتك في الرياض، جاهز من أول يوم.", page)
        self.assertIn('id="monthly-status"', page)
        self.assertIn('aria-live="polite"', page)
        self.assertIn('id="monthly-errors"', page)
        self.assertIn('aria-live="assertive"', page)
        self.assertNotIn("maximum-scale", page)
        self.assertNotIn("user-scalable", page)

    def test_shell_loads_only_explicit_versioned_local_assets(self):
        from monthly_public.page import CSS_PATH, JS_PATH, render_monthly_page

        page = render_monthly_page("home")
        parser = AssetParser()
        parser.feed(page)

        self.assertEqual(parser.assets, [CSS_PATH, JS_PATH])
        self.assertRegex(CSS_PATH, r"^/monthly/static/monthly\.[a-z0-9]+\.css$")
        self.assertRegex(JS_PATH, r"^/monthly/static/monthly\.[a-z0-9]+\.js$")
        self.assertFalse(any(value.startswith(("http://", "https://", "//")) for value in parser.assets))

    def test_page_state_is_safe_and_supports_every_approved_deep_link(self):
        from monthly_public.page import page_state, render_monthly_page

        cases = (
            ("home", None, None),
            ("match", None, None),
            ("browse", None, None),
            ("listing", "ouja-al-malqa-1001", None),
            ("listing", None, "1001"),
        )
        for route, slug, listing_id in cases:
            with self.subTest(route=route, slug=slug, listing_id=listing_id):
                state = page_state(route, slug=slug, listing_id=listing_id)
                page = render_monthly_page(route, slug=slug, listing_id=listing_id)
                match = re.search(
                    r'<script id="monthly-page-state" type="application/json">(.*?)</script>',
                    page,
                    re.S,
                )
                self.assertIsNotNone(match)
                self.assertEqual(json.loads(match.group(1)), state)

        with self.assertRaises(ValueError):
            page_state("listing", slug='bad</script><script>alert(1)</script>')
        with self.assertRaises(ValueError):
            page_state("unknown")

    def test_page_source_contains_no_discount_or_placeholder_presentation(self):
        from monthly_public.page import render_monthly_page

        page = render_monthly_page("home").casefold()
        forbidden = (
            "up to 30%",
            "30%",
            "maximum discount",
            "أقصى خصم",
            "خصم يصل",
            "placeholder",
            "lorem ipsum",
        )
        for phrase in forbidden:
            self.assertNotIn(phrase, page)


class MonthlyPublicPageBotBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot

        cls.bot = bot

    def test_v2_is_default_with_explicit_zero_rollback(self):
        with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn(
            'MONTHLY_PUBLIC_V2 = os.environ.get("MONTHLY_PUBLIC_V2", "1") != "0"',
            source,
        )

    def test_v2_page_handler_maps_all_approved_routes_to_one_shell(self):
        from monthly_public.page import CSS_PATH, JS_PATH

        expected = {
            "/monthly": "home",
            "/monthly/": "home",
            "/monthly/search": "browse",
            "/monthly/match": "match",
            "/monthly/id/{lid}": "listing",
            "/monthly/{slug}": "listing",
        }
        registered = self.bot._monthly_public_v2_page_routes()
        self.assertEqual(registered, expected)
        self.assertEqual(
            self.bot._monthly_public_v2_asset_routes(),
            {CSS_PATH: "css", JS_PATH: "js"},
        )

    def test_page_handlers_use_v2_shell_and_explicit_rollback_uses_legacy(self):
        class Request:
            path = "/monthly"
            query_string = ""
            match_info = {}

            class URL:
                @staticmethod
                def origin():
                    return "http://127.0.0.1:8000"

            url = URL()

        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        try:
            self.bot.MONTHLY_ENABLED = True
            self.bot.MONTHLY_PUBLIC_V2 = True
            with mock.patch.object(self.bot, "_monthly_public_page_html", return_value="V2") as v2:
                response = run(self.bot._handle_monthly(Request()))
                self.assertEqual(response.text, "V2")
                v2.assert_called_once()

            self.bot.MONTHLY_PUBLIC_V2 = False
            with mock.patch.object(self.bot, "_monthly_render", return_value="LEGACY") as legacy:
                response = run(self.bot._handle_monthly(Request()))
                self.assertEqual(response.text, "LEGACY")
                legacy.assert_called_once()
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved

    def test_listing_api_adapter_can_resolve_an_approved_slug_deep_link(self):
        class Request:
            query = {"lookup": "slug", "lang": "en"}

        parsed = self.bot._monthly_v2_listing_query(
            Request(), "ouja-al-malqa-1001"
        )

        self.assertEqual(
            parsed,
            {"slug": "ouja-al-malqa-1001", "lang": "en"},
        )

    def test_legacy_rollback_renderer_is_browse_safe_and_has_no_discount_pitch(self):
        risky_listing = {
            "id": "1001",
            "slug": "ouja-1001",
            "name_ar": "عوجا | الملقا",
            "name_en": "Ouja | Al Malqa",
            "area": "الملقا",
            "cover": "https://images.example.test/1001.jpg",
            "images": ["https://images.example.test/1001.jpg"],
            "m_before": 15000,
            "m_after": 12000,
            "m_pct": 0.2,
            "ceiling": 0.3,
            "quote": {"before": 15000, "after": 12000, "pct": 0.2},
        }

        for route, listing in (("home", None), ("search", None), ("listing", risky_listing)):
            with self.subTest(route=route), mock.patch.object(
                self.bot, "_monthly_public_snapshot", None
            ):
                rendered = self.bot._monthly_render(route, listing).casefold()
                for phrase in (
                    "up to",
                    "maximum discount",
                    "reference price",
                    "قبل الخصم",
                    "أقصى خصم",
                    "خصم يصل",
                    "m_before",
                    "m_after",
                    "q.before",
                    "q.after",
                    "<s>",
                    "line-through",
                ):
                    self.assertNotIn(phrase, rendered)
                self.assertNotIn("15000", rendered)
                self.assertNotIn("12000", rendered)
                if route == "listing":
                    self.assertNotIn("عوجا | الملقا", rendered)
                self.assertIn("/monthly/search", rendered)


if __name__ == "__main__":
    unittest.main()
