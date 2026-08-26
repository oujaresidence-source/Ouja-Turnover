# -*- coding: utf-8 -*-
"""
The v2 page (plan Tasks 6+11+12): version routing, token completeness, the
drawers as real routes, and the guard on every render.

Run: python3 -m unittest tests.test_cp_page_v2
"""
import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cp import admin_store, guard, page_v2  # noqa: E402
from tests.test_cp_admin import make_client, _Disk  # noqa: E402


def render(**kw):
    kw.setdefault("base", "https://oujares.com")
    return page_v2.render_v2(**kw)


class TokensAndGuard(unittest.TestCase):
    def test_default_render_fills_everything(self):
        html = render()
        self.assertEqual(page_v2.remaining_placeholders(html), [])

    def test_default_render_is_guard_clean(self):
        render()   # check=True raises on a hit

    def test_every_more_page_renders_clean_and_full(self):
        for key in page_v2.DRAWER_KEYS:
            with self.subTest(key=key):
                html = render(more_key=key)
                self.assertEqual(page_v2.remaining_placeholders(html), [],
                                 "unfilled tokens on /more/%s" % key)

    def test_poisoned_copy_override_cannot_render(self):
        with self.assertRaises(guard.DisclosureError):
            render(sections={"copy": {"hero_h1_tail": "حققنا 7,669,457 ريال"}})

    def test_no_multiplier_glyphs_in_the_comparison(self):
        """The v6 design dropped the ×-multiples; none may sneak back."""
        html = render()
        duel = html.split('class="duel')[1].split("</div>\n    <div")[0]
        self.assertNotIn("×", duel)

    def test_no_compound_names_on_the_public_page(self):
        html = render()
        for name in ("الماجدية", "ديار 20", "جاده 33", "هيو ريزيدنس",
                     "العجلان", "Calma", "كالما"):
            with self.subTest(name=name):
                self.assertNotIn(name, html)

    def test_figures_render_as_approved(self):
        html = render()
        for fig in ("8,114", "13,093", "76.9%", "4.77", "2,633", "94%",
                    "59.3%", "63.4%", "478", "644 · 554", "2.3", "66,000"):
            with self.subTest(fig=fig):
                self.assertIn(fig, html)

    def test_the_font_switcher_is_gone(self):
        html = render()
        self.assertNotIn("fontsw", html)
        self.assertNotIn("data-font", html)
        self.assertNotIn("ouja-font", html)   # its localStorage key

    def test_no_google_fonts_on_the_live_page(self):
        self.assertNotIn("fonts.googleapis.com", render())

    def test_the_form_posts_to_the_real_endpoint(self):
        html = render()
        self.assertIn('action="/api/cp/lead"', html)
        self.assertIn('name="company_url"', html)

    def test_booking_link_button_renders_only_when_set(self):
        self.assertNotIn("اختر الوقت من التقويم", render())
        html = render(sections={"contacts": {
            "booking_link": "https://calendly.com/ouja",
            "booking_modes": {"online": True, "office": True}}})
        self.assertIn("اختر الوقت من التقويم", html)
        self.assertIn("https://calendly.com/ouja", html)

    def test_disabling_office_mode_removes_its_radio(self):
        html = render(sections={"contacts": {
            "booking_modes": {"online": True, "office": False}}})
        self.assertNotIn('value="office"', html)

    def test_json_ld_present_without_figures(self):
        html = render()
        start = html.index('application/ld+json')
        blob = html[start:html.index("</script>", start)]
        self.assertIn("Organization", blob)
        for figure in ("8,114", "76.9", "7,669,457"):
            self.assertNotIn(figure, blob)

    def test_copy_override_swaps_the_default(self):
        html = render(sections={"copy": {"hero_h1_tail": "وحداتنا مختلفة."}})
        self.assertIn("وحداتنا مختلفة.", html)
        self.assertNotIn("وحداتنا لا.", html)


class ShowcaseRender(unittest.TestCase):
    UNITS = [{"listing_id": "487708", "name_ar": "جاباندي",
              "bedrooms_label_ar": "غرفتا نوم", "line_ar": "سينما منزلية",
              "cover_url": "", "hidden": False}]

    def test_configured_units_render_with_photos(self):
        html = render(sections={"showcase": {"units": self.UNITS}},
                      photos={"487708": {"photo": "/elite/img?u=x&w=1024",
                                         "srcset": "/elite/img?u=x&w=640 640w"}})
        self.assertIn("/elite/img?u=x&amp;w=1024", html)
        self.assertIn("جاباندي", html)

    def test_inactive_unit_is_skipped(self):
        units = [dict(self.UNITS[0], inactive=True)]
        html = render(sections={"showcase": {"units": units}}, photos={})
        # falls back to the mock's default tiles — the unit itself is absent
        self.assertNotIn("سينما منزلية</div>", html)

    def test_empty_showcase_keeps_the_mock_defaults(self):
        html = render()
        self.assertIn("صورة الوحدة", html)


