import asyncio
import json
import unittest
from unittest import mock


from monthly_public.catalog_profiles import CatalogContractError
from monthly_public.catalog_store import RevisionConflict
from tests.test_monthly_catalog_profiles import valid_profile, valid_settings


def run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def payload(response):
    return json.loads(response.text)


class FakeRequest:
    def __init__(self, body=None, match=None, method="POST", query=None):
        self._body = {} if body is None else body
        self.match_info = match or {}
        self.method = method
        self.path = "/api/monthly/ops/test"
        self.query = query or {}
        self.headers = {}
        self.cookies = {}

    async def json(self):
        return self._body


class Service:
    def __init__(self):
        self.calls = []
        self.failure = None

    def _call(self, name, *args):
        self.calls.append((name, args))
        if self.failure:
            raise self.failure
        return {"name": name, "args": list(args)}

    def portfolio(self):
        return self._call("portfolio")

    def listing(self, listing_id):
        return self._call("listing", listing_id)

    def save_profile_draft(self, listing_id, profile, revision, actor):
        return self._call("profile_draft", listing_id, profile, revision, actor)

    def approve_profile(self, listing_id, revision, actor):
        return self._call("profile_approve", listing_id, revision, actor)

    def settings(self):
        return self._call("settings")

    def save_settings_draft(self, settings, revision, actor):
        return self._call("settings_draft", settings, revision, actor)

    def approve_settings(self, revision, actor):
        return self._call("settings_approve", revision, actor)

    def places(self):
        return self._call("places")

    def save_place_draft(self, place_id, place, revision, actor):
        return self._call("place_draft", place_id, place, revision, actor)

    def approve_place(self, place_id, revision, active, actor):
        return self._call("place_approve", place_id, revision, active, actor)

    def refresh(self):
        return self._call("refresh")


class MonthlyCatalogRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot

        cls.bot = bot

    def setUp(self):
        self.service = Service()
        self.saved = (
            self.bot.MONTHLY_ENABLED,
            self.bot.MONTHLY_PUBLIC_V2,
            self.bot._monthly_catalog_service,
        )
        self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
        self.bot._monthly_catalog_service = self.service
        self.gate = mock.patch.object(self.bot, "_monthly_ops_gate", return_value=None)
        self.actor = mock.patch.object(self.bot, "_req_actor", return_value="Faisal")
        self.gate.start()
        self.actor.start()

    def tearDown(self):
        self.gate.stop()
        self.actor.stop()
        (
            self.bot.MONTHLY_ENABLED,
            self.bot.MONTHLY_PUBLIC_V2,
            self.bot._monthly_catalog_service,
        ) = self.saved

    def test_profile_draft_requires_monthly_operations_access(self):
        denied = self.bot._json({"error": "forbidden"}, 403)
        with mock.patch.object(self.bot, "_monthly_ops_gate", return_value=denied):
            response = run(
                self.bot._api_monthly_catalog_profile_draft(
                    FakeRequest(
                        {"revision": 0, "profile": valid_profile()}, {"id": "101"}
                    )
                )
            )
        self.assertEqual(response.status, 403)
        self.assertEqual(self.service.calls, [])

    def test_profile_draft_is_a_thin_authenticated_adapter(self):
        response = run(
            self.bot._api_monthly_catalog_profile_draft(
                FakeRequest(
                    {"revision": 2, "profile": valid_profile()}, {"id": "101"}
                )
            )
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(self.service.calls[0][0], "profile_draft")
        self.assertEqual(self.service.calls[0][1][0], "101")
        self.assertEqual(self.service.calls[0][1][2:], (2, "Faisal"))

    def test_revision_conflict_is_409_without_internal_details(self):
        self.service.failure = RevisionConflict(0, 1)
        response = run(
            self.bot._api_monthly_catalog_profile_draft(
                FakeRequest(
                    {"revision": 0, "profile": valid_profile()}, {"id": "101"}
                )
            )
        )
        self.assertEqual(response.status, 409)
        self.assertEqual(payload(response)["error"], "revision_conflict")
        self.assertEqual(payload(response)["current_revision"], 1)
        self.assertNotIn("trace", response.text.lower())

    def test_contract_error_is_400_and_source_failure_is_503(self):
        self.service.failure = CatalogContractError(
            "name_ar", "language_mismatch", "العربية مطلوبة", "Arabic is required"
        )
        invalid = run(
            self.bot._api_monthly_catalog_profile_draft(
                FakeRequest({"revision": 0, "profile": {}}, {"id": "101"})
            )
        )
        self.assertEqual(invalid.status, 400)
        self.assertEqual(payload(invalid)["issue"]["field"], "name_ar")

        self.service.failure = RuntimeError("database path and secret details")
        unavailable = run(
            self.bot._api_monthly_catalog_listings(FakeRequest(method="GET"))
        )
        self.assertEqual(unavailable.status, 503)
        self.assertEqual(payload(unavailable)["error"], "catalog_unavailable")
        self.assertNotIn("secret", unavailable.text)

    def test_unknown_and_missing_request_fields_are_rejected_before_service(self):
        response = run(
            self.bot._api_monthly_catalog_settings_draft(
                FakeRequest(
                    {
                        "revision": 0,
                        "settings": valid_settings(),
                        "unexpected": True,
                    }
                )
            )
        )
        self.assertEqual(response.status, 400)
        self.assertEqual(payload(response)["issue"]["code"], "unknown_field")
        self.assertEqual(self.service.calls, [])

        missing = run(
            self.bot._api_monthly_catalog_place_approve(
                FakeRequest({"place_id": "hospital", "revision": 1})
            )
        )
        self.assertEqual(missing.status, 400)
        self.assertEqual(payload(missing)["issue"]["code"], "required")

    def test_all_catalog_routes_call_the_expected_service_contract(self):
        cases = (
            (self.bot._api_monthly_catalog_listings, FakeRequest(method="GET"), "portfolio"),
            (self.bot._api_monthly_catalog_listing, FakeRequest(match={"id": "101"}, method="GET"), "listing"),
            (self.bot._api_monthly_catalog_profile_approve, FakeRequest({"revision": 1}, {"id": "101"}), "profile_approve"),
            (self.bot._api_monthly_catalog_settings, FakeRequest(method="GET"), "settings"),
            (self.bot._api_monthly_catalog_settings_draft, FakeRequest({"revision": 0, "settings": valid_settings()}), "settings_draft"),
            (self.bot._api_monthly_catalog_settings_approve, FakeRequest({"revision": 1}), "settings_approve"),
            (self.bot._api_monthly_catalog_places, FakeRequest(method="GET"), "places"),
            (self.bot._api_monthly_catalog_place_draft, FakeRequest({"place_id": "hospital", "revision": 0, "place": {} }), "place_draft"),
            (self.bot._api_monthly_catalog_place_approve, FakeRequest({"place_id": "hospital", "revision": 1, "active": True}), "place_approve"),
            (self.bot._api_monthly_catalog_refresh, FakeRequest({}), "refresh"),
        )
        for handler, request, expected in cases:
            with self.subTest(expected=expected):
                self.service.calls.clear()
                response = run(handler(request))
                self.assertEqual(response.status, 200, response.text)
                self.assertEqual(self.service.calls[0][0], expected)

    def test_catalog_routes_are_registered_only_behind_v2_switch(self):
        class Router:
            def __init__(self):
                self.routes = []

            def add_get(self, path, handler):
                self.routes.append(("GET", path))

            def add_post(self, path, handler):
                self.routes.append(("POST", path))

        router = Router()
        self.bot._register_monthly_v2_only_routes(router)
        expected = {
            ("GET", "/api/monthly/ops/listings"),
            ("GET", "/api/monthly/ops/listing/{id}"),
            ("POST", "/api/monthly/ops/listing/{id}/draft"),
            ("POST", "/api/monthly/ops/listing/{id}/approve"),
            ("GET", "/api/monthly/ops/settings"),
            ("POST", "/api/monthly/ops/settings/draft"),
            ("POST", "/api/monthly/ops/settings/approve"),
            ("GET", "/api/monthly/ops/places"),
            ("POST", "/api/monthly/ops/places/draft"),
            ("POST", "/api/monthly/ops/places/approve"),
            ("POST", "/api/monthly/ops/refresh"),
        }
        self.assertTrue(expected.issubset(set(router.routes)))

    def test_preview_api_requires_monthly_operations_access(self):
        denied = self.bot._json({"error": "unauthorized"}, 401)
        with mock.patch.object(
            self.bot, "_monthly_ops_gate", return_value=denied
        ), mock.patch.object(
            self.bot, "_build_monthly_preview_app"
        ) as builder:
            response = run(
                self.bot._api_monthly_preview_config(
                    FakeRequest(method="GET", query={"lang": "ar"})
                )
            )

        self.assertEqual(response.status, 401)
        builder.assert_not_called()

    def test_preview_api_is_a_thin_read_only_adapter(self):
        preview = mock.Mock()
        preview.config.return_value = {"ok": True, "preview": True}
        preview.browse.return_value = {"ok": True, "results": []}
        preview.match.return_value = {"ok": True, "catalog": []}
        preview.listing.return_value = {"ok": True, "listing": {"id": "101"}}
        with mock.patch.object(
            self.bot, "_build_monthly_preview_app", return_value=preview
        ) as builder:
            responses = (
                run(self.bot._api_monthly_preview_config(FakeRequest(method="GET"))),
                run(self.bot._api_monthly_preview_search(FakeRequest(method="GET"))),
                run(
                    self.bot._api_monthly_preview_match(
                        FakeRequest({"lang": "en", "purpose": "family"})
                    )
                ),
                run(
                    self.bot._api_monthly_preview_listing(
                        FakeRequest(match={"id": "101"}, method="GET")
                    )
                ),
            )

        self.assertTrue(all(response.status == 200 for response in responses))
        self.assertEqual(builder.call_count, 4)
        preview.config.assert_called_once_with("ar")
        preview.browse.assert_called_once()
        preview.match.assert_called_once_with({"purpose": "family"}, "en")
        preview.listing.assert_called_once()

    def test_preview_registers_only_read_only_customer_contracts(self):
        class Router:
            def __init__(self):
                self.routes = []

            def add_get(self, path, handler):
                self.routes.append(("GET", path))

            def add_post(self, path, handler):
                self.routes.append(("POST", path))

        router = Router()
        self.bot._register_monthly_v2_only_routes(router)
        routes = set(router.routes)
        self.assertTrue(
            {
                ("GET", "/monthly/ops/preview"),
                ("GET", "/monthly/ops/preview/search"),
                ("GET", "/monthly/ops/preview/match"),
                ("GET", "/monthly/ops/preview/id/{lid}"),
                ("GET", "/monthly/ops/preview/{slug}"),
                ("GET", "/api/monthly/ops/preview/config"),
                ("GET", "/api/monthly/ops/preview/search"),
                ("POST", "/api/monthly/ops/preview/match"),
                ("GET", "/api/monthly/ops/preview/listing/{id}"),
            }.issubset(routes)
        )
        self.assertFalse(
            any(
                method == "POST" and path.startswith("/api/monthly/ops/preview/")
                and path != "/api/monthly/ops/preview/match"
                for method, path in routes
            )
        )


if __name__ == "__main__":
    unittest.main()
