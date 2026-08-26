# -*- coding: utf-8 -*-
"""
Platform screenshots (plan Task 9): sniffed, capped, OCR'd, guarded.

Run: python3 -m unittest tests.test_cp_shots
"""
import asyncio
import io
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiohttp  # noqa: E402
from cp import admin as cp_admin  # noqa: E402
from tests.test_cp_admin import make_client, _Disk  # noqa: E402

UPLOADS = "/tmp/cp-test-uploads"


def _png_bytes(text=""):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (400, 120), "white")
    if text:
        ImageDraw.Draw(img).text((10, 40), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class _Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(UPLOADS, ignore_errors=True)
        self.loop = asyncio.new_event_loop()
        self.disk = _Disk()
        self.client, _ = make_client(self.loop, disk=self.disk)
        self._orig_ocr = cp_admin.ocr_text

    def tearDown(self):
        cp_admin.ocr_text = self._orig_ocr
        self.loop.run_until_complete(self.client.close())
        self.loop.close()

    def upload(self, data, filename="shot.png", caption="كشف المالك"):
        form = aiohttp.FormData()
        form.add_field("file", data, filename=filename, content_type="image/png")
        form.add_field("caption_ar", caption)
        return self.loop.run_until_complete(
            self.client.post("/api/cp/admin/shot-upload", data=form))

    def jbody(self, r):
        return self.loop.run_until_complete(r.json())


class Uploads(_Base):
    def test_clean_png_uploads_and_serves(self):
        cp_admin.ocr_text = lambda data: ("كشف نظيف بلا أرقام", "test")
        r = self.upload(_png_bytes())
        d = self.jbody(r)
        self.assertTrue(d["ok"], d)
        sid = d["shot"]["id"]
        resp = self.loop.run_until_complete(self.client.get("/cp/shot/" + sid))
        self.assertEqual(resp.status, 200)
        self.assertIn("max-age", resp.headers.get("Cache-Control", ""))

    def test_ocr_finding_a_withheld_figure_rejects(self):
        cp_admin.ocr_text = lambda data: ("Revenue total 7,669,457 SAR", "test")
        r = self.upload(_png_bytes())
        d = self.jbody(r)
        self.assertEqual(r.status, 400)
        self.assertIn("7,669,457", str(d))
        self.assertEqual(os.listdir(UPLOADS) if os.path.exists(UPLOADS) else [], [])

    def test_missing_tesseract_skips_ocr_but_uploads(self):
        cp_admin.ocr_text = lambda data: (None, "skipped")
        r = self.upload(_png_bytes())
        d = self.jbody(r)
        self.assertTrue(d["ok"])
        self.assertEqual(d["ocr"], "skipped")

    def test_bad_type_rejected_by_magic_bytes(self):
        cp_admin.ocr_text = lambda data: ("", "test")
        r = self.upload(b"GIF89a not really an allowed image", filename="x.png")
        self.assertEqual(r.status, 400)

    def test_size_cap(self):
        cp_admin.ocr_text = lambda data: ("", "test")
        big = _png_bytes() + b"\x00" * (4 * 1024 * 1024)
        r = self.upload(big)
        self.assertEqual(r.status, 400)

    def test_three_shots_max(self):
        cp_admin.ocr_text = lambda data: ("", "test")
        for i in range(3):
            self.assertTrue(self.jbody(self.upload(_png_bytes(),
                                                   caption="لقطة %d" % i))["ok"])
        r = self.upload(_png_bytes())
        self.assertEqual(r.status, 400)

    def test_unknown_shot_404s(self):
        r = self.loop.run_until_complete(self.client.get("/cp/shot/nope"))
        self.assertEqual(r.status, 404)

    def test_real_tesseract_if_present(self):
        if cp_admin._tesseract_available() is False:
            self.skipTest("tesseract not installed here")
        r = self.upload(_png_bytes("Revenue 7,669,457"))
        self.assertEqual(r.status, 400)


if __name__ == "__main__":
    unittest.main()


class LogoUpload(_Base):
    def _upload(self, data, filename="logo.png"):
        import aiohttp
        form = aiohttp.FormData()
        form.add_field("file", data, filename=filename, content_type="image/png")
        return self.loop.run_until_complete(
            self.client.post("/api/cp/admin/logo-upload", data=form))

    def test_upload_installs_and_derives_the_four_assets(self):
        r = self._upload(_png_bytes("OUJA"))
        d = self.jbody(r)
        self.assertTrue(d["ok"], d)
        self.assertEqual(set(d["derived"]),
                         {"icon.png", "icon-192.png", "icon-512.png", "share.png"})
        import os
        brand = os.path.join(UPLOADS, "brand")
        self.assertTrue(os.path.exists(os.path.join(brand, "logo.png")))

    def test_uploaded_logo_is_served_and_wins_over_the_built_in(self):
        self._upload(_png_bytes("OUJA"))
        r = self.loop.run_until_complete(self.client.get("/cp/logo.png"))
        self.assertEqual(r.status, 200)
        r2 = self.loop.run_until_complete(self.client.get("/cp/share.png"))
        self.assertEqual(r2.status, 200)

    def test_share_card_is_the_right_shape(self):
        self._upload(_png_bytes("OUJA"))
        from PIL import Image
        import os
        im = Image.open(os.path.join(UPLOADS, "brand", "share.png"))
        self.assertEqual(im.size, (1200, 630))

    def test_bad_type_refused(self):
        r = self._upload(b"not an image at all", filename="x.png")
        self.assertEqual(r.status, 400)

    def test_delete_reverts_to_the_built_in(self):
        self._upload(_png_bytes("OUJA"))
        r = self.loop.run_until_complete(
            self.client.post("/api/cp/admin/logo-delete", json={}))
        self.assertTrue(self.jbody(r)["ok"])
        import os
        self.assertFalse(os.path.exists(os.path.join(UPLOADS, "brand", "logo.png")))
