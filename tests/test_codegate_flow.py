# tests/test_codegate_flow.py
# -*- coding: utf-8 -*-
"""«تسليم الرموز» flow against a fake Discord + fake Hostaway, a temp brain.db, injected now.
Run: python3 -m unittest tests.test_codegate_flow"""
import asyncio
import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from brain import db as bdb  # noqa: E402
from codegate import db, engine, flow  # noqa: E402

TZ = engine.tz()
DAY = "2026-10-21"
GATED, OPEN = 461328, 999
CODE_WORD = "كود الدخول 4821"       # what the fake code_in treats as "the code message"


def at(hh, mm=0):
    return datetime.datetime(2026, 10, 21, hh, mm, tzinfo=TZ)


def run(c):
    return asyncio.run(c)


class Fake:
    def __init__(self):
        self.posts, self.edits, self.escalations = [], [], []
        self.arrivals = [self.arr("r1", GATED), self.arr("r9", OPEN)]
        self.msgs = {"c-r1": [{"inbound": False, "at": at(8),
                               "body": 'Please reply "I agree to the house rules"'},
                              {"inbound": True, "at": at(8, 30), "body": "I agree"}]}
        self.code = {}
        self._mid = 1000

    @staticmethod
    def arr(rid, lid, hh=16):
        return {"res_id": rid, "lid": lid, "day": DAY, "unit": "U%s" % lid, "guest": "G" + rid,
                "conversation_id": "c-" + rid,
                "checkin_at": at(hh).isoformat(timespec="seconds")}

    async def post(self, ch, text, embed=None, buttons=None):
        self._mid += 1
        self.posts.append({"id": str(self._mid), "text": text, "embed": embed, "buttons": buttons})
        return str(self._mid)

    async def edit(self, ch, mid, embed=None, buttons=None):
        self.edits.append({"id": mid, "embed": embed, "buttons": buttons})
        return True

    async def escalate(self, title, detail):
        self.escalations.append(title)

    async def channel(self):
        return "900"


class FlowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cgf_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        units = os.path.join(self.tmp, "codegate_units.json")
        with open(units, "w") as fh:
            json.dump({"listing_ids": [GATED]}, fh)
        self.f = Fake()
        self.now = at(9, 5)
        flow.wire_for_tests({
            "now": lambda: self.now,
            "state_path": lambda name: os.path.join(self.tmp, name),
            "today_arrivals": self.arrivals_for,
            "messages": lambda cid: list(self.f.msgs.get(cid, [])),
            "code_sent": lambda cid: bool(self.f.code.get(cid)),
            "code_in": lambda msgs: any(not m["inbound"] and CODE_WORD in m["body"]
                                        for m in msgs),
            "cover": lambda lid, day: {"name": "نورة", "did": "11", "role_id": "",
                                       "owner_did": "22"},
            "channel": self.f.channel, "post": self.f.post, "edit": self.f.edit,
            "escalate": self.f.escalate,
        })
        self.asked_days = []
        self.addCleanup(self._restore_globals, bdb._DB_PATH_OVERRIDE)
        if self.LIVE:
            flow.set_live(True, "test")

    @staticmethod
    def _restore_globals(prev_path):
        """FlowCase turns live ON and points brain.db at a temp file: neither may leak into
        the test modules that run after this one."""
        bdb.set_db_path_for_tests(prev_path)
        db.reset_init_cache()
        flow._live_cache.update({"v": None, "at": 0.0})
        flow._units_cache.update({"key": None, "ids": set()})

    LIVE = True

    def arrivals_for(self, day_iso):
        self.asked_days.append(day_iso)
        return list(self.f.arrivals)

    def cards(self):
        return [p for p in self.f.posts if p["buttons"]]


