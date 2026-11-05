# -*- coding: utf-8 -*-
"""Speed fix of 2026-11-05 — the three things that made the whole app feel laggy.

  1. Nothing was compressed. /dashboard is 1.3 MB of HTML; every text response left
     the server raw and only SOME of Railway's edge proxies gzip on the way out.
     _compress_mw now gzips text bodies itself (memoised for big static pages).
  2. Four handlers ran Hostaway / Google calls directly ON the event loop
     (_api_fb_profit, _api_strategy, _handle_invest, _api_listings_geocode). While one
     waited on the 11-calls/10s throttle, EVERY page and the Discord heartbeat froze.
  3. get_listings_map() refreshed synchronously once an hour, and ~25 async handlers
     call it on the loop — so once an hour some click froze everyone. It now serves the
     stale map at once and refreshes behind the reader.
Synthetic, no network.
Run: python3 -m unittest tests.test_speed_fix
"""
import asyncio
import gzip
import re
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import bot

ROOT = Path(__file__).resolve().parents[1]
# Captured at import: some older tests replace bot.get_listings_map with a lambda and never
# restore it, so by the time these tests run the module attribute may be someone's stub.
REAL_GET_LISTINGS_MAP = bot.get_listings_map
BOT_SRC = (ROOT / "bot.py").read_text(encoding="utf-8")


def _func_body(name):
    m = re.search(r"^(async def|def) %s\(" % re.escape(name), BOT_SRC, re.M)
    assert m, "function %s not found" % name
    rest = BOT_SRC[m.start():]
    nxt = re.search(r"\n(?:async def |def |@|class )", rest[1:])
    return rest[:nxt.start() + 1] if nxt else rest


BIG_HTML = "<html><body>" + ("<div class='row'>عوجا Ouja</div>\n" * 20000) + "</body></html>"
SMALL_JSON = '{"items": [' + ",".join('{"id": %d, "name": "unit"}' % i for i in range(200)) + "]}"
WEBP = b"RIFF" + b"\x00" * 5000


async def _h_html(request):
    return web.Response(text=BIG_HTML, content_type="text/html")


async def _h_json(request):
    return web.Response(text=SMALL_JSON, content_type="application/json")


async def _h_webp(request):
    return web.Response(body=WEBP, content_type="image/webp")


async def _h_tiny(request):
    return web.Response(text="ok", content_type="text/plain")


async def _h_notransform(request):
    return web.Response(text=BIG_HTML, content_type="text/html",
                        headers={"Cache-Control": "no-transform"})


async def _h_304(request):
    return web.Response(status=304, headers={"ETag": '"x"'})


def _run(coro):
    return asyncio.run(coro)


async def _with_client(routes, fn):
    app = web.Application(middlewares=[bot._compress_mw])
    for path, h in routes:
        app.router.add_get(path, h)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        return await fn(client)
    finally:
        await client.close()


ROUTES = [("/html", _h_html), ("/json", _h_json), ("/webp", _h_webp), ("/tiny", _h_tiny),
          ("/nt", _h_notransform), ("/304", _h_304), ("/dashboard", bot._handle_dashboard)]
GZ = {"Accept-Encoding": "gzip, deflate, br"}


async def _raw(client, path, headers=None, method="GET"):
    r = await client.request(method, path, headers=headers or {}, auto_decompress=False)
    body = await r.read()
    return r, body


