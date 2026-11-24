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
CARDS = []                    # the pinned live card goes here, so SENT stays the message list


def _host_send(pl):
    (CARDS if pl.get("kind") == "card" else SENT).append(pl)


def fresh_db():
    tmp = tempfile.mkdtemp(prefix="ctrtest_")
    bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
    db.reset_init_cache()


class Base(unittest.TestCase):
    def setUp(self):
        fresh_db()
        SENT.clear()
        CARDS.clear()
        HOST.send = _host_send
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
        self.assertIn("رفع مساحي", SENT[0]["embed"]["description"])   # the card, pinned
        self.assertIn("@أبو أمين", SENT[0]["text"])                  # the ping above it
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

    def test_photos_before_the_press_get_a_menu_not_the_bin(self):
        # owner 2026-11-24: Abo Amen uploaded before the question and the photos vanished
        r = notify.on_photos("900", ["u1", "u2", "u3"], "أبو أمين", "m1")
        self.assertIn("pick", r)
        vals = [o["value"] for o in r["pick"]["options"]]
        self.assertEqual(vals[-2:], ["progress", "ignore"])
        self.assertIn(self.line["id"], vals)
        self.assertIn("لأي بند", r["pick"]["text"])
        self.assertIsNone(notify.on_photos("777", ["u1"], "x"))     # not a project channel
        done = notify.on_pick(r["pick"]["batch_id"], self.line["id"], "أبو أمين")
        self.assertTrue(done["ok"] and done["done"])                 # picking = «خلص» + 3 photos
        self.assertEqual(db.item(self.line["id"])["status"], "done")
        again = notify.on_pick(r["pick"]["batch_id"], self.line["id"], "أصيل")
        self.assertFalse(again["ok"])                                # first answer wins

    def test_one_photo_picked_then_the_rest_follow_on_their_own(self):
        r = notify.on_photos("900", ["u1"], "أبو أمين", "m1")
        res = notify.on_pick(r["pick"]["batch_id"], self.line["id"], "أبو أمين")
        self.assertFalse(res["done"])
        self.assertIn("1 من 3", res["final"])
        r2 = notify.on_photos("900", ["u2", "u3"], "أبو أمين", "m2")   # only line waiting → no menu
        self.assertTrue(r2["done"])

    def test_two_lines_waiting_means_ask_dont_guess(self):
        its = db.project(self.d2["id"])["items"]
        notify.on_done_press(its[0]["id"], "أبو أمين")
        notify.on_done_press(its[1]["id"], "أبو أمين")
        r = notify.on_photos("900", ["u1", "u2", "u3"], "أبو أمين", "m1")
        self.assertIn("pick", r)
        self.assertEqual(db.item(its[0]["id"])["photos"], [])
        self.assertEqual(r["pick"]["options"][0]["description"][:5], "ينتظر")   # waiting lines first

    def test_press_tells_only_the_presser_and_closes_if_photos_came_first(self):
        r = notify.on_done_press(self.line["id"], "أبو أمين")
        self.assertTrue(r["ephemeral"])
        line2 = db.project(self.d2["id"])["items"][1]
        b = notify.on_photos("900", ["a", "b", "c"], "أبو أمين", "m9")      # line 1 waits → goes there
        self.assertTrue(b["done"])
        db.execute("UPDATE contracting_items SET photos=? WHERE id=?",
                   ('[{"url":"x"},{"url":"y"},{"url":"z"}]', line2["id"]))
        r2 = notify.on_done_press(line2["id"], "أبو أمين")
        self.assertTrue(r2["done"])
        self.assertEqual(db.item(line2["id"])["status"], "done")

    def test_progress_photos_close_nothing_and_are_kept(self):
        r = notify.on_photos("900", ["u1", "u2"], "أبو أمين", "m1")
        res = notify.on_pick(r["pick"]["batch_id"], "progress", "أبو أمين")
        self.assertIn("شغل جاري", res["final"])
        self.assertEqual(len(db.batches(self.d2["id"], "progress")), 1)
        self.assertEqual(db.item(self.line["id"])["status"], "open")

    def test_backfill_once_and_only_unknown_photos(self):
        notify.on_done_press(self.line["id"], "أبو أمين")
        notify.on_photos("900", ["k1"], "أبو أمين", "known")
        msgs = [{"id": "known", "by": "أبو أمين", "urls": ["k1"]},
                {"id": "old1", "by": "أبو أمين", "urls": ["o1", "o2"]}]
        pks = notify.backfill_candidates("900", msgs)
        self.assertEqual(len(pks), 2)                                # one menu per early photo
        self.assertEqual(notify.backfill_candidates("900", msgs), [])   # never twice

    def test_backfill_skips_photos_the_old_code_already_counted(self):
        # old rows have no message id; the channel must not get a menu for them
        notify.on_done_press(self.line["id"], "x")
        db.add_photos(self.line["id"], [{"url": "https://cdn/x/a.jpg?ex=1", "at": "2026-11-24T14:18:00"},
                                        {"url": "https://cdn/x/b.jpg", "at": "2026-11-24T14:18:00"},
                                        {"url": "https://cdn/x/c.jpg", "at": "2026-11-24T14:18:00"}], "x")
        msgs = [{"id": "e1", "by": "x", "urls": ["https://cdn/x/early.jpg"], "at": "2026-11-24T11:22:00"},
                {"id": "e2", "by": "x", "urls": ["https://cdn/x/a.jpg?ex=2"], "at": "2026-11-24T14:20:00"},
                {"id": "e3", "by": "x", "urls": ["https://cdn/x/new.jpg"], "at": "2026-11-24T14:25:00"}]
        pks = notify.backfill_candidates("900", msgs)
        self.assertEqual(len(pks), 1)                                # only the unseen, later one

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
        notify.tick(dt.datetime(2026, 11, 26, 16, 1))      # a Thursday: the owner's file goes too
        self.assertEqual([s["type"] for s in SENT if s["kind"] == "post"], ["ask"])

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

    def test_board_lists_discord_members_for_the_supervisor_dropdown(self):
        HOST.roster = lambda: {"rows": [{"id": "222222222222222222", "name": "ريم", "user": "reem"}],
                               "loading": False}
        try:
            b = routes.board_payload()
            self.assertEqual(b["discord_members"], [{"name": "ريم", "user": "reem"}])
            self.assertFalse(b["discord_loading"])
            self.assertNotIn("id", b["discord_members"][0])        # names only reach the page
        finally:
            HOST.roster = None
        b = routes.board_payload()                                 # no roster wired → empty, not broken
        self.assertEqual(b["discord_members"], [])
        self.assertFalse(b["discord_error"])

    def test_board_says_when_discord_members_could_not_load(self):
        HOST.roster = lambda: {"rows": [], "loading": False, "error": "no members returned"}
        try:
            b = routes.board_payload()
            self.assertTrue(b["discord_error"])                    # the dropdown says so, not «loading» forever
            self.assertFalse(b["discord_loading"])
        finally:
            HOST.roster = None

    def test_live_is_the_default_and_draft_projects_send_nothing(self):
        os.environ.pop("CONTRACTING_DRYRUN", None)
        self.assertFalse(notify.dryrun())                          # owner 2026-11-24: live by default
        os.environ["CONTRACTING_DRYRUN"] = "1"
        self.assertTrue(notify.dryrun())
        os.environ.pop("CONTRACTING_DRYRUN", None)
        rep = notify.tick(dt.datetime(2026, 12, 9, 9, 0))          # both seeds still «ما بدا»
        self.assertEqual((rep["opened"], rep["sent"]), (0, 0))
        self.assertEqual(SENT, [])

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



