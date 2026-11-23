# -*- coding: utf-8 -*-
"""
«المقاولات» end to end against a throwaway brain.db: seed → gate → start → reminders →
buttons → photos → done. Discord is a list (HOST.send appends), time is pinned.

Run: python3 -m unittest tests.test_contracting_flow
"""

import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                   # noqa: E402
from contracting import db, engine, notify, routes, seed     # noqa: E402
from contracting.host import HOST                             # noqa: E402

SENT = []


def fresh_db():
    tmp = tempfile.mkdtemp(prefix="ctrtest_")
    bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
    db.reset_init_cache()


class Base(unittest.TestCase):
    def setUp(self):
        fresh_db()
        SENT.clear()
        HOST.send = SENT.append
        HOST.lookup_did = lambda name: {"أصيل": "111111111111111111"}.get(name, "")
        HOST.now = lambda: dt.datetime(2026, 11, 23, 10, 0)
        os.environ["CONTRACTING_DRYRUN"] = "0"
        os.environ["CONTRACTING_ENABLED"] = "1"
        seed.seed_if_empty()
        self.d2 = [p for p in db.projects() if "D2" in p["title"]][0]
        self.apt = [p for p in db.projects() if "شقة" in p["title"]][0]

    def tearDown(self):
        os.environ.pop("CONTRACTING_DRYRUN", None)

    def start_d2(self, sup="أبو أمين"):
        db.save_draft(self.d2["id"], {"supervisor": sup}, {})
        return routes._start(self.d2["id"], "فيصل")

    def opened(self, pid, cid="900"):
        notify.delivered({"key": "open|" + pid, "ok": True, "channel_id": cid})


class TestSeed(Base):
    def test_two_projects_and_team_once(self):
        self.assertEqual(len(db.projects()), 2)
        self.assertFalse(seed.seed_if_empty())          # never twice
        self.assertEqual(len(db.projects()), 2)
        names = {p["name"] for p in db.people()}
        for n in ("فيصل", "أصيل", "ناصر", "أبو أمين", "تقي", "وجدان"):
            self.assertIn(n, names)

    def test_handover_is_the_last_line(self):
        its = self.d2["items"]
        self.assertEqual(its[-1]["name"], "فحص وتسليم")
        self.assertEqual(its[-1]["due"], "2026-12-15")
        self.assertEqual(engine.order_problems(its), {})
        self.assertEqual(len(its), 8)

    def test_a_deleted_project_never_comes_back(self):
        db.delete_draft(self.apt["id"])
        seed.seed_if_empty()
        self.assertEqual(len(db.projects()), 1)


class TestGate(Base):
    def test_no_supervisor_no_start(self):
        r = routes._start(self.d2["id"], "فيصل")
        self.assertFalse(r["ok"])
        self.assertIn("مشرف الموقع", r["error"])
        self.assertEqual(db.project(self.d2["id"])["status"], "draft")
        self.assertEqual(SENT, [])

    def test_apartment_blank_owner_and_unit_refused(self):
        db.save_draft(self.apt["id"], {"supervisor": "تقي"}, {})
        r = routes._start(self.apt["id"], "فيصل")
        self.assertFalse(r["ok"])
        self.assertIn("اسم المالك", r["why"])
        self.assertIn("الوحدة", r["why"])

    def test_out_of_order_refused(self):
        first = self.d2["items"][0]["id"]
        db.save_draft(self.d2["id"], {"supervisor": "أبو أمين"}, {first: "2026-12-20"})
        r = routes._start(self.d2["id"], "فيصل")
        self.assertFalse(r["ok"])
        self.assertIn("ترتيب التواريخ", r["why"])

    def test_start_opens_the_channel_once(self):
        r = self.start_d2()
        self.assertTrue(r["ok"])
        self.assertEqual([s["kind"] for s in SENT], ["open"])
        self.assertIn("مقاولات-", SENT[0]["channel_name"])
        self.assertIn("رفع مساحي", SENT[0]["text"])
        notify.tick(dt.datetime(2026, 11, 23, 10, 5))   # channel not reported yet → no 2nd open
        self.assertEqual([s["kind"] for s in SENT].count("open"), 1)
        self.assertFalse(routes._start(self.d2["id"], "فيصل")["ok"])   # already running


