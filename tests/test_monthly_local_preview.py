"""Safety and source-contract checks for the local monthly preview server."""

import unittest

from monthly_public.fonts import FONT_ASSET_FILES, FONT_CSS_PATH
from monthly_public.local_preview import build_source, route_contract
from monthly_public.local_preview import create_web_app


class LocalPreviewSourceTest(unittest.TestCase):
    def test_public_catalog_rows_are_preserved_once_without_private_fields(self):
        payload = {
            "results": [
                {
                    "id": 71,
                    "slug": "real-home",
                    "name_ar": "شقة فعلية",
                    "name_en": "Ouja | Real Home",
                    "images": ["https://images.example/one.jpg"],
                    "bedrooms": 2,
                    "rating": 4.8,
                    "reviews_count": 17,
                    "wifi_pass": "must-not-pass-through",
                },
                {
                    "id": 72,
                    "slug": "incomplete-home",
                    "name_en": "Ouja | Incomplete Home",
                    "images": [],
                },
            ]
        }

        source = build_source(payload)

        self.assertEqual(["71", "72"], [str(row["id"]) for row in source["listings"]])
        self.assertEqual(2, len(source["listings"]))
        self.assertNotIn("wifi_pass", source["listings"][0])
        self.assertEqual(["https://images.example/one.jpg"], source["listings"][0]["images"])
        self.assertTrue(source["listings"][0]["rating_verified"])
        self.assertFalse(source["listings"][1]["rating_verified"])

    def test_duplicate_or_missing_identifiers_fail_closed(self):
        with self.assertRaises(ValueError):
            build_source({"results": [{"id": 7}, {"id": "7"}]})
        with self.assertRaises(ValueError):
            build_source({"results": [{"name_ar": "بدون معرف"}]})


class LocalPreviewRouteTest(unittest.TestCase):
    def test_route_contract_is_read_only_except_for_in_memory_matching(self):
        routes = route_contract()

        self.assertIn(("GET", "/monthly/ops/preview"), routes)
        self.assertIn(("GET", "/api/monthly/ops/preview/search"), routes)
        self.assertIn(("POST", "/api/monthly/ops/preview/match"), routes)
        self.assertFalse(any("draft" in path or "approve" in path or "refresh" in path
                             for _method, path in routes))
        self.assertEqual(
            [("POST", "/api/monthly/ops/preview/match")],
            [(method, path) for method, path in routes if method == "POST"],
        )

    def test_preview_serves_the_shared_font_stylesheet_and_allowlisted_fonts(self):
        app = create_web_app(build_source({"results": [{"id": 1}]}))
        paths = {
            resource.canonical
            for resource in app.router.resources()
            if getattr(resource, "canonical", None)
        }

        self.assertIn(FONT_CSS_PATH, paths)
        self.assertTrue(set(FONT_ASSET_FILES).issubset(paths))


if __name__ == "__main__":
    unittest.main()
