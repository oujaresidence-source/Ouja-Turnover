# -*- coding: utf-8 -*-
"""Guards for the Hostaway rate-limit fixes.

The bot was issuing ~108 Hostaway calls/minute at idle against a documented ceiling
of 15 req/10s per IP. Over-budget calls come back 429, and _api_request answers a 429
by SLEEPING (5s -> 10s -> 20s) on a thread borrowed from the shared to_thread pool.
Once ~32 threads are parked in backoff every other to_thread in the app queues behind
them — including the dashboard's own page loads. These tests lock the four mechanisms
that keep that from happening:

  1. a sliding-window token bucket in front of every call,
  2. one pooled requests.Session (no TLS handshake per call),
  3. the 429 backoff still working, and counted,
  4. _save_json not touching disk when nothing changed,
  5. _conv_to_item not re-fetching messages that already arrived inline.
"""
import os
import sys
import time as _real_time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HOSTAWAY_ACCOUNT_ID", "147296")
os.environ.setdefault("HOSTAWAY_API_KEY", "test")
os.environ.setdefault("DISCORD_TOKEN", "test")
os.environ.setdefault("DISCORD_GUILD_ID", "1")

import requests

import bot


class _FakeClock:
    """Stand-in for the `time` module: sleeping just moves the clock forward, so a
    test of a 10-second window runs in microseconds instead of 10 seconds."""

    def __init__(self, start=1_000_000.0):
        self.t = start
        self.slept = []

    def time(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds

    def __getattr__(self, name):          # anything else falls through to the real module
        return getattr(_real_time, name)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"result": []}
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")


class ThrottleWindowTest(unittest.TestCase):
    """The bucket must never let more than HOSTAWAY_MAX_PER_10S calls sit in one
    10-second window, and must actually block (not drop) the overflow.

    These exercise the USER lane, i.e. the real Hostaway ceiling. Background
    callers are deliberately held below it — that reserve is covered in
    tests/test_hostaway_priority_lane.py."""

    def setUp(self):
        bot._ha_bucket_times.clear()

    tearDown = setUp

    def test_overflow_waits_and_window_is_never_exceeded(self):
        clock = _FakeClock()
        cap = 3
        with mock.patch.object(bot, "time", clock), \
             mock.patch.object(bot, "HOSTAWAY_MAX_PER_10S", cap):
            for _ in range(cap + 3):
                bot._ha_throttle_acquire(priority="user")
                # checked after EVERY acquire, not just at the end
                self.assertLessEqual(len(bot._ha_bucket_times), cap)
        self.assertGreaterEqual(len(clock.slept), 1,
                                "going over the cap must block, not sail through")

    def test_under_the_cap_never_sleeps(self):
        clock = _FakeClock()
        with mock.patch.object(bot, "time", clock), \
             mock.patch.object(bot, "HOSTAWAY_MAX_PER_10S", 5):
            for _ in range(5):
                bot._ha_throttle_acquire(priority="user")
        self.assertEqual(clock.slept, [], "a call under budget must not be delayed")

    def test_window_slides_so_old_calls_stop_counting(self):
        clock = _FakeClock()
        with mock.patch.object(bot, "time", clock), \
             mock.patch.object(bot, "HOSTAWAY_MAX_PER_10S", 2):
            bot._ha_throttle_acquire(priority="user")
            bot._ha_throttle_acquire(priority="user")
            clock.t += 11.0                      # both are now outside the window
            bot._ha_throttle_acquire(priority="user")
        self.assertEqual(clock.slept, [], "expired timestamps must be evicted, not counted")
        self.assertEqual(len(bot._ha_bucket_times), 1)


class PooledSessionTest(unittest.TestCase):
    """Every Hostaway call must go through the ONE keep-alive session. requests.request()
    opened a fresh TLS connection per call — 100-300ms of pure handshake, 100+ times/min."""

    def setUp(self):
        bot._ha_bucket_times.clear()

    tearDown = setUp

    def test_module_holds_a_single_session(self):
        self.assertIsInstance(bot._ha_session, requests.Session)
        self.assertIs(bot._ha_session, bot._ha_session)
        adapter = bot._ha_session.get_adapter("https://api.hostaway.com/v1/listings")
        self.assertIsInstance(adapter, requests.adapters.HTTPAdapter)

    def test_api_request_uses_the_session_not_requests_request(self):
        fake = mock.Mock(return_value=_FakeResponse(200, {"result": [{"id": 7}]}))
        with mock.patch.object(bot, "get_token", return_value="tok"), \
             mock.patch.object(bot._ha_session, "request", fake), \
             mock.patch.object(requests, "request",
                               side_effect=AssertionError("bypassed the pooled session")):
            out = bot.api_get("/listings", params={"limit": 1})
        self.assertEqual(out, {"result": [{"id": 7}]})
        self.assertEqual(fake.call_count, 1)
        args, kwargs = fake.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], "https://api.hostaway.com/v1/listings")
        self.assertEqual(kwargs["params"], {"limit": 1})

    def test_every_call_passes_through_the_throttle(self):
        seen = []
        with mock.patch.object(bot, "get_token", return_value="tok"), \
             mock.patch.object(bot, "_ha_throttle_acquire", lambda: seen.append(1)), \
             mock.patch.object(bot._ha_session, "request",
                               return_value=_FakeResponse(200, {"result": []})):
            bot.api_get("/listings")
            bot.api_post("/x", {"a": 1})
            bot.api_put("/y", {"b": 2})
        self.assertEqual(len(seen), 3, "GET, POST and PUT must all be throttled")


