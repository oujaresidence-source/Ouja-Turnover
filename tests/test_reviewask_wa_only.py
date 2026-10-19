# -*- coding: utf-8 -*-
"""
«رفع التقييم» WhatsApp-only (team ruling 2026-10-19, confirmed by the owner): no calls.

    day 1 (checkout)  17:00 WhatsApp prompt — «أرسلت الرسالة» / «الضيف رد»
    any time          «الضيف رد» closes the room (the 1-day sweep deletes it)
    day 2             no reply yet → ONE «تابع مع الضيف» prompt at 17:00
    day 3             13:00 the room closes by itself (no_reply) and is deleted at once,
                      transcript first — the same fence as every other review-room delete
    «بيقيّم»          the ticket keeps waiting for Airbnb quietly; its room goes after 1 day

REVIEWASK_WA_ONLY=0 brings the call flow back unchanged (tests in test_reviewask_engine).

Run: python3 -m unittest tests.test_reviewask_wa_only
"""

import asyncio
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb  # noqa: E402
from reviewask import config, db, engine as E, flow, texts  # noqa: E402
from reviewask.host import HOST  # noqa: E402

TZ = E.tz()


def at(y, mo, d, h=0, mi=0):
    return datetime.datetime(y, mo, d, h, mi, tzinfo=TZ)


def cfg(**kw):
    c = E.default_cfg()
    c.update({"wa_only": True})
    c.update(kw)
    return c


def row(**kw):
    r = {"state": E.WAITING, "mode": "review", "day": "2026-10-14", "stage_due_at": None,
         "pinged_at": None, "remind_count": 0, "missed_at": None, "next_due_at": None,
         "calls_used": 0, "later_used": 0, "care_ok": 0, "state_at": None}
    r.update(kw)
    return r


C = cfg()


class TestClock(unittest.TestCase):
    def test_day1_whatsapp_at_17(self):
        self.assertIsNone(E.next_action(row(), at(2026, 10, 14, 16, 59), C))
        a = E.next_action(row(), at(2026, 10, 14, 17, 0), C)
        self.assertEqual((a["act"], a["state"]), ("stage", E.WA_DUE))

    def test_care_room_also_starts_with_whatsapp(self):
        a = E.next_action(row(mode="care"), at(2026, 10, 14, 17, 0), C)
        self.assertEqual((a["act"], a["state"]), ("stage", E.WA_DUE))

    def test_sent_then_day2_followup(self):
        r = row(state=E.WA_SENT, state_at="2026-10-14T17:20:00+03:00",
                next_due_at="2026-10-15T20:00:00+03:00")
        self.assertIsNone(E.next_action(r, at(2026, 10, 15, 16, 59), C))
        a = E.next_action(r, at(2026, 10, 15, 17, 0), C)
        self.assertEqual((a["act"], a["state"]), ("stage", E.FOLLOW_DUE))

    def test_sent_late_on_day2_gets_no_second_followup(self):
        r = row(state=E.WA_SENT, state_at="2026-10-15T18:00:00+03:00")
        self.assertIsNone(E.next_action(r, at(2026, 10, 15, 19, 0), C))
        self.assertIsNone(E.next_action(r, at(2026, 10, 16, 12, 59), C))

    def test_missed_whatsapp_still_gets_the_followup(self):
        sd = "2026-10-14T17:00:00+03:00"
        r = row(state=E.WA_DUE, stage_due_at=sd, pinged_at=sd, remind_count=2)
        a = E.next_action(r, at(2026, 10, 14, 22, 0), C)
        self.assertEqual(a["act"], "miss")
        r["missed_at"] = sd
        self.assertIsNone(E.next_action(r, at(2026, 10, 15, 16, 0), C))
        a = E.next_action(r, at(2026, 10, 15, 17, 0), C)
        self.assertEqual((a["act"], a["state"]), ("stage", E.FOLLOW_DUE))

    def test_followup_reminds_then_misses_without_rescheduling(self):
        sd = "2026-10-15T17:00:00+03:00"
        r = row(state=E.FOLLOW_DUE, stage_due_at=sd, pinged_at=sd)
        a = E.next_action(r, at(2026, 10, 15, 18, 0), C)
        self.assertEqual(a["act"], "remind")
        a = E.next_action(r, at(2026, 10, 15, 22, 0), C)
        self.assertEqual(a["act"], "miss")
        self.assertNotIn("stage_due_at", a["fields"])
        r["missed_at"] = sd
        self.assertIsNone(E.next_action(r, at(2026, 10, 16, 9, 0), C))

    def test_day3_closes_every_waiting_state(self):
        for st in (E.WAITING, E.WA_DUE, E.WA_SENT, E.FOLLOW_DUE, E.CALL_DUE, E.CALL_RETRY,
                   E.CARE_DUE):
            r = row(state=st, stage_due_at="2026-10-15T17:00:00+03:00",
                    pinged_at="2026-10-15T17:00:00+03:00")
            self.assertNotEqual((E.next_action(r, at(2026, 10, 16, 12, 59), C) or {}).get("act"),
                                "expire", st)
            a = E.next_action(r, at(2026, 10, 16, 13, 0), C)
            self.assertEqual((a["act"], a["state"]), ("expire", E.NO_REPLY), st)

    def test_promised_is_not_closed_on_day3_only_by_airbnb(self):
        r = row(state=E.PROMISED)
        self.assertIsNone(E.next_action(r, at(2026, 10, 16, 13, 0), C))
        a = E.next_action(r, at(2026, 10, 27, 23, 59), C)
        self.assertEqual((a["act"], a["state"]), ("expire", E.PROMISED_EXPIRED))

    def test_legacy_call_rows_become_the_followup(self):
        for st in (E.CALL_DUE, E.CALL_RETRY, E.CARE_DUE):
            r = row(state=st, stage_due_at="2026-10-15T09:00:00+03:00",
                    pinged_at="2026-10-15T09:00:00+03:00", next_due_at="2026-10-15T20:00:00+03:00")
            a = E.next_action(r, at(2026, 10, 15, 17, 0), C)
            self.assertEqual((a["act"], a["state"]), ("stage", E.FOLLOW_DUE), st)

    def test_quiet_hours_still_hold(self):
        r = row(state=E.WA_SENT, state_at="2026-10-14T17:20:00+03:00")
        self.assertIsNone(E.next_action(r, at(2026, 10, 15, 12, 0), dict(C, wa_at="12:00")))

    def test_switch_off_keeps_the_call_flow(self):
        r = row(state=E.WA_SENT, next_due_at="2026-10-15T20:00:00+03:00")
        a = E.next_action(r, at(2026, 10, 15, 20, 0), cfg(wa_only=False))
        self.assertEqual((a["act"], a["state"]), ("stage", E.CALL_DUE))


