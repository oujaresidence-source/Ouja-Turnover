# -*- coding: utf-8 -*-
"""Discord must keep answering when the shared worker pool is jammed.

2026-11-06: /deletethischannel said "The application did not respond" and every button died,
while the website stayed fine. The event loop was never frozen. The default thread pool
(asyncio.to_thread) was 32/32 busy with 120+ jobs queued, nearly all of them dashboard
requests for /api/home/urgent waiting on the Hostaway throttle — and aiohttp's address
lookup for Discord uses that SAME pool. So every new Discord connection queued behind
Hostaway work: replies landed after Discord's 3-second limit («Unknown interaction») and
gateway reconnects died at 60s inside _resolve_host.

These lock the five repairs:
  1. Discord has its own address-lookup lane, so a jam cannot reach it.
  2. Only one forward-calendar refresh runs at a time.
  3. The two home feeds run one job at a time and share the answer for 30s.
  4. A reconnect no longer reloads the saved files over live memory.
  5. A long shared-pool queue is reported in the log, never restarted.
Synthetic, no network.
Run: python3 -m unittest tests.test_discord_pool_isolation
"""
import asyncio
import json
import re
import socket
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import aiohttp
import discord
from aiohttp import web
from aiohttp.test_utils import TestServer

import bot

ROOT = Path(__file__).resolve().parents[1]
BOT_SRC = (ROOT / "bot.py").read_text(encoding="utf-8")

ME = {"id": "1", "username": "ouja", "discriminator": "0", "avatar": None, "bot": True}


def _users_me_app():
    async def me(_request):
        return web.Response(body=json.dumps(ME).encode(), content_type="application/json")
    app = web.Application()
    app.router.add_get("/api/v10/users/@me", me)
    return app


class _JammedPool:
    """The incident in miniature: every worker of the loop's default pool is busy."""

    def __init__(self, loop, workers=2):
        self.release = threading.Event()
        self.pool = ThreadPoolExecutor(max_workers=workers)
        loop.set_default_executor(self.pool)
        self.jobs = [loop.run_in_executor(None, self.release.wait) for _ in range(workers + 3)]

    async def clear(self):
        self.release.set()
        await asyncio.gather(*self.jobs)


class ResolverLane(unittest.TestCase):
    def test_control_a_jammed_pool_really_blocks_the_stock_lookup(self):
        """Without this, the test below could pass for a boring reason."""
        async def go():
            jam = _JammedPool(asyncio.get_running_loop())
            server = TestServer(_users_me_app(), host="127.0.0.1")
            await server.start_server()
            connector = aiohttp.TCPConnector(limit=0, force_close=True)
            try:
                async with aiohttp.ClientSession(connector=connector) as s:
                    with self.assertRaises(asyncio.TimeoutError):
                        await asyncio.wait_for(
                            s.get("http://localhost:%d/api/v10/users/@me" % server.port), 1.0)
            finally:
                await jam.clear()
                await server.close()
        asyncio.run(go())

    def test_lookup_finishes_while_the_shared_pool_is_jammed(self):
        async def go():
            jam = _JammedPool(asyncio.get_running_loop())
            server = TestServer(_users_me_app(), host="127.0.0.1")
            await server.start_server()
            try:
                async with aiohttp.ClientSession(connector=bot._discord_connector()) as s:
                    r = await asyncio.wait_for(
                        s.get("http://localhost:%d/api/v10/users/@me" % server.port), 2.0)
                    self.assertEqual(r.status, 200)
                    self.assertEqual((await r.json())["username"], "ouja")
            finally:
                await jam.clear()
                await server.close()
        asyncio.run(go())

    def test_resolver_returns_the_shape_aiohttp_expects(self):
        async def go():
            return await bot._DiscordResolver().resolve("localhost", 443, socket.AF_INET)
        rows = asyncio.run(go())
        self.assertTrue(rows)
        self.assertEqual(rows[0]["hostname"], "localhost")
        self.assertEqual(rows[0]["host"], "127.0.0.1")
        self.assertEqual(rows[0]["port"], 443)
        self.assertEqual(rows[0]["family"], socket.AF_INET)
        self.assertEqual(rows[0]["flags"], socket.AI_NUMERICHOST | socket.AI_NUMERICSERV)

    def test_a_real_dns_failure_is_reported_not_hidden(self):
        async def go():
            with mock.patch("socket.getaddrinfo", side_effect=socket.gaierror(-2, "no name")):
                await bot._DiscordResolver().resolve("discord.com", 443)
        with self.assertRaises(OSError):
            asyncio.run(go())

    def test_a_broken_lane_falls_back_to_the_stock_lookup(self):
        async def go():
            with mock.patch("asyncio.BaseEventLoop.run_in_executor",
                            side_effect=RuntimeError("lane down")):
                with mock.patch("aiohttp.ThreadedResolver.resolve",
                                new=mock.AsyncMock(return_value=[{"host": "1.2.3.4"}])) as stock:
                    out = await bot._DiscordResolver().resolve("discord.com", 443)
                    stock.assert_awaited_once()
                    return out
        self.assertEqual(asyncio.run(go()), [{"host": "1.2.3.4"}])

    def test_addresses_are_remembered_for_five_minutes_not_ten_seconds(self):
        async def go():
            connector = bot._discord_connector()
            try:
                self.assertEqual(connector.limit, 0)     # discord.py's own default: no cap
                self.assertIsInstance(connector._resolver, bot._DiscordResolver)
                self.assertTrue(connector.use_dns_cache)
                self.assertEqual(connector._cached_hosts._ttl, 300)
            finally:
                await connector.close()
        asyncio.run(go())


