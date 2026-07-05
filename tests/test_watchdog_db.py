# -*- coding: utf-8 -*-
"""watchdog.db — code-mode registry, code-send log (idempotent), ping dedup, stats, fingerprints."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from watchdog import db as wdb


class TestWatchdogDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="wdtest_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        wdb.reset_init_cache()

    def test_code_mode_default_auto(self):
        self.assertEqual(wdb.code_mode("999111"), "auto")

    def test_code_mode_set_and_list(self):
        wdb.set_code_mode("777", "manual", by="faisal")
        self.assertEqual(wdb.code_mode("777"), "manual")
        self.assertIn("777", wdb.manual_listing_ids())
        wdb.set_code_mode("777", "auto", by="faisal")
        self.assertNotIn("777", wdb.manual_listing_ids())

    def test_code_send_log_idempotent(self):
        rec = {"listing_id": "1", "reservation_id": "r1", "guest_name": "g",
               "sent_by": "نورة", "sent_at": "2026-07-05T10:00:00",
               "arrival_ts": "2026-07-05T15:00:00", "on_time": 1}
        wdb.log_code_send(rec)
        wdb.log_code_send(rec)
        rows = wdb.code_sends_since("2026-06-28")
        rows = [r for r in rows if r["reservation_id"] == "r1"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sent_by"], "نورة")

    def test_flag_state_ping_once_then_reping_window(self):
        key = "code:1:2026-07-05"
        self.assertTrue(wdb.claim_ping(key, "2026-07-05T10:00:00"))
        self.assertFalse(wdb.claim_ping(key, "2026-07-05T10:05:00"))
        # not due yet at +1h with a 2h window
        self.assertFalse(wdb.reping_due(key, "2026-07-05T11:00:00", 2.0))
        # due at +3h; claims the ping again exactly once
        self.assertTrue(wdb.reping_due(key, "2026-07-05T13:00:00", 2.0))
        self.assertFalse(wdb.reping_due(key, "2026-07-05T13:05:00", 2.0))
        wdb.resolve_flag(key, "2026-07-05T14:00:00")
        self.assertIsNotNone(wdb.flag_get(key)["resolved_at"])

    def test_stats_upsert_and_query(self):
        wdb.bump_stat("2026-07-05", "نورة", resp_min=10.0)
        wdb.bump_stat("2026-07-05", "نورة", resp_min=20.0)
        wdb.bump_stat("2026-07-05", "أسيل", automated=True)
        rows = {r["employee"]: r for r in wdb.stats_since("2026-07-01")}
        self.assertEqual(rows["نورة"]["replies"], 2)
        self.assertEqual(rows["نورة"]["resp_min_sum"], 30.0)
        self.assertEqual(rows["أسيل"]["replies"], 0)
        self.assertEqual(rows["أسيل"]["automations_skipped"], 1)

    def test_fp_accumulate_distinct(self):
        for c in ("c1", "c2", "c2", "c3"):
            wdb.fp_bump("abc", conv=c, minute=660)
        rec = wdb.fp_get("abc")
        self.assertEqual(rec["n"], 4)
        self.assertEqual(sorted(rec["convs"]), ["c1", "c2", "c3"])
        self.assertEqual(rec["minutes"].count(660), 4)

    def test_events_log(self):
        wdb.log_event("2026-07-05", "esc_claim", "أسيل")
        wdb.log_event("2026-07-05", "esc_claim", "أسيل")
        rows = wdb.events_since("2026-07-01", "esc_claim")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["employee"], "أسيل")

    def test_seen_msgs(self):
        self.assertFalse(wdb.msg_seen("cv1", "m1"))
        wdb.mark_msg_seen("cv1", "m1")
        self.assertTrue(wdb.msg_seen("cv1", "m1"))


if __name__ == "__main__":
    unittest.main()