class CompressionMiddleware(unittest.TestCase):
    def test_big_html_is_gzipped_and_identical(self):
        async def go(c):
            r, body = await _raw(c, "/html", GZ)
            self.assertEqual(r.status, 200)
            self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
            self.assertIn("Accept-Encoding", r.headers.get("Vary", ""))
            self.assertEqual(gzip.decompress(body).decode("utf-8"), BIG_HTML)
            self.assertLess(len(body), len(BIG_HTML.encode()) / 5)
        _run(_with_client(ROUTES, go))

    def test_small_json_is_gzipped(self):
        async def go(c):
            r, body = await _raw(c, "/json", GZ)
            self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
            self.assertEqual(gzip.decompress(body).decode(), SMALL_JSON)
        _run(_with_client(ROUTES, go))

    def test_left_alone(self):
        async def go(c):
            # positive control first: the same client DOES compress /html
            r, _ = await _raw(c, "/html", GZ)
            self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
            for path, hdrs in (("/webp", GZ), ("/tiny", GZ), ("/nt", GZ), ("/html", {"Accept-Encoding": "identity"})):
                r, body = await _raw(c, path, hdrs)
                self.assertIsNone(r.headers.get("Content-Encoding"), path)
            r, body = await _raw(c, "/webp", GZ)
            self.assertEqual(body, WEBP)
            r, body = await _raw(c, "/304", GZ)
            self.assertEqual(r.status, 304)
            self.assertFalse(body)
            r, body = await _raw(c, "/html", GZ, method="HEAD")
            self.assertIsNone(r.headers.get("Content-Encoding"))
        _run(_with_client(ROUTES, go))

    def test_dashboard_on_the_wire_and_memoised(self):
        bot._gz_memo.clear()
        calls = []
        real = bot._gz_bytes

        def spy(b):
            calls.append(len(b))
            return real(b)

        async def go(c):
            with mock.patch.object(bot, "_gz_bytes", side_effect=spy):
                r1, b1 = await _raw(c, "/dashboard", GZ)
                r2, b2 = await _raw(c, "/dashboard", GZ)
            self.assertEqual(r1.headers.get("Content-Encoding"), "gzip")
            self.assertEqual(gzip.decompress(b1).decode("utf-8"), bot.DASHBOARD_HTML)
            self.assertLess(len(b1), 400 * 1024, "dashboard on the wire must be < 400 KB")
            self.assertEqual(b1, b2)
            self.assertEqual(len(calls), 1, "the 1.3 MB page must be compressed once, then memoised")
            tag = r1.headers["ETag"]
            r3, b3 = await _raw(c, "/dashboard", dict(GZ, **{"If-None-Match": tag}))
            self.assertEqual(r3.status, 304)
            self.assertFalse(b3)
        _run(_with_client(ROUTES, go))

    def test_registered_outermost_on_the_real_app(self):
        body = _func_body("start_web_server")
        self.assertIn("middlewares=[_compress_mw, _security_headers_mw, _role_enforce_mw]", body)


class HandlersOffTheLoop(unittest.TestCase):
    CASES = {
        "_api_fb_profit": ("_fb_unit_profitability(", "_fb_company_profitability("),
        "_api_strategy": ("_strategy_view(",),
        "_handle_invest": ("_render_invest_html(",),
        "_api_listings_geocode": ("requests.get(",),
    }

    def test_each_blocking_call_goes_through_web_thread(self):
        for handler, calls in self.CASES.items():
            body = _func_body(handler)
            self.assertIn("web_thread(", body, handler)
            for c in calls:
                name = c[:-1]
                direct = re.findall(r"(?<![\w.])%s\(" % re.escape(name), body)
                self.assertEqual(direct, [], "%s still calls %s directly on the loop" % (handler, name))
                self.assertRegex(body, r"web_thread\(\s*%s\s*[,)]" % re.escape(name), handler)

    def test_strategy_handler_really_runs_off_loop(self):
        seen = {}

        def fake_view(lid):
            seen["thread"] = threading.current_thread().name
            return {"lid": lid}
        req = mock.Mock()
        req.query = {"lid": "7"}
        with mock.patch.object(bot, "_dash_auth", return_value=True), \
             mock.patch.object(bot, "_strategy_view", side_effect=fake_view):
            asyncio.run(bot._api_strategy(req))
        self.assertTrue(seen["thread"].startswith("ouja-web"), seen)


