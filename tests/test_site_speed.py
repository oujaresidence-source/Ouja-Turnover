# -*- coding: utf-8 -*-
"""Guest photos and the dashboard page — the two cheap speed wins of 2026-10-27.

Measured live that day from Riyadh:
  * /apartments showed Hostaway's ORIGINAL photos straight from S3 us-west-2 (Oregon):
    ~300 KB JPEG, 1350x900, ~1.6s each — for a card drawn ~360px wide. The WebP proxy
    that /elite already used (/elite/img) was sitting right there, unused.
  * /dashboard is 1.3 MB of HTML and was sent with no validator at all, so every open
    re-downloaded ~350 KB even though the page only changes on deploy.

What these lock:
  * every <img> and the hero on /apartments goes through pimg(); pimg proxies only
    absolute http(s) URLs (an uploaded hero is a relative path) and only when the server
    says the proxy is on (ELITE_IMG_PROXY=0 turns it off -> original URLs again)
  * the proxy shrinks a photo to the asked width as WebP, serves the second ask from
    disk, and runs on the WEB lane — never the shared default pool that bot loops jam
  * /dashboard carries an ETag + "no-cache" (revalidate every time, so a deploy shows
    immediately) and answers a matching If-None-Match with an empty 304
Synthetic, no network.
"""
import asyncio
import inspect
import io
import re
import tempfile
import unittest
from unittest import mock

from aiohttp.test_utils import make_mocked_request

import bot


def _stay_js():
    return bot.STAY_HTML


class StayPhotosGoThroughProxy(unittest.TestCase):
    def test_no_img_uses_a_raw_url(self):
        html = _stay_js()
        imgs = re.findall(r"<img[^>]*>", html)
        self.assertGreaterEqual(len(imgs), 6, "positive control: the page still draws photos")
        raw = [i for i in imgs if "src=\"'+he(" in i and "pimg(" not in i]
        self.assertEqual(raw, [], "a photo bypasses pimg():\n" + "\n".join(raw))

    def test_hero_goes_through_proxy(self):
        line = next(l for l in _stay_js().split("\n") if "var heroBg=" in l)
        self.assertIn("pimg(cfg.hero", line)

    def test_pimg_only_proxies_absolute_urls_when_enabled(self):
        m = re.search(r"function pimg\(u,w\)\{.*?\}\s*\n", _stay_js(), re.S)
        self.assertIsNotNone(m, "pimg helper missing from STAY_HTML")
        body = m.group(0)
        self.assertIn("imgproxy", body)
        self.assertIn("/^https?:", body)
        self.assertIn("/elite/img?u=", body)

    def test_server_tells_the_page_whether_the_proxy_is_on(self):
        src = inspect.getsource(bot._stay_render)
        self.assertIn('"imgproxy": bool(ELITE_IMG_PROXY)', src)


def _jpeg(w=1350, h=900):
    out = io.BytesIO()
    bot._PILImage.new("RGB", (w, h), (180, 140, 90)).save(out, format="JPEG", quality=90)
    return out.getvalue()


@unittest.skipUnless(bot._ELITE_PIL, "Pillow missing")
class ProxyShrinksAndCaches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (mock.patch.object(bot, "STATE_DIR", self.tmp.name),
                  mock.patch.object(bot, "ELITE_IMG_PROXY", True)):
            p.start()
            self.addCleanup(p.stop)
        self.fetches = 0
        src = _jpeg()

        def fake_get(url, timeout=None):
            self.fetches += 1
            r = mock.Mock()
            r.content = src
            r.raise_for_status = lambda: None
            return r
        p = mock.patch.object(bot.requests, "get", side_effect=fake_get)
        p.start()
        self.addCleanup(p.stop)

    def _ask(self, w):
        u = "https://hostaway-platform.s3.us-west-2.amazonaws.com/listing/147296-1-x"
        req = make_mocked_request("GET", "/elite/img?u=" + bot.urllib.parse.quote(u, safe="") + "&w=" + str(w))
        return asyncio.run(bot._handle_elite_img(req))

    def test_resized_webp_then_disk_cache(self):
        r1 = self._ask(720)
        self.assertEqual(r1.content_type, "image/webp")
        im = bot._PILImage.open(io.BytesIO(r1.body))
        self.assertEqual(im.width, 720)
        self.assertLess(len(r1.body), len(_jpeg()))
        r2 = self._ask(720)
        self.assertEqual(r2.body, r1.body)
        self.assertEqual(self.fetches, 1, "second ask must come from the disk cache")

    def test_transcode_runs_on_the_web_lane(self):
        seen = []
        real = bot.web_thread

        async def spy(fn, *a, **k):
            seen.append(fn)
            return await real(fn, *a, **k)
        with mock.patch.object(bot, "web_thread", side_effect=spy):
            self._ask(320)
        self.assertEqual(len(seen), 1, "the fetch+transcode must go through web_thread")


class DashboardRevalidates(unittest.TestCase):
    def _get(self, headers=None):
        req = make_mocked_request("GET", "/dashboard", headers=headers or {})
        return asyncio.run(bot._handle_dashboard(req))

    def test_first_open_sends_validator(self):
        r = self._get()
        self.assertEqual(r.status, 200)
        self.assertTrue(r.headers.get("ETag"))
        self.assertIn("no-cache", r.headers.get("Cache-Control", ""))
        self.assertEqual(r.text, bot.DASHBOARD_HTML)

    def test_matching_etag_is_an_empty_304(self):
        tag = self._get().headers["ETag"]
        r = self._get({"If-None-Match": tag})
        self.assertEqual(r.status, 304)
        self.assertFalse(r.body)
        self.assertEqual(r.headers.get("ETag"), tag)

    def test_stale_etag_gets_the_page(self):
        r = self._get({"If-None-Match": '"old-deploy"'})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.text, bot.DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
