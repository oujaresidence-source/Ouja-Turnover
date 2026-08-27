import asyncio
import json
import unittest
from unittest import mock


def run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def payload(response):
    return json.loads(response.text)


class FakeRequest:
    def __init__(self, body=None, match=None, query=None):
        self._body = {} if body is None else body
        self.match_info = match or {}
        self.query = query or {}
        self.query_string = ""
        self.path = "/api/monthly/test"
        self.method = "POST"
        self.headers = {}
        self.cookies = {}

    async def json(self):
        return self._body


class ShowcaseServiceFake:
    def __init__(self):
        self.calls = []

    def _call(self, name, *args):
        self.calls.append((name, args))
        return {"name": name, "args": list(args)}

    def portfolio(self):
        return self._call("portfolio")

    def group(self, group_id):
        return self._call("group", group_id)

    def create_draft(self, value, actor):
        return self._call("create_draft", value, actor)

    def save_draft(self, group_id, value, revision, actor):
        return self._call("save_draft", group_id, value, revision, actor)

    def approve(self, group_id, revision, actor):
        return self._call("approve", group_id, revision, actor)

    def set_price_enabled(self, group_id, enabled, revision, actor):
        return self._call("set_price_enabled", group_id, enabled, revision, actor)


class PublicAppFake:
    def __init__(self):
        self.calls = []

    def showcase(self, value):
        self.calls.append(value)
        return {"ok": True, "showcase": {"slug": value["slug"]}}


class MonthlyShowcaseBotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot

        cls.bot = bot

    def setUp(self):
        self.service = ShowcaseServiceFake()
        self.public = PublicAppFake()
        self.saved = (
            self.bot.MONTHLY_ENABLED,
            self.bot.MONTHLY_PUBLIC_V2,
            self.bot._monthly_showcase_service,
            self.bot._monthly_public_app,
        )
        self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
        self.bot._monthly_showcase_service = self.service
        self.bot._monthly_public_app = self.public
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
            self.bot._monthly_showcase_service,
            self.bot._monthly_public_app,
        ) = self.saved

    @staticmethod
    def group():
        return {
            "name_ar": "مجموعة الملقا",
            "name_en": "Al Malqa Collection",
            "slug": "al-malqa",
            "description_ar": "ثمان شقق في مبنى واحد",
            "description_en": "Eight homes in one building",
            "image_url": "https://images.example/building.jpg",
            "listing_ids": ["101", "102"],
            "fixed_monthly_rate_sar": 12500,
            "fixed_price_enabled": True,
        }

    def test_page_and_public_endpoint_are_thin_explicit_routes(self):
        page_request = FakeRequest(match={"showcase_slug": "al-malqa"})
        with mock.patch.object(
            self.bot, "_monthly_public_page_html", return_value="SHOWCASE"
        ) as renderer:
            response = run(self.bot._handle_monthly_showcase(page_request))
        self.assertEqual(response.status, 200)
        renderer.assert_called_once_with(
            "showcase", page_request, showcase_slug="al-malqa"
        )

        api_response = run(
            self.bot._api_monthly_v2_showcase(
                FakeRequest(query={"slug": "al-malqa", "lang": "ar"})
            )
        )
        self.assertEqual(api_response.status, 200)
        self.assertEqual(self.public.calls, [{"slug": "al-malqa", "lang": "ar"}])

    def test_listing_query_forwards_only_the_signed_showcase_context(self):
        token = "sc_showcase_group.1." + "A" * 43
        request = FakeRequest(
            query={"move_in": "2026-09-01", "duration_months": "1", "showcase_context": token}
        )

        result = self.bot._monthly_v2_listing_query(request, "101")

        self.assertEqual(result["showcase_context"], token)
        self.assertNotIn("fixed_monthly_rate_sar", result)

    def test_staff_group_workflow_uses_authenticated_service_contracts(self):
        cases = (
            (self.bot._api_monthly_showcases, FakeRequest(), "portfolio"),
            (self.bot._api_monthly_showcase, FakeRequest(match={"id": "showcase_a1"}), "group"),
            (self.bot._api_monthly_showcase_create, FakeRequest({"showcase": self.group()}), "create_draft"),
            (
                self.bot._api_monthly_showcase_draft,
                FakeRequest({"revision": 1, "showcase": self.group()}, {"id": "showcase_a1"}),
                "save_draft",
            ),
            (
                self.bot._api_monthly_showcase_approve,
                FakeRequest({"revision": 2}, {"id": "showcase_a1"}),
                "approve",
            ),
            (
                self.bot._api_monthly_showcase_price,
                FakeRequest({"revision": 3, "enabled": False}, {"id": "showcase_a1"}),
                "set_price_enabled",
            ),
        )
        for handler, request, expected in cases:
            with self.subTest(expected=expected):
                self.service.calls.clear()
                response = run(handler(request))
                self.assertEqual(response.status, 200, response.text)
                self.assertEqual(self.service.calls[0][0], expected)

    def test_routes_are_registered_before_the_generic_listing_slug(self):
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
            ("GET", "/api/monthly/ops/showcases"),
            ("GET", "/api/monthly/ops/showcase/{id}"),
            ("POST", "/api/monthly/ops/showcase"),
            ("POST", "/api/monthly/ops/showcase/{id}/draft"),
            ("POST", "/api/monthly/ops/showcase/{id}/approve"),
            ("POST", "/api/monthly/ops/showcase/{id}/price"),
        }
        self.assertTrue(expected.issubset(set(router.routes)))


if __name__ == "__main__":
    unittest.main()
