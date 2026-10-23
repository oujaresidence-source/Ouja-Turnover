# -*- coding: utf-8 -*-
"""
«طلبات سام» end to end on a real (temporary) brain.db with a fake HOST and a fake model.

Locked here: edits/deletes mirrored on OUR reply only; two overlapping bot copies post once;
the outbox backs off 1/5/15/60; presses are found by message id (they survive a redeploy);
permission gates refuse AND log who tried; «سلّمت» needs a file for file-type asks and fails
open (with a flag) when the history cannot be read; the five-rule owner order; leave hands the
request to the coverer; the ladder fires each step once and only the latest after downtime;
the board is edited in place; a closed ticket closes its requests with no miss.

Run: python3 -m unittest tests.test_rrdesk_flow
"""

import asyncio
import datetime
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "fixtures", "rrdesk"))

import fakes as F                                   # noqa: E402
from rrdesk import db, engine, flow, outbox         # noqa: E402

D = datetime.timedelta


def sam_asks(tc, mid="s1", text="@Nasser please send the check-in photos", mentions=(F.NASSER,),
             mode="auto", classify=None, asks=None, **kw):
    db.set_setting("detect_mode", mode)
    c = dict(classify or F.REQ_CLASSIFY)
    if asks:
        c["asks"] = list(asks)
        text = "%s — %s" % (text, " ".join(asks))     # distinct text: the cache keys on it
    F.fake_model(tc, classify=c)
    return flow.on_message(F.msg(mid, text, mentions=mentions, **kw))


class Translation(unittest.TestCase):
    def setUp(self):
        F.setup(self)
        F.fake_model(self)

    def test_staff_message_gets_one_reply(self):
        rep = flow.on_message(F.msg("m1", "الفاتورة بتوصل بكرة", author=F.NASSER, name="Nasser"))
        self.assertEqual(rep["translation"], "model")
        rows = F.queued("post", "tr:")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payload"]["embeds"][0]["footer"], "Auto-translation · AR→EN")
        # a second bot copy sees the same message: no second translation, no second call
        n = len(self.model_calls)
        rep2 = flow.on_message(F.msg("m1", "الفاتورة بتوصل بكرة", author=F.NASSER, name="Nasser"))
        self.assertEqual(rep2["translation"], "claimed_elsewhere")
        self.assertEqual(len(self.model_calls), n)
        self.assertEqual(len(F.queued("post", "tr:")), 1)

    def test_thread_message_counts_as_the_room(self):
        rep = flow.on_message(F.msg("m2", "الصور بالثريد", author=F.NASSER, channel=F.THREAD,
                                    parent=F.ROOM))
        self.assertEqual(rep["room"], F.ROOM)
        self.assertEqual(F.queued("post", "tr:")[0]["payload"]["channel_id"], F.THREAD)

    def test_room_toggle_and_closed_room(self):
        ok, _ = flow.set_translate(F.ROOM, None, False, F.NASSER, "Nasser", False)
        self.assertFalse(ok)                                 # staff cannot switch it
        ok, _ = flow.set_translate(F.ROOM, None, False, F.SAM, "Sam", False)
        self.assertTrue(ok)
        self.assertEqual(flow.on_message(F.msg("m3", "وش صار", author=F.NASSER))["translation"], "off")
        self.state["rec"]["status"] = "closed"
        self.assertIsNone(flow.on_message(F.msg("m4", "وش صار", author=F.NASSER))["room"])

    def test_edit_and_delete_touch_only_our_reply(self):
        flow.on_message(F.msg("m5", "الضيف كسر الطاولة", author=F.NASSER))
        F.deliver_all()
        self.assertEqual(db.translation("m5")["our_message_ids"], ["p:tr:m5"])
        flow.on_edit(F.msg("m5", "الضيف كسر الطاولة والكرسي", author=F.NASSER))
        e = F.queued("edit")
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["payload"]["message_id"], "p:tr:m5")
        flow.on_delete(F.ROOM, "m5")
        d = F.queued("delete")
        self.assertEqual([x["payload"]["message_id"] for x in d], ["p:tr:m5"])

    def test_voice_note_reply_once_and_counted(self):
        flow.on_message(F.msg("v1", "", author=F.NASSER, voice=True))
        flow.on_message(F.msg("v1", "", author=F.NASSER, voice=True))
        self.assertEqual(len(F.queued("post", "voice:")), 1)
        self.assertEqual(db.voice_counts(F.at(2026, 10, 1, 0), F.at(2026, 11, 1, 0)), {F.NASSER: 1})

    def test_image_without_caption_gets_only_the_button(self):
        flow.on_message(F.msg("i1", "", author=F.NASSER,
                              media=[{"url": "https://cdn/x.jpg", "content_type": "image/jpeg"}]))
        rows = F.queued("post", "media:")
        self.assertEqual(rows[0]["payload"]["buttons"][0]["custom_id"], "rd:img")
        self.assertEqual(self.model_calls, [])            # never automatic: cost

    def test_force_off_mutes_everything(self):
        flow.set_switch("force_off", True, "test")
        self.assertEqual(flow.on_message(F.msg("m6", "وش صار", author=F.NASSER)).get("skipped"), "force_off")
        self.assertEqual(F.queued(), [])


