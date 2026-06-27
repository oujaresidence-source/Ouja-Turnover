# -*- coding: utf-8 -*-
"""Synthetic-data logic tests for the Conversation Watchman «الرقيب».

These never touch the network or Discord: api_get / claude_json / guide-page fetch are
stubbed, and a fake quiet conversation is fed through run_watchman_scan(). They lock the
behaviors the owner depends on:
  - dry-run analyzes + marks seen but creates NO ticket records (so going live works);
  - live mode opens a guide-gap + a promise ticket from the AI result;
  - a known responder name maps to a Discord mention; an unknown one stays unassigned;
  - low-confidence findings are dropped (pleasantry guard);
  - sender detection + mention rendering + the name-map parser.
"""
import tempfile
import unittest

import bot


# a conversation whose last message is far in the past -> always "quiet"
_OLD = "2020-01-01 00:00:00"
_MSGS = [
    {"id": 1, "isIncoming": 1, "body": "وين أركن السيارة؟", "date": _OLD},
    {"id": 2, "isIncoming": 0, "body": "اركن بقبو B2 الموقف رقم 14. وبرسل لك فني للمكيف بكرة الساعة 5.",
     "date": _OLD, "userName": "Ahmed"},
]


def _fake_api_get(path, params=None):
    if path == "/conversations":
        return {"result": [{"id": 555, "listingMapId": 101,
                            "recipientName": "Mohammed", "reservation": {}}]}
    if str(path).endswith("/messages"):
        return {"result": list(_MSGS)}
    return {}


def _fake_result(*a, **k):
    return {
        "guide_gaps": [{
            "topic": "موقف السيارة",
            "guest_question": "وين أركن؟",
            "our_answer": "قبو B2 موقف 14",
            "suggested_guide_text": "السيارة تُركن في قبو B2، الموقف رقم 14.",
            "used_fallback": False, "confidence": 0.9,
        }],
        "promises": [{
            "type": "action", "summary": "إرسال فني للمكيف بكرة الساعة 5",
            "quote": "برسل لك فني للمكيف بكرة الساعة 5", "responder": "Ahmed",
            "due_hint": "tomorrow 5pm", "confidence": 0.9,
        }],
    }


class WatchmanScan(unittest.TestCase):
    def setUp(self):
        # isolate state to a temp dir + reset in-memory stores
        self._tmp = tempfile.mkdtemp()
        self._saved = {k: getattr(bot, k) for k in (
            "STATE_DIR", "api_get", "claude_json", "get_listings_map", "_wm_guide_text",
            "WATCHMAN_ENABLED", "WATCHMAN_DRYRUN", "WATCHMAN_NAME_MAP", "_wm_meta", "_wm_namemap")}
        bot.STATE_DIR = self._tmp
        bot.api_get = _fake_api_get
        bot.claude_json = _fake_result
        bot.get_listings_map = lambda: {101: "Ouja | Turaif"}
        bot._wm_guide_text = lambda lid: "wifi: OUJA1234. تسجيل الخروج 11 صباحاً."  # no parking, no AC
        bot.WATCHMAN_ENABLED = True
        bot.WATCHMAN_NAME_MAP = {"ahmed": "111222333"}
        bot._wm_seen, bot._wm_gaps, bot._wm_promises, bot._wm_msg2promise = {}, {}, {}, {}
        bot._wm_namemap = {}
        bot._wm_meta = {"baselined": True}      # skip the first-live-run baseline in most tests
        bot._wm_diag_logged = {"v": True}

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(bot, k, v)

    def test_dryrun_creates_no_records_but_marks_seen(self):
        bot.WATCHMAN_DRYRUN = True
        intents = bot.run_watchman_scan()
        kinds = sorted({k for k, _ in intents})
        self.assertEqual(kinds, ["dry_gap", "dry_promise"])
        # nothing persisted as a real ticket — so flipping live later still posts fresh
        self.assertEqual(bot._wm_gaps, {})
        self.assertEqual(bot._wm_promises, {})
        # but the conversation is marked analyzed (no token re-spend)
        self.assertEqual(bot._wm_seen.get("555"), _OLD)

    def test_live_opens_gap_and_promise_with_attribution(self):
        bot.WATCHMAN_DRYRUN = False
        intents = bot.run_watchman_scan()
        kinds = sorted(k for k, _ in intents)
        self.assertIn("gap_new", kinds)
        self.assertIn("promise_new", kinds)
        # gap record stored + carries the suggested guide text
        self.assertEqual(len(bot._wm_gaps), 1)
        gap = next(iter(bot._wm_gaps.values()))
        self.assertEqual(gap["apartment"], "Ouja | Turaif")
        self.assertIn("B2", gap["suggested"])
        # promise record stored + attributed to Ahmed's Discord id
        self.assertEqual(len(bot._wm_promises), 1)
        pr = next(iter(bot._wm_promises.values()))
        self.assertEqual(pr["type"], "action")
        self.assertEqual(pr["discord_id"], "111222333")
        self.assertEqual(pr["state"], "open")

    def test_first_live_run_baselines_without_posting(self):
        # going live with a fresh (never-baselined) store must NOT dump backlog tickets:
        # it marks the existing conversations seen and opens nothing this tick.
        bot.WATCHMAN_DRYRUN = False
        bot._wm_meta = {}
        intents = bot.run_watchman_scan()
        self.assertEqual(intents, [])
        self.assertEqual(bot._wm_gaps, {})
        self.assertEqual(bot._wm_promises, {})
        self.assertEqual(bot._wm_seen.get("555"), _OLD)     # backlog marked seen
        self.assertTrue(bot._wm_meta.get("baselined"))

    def test_unknown_responder_stays_unassigned(self):
        bot.WATCHMAN_DRYRUN = False
        bot.WATCHMAN_NAME_MAP = {}                       # Ahmed no longer mapped
        bot.run_watchman_scan()
        pr = next(iter(bot._wm_promises.values()))
        self.assertEqual(pr["discord_id"], "")           # -> unassigned managers path

    def test_admin_namemap_wins_over_env(self):
        bot.WATCHMAN_DRYRUN = False
        bot.WATCHMAN_NAME_MAP = {"ahmed": "111"}         # env says 111
        bot._wm_namemap = {"ahmed": "999"}               # admin-assigned says 999
        bot.run_watchman_scan()
        pr = next(iter(bot._wm_promises.values()))
        self.assertEqual(pr["discord_id"], "999")        # admin channel wins

    def test_responder_name_recorded_for_admin_mapping(self):
        bot.WATCHMAN_DRYRUN = False
        bot.run_watchman_scan()
        self.assertIn("Ahmed", bot._wm_meta.get("names", []))   # surfaces in «مطابقة-الأسماء»

    def test_low_confidence_is_dropped(self):
        bot.WATCHMAN_DRYRUN = False
        bot.claude_json = lambda *a, **k: {
            "guide_gaps": [{"topic": "x", "confidence": 0.2}],
            "promises": [{"type": "action", "summary": "y", "confidence": 0.1}],
        }
        intents = bot.run_watchman_scan()
        self.assertEqual(intents, [])
        self.assertEqual(bot._wm_gaps, {})
        self.assertEqual(bot._wm_promises, {})