class ListingsMapNeverFreezes(unittest.TestCase):
    def setUp(self):
        self.saved = dict(bot._listings)
        self.addCleanup(lambda: (bot._listings.clear(), bot._listings.update(self.saved)))

    def test_stale_map_answers_at_once_and_refreshes_behind(self):
        done = threading.Event()

        def slow_fetch():
            time.sleep(1.5)
            bot._listings["map"], bot._listings["ts"] = {1: "new"}, time.time()
            done.set()
            return bot._listings["map"]
        bot._listings.clear()
        bot._listings.update({"map": {1: "old"}, "ts": time.time() - 7200})
        with mock.patch.object(bot, "_listings_map_fetch", side_effect=slow_fetch) as f:
            t0 = time.time()
            m = REAL_GET_LISTINGS_MAP()
            self.assertLess(time.time() - t0, 0.2, "a stale map must not block the caller")
            self.assertEqual(m, {1: "old"})
            REAL_GET_LISTINGS_MAP()                      # inside the cooldown: no second kick
            self.assertTrue(done.wait(5), "background refresh never ran")
            self.assertEqual(f.call_count, 1)
        self.assertEqual(REAL_GET_LISTINGS_MAP(), {1: "new"})

    def test_cold_start_still_fills_synchronously(self):
        bot._listings.clear()
        bot._listings.update({"map": {}, "ts": 0})

        def fetch():
            bot._listings["map"], bot._listings["ts"] = {5: "x"}, time.time()
            return bot._listings["map"]
        with mock.patch.object(bot, "_listings_map_fetch", side_effect=fetch):
            self.assertEqual(REAL_GET_LISTINGS_MAP(), {5: "x"})

    def test_fresh_map_does_not_refetch(self):
        bot._listings.clear()
        bot._listings.update({"map": {2: "y"}, "ts": time.time()})
        with mock.patch.object(bot, "_listings_map_fetch") as f:
            self.assertEqual(REAL_GET_LISTINGS_MAP(), {2: "y"})
            f.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class RefusedListingsAreRemembered(unittest.TestCase):
    """Live logs 2026-11-05: the same 21 listings answered 403 every cycle, and each one
    cost calendar call + forced token refresh + calendar call on the shared throttle."""

    def setUp(self):
        self.calls, self.refreshes = [], []
        bot._ha_forbidden.clear()
        self.addCleanup(bot._ha_forbidden.clear)
        saved_tok = dict(bot._token)
        self.addCleanup(lambda: (bot._token.clear(), bot._token.update(saved_tok)))
        bot._token.update({"value": "T", "expires_at": time.time() + 9999, "issued_at": time.time()})

        def fake_request(method, url, **kw):
            self.calls.append(url)
            r = mock.Mock()
            r.status_code = 403 if "/listings/9/" in url else 200
            r.headers = {}
            r.json = lambda: {"result": []}

            def rfs():
                if r.status_code >= 400:
                    raise bot.requests.HTTPError("%d Client Error: Forbidden for url: %s" % (r.status_code, url))
            r.raise_for_status = rfs
            return r

        def fake_token(force=False):
            if force:
                self.refreshes.append(1)
                bot._token["issued_at"] = time.time()
            return "T"
        for p in (mock.patch.object(bot._ha_session, "request", side_effect=fake_request),
                  mock.patch.object(bot, "get_token", side_effect=fake_token),
                  mock.patch.object(bot, "_ha_throttle_acquire", lambda *a, **k: None)):
            p.start()
            self.addCleanup(p.stop)

    def test_fresh_token_403_is_one_call_then_zero(self):
        with self.assertRaises(bot.requests.HTTPError):
            bot.api_get("/listings/9/calendar", params={})
        self.assertEqual((len(self.calls), len(self.refreshes)), (1, 0),
                         "a fresh token must not be refreshed for a listing 403")
        t0 = time.time()
        with self.assertRaises(bot.requests.HTTPError) as cm:
            bot.api_get("/listings/9/calendar", params={})
        self.assertLess(time.time() - t0, 0.05)
        self.assertIn("Forbidden", str(cm.exception))
        self.assertEqual(len(self.calls), 1, "the remembered listing must not be asked again")
        self.assertIn("9", bot.ha_forbidden_listings())

    def test_other_listings_and_writes_are_unaffected(self):
        with self.assertRaises(bot.requests.HTTPError):
            bot.api_get("/listings/9/calendar", params={})
        self.assertEqual(bot.api_get("/listings/10/calendar", params={}), {"result": []})
        self.assertEqual(len(self.calls), 2)

    def test_old_token_still_gets_one_refresh(self):
        bot._token["issued_at"] = time.time() - 3600
        with self.assertRaises(bot.requests.HTTPError):
            bot.api_get("/listings/9/calendar", params={})
        self.assertEqual((len(self.calls), len(self.refreshes)), (2, 1))

    def test_memory_expires(self):
        bot._ha_forbidden["9"] = time.time() - bot.HOSTAWAY_FORBIDDEN_TTL_S - 1
        with self.assertRaises(bot.requests.HTTPError):
            bot.api_get("/listings/9/calendar", params={})
        self.assertEqual(len(self.calls), 1, "after the TTL Hostaway is asked again")

    def test_a_refused_write_does_not_block_reads(self):
        with self.assertRaises(bot.requests.HTTPError):
            bot.api_put("/listings/9/calendar", {"price": 1})
        self.assertEqual(bot.ha_forbidden_listings(), {}, "a refused PUT must not be remembered")
        self.calls.clear()
        with self.assertRaises(bot.requests.HTTPError):
            bot.api_get("/listings/9/calendar", params={})
        self.assertEqual(len(self.calls), 1, "the GET after a refused PUT must really be asked")


