# -*- coding: utf-8 -*-
"""Synthetic end-to-end run of studio.mine — fake Hostaway + fake Claude.
Locks (v2): inquiry/short threads skipped; POSITIVE brand-safe story extracted +
name-scrubbed; brand-unsafe high scorers BLOCKED (never become content); dedup cursor
means a re-run never re-sends the same conversation to Claude; deep-scan reset clears
weak legacy cards but keeps posted/filmed."""
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


# Live Hostaway shape (the 2026-07-06 all-skipped bug): conversations carry a
# top-level reservationId but NO embedded reservation object — status must be
# resolved via GET /reservations/{id}.
CONVOS = [
    {"id": 1, "listingMapId": 101, "reservationId": 9001,
     "recipientName": "سعد الدوسري"},                 # positive hero_save → story
    {"id": 2, "listingMapId": 101, "reservationId": 9002,
     "recipientName": "خالد"},                       # inquiry per /reservations
    {"id": 3, "listingMapId": 102, "reservationId": 9003,
     "recipientName": "نايف"},                        # short thread
    {"id": 4, "listingMapId": 102,
     "recipientName": "مجهول"},                       # long thread, NO reservation
    {"id": 5, "listingMapId": 101, "reservationId": 9005,
     "recipientName": "عبدالله"},                     # high score but brand-UNSAFE → blocked
]
MSGS = {1: _msgs(4, 4), 2: _msgs(4, 4), 3: _msgs(2, 2), 4: _msgs(4, 4), 5: _msgs(4, 4)}
RES = {9001: "modified", 9002: "inquiry", 9003: "new", 9005: "checked-out"}
RES_LOOKUPS = []


def _fake_api_get(path, params=None):
    if path == "/conversations":
        return {"result": CONVOS if (params or {}).get("offset", 0) == 0 else []}
    if path.startswith("/reservations/"):
        rid = int(path.split("/")[2])
        RES_LOOKUPS.append(rid)
        return {"result": {"id": rid, "status": RES[rid]}}
    cid = int(path.split("/")[2])
    return {"result": MSGS[cid]}


CLAUDE_CALLS = []


def _fake_claude_json(system, user, max_tokens=900, model=None):
    CLAUDE_CALLS.append(model)
    if "brand_safe" in system:   # triage (v2 marker)
        # convo 5 is the brand-unsafe one — high score but must be blocked
        if "5" in _CURRENT_UNIT.get("cid", ""):
            return {"story": True, "brand_safe": False, "positive": False,
                    "score": 9, "type": "other", "one_line": "شكوى ما انحلّت"}
        return {"story": True, "brand_safe": True, "positive": True,
                "score": 9, "type": "hero_save", "one_line": "عطل انحل بسرعة والضيف انبسط"}
    return {"title": "قصة سعد الدوسري انتهت زين", "angle": "الفريق حل الموقف بسرعة",
            "summary": "صار عطل وحلّه الفريق بأقل من ساعة والضيف سعد الدوسري انبسط",
            "beats": ["صار عطل", "الفريق تحرّك", "انبسط سعد"], "quotes": ["قال سعد: شكراً"],
            "emotion": "من توتر إلى ارتياح", "lesson": "سرعة الرد تصنع الفرق"}


# the fake needs to know which conversation is being triaged; the miner doesn't pass
# the id into claude_json, so we sniff it from a shared marker set by a patched loop.
_CURRENT_UNIT = {}
_orig_build = mine.engine.build_transcript


def _tracking_build(msgs, **kw):
    # tag which convo this transcript belongs to so the fake triage can vary its verdict
    _CURRENT_UNIT["cid"] = "5" if msgs is MSGS.get(5) else ""
    return _orig_build(msgs, **kw)


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
        mine.engine.build_transcript = _tracking_build

    @classmethod
    def tearDownClass(cls):
        mine.engine.build_transcript = _orig_build

    def test_scan_pipeline_then_rescan(self):
        # poisoned legacy row (the 2026-07-06 bug) must be healed + re-evaluated
        sdb.mark_scanned("1", "101", "Ouja | Test A", "سعد الدوسري", "",
                         "", 8, "skipped_inquiry", ts="2026-07-06 14:40:00")
        mine.run_scan(target=300)
        counts = sdb.scan_counts()
        self.assertEqual(counts.get("story"), 1)            # convo 1 (healed + mined)
        self.assertEqual(counts.get("skipped_short"), 1)    # convo 3
        self.assertEqual(counts.get("skip_inquiry"), 2)     # convo 2 + no-reservation 4
        self.assertEqual(counts.get("blocked_brand"), 1)    # convo 5 (high score, brand-unsafe)
        self.assertNotIn("skipped_inquiry", counts)         # legacy verdict purged
        # short thread (convo 3) must NOT cost a /reservations lookup
        self.assertNotIn(9003, RES_LOOKUPS)
        rows = sdb.stories()
        self.assertEqual(len(rows), 1)
        s = rows[0]
        self.assertTrue(s["angle"])                          # v2 positive angle stored
        # guest name scrubbed everywhere
        for blob in (s["title"], s["summary"], " ".join(s["quotes"]),
                     " ".join(s["beats"])):
            self.assertNotIn("سعد", blob)
            self.assertNotIn("الدوسري", blob)
        self.assertIn("الضيف", s["title"])
        self.assertIn("fast-model", CLAUDE_CALLS)
        self.assertIn("premium-model", CLAUDE_CALLS)
        # re-scan: dedup cursor means ZERO new Claude calls for the same convos
        before = len(CLAUDE_CALLS)
        mine.run_scan(target=300)
        self.assertEqual(len(CLAUDE_CALLS), before)


class TestDeepScanReset(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="studioreset_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        sdb.reset_init_cache()

    def _story(self, cid, title, status="new"):
        sid = sdb.add_story(cid, "101", "Ouja | X", 8, "hero_save",
                            {"title": title, "summary": "s", "angle": "a",
                             "beats": [], "quotes": [], "emotion": "", "lesson": ""},
                            "2026-07-08 09:00:00")
        if status != "new":
            sdb.set_story_status(sid, status)
        return sid

    def test_keeps_posted_clears_new(self):
        kept_sid = self._story("c-posted", "قصة منشورة")
        weak_sid = self._story("c-weak", "قصة ضعيفة")
        # a posted idea pins its story
        idea = {"hook_spoken": "h", "visual_title": "t", "visual_sub": "", "angle": "",
                "why_it_works": "w", "script": [], "video_type": "talking", "cta": "",
                "audience": "niche", "trigger": "curiosity"}
        iid = sdb.add_idea(kept_sid, idea, "2026-07-08 09:00:00")
        sdb.set_idea_status(iid, "posted", views=50000)
        sdb.add_idea(weak_sid, idea, "2026-07-08 09:00:00")  # status new → should clear

        res = sdb.reset_for_deep_scan()

        titles = {s["title"] for s in sdb.stories()}
        self.assertIn("قصة منشورة", titles)       # kept (has posted idea)
        self.assertNotIn("قصة ضعيفة", titles)      # cleared
        posted = sdb.ideas(status="posted")
        self.assertEqual(len(posted), 1)            # posted idea survived
        self.assertEqual(res["kept_stories"], 1)


if __name__ == "__main__":
    unittest.main()