class TestReminders(Base):
    def test_full_day_ladder(self):
        self.start_d2()
        self.opened(self.d2["id"])
        SENT.clear()
        # line 1 due Tue 24 Nov; heads-up (Sun 22nd) predates the start → skipped
        notify.tick(dt.datetime(2026, 11, 24, 16, 1))
        self.assertEqual([(s["type"], s["target"], s["view"]) for s in SENT],
                         [("ask", "project", "ask")])
        ask = SENT[0]
        self.assertIn("رفع مساحي", ask["text"])
        self.assertIn("@أبو أمين", ask["text"])      # no Discord id yet → readable fallback
        notify.delivered({"key": ask["key"], "ok": True, "msg_id": "55", "type": "ask",
                          "item_id": ask["item_id"]})
        notify.tick(dt.datetime(2026, 11, 24, 16, 30))
        self.assertEqual(len(SENT), 1)                # sent once
        notify.tick(dt.datetime(2026, 11, 24, 19, 2))
        self.assertEqual(SENT[-1]["type"], "esc_lead")
        self.assertEqual(SENT[-1]["target"], "admin")
        self.assertIn("<@111111111111111111>", SENT[-1]["text"])   # Asil via the ops id map
        notify.delivered({"key": SENT[-1]["key"], "ok": True})
        notify.tick(dt.datetime(2026, 11, 25, 9, 1))
        types = [s["type"] for s in SENT]
        self.assertIn("esc_boss", types)
        self.assertIn("summary", types)

    def test_undelivered_ask_accuses_nobody(self):
        self.start_d2()
        self.opened(self.d2["id"])
        notify.tick(dt.datetime(2026, 11, 24, 16, 1))
        ask = [s for s in SENT if s.get("type") == "ask"][0]
        notify.delivered({"key": ask["key"], "ok": False, "error": "Missing Access"})
        SENT.clear()
        notify.tick(dt.datetime(2026, 11, 24, 19, 2))
        self.assertEqual([s.get("type") for s in SENT], [])

    def test_no_channel_no_reminders(self):
        self.start_d2()                               # channel never reported back
        SENT.clear()
        notify.tick(dt.datetime(2026, 11, 24, 16, 1))
        self.assertEqual(SENT, [])

    def test_dryrun_logs_and_sends_nothing(self):
        os.environ["CONTRACTING_DRYRUN"] = "1"
        r = self.start_d2()
        self.assertTrue(r["ok"])
        self.assertFalse(r["opening"])
        rep = notify.tick(dt.datetime(2026, 11, 24, 16, 1))
        self.assertEqual(SENT, [])
        self.assertGreaterEqual(rep["logged"], 1)
        kinds = [x["kind"] for x in db.sent_log()]
        self.assertIn("ask", kinds)
        self.assertTrue(all(x["dryrun"] for x in db.sent_log()))

    def test_flip_to_live_does_not_escalate_a_dry_question(self):
        os.environ["CONTRACTING_DRYRUN"] = "1"
        self.start_d2()
        notify.tick(dt.datetime(2026, 11, 24, 16, 1))   # ask lands only in the log
        os.environ["CONTRACTING_DRYRUN"] = "0"
        self.opened(self.d2["id"])
        SENT.clear()
        notify.tick(dt.datetime(2026, 11, 24, 19, 2))
        self.assertNotIn("esc_lead", [s.get("type") for s in SENT])