class GuestSearchHasATimeCap(unittest.TestCase):
    """A dated /apartments search must answer within STAY_LIVE_BUDGET_S even when Hostaway
    is slow; the slow units come back as «unknown», the page still lists them."""

    def setUp(self):
        from tests.test_match_api import _fake_snaps_for_search, _fake_gw_listing_public
        snaps = _fake_snaps_for_search(5)
        saved = bot._mcal
        self.addCleanup(setattr, bot, "_mcal", saved)
        bot._mcal = {"units": {}, "unit_synced_at": {}}           # nothing in the store -> all live
        for p in (mock.patch.object(bot, "_gw_visible_snaps", return_value=snaps),
                  mock.patch.object(bot, "_gw_listing_public", side_effect=_fake_gw_listing_public),
                  mock.patch.object(bot, "STAY_LIVE_BUDGET_S", 0.6)):
            p.start()
            self.addCleanup(p.stop)
        self.release = threading.Event()
        self.addCleanup(self.release.set)

    def live(self, lid, ci, co):
        if lid in (2, 4):                                        # Hostaway is slow for these two
            self.release.wait(10)
        return {"available": True, "nights": 3, "total": 900, "avg": 300}

    def test_slow_units_do_not_hold_the_guest(self):
        with mock.patch.object(bot, "unit_availability_price", side_effect=self.live):
            t0 = time.time()
            out = bot._gw_search(ci="2026-11-01", co="2026-11-04")
            took = time.time() - t0
        self.assertLess(took, 2.0, "search waited %.1fs — the cap did not hold" % took)
        self.assertEqual(len(out["results"]), 5, "slow units are still listed (availability unknown)")
        self.assertTrue(out["avail_error"])
        known = [r for r in out["results"] if r.get("est_total") == 900]
        self.assertEqual(len(known), 3)

    def test_fast_hostaway_is_unchanged(self):
        self.release.set()
        with mock.patch.object(bot, "unit_availability_price", side_effect=self.live):
            out = bot._gw_search(ci="2026-11-01", co="2026-11-04")
        self.assertFalse(out["avail_error"])
        self.assertEqual(len([r for r in out["results"] if r.get("est_total") == 900]), 5)


class AnalyticsSaveIsBatched(unittest.TestCase):
    def test_many_events_one_write(self):
        writes = []
        saved_events = list(bot._gw_analytics.get("events", []))
        self.addCleanup(lambda: bot._gw_analytics.__setitem__("events", saved_events))
        with mock.patch.object(bot, "_gw_save_an", side_effect=lambda: writes.append(1)), \
             mock.patch.object(bot, "GW_AN_SAVE_EVERY_S", 0.3):
            t0 = time.time()
            for i in range(200):
                bot._gw_track({"event": "stay_page_view", "session": str(i)})
            self.assertLess(time.time() - t0, 0.5, "tracking must not write on the caller")
            self.assertEqual(writes, [], "no write inline")
            deadline = time.time() + 5
            while not writes and time.time() < deadline:
                time.sleep(0.05)
            time.sleep(0.2)
        self.assertEqual(len(writes), 1, "200 events -> one batched write")