class BotLogin(unittest.TestCase):
    """The real discord.py login path, pointed at a local stand-in for Discord."""

    def _login(self, jam=False):
        seen = {}

        async def go():
            server = TestServer(_users_me_app(), host="127.0.0.1")
            await server.start_server()
            base = "http://localhost:%d/api/v10" % server.port
            client = bot.OujaBot(command_prefix="!t ", intents=discord.Intents.none(),
                                 application_id=1)
            client.application_info = mock.AsyncMock(return_value=mock.Mock(id=1))
            blocker = _JammedPool(asyncio.get_running_loop()) if jam else None
            try:
                with mock.patch.object(discord.http.Route, "BASE", base):
                    async with client:
                        await asyncio.wait_for(client.login("fake-token"), 3.0)
                        seen["resolver"] = client.http.connector._resolver
                        seen["user"] = client.user.name
            finally:
                if blocker:
                    await blocker.clear()
                await server.close()
        asyncio.run(go())
        return seen

    def test_login_uses_the_private_lane(self):
        seen = self._login()
        self.assertIsInstance(seen["resolver"], bot._DiscordResolver)
        self.assertEqual(seen["user"], "ouja")

    def test_login_works_during_a_jam(self):
        self.assertEqual(self._login(jam=True)["user"], "ouja")

    def test_if_the_lane_cannot_be_built_discord_still_logs_in(self):
        with mock.patch.object(bot, "_discord_connector", side_effect=RuntimeError("boom")):
            seen = self._login()
        self.assertNotIsInstance(seen["resolver"], bot._DiscordResolver)
        self.assertEqual(seen["user"], "ouja")

    def test_the_real_bot_is_built_from_the_subclass(self):
        self.assertIsInstance(bot.bot, bot.OujaBot)