class Requests(unittest.TestCase):
    def setUp(self):
        F.setup(self)

    def test_detected_request_owner_rule_1_and_card(self):
        rep = sam_asks(self)
        req = db.request(rep["request"])
        self.assertEqual((req["owner_did"], req["owner_rule"], req["path"]), (F.NASSER, 1, "detected"))
        self.assertEqual(req["asks"], ["photos"])
        card = F.queued("post", "card:")[0]["payload"]
        self.assertEqual(card["reply_to"], "s1")
        self.assertEqual(card["mentions"], [F.NASSER])
        self.assertIn("<@111>", card["content"])

    def test_confirm_mode_asks_sam_instead(self):
        rep = sam_asks(self, mode="confirm")
        self.assertNotIn("request", rep)
        btns = [b["custom_id"] for b in F.queued("post", "tr:")[0]["payload"]["buttons"]]
        self.assertEqual(btns[:2], ["rd:qyes", "rd:qno"])
        F.deliver_all()
        ok, text = flow.press("q_yes", "p:tr:s1", {"did": F.NASSER, "name": "Nasser"})
        self.assertFalse(ok)                               # only Sam / admin
        self.assertTrue(db.events(kinds=["press_refused"]))
        ok, text = flow.press("q_yes", "p:tr:s1", {"did": F.SAM, "name": "Sam"})
        self.assertTrue(ok)
        req = db.request_by_source("s1")
        self.assertEqual((req["path"], req["owner_did"]), ("confirmed", F.NASSER))

    def test_low_confidence_is_nothing(self):
        c = dict(F.REQ_CLASSIFY, confidence=0.2)
        rep = sam_asks(self, classify=c)
        self.assertNotIn("request", rep)
        self.assertEqual(F.queued("post", "tr:")[0]["payload"]["buttons"], [])

    def test_owner_order(self):
        # 3: opener in the calendar
        r = db.request(sam_asks(self, mid="a", mentions=(), asks=["photos"])["request"])
        self.assertEqual((r["owner_did"], r["owner_rule"]), (F.ASEEL, 3))
        # 2: a role mention → the apartment's responsible person today
        self.clock.t += datetime.timedelta(minutes=20)        # not a burst
        r = db.request(sam_asks(self, mid="b", mentions=(), role_mentioned=True, asks=["video"])["request"])
        self.assertEqual((r["owner_did"], r["owner_rule"]), (F.NOURA, 2))
        # 4: opener not in the calendar → responsible
        self.state["rec"]["opener_id"] = "424242"
        self.clock.t += datetime.timedelta(minutes=20)        # not a burst
        r = db.request(sam_asks(self, mid="c", mentions=(), asks=["invoice"])["request"])
        self.assertEqual((r["owner_did"], r["owner_rule"]), (F.NOURA, 4))
        # 5: nobody → the ops lead, flagged unowned
        self.state["resp"] = ("", "", "unknown")
        self.clock.t += datetime.timedelta(minutes=20)        # not a burst
        r = db.request(sam_asks(self, mid="d", mentions=(), asks=["receipt"])["request"])
        self.assertEqual((r["owner_did"], r["owner_rule"], r["unowned"]), (F.ASEEL, 5, 1))
        # Sam mentioning himself / the bot is not an owner
        self.state["resp"] = ("نورة", F.NOURA, "owner")
        self.clock.t += datetime.timedelta(minutes=20)        # not a burst
        r = db.request(sam_asks(self, mid="e", mentions=(F.SAM, F.BOT), asks=["quote"])["request"])
        self.assertEqual(r["owner_rule"], 4)

    def test_reask_is_logged_not_a_second_request(self):
        rid = sam_asks(self)["request"]
        rep = sam_asks(self, mid="s2", text="hello, can i have the before check-in photos?")
        self.assertTrue(rep.get("reask"))
        self.assertNotIn("request", rep)
        self.assertEqual(len(db.recent_requests()), 1)
        self.assertTrue([e for e in db.events(request_id=rid) if e["kind"] == "sam_reask"])

    def test_two_lines_in_a_burst_are_one_request(self):
        rid = sam_asks(self, asks=["invoice"], text="carpet invoice")["request"]
        rep = sam_asks(self, mid="s2", asks=["photos"], text="and any other photos?")
        self.assertTrue(rep.get("merged"))
        self.assertEqual(db.request(rid)["asks"], ["invoice", "photos"])
        self.assertEqual(len(db.recent_requests()), 1)

    def test_owner_on_leave_goes_to_coverer(self):
        self.state["off"].add("ناصر")
        r = db.request(sam_asks(self)["request"])
        self.assertEqual(r["owner_did"], F.NOURA)
        ev = [e for e in db.events(request_id=r["id"]) if e["kind"] == "owner_chosen"][0]
        self.assertEqual(ev["detail"]["covered_for"], "ناصر")

    def test_pin_and_command_paths(self):
        F.fake_model(self, classify=dict(F.REQ_CLASSIFY, is_request=False, confidence=0.1))
        flow.on_message(F.msg("p1", "need the invoice for the sofa"))
        req = flow.on_pin(F.ROOM, None, "p1", F.SAM, F.SAM, "need the invoice for the sofa", F.at(2026, 10, 20, 12, 5))
        self.assertEqual((req["path"], req["asks"]), ("pin", ["invoice"]))
        self.assertIsNone(flow.on_pin(F.ROOM, None, "p1", F.NASSER, F.SAM, "x", F.at(2026, 10, 20, 12, 5)))
        ok, text = flow.ask_command(F.ROOM, None, F.SAM, "Sam", "Upload the receipt please", F.NASSER, True,
                                    F.at(2026, 10, 20, 12, 6), 12345)
        self.assertTrue(ok)
        r = db.request_by_source("cmd:12345")
        self.assertEqual((r["path"], r["urgent"], r["urgent_why"], r["owner_did"]), ("command", 1, "flag", F.NASSER))
        self.assertNotIn("reply_to", F.queued("post", "card:%d" % r["id"])[0]["payload"])

    def test_aircover_deadline_makes_it_urgent(self):
        from rrdesk.host import HOST
        HOST.enrich = lambda code: {"days_left": 2, "deadline_passed": False, "lid": 383921}
        r = db.request(sam_asks(self)["request"])
        self.assertEqual((r["urgent"], r["urgent_why"]), (1, "aircover"))
        self.assertEqual(db.parse(r["resp_due"]), F.at(2026, 10, 20, 12, 30))