class TestTick(FlowCase):
    def test_only_gated_units_get_cards(self):
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
        self.assertIn("U%s" % GATED, self.cards()[0]["embed"]["title"])
        self.assertIsNone(db.get("r9"))

    def test_nothing_posted_before_nine_unless_forced(self):
        self.now = at(8, 30)
        run(flow.tick())
        self.assertEqual(self.f.posts, [])
        run(flow.tick(force=True))
        self.assertEqual(len(self.cards()), 1)

    def test_header_mentions_coverer_once(self):
        run(flow.tick())
        headers = [p for p in self.f.posts if not p["buttons"]]
        self.assertEqual(len(headers), 1)
        self.assertIn("<@11>", headers[0]["text"])

    def test_tick_twice_and_restart_is_idempotent(self):
        run(flow.tick())
        db.reset_init_cache()                              # simulated redeploy
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
        self.assertEqual(len([p for p in self.f.posts if not p["buttons"]]), 1)
        self.assertEqual(self.f.edits, [])                 # unchanged content → no edit

    def test_new_reply_edits_card(self):
        run(flow.tick())
        self.f.msgs["c-r1"].append({"inbound": True, "at": at(9, 10), "body": "see you"})
        self.now = at(9, 20)
        run(flow.tick())
        self.assertEqual(len(self.f.edits), 1)
        self.assertIn("see you", json.dumps(self.f.edits[0]["embed"], ensure_ascii=False))

    def test_two_hour_then_late_alerts_once_each(self):
        run(flow.tick())
        self.now = at(14, 1)
        run(flow.tick())
        run(flow.tick())
        self.now = at(16, 2)
        run(flow.tick())
        run(flow.tick())
        self.assertEqual(len(self.f.escalations), 2)

    def test_tick_late_booking_alerts_once(self):
        self.now = at(17)
        self.f.arrivals = [self.f.arr("r2", GATED, hh=16)]
        run(flow.tick())
        run(flow.tick())
        self.assertEqual(len(self.f.escalations), 1)
        it = db.get("r2")
        self.assertTrue(it["alert_2h_at"] and it["alert_late_at"])

    def test_cancelled_after_card(self):
        run(flow.tick())
        self.f.arrivals = []
        self.now = at(14, 5)
        run(flow.tick())
        self.assertEqual(db.get("r1")["cancelled"], 1)
        self.assertEqual(self.f.escalations, [])
        self.assertEqual(self.f.edits[-1]["embed"]["color"], engine.COLOR_OFF)

    def test_disabled_does_nothing(self):
        os.environ["CODEGATE_ENABLED"] = "0"
        try:
            self.assertEqual(run(flow.tick()), {"skipped": "off"})
        finally:
            os.environ.pop("CODEGATE_ENABLED")


