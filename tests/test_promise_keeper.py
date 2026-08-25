# -*- coding: utf-8 -*-
"""Promise Keeper (متتبع الوعود) — ledger + engine contract.

Covers: db CRUD + status flips, due-hint parsing, reping cadence, 24h expiry,
leaderboard math, and the watchman→ledger mirror shape.

Run: python3 -m unittest tests.test_promise_keeper
"""
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb          # noqa: E402
from promises import db as pdb       # noqa: E402
from promises import engine          # noqa: E402

NOW = datetime.datetime(2026, 7, 2, 12, 0, 0)


class PromiseDbTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pk_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        pdb.reset_init_cache()

    def test_upsert_get_done_flow(self):
        pid = pdb.upsert({"source": "assistant", "promise_text": "بنرسل فني تكييف اليوم",
                          "promised_by": "نورة", "guest_name": "أحمد",
                          "apartment": "Ouja | 101A", "category": "maintenance",
                          "due_at": "2026-07-02T18:00:00"})
        rec = pdb.get(pid)
        self.assertEqual(rec["status"], "open")
        self.assertEqual(rec["promised_by"], "نورة")
        done = pdb.mark_done(pid, by="نورة")
        self.assertEqual(done["status"], "done")
        self.assertEqual(done["done_by"], "نورة")
        # done is terminal — expiring it must not change anything
        pdb.mark_expired(pid)
        self.assertEqual(pdb.get(pid)["status"], "done")

    def test_expire_open_only(self):
        pid = pdb.upsert({"promise_text": "x", "due_at": "2026-07-01T00:00:00"})
        pdb.mark_expired(pid)
        self.assertEqual(pdb.get(pid)["status"], "expired")

    def test_upsert_updates_existing(self):
        pid = pdb.upsert({"promise_text": "الوعد الأول"})
        pdb.upsert({"id": pid, "status": "open", "msg_id": "999", "channel_id": "888"})
        rec = pdb.get_by_msg("999")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["id"], pid)

    def test_watchman_mirror_shape(self):
        """The watchman payload fields map cleanly onto the ledger columns."""
        wm = {"id": "wm-1", "apartment": "Ouja | 202B", "guest": "سارة",
              "responder": "Ohoud", "summary": "نعوّضك بليلة مجانية",
              "quote": "we will refund one night", "type": "money",
              "due": "2026-07-03T12:00:00", "state": "open"}
        pid = pdb.upsert({"id": wm["id"], "source": "watchman",
                          "apartment": wm["apartment"], "guest_name": wm["guest"],
                          "promised_by": wm["responder"], "promise_text": wm["summary"],
                          "quote": wm["quote"], "category": wm["type"],
                          "due_at": wm["due"]})
        self.assertEqual(pid, "wm-1")
        self.assertEqual(pdb.get("wm-1")["category"], "money")

    def test_nudge_counter(self):
        pid = pdb.upsert({"promise_text": "y", "due_at": "2026-07-02T10:00:00"})
        pdb.record_nudge(pid, at="2026-07-02T14:00:00")
        rec = pdb.get(pid)
        self.assertEqual(rec["nudges"], 1)
        self.assertEqual(rec["last_nudge_at"], "2026-07-02T14:00:00")


class PromiseEngineTest(unittest.TestCase):
    def test_due_from_hint(self):
        self.assertEqual(engine.due_from_hint("we'll fix it today", NOW),
                         "2026-07-02T18:00:00")
        self.assertEqual(engine.due_from_hint("بكرة نجيبها", NOW),
                         "2026-07-03T12:00:00")
        self.assertEqual(engine.due_from_hint("at checkout", NOW),
                         "2026-07-03T00:00:00")
        self.assertEqual(engine.due_from_hint("خلال 30 دقيقة", NOW),
                         "2026-07-02T12:30:00")
        # no hint → +4h default
        self.assertEqual(engine.due_from_hint("", NOW), "2026-07-02T16:00:00")

    def test_needs_reping_cadence(self):
        rec = {"status": "open", "due_at": "2026-07-02T08:00:00", "last_nudge_at": None}
        self.assertTrue(engine.needs_reping(rec, NOW))          # overdue, never nudged
        rec["last_nudge_at"] = "2026-07-02T09:00:00"
        self.assertFalse(engine.needs_reping(rec, NOW))          # nudged 3h ago < 4h
        rec["last_nudge_at"] = "2026-07-02T07:00:00"
        self.assertTrue(engine.needs_reping(rec, NOW))           # nudged 5h ago ≥ 4h
        rec2 = {"status": "open", "due_at": "2026-07-02T20:00:00"}
        self.assertFalse(engine.needs_reping(rec2, NOW), "not due yet")
        rec3 = {"status": "done", "due_at": "2026-07-02T08:00:00"}
        self.assertFalse(engine.needs_reping(rec3, NOW), "done never repings")

    def test_is_expired_after_24h(self):
        rec = {"status": "open", "due_at": "2026-07-01T11:00:00"}   # 25h overdue
        self.assertTrue(engine.is_expired(rec, NOW))
        rec = {"status": "open", "due_at": "2026-07-01T13:00:00"}   # 23h overdue
        self.assertFalse(engine.is_expired(rec, NOW))

    def test_leaderboard(self):
        rows = [
            {"promised_by": "نورة", "status": "done"},
            {"promised_by": "نورة", "status": "done"},
            {"promised_by": "نورة", "status": "open", "due_at": "2026-07-02T08:00:00"},
            {"promised_by": "ناصر", "status": "expired"},
            {"promised_by": "ناصر", "status": "done"},
            {"promised_by": "", "status": "open", "due_at": "2026-07-03T08:00:00"},
        ]
        lb = engine.leaderboard(rows, NOW)
        by = {p["person"]: p for p in lb}
        self.assertEqual(by["نورة"]["kept"], 2)
        self.assertEqual(by["نورة"]["overdue"], 1)
        self.assertEqual(by["نورة"]["kept_rate"], 100)
        self.assertEqual(by["ناصر"]["kept_rate"], 50)
        self.assertEqual(by["غير معروف"]["open"], 1)
        self.assertEqual(by["غير معروف"]["overdue"], 0)
        self.assertEqual(lb[0]["person"], "نورة", "best keeper first")