class ForwardCalendarOneRefresh(unittest.TestCase):
    ROWS = [{"date": "d%d" % i} for i in range(60)]

    def setUp(self):
        saved = dict(bot._forward_cache)
        self.addCleanup(lambda: bot._forward_cache.update(saved))
        bot._forward_cache.update(data=None, ts=0)

    def _crowd(self, n, days=45):
        out, errs = [], []

        def call():
            try:
                out.append(bot.get_forward_calendar(days=days))
            except Exception as e:
                errs.append(e)
        threads = [threading.Thread(target=call) for _ in range(n)]
        for t in threads:
            t.start()
        return threads, out, errs

    def test_stale_numbers_answer_at_once_while_one_refresh_runs(self):
        bot._forward_cache.update(data=[{"date": "old"}] * 60, ts=time.time() - 5000)
        go = threading.Event()
        calls = []

        def slow(days=60):
            calls.append(days)
            go.wait(5)
            return self.ROWS
        with mock.patch.object(bot, "compute_forward_calendar", side_effect=slow):
            threads, out, errs = self._crowd(20)
            deadline = time.time() + 2
            while len(out) < 19 and time.time() < deadline:
                time.sleep(0.01)
            self.assertEqual(len(out), 19, "19 callers must get the old numbers without waiting")
            self.assertTrue(all(r[0]["date"] == "old" for r in out))
            go.set()
            for t in threads:
                t.join(5)
        self.assertEqual(calls, [60])
        self.assertEqual(errs, [])
        self.assertEqual(bot._forward_cache["data"], self.ROWS)

    def test_cold_cache_one_refresh_and_everyone_gets_it(self):
        calls = []

        def slow(days=60):
            calls.append(days)
            time.sleep(0.2)
            return self.ROWS
        with mock.patch.object(bot, "compute_forward_calendar", side_effect=slow):
            threads, out, errs = self._crowd(10)
            for t in threads:
                t.join(5)
        self.assertEqual(calls, [60])
        self.assertEqual(errs, [])
        self.assertEqual(len(out), 10)
        self.assertTrue(all(len(r) == 45 for r in out))

    def test_a_fresh_cache_never_refreshes(self):
        bot._forward_cache.update(data=self.ROWS, ts=time.time())
        with mock.patch.object(bot, "compute_forward_calendar", side_effect=AssertionError):
            self.assertEqual(len(bot.get_forward_calendar(days=30)), 30)

    def test_a_failed_refresh_lets_the_next_one_run(self):
        with mock.patch.object(bot, "compute_forward_calendar",
                               side_effect=[RuntimeError("hostaway down"), self.ROWS]):
            with self.assertRaises(RuntimeError):
                bot.get_forward_calendar()
            self.assertEqual(bot.get_forward_calendar(), self.ROWS)

    def test_a_price_change_during_a_refresh_is_not_buried_for_20_minutes(self):
        bot._forward_cache.update(data=[{"date": "old"}] * 60, ts=time.time() - 5000)

        def price_change_mid_refresh(days=60):
            bot._forward_cache["data"] = None
            bot._forward_cache["ts"] = 0
            return self.ROWS
        with mock.patch.object(bot, "compute_forward_calendar",
                               side_effect=price_change_mid_refresh):
            bot.get_forward_calendar()
        self.assertEqual(bot._forward_cache["ts"], 0, "next reader must refresh again")

    def test_a_cold_waiter_gives_up_instead_of_starting_a_second_refresh(self):
        release = threading.Event()

        def slow(days=60):
            release.wait(5)
            return self.ROWS
        with mock.patch.object(bot, "compute_forward_calendar", side_effect=slow) as compute, \
                mock.patch.object(bot, "SINGLE_FLIGHT_WAIT", 0.05):
            leader = threading.Thread(target=bot.get_forward_calendar)
            leader.start()
            deadline = time.time() + 2
            while not compute.called and time.time() < deadline:
                time.sleep(0.01)
            with self.assertRaises(TimeoutError):
                bot.get_forward_calendar()
            release.set()
            leader.join(5)
        self.assertEqual(compute.call_count, 1)


class HomeFeedOneJob(unittest.TestCase):
    def setUp(self):
        bot._home_feed_cache.clear()
        bot._home_feed_jobs.clear()
        self.addCleanup(bot._home_feed_cache.clear)
        self.addCleanup(bot._home_feed_jobs.clear)

    def test_fifty_readers_one_job(self):
        calls = []

        def fn():
            calls.append(1)
            time.sleep(0.1)
            return ["item"]

        async def go():
            return await asyncio.gather(*[bot._home_feed("k", fn) for _ in range(50)])
        self.assertEqual(asyncio.run(go()), [["item"]] * 50)
        self.assertEqual(len(calls), 1)

    def test_answer_is_reused_inside_the_window_and_redone_after_it(self):
        calls = []

        def fn():
            calls.append(1)
            return len(calls)

        async def go():
            first = await bot._home_feed("k", fn)
            again = await bot._home_feed("k", fn)
            ts, value = bot._home_feed_cache["k"]
            bot._home_feed_cache["k"] = (ts - bot.HOME_FEED_TTL_S - 1, value)
            later = await bot._home_feed("k", fn)
            return first, again, later
        self.assertEqual(asyncio.run(go()), (1, 1, 2))

    def test_different_keys_do_not_share(self):
        async def go():
            return await asyncio.gather(bot._home_feed("a", lambda: 1),
                                        bot._home_feed("b", lambda: 2))
        self.assertEqual(asyncio.run(go()), [1, 2])

    def test_a_browser_giving_up_does_not_kill_the_job_for_others(self):
        release = threading.Event()
        calls = []

        def fn():
            calls.append(1)
            release.wait(5)
            return "done"

        async def go():
            quitter = asyncio.ensure_future(bot._home_feed("k", fn))
            await asyncio.sleep(0.05)
            stayer = asyncio.ensure_future(bot._home_feed("k", fn))
            await asyncio.sleep(0.05)
            quitter.cancel()
            await asyncio.sleep(0.05)
            release.set()
            return await stayer
        self.assertEqual(asyncio.run(go()), "done")
        self.assertEqual(len(calls), 1)

    def test_a_failure_reaches_the_reader_and_is_never_remembered(self):
        results = [RuntimeError("hostaway down"), "ok"]

        def fn():
            r = results.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        async def go():
            with self.assertRaises(RuntimeError):
                await bot._home_feed("k", fn)
            self.assertNotIn("k", bot._home_feed_cache)
            self.assertNotIn("k", bot._home_feed_jobs)
            return await bot._home_feed("k", fn)
        self.assertEqual(asyncio.run(go()), "ok")

    def test_the_urgent_endpoint_uses_it_and_still_checks_the_login(self):
        request = mock.Mock()
        request.query = {}

        async def go():
            with mock.patch.object(bot, "compute_urgent_now",
                                   return_value=[{"severity": "high"}]) as compute:
                with mock.patch.object(bot, "_dash_auth", return_value=True):
                    await bot._api_home_urgent(request)
                    await bot._api_home_urgent(request)
                self.assertEqual(compute.call_count, 1)
                with mock.patch.object(bot, "_dash_auth", return_value=False):
                    denied = await bot._api_home_urgent(request)
                self.assertEqual(denied.status, 401)
        asyncio.run(go())

    def test_the_arrivals_endpoint_shares_by_window(self):
        async def go():
            with mock.patch.object(bot, "compute_arrivals_with_status",
                                   return_value=[]) as compute, \
                    mock.patch.object(bot, "_dash_auth", return_value=True):
                for hours in ("36", "36", "24"):
                    request = mock.Mock()
                    request.query = {"hours": hours}
                    await bot._api_home_arrivals(request)
                self.assertEqual(compute.call_count, 2)
        asyncio.run(go())


