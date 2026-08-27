import json
import os
import re
import subprocess
import unittest


ROOT = os.path.dirname(os.path.dirname(__file__))


class MonthlyShowcasePageTest(unittest.TestCase):
    def test_showcase_hero_uses_only_approved_or_real_home_images(self):
        script = """
          const app = require('./monthly_public/static/monthly.js');
          const select = app.showcaseHeroImage;
          const output = typeof select === 'function' ? {
            approved: select(
              {image_url: 'https://images.ouja.test/building.jpg'},
              [{cover: {url: 'https://images.ouja.test/home.jpg'}}]
            ),
            fallback: select(
              {image_url: 'javascript:alert(1)'},
              [{cover: {url: 'data:image/png;base64,AA'}}, {cover: {url: 'https://images.ouja.test/real-home.jpg'}}]
            ),
            missing: select({}, [{cover: {url: 'javascript:alert(1)'}}, {}])
          } : {exported: false};
          process.stdout.write(JSON.stringify(output));
        """
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            json.loads(result.stdout),
            {
                "approved": "https://images.ouja.test/building.jpg",
                "fallback": "https://images.ouja.test/real-home.jpg",
                "missing": "",
            },
        )

    def test_showcase_hero_image_precedes_copy_and_fails_closed(self):
        js_path = os.path.join(ROOT, "monthly_public", "static", "monthly.js")
        css_path = os.path.join(ROOT, "monthly_public", "static", "monthly.css")
        with open(js_path, encoding="utf-8") as handle:
            source = handle.read()
        with open(css_path, encoding="utf-8") as handle:
            styles = handle.read()
        showcase = source[
            source.index("async function renderShowcase"):
            source.index("async function renderHome")
        ]

        self.assertIn("showcaseHeroImage(showcase, homes)", showcase)
        self.assertIn("append(hero, media, words)", showcase)
        self.assertIn('image.addEventListener("error"', showcase)
        self.assertIn("media.hidden = true", showcase)
        media = styles[
            styles.index(".showcase-hero-media {"):
            styles.index(".showcase-offer {")
        ]
        self.assertIn("aspect-ratio: 16 / 7", media)
        self.assertIn("object-fit: cover", media)

    def test_showcase_route_is_explicit_and_precedes_listing_slug(self):
        from monthly_public.page import PAGE_ROUTES

        paths = list(PAGE_ROUTES)
        self.assertEqual(PAGE_ROUTES["/monthly/showcase/{showcase_slug}"], "showcase")
        self.assertLess(
            paths.index("/monthly/showcase/{showcase_slug}"),
            paths.index("/monthly/{slug}"),
        )

    def test_showcase_page_state_is_safe_and_separate_from_listing_state(self):
        from monthly_public.page import page_state, render_monthly_page

        state = page_state("showcase", showcase_slug="one-building")
        page = render_monthly_page("showcase", showcase_slug="one-building")
        match = re.search(
            r'<script id="monthly-page-state" type="application/json">(.*?)</script>',
            page,
            re.S,
        )

        self.assertEqual(json.loads(match.group(1)), state)
        self.assertEqual(state["showcase_slug"], "one-building")
        self.assertIsNone(state["slug"])
        self.assertIsNone(state["listing_id"])
        with self.assertRaises(ValueError):
            page_state("showcase", showcase_slug="Bad Slug")
        with self.assertRaises(ValueError):
            page_state("home", showcase_slug="one-building")

    def test_javascript_loads_showcase_and_keeps_context_through_handoff(self):
        path = os.path.join(ROOT, "monthly_public", "static", "monthly.js")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()

        required = (
            'showcase: "/api/monthly/showcase"',
            "function renderShowcase()",
            "showcase_context: runtime.showcaseContext",
            'track("showcase_view"',
            'track("showcase_listing_impression"',
            'track("showcase_listing_view"',
            'params.set("sc", context)',
        )
        for value in required:
            self.assertIn(value, source)
        self.assertIn('showcase: "/api/monthly/ops/preview/showcase"', source)
        self.assertIn("item.showcase_monthly_rate_sar", source)

    def test_showcase_copy_is_bilingual_and_has_no_discount_claims(self):
        script = """
          const app = require('./monthly_public/static/monthly.js');
          const keys = ['showcaseKicker','showcaseFixedPrice','showcaseListingPrice',
                        'showcaseHomes','showcaseEmptyTitle','showcaseEmptyText'];
          for (const lang of ['ar', 'en']) {
            for (const key of keys) {
              if (!app.COPY[lang][key]) throw new Error(lang + ':' + key);
            }
          }
          process.stdout.write(JSON.stringify({
            ar: app.showcaseListingPath({id: '101', slug: 'home-101'}, 'ctx.ABC'),
            en: app.showcaseListingPath({id: '101'}, 'ctx.ABC')
          }));
        """
        result = subprocess.run(
            ["node", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        paths = json.loads(result.stdout)
        self.assertEqual(paths["ar"], "/monthly/home-101?sc=ctx.ABC")
        self.assertEqual(paths["en"], "/monthly/id/101?sc=ctx.ABC")

        with open(
            os.path.join(ROOT, "monthly_public", "static", "monthly.js"),
            encoding="utf-8",
        ) as handle:
            source = handle.read().casefold()
        for phrase in ("up to 30%", "maximum discount", "خصم يصل", "أقصى خصم"):
            self.assertNotIn(phrase, source)


if __name__ == "__main__":
    unittest.main()
