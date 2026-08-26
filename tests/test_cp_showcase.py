# -*- coding: utf-8 -*-
"""
The Hostaway showcase (plan Task 7): the picker reads the gw cache, the public
render never touches Hostaway, and every image URL goes through /elite/img.

Run: python3 -m unittest tests.test_cp_showcase
"""
import asyncio
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cp import admin_store  # noqa: E402
from tests.test_cp_admin import make_client, _Disk, FAKE_CACHE  # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.disk = _Disk()
        self.client, _ = make_client(self.loop, disk=self.disk)
        self.store = admin_store.Store(load_json=self.disk.load,
                                       save_json=self.disk.save)

    def tearDown(self):
        self.loop.run_until_complete(self.client.close())
        self.loop.close()

    def get(self, path):
        r = self.loop.run_until_complete(self.client.get(path))
        return r, self.loop.run_until_complete(r.text())

    def post(self, path, payload):
        return self.loop.run_until_complete(self.client.post(path, json=payload))


class Picker(_Base):
    def test_payload_is_the_cache_projection(self):
        import json
        r, body = self.get("/api/cp/admin/showcase")
        d = json.loads(body)
        row = [x for x in d["cache"] if x["id"] == 487708][0]
        self.assertEqual(row["image_urls"], FAKE_CACHE[0]["image_urls"])
        self.assertTrue(row["active"])

    def test_selection_saves_and_hard_max_enforced(self):
        units = [{"listing_id": str(1000 + i), "name_ar": "وحدة %d" % i,
                  "bedrooms_label_ar": "غرفتا نوم", "line_ar": "سطر"}
                 for i in range(13)]
        r = self.post("/api/cp/admin/showcase", {"units": units})
        self.assertEqual(r.status, 400)
        r = self.post("/api/cp/admin/showcase", {"units": units[:6]})
        self.assertEqual(r.status, 200)

    def test_sync_button_calls_the_existing_sync(self):
        r = self.post("/api/cp/admin/sync-listings", {})
        self.assertEqual(r.status, 200)


class PublicRender(_Base):
    UNITS = [{"listing_id": "487708", "name_ar": "جاباندي",
              "bedrooms_label_ar": "غرفتا نوم", "line_ar": "سينما منزلية",
              "cover_url": "https://img/x2.jpg"},
             {"listing_id": "999001", "name_ar": "وحدة متوقفة",
              "bedrooms_label_ar": "غرفة", "line_ar": "يجب ألا تظهر"}]

    def _publish(self):
        self.store.update_section("showcase", {"units": self.UNITS}, by="u")
        self.store.publish("v2", by="admin")

    def test_inactive_listing_never_renders_publicly(self):
        self._publish()
        _, html = self.get("/cp/ar")
        self.assertIn("جاباندي", html)
        self.assertNotIn("وحدة متوقفة", html)

    def test_every_image_url_is_the_proxy(self):
        self._publish()
        _, html = self.get("/cp/ar")
        srcs = re.findall(r'<img[^>]+src="([^"]+)"', html)
        self.assertTrue(srcs, "no images rendered — the assertion would pass vacuously")
        for src in srcs:
            with self.subTest(src=src):
                # the rule is that no VENDOR url reaches a reader: photos go
                # through /elite/img, and our own brand assets are served from
                # /cp/. Anything else (an S3 host, a CDN) is the leak.
                self.assertTrue(src.startswith("/elite/img") or src.startswith("/cp/"),
                                "raw image URL leaked: %r" % src)
                self.assertNotIn("://", src)

    def test_hostaway_is_never_called_on_the_public_path(self):
        """listing_photos is the pipeline; the sync function is the only thing
        allowed to touch Hostaway and it must NOT run on a page request."""
        calls = []
        from cp.host import HOST
        HOST.sync_listings = lambda: calls.append(1)
        self._publish()
        self.get("/cp/ar")
        self.get("/cp/ar/more/units")
        self.assertEqual(calls, [])

    def test_empty_cache_keeps_placeholder_tiles(self):
        """In production listing_photos resolves through the same cache, so an
        empty cache means no photos — the fakes must agree."""
        from cp.host import HOST
        HOST.listings_cache = lambda: {"listings": [], "synced_at": None}
        HOST.listing_photos = lambda lid, pinned=None: {}
        self._publish()
        _, html = self.get("/cp/ar")
        self.assertGreaterEqual(html.count("صورة الوحدة"), 1)


if __name__ == "__main__":
    unittest.main()