class Presses(unittest.TestCase):
    def setUp(self):
        F.setup(self)
        self.rid = sam_asks(self)["request"]
        F.deliver_all()
        self.card = db.request(self.rid)["card_message_id"]
        self.assertEqual(self.card, "p:card:%d" % self.rid)

    def test_team_message_acknowledges(self):
        F.fake_model(self)
        self.clock.t = F.at(2026, 10, 20, 12, 20)
        flow.on_message(F.msg("t1", "ابشر", author=F.NOURA, name="Noura", at_=self.clock.t))
        r = db.request(self.rid)
        self.assertEqual((r["state"], r["acked_by"]), ("acknowledged", "Noura"))
        self.assertTrue(F.queued("edit", "cardedit:"))     # the card shows the new state

    def test_found_by_message_id_after_a_redeploy(self):
        db.reset_init_cache()                              # a fresh process, same database
        ok, _ = flow.press("ack", self.card, {"did": F.NASSER, "name": "Nasser"})
        self.assertTrue(ok)
        self.assertEqual(db.request(self.rid)["state"], "acknowledged")

    def test_gates_and_refusals_are_logged(self):
        ok, _ = flow.press("ack", self.card, {"did": F.SAM, "name": "Sam"})
        self.assertFalse(ok)
        ok, _ = flow.press("got_it", self.card, {"did": F.NASSER, "name": "Nasser"})
        self.assertFalse(ok)
        ok, _ = flow.press("reassign", self.card, {"did": F.NOURA, "name": "Noura"},
                           {"to_did": F.NOURA, "reason": "covering"})
        self.assertFalse(ok)
        refused = [e["detail"]["why"] for e in db.events(kinds=["press_refused"])]
        self.assertEqual(sorted(refused), ["not_lead", "not_sam", "sam_cannot"])

    def test_proof_rule(self):
        ok, text = flow.press("deliver", self.card, {"did": F.NASSER, "name": "Nasser"}, {"proof": False})
        self.assertFalse(ok)
        self.assertIn("ملف", text)
        self.assertIsNone(flow.proof_known(self.card))
        db.record_file("f1", F.THREAD, F.NASSER, 2, F.at(2026, 10, 20, 12, 30))
        flow._note_thread(F.ROOM, F.THREAD)
        self.assertTrue(flow.proof_known(self.card))
        # history unreadable → fails OPEN with a flag
        ok, _ = flow.press("deliver", self.card, {"did": F.NASSER, "name": "Nasser"}, {"proof": None})
        self.assertTrue(ok)
        self.assertEqual(db.request(self.rid)["proof_unchecked"], 1)

    def test_not_available_needs_a_reason_and_skips_the_file_rule(self):
        ok, _ = flow.press("unavailable", self.card, {"did": F.NASSER, "name": "Nasser"}, {"note": ""})
        self.assertFalse(ok)
        ok, _ = flow.press("unavailable", self.card, {"did": F.NASSER, "name": "Nasser"},
                           {"note": "no invoice — bought in cash"})
        self.assertTrue(ok)
        r = db.request(self.rid)
        self.assertEqual((r["state"], r["delivered_note"]), ("delivered", "no invoice — bought in cash"))
        ok, _ = flow.press("unavailable", self.card, {"did": F.SAM, "name": "Sam"}, {"note": "xx yy"})
        self.assertFalse(ok)

    def test_first_final_wins(self):
        flow.press("deliver", self.card, {"did": F.NASSER, "name": "Nasser"}, {"proof": True})
        ok1, _ = flow.press("got_it", self.card, {"did": F.SAM, "name": "Sam"})
        ok2, text = flow.press("cancel", self.card, {"did": F.SAM, "name": "Sam"}, {"reason": "late"})
        self.assertTrue(ok1)
        self.assertFalse(ok2)

    def test_rework_keeps_the_original_due(self):
        due = db.request(self.rid)["deliv_due"]
        flow.press("deliver", self.card, {"did": F.NASSER, "name": "Nasser"}, {"proof": True})
        ok, _ = flow.press("not_what", self.card, {"did": F.SAM, "name": "Sam"}, {"note": "wrong room"})
        self.assertTrue(ok)
        r = db.request(self.rid)
        self.assertEqual((r["state"], r["rework"], r["deliv_due"]), ("acknowledged", 1, due))

    def test_rework_reminds_before_any_miss(self):
        flow.press("deliver", self.card, {"did": F.NASSER, "name": "Nasser"}, {"proof": True})
        self.clock.t = F.at(2026, 10, 22, 12, 0)            # rework long after the original due
        flow.press("not_what", self.card, {"did": F.SAM, "name": "Sam"}, {"note": "wrong room"})
        flow.tick()
        self.assertIsNone(db.miss(self.rid))
        self.assertTrue([s for s in db.ladder_sent(self.rid) if s.startswith("D2")])

    def test_reassign_restarts_the_clock(self):
        self.clock.t = F.at(2026, 10, 20, 13, 0)
        ok, _ = flow.press("reassign", self.card, {"did": F.ASEEL, "name": "Aseel"},
                           {"to_did": F.NOURA, "reason": "Nasser is in the field"})
        self.assertTrue(ok)
        r = db.request(self.rid)
        self.assertEqual((r["owner_did"], r["gen"]), (F.NOURA, 2))
        self.assertEqual(db.parse(r["clock_at"]), F.at(2026, 10, 20, 13, 0))

    def test_ticket_closed(self):
        self.assertEqual(flow.ticket_closed(F.ROOM), 1)
        self.assertEqual(db.request(self.rid)["state"], "closed_with_ticket")
        self.clock.t = F.at(2026, 10, 22, 12, 0)
        flow.tick()
        self.assertEqual(db.q("SELECT * FROM rrdesk_misses"), [])


