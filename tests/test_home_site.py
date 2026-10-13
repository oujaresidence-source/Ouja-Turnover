# -*- coding: utf-8 -*-
"""
oujares.com company homepage (site_home/) — the page business.sa reviews.

Locks the brief's nine requirements plus the structural rules behind them:
  * the identity values are EXACTLY the commercial-register values,
  * no booking / no payment / no "book direct" / no unit count anywhere,
  * the travel licence and business.sa badge stay hidden until filled in,
  * the pages never touch Hostaway, a database or a thread pool (CLAUDE.md trap 6),
  * bot.py moved the plain-text health check to /healthz and gave "/" to the site.

Run:  python3 -m unittest tests.test_home_site
"""
import asyncio
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import site_home  # noqa: E402
from site_home import SITE_IDENTITY  # noqa: E402

EMAIL = "info@oujares.com"           # business.sa request EACR110675
OLD_EMAIL = "oujaresidence@gmail.com"  # bot.py's OUJA_CONTACT_EMAIL — must never reach the site
MOBILE, MOBILE_TEL = "0505783355", "tel:+966505783355"
SUPPORT, SUPPORT_TEL = "0115165916", "tel:+966115165916"
SOCIAL = {
    "tiktok_url": "https://www.tiktok.com/@oujares",
    "instagram_url": "https://www.instagram.com/oujares/",
    "x_url": "https://x.com/Oujares",
    "snapchat_url": "https://snapchat.com/t/5OPZpUKY",
    "whatsapp_url": "https://wa.me/966115165916",
}
NO_SOCIAL = dict.fromkeys(SOCIAL, "")
LEGAL_AR = "شركة أحمد مساعد بن نصار"
LEGAL_EN = "AHMED MUSAED NASSAR Company"
NO_BOOKING_AR = "لا يتم أي حجز أو دفع عبر هذا الموقع"
NO_BOOKING_EN = "No booking or payment takes place on this website"
PAGES_AR = ("/", "/privacy", "/terms", "/contact")
PAGES_EN = ("/en", "/en/privacy", "/en/terms", "/en/contact")
SOCIAL_HOSTS = ("tiktok.com", "instagram.com", "snapchat.com", "facebook.com", "x.com/", "twitter.com", "wa.me/")


def _app(with_bot=False):
    """The site's own routes; with_bot=True adds bot.py's security middleware,
    /healthz, robots.txt and sitemap.xml exactly as start_web_server wires them."""
    site_home.wire({"web": web, "email": OLD_EMAIL, "whatsapp": ""})
    if not with_bot:
        app = web.Application()
    else:
        import bot
        app = web.Application(middlewares=[bot._security_headers_mw])
        app.router.add_get("/healthz", bot._handle_health)
        app.router.add_get("/robots.txt", bot._handle_robots)
        app.router.add_get("/sitemap.xml", bot._handle_sitemap)
    site_home.register_routes(app)
    return app


def fetch(path, with_bot=False, raw=False):
    async def go():
        async with TestClient(TestServer(_app(with_bot))) as c:
            r = await c.get(path, allow_redirects=False)
            return r.status, r.headers, (await r.read() if raw else await r.text())
    return asyncio.run(go())


def _main_part(html):
    """Everything before the shared footer — where a call-to-action would live."""
    return html.split('<footer', 1)[0]


class IdentityIsTheRegister(unittest.TestCase):
    """Section 3: every value matches what business.sa displays — no drift, ever."""

    def test_locked_values(self):
        self.assertEqual(SITE_IDENTITY["legal_name_ar"], LEGAL_AR)
        self.assertEqual(SITE_IDENTITY["legal_name_en"], LEGAL_EN)
        self.assertEqual(SITE_IDENTITY["brand_ar"], "عوجا ريزيدنس")
        self.assertEqual(SITE_IDENTITY["brand_en"], "Ouja Residence")
        self.assertEqual(SITE_IDENTITY["cr_number"], "7050158810")
        self.assertEqual(SITE_IDENTITY["national_address_short"], "RGMB7388")
        self.assertEqual(SITE_IDENTITY["address_ar"],
                         "مبنى 7388، الرقم الإضافي 3052، طريق التخصصي، حي المعذر الشمالي، الرياض 12314")
        self.assertEqual(SITE_IDENTITY["address_unit_ar"], "مبنى نقوه، الدور الثاني، مكتب 16")
        self.assertEqual(SITE_IDENTITY["fal_marketing_no"], "1200050611")
        self.assertEqual(SITE_IDENTITY["fal_management_no"], "2200005540")
        self.assertEqual(SITE_IDENTITY["travel_licence_category_ar"], "وكالة السفر والسياحة")

    def test_pending_slots_ship_empty(self):
        for k in ("travel_licence_no", "business_sa_cert_url", "business_sa_badge_img"):
            self.assertEqual(SITE_IDENTITY[k], "", k)


