import ast
import inspect
import os
import tempfile
import unittest
from unittest import mock

from monthly_public.analytics import AnalyticsStore
from monthly_public.leads import LeadStore
from monthly_public.routes import MonthlyPublicApp
from monthly_public.snapshot import SnapshotStore
from tests.monthly_public_fixtures import NOW, valid_listing, valid_settings


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


if __name__ == "__main__":
    unittest.main()