class Ladder(unittest.TestCase):
    def setUp(self):
        F.setup(self)
        self.rid = sam_asks(self)["request"]
        F.deliver_all()

    def tick_at(self, *t):
        self.clock.t = F.at(*t)
        return flow.tick()

    def test_each_step_once(self):
        self.tick_at(2026, 10, 20, 12, 31)
        self.tick_at(2026, 10, 20, 12, 32)                 # a second (overlapping) tick
        self.assertEqual([r["ref"] for r in F.queued("post", "ladder:")], ["ladder:%d:R1" % self.rid])
        self.tick_at(2026, 10, 20, 13, 1)
        self.assertEqual(len(F.queued("dm", "ladderdm:")), 1)        # R2 also DMs the owner

    def test_downtime_sends_one_reminder_then_the_miss(self):
        self.tick_at(2026, 10, 20, 15, 0)                  # asleep through R1, R2 and the miss time
        refs = [r["ref"] for r in F.queued("post", "ladder:")]
        self.assertEqual(refs, ["ladder:%d:R2" % self.rid])  # no backlog burst, and no miss first
        self.assertIsNone(db.miss(self.rid))
        self.tick_at(2026, 10, 20, 15, 20)
        self.assertIsNone(db.miss(self.rid))               # 30 working minutes after the reminder
        self.tick_at(2026, 10, 20, 15, 31)
        m = db.miss(self.rid)
        self.assertEqual((m["owner_did"], m["eligible"]), (F.NASSER, 1))
        self.assertEqual(F.queued("post", "ladder:%d:MISS" % self.rid), [])   # never in the shared room
        self.assertTrue(F.queued("dm", "missdm:"))

    def test_closed_or_deleted_room_ends_requests_without_a_miss(self):
        self.state["rec"]["status"] = "closed"             # the close hook timed out / never ran
        self.tick_at(2026, 10, 22, 12, 0)
        self.assertEqual(db.request(self.rid)["state"], "closed_with_ticket")
        self.assertEqual(db.q("SELECT * FROM rrdesk_misses"), [])

    def test_silent_outside_working_hours(self):
        self.tick_at(2026, 10, 21, 3, 0)
        self.assertEqual(F.queued("post", "ladder:"), [])

    def test_acknowledged_ladder_and_d2_watchdog(self):
        flow.press("ack", db.request(self.rid)["card_message_id"], {"did": F.NASSER, "name": "Nasser"})
        self.tick_at(2026, 10, 20, 20, 1)
        self.assertEqual([r["ref"] for r in F.queued("post", "ladder:")], ["ladder:%d:D2" % self.rid])
        wd = F.queued("room", "ladderwd:")
        self.assertEqual(wd[0]["payload"]["channel_name"], "غرفة-المراقبة")

    def test_admin_owner_is_reminded_never_missed_eligible(self):
        flow.remember_admin(F.NASSER, True)
        self.tick_at(2026, 10, 20, 15, 0)                  # the reminder
        self.tick_at(2026, 10, 20, 15, 31)                 # the miss
        self.assertEqual(db.miss(self.rid)["eligible"], 0)