class VersionRouting(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.disk = _Disk()
        self.client, _ = make_client(self.loop, disk=self.disk)

    def tearDown(self):
        self.loop.run_until_complete(self.client.close())
        self.loop.close()
        os.environ.pop("CP_V2", None)

    def _get(self, path):
        r = self.loop.run_until_complete(self.client.get(path))
        return r, self.loop.run_until_complete(r.text())

    def test_default_is_v1(self):
        r, html = self._get("/cp/ar")
        self.assertEqual(r.status, 200)
        self.assertIn("dir=\"rtl\"", html)
        self.assertNotIn('id="drawer"', html)   # the drawer exists only in v2

    def test_preview_token_serves_v2(self):
        r, html = self._get("/cp/ar?v=2")
        self.assertEqual(r.status, 200)
        self.assertIn('id="drawer"', html)

    def test_published_v2_serves_v2_publicly(self):
        store = admin_store.Store(load_json=self.disk.load, save_json=self.disk.save)
        store.publish("v2", by="admin1")
        r, html = self._get("/cp/ar")
        self.assertIn('id="drawer"', html)

    def test_env_flag_forces_v2(self):
        os.environ["CP_V2"] = "1"
        r, html = self._get("/cp/ar")
        self.assertIn('id="drawer"', html)

    def test_more_routes_serve_and_unknown_404s(self):
        for key in page_v2.DRAWER_KEYS:
            r, html = self._get("/cp/ar/more/" + key)
            self.assertEqual(r.status, 200, key)
            self.assertIn("عوجا", html)
        r, _ = self._get("/cp/ar/more/evil")
        self.assertEqual(r.status, 404)

    def test_published_edits_stay_frozen_until_republished(self):
        store = admin_store.Store(load_json=self.disk.load, save_json=self.disk.save)
        store.update_section("copy", {"hero_h1_tail": "نسخة منشورة."}, by="u")
        store.publish("v2", by="admin1")
        store.update_section("copy", {"hero_h1_tail": "مسودة جديدة."}, by="u")
        _, public = self._get("/cp/ar")
        self.assertIn("نسخة منشورة.", public)
        self.assertNotIn("مسودة جديدة.", public)
        _, preview = self._get("/cp/ar?v=2")
        self.assertIn("مسودة جديدة.", preview)


if __name__ == "__main__":
    unittest.main()


class DocumentShellAndContrast(unittest.TestCase):
    """Findings from driving a real browser, locked so they cannot regress.

    The approved mock was authored to sit inside a preview wrapper: it has no
    <html> element, so the live page had no lang and no dir. And three neutral
    tokens measured below 4.5:1 on their own grounds at 13-14px.
    """

    def test_the_page_is_a_document(self):
        html = render()
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn('<html lang="ar" dir="rtl">', html)
        for tag in ("head", "body", "html"):
            with self.subTest(tag=tag):
                self.assertIn("</%s>" % tag, html)

    def test_more_pages_are_documents_too(self):
        for key in page_v2.DRAWER_KEYS:
            with self.subTest(key=key):
                html = render(more_key=key)
                self.assertIn('<html lang="ar" dir="rtl">', html)
                self.assertIn("</html>", html)

    def test_tags_balance(self):
        import re
        html = render()
        for tag in ("html", "head", "body", "a", "button", "div", "section", "form"):
            with self.subTest(tag=tag):
                self.assertEqual(len(re.findall(r"<%s\b" % tag, html)),
                                 len(re.findall(r"</%s>" % tag, html)),
                                 "unbalanced <%s> — an unclosed tag swallows the "
                                 "rest of the document" % tag)

    def test_more_controls_are_closed_anchors(self):
        """They were <button>s; swapping only the opening tag left </button>
        behind and the anchor never closed — the submit button ended up inside
        it and a real click did nothing."""
        html = render()
        self.assertEqual(html.count('<a class="more"'), 7)
        self.assertEqual(html.count('class="more"'), 7)

    def test_contrast_tokens_meet_the_floor(self):
        def lum(h):
            h = h.lstrip("#")
            c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
                 for x in c]
            return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

        def ratio(a, b):
            la, lb = lum(a), lum(b)
            return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

        html = render()
        self.assertIn("--mute:#676057;", html)
        self.assertIn("--mkt:#6F685D;", html)
        self.assertGreaterEqual(ratio("#676057", "#EFE9DE"), 4.5)
        self.assertGreaterEqual(ratio("#676057", "#E4DCCB"), 4.5)
        self.assertGreaterEqual(ratio("#6F685D", "#FFFFFF"), 4.5)

    def test_faint_is_not_used_on_a_light_ground(self):
        """--faint is a light-on-dark token; on beige it measures 2.27:1."""
        html = render()
        self.assertNotIn("footer h4{font-size:12px;letter-spacing:.04em;color:var(--faint)", html)
        self.assertNotIn('<span style="color:var(--faint)">النسخة', html)
        self.assertNotIn("gap:10px;font-size:13px;color:var(--faint)}", html)

    def test_unit_photos_are_constrained(self):
        """A real 1024px <img> inside .ph overflowed a 390px phone by 14px."""
        self.assertIn(".unit .ph img{display:block;width:100%;height:100%;"
                      "object-fit:cover}", render())


class BrandLogo(unittest.TestCase):
    """One upload drives the header, the footer, the tab icon and the share
    card. Without a logo the page falls back to the design's placeholder mark
    rather than showing a broken image."""

    def test_logo_renders_in_header_and_footer(self):
        html = render(has_logo=True)
        self.assertEqual(html.count("/cp/logo.png"), 2)

    def test_logo_has_explicit_height_so_it_cannot_shift_the_header(self):
        html = render(has_logo=True)
        self.assertIn('height="21"', html)
        self.assertIn('height="19"', html)

    def test_without_a_logo_the_design_mark_is_used(self):
        html = render(has_logo=False)
        self.assertEqual(html.count('viewBox="0 0 34 22"'), 2)
        self.assertNotIn("/cp/logo.png", html)

    def test_the_mock_placeholder_title_is_gone(self):
        self.assertNotIn("مكان الشعار الرسمي", render(has_logo=True))
        self.assertNotIn("مكان الشعار الرسمي", render(has_logo=False))