class TestCard(Base):
    """The pinned card: one message per project channel, edited as the lines move."""

    def card(self, today=dt.date(2026, 11, 24)):
        return notify.card_embed(db.project(self.d2["id"]), today)

    def test_card_shape(self):
        its = self.d2["items"]
        db.save_draft(self.d2["id"], {}, {its[i]["id"]: "2026-12-10" for i in (2, 3, 4)})
        self.start_d2()
        e = self.card()
        self.assertEqual(e["title"], self.d2["title"])
        names = [f["name"] for f in e["fields"]]
        self.assertEqual(names, ["المالك", "مشرف الموقع", "المبلغ المعتمد"])   # unit repeats the title → hidden
        self.assertIn("22,317.90", e["fields"][2]["value"])
        self.assertIn("0 من 8 خلصت", e["description"])
        self.assertEqual(e["description"].count("الخميس 10 ديسمبر"), 1)       # 4 lines, one header
        self.assertIn("3 صور", e["footer"]["text"])

    def test_unit_shown_when_the_title_does_not_say_it(self):
        db.save_draft(self.apt["id"], {"owner": "م. سعد", "unit": "N12"}, {})
        e = notify.card_embed(db.project(self.apt["id"]), dt.date(2026, 11, 24))
        self.assertIn("الوحدة", [f["name"] for f in e["fields"]])

    def test_marks_follow_the_lines(self):
        self.start_d2()
        its = db.project(self.d2["id"])["items"]
        db.mark_done(its[0]["id"], "فيصل", "خلص قبل النظام")
        db.press_done(its[1]["id"], "أبو أمين")
        e = notify.card_embed(db.project(self.d2["id"]), dt.date(2026, 12, 7))
        self.assertIn("1 من 8 خلصت", e["description"])
        self.assertIn("✅", e["description"])
        self.assertIn("ينتظر الصور", e["description"])
        self.assertIn("فات موعده", e["description"])        # the 6 Dec line, today the 7th

    def test_tick_posts_the_card_once_then_edits_only_on_change(self):
        self.start_d2()
        self.opened(self.d2["id"])
        notify.tick(dt.datetime(2026, 11, 24, 10, 0))
        self.assertEqual(len(CARDS), 1)
        self.assertIsNone(CARDS[0]["msg_id"])                # first time: post + pin
        notify.tick(dt.datetime(2026, 11, 24, 10, 2))
        self.assertEqual(len(CARDS), 1)                      # in flight → not twice
        notify.delivered({"key": CARDS[0]["key"], "ok": True, "msg_id": "777",
                          "hash": CARDS[0]["hash"]})
        notify.tick(dt.datetime(2026, 11, 24, 10, 4))
        self.assertEqual(len(CARDS), 1)                      # nothing changed → silent
        db.mark_done(db.project(self.d2["id"])["items"][0]["id"], "فيصل", "")
        notify.tick(dt.datetime(2026, 11, 24, 10, 6))
        self.assertEqual(len(CARDS), 2)
        self.assertEqual(CARDS[1]["msg_id"], "777")          # edit the pinned one, not a new post

    def test_open_delivery_remembers_the_card(self):
        self.start_d2()
        op = SENT[0]
        notify.delivered({"key": op["key"], "ok": True, "channel_id": "900", "card_msg_id": "778",
                          "hash": op["hash"]})
        notify.tick(dt.datetime(2026, 11, 23, 10, 5))
        self.assertEqual(CARDS, [])                          # same day, same card → nothing

    def test_no_card_in_dry_run(self):
        os.environ["CONTRACTING_DRYRUN"] = "1"
        self.start_d2()
        db.set_channel(self.d2["id"], "900")
        notify.tick(dt.datetime(2026, 11, 24, 10, 0))
        self.assertEqual(CARDS, [])