class LateOpen(unittest.TestCase):
    """Reviewer finding 1: a request opened hours after Sam asked must not start overdue."""

    def setUp(self):
        F.setup(self)

    def test_yes_hours_later_starts_the_clock_at_the_press_and_counts_earlier_replies(self):
        sam_asks(self, mode="confirm")                      # 12:00 — Sam is asked «Is this a request?»
        F.fake_model(self)
        self.clock.t = F.at(2026, 10, 20, 12, 5)
        flow.on_message(F.msg("t1", "ابشر", author=F.NASSER, name="Nasser", at_=self.clock.t))
        F.deliver_all()
        self.clock.t = F.at(2026, 10, 20, 16, 0)
        ok, _ = flow.press("q_yes", "p:tr:s1", {"did": F.SAM, "name": "Sam"}, {}, self.clock.t)
        self.assertTrue(ok)
        r = db.request_by_source("s1")
        self.assertEqual(db.parse(r["clock_at"]), F.at(2026, 10, 20, 16, 0))
        self.assertEqual(r["state"], "acknowledged")        # Nasser's 12:05 reply counts
        F.deliver_all()
        self.clock.t = F.at(2026, 10, 20, 16, 1)
        flow.tick()
        self.assertEqual(db.ladder_sent(r["id"]), set())     # nothing overdue
        self.assertIsNone(db.miss(r["id"]))

    def test_pin_on_an_old_message(self):
        F.fake_model(self, classify=dict(F.REQ_CLASSIFY, is_request=False, confidence=0.1))
        flow.on_message(F.msg("p1", "need the invoice", at_=F.at(2026, 10, 18, 12, 0)))
        req = flow.on_pin(F.ROOM, None, "p1", F.SAM, F.SAM, "need the invoice",
                          F.at(2026, 10, 18, 12, 0), F.at(2026, 10, 20, 12, 0))
        self.assertEqual(db.parse(req["clock_at"]), F.at(2026, 10, 20, 12, 0))