class WatchmanHelpers(unittest.TestCase):
    def test_sender_name_detection(self):
        self.assertEqual(bot._wm_sender_name({"userName": "Sara"}), "Sara")
        self.assertEqual(bot._wm_sender_name(
            {"user": {"firstName": "Abu", "lastName": "Fahad"}}), "Abu Fahad")
        self.assertEqual(bot._wm_sender_name({"body": "hi"}), "")   # Airbnb-app: no sender

    def test_mention_rendering(self):
        self.assertEqual(bot._wm_mention("123"), "<@123>")
        self.assertEqual(bot._wm_mention("role:999"), "<@&999>")
        self.assertEqual(bot._wm_mention("<@123>"), "<@123>")
        self.assertEqual(bot._wm_mention(""), "")

    def test_resolve_id_priority(self):
        saved = (bot._wm_namemap, bot.WATCHMAN_NAME_MAP)
        try:
            bot._wm_namemap = {"noura": "777"}
            bot.WATCHMAN_NAME_MAP = {"noura": "111", "nasser": "222"}
            self.assertEqual(bot._wm_resolve_id("Noura"), "777")   # admin map wins
            self.assertEqual(bot._wm_resolve_id("nasser"), "222")  # falls back to env
            self.assertEqual(bot._wm_resolve_id("ghost"), "")      # neither
            self.assertEqual(bot._wm_resolve_id(""), "")
        finally:
            bot._wm_namemap, bot.WATCHMAN_NAME_MAP = saved

    def test_known_names_seed(self):
        saved = (bot.WATCHMAN_KNOWN_NAMES, bot._wm_meta)
        try:
            bot.WATCHMAN_KNOWN_NAMES = "Ohoud,nasser,Noura,Aseel,Mohammed,Maather"
            bot._wm_meta = {"names": ["Khalid", "nasser"]}   # discovered; nasser dupes the seed
            names = bot._wm_known_names()
            self.assertIn("Ohoud", names)
            self.assertIn("Khalid", names)                  # discovered names included
            self.assertEqual(sum(1 for n in names if n.lower() == "nasser"), 1)  # de-duped
        finally:
            bot.WATCHMAN_KNOWN_NAMES, bot._wm_meta = saved

    def test_name_map_parses_and_lowercases(self):
        import os
        old = os.environ.get("WATCHMAN_NAME_MAP")
        os.environ["WATCHMAN_NAME_MAP"] = '{"Ahmed":"111","Sara":"role:222"}'
        try:
            m = bot._wm_name_map()
            self.assertEqual(m["ahmed"], "111")
            self.assertEqual(m["sara"], "role:222")
        finally:
            if old is None:
                os.environ.pop("WATCHMAN_NAME_MAP", None)
            else:
                os.environ["WATCHMAN_NAME_MAP"] = old


if __name__ == "__main__":
    unittest.main()
