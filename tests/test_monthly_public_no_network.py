import ast
import asyncio
import inspect
import os
import tempfile
import unittest
from unittest import mock

from monthly_public.analytics import AnalyticsStore
from monthly_public.leads import LeadStore
from monthly_public.publication import validate_listing
from monthly_public.routes import MonthlyPublicApp
from monthly_public.snapshot import SnapshotStore
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


def run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class FakeRequest:
    def __init__(self, path="", method="GET", query=None):
        self.path = path
        self.method = method
        self.query = query or {}
        self.headers = {}
        self.cookies = {}


class RefreshSpySnapshot(SnapshotStore):
    def __init__(self):
        super().__init__()
        self.refresh_calls = 0

    def refresh(self, *args, **kwargs):
        self.refresh_calls += 1
        return super().refresh(*args, **kwargs)


class MonthlyPublicNoNetworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.snapshot = RefreshSpySnapshot()
        self.snapshot.refresh(
            {"refresh_ok": True, "catalog_complete": True, "listings": [valid_listing()]},
            valid_settings(),
            NOW,
        )
        self.snapshot.refresh_calls = 0
        self.leads = LeadStore(os.path.join(self.tmp.name, "leads.sqlite3"), clock=lambda: NOW)
        self.analytics = AnalyticsStore(os.path.join(self.tmp.name, "analytics.sqlite3"), clock=lambda: NOW)
        self.app = MonthlyPublicApp(
            snapshot_store=self.snapshot,
            settings=valid_settings(),
            lead_store=self.leads,
            analytics_store=self.analytics,
            approved_places={},
            session_secret=b"zero-network-secret-that-is-at-least-32-bytes",
            clock=lambda: NOW,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_customer_method_reads_current_without_refreshing(self):
        session = self.app.config()["session_id"]
        request = {
            "purpose": "family",
            "residents": 2,
            "sleeping": "one_bedroom",
            "move_in": "2026-09-01",
            "duration_months": 1,
            "flexibility": "fixed",
        }
        calls = [
            lambda: self.app.config(),
            lambda: self.app.browse({}),
            lambda: self.app.browse({"move_in": "2026-09-01", "duration_months": 1}),
            lambda: self.app.match(request),
            lambda: self.app.listing({"listing_id": "1001"}),
            lambda: self.app.quote({"listing_id": "1001", "move_in": "2026-09-01", "duration_months": 1}),
            lambda: self.app.event({"event": "landing_view", "session_id": session}),
            lambda: self.app.lead({"session_id": session, "listing_id": "1001", "request": request, "lang": "ar"}),
        ]
        with mock.patch("socket.create_connection", side_effect=AssertionError("network reached")) as network:
            for call in calls:
                self.assertIsInstance(call(), dict)
        network.assert_not_called()
        self.assertEqual(self.snapshot.refresh_calls, 0)

    def test_routes_module_has_no_network_or_provider_imports(self):
        tree = ast.parse(inspect.getsource(__import__("monthly_public.routes", fromlist=["routes"])))
        forbidden = {"requests", "aiohttp", "urllib", "httpx", "hostaway", "monthly"}
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(forbidden.intersection(imported))

    def test_bot_monthly_v2_handlers_do_not_call_refresh_or_provider(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source)
        names = {
            "_api_monthly_v2_config",
            "_api_monthly_v2_search",
            "_api_monthly_v2_listing",
            "_api_monthly_v2_quote",
            "_api_monthly_v2_match",
            "_api_monthly_v2_lead",
            "_api_monthly_v2_event",
            "_api_monthly_v2_featured",
            "_api_monthly_v2_deals",
        }
        found = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                found[node.name] = ast.get_source_segment(source, node) or ""
        self.assertEqual(set(found), names)
        forbidden = ("api_get(", "api_post(", "_gw_sync(", "_mcal_refresh_sync(", "_mengine_refresh_sync(")
        for name, body in found.items():
            for token in forbidden:
                self.assertNotIn(token, body, "%s reached %s" % (name, token))

    def test_bot_source_adapter_uses_no_provider_or_legacy_discount_price(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source)
        adapter = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_monthly_public_source_adapter"
        )
        body = ast.get_source_segment(source, adapter) or ""
        for token in ("api_get(", "_gw_sync(", "monthly_quote(", "monthly_pricing(",
                      '"before"', '"after"', '"discount"'):
            self.assertNotIn(token, body)
        self.assertIn("_gw_cache", body)
        self.assertIn("_mcal", body)
        self.assertIn("_monthly_public_engine_prices", body)


class MonthlyPublicBotBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot
        cls.bot = bot

    def test_anonymous_middleware_allows_only_the_three_public_monthly_posts(self):
        async def reached(request):
            return request.path

        public = ("/api/monthly/match", "/api/monthly/lead", "/api/monthly/event")
        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        try:
            self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
            for path in public:
                result = run(self.bot._role_enforce_mw(FakeRequest(path, "POST"), reached))
                self.assertEqual(result, path)
            for private in ("/api/monthly/ops/response", "/api/monthly/ops/outcome", "/api/monthly/admin"):
                response = run(self.bot._role_enforce_mw(FakeRequest(private, "POST"), reached))
                self.assertEqual(response.status, 401)

            for enabled, v2 in ((False, True), (True, False), (False, False)):
                self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = enabled, v2
                for path in public:
                    response = run(self.bot._role_enforce_mw(
                        FakeRequest(path, "POST"), reached
                    ))
                    self.assertEqual(response.status, 401)
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved

    def test_v2_only_routes_register_only_when_both_switches_are_on(self):
        class Router:
            def __init__(self):
                self.routes = []

            def add_get(self, path, handler):
                self.routes.append(("GET", path, handler))

            def add_post(self, path, handler):
                self.routes.append(("POST", path, handler))

        expected = {
            ("POST", "/api/monthly/match"),
            ("POST", "/api/monthly/lead"),
            ("POST", "/api/monthly/event"),
            ("GET", "/api/monthly/ops/health"),
            ("GET", "/api/monthly/ops/funnel"),
            ("POST", "/api/monthly/ops/response"),
            ("POST", "/api/monthly/ops/outcome"),
        }
        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        try:
            for enabled, v2 in ((False, True), (True, False), (False, False)):
                self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = enabled, v2
                router = Router()
                self.bot._register_monthly_v2_only_routes(router)
                self.assertEqual(router.routes, [])
            self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
            router = Router()
            self.bot._register_monthly_v2_only_routes(router)
            self.assertEqual({(method, path) for method, path, _ in router.routes}, expected)
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved

    def test_every_v2_handler_refuses_calls_when_either_switch_is_off(self):
        handlers = (
            self.bot._handle_monthly_v2_img,
            self.bot._api_monthly_v2_config,
            self.bot._api_monthly_v2_search,
            self.bot._api_monthly_v2_featured,
            self.bot._api_monthly_v2_deals,
            self.bot._api_monthly_v2_listing,
            self.bot._api_monthly_v2_quote,
            self.bot._api_monthly_v2_match,
            self.bot._api_monthly_v2_lead,
            self.bot._api_monthly_v2_event,
            self.bot._api_monthly_v2_ops_health,
            self.bot._api_monthly_v2_ops_funnel,
            self.bot._api_monthly_v2_ops_response,
            self.bot._api_monthly_v2_ops_outcome,
        )
        saved = (
            self.bot.MONTHLY_ENABLED,
            self.bot.MONTHLY_PUBLIC_V2,
            self.bot._monthly_public_app,
        )
        self.bot._monthly_public_app = object()
        try:
            for enabled, v2 in ((False, True), (True, False)):
                self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = enabled, v2
                for handler in handlers:
                    with self.subTest(enabled=enabled, v2=v2, handler=handler.__name__):
                        response = run(handler(FakeRequest(
                            "/api/monthly/test", "POST",
                            {"u": "https://images.example.test/home.jpg"},
                        )))
                        self.assertEqual(response.status, 404)
        finally:
            (self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2,
             self.bot._monthly_public_app) = saved

    def test_calendar_adapter_rejects_a_gap_inside_reported_coverage(self):
        original = self.bot._mcal
        self.bot._mcal = {
            "units": {"1001": {
                "2026-09-01": [1, 400, 0],
                "2026-09-03": [1, 400, 0],
            }},
            "unit_synced_at": {"1001": "2026-08-25T09:40:00+03:00"},
        }
        try:
            calendar = self.bot._monthly_public_calendar("1001")
            self.assertIsNone(calendar)
            publication = validate_listing(
                valid_listing(calendar=calendar), valid_settings(), NOW
            )
            self.assertEqual(publication.availability_status, "pending")
            self.assertFalse(publication.exact_match_eligible)
        finally:
            self.bot._mcal = original

    def test_calendar_adapter_rejects_malformed_cached_rows(self):
        malformed_rows = (
            None,
            [],
            "not-a-calendar-row",
            [2, 400, 0],
            ["1", 400, 0],
            [1, 400],
            [1, 400, 2],
            [1, "400", 0],
        )
        original = self.bot._mcal
        try:
            for row in malformed_rows:
                with self.subTest(row=row):
                    self.bot._mcal = {
                        "units": {"1001": {"2026-09-01": row}},
                        "unit_synced_at": {
                            "1001": "2026-08-25T09:40:00+03:00",
                        },
                    }
                    calendar = self.bot._monthly_public_calendar("1001")
                    self.assertIsNone(calendar)
                    publication = validate_listing(
                        valid_listing(calendar=calendar), valid_settings(), NOW
                    )
                    self.assertEqual(publication.availability_status, "pending")
                    self.assertFalse(publication.exact_match_eligible)
        finally:
            self.bot._mcal = original

    def test_cold_rating_cache_is_warmed_locally_without_network(self):
        saved = {
            "gw_cache": self.bot._gw_cache,
            "gw_overrides": self.bot._gw_overrides,
            "gw_ratings_cache": self.bot._gw_ratings_cache,
            "reviews": self.bot._reviews,
            "has_monthly": self.bot._HAS_MONTHLY,
            "mcal": self.bot._mcal,
            "monthly_cfg": self.bot._monthly_cfg,
        }
        self.bot._gw_cache = {
            "listings": [{
                "id": 1001,
                "name": "Ouja | Cached rating test",
                "active": True,
                "images": [],
                "amenities": [],
            }],
            "synced_at": "2026-08-25T09:00:00+03:00",
        }
        self.bot._gw_overrides = {"1001": {}}
        self.bot._gw_ratings_cache = {"t": 0.0, "map": {}}
        self.bot._reviews = {
            "r1": {"listing_id": 1001, "rating": 4.0},
            "r2": {"listing_id": 1001, "rating": 4.5},
            "r3": {"listing_id": 1001, "rating": 5.0},
        }
        self.bot._HAS_MONTHLY = False
        self.bot._mcal = {"units": {}, "unit_synced_at": {}}
        self.bot._monthly_cfg = {"hidden": []}
        try:
            with mock.patch.object(self.bot.requests, "get", side_effect=AssertionError("network reached")) as network:
                source = self.bot._monthly_public_source_adapter()
            network.assert_not_called()
            self.assertEqual(source["listings"][0]["rating"], 4.5)
            self.assertEqual(source["listings"][0]["reviews_count"], 3)
        finally:
            self.bot._gw_cache = saved["gw_cache"]
            self.bot._gw_overrides = saved["gw_overrides"]
            self.bot._gw_ratings_cache = saved["gw_ratings_cache"]
            self.bot._reviews = saved["reviews"]
            self.bot._HAS_MONTHLY = saved["has_monthly"]
            self.bot._mcal = saved["mcal"]
            self.bot._monthly_cfg = saved["monthly_cfg"]

    def test_v2_monthly_image_handler_redirects_directly_without_server_fetch(self):
        url = "https://images.example.test/home.jpg"
        saved = self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2
        self.bot.MONTHLY_ENABLED = self.bot.MONTHLY_PUBLIC_V2 = True
        try:
            with mock.patch.object(self.bot.requests, "get", side_effect=AssertionError("network reached")) as network:
                with self.assertRaises(self.bot.web.HTTPFound) as raised:
                    run(self.bot._handle_monthly_v2_img(FakeRequest(
                        "/monthly/img", "GET", {"u": url, "w": "1200"}
                    )))
        finally:
            self.bot.MONTHLY_ENABLED, self.bot.MONTHLY_PUBLIC_V2 = saved
        network.assert_not_called()
        self.assertEqual(raised.exception.location, url)
        source = inspect.getsource(self.bot.start_web_server)
        self.assertIn("_handle_monthly_v2_img", source)


if __name__ == "__main__":
    unittest.main()
