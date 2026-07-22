# -*- coding: utf-8 -*-
"""/api/gw/facts (GET + POST): the owner-editor endpoints for match/facts.py --
the single source of truth for guest-matching amenity signals (owner
instruction 2026-07-22: never derived from Hostaway amenities again). Both
verbs are dashboard-only (_dash_auth) -- getting that wrong leaks or lets
anyone edit inventory data. Hermetic: patches bot._gw_cache / _gw_overrides /
_gw_save_ov / DASHBOARD_TOKEN, no network, no disk writes."""
import asyncio
import json
import unittest
from unittest import mock

import bot


class _Req:
    def __init__(self, query=None, body=None):
        self.query = query or {}
        self.headers = {}
        self.cookies = {}
        self._body = body if body is not None else {}

    async def json(self):
        return self._body


class TestGwFactsAuthGate(unittest.TestCase):
    def test_get_handler_source_checks_dash_auth(self):
        src = open("bot.py", encoding="utf-8").read()
        i = src.index("async def _api_gw_facts(request):")
        self.assertIn("_dash_auth", src[i:i + 600])

    def test_post_handler_source_checks_dash_auth(self):
        src = open("bot.py", encoding="utf-8").read()
        i = src.index("async def _api_gw_facts_set(request):")
        self.assertIn("_dash_auth", src[i:i + 600])

    def test_both_routes_are_registered(self):
        src = open("bot.py", encoding="utf-8").read()
        self.assertIn('add_get("/api/gw/facts", _api_gw_facts)', src)
        self.assertIn('add_post("/api/gw/facts", _api_gw_facts_set)', src)

    def test_get_rejects_unauthenticated_request(self):
        with mock.patch.object(bot, "DASHBOARD_TOKEN", "gwf-test-token"):
            resp = asyncio.run(bot._api_gw_facts(_Req()))
        self.assertEqual(resp.status, 401)

    def test_post_rejects_unauthenticated_request(self):
        body = {"listing_id": "1", "facts": {"parking": True}}
        with mock.patch.object(bot, "DASHBOARD_TOKEN", "gwf-test-token"):
            resp = asyncio.run(bot._api_gw_facts_set(_Req(body=body)))
        self.assertEqual(resp.status, 403)


class TestGwFactsRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tok = "gwf-rt-token"
        self.patches = [
            mock.patch.object(bot, "DASHBOARD_TOKEN", self.tok),
            mock.patch.object(bot, "_gw_cache",
                              {"listings": [{"id": 1, "name": "Ouja | A"},
                                            {"id": 2, "name": "Ouja | B"}]}),
            mock.patch.object(bot, "_gw_overrides", {}),
            mock.patch.object(bot, "_gw_save_ov", lambda: None),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def _get(self):
        resp = asyncio.run(bot._api_gw_facts(_Req(query={"token": self.tok})))
        return resp.status, json.loads(resp.text)

    def _post(self, body):
        resp = asyncio.run(bot._api_gw_facts_set(_Req(query={"token": self.tok}, body=body)))
        return resp.status, json.loads(resp.text)

    def test_get_lists_every_listing_unanswered_by_default(self):
        status, data = self._get()
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(len(data["facts_def"]), 17)
        self.assertEqual(len(data["units"]), 2)
        for u in data["units"]:
            self.assertEqual(u["facts"], {})
            self.assertEqual(u["filled"], 0)
            self.assertEqual(u["total"], 17)

    def test_post_sets_a_fact_and_get_reflects_it(self):
        status, data = self._post({"listing_id": "1", "facts": {"parking": True}})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["facts"], {"parking": True})
        self.assertEqual(data["filled"], 1)

        _, gdata = self._get()
        unit1 = next(u for u in gdata["units"] if u["id"] == 1)
        self.assertEqual(unit1["facts"], {"parking": True})
        self.assertEqual(unit1["filled"], 1)
        # the other unit must stay untouched
        unit2 = next(u for u in gdata["units"] if u["id"] == 2)
        self.assertEqual(unit2["facts"], {})

    def test_post_false_is_stored_distinctly_from_unanswered(self):
        _, data = self._post({"listing_id": "1", "facts": {"parking": False}})
        self.assertIn("parking", data["facts"])
        self.assertIs(data["facts"]["parking"], False)
        self.assertEqual(data["filled"], 1)

    def test_post_null_clears_a_previously_set_fact(self):
        self._post({"listing_id": "1", "facts": {"parking": True, "elevator": False}})
        status, data = self._post({"listing_id": "1", "facts": {"parking": None}})
        self.assertEqual(status, 200)
        self.assertNotIn("parking", data["facts"])
        self.assertEqual(data["facts"], {"elevator": False})
        self.assertEqual(data["filled"], 1)

    def test_post_drops_unknown_keys(self):
        _, data = self._post({"listing_id": "1",
                              "facts": {"not_a_real_fact": True, "parking": True}})
        self.assertEqual(data["facts"], {"parking": True})

    def test_post_drops_non_boolean_non_null_values(self):
        _, data = self._post({"listing_id": "1",
                              "facts": {"parking": "yes", "elevator": 1, "pool": "false"}})
        self.assertEqual(data["facts"], {})

    def test_post_missing_listing_id_errors(self):
        status, data = self._post({"facts": {"parking": True}})
        self.assertEqual(status, 400)

    def test_post_missing_facts_body_errors(self):
        status, data = self._post({"listing_id": "1"})
        self.assertEqual(status, 400)

    def test_units_sorted_by_name(self):
        with mock.patch.object(bot, "_gw_cache",
                               {"listings": [{"id": 9, "name": "Ouja | Z"},
                                             {"id": 5, "name": "Ouja | A"}]}):
            _, data = self._get()
        self.assertEqual([u["id"] for u in data["units"]], [5, 9])


if __name__ == "__main__":
    unittest.main()