class TestPresses(unittest.TestCase):
    NOW = at(2026, 10, 14, 18, 0)

    def test_any_reply_closes(self):
        p = E.press(row(state=E.WA_SENT), "replied_quiet", self.NOW, C)
        self.assertEqual(p["fields"]["state"], E.REPLIED)
        self.assertIn(E.REPLIED, E.TERMINAL)
        self.assertEqual(E.press(row(state=E.WA_SENT), "replied_no", self.NOW, C)["fields"]["state"],
                         E.DECLINED)
        self.assertEqual(E.press(row(state=E.WA_SENT), "replied_will", self.NOW, C)["fields"]["state"],
                         E.PROMISED)

    def test_switch_off_keeps_quiet_reply_open(self):
        p = E.press(row(state=E.WA_SENT), "replied_quiet", self.NOW, cfg(wa_only=False))
        self.assertEqual(p["fields"]["state"], E.WA_SENT)

    def test_followup_accepts_sent_reply_and_complaint(self):
        for kind in ("sent", "replied_will", "replied_no", "replied_quiet", "complaint"):
            self.assertIn(E.FOLLOW_DUE, E.ALLOWED_FROM[kind], kind)
        self.assertIn(E.FOLLOW_DUE, E.OPEN)
        self.assertIn(E.FOLLOW_DUE, E.DUE_STATES)

    def test_no_call_button_is_ever_shown(self):
        calls = {"rated", "promise", "noanswer", "later", "decline", "wrong", "satisfied"}
        for st in (E.WAITING, E.WA_DUE, E.WA_SENT, E.FOLLOW_DUE):
            self.assertFalse(calls & set(E.stage_buttons(row(state=st))), st)
        self.assertEqual(E.stage_buttons(row(state=E.FOLLOW_DUE)), ["wa", "sent", "replied"])