class RateLimitRetryTest(unittest.TestCase):
    """The throttle makes 429s rare; it must not make the 429 handling disappear."""

    def setUp(self):
        bot._ha_bucket_times.clear()
        self._before = dict(bot._ha_throttle_stats)

    def tearDown(self):
        bot._ha_bucket_times.clear()
        bot._ha_throttle_stats.update(self._before)

    def test_429_twice_then_success(self):
        clock = _FakeClock()
        responses = [_FakeResponse(429), _FakeResponse(429),
                     _FakeResponse(200, {"result": "ok"})]
        fake = mock.Mock(side_effect=responses)
        before = bot._ha_throttle_stats["429s"]
        with mock.patch.object(bot, "time", clock), \
             mock.patch.object(bot, "get_token", return_value="tok"), \
             mock.patch.object(bot._ha_session, "request", fake):
            out = bot.api_get("/listings")
        self.assertEqual(out, {"result": "ok"})
        self.assertEqual(fake.call_count, 3)
        self.assertEqual(bot._ha_throttle_stats["429s"] - before, 2)
        self.assertEqual(clock.slept, [5, 10], "backoff must stay exponential")

    def test_retry_after_header_is_honoured(self):
        clock = _FakeClock()
        fake = mock.Mock(side_effect=[_FakeResponse(429, headers={"Retry-After": "2"}),
                                      _FakeResponse(200, {"result": "ok"})])
        with mock.patch.object(bot, "time", clock), \
             mock.patch.object(bot, "get_token", return_value="tok"), \
             mock.patch.object(bot._ha_session, "request", fake):
            bot.api_get("/listings")
        self.assertEqual(clock.slept, [2.0])

    def test_backoff_does_not_hold_an_inflight_slot(self):
        """A thread sleeping off a 429 must have RELEASED its in-flight permit — otherwise
        the few permits fill with sleepers and healthy calls queue behind them."""
        clock = _FakeClock()
        free_during_sleep = []

        def _watch(seconds):
            # semaphore is un-acquired => we can take and give back all permits
            got = [bot._ha_inflight.acquire(blocking=False)
                   for _ in range(bot.HOSTAWAY_MAX_INFLIGHT)]
            for ok in got:
                if ok:
                    bot._ha_inflight.release()
            free_during_sleep.append(all(got))
            clock.t += seconds

        clock.sleep = _watch
        fake = mock.Mock(side_effect=[_FakeResponse(429), _FakeResponse(200, {"r": 1})])
        with mock.patch.object(bot, "time", clock), \
             mock.patch.object(bot, "get_token", return_value="tok"), \
             mock.patch.object(bot._ha_session, "request", fake):
            bot.api_get("/listings")
        self.assertEqual(free_during_sleep, [True])