class BotWiringTest(unittest.TestCase):
    """bot.py side: extraction parsing, send hook → ledger, watchman mirror,
    nav/i18n/view wiring (trap #2 parity)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="pk_bot_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        pdb.reset_init_cache()
        os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-pk")
        os.makedirs("/tmp/ouja-test-state-pk", exist_ok=True)
        import bot
        cls.b = bot

    def test_parse_filters_junk(self):
        b = self.b
        out = b._pk_parse({"promises": [
            {"promise_text_ar": "نرسل فني اليوم", "due_hint": "today", "category": "maintenance"},
            {"promise_text_ar": "", "promise_text_en": ""},
            "junk",
            {"promise_text_en": "weird cat", "category": "nonsense"},
        ]})
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["category"], "maintenance")
        self.assertEqual(out[1]["category"], "other", "unknown category → other")
        self.assertEqual(b._pk_parse(None), [])
        self.assertEqual(b._pk_parse({"promises": []}), [])

    def test_record_send_creates_attributed_ledger_rows(self):
        b = self.b
        orig_cj, orig_flag = b.claude_json, b.PROMISE_KEEPER_ENABLED
        b.PROMISE_KEEPER_ENABLED = 1
        b.claude_json = lambda s, u, max_tokens=900, model=None: {"promises": [
            {"promise_text_ar": "بنعوضك بليلة مجانية", "due_hint": "بكرة", "category": "refund"}]}
        try:
            item = {"conversation_id": 777, "listing_id": 5,
                    "unit": "Ouja | 101A", "guest": "أحمد"}
            pids = b._pk_record_send(item, "أبشر — بنعوضك بليلة مجانية", "نورة", "123456")
            self.assertEqual(len(pids), 1)
            rec = pdb.get(pids[0])
            self.assertEqual(rec["source"], "assistant")
            self.assertEqual(rec["promised_by"], "نورة")
            self.assertEqual(rec["promised_by_id"], "123456")
            self.assertEqual(rec["category"], "refund")
            self.assertTrue(rec["due_at"], "a due hint must resolve to a concrete due_at")
        finally:
            b.claude_json = orig_cj
            b.PROMISE_KEEPER_ENABLED = orig_flag

    def test_disabled_flag_records_nothing(self):
        b = self.b
        orig = b.PROMISE_KEEPER_ENABLED
        b.PROMISE_KEEPER_ENABLED = 0
        try:
            self.assertEqual(b._pk_record_send({}, "بنرسل فني", "x", "1"), [])
        finally:
            b.PROMISE_KEEPER_ENABLED = orig

    def test_watchman_mirror(self):
        b = self.b
        orig = b.PROMISE_KEEPER_ENABLED
        b.PROMISE_KEEPER_ENABLED = 1
        try:
            b._pk_mirror_watchman({"id": "wmx-1", "apartment": "Ouja | 303", "guest": "منى",
                                   "responder": "Ohoud", "summary": "نرسل مناشف زيادة",
                                   "type": "action", "due": "2026-07-03T10:00:00",
                                   "state": "open"})
            rec = pdb.get("wmx-1")
            self.assertIsNotNone(rec)
            self.assertEqual(rec["source"], "watchman")
            self.assertEqual(rec["promised_by"], "Ohoud")
        finally:
            b.PROMISE_KEEPER_ENABLED = orig

    def test_nav_view_and_i18n_wiring(self):
        b = self.b
        self.assertIn("promises", b.NAV_DEF["labels"]["ar"], "trap #2: AR label required")
        self.assertIn("promises", b.NAV_DEF["labels"]["en"], "trap #2: EN label required")
        self.assertIn("promises", [i["id"] for i in b.NAV_DEF["items"]])
        self.assertTrue(any("promises" in c["ids"] for c in b.NAV_DEF["cats"]))
        self.assertIn('id="view_promises"', b.DASHBOARD_HTML)
        self.assertIn("function loadPromises", b.DASHBOARD_HTML)
        self.assertIn("/api/promises", b.DASHBOARD_HTML)


if __name__ == "__main__":
    unittest.main()