class HomeArabic(unittest.TestCase):
    """Test 1: / is the company homepage, not the debug line."""

    def setUp(self):
        self.status, self.headers, self.html = fetch("/")

    def test_ok_html(self):
        self.assertEqual(self.status, 200)
        self.assertIn("text/html", self.headers.get("Content-Type", ""))

    def test_identity_and_links(self):
        for needle in (LEGAL_AR, "7050158810", "RGMB7388", EMAIL,
                       'href="/privacy"', 'href="/terms"', 'href="/contact"', 'href="/apartments"',
                       'href="/monthly"', 'href="/business"', "1200050611", "2200005540"):
            self.assertIn(needle, self.html, needle)

    def test_not_the_health_text(self):
        self.assertNotIn("Ouja bot is up", self.html)


class HomeEnglish(unittest.TestCase):
    """Test 2: /en mirrors / in English; both carry lang/dir and hreflang."""

    def test_en_mirrors(self):
        status, headers, html = fetch("/en")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        for needle in (LEGAL_EN, "7050158810", "RGMB7388", EMAIL,
                       'href="/en/privacy"', 'href="/en/terms"', 'href="/en/contact"',
                       'href="/apartments"', "1200050611", "2200005540"):
            self.assertIn(needle, html, needle)
        self.assertIn('lang="en" dir="ltr"', html)
        self.assertNotIn("Ouja bot is up", html)

    def test_lang_dir_and_hreflang(self):
        _, _, ar = fetch("/")
        _, _, en = fetch("/en")
        self.assertIn('lang="ar" dir="rtl"', ar)
        for html in (ar, en):
            self.assertIn('hreflang="ar" href="https://oujares.com/"', html)
            self.assertIn('hreflang="en" href="https://oujares.com/en"', html)
            self.assertIn('hreflang="x-default"', html)

    def test_trailing_slash_redirects(self):
        status, headers, _ = fetch("/en/")
        self.assertIn(status, (301, 308))
        self.assertEqual(headers.get("Location"), "/en")


class Health(unittest.TestCase):
    """Test 3: the plain-text health check lives on at /healthz."""

    def test_healthz_keeps_the_old_text(self):
        status, _, body = fetch("/healthz", with_bot=True)
        self.assertEqual(status, 200)
        self.assertEqual(body, "Ouja bot is up")

    def test_bot_wires_healthz_and_hands_root_to_the_site(self):
        src = (ROOT / "bot.py").read_text(encoding="utf-8")
        for needle, want in (('app.router.add_get("/healthz", _handle_health)', True),
                             ('app.router.add_get("/", _handle_health)', False),
                             ('app.router.add_get("/hook/{secret}", _handle_health)', True),
                             ("_site_home.register_routes(app)", True)):
            self.assertEqual(needle in src, want, needle)


class LegalPages(unittest.TestCase):
    """Test 4: privacy / terms / contact in both languages, footer + notice on each."""

    def test_every_page_has_footer_and_notice(self):
        for path in PAGES_AR + PAGES_EN:
            status, headers, html = fetch(path)
            self.assertEqual(status, 200, path)
            self.assertIn("text/html", headers.get("Content-Type", ""), path)
            self.assertIn('<footer class="site-foot"', html, path)
            self.assertIn("7050158810", html.split("<footer", 1)[1], path)
            self.assertIn(NO_BOOKING_EN if path.startswith("/en") else NO_BOOKING_AR, html, path)
            self.assertIn('rel="canonical"', html, path)
            self.assertIn('property="og:title"', html, path)
            self.assertIn('name="description"', html, path)

    def test_footer_links_to_the_legal_pages(self):
        for path in PAGES_AR:
            foot = fetch(path)[2].split("<footer", 1)[1]
            for href in ('href="/privacy"', 'href="/terms"', 'href="/contact"'):
                self.assertIn(href, foot, path + " " + href)

    def test_terms_defer_cancellation_to_airbnb(self):
        self.assertIn("Airbnb", fetch("/terms")[2])
        self.assertIn("الإلغاء", fetch("/terms")[2])
        self.assertIn("cancellation", fetch("/en/terms")[2].lower())

    def test_privacy_explains_deletion(self):
        self.assertIn("حذف", fetch("/privacy")[2])
        self.assertIn("deletion", fetch("/en/privacy")[2].lower())

    def test_contact_has_a_complaints_section(self):
        self.assertIn('id="complaints"', fetch("/contact")[2])
        self.assertIn('id="complaints"', fetch("/en/contact")[2])

    def test_one_h1_per_page(self):
        for path in PAGES_AR + PAGES_EN:
            self.assertEqual(len(re.findall(r"<h1[ >]", fetch(path)[2])), 1, path)