class LivenessGuard(unittest.TestCase):
    """A hang must heal itself (restart) and name its cause (thread fingerprint) — but never
    during warm-up, never twice inside the cooldown, never when switched off."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(bot, "STATE_DIR", self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def test_verdicts(self):
        now = time.time()
        with mock.patch.object(bot, "LIVENESS_AUTORESTART", True):
            self.assertEqual(bot._liveness_verdict(now, 1, None, 5000), "ok")
            self.assertTrue(bot._liveness_verdict(now, 200, None, 5000).startswith("restart:"))
            self.assertTrue(bot._liveness_verdict(now, 0, 500, 5000).startswith("restart:"))
            self.assertTrue(bot._liveness_verdict(now, 200, None, 60).startswith("warn:"), "warm-up")
            with open(bot._state_path("liveness_last_restart.txt"), "w") as f:
                f.write(str(now - 60))
            self.assertTrue(bot._liveness_verdict(now, 200, None, 5000).startswith("warn:"), "cooldown")
        with mock.patch.object(bot, "LIVENESS_AUTORESTART", False):
            self.assertTrue(bot._liveness_verdict(now + 99999, 200, None, 5000).startswith("warn:"))

    def test_a_blocked_loop_is_caught_and_fingerprinted(self):
        printed = []
        exits = []
        patches = [mock.patch.object(bot, "LIVENESS_TICK_S", 0.1),
                   mock.patch.object(bot, "LIVENESS_LOOP_STUCK_S", 0.5),
                   mock.patch.object(bot, "LIVENESS_MIN_UPTIME_S", 0),
                   mock.patch.object(bot, "LIVENESS_AUTORESTART", True),
                   mock.patch.object(bot, "persist_state", lambda: None),
                   mock.patch.object(bot.os, "_exit", side_effect=lambda c: exits.append(c)),
                   mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a))))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        saved = dict(bot._liveness)
        self.addCleanup(lambda: (bot._liveness.clear(), bot._liveness.update(saved)))
        bot._liveness.update({"boot": time.time() - 10, "started": False})

        def a_function_that_freezes_the_loop():
            time.sleep(1.5)                      # what a sync Hostaway call on the loop does

        async def main():
            threading.Thread(target=bot._liveness_run, args=(asyncio.get_running_loop(),),
                             daemon=True).start()
            await asyncio.sleep(0.3)
            a_function_that_freezes_the_loop()
            await asyncio.sleep(0.3)
        asyncio.run(main())
        text = "\n".join(printed)
        self.assertIn("LIVENESS TRIP", text)
        self.assertIn("a_function_that_freezes_the_loop", text, "fingerprint must name the culprit")
        self.assertTrue(exits and exits[0] == 1, "must exit(1) so Railway restarts it")

    def test_guard_is_started_by_the_web_server(self):
        self.assertIn("start_liveness_guard()", _func_body("start_web_server"))


class LivenessSeesAJammedWebLane(unittest.TestCase):
    def test_full_web_pool_trips(self):
        from concurrent.futures import ThreadPoolExecutor
        printed, exits = [], []
        jam = threading.Event()
        pool = ThreadPoolExecutor(max_workers=1)
        pool.submit(jam.wait, 10)                 # the only worker is stuck (a 403 storm, say)
        self.addCleanup(lambda: (jam.set(), pool.shutdown(wait=False)))
        patches = [mock.patch.object(bot, "_web_pool", pool),
                   mock.patch.object(bot, "LIVENESS_TICK_S", 0.1),
                   mock.patch.object(bot, "LIVENESS_WEB_STUCK_S", 0.6),
                   mock.patch.object(bot, "LIVENESS_MIN_UPTIME_S", 0),
                   mock.patch.object(bot, "LIVENESS_AUTORESTART", True),
                   mock.patch.object(bot, "_liveness_cooldown_ok", lambda now: True),
                   mock.patch.object(bot, "persist_state", lambda: None),
                   mock.patch.object(bot, "_state_path", lambda n: "/tmp/ouja_liveness_" + n),
                   mock.patch.object(bot.os, "_exit", side_effect=lambda c: exits.append(c)),
                   mock.patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a))))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        saved = dict(bot._liveness)
        self.addCleanup(lambda: (bot._liveness.clear(), bot._liveness.update(saved)))
        bot._liveness["boot"] = time.time() - 10

        async def main():
            threading.Thread(target=bot._liveness_run, args=(asyncio.get_running_loop(),),
                             daemon=True).start()
            for _ in range(30):
                if exits:
                    break
                await asyncio.sleep(0.1)          # the loop itself stays healthy
        asyncio.run(main())
        self.assertTrue(exits, "a jammed web lane must trip the guard")
        self.assertIn("web lane", "\n".join(printed))


class HostawayOutageIsNotRefusedListings(unittest.TestCase):
    """A 403 on one listing is that listing. A 403 on most of the portfolio at once is
    Hostaway itself — remembering those would hide every healthy unit for an hour after
    Hostaway recovered (simulated 2026-11-05: 70/70 units, at any token age)."""

    def setUp(self):
        self.calls = []
        self.outage = True
        bot._ha_forbidden.clear()
        bot._ha_forbidden_outage.update({"until": 0, "trips": 0})
        self.addCleanup(bot._ha_forbidden.clear)
        self.addCleanup(lambda: bot._ha_forbidden_outage.update({"until": 0, "trips": 0}))
        saved_tok = dict(bot._token)
        self.addCleanup(lambda: (bot._token.clear(), bot._token.update(saved_tok)))
        bot._token.update({"value": "T", "expires_at": time.time() + 9999, "issued_at": time.time()})

        def fake_request(method, url, **kw):
            self.calls.append(url)
            r = mock.Mock()
            r.status_code = 403 if self.outage else 200
            r.headers = {}
            r.json = lambda: {"result": []}

            def rfs():
                if r.status_code >= 400:
                    raise bot.requests.HTTPError("%d Client Error: Forbidden for url: %s" % (r.status_code, url))
            r.raise_for_status = rfs
            return r
        for p in (mock.patch.object(bot._ha_session, "request", side_effect=fake_request),
                  mock.patch.object(bot, "get_token", lambda force=False: "T"),
                  mock.patch.object(bot, "_ha_throttle_acquire", lambda *a, **k: None),
                  mock.patch("builtins.print")):
            p.start()
            self.addCleanup(p.stop)

    def sweep(self, ids):
        """Ask for every unit once; returns how many came back refused."""
        refused = 0
        for i in ids:
            try:
                bot.api_get("/listings/%d/calendar" % i, params={})
            except bot.requests.HTTPError:
                refused += 1
        return refused

    def test_a_portfolio_wide_403_leaves_nothing_blocked_after_recovery(self):
        ids = list(range(1000, 1070))
        self.assertEqual(self.sweep(ids), 70)
        self.outage = False
        self.calls.clear()
        self.assertEqual(self.sweep(ids), 0, "healthy units must not stay blocked after the outage")
        self.assertEqual(len(self.calls), 70, "every unit must really be asked again")
        self.assertEqual(bot.ha_forbidden_listings(), {})
        self.assertEqual(bot._ha_forbidden_outage["trips"], 1)

    def test_the_real_refused_group_is_still_remembered(self):
        ids = list(range(2000, 2021))             # the 21 units seen in the live logs
        self.sweep(ids)
        self.calls.clear()
        self.assertEqual(self.sweep(ids), 21)
        self.assertEqual(self.calls, [], "21 refused units are under the cap: no real calls")
        self.assertEqual(bot._ha_forbidden_outage["trips"], 0)

    def test_nothing_is_remembered_during_the_pause_then_it_works_again(self):
        self.sweep(range(1000, 1070))
        self.calls.clear()
        self.sweep([5000, 5000])
        self.assertEqual(len(self.calls), 2, "inside the pause a refusal is not remembered")
        bot._ha_forbidden_outage["until"] = time.time() - 1
        self.calls.clear()
        self.sweep([5000, 5000])
        self.assertEqual(len(self.calls), 1, "after the pause the memory works again")

    def test_an_expired_refusal_does_not_count_toward_the_cap(self):
        stale = time.time() - bot.HOSTAWAY_FORBIDDEN_TTL_S - 1
        bot._ha_forbidden.update({str(i): stale for i in range(100)})
        self.sweep([1])
        self.assertEqual(bot._ha_forbidden_outage["trips"], 0)

    def test_the_outage_shows_on_the_health_page(self):
        self.sweep(range(1000, 1070))
        self.assertEqual(bot.thread_health()["hostaway_refused_outage"]["trips"], 1)