class ReconnectKeepsMemory(unittest.TestCase):
    def setUp(self):
        saved = getattr(bot.bot, "_state_loaded", False)
        self.addCleanup(lambda: setattr(bot.bot, "_state_loaded", saved))
        bot.bot._state_loaded = False

    def test_saved_files_load_once(self):
        with mock.patch.object(bot, "load_state") as load:
            bot._load_state_once()
            bot._load_state_once()
            bot._load_state_once()
        self.assertEqual(load.call_count, 1)

    def test_a_failed_load_is_tried_again(self):
        with mock.patch.object(bot, "load_state", side_effect=[OSError("volume"), None]) as load:
            with self.assertRaises(OSError):
                bot._load_state_once()
            bot._load_state_once()
        self.assertEqual(load.call_count, 2)

    def test_on_ready_goes_through_the_guard(self):
        body = re.search(r"^async def on_ready\(\):.*?(?=^\S)", BOT_SRC, re.M | re.S).group(0)
        self.assertIn("_load_state_once()", body)
        self.assertNotRegex(body, r"(?<![_\w])load_state\(\)")


class SharedPoolWarning(unittest.TestCase):
    def setUp(self):
        saved = dict(bot._liveness)
        self.addCleanup(lambda: (bot._liveness.clear(), bot._liveness.update(saved)))
        bot._liveness.update(pool_queued=0, pool_jam_since=None, pool_jam_warned=False)

    def test_a_short_spike_is_quiet(self):
        self.assertIsNone(bot._pool_jam_check(50, 1000.0))
        self.assertIsNone(bot._pool_jam_check(0, 1010.0))
        self.assertIsNone(bot._pool_jam_check(50, 1020.0))

    def test_a_lasting_queue_warns_once_then_says_when_it_clears(self):
        self.assertIsNone(bot._pool_jam_check(50, 1000.0))
        first = bot._pool_jam_check(60, 1000.0 + bot.LIVENESS_POOL_WARN_S)
        self.assertIn("60", first)
        self.assertIsNone(bot._pool_jam_check(70, 1100.0 + bot.LIVENESS_POOL_WARN_S))
        self.assertIn("cleared", bot._pool_jam_check(0, 1200.0 + bot.LIVENESS_POOL_WARN_S))
        self.assertIsNone(bot._pool_jam_check(0, 1300.0 + bot.LIVENESS_POOL_WARN_S))

    def test_an_unknown_queue_is_ignored(self):
        self.assertIsNone(bot._pool_jam_check(None, 1000.0))
        self.assertEqual(bot._liveness["pool_queued"], 0)

    def test_the_health_page_shows_the_number(self):
        bot._pool_jam_check(7, 1000.0)
        self.assertEqual(bot.thread_health()["liveness"]["pool_queued"], 7)

    def test_a_jam_can_never_trigger_a_restart(self):
        """The warning stays outside the verdict that decides restarts."""
        verdict = re.search(r"^def _liveness_verdict\(.*?(?=^def )", BOT_SRC, re.M | re.S).group(0)
        self.assertNotIn("pool", verdict)
        with mock.patch.object(bot, "_liveness_restart", side_effect=AssertionError):
            bot._pool_jam_check(500, 1000.0)
            bot._pool_jam_check(500, 2000.0)


if __name__ == "__main__":
    unittest.main()