class TravelLicenceSlot(unittest.TestCase):
    """Test 5: hidden while empty; once set, number + category show in the footer."""

    def test_hidden_when_empty(self):
        for path in ("/", "/en", "/contact"):
            html = fetch(path)[2]
            self.assertNotIn("وكالة السفر والسياحة", html, path)
            self.assertNotIn("Travel and Tourism Agency", html, path)
            self.assertNotIn('class="licence-travel"', html, path)

    def test_shown_when_set(self):
        with mock.patch.dict(SITE_IDENTITY, {"travel_licence_no": "TEST-73001"}):
            for path in PAGES_AR + PAGES_EN:
                foot = fetch(path)[2].split("<footer", 1)[1]
                self.assertIn("TEST-73001", foot, path)
                self.assertIn(SITE_IDENTITY["brand_ar"] if not path.startswith("/en")
                              else SITE_IDENTITY["brand_en"], foot, path)
            self.assertIn("وكالة السفر والسياحة", fetch("/")[2].split("<footer", 1)[1])
            self.assertIn("Travel and Tourism Agency", fetch("/en")[2].split("<footer", 1)[1])


class BusinessSaBadge(unittest.TestCase):
    """Test 6: the business.sa verification badge, same show/hide rule."""

    def test_hidden_when_empty(self):
        for path in ("/", "/en", "/privacy"):
            self.assertNotIn('class="badge-bsa"', fetch(path)[2], path)

    def test_shown_when_set(self):
        cert = "https://eauthenticate.saudibusiness.gov.sa/certificate-details/TEST1"
        img = "https://eauthenticate.saudibusiness.gov.sa/badge/TEST1.png"
        with mock.patch.dict(SITE_IDENTITY, {"business_sa_cert_url": cert,
                                             "business_sa_badge_img": img}):
            for path in PAGES_AR + PAGES_EN:
                foot = fetch(path)[2].split("<footer", 1)[1]
                self.assertIn('class="badge-bsa"', foot, path)
                self.assertIn('href="%s"' % cert, foot, path)
                self.assertIn('src="%s"' % img, foot, path)
                self.assertRegex(foot, r'<img[^>]+src="%s"[^>]+alt="[^"]+"' % re.escape(img))

    def test_link_alone_still_shows_a_text_badge(self):
        cert = "https://eauthenticate.saudibusiness.gov.sa/certificate-details/TEST2"
        with mock.patch.dict(SITE_IDENTITY, {"business_sa_cert_url": cert}):
            foot = fetch("/")[2].split("<footer", 1)[1]
            self.assertIn('href="%s"' % cert, foot)


