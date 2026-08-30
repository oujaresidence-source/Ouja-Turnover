# -*- coding: utf-8 -*-
"""G10 — the ERP's static assets over the wire.

erp.js is ~392 KB and erp.css ~42 KB, and both were served uncompressed on every
cold load, cache-busted by ?v=<commit> on every deploy. Over a mobile link that is
most of the wait before the page can even ask for data.

These make REAL requests against the handler rather than trusting the code, and
they check the fallbacks, because a client that advertises no encoding must still
get working bytes.

Run: python3 -m unittest tests.test_erp_static_assets -v
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-static"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import finance  # noqa: E402

MAX_KB = 90


class StaticAssetTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = web.Application()
        app.router.add_get("/erp/static/{filename}", finance._h_erp_static)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_erp_js_is_compressed_under_the_budget(self):
        r = await self.client.get("/erp/static/erp.js",
                                  headers={"Accept-Encoding": "br, gzip"},
                                  auto_decompress=False)
        self.assertEqual(r.status, 200)
        self.assertIn(r.headers.get("Content-Encoding"), ("br", "gzip"))
        body = await r.read()
        kb = len(body) / 1024.0
        self.assertLess(kb, MAX_KB,
                        "erp.js went over the wire at %.1f KB (budget %d KB)"
                        % (kb, MAX_KB))

    async def test_it_is_cacheable_forever(self):
        """Safe only because the URL already carries ?v=<commit>."""
        r = await self.client.get("/erp/static/erp.js")
        cc = r.headers.get("Cache-Control") or ""
        self.assertIn("immutable", cc)
        self.assertIn("max-age=31536000", cc)
        self.assertIn("Accept-Encoding", r.headers.get("Vary") or "")

    async def test_a_client_without_compression_still_gets_the_file(self):
        r = await self.client.get("/erp/static/erp.js",
                                  headers={"Accept-Encoding": ""},
                                  auto_decompress=False)
        self.assertEqual(r.status, 200)
        self.assertIsNone(r.headers.get("Content-Encoding"))
        body = await r.read()
        self.assertGreater(len(body), 100000, "the plain fallback must be the real file")

    async def test_the_decompressed_bytes_are_the_real_file(self):
        """A compressed asset that decodes to something else is worse than a big one."""
        r = await self.client.get("/erp/static/erp.js",
                                  headers={"Accept-Encoding": "gzip"})
        body = await r.read()                       # aiohttp decompresses for us
        on_disk = (Path(__file__).resolve().parents[1] /
                   "finance" / "static" / "erp.js").read_bytes()
        self.assertEqual(body, on_disk, "served bytes do not match the file on disk")

    async def test_css_is_compressed_too(self):
        r = await self.client.get("/erp/static/erp.css",
                                  headers={"Accept-Encoding": "br, gzip"},
                                  auto_decompress=False)
        self.assertEqual(r.status, 200)
        self.assertIn(r.headers.get("Content-Encoding"), ("br", "gzip"))
        self.assertLess(len(await r.read()) / 1024.0, 20)

    async def test_path_traversal_is_refused(self):
        for bad in ("..%2f..%2fbot.py", "%2e%2e%2fbot.py", ".hidden"):
            r = await self.client.get("/erp/static/" + bad)
            self.assertEqual(r.status, 404, "traversal attempt %r was not refused" % bad)

    async def test_a_missing_file_is_a_clean_404(self):
        r = await self.client.get("/erp/static/nope.js")
        self.assertEqual(r.status, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