class TestGrouped(Base):
    """Lines due together → one message; a closed line's buttons go grey."""

    def setUp(self):
        super().setUp()
        its = self.d2["items"]
        db.save_draft(self.d2["id"], {}, {its[i]["id"]: "2026-12-10" for i in (2, 3, 4)})
        self.start_d2()
        self.opened(self.d2["id"])
        SENT.clear()

    def posts(self):
        return [x for x in SENT if x.get("kind") == "post"]

    def test_four_lines_one_question(self):
        notify.tick(dt.datetime(2026, 12, 10, 16, 1))
        asks = [x for x in self.posts() if x["type"] == "ask"]
        self.assertEqual(len(asks), 1)
        a = asks[0]
        self.assertEqual(len(a["keys"]), 4)
        self.assertEqual(len(a["ask_items"]), 4)
        self.assertIn("هالبنود موعدها اليوم", a["text"])
        notify.delivered({"key": a["key"], "keys": a["keys"], "item_ids": a["item_ids"],
                          "ok": True, "msg_id": "60", "type": "ask"})
        for iid in a["item_ids"]:
            self.assertEqual(db.item(iid)["ask_msg_id"], "60")
        notify.tick(dt.datetime(2026, 12, 10, 19, 2))
        esc = [x for x in self.posts() if x["type"] == "esc_lead"]
        self.assertEqual(len(esc), 1)                                # one escalation, four lines
        self.assertEqual(esc[0]["text"].count("ما انرد"), 4)

    def test_a_closed_line_greys_its_buttons_once(self):
        notify.tick(dt.datetime(2026, 12, 10, 16, 1))
        a = [x for x in self.posts() if x["type"] == "ask"][0]
        notify.delivered({"key": a["key"], "keys": a["keys"], "item_ids": a["item_ids"],
                          "ok": True, "msg_id": "60", "type": "ask"})
        CARDS.clear()
        notify.tick(dt.datetime(2026, 12, 10, 16, 3))
        self.assertEqual([c for c in CARDS if c["kind"] == "askview"], [])
        db.mark_done(a["item_ids"][0], "فيصل", "")
        notify.tick(dt.datetime(2026, 12, 10, 16, 5))
        av = [c for c in SENT + CARDS if c.get("kind") == "askview"]
        self.assertEqual(len(av), 1)
        self.assertEqual([i["done"] for i in av[0]["ask_items"]], [True, False, False, False])
        notify.tick(dt.datetime(2026, 12, 10, 16, 7))
        self.assertEqual(len([c for c in SENT + CARDS if c.get("kind") == "askview"]), 1)