class SaveJsonSkipTest(unittest.TestCase):
    """persist_state rewrites 55 JSON files every 60 seconds on a network volume.
    An unchanged file must cost zero disk I/O — but a CHANGED one must still be written."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self._patch = mock.patch.object(bot, "STATE_DIR", self.tmp)
        self._patch.start()
        bot._save_hashes.clear()

    def tearDown(self):
        self._patch.stop()
        bot._save_hashes.clear()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_identical_second_write_touches_nothing(self):
        payload = {"a": 1, "b": ["x", "y"], "ar": "مرحبا"}
        self.assertTrue(bot._save_json("t.json", payload))
        path = os.path.join(self.tmp, "t.json")
        mtime = os.stat(path).st_mtime_ns

        # A sentinel nobody would write: if _save_json really skipped, it survives.
        with open(path, "w", encoding="utf-8") as f:
            f.write("SENTINEL")
        os.utime(path, ns=(mtime, mtime))

        self.assertTrue(bot._save_json("t.json", payload))
        self.assertEqual(os.stat(path).st_mtime_ns, mtime, "unchanged file was rewritten")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "SENTINEL")

    def test_changed_content_is_still_written(self):
        import json
        self.assertTrue(bot._save_json("t.json", {"a": 1}))
        self.assertTrue(bot._save_json("t.json", {"a": 2}))
        with open(os.path.join(self.tmp, "t.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"a": 2})

    def test_content_round_trips_and_arabic_is_not_escaped(self):
        import json
        bot._save_json("ar.json", {"unit": "Ouja | الملقا"})
        with open(os.path.join(self.tmp, "ar.json"), encoding="utf-8") as f:
            raw = f.read()
        self.assertIn("الملقا", raw, "ensure_ascii=False must be preserved")
        self.assertEqual(json.loads(raw), {"unit": "Ouja | الملقا"})

    def test_a_failed_write_clears_the_hash_so_the_next_try_is_real(self):
        path = os.path.join(self.tmp, "t.json")
        bot._save_json("t.json", {"a": 1})
        self.assertIn(path, bot._save_hashes)
        with mock.patch.object(bot.os, "replace", side_effect=OSError("disk full")):
            self.assertFalse(bot._save_json("t.json", {"a": 9}))
        self.assertNotIn(path, bot._save_hashes,
                         "a failed write must not be remembered as successful")

    def test_a_missing_file_is_rewritten_even_when_the_content_matches(self):
        """The cache says "already written"; the disk says otherwise. The disk wins —
        otherwise a wiped volume (or a changed STATE_DIR) never gets its state back."""
        payload = {"a": 1}
        self.assertTrue(bot._save_json("t.json", payload))
        os.remove(os.path.join(self.tmp, "t.json"))
        self.assertTrue(bot._save_json("t.json", payload))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "t.json")))

    def test_the_cache_is_per_directory_not_per_filename(self):
        import tempfile, shutil, json
        payload = {"a": 1}
        self.assertTrue(bot._save_json("t.json", payload))
        other = tempfile.mkdtemp()
        try:
            with mock.patch.object(bot, "STATE_DIR", other):
                self.assertTrue(bot._save_json("t.json", payload))
                with open(os.path.join(other, "t.json"), encoding="utf-8") as f:
                    self.assertEqual(json.load(f), payload)
        finally:
            shutil.rmtree(other, ignore_errors=True)


class ConvToItemInlineMessagesTest(unittest.TestCase):
    """The scan asks Hostaway for includeResources=1, so messages arrive INLINE.
    Fetching /conversations/{id}/messages again was ~60 extra calls/min — 60% of all
    Hostaway traffic and the single biggest source of 429s."""

    def _convo(self, key="conversationMessages"):
        return {
            "id": 555,
            "listingMapId": 99,
            "listingName": "Ouja | Test",
            "recipientName": "Guest",
            key: [
                {"id": 1, "isIncoming": 0, "body": "Welcome!",
                 "date": "2026-08-20 09:00:00", "communicationType": "email"},
                {"id": 2, "isIncoming": 1, "body": "What is the wifi password?",
                 "date": "2026-08-20 10:00:00", "communicationType": "email"},
            ],
        }

    def test_inline_messages_cost_zero_api_calls(self):
        calls = []

        def _no_calls(*a, **k):
            calls.append((a, k))
            raise RuntimeError("no Hostaway call may happen here")

        # patched at _api_request so a nested call inside a swallowed try/except is
        # still COUNTED rather than silently absorbed
        with mock.patch.object(bot, "_api_request", _no_calls):
            item = bot._conv_to_item(self._convo(), {99: "Ouja | Test"}, set())
        self.assertEqual(calls, [], f"unexpected Hostaway call(s): {calls}")
        self.assertIsNotNone(item)
        self.assertEqual(item["conversation_id"], 555)
        self.assertEqual(item["message_id"], "2")
        self.assertEqual(item["guest_text"], "What is the wifi password?")

    def test_messages_key_variant_also_works(self):
        with mock.patch.object(bot, "_api_request",
                               side_effect=AssertionError("should not fetch")):
            item = bot._conv_to_item(self._convo("messages"), {99: "Ouja | Test"}, set())
        self.assertIsNotNone(item)
        self.assertEqual(item["message_id"], "2")

    def test_falls_back_to_the_api_when_messages_are_genuinely_absent(self):
        fetched = []

        def _fake_get(path, params=None, _retry=0):
            fetched.append(path)
            return {"result": [{"id": 3, "isIncoming": 1, "body": "hi",
                                "date": "2026-08-20 10:00:00"}]}

        c = {"id": 777, "listingMapId": 99, "recipientName": "G"}
        with mock.patch.object(bot, "api_get", _fake_get):
            item = bot._conv_to_item(c, {99: "Ouja | Test"}, set())
        self.assertEqual(fetched, ["/conversations/777/messages"])
        self.assertIsNotNone(item)


class PollBudgetTest(unittest.TestCase):
    """The whole point of the change: idle Hostaway traffic must fit inside the limit."""

    def test_assistant_idle_call_rate_is_inside_the_ip_ceiling(self):
        # one /conversations call per poll now that messages come inline
        calls_per_min = 1.0 / bot.ASSISTANT_POLL_MIN
        self.assertLessEqual(calls_per_min, 1.0,
                             "assistant poll must not exceed 1 Hostaway call/min at idle")
        self.assertLessEqual(bot.ASSISTANT_SCAN, 20)

    def test_fanout_fits_the_ten_second_window(self):
        self.assertLessEqual(bot.INTEL_PARALLEL, bot.HOSTAWAY_MAX_INFLIGHT * 2)
        self.assertLessEqual(bot.HOSTAWAY_MAX_PER_10S, 15,
                             "must stay under Hostaway's documented 15 req/10s per IP")


if __name__ == "__main__":
    unittest.main()