class TestConfigAndWords(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("REVIEWASK_WA_ONLY", None)

    def test_on_by_default(self):
        os.environ.pop("REVIEWASK_WA_ONLY", None)
        self.assertTrue(config.snapshot()["wa_only"])
        os.environ["REVIEWASK_WA_ONLY"] = "0"
        self.assertFalse(config.snapshot()["wa_only"])

    def test_every_new_state_has_words(self):
        for st in (E.FOLLOW_DUE, E.REPLIED, E.NO_REPLY):
            self.assertIn(st, texts.STATE_AR)
        ping = texts.stage_ping(row(state=E.FOLLOW_DUE, guest="Sara"))
        self.assertIn("تابع", ping)
        self.assertNotIn("اتص", texts.stage_ping(row(state=E.FOLLOW_DUE)))
        self.assertNotIn("اتص", texts.FOOTER)
        self.assertNotIn("مكالم", texts.miss_line(row(state=E.WA_DUE)))
        self.assertNotIn("مكالم", texts.remind(row(state=E.FOLLOW_DUE), 1))
        self.assertNotIn("مكالم", texts.press_saved("no_phone", row(state=E.WA_SENT)))
        self.assertIn("انقفلت", texts.press_saved("replied_quiet", row(state=E.REPLIED)))


# ------------------------------------------------------------------ the rooms

class Rooms:
    def __init__(self):
        self.rooms, self.deleted, self.posts = {}, [], []

    async def room_info(self, cid):
        if cid not in self.rooms:
            return {"exists": False, "topic": ""}
        return {"exists": True, "topic": self.rooms[cid]}

    async def fetch_transcript(self, cid, limit):
        return [{"author": "bot", "at": "2026-10-16T10:00:00+03:00", "content": "card",
                 "embeds": [], "attachments": []}]

    async def delete_room(self, cid):
        t = db.by_channel(cid)
        assert t and db.transcript(t["id"]) is not None, "deleted before the transcript was saved"
        self.deleted.append(cid)
        self.rooms.pop(cid, None)
        return True

    async def post(self, cid, text="", buttons=None, mentions=False, **kw):
        self.posts.append((cid, text))
        return None

    async def edit(self, *a, **kw):
        return True


class TestRooms(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="rv_wa_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        db.reset_init_cache()
        flow._locks.clear()
        os.environ.pop("REVIEWASK_WA_ONLY", None)
        os.environ.pop("REVIEWASK_DELETE_AFTER_DAYS", None)
        self.r = Rooms()
        HOST.room_info = self.r.room_info
        HOST.fetch_transcript = self.r.fetch_transcript
        HOST.delete_room = self.r.delete_room
        HOST.post = self.r.post
        HOST.edit = self.r.edit

    def make(self, res, cid, **fields):
        base = {"reservation_id": res, "lid": 1, "day": "2026-10-14", "unit": "Ouja | A",
                "guest": "G", "state": E.WA_SENT, "channel_id": cid}
        _c, t = db.insert_ticket(base)
        if fields:
            db.update_ticket(t["id"], fields)
        self.r.rooms[cid] = E.topic(res, 1, t["id"])
        return db.ticket(t["id"])

    def test_day3_close_deletes_the_room_at_once(self):
        t = self.make("r1", "c1", state_at="2026-10-14T17:20:00+03:00")
        now_ = at(2026, 10, 16, 13, 0)
        act = asyncio.run(flow.process(t, now_, C))
        self.assertEqual(act, "expire")
        row2 = db.ticket(t["id"])
        self.assertEqual(row2["state"], E.NO_REPLY)
        self.assertEqual(self.r.deleted, ["c1"])
        self.assertIsNotNone(db.transcript(t["id"]))

    def test_promised_room_goes_after_one_day_ticket_keeps_waiting(self):
        t = self.make("r2", "c2", state=E.PROMISED, state_at="2026-10-14T18:00:00+03:00")
        fresh = self.make("r3", "c3", state=E.PROMISED, state_at="2026-10-15T12:00:00+03:00")
        done = asyncio.run(flow.sweep_closed(at(2026, 10, 15, 19, 0), pause=0))
        self.assertEqual(done, [t["id"]])
        self.assertEqual(self.r.deleted, ["c2"])
        self.assertEqual(db.ticket(t["id"])["state"], E.PROMISED)
        self.assertIsNone(db.ticket(fresh["id"])["deleted_at"])

    def test_switch_off_never_sweeps_promised(self):
        os.environ["REVIEWASK_WA_ONLY"] = "0"
        self.make("r4", "c4", state=E.PROMISED, state_at="2026-10-01T18:00:00+03:00")
        asyncio.run(flow.sweep_closed(at(2026, 10, 15, 19, 0), pause=0))
        self.assertEqual(self.r.deleted, [])


if __name__ == "__main__":
    unittest.main()