class ForbiddenContent(unittest.TestCase):
    """Test 7: no unit count, no 'book direct', no social page as the main CTA."""

    COUNT_AR = re.compile(r"[0-9٠-٩]+\s*(?:\+\s*)?(?:شقة|شقق|وحدة|وحدات)")
    COUNT_EN = re.compile(r"\b[0-9]+\s*\+?\s*(?:apartments|units|homes|properties)\b", re.I)

    def test_nothing_forbidden_on_any_page(self):
        for path in PAGES_AR + PAGES_EN:
            html = fetch(path)[2]
            self.assertIsNone(self.COUNT_AR.search(html), path)
            self.assertIsNone(self.COUNT_EN.search(html), path)
            for phrase in ("احجز مباشرة", "احجز الآن", "ادفع الآن", "Book direct", "Book now", "Pay now"):
                self.assertNotIn(phrase, html, path + " " + phrase)
            self.assertNotRegex(html, r"(?:ر\.س|SAR)\s*[0-9٠-٩]|[0-9٠-٩]\s*(?:ر\.س|SAR)")

    def test_social_links_only_in_the_footer_and_on_contact(self):
        for path in PAGES_AR + PAGES_EN:
            html = fetch(path)[2]
            self.assertIn("tiktok.com/@oujares", html.split("<footer", 1)[1], path)
            if path.endswith("/contact"):
                continue
            for host in SOCIAL_HOSTS:
                self.assertNotIn(host, _main_part(html), path + " " + host)

    def test_social_hidden_when_unset(self):
        with mock.patch.dict(SITE_IDENTITY, NO_SOCIAL):
            for path in ("/", "/contact"):
                html = fetch(path)[2]
                for host in SOCIAL_HOSTS:
                    self.assertNotIn(host, html, path + " " + host)

    def test_phones_hidden_when_unset(self):
        with mock.patch.dict(SITE_IDENTITY, {"mobile": "", "support_phone": ""}):
            for path in ("/", "/contact"):
                self.assertNotIn("tel:", fetch(path)[2], path)

    def test_whatsapp_falls_back_to_stay_whatsapp(self):
        from site_home import render
        with mock.patch.dict(SITE_IDENTITY, {"whatsapp_url": ""}), \
                mock.patch.dict(render._FALLBACK, {"whatsapp": "966500000000"}):
            self.assertIn('href="https://wa.me/966500000000"', render.render_contact("ar"))


class BusinessSaContactDetails(unittest.TestCase):
    """business.sa request EACR110675: the site must show exactly what the request lists."""

    def test_identity_holds_the_request_values(self):
        self.assertEqual(SITE_IDENTITY["email"], EMAIL)
        self.assertEqual(SITE_IDENTITY["mobile"], MOBILE)
        self.assertEqual(SITE_IDENTITY["support_phone"], SUPPORT)
        for key, url in SOCIAL.items():
            self.assertEqual(SITE_IDENTITY[key], url, key)

    def test_every_value_is_on_home_and_contact(self):
        for path in ("/", "/contact", "/en", "/en/contact"):
            html = fetch(path)[2]
            for needle in (EMAIL, 'href="mailto:' + EMAIL, MOBILE, 'href="%s"' % MOBILE_TEL,
                           SUPPORT, 'href="%s"' % SUPPORT_TEL):
                self.assertIn(needle, html, path + " " + needle)
            for url in SOCIAL.values():
                self.assertIn('href="%s"' % url, html, path + " " + url)

    def test_phones_are_on_the_identity_card(self):
        for path in ("/", "/en"):
            card = _main_part(fetch(path)[2])
            self.assertIn('href="%s"' % MOBILE_TEL, card, path)
            self.assertIn('href="%s"' % SUPPORT_TEL, card, path)

    def test_contact_page_body_carries_phones_and_social(self):
        for path in ("/contact", "/en/contact"):
            body = _main_part(fetch(path)[2])
            for needle in (MOBILE_TEL, SUPPORT_TEL) + tuple(SOCIAL.values()):
                self.assertIn('href="%s"' % needle, body, path + " " + needle)

    def test_social_links_open_a_new_tab_safely_and_are_labelled(self):
        for path in ("/", "/contact", "/en/contact"):
            html = fetch(path)[2]
            for url in SOCIAL.values():
                tags = re.findall(r'<a [^>]*href="%s"[^>]*>' % re.escape(url), html)
                self.assertTrue(tags, path + " " + url)
                for tag in tags:
                    self.assertIn('target="_blank"', tag, tag)
                    self.assertRegex(tag, r'rel="[^"]*\bnoopener\b', tag)
                    self.assertRegex(tag, r'aria-label="[^"]+"', tag)

    def test_the_old_gmail_is_gone_from_every_page(self):
        for path in PAGES_AR + PAGES_EN:
            self.assertNotIn(OLD_EMAIL, fetch(path)[2], path)

    def test_html_lang_and_direction(self):
        self.assertIn('<html lang="ar" dir="rtl">', fetch("/")[2])
        self.assertIn('<html lang="en" dir="ltr">', fetch("/en")[2])


