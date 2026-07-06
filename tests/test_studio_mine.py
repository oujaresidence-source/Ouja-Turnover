# -*- coding: utf-8 -*-
"""Synthetic end-to-end run of studio.mine.run_scan — fake Hostaway + fake Claude.
Locks: inquiry/short threads skipped, story extracted + name-scrubbed, dedup cursor
means a second run never re-sends the same conversation to Claude."""
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from studio import db as sdb, mine
from studio.host import HOST


def _msgs(n_in, n_out):
    out = []
    for i in range(max(n_in, n_out)):
        if i < n_in:
            out.append({"body": "سؤال %d" % i, "isIncoming": 1,
                        "date": "2026-06-01 1%d:00:00" % i})
        if i < n_out:
            out.append({"body": "رد %d" % i, "isIncoming": 0,
                        "date": "2026-06-01 1%d:30:00" % i})
    return out


CONVOS = [
    {"id": 1, "listingMapId": 101,
     "reservation": {"status": "confirmed", "guestName": "سعد الدوسري"}},
    {"id": 2, "listingMapId": 101,
     "reservation": {"status": "inquiry", "guestName": "خالد"}},
    {"id": 3, "listingMapId": 102,
     "reservation": {"status": "new", "guestName": "نايف"}},
]
MSGS = {1: _msgs(4, 4), 2: _msgs(4, 4), 3: _msgs(2, 2)}   # 3 = short thread


def _fake_api_get(path, params=None):
    if path == "/conversations":
        return {"result": CONVOS if (params or {}).get("offset", 0) == 0 else []}
    cid = int(path.split("/")[2])
    return {"result": MSGS[cid]}


CLAUDE_CALLS = []


def _fake_claude_json(system, user, max_tokens=900, model=None):
    CLAUDE_CALLS.append(model)
    if "محرر قصص" in system:   # triage
        return {"story": True, "score": 9, "type": "weird_request",
                "one_line": "سعد الدوسري طلب شي غريب"}
    return {"title": "قصة سعد الدوسري", "summary": "طلب سعد شي غريب وسويناه",
            "beats": ["طلب", "نفّذنا"], "quotes": ["قال سعد: أبغى"],
            "emotion": "استغراب", "lesson": "نفّذ"}


class TestStudioMine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="studiomine_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        HOST.api_get = _fake_api_get
        HOST.claude_json = _fake_claude_json
        HOST.listings = lambda: {101: "Ouja | Test A", 102: "Ouja | Test B"}
        HOST.now = lambda: datetime(2026, 7, 6, 10, 0, 0)
        HOST.save_json = None
        HOST.model_fast = "fast-model"
        HOST.model_premium = "premium-model"

    def test_scan_pipeline_then_rescan(self):
        mine.run_scan(target=300)
        counts = sdb.scan_counts()
        self.assertEqual(counts.get("story"), 1)            # convo 1
        self.assertEqual(counts.get("skipped_short"), 1)    # convo 3
        # inquiry (convo 2) is skipped BEFORE fetch? no — after fetch, by status
        self.assertEqual(counts.get("skipped_inquiry"), 1)
        rows = sdb.stories()
        self.assertEqual(len(rows), 1)
        s = rows[0]
        # guest name scrubbed everywhere
        for blob in (s["title"], s["summary"], " ".join(s["quotes"]),
                     " ".join(s["beats"])):
            self.assertNotIn("سعد", blob)
            self.assertNotIn("الدوسري", blob)
        self.assertIn("الضيف", s["title"])
        # triage used the fast model, story the premium one
        self.assertIn("fast-model", CLAUDE_CALLS)
        self.assertIn("premium-model", CLAUDE_CALLS)
        # re-scan: dedup cursor means ZERO new Claude calls for the same convos
        before = len(CLAUDE_CALLS)
        mine.run_scan(target=300)
        self.assertEqual(len(CLAUDE_CALLS), before)


if __name__ == "__main__":
    unittest.main()
