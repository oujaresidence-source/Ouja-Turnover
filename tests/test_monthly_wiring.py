# -*- coding: utf-8 -*-
"""
S2 — the wiring, and the two invariants that are cheapest to lock before there is
any code to tempt anyone.

    1. READ-ONLY BY CONSTRUCTION. host.py exposes no Hostaway write capability,
       so no future code path in this package can write a price even by accident.
    2. THE NAMESPACE IS NOT SHARED. /api/monthly/* is the PUBLIC guest site.
       Nothing this package registers may land under it.

Run: python3 -m unittest tests.test_monthly_wiring
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import monthly                                    # noqa: E402
from monthly import host, routes                  # noqa: E402


class _Req:
    def __init__(self, role="admin", logged_in=True):
        self.role = role
        self.logged_in = logged_in
        self.method = "GET"


def _json(data, status=200):
    return {"status": status, "data": data}


class _App:
    """Just enough aiohttp app to record what register() asks for."""
    def __init__(self):
        self.routes = []
        self.router = self

    def add_get(self, path, handler):
        self.routes.append(("GET", path, handler))

    def add_post(self, path, handler):
        self.routes.append(("POST", path, handler))


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _wire(role="admin", logged_in=True):
    monthly.wire({
        "dash_auth": lambda r: r.logged_in,
        "req_role": lambda r: r.role,
        "actor": lambda r: "tester",
        "json_response": _json,
    })


class ReadOnlyByConstructionTest(unittest.TestCase):
    def test_host_exposes_no_hostaway_write(self):
        """A capability that was never wired cannot be misused. If someone adds
        api_post here later, they have to delete this test to do it — which is
        the point."""
        for verb in ("api_post", "api_put", "api_delete", "api_patch"):
            self.assertFalse(
                hasattr(host._Host, verb),
                "monthly.host must never expose %s — this package computes a "
                "price, it does not write one" % verb)

    def test_truncating_cache_is_not_wired(self):
        """CLAUDE.md trap #4. get_reservations_cached drops the NEWEST months, so
        a price built on it is a wrong price sent to an owner."""
        self.assertFalse(hasattr(host._Host, "get_reservations_cached"))
        self.assertTrue(hasattr(host._Host, "fetch_reservations_window"))


class NamespaceTest(unittest.TestCase):
    def test_nothing_lands_under_the_public_monthly_prefix(self):
        app = _App()
        monthly.register_routes(app)
        self.assertTrue(app.routes, "register() registered nothing at all")
        for method, path, _h in app.routes:
            self.assertFalse(
                path.startswith("/api/monthly/"),
                "%s %s collides with the PUBLIC guest site at /api/monthly/* — "
                "owner economics and guest pages must not share a prefix" % (method, path))
            self.assertTrue(
                path.startswith("/api/mrent/") or path == "/monthly-lab",
                "unexpected route %s %s" % (method, path))


class GateTest(unittest.TestCase):
    def test_logged_out_is_401(self):
        _wire()
        r = run(routes._safe(routes._api_health)(_Req(logged_in=False)))
        self.assertEqual(r["status"], 401)

    def test_non_admin_is_403_in_arabic(self):
        _wire()
        r = run(routes._safe(routes._api_health)(_Req(role="ops")))
        self.assertEqual(r["status"], 403)
        # «للمالك» — the alef of «ال» elides after the ل, so the bare word
        # «المالك» is not a substring of it.
        self.assertIn("للمالك", r["data"]["message"])

    def test_admin_reaches_the_handler(self):
        _wire()
        r = run(routes._safe(routes._api_health)(_Req(role="admin")))
        self.assertEqual(r["status"], 200)
        self.assertTrue(r["data"]["ok"])
        self.assertTrue(r["data"]["read_only"])

    def test_handler_errors_never_leak_a_traceback(self):
        _wire()

        async def boom(_request):
            raise RuntimeError("secret internal detail")

        r = run(routes._safe(boom)(_Req()))
        self.assertEqual(r["status"], 200)
        self.assertFalse(r["data"]["ok"])
        self.assertIn("RuntimeError", r["data"]["error"])


class BootstrapTest(unittest.TestCase):
    def test_bootstrap_never_raises_and_never_blocks_the_boot(self):
        """Called with brain unwired (as at import time here) it must defer, not
        explode: the tables are created on first real use either way."""
        self.assertIn(monthly.bootstrap(), ("created", "deferred"))
        self.assertIn(monthly.bootstrap(), ("created", "deferred"))


if __name__ == "__main__":
    unittest.main()
