# -*- coding: utf-8 -*-
"""Guide Engine (دليل الشقق) — db + importer + public data.json shape.

Run: python3 -m unittest tests.test_guide_engine
"""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb        # noqa: E402
from guide import db as gdb        # noqa: E402
from guide import importer         # noqa: E402


class _Resp:
    def __init__(self, body=b"", ctype="image/jpeg", status=200):
        self.content = body
        self.headers = {"content-type": ctype}
        self.status_code = status


def _write_csv(path, rows):
    cols = ["id", "listing_name", "map_link", "complex_pic", "complex_caption",
            "building_pic", "building_caption", "elevator_pic", "elevator_caption",
            "door_pic", "door_caption", "wifi_name", "wifi_pass", "notes", "updated_at"]
    with open(path, "w", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


class GuideEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="guide_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        gdb.reset_init_cache()

    def test_drive_direct(self):
        self.assertEqual(
            importer.drive_direct("https://drive.google.com/file/d/FILE123/view?usp=sharing"),
            "https://drive.google.com/uc?export=download&id=FILE123")
        self.assertEqual(importer.drive_direct("https://i.imgur.com/x.jpg"),
                         "https://i.imgur.com/x.jpg")

    def test_match_listing_exact_and_ambiguous(self):
        lm = {1: "Ouja | Spacious 1BR  Prime Location  Self-Entry",
              2: "Ouja | MLQ 1", 3: "Ouja | MLQ 11"}
        self.assertEqual(importer.match_listing("Ouja | Spacious 1BR Prime Location Self-Entry", lm), 1)
        self.assertEqual(importer.match_listing("MLQ 1", lm), 2)
        self.assertIsNone(importer.match_listing("totally unknown", lm))

    def test_import_idempotent_with_media_and_report(self):
        csvp = os.path.join(self.tmp, "listings.csv")
        _write_csv(csvp, [
            {"id": "6b-htn", "listing_name": "Ouja | Test Apt",
             "map_link": "https://maps.google.com/?q=24.77,46.58",
             "complex_pic": "https://drive.google.com/file/d/GOOD1/view",
             "complex_caption": "المجمع",
             "door_pic": "https://drive.google.com/file/d/DEAD1/view",
             "wifi_name": "Ouja_WiFi", "wifi_pass": "12345678",
             "notes": "العنوان: الرياض"},
            {"id": "a5-mlq", "listing_name": "no match here",
             "map_link": "", "notes": "بدون صور"},
        ])
        media_dir = os.path.join(self.tmp, "guide_media")

        def fake_get(url, timeout=30):
            if "GOOD1" in url:
                return _Resp(b"\xff\xd8\xd9" * 40)                 # jpeg-ish bytes
            return _Resp(b"<html>sign in</html>", ctype="text/html")  # dead/private link

        rep = importer.import_csv(csvp, media_dir=media_dir, http_get=fake_get,
                                  listings_map={9: "Ouja | Test Apt"})
        self.assertEqual(rep["units"], 2)
        self.assertEqual(rep["created"], 2)
        self.assertEqual(rep["matched"], 1)
        self.assertIn("no match here", rep["unmatched"])
        self.assertEqual(rep["media_ok"], 1)
        self.assertEqual(len(rep["media_failed"]), 1, "dead Drive link must be reported, not saved")
        self.assertEqual(rep["media_failed"][0]["field"], "door_pic")
        self.assertTrue(os.path.exists(os.path.join(media_dir, "6b-htn", "complex_pic.jpg")))
        u = gdb.get_unit("6b-htn")
        self.assertEqual(u["listing_id"], 9)
        self.assertEqual(u["wifi_pass"], "12345678")
        # re-run → idempotent: no dupes, mirrored media skipped
        rep2 = importer.import_csv(csvp, media_dir=media_dir, http_get=fake_get,
                                   listings_map={9: "Ouja | Test Apt"})
        self.assertEqual(rep2["created"], 0)
        self.assertEqual(rep2["updated"], 2)
        self.assertEqual(rep2["media_skipped"], 1)
        self.assertEqual(len(gdb.units(active_only=True)), 2)

        # ---- public data.json shape + media swap (depends on the import above) ----
        recs = {r["id"]: r for r in gdb.public_records()}
        r = recs["6b-htn"]
        # the mirrored photo is served from OUR media route
        self.assertEqual(r["complex_pic"], "/guide/media/6b-htn/complex_pic.jpg")
        # the failed one keeps the original Drive link (page normalizes it)
        self.assertIn("drive.google.com", r["door_pic"])
        for k in ("listing_name", "map_link", "wifi_name", "wifi_pass", "notes", "faq"):
            self.assertIn(k, r)

        # ---- FAQ entries flow ----
        eid = gdb.add_entry("6b-htn", "faq", title_ar="وين الموقف؟",
                            body_ar="الموقف رقم ١٢ بالقبو", source="gap", by="نورة")
        self.assertTrue(any(e["id"] == eid for e in gdb.entries_for("6b-htn")))
        # a for-all-units entry shows on every slug
        gdb.add_entry("", "faq", title_ar="سياسة التدخين", body_ar="ممنوع التدخين داخل الشقة")
        self.assertTrue(any(e["title_ar"] == "سياسة التدخين" for e in gdb.entries_for("a5-mlq")))
        rec = {x["id"]: x for x in gdb.public_records()}["6b-htn"]
        self.assertTrue(any(f["title_ar"] == "وين الموقف؟" for f in rec["faq"]))
        gdb.del_entry(eid)
        self.assertFalse(any(e["id"] == eid for e in gdb.entries_for("6b-htn")))


class GuideImportSpeedTest(unittest.TestCase):
    """The import must not hang the button: shared Drive links download ONCE
    (dead ones fail ONCE), and the routes layer runs it as a background job."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="guide_speed_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        gdb.reset_init_cache()

    def test_shared_links_download_once_dead_links_fail_once(self):
        csvp = os.path.join(self.tmp, "l.csv")
        shared = "https://drive.google.com/file/d/SHARED/view"
        dead = "https://drive.google.com/file/d/DEAD/view"
        _write_csv(csvp, [
            {"id": "u1", "listing_name": "A", "complex_pic": shared, "door_pic": dead},
            {"id": "u2", "listing_name": "B", "complex_pic": shared, "door_pic": dead},
            {"id": "u3", "listing_name": "C", "building_pic": shared},
        ])
        calls = []

        def fake_get(url, timeout=12):
            calls.append(url)
            if "SHARED" in url:
                return _Resp(b"\xff\xd8\xd9" * 40)
            return _Resp(b"<html>denied</html>", ctype="text/html")
        rep = importer.import_csv(csvp, media_dir=os.path.join(self.tmp, "m"),
                                  http_get=fake_get, listings_map={})
        self.assertEqual(len(calls), 2, "1 shared + 1 dead — never re-downloaded")
        self.assertEqual(rep["media_ok"], 3, "the shared photo lands on all 3 units")
        self.assertEqual(len(rep["media_failed"]), 2, "dead link reported per unit, fetched once")
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "m", "u3", "building_pic.jpg")))

    def test_background_job_state_machine(self):
        from guide import routes as groutes
        csvp = os.path.join(self.tmp, "bg.csv")
        _write_csv(csvp, [{"id": "bg1", "listing_name": "BG"}])
        groutes._import_state.update({"running": True, "done": 0, "total": 0,
                                      "report": None, "error": ""})
        groutes._run_import_job(csvp, os.path.join(self.tmp, "m2"), {})
        st = groutes._import_state
        self.assertFalse(st["running"], "job must always end not-running")
        self.assertIsNotNone(st["report"])
        self.assertEqual(st["report"]["units"], 1)
        self.assertEqual(st["done"], 1)
        self.assertTrue(st["finished_at"])

    def test_background_job_error_is_captured(self):
        from guide import routes as groutes
        groutes._import_state.update({"running": True, "report": None, "error": ""})
        groutes._run_import_job(os.path.join(self.tmp, "missing.csv"),
                                os.path.join(self.tmp, "m3"), {})
        st = groutes._import_state
        self.assertFalse(st["running"])
        self.assertIn("FileNotFoundError", st["error"])


if __name__ == "__main__":
    unittest.main()