class TestButtons(Base):
    def setUp(self):
        super().setUp()
        self.start_d2()
        self.opened(self.d2["id"], "900")
        self.line = db.project(self.d2["id"])["items"][0]

    def test_done_needs_three_photos(self):
        r = notify.on_done_press(self.line["id"], "أبو أمين")
        self.assertTrue(r["ok"])
        self.assertEqual(db.item(self.line["id"])["status"], "awaiting_photos")
        r1 = notify.on_photos("900", ["u1", "u2"], "أبو أمين")
        self.assertFalse(r1["done"])
        self.assertEqual(db.item(self.line["id"])["status"], "awaiting_photos")
        r2 = notify.on_photos("900", ["u3"], "أبو أمين")
        self.assertTrue(r2["done"])
        self.assertIn("منقل غاز", r2["text"])                 # names the next line
        self.assertEqual(db.item(self.line["id"])["status"], "done")

    def test_photos_without_a_press_are_ignored(self):
        self.assertIsNone(notify.on_photos("900", ["u1", "u2", "u3"], "أبو أمين"))
        self.assertIsNone(notify.on_photos("777", ["u1"], "x"))     # not a project channel

    def test_delay_needs_reason_and_valid_date_then_reschedules(self):
        now = dt.datetime(2026, 11, 24, 16, 10)
        self.assertFalse(notify.on_delay(self.line["id"], "أبو أمين", "", "26/11", now)["ok"])
        self.assertIn("فات", notify.on_delay(self.line["id"], "أبو أمين", "x", "20/11", now)["error"])
        self.assertIn("جمعة", notify.on_delay(self.line["id"], "أبو أمين", "x", "27/11", now)["error"])
        r = notify.on_delay(self.line["id"], "أبو أمين", "المساح ما حضر", "26/11", now)
        self.assertTrue(r["ok"])
        self.assertEqual(db.item(self.line["id"])["due"], "2026-11-26")
        self.assertEqual(db.item(self.line["id"])["delays"], 1)
        SENT.clear()
        notify.tick(dt.datetime(2026, 11, 26, 16, 1))
        self.assertEqual([s["type"] for s in SENT], ["ask"])

    def test_block_tells_asil_now_and_faisal_after_a_day(self):
        now = dt.datetime(2026, 11, 24, 11, 0)
        r = notify.on_block(self.line["id"], "أبو أمين", "المالك قفل الباب", now)
        self.assertTrue(r["ok"])
        self.assertIn("<@111111111111111111>", r["admin_text"])
        SENT.clear()
        notify.tick(dt.datetime(2026, 11, 24, 19, 2))       # blocked lines don't escalate
        self.assertNotIn("esc_lead", [s.get("type") for s in SENT])
        notify.tick(dt.datetime(2026, 11, 25, 11, 5))
        self.assertIn("blocked_boss", [s.get("type") for s in SENT])

    def test_all_done_finishes_the_project(self):
        for it in db.project(self.d2["id"])["items"]:
            notify.on_done_press(it["id"], "أصيل")
            notify.on_photos("900", ["a", "b", "c"], "أصيل")
        self.assertEqual(db.project(self.d2["id"])["status"], "done")


class TestBoard(Base):
    def test_board_shape(self):
        b = routes.board_payload()
        self.assertTrue(b["ok"])
        self.assertEqual(len(b["projects"]), 2)
        d2 = [p for p in b["projects"] if "D2" in p["title"]][0]
        self.assertFalse(d2["gate"]["ok"])
        self.assertEqual(d2["gate"]["why"], ["مشرف الموقع"])
        asil = [p for p in b["people"] if p["name"] == "أصيل"][0]
        self.assertTrue(asil["linked"])
        self.assertEqual(asil["linked_from"], "ops")

    def test_new_project_from_pasted_lines(self):
        r = routes._new({"title": "مشروع تجربة", "lines": "دهان 1,200" + chr(10) + "إضاءة\t800"},
                        "فيصل")
        self.assertTrue(r["ok"])
        p = db.project(r["id"])
        self.assertEqual([i["name"] for i in p["items"]], ["دهان", "إضاءة", "فحص وتسليم"])
        self.assertEqual(p["signed"], 0)
        self.assertFalse(routes._new({"title": "x", "lines": ""}, "فيصل")["ok"])

    def test_people_id_validation(self):
        self.assertFalse(routes._people({"name": "تقي", "did": "123"}, "فيصل")["ok"])
        self.assertTrue(routes._people({"name": "تقي", "did": "222222222222222222"}, "فيصل")["ok"])
        self.assertEqual(notify.mention("تقي"), "<@222222222222222222>")


if __name__ == "__main__":
    unittest.main()