class TestPress(FlowCase):
    def setUp(self):
        super().setUp()
        run(flow.tick())
        self.mid = self.cards()[0]["id"]

    def p(self, did="11", admin=False, ops=False, name="نورة"):
        return {"name": name, "did": did, "is_admin": admin, "is_ops": ops}

    def test_coverer_releases_card_turns_green(self):
        ok, msg = run(flow.press_release(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(self.f.edits[-1]["embed"]["color"], engine.COLOR_DONE)
        self.assertEqual(db.get("r1")["released_by"], "نورة")

    def test_stranger_refused(self):
        ok, msg = run(flow.press_release(self.mid, self.p(did="77", name="x")))
        self.assertFalse(ok)
        self.assertIsNone(db.get("r1")["released_at"])

    def test_double_press_first_wins(self):
        run(flow.press_release(self.mid, self.p()))
        ok, msg = run(flow.press_release(self.mid, self.p(did="22", name="ناصر")))
        self.assertFalse(ok)
        self.assertIn("أُرسل من قبل", msg)

    def test_unknown_message(self):
        ok, msg = run(flow.press_release("424242", self.p()))
        self.assertFalse(ok)

    def test_release_stops_alerts(self):
        run(flow.press_release(self.mid, self.p()))
        self.now = at(16, 30)
        run(flow.tick())
        self.assertEqual(self.f.escalations, [])

    def test_honesty_warning_when_code_not_seen(self):
        self.now = at(13)
        run(flow.press_release(self.mid, self.p()))
        self.now = at(13, 20)
        run(flow.tick())
        warns = [p for p in self.f.posts if p["text"] and "ما شفت رسالة الرمز" in p["text"]]
        self.assertEqual(len(warns), 1)
        self.assertIn("<@11>", warns[0]["text"])
        run(flow.tick())
        self.assertEqual(len([p for p in self.f.posts
                              if p["text"] and "ما شفت رسالة الرمز" in p["text"]]), 1)

    def test_no_warning_when_code_seen(self):
        self.now = at(13)
        run(flow.press_release(self.mid, self.p()))
        self.f.code["c-r1"] = True
        self.now = at(13, 20)
        run(flow.tick())
        self.assertEqual(db.get("r1")["code_seen"], 1)
        self.assertFalse(any(p["text"] and "ما شفت" in p["text"] for p in self.f.posts))

    def test_undo_admin_only(self):
        run(flow.press_release(self.mid, self.p()))
        ok, _ = run(flow.press_undo(self.mid, self.p()))
        self.assertFalse(ok)
        ok, _ = run(flow.press_undo(self.mid, self.p(did="5", admin=True, name="Faisal")))
        self.assertTrue(ok)
        self.assertIsNone(db.get("r1")["released_at"])


class TestRobust(FlowCase):
    def test_one_bad_conversation_does_not_stop_the_day(self):
        self.f.arrivals = [self.f.arr("r1", GATED, hh=16), self.f.arr("r2", GATED, hh=16)]
        good = flow.HOST.messages

        def flaky(cid):
            if cid == "c-r1":
                raise RuntimeError("hostaway down")
            return good(cid)
        flow.HOST.messages = flaky
        run(flow.tick())
        self.assertIsNotNone(db.get("r2")["card_message_id"])
        self.now = at(14, 1)
        run(flow.tick())
        self.assertTrue(db.get("r2")["alert_2h_at"])
        self.assertTrue(db.get("r1")["alert_2h_at"])   # the bad one is still alerted
        self.assertEqual(len(self.f.escalations), 2)

    def test_item_that_blows_up_late_does_not_stop_the_next(self):
        self.f.arrivals = [self.f.arr("r1", GATED), self.f.arr("r2", GATED)]
        real = self.f.post

        async def post(ch, text, embed=None, buttons=None):
            if embed and "Gr1" in embed["title"] + str(embed.get("fields")):
                raise RuntimeError("discord 500")
            return await real(ch, text, embed=embed, buttons=buttons)
        flow.HOST.post = post
        run(flow.tick())
        self.assertIsNotNone(db.get("r2")["card_message_id"])

    def test_failed_arrivals_fetch_raises(self):
        def boom(day_iso):
            raise RuntimeError("hostaway down")
        flow.HOST.today_arrivals = boom
        with self.assertRaises(RuntimeError):
            run(flow.tick())

    def test_cancelled_before_nine_never_gets_a_ghost_card(self):
        self.now = at(8, 30)
        run(flow.tick())
        self.f.arrivals = []
        self.now = at(9, 5)
        run(flow.tick())
        self.assertEqual(db.get("r1")["cancelled"], 1)
        self.assertEqual(self.cards(), [])
        self.assertIsNone(db.get("r1")["card_message_id"])

    def test_failed_header_post_is_retried(self):
        real = self.f.post
        state = {"n": 0}

        async def post(ch, text, embed=None, buttons=None):
            state["n"] += 1
            if state["n"] == 1:
                return None
            return await real(ch, text, embed=embed, buttons=buttons)
        flow.HOST.post = post
        run(flow.tick())
        self.assertEqual([p for p in self.f.posts if not p["buttons"]], [])
        run(flow.tick())
        self.assertEqual(len([p for p in self.f.posts if not p["buttons"]]), 1)

    def test_release_during_alert_is_not_followed_by_alert_or_red_card(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        self.now = at(14, 1)
        real = self.f.escalate

        async def escalate(title, detail):
            await real(title, detail)
            await flow.press_release(mid, {"name": "نورة", "did": "11",
                                           "is_admin": False, "is_ops": False})
        flow.HOST.escalate = escalate
        run(flow.tick())
        self.assertEqual(self.f.edits[-1]["embed"]["color"], engine.COLOR_DONE)

    def test_press_between_read_and_alert_suppresses_alert(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        self.now = at(14, 1)
        real = flow.db.stamp

        def stamp(rid, col, at_iso):
            real(rid, col, at_iso)
            if col == "alert_2h_at" and not db.get(rid)["released_at"]:
                db.release(rid, "نورة", "11", at_iso)
        flow.db.stamp = stamp
        try:
            run(flow.tick())
        finally:
            flow.db.stamp = real
        self.assertEqual(self.f.escalations, [])
        self.assertTrue(mid)

    def test_failed_cover_lookup_keeps_stored_coverer(self):
        run(flow.tick())
        flow.HOST.cover = lambda lid, day: None
        self.now = at(9, 30)
        run(flow.tick())
        it = db.get("r1")
        self.assertEqual((it["cover_name"], it["cover_did"]), ("نورة", "11"))
        self.assertEqual(len([p for p in self.f.posts if not p["buttons"]]), 1)


class TestPressEdges(FlowCase):
    def p(self):
        return {"name": "نورة", "did": "11", "is_admin": False, "is_ops": False}

    def test_press_on_cancelled_booking_refused(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        self.f.arrivals = []
        self.now = at(10)
        run(flow.tick())
        ok, msg = run(flow.press_release(mid, self.p()))
        self.assertFalse(ok)
        self.assertIsNone(db.get("r1")["released_at"])

    def test_press_after_redeploy_still_works(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        db.reset_init_cache()
        ok, _ = run(flow.press_release(mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(db.get("r1")["released_by"], "نورة")


class TestSoak(FlowCase):
    """C1/I1: while Hostaway still runs the old e-sign flow, the list runs but nothing alerts."""
    LIVE = False

    def test_default_is_soak(self):
        self.assertFalse(flow.live())

    def test_soak_posts_cards_and_headers_only(self):
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
        self.assertEqual(len([p for p in self.f.posts if not p["buttons"]]), 1)
        blob = json.dumps(self.cards()[0]["embed"], ensure_ascii=False)
        self.assertIn(engine.SOAK_NAME, blob)
        self.assertIn(engine.SOAK_TEXT, blob)
        self.now = at(14, 1)
        run(flow.tick())
        self.now = at(16, 30)
        rep = run(flow.tick())
        self.assertEqual(rep["live"], 0)
        self.assertEqual(rep["alerts"], 0)
        self.assertEqual(self.f.escalations, [])
        it = db.get("r1")
        self.assertIsNone(it["alert_2h_at"])
        self.assertIsNone(it["alert_late_at"])

    def test_soak_refreshes_quoted_replies(self):
        run(flow.tick())
        self.f.msgs["c-r1"].append({"inbound": True, "at": at(9, 10), "body": "see you"})
        self.now = at(9, 20)
        run(flow.tick())
        self.assertIn("see you", json.dumps(self.f.edits[-1]["embed"], ensure_ascii=False))

    def test_soak_press_is_recorded_without_honesty_check(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        calls = []
        flow.HOST.code_sent = lambda cid: calls.append(cid) or False
        self.now = at(13)
        ok, _ = run(flow.press_release(mid, {"name": "نورة", "did": "11",
                                             "is_admin": False, "is_ops": False}))
        self.assertTrue(ok)
        self.assertIn(engine.SOAK_NAME, json.dumps(self.f.edits[-1]["embed"], ensure_ascii=False))
        self.now = at(13, 30)
        run(flow.tick())
        self.assertEqual(calls, [])
        self.assertIsNone(db.get("r1")["code_seen"])
        self.assertIsNone(db.get("r1")["code_check_at"])
        self.assertFalse(any(p["text"] and "ما شفت" in p["text"] for p in self.f.posts))

    def test_flip_live_then_next_tick_alerts_normally(self):
        run(flow.tick())
        self.now = at(14, 1)
        run(flow.tick())
        self.assertEqual(self.f.escalations, [])
        flow.set_live(True, "Faisal")
        self.assertTrue(flow.live())
        self.now = at(14, 11)
        rep = run(flow.tick())
        self.assertEqual(rep["live"], 1)
        self.assertEqual(len(self.f.escalations), 1)
        self.assertTrue(db.get("r1")["alert_2h_at"])
        self.assertNotIn(engine.SOAK_NAME,
                         json.dumps(self.f.edits[-1]["embed"], ensure_ascii=False))

    def test_switch_survives_restart_and_turns_off(self):
        flow.set_live(True, "Faisal")
        flow._live_cache.update({"v": None, "at": 0.0})    # simulated redeploy
        db.reset_init_cache()
        self.assertTrue(flow.live())
        flow.set_live(False, "Faisal")
        self.assertFalse(flow.live())
        self.assertEqual(db.get_setting("live"), "0")


class TestMovedBooking(FlowCase):
    """I2: a booking moved to another date starts over — new card, fresh alerts."""

    def test_moved_booking_gets_new_card_and_alerts(self):
        self.now = at(14, 30)
        run(flow.tick())
        self.assertEqual(len(self.f.escalations), 1)
        old_mid = db.get("r1")["card_message_id"]
        nxt = "2026-10-22"
        self.f.arrivals = [dict(self.f.arr("r1", GATED), day=nxt,
                                checkin_at=nxt + "T16:00:00+03:00")]
        self.now = datetime.datetime(2026, 10, 22, 14, 30, tzinfo=TZ)
        self.f.edits.clear()
        run(flow.tick())
        it = db.get("r1")
        self.assertEqual(it["day"], nxt)
        self.assertNotEqual(it["card_message_id"], old_mid)
        self.assertTrue(it["alert_2h_at"].startswith(nxt))
        self.assertEqual(len(self.f.escalations), 2)
        self.assertEqual(self.f.edits, [])           # no edit of the old day's card
        self.assertEqual(self.asked_days[-1], nxt)


class TestCodeCheckErrors(FlowCase):
    """I3: a Hostaway error is not "no code"."""

    def test_code_check_error_retries_without_warning(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        self.now = at(13)
        run(flow.press_release(mid, {"name": "نورة", "did": "11",
                                     "is_admin": False, "is_ops": False}))

        def boom(cid):
            raise RuntimeError("hostaway 500")
        flow.HOST.code_sent = boom
        self.now = at(13, 20)
        run(flow.tick())
        it = db.get("r1")
        self.assertIsNone(it["code_seen"])
        self.assertIsNone(it["code_check_at"])
        self.assertFalse(any(p["text"] and "ما شفت" in p["text"] for p in self.f.posts))
        flow.HOST.code_sent = lambda cid: True          # Hostaway back: checked normally
        self.now = at(13, 30)
        run(flow.tick())
        self.assertEqual(db.get("r1")["code_seen"], 1)

    def test_messages_error_keeps_stored_replies(self):
        run(flow.tick())

        def boom(cid):
            raise RuntimeError("hostaway 500")
        flow.HOST.messages = boom
        self.now = at(9, 20)
        run(flow.tick())
        self.assertEqual(db.get("r1")["replies"][0]["text"], "I agree")
        self.assertEqual(self.f.edits, [])


class TestTickDay(FlowCase):
    def test_tick_passes_its_own_day(self):
        run(flow.tick())
        self.assertEqual(self.asked_days, [DAY])




class TestGoLive(FlowCase):
    """Turning live ON mid-day: arrivals Hostaway's Doorcodera already covers (check-in within
    live_since + 3 h) are looked at ONCE in the chat; a code there means no false alert."""
    LIVE = False

    def setUp(self):
        super().setUp()
        self.f.arrivals = [self.mk("r1", "U-past", 13, 0), self.mk("r2", "U-inside", 16, 30),
                           self.mk("r3", "U-outside", 20, 0)]
        self.fetches = []                      # every HOST.messages call = one Hostaway fetch
        self.boom = set()
        self.honesty_calls = []
        self.give_code("c-r1")
        self.give_code("c-r3")

        def messages(cid):
            self.fetches.append(cid)
            if cid in self.boom:
                raise RuntimeError("hostaway 500")
            return list(self.f.msgs.get(cid, []))
        flow.HOST.messages = messages
        flow.HOST.code_sent = lambda cid: self.honesty_calls.append(cid) or True
        run(flow.tick())                       # soak morning: cards only
        self.now = at(15, 0)
        flow.set_live(True, "Faisal")          # live_since = 15:00 → window ends 18:00
        self.fetches.clear()

    def give_code(self, cid):
        self.f.msgs.setdefault(cid, []).append(
            {"inbound": False, "at": at(12), "body": CODE_WORD})

    def take_code(self, cid):
        self.f.msgs[cid] = [m for m in self.f.msgs[cid] if m["body"] != CODE_WORD]

    def mk(self, rid, unit, hh, mm):
        a = Fake.arr(rid, GATED)
        a.update(unit=unit, checkin_at=at(hh, mm).isoformat(timespec="seconds"))
        return a

    def esc_units(self):
        return [t for t in self.f.escalations]

    def test_code_found_releases_quietly_and_card_turns_green(self):
        run(flow.tick())
        it = db.get("r1")
        self.assertEqual(it["released_by"], "Hostaway (قبل التشغيل)")
        self.assertEqual(it["released_by_did"], "")
        self.assertTrue(it["released_at"])
        self.assertEqual(it["code_seen"], 1)
        self.assertTrue(it["prelive_checked_at"])
        self.assertIsNone(it["alert_late_at"])
        self.assertIsNone(it["alert_2h_at"])
        self.assertFalse(any("U-past" in t for t in self.esc_units()))
        self.assertFalse(any("U-past" in (p["text"] or "") for p in self.f.posts))
        self.assertIn("prelive_auto", [e["kind"] for e in db._q(
            "SELECT kind FROM codegate_events WHERE res_id='r1'")])
        mine = [e for e in self.f.edits if e["id"] == it["card_message_id"]]
        self.assertEqual(len(mine), 1)
        self.assertIn("Hostaway (قبل التشغيل)", json.dumps(mine[0]["embed"], ensure_ascii=False))
        self.assertEqual(mine[0]["buttons"], ["undo"])

    def test_no_code_in_window_alerts_normally_at_the_right_time(self):
        rep = run(flow.tick())
        self.assertEqual(rep["alerts"], 1)
        self.assertEqual(len(self.f.escalations), 1)
        self.assertIn("U-inside", self.f.escalations[0])
        self.assertIn("باقي ساعتين", self.f.escalations[0])
        it = db.get("r2")
        self.assertTrue(it["alert_2h_at"])
        self.assertTrue(it["prelive_checked_at"])
        self.assertIsNone(it["released_at"])

    def test_outside_window_untouched_until_its_own_2h_mark(self):
        run(flow.tick())
        self.assertIsNone(db.get("r3")["prelive_checked_at"])
        self.now = at(17, 59)
        run(flow.tick())
        self.assertFalse(any("U-outside" in t for t in self.f.escalations))
        self.now = at(18, 1)
        run(flow.tick())
        self.assertTrue(any("U-outside" in t for t in self.f.escalations))
        self.assertIsNone(db.get("r3")["prelive_checked_at"])      # still never looked at

    def test_each_item_checked_once_with_no_extra_hostaway_call(self):
        called = []
        real = flow.HOST.code_in
        flow.HOST.code_in = lambda msgs: called.append(1) or real(msgs)
        for m in (0, 10, 20, 30):
            self.now = at(15, m)
            run(flow.tick())
        self.assertEqual(len(called), 2)                   # r1 and r2, once each
        self.assertEqual(self.honesty_calls, [])           # the chat is NOT asked for again
        self.assertEqual(self.fetches.count("c-r1"), 4)    # one fetch per tick, as always
        self.assertEqual(len(self.f.escalations), 1)       # r2's 2h alert, once

    def test_error_means_no_alert_this_tick_and_retry_next(self):
        self.boom = {"c-r2"}                 # the message FETCH fails
        rep = run(flow.tick())
        self.assertEqual(rep["alerts"], 0)
        self.assertEqual(self.f.escalations, [])
        it = db.get("r2")
        self.assertIsNone(it["prelive_checked_at"])
        self.assertIsNone(it["alert_2h_at"])
        self.assertIsNone(it["alert_late_at"])
        self.now = at(15, 10)
        run(flow.tick())
        self.assertEqual(self.fetches.count("c-r2"), 2)     # retried
        self.assertIsNone(db.get("r2")["prelive_checked_at"])
        self.assertEqual(self.f.escalations, [])
        self.boom = set()
        self.now = at(15, 20)
        run(flow.tick())
        self.assertEqual(len(self.f.escalations), 1)
        self.assertTrue(db.get("r2")["prelive_checked_at"])
        self.now = at(15, 30)
        run(flow.tick())
        called = []
        real = flow.HOST.code_in
        flow.HOST.code_in = lambda msgs: called.append(1) or real(msgs)
        self.now = at(15, 40)
        run(flow.tick())
        self.assertEqual(called, [])                         # then never again

    def test_press_before_the_check_wins_and_is_kept(self):
        mid = db.get("r2")["card_message_id"]
        ok, _ = run(flow.press_release(mid, {"name": "نورة", "did": "11",
                                             "is_admin": False, "is_ops": False}))
        self.assertTrue(ok)
        self.give_code("c-r2")
        run(flow.tick())
        self.assertEqual(db.get("r2")["released_by"], "نورة")
        self.assertEqual(self.f.escalations, [])

    def test_press_landing_during_the_check_wins(self):
        """A staff press lands while the chat is being read: first press wins, the honesty
        check is still owed to it, nothing alerts, and no prelive_auto event is written."""
        real = flow.HOST.code_in

        def code_in(msgs):
            db.release("r1", "نورة", "11", at(15, 0).isoformat(timespec="seconds"))
            return real(msgs)
        flow.HOST.code_in = code_in
        rep = run(flow.tick())
        it = db.get("r1")
        self.assertEqual(it["released_by"], "نورة")
        self.assertEqual(it["released_by_did"], "11")
        self.assertIsNone(it["code_seen"])              # honesty check still applies
        self.assertTrue(it["prelive_checked_at"])
        self.assertEqual(rep["prelive"], 0)
        self.assertFalse(any("U-past" in t for t in self.f.escalations))
        self.assertNotIn("prelive_auto", [e["kind"] for e in db._q(
            "SELECT kind FROM codegate_events WHERE res_id='r1'")])

    def test_rollback_then_go_live_again_rechecks(self):
        """15:00 live, r2 has no code (checked, 2h alert). Rollback, Doorcodera sends the code,
        live again at 16:00: the 15:00 check is stale — r2 is looked at again, found, released."""
        run(flow.tick())
        first = db.get("r2")["prelive_checked_at"]
        self.assertTrue(first)
        self.assertEqual(len(self.f.escalations), 1)
        flow.set_live(False, "Faisal")
        self.give_code("c-r2")
        self.now = at(16, 0)
        flow.set_live(True, "Faisal")
        self.now = at(16, 40)
        run(flow.tick())
        it = db.get("r2")
        self.assertEqual(it["released_by"], "Hostaway (قبل التشغيل)")
        self.assertIsNone(it["alert_late_at"])
        self.assertEqual(len(self.f.escalations), 1)    # still only the first 2h alert
        self.assertGreater(it["prelive_checked_at"], first)
        self.now = at(16, 50)                            # and only once for this go-live
        called = []
        real = flow.HOST.code_in
        flow.HOST.code_in = lambda msgs: called.append(1) or real(msgs)
        run(flow.tick())
        self.assertEqual(called, [])

    def test_live_since_set_on_off_to_on_and_kept_on_on_to_on(self):
        first = db.get_setting("live_since")
        self.assertEqual(first, at(15, 0).isoformat(timespec="seconds"))
        self.now = at(16, 0)
        flow.set_live(True, "again")
        self.assertEqual(db.get_setting("live_since"), first)

    def test_off_then_on_again_restarts_the_window(self):
        first = db.get_setting("live_since")
        flow.set_live(False, "Faisal")
        self.assertEqual(db.get_setting("live_since"), first)    # OFF keeps it (documented)
        self.now = at(17, 0)
        flow.set_live(True, "Faisal")
        self.assertEqual(db.get_setting("live_since"), at(17, 0).isoformat(timespec="seconds"))

    def test_no_live_since_means_no_prelive_check(self):
        db.set_setting("live_since", None)
        run(flow.tick())
        self.assertIsNone(db.get("r1")["prelive_checked_at"])
        self.assertEqual(len(self.f.escalations), 2)        # r1 late + r2 2h, as before


if __name__ == "__main__":
    unittest.main()