class Shift(unittest.TestCase):
    def setUp(self):
        F.setup(self)

    def test_midnight_hand_over_uses_the_shift_and_restarts_the_clock(self):
        self.clock.t = F.at(2026, 10, 20, 22, 0)
        rid = sam_asks(self, at_=self.clock.t)["request"]
        F.deliver_all()
        from rrdesk.host import HOST
        HOST.off_today = lambda name, day: name == "ناصر" and day.isoformat() == "2026-10-21"
        self.clock.t = F.at(2026, 10, 21, 0, 5)            # still the 20th's shift
        flow.tick()
        self.assertEqual(db.request(rid)["owner_did"], F.NASSER)
        self.clock.t = F.at(2026, 10, 21, 11, 0)           # the 21st's shift: hand-over
        flow.tick()
        r = db.request(rid)
        self.assertEqual((r["owner_did"], r["gen"]), (F.NOURA, 2))
        self.assertEqual(db.parse(r["clock_at"]), F.at(2026, 10, 21, 11, 0))
        self.assertIsNone(db.miss(rid))

    def test_work_day(self):
        from rrdesk import engine as E
        self.assertEqual(E.work_day(F.at(2026, 10, 21, 1, 20)).isoformat(), "2026-10-20")
        self.assertEqual(E.work_day(F.at(2026, 10, 21, 1, 30)).isoformat(), "2026-10-21")


