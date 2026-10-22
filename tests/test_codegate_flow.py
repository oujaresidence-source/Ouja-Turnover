# tests/test_codegate_flow.py
# -*- coding: utf-8 -*-
"""«تسليم الرموز» flow against a fake Discord + fake Hostaway, a temp brain.db, injected now.
Run: python3 -m unittest tests.test_codegate_flow"""
import asyncio
import contextlib
import datetime
import io
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
GATED2 = 526697                     # a second gated unit (no turnover room in the fake)
CODE_WORD = "كود الدخول 4821"       # what the fake code_in treats as "the code message"
ROOM = "room-T"                     # the gated unit's turnover room in the fake


def at(hh, mm=0):
    return datetime.datetime(2026, 10, 21, hh, mm, tzinfo=TZ)


def run(c):
    return asyncio.run(c)


class Fake:
    def __init__(self):
        self.posts, self.edits, self.escalations = [], [], []
        self.rooms = {(GATED, DAY): ROOM}           # (lid, day) -> turnover room
        self.departures = set()
        self.departure_calls = []
        self.code_rooms, self.deleted, self.reviews, self.sends = [], [], [], []
        self.send_result = (True, "sent")
        self.create_ok = True
        self.delete_ok = True                       # False = Discord error (retry)
        self.gone = set()                           # rooms already deleted by hand
        self.gone_hits = []
        self.delete_calls = 0
        self.edit_ok = True
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
        self.posts.append({"id": str(self._mid), "ch": ch, "text": text, "embed": embed,
                           "buttons": buttons})
        return str(self._mid)

    async def edit(self, ch, mid, embed=None, buttons=None):
        self.edits.append({"id": mid, "ch": ch, "embed": embed, "buttons": buttons})
        return self.edit_ok

    async def escalate(self, title, detail):
        self.escalations.append(title)

    def find_room(self, lid, day):
        return self.rooms.get((int(lid), day))

    def departures_today(self, day):
        self.departure_calls.append(day)
        return set(self.departures)

    async def create_code_room(self, item):
        if not self.create_ok:
            return None
        ch = "code-%s-%d" % (item["res_id"], len(self.code_rooms) + 1)
        self.code_rooms.append(ch)
        return ch

    def send_code(self, res_id, conversation_id):
        self.sends.append(res_id)
        if isinstance(self.send_result, Exception):
            raise self.send_result
        return self.send_result

    async def delete_room(self, channel_id, reason):
        """The R2 contract: True when deleted OR already gone (NotFound); False = error."""
        self.delete_calls += 1
        if channel_id in self.gone:
            self.gone_hits.append((channel_id, reason))
            return True
        if not self.delete_ok:
            return False
        self.deleted.append((channel_id, reason))
        return True

    async def log_review(self, text):
        self.reviews.append(text)


class FlowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cgf_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        units = os.path.join(self.tmp, "codegate_units.json")
        with open(units, "w") as fh:
            json.dump({"listing_ids": [GATED, GATED2]}, fh)
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
            "post": self.f.post, "edit": self.f.edit, "escalate": self.f.escalate,
            "find_room": self.f.find_room, "departures_today": self.f.departures_today,
            "create_code_room": self.f.create_code_room, "send_code": self.f.send_code,
            "delete_room": self.f.delete_room, "log_review": self.f.log_review,
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
        return [p for p in self.f.posts if p["embed"]]

    def texts(self):
        return [p for p in self.f.posts if not p["embed"]]

    @staticmethod
    def p(did="11", admin=False, ops=False, name="نورة"):
        return {"name": name, "did": did, "is_admin": admin, "is_ops": ops}


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

    def test_card_mentions_coverer_and_no_header(self):
        run(flow.tick())
        self.assertEqual(self.texts(), [])                 # no per-person header any more
        self.assertEqual(self.cards()[0]["text"], "<@11>")

    def test_tick_twice_and_restart_is_idempotent(self):
        run(flow.tick())
        db.reset_init_cache()                              # simulated redeploy
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
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

    def test_coverer_manual_card_turns_green(self):
        ok, msg = run(flow.press_manual(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(self.f.edits[-1]["embed"]["color"], engine.COLOR_DONE)
        self.assertEqual(self.f.edits[-1]["buttons"], ["undo"])
        self.assertEqual(db.get("r1")["released_by"], "نورة")
        self.assertEqual(self.f.sends, [])                 # manual = the bot sends nothing

    def test_stranger_refused(self):
        for press in (flow.press_send, flow.press_manual):
            ok, msg = run(press(self.mid, self.p(did="77", name="x")))
            self.assertFalse(ok)
            self.assertIn("نورة", msg)
        self.assertIsNone(db.get("r1")["released_at"])
        self.assertEqual(self.f.sends, [])

    def test_double_press_first_wins(self):
        run(flow.press_manual(self.mid, self.p()))
        ok, msg = run(flow.press_manual(self.mid, self.p(did="22", name="ناصر")))
        self.assertFalse(ok)
        self.assertIn("أُرسل من قبل", msg)

    def test_unknown_message(self):
        for press in (flow.press_send, flow.press_manual):
            ok, msg = run(press("424242", self.p()))
            self.assertFalse(ok)

    def test_release_alias_is_manual(self):
        """bot.py (revision 1) still calls press_release until R3 rewires the view."""
        self.assertIs(flow.press_release, flow.press_manual)

    def test_release_stops_alerts(self):
        run(flow.press_manual(self.mid, self.p()))
        self.now = at(16, 30)
        run(flow.tick())
        self.assertEqual(self.f.escalations, [])

    def test_honesty_warning_when_code_not_seen(self):
        self.now = at(13)
        run(flow.press_manual(self.mid, self.p()))
        self.now = at(13, 20)
        run(flow.tick())
        warns = [p for p in self.f.posts if p["text"] and "ما شفت رسالة الرمز" in p["text"]]
        self.assertEqual(len(warns), 1)
        self.assertIn("<@11>", warns[0]["text"])
        self.assertEqual(warns[0]["ch"], ROOM)              # into the card's room
        run(flow.tick())
        self.assertEqual(len([p for p in self.f.posts
                              if p["text"] and "ما شفت رسالة الرمز" in p["text"]]), 1)

    def test_no_warning_when_code_seen(self):
        self.now = at(13)
        run(flow.press_manual(self.mid, self.p()))
        self.f.code["c-r1"] = True
        self.now = at(13, 20)
        run(flow.tick())
        self.assertEqual(db.get("r1")["code_seen"], 1)
        self.assertFalse(any(p["text"] and "ما شفت" in p["text"] for p in self.f.posts))

    def test_undo_admin_only(self):
        run(flow.press_manual(self.mid, self.p()))
        ok, _ = run(flow.press_undo(self.mid, self.p()))
        self.assertFalse(ok)
        ok, msg = run(flow.press_undo(self.mid, self.p(did="5", admin=True, name="Faisal")))
        self.assertTrue(ok)
        self.assertIn("صححت السجل — الرسالة اللي انرسلت ما تنحذف.", msg)
        self.assertIsNone(db.get("r1")["released_at"])
        self.assertEqual(self.f.edits[-1]["buttons"], ["send", "manual"])


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

    def test_failed_card_post_is_retried(self):
        real = self.f.post
        state = {"n": 0}

        async def post(ch, text, embed=None, buttons=None):
            state["n"] += 1
            if state["n"] == 1:
                return None
            return await real(ch, text, embed=embed, buttons=buttons)
        flow.HOST.post = post
        run(flow.tick())
        self.assertEqual(self.cards(), [])
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)

    def test_release_during_alert_is_not_followed_by_alert_or_red_card(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        self.now = at(14, 1)
        real = self.f.escalate

        async def escalate(title, detail):
            await real(title, detail)
            await flow.press_manual(mid, {"name": "نورة", "did": "11",
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


class TestPressEdges(FlowCase):
    def test_press_on_cancelled_booking_refused(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        self.f.arrivals = []
        self.now = at(10)
        run(flow.tick())
        for press in (flow.press_send, flow.press_manual):
            ok, msg = run(press(mid, self.p()))
            self.assertFalse(ok)
            self.assertIn("ملغي", msg)
        self.assertIsNone(db.get("r1")["released_at"])
        self.assertEqual(self.f.sends, [])

    def test_press_after_redeploy_still_works(self):
        run(flow.tick())
        mid = self.cards()[0]["id"]
        db.reset_init_cache()
        ok, _ = run(flow.press_manual(mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(db.get("r1")["released_by"], "نورة")


class TestSoak(FlowCase):
    """C1/I1: while Hostaway still runs the old e-sign flow, the list runs but nothing alerts."""
    LIVE = False

    def test_default_is_soak(self):
        self.assertFalse(flow.live())

    def test_soak_posts_cards_only(self):
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
        self.assertEqual(self.texts(), [])
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
        ok, _ = run(flow.press_manual(mid, {"name": "نورة", "did": "11",
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
        run(flow.press_manual(mid, {"name": "نورة", "did": "11",
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
        ok, _ = run(flow.press_manual(mid, {"name": "نورة", "did": "11",
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


def quiet(fn, *a, **k):
    """Run fn with the package's expected failure prints swallowed (pristine test output)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


class TestPlacement(FlowCase):
    """R2: the card lives in the unit's turnover room; a code-only room only when none comes."""

    def test_card_goes_into_turnover_room(self):
        run(flow.tick())
        card = self.cards()[0]
        self.assertEqual(card["ch"], ROOM)
        self.assertEqual(card["buttons"], ["send", "manual"])
        it = db.get("r1")
        self.assertEqual((it["channel_id"], it["room_kind"]), (ROOM, "turnover"))
        self.assertEqual(self.f.code_rooms, [])
        self.assertEqual(self.f.departure_calls, [])    # nobody needed a fallback

    def test_code_room_when_no_departure(self):
        self.f.rooms = {}
        self.f.arrivals = [self.f.arr("r1", GATED), self.f.arr("r2", GATED2)]
        run(flow.tick())
        self.assertEqual(self.f.code_rooms, ["code-r1-1", "code-r2-2"])
        self.assertEqual(self.f.departure_calls, [DAY])  # once per tick, not per item
        self.assertEqual({c["ch"] for c in self.cards()}, {"code-r1-1", "code-r2-2"})
        self.assertEqual(db.get("r1")["room_kind"], "code")
        run(flow.tick())                                  # placed: no second room
        self.assertEqual(len(self.f.code_rooms), 2)
        self.assertEqual(len(self.cards()), 2)

    def test_waits_for_late_turnover_room(self):
        """Checkout after 21:00: the turnover room opens after 09:00. No code room meanwhile."""
        self.f.rooms = {}
        self.f.departures = {GATED}
        run(flow.tick())
        self.now = at(11, 0)
        run(flow.tick())
        self.assertEqual(self.cards(), [])
        self.assertEqual(self.f.code_rooms, [])
        self.f.rooms = {(GATED, DAY): ROOM}               # the turnover room appears
        self.now = at(12, 0)
        run(flow.tick())
        self.assertEqual([c["ch"] for c in self.cards()], [ROOM])
        self.assertEqual(self.f.code_rooms, [])

    def test_fallback_code_room_at_2h(self):
        self.f.rooms = {}
        self.f.departures = {GATED}
        self.now = at(13, 59)
        run(flow.tick())
        self.assertEqual(self.f.code_rooms, [])
        self.assertEqual(self.f.escalations, [])
        self.now = at(14, 0)
        run(flow.tick())
        self.assertEqual(self.f.code_rooms, ["code-r1-1"])
        self.assertEqual([c["ch"] for c in self.cards()], ["code-r1-1"])
        alerts = [p for p in self.texts() if "باقي ساعتين" in (p["text"] or "")]
        self.assertEqual([a["ch"] for a in alerts], ["code-r1-1"])   # the alert is in the room
        self.assertEqual(len(self.f.escalations), 1)

    def test_departure_lookup_error_waits_until_fallback(self):
        self.f.rooms = {}

        def boom(day):
            raise RuntimeError("hostaway 500")
        flow.HOST.departures_today = boom
        quiet(run, flow.tick())
        self.assertEqual(self.f.code_rooms, [])           # unknown ≠ "no departure"
        self.now = at(14, 0)
        quiet(run, flow.tick())
        self.assertEqual(self.f.code_rooms, ["code-r1-1"])

    def test_code_room_failure_retried(self):
        self.f.rooms = {}
        self.f.create_ok = False
        run(flow.tick())
        self.assertEqual(self.cards(), [])
        self.assertIsNone(db.get("r1")["channel_id"])
        self.f.create_ok = True
        self.now = at(9, 20)
        run(flow.tick())
        self.assertEqual([c["ch"] for c in self.cards()], ["code-r1-1"])

    def test_alerts_post_into_room(self):
        self.f.arrivals = [self.f.arr("r1", GATED), self.f.arr("r2", GATED2)]
        self.f.create_ok = False                          # r2 can't get a room
        self.now = at(14, 1)
        run(flow.tick())
        alerts = [p for p in self.texts() if "باقي ساعتين" in (p["text"] or "")]
        self.assertEqual([a["ch"] for a in alerts], [ROOM])           # r1, in its room
        self.assertEqual(len(self.f.escalations), 2)                  # r2 still escalates
        self.assertTrue(any("U%s" % GATED2 in t for t in self.f.escalations))


class TestSoakR2(FlowCase):
    LIVE = False

    def test_soak_only_existing_turnover_rooms_no_buttons(self):
        self.f.arrivals = [self.f.arr("r1", GATED), self.f.arr("r2", GATED2)]
        run(flow.tick())
        self.assertEqual([c["ch"] for c in self.cards()], [ROOM])
        self.assertEqual(self.cards()[0]["buttons"], [])
        self.assertIn(engine.SOAK_NAME, json.dumps(self.cards()[0]["embed"], ensure_ascii=False))
        self.now = at(14, 30)
        run(flow.tick())
        self.now = at(16, 30)
        run(flow.tick())
        self.assertEqual(self.f.code_rooms, [])           # no code-only room in soak
        self.assertEqual(self.f.departure_calls, [])
        self.assertEqual(self.f.escalations, [])
        self.assertEqual(self.texts(), [])
        self.assertIsNone(db.get("r2")["channel_id"])
        self.assertFalse(flow.should_hold(GATED, DAY))    # no holds in soak
        ok, msg = run(flow.press_send(self.cards()[0]["id"], self.p()))
        self.assertFalse(ok)                              # Hostaway still auto-sends
        self.assertEqual(self.f.sends, [])
        self.assertIsNone(db.get("r1")["released_at"])

    def test_lost_card_dropped_in_soak(self):
        run(flow.tick())
        self.f.edit_ok = False
        self.f.msgs["c-r1"].append({"inbound": True, "at": at(9, 10), "body": "see you"})
        self.now = at(9, 20)
        run(flow.tick())
        self.assertEqual(db.get("r1")["channel_id"], ROOM)
        self.f.rooms = {}
        self.now = at(9, 30)
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
        self.assertEqual(self.f.code_rooms, [])


class TestSend(FlowCase):
    def setUp(self):
        super().setUp()
        self.f.rooms = {}                                 # vacant last night: code-only room
        run(flow.tick())
        self.mid = self.cards()[0]["id"]
        self.room = "code-r1-1"
        self.hash0 = db.get("r1")["card_hash"]

    def test_send_success_records_green_and_deletes_code_room(self):
        self.now = at(12, 7)
        ok, msg = run(flow.press_send(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(msg, "تم ✅ — أرسلت الرمز للضيف.")
        self.assertEqual(self.f.sends, ["r1"])
        it = db.get("r1")
        self.assertEqual((it["released_by"], it["sent_by_bot"], it["code_seen"]), ("نورة", 1, 1))
        self.assertEqual(self.f.edits[-1]["embed"]["color"], engine.COLOR_DONE)
        self.assertEqual(self.f.deleted, [(self.room, "codegate: code sent")])
        self.assertEqual(len(self.f.reviews), 1)
        line = self.f.reviews[0]
        for part in ("🔑 أُرسل الرمز", "U%s" % GATED, "Gr1", "نورة", "12:07"):
            self.assertIn(part, line)
        self.assertIsNone(it["channel_id"])
        kinds = [e["kind"] for e in db._q("SELECT kind FROM codegate_events WHERE res_id='r1'")]
        self.assertIn("code_sent_bot", kinds)
        self.now = at(16, 30)                             # nothing re-posted, nothing alerted
        run(flow.tick())
        self.assertEqual(len(self.cards()), 1)
        self.assertEqual(self.f.escalations, [])
        self.assertEqual(len(self.f.deleted), 1)

    def test_send_empty_code_refuses_and_records_nothing(self):
        self.f.send_result = (False, "no_code")
        ok, msg = run(flow.press_send(self.mid, self.p()))
        self.assertFalse(ok)
        self.assertIn("Hostaway ما فيه رمز لهذا الحجز", msg)
        self.assertIn(engine.LABEL_MANUAL, msg)
        it = db.get("r1")
        self.assertIsNone(it["released_at"])
        self.assertIsNone(it["released_by"])
        self.assertFalse(it["sent_by_bot"])
        self.assertEqual(self.f.deleted, [])
        # release → undo leaves the card exactly as it was: never repainted, hash unchanged
        self.assertEqual([e for e in self.f.edits if e["id"] == self.mid], [])
        self.assertEqual(it["card_hash"], self.hash0)
        self.assertEqual(flow._buttons(it, True), ["send", "manual"])
        ok, _ = run(flow.press_manual(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(db.get("r1")["released_by"], "نورة")
        self.assertEqual(self.f.deleted, [])              # manual: wait for the honesty check

    def test_send_failure_undoes_release(self):
        cases = [((False, "killed"), "مفتاح الإيقاف"),
                 ((False, "duplicate"), "ما أرسلتها مرتين"),
                 ((False, "error"), "Hostaway ما رد"),
                 ((False, "something new"), "Hostaway ما رد"),
                 (RuntimeError("boom"), "Hostaway ما رد"),
                 (None, "Hostaway ما رد")]
        for result, want in cases:
            with self.subTest(result=result):
                self.f.send_result = result
                ok, msg = quiet(run, flow.press_send(self.mid, self.p()))
                self.assertFalse(ok)
                self.assertIn(want, msg)
                it = db.get("r1")
                self.assertIsNone(it["released_at"])
                self.assertFalse(it["sent_by_bot"])
        self.assertEqual(self.f.deleted, [])
        kinds = [e["kind"] for e in db._q("SELECT kind FROM codegate_events WHERE res_id='r1'")]
        self.assertEqual(kinds.count("code_send_failed"), len(cases))
        self.now = at(14, 1)                              # still waiting: the alert still fires
        run(flow.tick())
        self.assertEqual(len(self.f.escalations), 1)

    def test_send_double_press_one_send(self):
        async def both():
            return await asyncio.gather(flow.press_send(self.mid, self.p()),
                                        flow.press_send(self.mid, self.p(did="22", name="ناصر")))
        res = run(both())
        self.assertEqual(sorted(ok for ok, _ in res), [False, True])
        self.assertIn("أُرسل من قبل", [m for ok, m in res if not ok][0])
        ok, msg = run(flow.press_send(self.mid, self.p()))
        self.assertFalse(ok)
        self.assertEqual(self.f.sends, ["r1"])

    def test_manual_records_then_honesty_deletes_code_room(self):
        self.now = at(13)
        ok, _ = run(flow.press_manual(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(self.f.sends, [])
        self.now = at(13, 10)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [])              # not checked yet
        self.f.code["c-r1"] = True
        self.now = at(13, 20)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(self.room, "codegate: code sent")])
        self.assertEqual(len(self.f.reviews), 1)
        self.assertIn("نورة", self.f.reviews[0])
        run(flow.tick())
        self.assertEqual(len(self.f.deleted), 1)

    def test_manual_without_code_keeps_room(self):
        self.now = at(13)
        run(flow.press_manual(self.mid, self.p()))
        self.now = at(13, 20)
        run(flow.tick())                                  # honesty check: no code
        self.assertEqual(self.f.deleted, [])
        self.assertEqual(db.get("r1")["code_seen"], 0)

    def test_audit_line_on_every_delete(self):
        """A successful delete writes exactly one audit line; a failed one writes none, never
        raises, and is retried by the tick."""
        self.f.arrivals = [self.f.arr("r1", GATED), self.f.arr("r2", GATED2)]
        run(flow.tick())
        mid2 = db.get("r2")["card_message_id"]
        ok, _ = run(flow.press_send(mid2, self.p()))       # immediate success
        self.assertTrue(ok)
        self.assertEqual(self.f.deleted, [("code-r2-2", "codegate: code sent")])
        self.assertEqual(len(self.f.reviews), 1)
        self.assertIn("U%s" % GATED2, self.f.reviews[0])
        self.f.deleted.clear()
        self.f.reviews.clear()
        self.f.delete_ok = False
        ok, _ = quiet(run, flow.press_send(self.mid, self.p()))
        self.assertTrue(ok)                               # the code WAS sent
        self.assertEqual(self.f.reviews, [])
        self.assertEqual(db.get("r1")["channel_id"], self.room)
        self.f.delete_ok = True
        self.now = at(9, 20)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(self.room, "codegate: code sent")])
        self.assertEqual(len(self.f.reviews), len(self.f.deleted))

    def test_undo_after_bot_send_only_corrects_record(self):
        run(flow.press_send(self.mid, self.p()))
        ok, msg = run(flow.press_undo(self.mid, self.p(did="5", admin=True, name="Faisal")))
        # the room (and so the card) is gone after a bot send: nothing to undo from
        self.assertFalse(ok)
        self.assertEqual(self.f.sends, ["r1"])


class TestHoldAndClose(FlowCase):
    def setUp(self):
        super().setUp()
        run(flow.tick())
        self.mid = self.cards()[0]["id"]

    def test_pending_close_runs_after_send(self):
        self.assertTrue(flow.should_hold(GATED, DAY))
        flow.defer_close(GATED, DAY)
        self.assertEqual(db.get("r1")["room_close_pending"], 1)
        self.now = at(15, 3)
        ok, _ = run(flow.press_send(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(self.f.deleted, [(ROOM, "codegate: code sent")])
        self.assertEqual(db.get("r1")["room_close_pending"], 0)
        self.assertEqual(len(self.f.reviews), 1)
        self.assertIn("15:03", self.f.reviews[0])

    def test_turnover_room_not_deleted_without_pending(self):
        ok, _ = run(flow.press_send(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(self.f.deleted, [])
        self.assertEqual(self.f.reviews, [])
        self.assertFalse(flow.should_hold(GATED, DAY))    # sent: cleaning may delete it
        run(flow.tick())
        self.assertEqual(self.f.deleted, [])

    def test_pending_close_after_manual_waits_for_honesty(self):
        flow.defer_close(GATED, DAY)
        self.now = at(13)
        run(flow.press_manual(self.mid, self.p()))
        self.assertEqual(self.f.deleted, [])
        self.f.code["c-r1"] = True
        self.now = at(13, 20)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(ROOM, "codegate: code sent")])

    def test_held_room_closed_when_booking_cancelled(self):
        flow.defer_close(GATED, DAY)
        self.f.arrivals = []
        self.now = at(11)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(ROOM, "codegate: booking cancelled")])
        self.assertEqual(len(self.f.reviews), 1)

    def test_held_room_closed_next_day_without_code(self):
        flow.defer_close(GATED, DAY)
        self.f.arrivals = []
        self.now = datetime.datetime(2026, 10, 22, 9, 5, tzinfo=TZ)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(ROOM, "codegate: day over")])
        self.assertEqual(len(self.f.reviews), 1)

    def test_unheld_turnover_room_never_swept(self):
        self.f.arrivals = []
        self.now = at(11)
        run(flow.tick())                                  # cancelled, not held
        self.now = datetime.datetime(2026, 10, 22, 9, 5, tzinfo=TZ)
        run(flow.tick())                                  # day over, not held
        self.assertEqual(self.f.deleted, [])

    def test_should_hold_matrix(self):
        self.assertTrue(flow.should_hold(GATED, DAY))
        self.assertTrue(flow.should_hold(str(GATED), DAY))
        self.assertFalse(flow.should_hold(OPEN, DAY))       # not gated
        self.assertFalse(flow.should_hold(GATED2, DAY))     # gated, but no arrival today
        self.assertFalse(flow.should_hold(GATED, "2026-10-22"))
        self.assertFalse(flow.should_hold(None, DAY))
        flow.set_live(False, "t")
        self.assertFalse(flow.should_hold(GATED, DAY))      # soak
        flow.set_live(True, "t")
        real = flow.db.items_for

        def boom(lid, day):
            raise RuntimeError("db locked")
        flow.db.items_for = boom
        try:
            self.assertFalse(quiet(flow.should_hold, GATED, DAY))   # never raises
        finally:
            flow.db.items_for = real
        run(flow.press_manual(self.mid, self.p()))
        self.assertFalse(flow.should_hold(GATED, DAY))      # released
        db.undo("r1", "t", "t")
        self.assertTrue(flow.should_hold(GATED, DAY))
        self.f.arrivals = []
        self.now = at(10)
        run(flow.tick())
        self.assertFalse(flow.should_hold(GATED, DAY))      # cancelled

    def test_lost_card_reposted_when_live(self):
        self.f.edit_ok = False
        self.f.msgs["c-r1"].append({"inbound": True, "at": at(9, 10), "body": "see you"})
        self.now = at(9, 20)
        run(flow.tick())
        it = db.get("r1")
        self.assertIsNone(it["channel_id"])
        self.assertIsNone(it["card_message_id"])
        self.f.edit_ok = True
        self.now = at(9, 30)
        run(flow.tick())                                  # turnover room still there
        self.assertEqual([c["ch"] for c in self.cards()], [ROOM, ROOM])
        self.f.edit_ok = False                            # now the whole room goes
        self.f.rooms = {}
        self.f.msgs["c-r1"].append({"inbound": True, "at": at(9, 35), "body": "ok"})
        self.now = at(9, 40)
        run(flow.tick())
        self.f.edit_ok = True
        self.now = at(9, 50)
        run(flow.tick())
        self.assertEqual([c["ch"] for c in self.cards()], [ROOM, ROOM, "code-r1-1"])

    def test_lost_code_room_card_closes_old_room(self):
        """Only the card was deleted by hand: the old code-only room must not be orphaned."""
        self.f.rooms = {}
        self.f.arrivals = [self.f.arr("r2", GATED2)]
        run(flow.tick())
        self.f.edit_ok = False
        self.f.msgs["c-r2"] = [{"inbound": True, "at": at(9, 10), "body": "hello"}]
        self.now = at(9, 20)
        run(flow.tick())
        self.assertEqual([d[0] for d in self.f.deleted], ["code-r2-1"])
        self.assertEqual(len(self.f.reviews), 1)
        self.f.edit_ok = True
        self.now = at(9, 30)
        run(flow.tick())
        self.assertEqual(self.f.code_rooms, ["code-r2-1", "code-r2-2"])


class TestRoomCleanup(FlowCase):
    def setUp(self):
        super().setUp()
        self.f.rooms = {}
        run(flow.tick())
        self.room = "code-r1-1"

    def test_cancelled_code_room_deleted(self):
        self.f.arrivals = []
        self.now = at(11)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(self.room, "codegate: booking cancelled")])
        self.assertEqual(len(self.f.reviews), 1)
        self.assertIn("الحجز ملغي أو انتقل", self.f.reviews[0])
        run(flow.tick())
        self.assertEqual(len(self.f.deleted), 1)

    def test_old_code_room_deleted_next_day(self):
        self.f.arrivals = []
        self.now = datetime.datetime(2026, 10, 22, 9, 5, tzinfo=TZ)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(self.room, "codegate: day over")])
        self.assertEqual(len(self.f.reviews), 1)

    def test_moved_booking_closes_old_code_room(self):
        nxt = "2026-10-22"
        self.f.arrivals = [dict(self.f.arr("r1", GATED), day=nxt,
                                checkin_at=nxt + "T16:00:00+03:00")]
        self.now = datetime.datetime(2026, 10, 22, 9, 5, tzinfo=TZ)
        run(flow.tick())
        self.assertIn((self.room, "codegate: booking moved"), self.f.deleted)
        self.assertEqual(self.f.code_rooms, [self.room, "code-r1-2"])   # a fresh room today

    def test_soak_never_deletes(self):
        flow.set_live(False, "t")
        self.f.arrivals = []
        self.now = datetime.datetime(2026, 10, 22, 9, 5, tzinfo=TZ)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [])

    def test_turnover_room_of_cancelled_booking_not_deleted(self):
        self.f.rooms = {(GATED2, DAY): "room-2"}
        self.f.arrivals = [self.f.arr("r1", GATED), self.f.arr("r2", GATED2)]
        self.now = at(9, 30)
        run(flow.tick())
        self.f.arrivals = [self.f.arr("r1", GATED)]
        self.now = at(10)
        run(flow.tick())
        self.assertNotIn("room-2", [d[0] for d in self.f.deleted])


class TestMoves(FlowCase):
    """Fix round 1: a booking moved to another unit or date takes nothing of the old one with it,
    and never deletes another unit's turnover room."""

    def test_unit_move_same_day_never_deletes_old_turnover_room(self):
        run(flow.tick())                                  # r1's card in room-T (GATED)
        self.f.rooms[(GATED2, DAY)] = "room-2"
        self.f.arrivals = [self.f.arr("r1", GATED2)]      # guest moved to GATED2
        self.now = at(10)
        run(flow.tick())
        it = db.get("r1")
        self.assertEqual((it["lid"], it["channel_id"], it["room_kind"]),
                         (GATED2, "room-2", "turnover"))
        self.assertEqual(self.cards()[-1]["ch"], "room-2")   # the new unit's card, new room
        self.assertFalse(flow.should_hold(GATED, DAY))
        self.assertTrue(flow.should_hold(GATED2, DAY))
        flow.defer_close(GATED2, DAY)
        ok, _ = run(flow.press_send(it["card_message_id"], self.p()))
        self.assertTrue(ok)
        self.assertEqual(self.f.deleted, [("room-2", "codegate: code sent")])
        self.assertNotIn(ROOM, [d[0] for d in self.f.deleted])

    def test_unit_move_closes_old_code_room_only(self):
        self.f.rooms = {}
        run(flow.tick())                                  # code-r1-1 for GATED
        self.f.rooms = {(GATED2, DAY): "room-2"}
        self.f.arrivals = [self.f.arr("r1", GATED2)]
        self.now = at(10)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [("code-r1-1", "codegate: booking moved")])
        self.assertEqual(db.get("r1")["channel_id"], "room-2")

    def test_unit_move_closes_old_held_room(self):
        """The old unit's room was HELD: cleaning already asked for its delete, so it goes."""
        run(flow.tick())
        flow.defer_close(GATED, DAY)
        self.f.rooms[(GATED2, DAY)] = "room-2"
        self.f.arrivals = [self.f.arr("r1", GATED2)]
        self.now = at(10)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(ROOM, "codegate: booking moved")])
        self.assertEqual(len(self.f.reviews), 1)
        it = db.get("r1")
        self.assertEqual((it["held_channel_id"], it["room_close_pending"]), (None, 0))
        self.assertEqual(it["channel_id"], "room-2")

    def test_held_room_closed_when_booking_moves_date(self):
        """Case (c): held, then moved to tomorrow before the tick saw it as gone today."""
        run(flow.tick())
        flow.defer_close(GATED, DAY)
        nxt = "2026-10-22"
        self.f.arrivals = [dict(self.f.arr("r1", GATED), day=nxt,
                                checkin_at=nxt + "T16:00:00+03:00")]
        self.now = datetime.datetime(2026, 10, 22, 9, 5, tzinfo=TZ)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(ROOM, "codegate: booking moved")])
        self.assertEqual(db.get("r1")["day"], nxt)

    def test_move_close_failure_keeps_room_and_retries(self):
        self.f.rooms = {}
        run(flow.tick())                                  # code-r1-1 on DAY
        nxt = "2026-10-22"
        self.f.arrivals = [dict(self.f.arr("r1", GATED), day=nxt,
                                checkin_at=nxt + "T16:00:00+03:00")]
        self.f.delete_ok = False
        self.now = datetime.datetime(2026, 10, 22, 9, 5, tzinfo=TZ)
        quiet(run, flow.tick())
        it = db.get("r1")
        self.assertEqual((it["day"], it["channel_id"]), (DAY, "code-r1-1"))   # not wiped
        self.f.delete_ok = True
        self.now = datetime.datetime(2026, 10, 22, 9, 20, tzinfo=TZ)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [("code-r1-1", "codegate: booking moved")])
        it = db.get("r1")
        self.assertEqual((it["day"], it["channel_id"]), (nxt, "code-r1-2"))


class TestHeldRoom(FlowCase):
    """Fix round 1: the held room is tracked by its own id, whatever room the card is in."""

    def test_code_room_card_and_held_turnover_both_close(self):
        """Probe A: card in a code-only room; the turnover room appears later and is held."""
        self.f.rooms = {}
        run(flow.tick())
        mid = self.cards()[0]["id"]
        self.f.rooms = {(GATED, DAY): ROOM}
        self.assertTrue(flow.should_hold(GATED, DAY))
        flow.defer_close(GATED, DAY)
        self.assertEqual(db.get("r1")["held_channel_id"], ROOM)
        ok, _ = run(flow.press_send(mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(sorted(d[0] for d in self.f.deleted), sorted(["code-r1-1", ROOM]))
        self.assertEqual(len(self.f.reviews), 2)          # one line per room
        self.now = datetime.datetime(2026, 10, 22, 9, 5, tzinfo=TZ)
        self.f.arrivals = []
        run(flow.tick())
        self.assertEqual(len(self.f.deleted), 2)

    def test_held_survives_lost_card_after_manual(self):
        """Case (b): manual record, the card is lost (channel_id wiped), the hold still closes."""
        run(flow.tick())
        mid = self.cards()[0]["id"]
        flow.defer_close(GATED, DAY)
        self.now = at(13)
        run(flow.press_manual(mid, self.p()))
        self.f.edit_ok = False
        self.f.msgs["c-r1"].append({"inbound": True, "at": at(13, 5), "body": "thanks"})
        self.now = at(13, 10)
        run(flow.tick())
        it = db.get("r1")
        self.assertIsNone(it["channel_id"])
        self.assertEqual(it["held_channel_id"], ROOM)
        self.f.code["c-r1"] = True
        self.now = at(13, 20)
        run(flow.tick())
        self.assertEqual(self.f.deleted, [(ROOM, "codegate: code sent")])

    def test_defer_close_without_item_does_nothing(self):
        flow.defer_close(GATED2, DAY)                     # no arrival for that unit
        flow.defer_close(GATED, DAY)                      # tick hasn't run: no item yet
        self.assertEqual(db._q("SELECT * FROM codegate_items"), [])

    def test_defer_close_explicit_channel_wins(self):
        run(flow.tick())
        flow.defer_close(GATED, DAY, "room-held")
        self.assertEqual(db.get("r1")["held_channel_id"], "room-held")

    def test_defer_close_unresolved_room_looked_up_at_close(self):
        self.f.rooms = {}
        run(flow.tick())                                  # code room; no turnover room yet
        flow.defer_close(GATED, DAY)
        it = db.get("r1")
        self.assertEqual((it["held_channel_id"], it["room_close_pending"]), (None, 1))
        self.f.rooms = {(GATED, DAY): ROOM}
        run(flow.press_send(it["card_message_id"], self.p()))
        self.assertIn((ROOM, "codegate: code sent"), self.f.deleted)

    def test_held_room_gone_clears_pending(self):
        self.f.rooms = {}
        run(flow.tick())
        flow.defer_close(GATED, DAY)                      # unresolvable, and stays so
        run(flow.press_send(db.get("r1")["card_message_id"], self.p()))
        self.assertEqual(db.get("r1")["room_close_pending"], 0)


class TestDeleteFailures(FlowCase):
    """Fix round 1: a delete that keeps failing is retried at most 3 times, then given up."""

    def setUp(self):
        super().setUp()
        self.f.rooms = {}
        run(flow.tick())
        self.mid = self.cards()[0]["id"]

    def gave_up(self):
        return [r for r in self.f.reviews if r.startswith("⚠️ ما قدرت أقفل الغرفة")]

    def test_already_gone_counts_as_closed(self):
        self.f.gone.add("code-r1-1")                      # deleted by hand
        ok, _ = run(flow.press_send(self.mid, self.p()))
        self.assertTrue(ok)
        self.assertEqual(self.f.gone_hits, [("code-r1-1", "codegate: code sent")])
        self.assertIsNone(db.get("r1")["channel_id"])
        self.assertEqual(len(self.f.reviews), 1)
        calls = self.f.delete_calls
        self.now = at(9, 20)
        run(flow.tick())
        self.assertEqual(self.f.delete_calls, calls)      # nothing left to retry

    def test_error_gives_up_after_three(self):
        self.f.delete_ok = False
        quiet(run, flow.press_send(self.mid, self.p()))   # failure 1
        for m in (20, 35):                                # failures 2 and 3
            self.now = at(9, m)
            quiet(run, flow.tick())
        it = db.get("r1")
        self.assertIsNone(it["channel_id"])
        self.assertEqual(self.f.delete_calls, 3)
        self.assertEqual(len(self.gave_up()), 1)
        self.assertIn("U%s" % GATED, self.gave_up()[0])
        self.now = at(9, 50)
        quiet(run, flow.tick())
        self.assertEqual(self.f.delete_calls, 3)          # stopped
        self.assertEqual(len(self.f.reviews), 1)

    def test_error_on_held_room_gives_up_too(self):
        self.f.rooms = {(GATED, DAY): ROOM}
        flow.defer_close(GATED, DAY)
        self.f.delete_ok = False
        self.f.gone.add("code-r1-1")                      # the code room closes fine
        quiet(run, flow.press_send(self.mid, self.p()))
        for m in (20, 35, 50):
            self.now = at(9, m)
            quiet(run, flow.tick())
        it = db.get("r1")
        self.assertEqual((it["held_channel_id"], it["room_close_pending"]), (None, 0))
        self.assertEqual(len(self.gave_up()), 1)

    def test_old_row_gives_up_at_once(self):
        self.f.arrivals = []
        db.set_close_pending("r1", False)
        self.f.delete_ok = False
        self.now = datetime.datetime(2026, 10, 24, 9, 5, tzinfo=TZ)   # 3 days on
        quiet(run, flow.tick())
        self.assertEqual(self.f.delete_calls, 1)
        self.assertIsNone(db.get("r1")["channel_id"])
        self.assertEqual(len(self.gave_up()), 1)

    def test_sweep_db_error_does_not_abort_tick(self):
        real = flow.db.code_room_items

        def boom(*a, **k):
            raise RuntimeError("db locked")
        flow.db.code_room_items = boom
        try:
            self.f.msgs["c-r1"].append({"inbound": True, "at": at(9, 10), "body": "see you"})
            self.now = at(9, 20)
            quiet(run, flow.tick())
        finally:
            flow.db.code_room_items = real
        self.assertIn("see you", json.dumps(self.f.edits[-1]["embed"], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