class TestOwnerFile(Base):
    def test_thursday_once_and_handover_once(self):
        self.start_d2()
        self.opened(self.d2["id"])
        SENT.clear()
        notify.tick(dt.datetime(2026, 11, 26, 13, 0))               # Thursday
        notify.tick(dt.datetime(2026, 11, 26, 15, 0))
        pdfs = [x for x in SENT if x.get("kind") == "ownerpdf"]
        self.assertEqual([x["reason"] for x in pdfs], ["weekly"])
        notify.tick(dt.datetime(2026, 11, 27, 13, 0))               # Friday — nothing
        self.assertEqual(len([x for x in SENT if x.get("kind") == "ownerpdf"]), 1)
        for it in db.project(self.d2["id"])["items"]:
            db.mark_done(it["id"], "فيصل", "")
        db.finish_if_complete(self.d2["id"])
        notify.tick(dt.datetime(2026, 11, 28, 10, 0))
        notify.tick(dt.datetime(2026, 11, 28, 10, 2))
        self.assertEqual([x["reason"] for x in SENT if x.get("kind") == "ownerpdf"],
                         ["weekly", "final"])

    def test_the_page_is_for_the_owner(self):
        from contracting import ownerpdf
        self.start_d2()
        its = db.project(self.d2["id"])["items"]
        db.mark_done(its[0]["id"], "فيصل", "")
        notify.on_delay(its[1]["id"], "أبو أمين", "المورد تأخر <b>", "3/12",
                        dt.datetime(2026, 11, 25, 10, 0))
        p, page = ownerpdf.project_html(self.d2["id"], "weekly", dt.date(2026, 11, 26))
        self.assertIn("الجلسة الخارجية", page)
        self.assertIn("1</span><span class='of'>من 8", page)
        self.assertIn("المورد تأخر &lt;b&gt;", page)                # escaped, and the reason shows
        self.assertNotIn("أبو أمين", page)                          # no staff names in the owner's file
        self.assertNotIn("فيصل", page)
        self.assertIn("22,317.90", page)


class TestPhotoCopies(Base):
    def test_shrinks_and_respects_the_ceiling(self):
        import io
        from PIL import Image
        from contracting import photos
        buf = io.BytesIO()
        Image.new("RGB", (4000, 3000), (200, 180, 150)).save(buf, "PNG")
        rel = photos.keep("", "cp_x", raw=buf.getvalue())
        self.assertTrue(rel)
        with Image.open(photos.path_of(rel)) as im:
            self.assertEqual(max(im.size), photos.MAX_PX)
        self.assertEqual(photos.path_of("../../etc/passwd"), "")
        os.environ["CONTRACTING_PHOTO_CAP_MB"] = "0"
        try:
            self.assertEqual(photos.keep("", "cp_x", raw=buf.getvalue()), "")
        finally:
            os.environ.pop("CONTRACTING_PHOTO_CAP_MB", None)
        self.assertEqual(photos.keep("not-a-url", "cp_x"), "")


class TestMarkDone(Base):
    def test_admin_marks_a_line_done_without_photos(self):
        self.start_d2()
        first = db.project(self.d2["id"])["items"][0]
        r = routes._mark_done({"item_id": first["id"]}, "فيصل", "admin")
        self.assertTrue(r["ok"])
        it = db.item(first["id"])
        self.assertEqual((it["status"], it["done_by"]), ("done", "فيصل"))
        kinds = [e["kind"] for e in db.events(self.d2["id"])]
        self.assertIn("done_manual", kinds)                  # who closed it without photos stays on record

    def test_only_admin(self):
        self.start_d2()
        first = db.project(self.d2["id"])["items"][0]
        self.assertFalse(routes._mark_done({"item_id": first["id"]}, "ناصر", "ops")["ok"])
        self.assertEqual(db.item(first["id"])["status"], "open")

    def test_not_on_a_draft(self):
        first = self.d2["items"][0]
        self.assertFalse(routes._mark_done({"item_id": first["id"]}, "فيصل", "admin")["ok"])

    def test_last_line_finishes_the_project(self):
        self.start_d2()
        for it in db.project(self.d2["id"])["items"]:
            routes._mark_done({"item_id": it["id"]}, "فيصل", "admin")
        self.assertEqual(db.project(self.d2["id"])["status"], "done")


if __name__ == "__main__":
    unittest.main()