class DetectionWithoutTranslation(unittest.TestCase):
    def setUp(self):
        F.setup(self)

    def test_translation_off_still_detects(self):
        flow.set_translate(F.ROOM, None, False, F.SAM, "Sam", False)
        rep = sam_asks(self, mode="auto")
        self.assertTrue(rep.get("classified"))
        self.assertTrue(rep.get("request"))
        self.assertEqual(F.queued("post", "tr:"), [])

    def test_translation_off_confirm_mode_posts_the_question(self):
        flow.set_translate(F.ROOM, None, False, F.SAM, "Sam", False)
        sam_asks(self, mode="confirm")
        q = F.queued("post", "q:")
        self.assertEqual([b["custom_id"] for b in q[0]["payload"]["buttons"]], ["rd:qyes", "rd:qno"])
        F.deliver_all()
        ok, _ = flow.press("q_yes", "p:q:s1", {"did": F.SAM, "name": "Sam"})
        self.assertTrue(ok)

    def test_failed_translation_is_retried_by_an_edit(self):
        from rrdesk import translate as T

        def boom(*a, **k):
            raise T.TranslateFailed("timeout")
        T.call_model = boom
        flow.on_message(F.msg("m9", "الفاتورة بالطريق", author=F.NASSER))
        self.assertIsNone(db.translation("m9"))
        F.fake_model(self)
        self.assertEqual(flow.on_edit(F.msg("m9", "الفاتورة بالطريق الحين", author=F.NASSER)), "model")
        self.assertTrue(F.queued("post", "tr:m9"))


class OutboxAndBoard(unittest.TestCase):
    def setUp(self):
        F.setup(self)

    def test_backoff_and_double_drain(self):
        db.enqueue("x1", "post", {"channel_id": F.ROOM, "content": "hi"}, F.at(2026, 10, 20, 12))
        calls = []

        async def failing(kind, payload):
            calls.append(kind)
            raise RuntimeError("discord 503")
        now = [F.at(2026, 10, 20, 12, 0)]

        async def run():
            return await outbox.drain(failing, now_fn=lambda: now[0])
        asyncio.run(run())
        row = db.outbox("x1")
        self.assertEqual((row["state"], db.parse(row["next_at"])), ("queued", F.at(2026, 10, 20, 12, 1)))
        now[0] = F.at(2026, 10, 20, 12, 1)
        asyncio.run(run())
        self.assertEqual(db.parse(db.outbox("x1")["next_at"]), F.at(2026, 10, 20, 12, 6))

        async def ok(kind, payload):
            calls.append("ok")
            return {"message_ids": ["m"]}
        now[0] = F.at(2026, 10, 20, 12, 6)

        async def both():
            return await asyncio.gather(outbox.drain(ok, now_fn=lambda: now[0]),
                                        outbox.drain(ok, now_fn=lambda: now[0]))
        asyncio.run(both())
        self.assertEqual(calls.count("ok"), 1)              # two drainers, one post
        self.assertEqual(db.outbox("x1")["state"], "done")

    def test_claim_is_atomic(self):
        db.enqueue("x2", "post", {}, F.at(2026, 10, 20, 12))
        oid = db.outbox("x2")["id"]
        t = F.at(2026, 10, 20, 12, 0)
        self.assertTrue(db.claim_outbox(oid, t))
        self.assertFalse(db.claim_outbox(oid, t))
        self.assertFalse(db.claim_outbox(oid, t + datetime.timedelta(minutes=6)))  # maybe just slow
        self.assertTrue(db.claim_outbox(oid, t + datetime.timedelta(minutes=31)))  # crashed worker

    def test_board_is_edited_in_place(self):
        sam_asks(self)
        self.clock.t = F.at(2026, 10, 20, 12, 1)
        flow._board(self.clock.t)
        F.deliver_all()
        first = db.setting("board_mid")
        self.assertTrue(first.startswith("p:board:" + db.setting("board_hash")))
        self.assertEqual(flow._board(self.clock.t), 0)      # nothing changed → nothing sent
        flow.press("ack", db.request(1)["card_message_id"], {"did": F.NASSER, "name": "Nasser"})
        flow._board(self.clock.t)
        b = F.queued("board")[-1]["payload"]
        self.assertEqual(b["message_id"], first)

    def test_board_refreshes_when_it_returns_to_an_earlier_state(self):
        empty = flow._board(F.at(2026, 10, 20, 12, 0))
        F.deliver_all()
        rid = sam_asks(self)["request"]
        F.deliver_all()
        self.assertEqual(flow._board(F.at(2026, 10, 20, 12, 1)), 1)
        flow.ticket_closed(F.ROOM)
        self.assertEqual(flow._board(F.at(2026, 10, 20, 12, 2)), 1)   # empty again → re-published
        self.assertEqual(len(F.queued("board")), 3)
        self.assertEqual(empty, 1)
        self.assertTrue(rid)