class RobotsAndSitemap(unittest.TestCase):
    """Test 8: crawlers are invited to the homepage and the legal pages."""

    def test_robots_allows_the_site(self):
        status, _, txt = fetch("/robots.txt", with_bot=True)
        self.assertEqual(status, 200)
        lines = txt.splitlines()
        for path in ("/", "/en", "/privacy", "/terms", "/contact"):
            self.assertIn("Allow: " + path, lines, path)
        self.assertIn("Disallow: /dashboard", lines)       # the old rules survive

    def test_sitemap_lists_the_pages_with_alternates(self):
        status, _, xml = fetch("/sitemap.xml", with_bot=True)
        self.assertEqual(status, 200)
        for path in ("/", "/en", "/privacy", "/en/privacy", "/terms", "/en/terms",
                     "/contact", "/en/contact"):
            self.assertIn("<loc>https://oujares.com%s</loc>" % path, xml, path)
        self.assertIn('xmlns:xhtml="http://www.w3.org/1999/xhtml"', xml)
        self.assertIn('hreflang="en" href="https://oujares.com/en"', xml)

    def test_sitemap_keeps_the_site_while_apartments_paused(self):
        with mock.patch.dict("os.environ", {"APARTMENTS_PAUSED": "1"}):
            xml = fetch("/sitemap.xml", with_bot=True)[2]
        self.assertIn("<loc>https://oujares.com/</loc>", xml)
        self.assertNotIn("/apartments", xml)


class SecurityHeaders(unittest.TestCase):
    """Test 9: the new pages still pass through bot.py's security middleware."""

    def test_headers_on_every_page(self):
        for path in PAGES_AR + PAGES_EN:
            _, h, _ = fetch(path, with_bot=True)
            self.assertEqual(h.get("X-Frame-Options"), "DENY", path)
            self.assertEqual(h.get("X-Content-Type-Options"), "nosniff", path)
            self.assertIn("default-src 'self'", h.get("Content-Security-Policy", ""), path)


class StaysFastAndStatic(unittest.TestCase):
    """CLAUDE.md trap 6 + the brief: '/' never calls Hostaway, a DB or a thread pool."""

    FORBIDDEN = ("to_thread", "web_thread", "hostaway", "Hostaway", "sqlite", "ClientSession",
                 "_load_json", "get_reservations", "fetch_", "open(")
    FORBIDDEN_IMPORT = re.compile(r"^\s*(?:import|from)\s+(?:requests|urllib|sqlite3|brain|bot)\b", re.M)

    def test_package_source_is_static(self):
        files = sorted((ROOT / "site_home").glob("*.py"))
        self.assertTrue(files)
        for f in files:
            src = f.read_text(encoding="utf-8")
            code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
            code = re.sub(r'"""[\s\S]*?"""', "", code)
            for bad in self.FORBIDDEN:
                self.assertNotIn(bad, code, "%s uses %s" % (f.name, bad))
            self.assertIsNone(self.FORBIDDEN_IMPORT.search(code), f.name)

    def test_assets_serve(self):
        for name in ("logo.png", "share.png"):
            status, h, body = fetch("/site/" + name, raw=True)
            self.assertEqual(status, 200, name)
            self.assertEqual(h.get("Content-Type"), "image/png", name)
            self.assertTrue(body.startswith(b"\x89PNG"), name)

    def test_no_external_hosts_in_markup(self):
        for path in ("/", "/en"):
            html = fetch(path)[2]
            for src in re.findall(r'(?:src|href)="(https?://[^"]+)"', _main_part(html)):
                self.assertTrue(src.startswith("https://oujares.com"), path + " " + src)

    def test_phone_breakpoint_keeps_the_top_spacing(self):
        # A ".wrap{padding:0 16px}" override under 420px once zeroed the page's top
        # padding, gluing the headline to the header on phones (seen live 2026-10-12).
        from site_home import render
        phone = render._CSS.split("@media (max-width:420px)", 1)[1].split("@media", 1)[0]
        self.assertNotRegex(phone, r"\.wrap\{padding:\s*0")

    def test_embedded_scripts_parse(self):
        try:
            import esprima
        except ImportError:
            self.skipTest("esprima not installed")
        for path in PAGES_AR + PAGES_EN:
            for js in re.findall(r"<script>(.*?)</script>", fetch(path)[2], re.S):
                esprima.parseScript(js)


if __name__ == "__main__":
    unittest.main()