class Defaults(unittest.TestCase):
    def test_shipped_sla_is_the_calibrated_one(self):
        F.setup(self)
        db.set_setting("sla:resp_min", None)
        db.set_setting("sla:deliv_min", None)
        self.assertEqual(flow.sla_cfg(), {"resp_min": 90, "deliv_min": 240, "urg_resp_min": 30,
                                          "urg_deliv_min": 180})

    def test_switch_defaults_are_correct_as_shipped(self):
        F.setup(self)
        for k in ("RRDESK_TRANSLATE", "RRDESK_WARN_LIVE", "RRDESK_FORCE_OFF"):
            os.environ.pop(k, None)
        self.assertTrue(flow.switch("translate"))
        self.assertTrue(flow.switch("requests"))
        self.assertTrue(flow.switch("ladder"))
        self.assertFalse(flow.switch("warn_live"))       # money is dry-run on deploy
        self.assertFalse(flow.switch("force_off"))
        self.assertEqual(flow.detect_mode(), "confirm")
        os.environ["RRDESK_WARN_LIVE"] = "1"
        try:
            self.assertTrue(flow.switch("warn_live"))
            flow.set_switch("warn_live", False, "t")      # the stored switch wins over env
            self.assertFalse(flow.switch("warn_live"))
        finally:
            os.environ.pop("RRDESK_WARN_LIVE", None)

    def test_sam_follow_up_is_logged_on_the_open_request(self):
        F.setup(self)
        rid = sam_asks(self)["request"]
        F.fake_model(self, classify=dict(F.REQ_CLASSIFY, is_request=False, confidence=0.1))
        rep = flow.on_message(F.msg("f1", "following up on this @Nasser", mentions=(F.NASSER,)))
        self.assertTrue(rep.get("followup"))
        self.assertTrue([e for e in db.events(request_id=rid) if e["kind"] == "sam_followup"])


class WhyAndHealth(unittest.TestCase):
    def setUp(self):
        F.setup(self)

    def test_why_explains_each_step(self):
        sam_asks(self)
        F.deliver_all()
        self.clock.t = F.at(2026, 10, 20, 12, 31)
        flow.tick()
        text = chr(10).join(flow.why(F.ROOM))
        self.assertIn("R1 @", text)
        self.assertIn("sent", text)
        self.assertIn("rule 1", text)

    def test_health_has_counts_only(self):
        sam_asks(self)
        h = flow.health()
        self.assertEqual(h["open_requests"], 1)
        self.assertTrue(h["sam_resolved"])
        blob = str(h)
        self.assertNotIn("Nasser", blob)
        self.assertNotIn("photos", blob)


if __name__ == "__main__":
    unittest.main()
