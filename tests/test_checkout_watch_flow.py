# -*- coding: utf-8 -*-
"""
«متابعة الخروج» — the flow, end to end, against a fake Discord + fake Hostaway, a temp
brain.db and an injected `now`. No network.

Locked here:
  * idempotency — two ticks and a simulated redeploy post the card once; /checkout-start
    twice converts once
  * Airbnb — sent on the first «ما رد» and with the 3rd reminder, never a 3rd time; a block is
    logged once and never retried
  * oujact wiring — ✅ guest_confirmed · ⛔ late late_checkout · ⛔ other inside ·
    ما رد no_answer · 🚨 inside
  * demo isolation — no guest send, no oujact write, not on the board / report / stats;
    demo-end deletes only demo rows
  * WhatsApp — the presser's name; no phone → the Airbnb link
  * board — content hash (no edit when unchanged); the 17:00 summary once per day across two
    ticks and a restart

Run: python3 -m unittest tests.test_checkout_watch_flow
"""

import asyncio
import datetime
import os
import sys
import tempfile
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                  # noqa: E402
from checkout import db, engine, flow, texts                 # noqa: E402
from checkout.host import HOST                                # noqa: E402

TZ = engine.tz()
DAY = "2026-09-26"
LID, LID2 = 101, 202
WK, WK2 = "%d:%s" % (LID, DAY), "%d:%s" % (LID2, DAY)


def at(hh, mm=0):
    return datetime.datetime(2026, 9, 26, hh, mm, tzinfo=TZ)


def run(coro):
    return asyncio.run(coro)


def wa_from_phone(phone):
    """Mirror of bot._wa_from_phone (the bot test proves the real one is what gets wired)."""
    d = "".join(c for c in str(phone or "") if c.isdigit())
    if d.startswith("00"):
        d = d[2:]
    if d.startswith("0") and len(d) == 10:
        d = "966" + d[1:]
    return ("wa.me/" + d) if len(d) >= 8 else ""


class FakeDiscord:
    def __init__(self):
        self.n = 1000
        self.posts, self.edits, self.pins = [], [], []
        self.board = "900"
        self.missing = set()

    async def post(self, channel_id, text=None, embed=None, buttons=None, demo=False, pin=False,
                   mentions=True):
        self.n += 1
        self.posts.append({"id": str(self.n), "channel": str(channel_id), "text": text,
                           "embed": embed, "buttons": list(buttons or []), "demo": demo})
        if pin:
            self.pins.append(str(self.n))
        return str(self.n)

    async def edit(self, channel_id, message_id, text=None, embed=None, buttons=None, demo=False,
                   disabled=False):
        if str(message_id) in self.missing:
            return False
        self.edits.append({"channel": str(channel_id), "id": str(message_id), "text": text,
                           "embed": embed, "buttons": buttons, "disabled": disabled})
        return True

    async def board_channel(self):
        return self.board

    def texts_in(self, channel):
        return [p["text"] or "" for p in self.posts if p["channel"] == str(channel)]


class FlowCase(unittest.TestCase):
    ENV = {"CHECKOUT_WATCH_LIVE": "0", "CHECKOUT_WATCH_AIRBNB": "1", "CHECKOUT_REMIND_MIN": "30",
           "CHECKOUT_DEADLINE": "17:00", "CHECKOUT_QUIET_FROM": "23:00",
           "CHECKOUT_QUIET_TO": "08:00"}

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in self.ENV}
        os.environ.update(self.ENV)
        self.tmp = tempfile.mkdtemp(prefix="cw_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        flow.reset_cache()
        self.d = FakeDiscord()
        self.now = at(9)
        self.sent, self.oujact, self.oulog = [], [], []
        self.send_result = {"status": "success"}
        self.status = {}                    # lid -> cleaning status
        self.turnover_calls = 0
        self.tovers = [
            {"lid": LID, "day": DAY, "res_id": "5001", "unit": "Ouja | الملقا 1",
             "guest": "Sara Ahmed", "phone": "0501234567", "conversation_id": "c1",
             "channel_name": "airbnbOfficial", "checkout_at": at(12).isoformat(),
             "checkin_at": at(16).isoformat(), "clean_minutes": 40},
            {"lid": LID2, "day": DAY, "res_id": "5002", "unit": "Ouja | النرجس 2",
             "guest": "Omar", "phone": "", "conversation_id": "c2",
             "channel_name": "airbnbOfficial", "checkout_at": at(11).isoformat(),
             "checkin_at": None, "clean_minutes": 40},
        ]
        self.chans = [{"channel_id": "501", "key": WK, "review": False},
                      {"channel_id": "502", "key": WK2, "review": False}]

        def turnovers():
            self.turnover_calls += 1
            return list(self.tovers)

        def send(cid, body):
            self.sent.append((cid, body))
            return self.send_result

        HOST.now = lambda: self.now
        HOST.today_turnovers = turnovers
        HOST.send_guest = send
        HOST.guest_links = lambda rid: [("https://wa.me/1", "📱"),
                                        ("https://www.airbnb.com/hosting/stay/ABC123", "💬 حجز الضيف في Airbnb")]
        HOST.channels = lambda: list(self.chans)
        HOST.cover = lambda lid, day, ch: {"name": "ناصر", "did": "111", "role_id": ""}
        HOST.cleaning_status = lambda lid, day, ch: self.status.get(int(lid), "none")
        HOST.early_hint = lambda lid: False
        HOST.early_checkin = lambda lid, day: False
        HOST.set_oujact_state = lambda lid, day, st, by: self.oujact.append((lid, day, st, by))
        HOST.log_oujact = lambda lid, day, act, note, by: self.oulog.append((lid, act, by))
        HOST.wa_number = wa_from_phone
        HOST.clean_minutes_default = 40
        HOST.post, HOST.edit, HOST.board_channel = self.d.post, self.d.edit, self.d.board_channel
        HOST.is_live = None

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # helpers
    def start(self, now=None):
        return run(flow.start("admin", now or self.now))

    def tick(self, now):
        self.now = now
        return run(flow.tick(now))

    def cards(self, channel="501"):
        return [p for p in self.d.posts if p["channel"] == channel and p["embed"]
                and "متابعة الخروج" in p["embed"]["title"]]

    def kinds(self, wk=WK):
        return [e["kind"] for e in db.events(wk)]


# ============================================================== idempotency

class TestIdempotency(FlowCase):

    def test_off_by_default_posts_nothing(self):
        rep = self.tick(at(12, 30))
        self.assertEqual(rep, {"skipped": "off"})
        self.assertEqual(self.d.posts, [])

    def test_two_ticks_and_a_redeploy_post_the_card_once(self):
        self.start(at(9))
        self.assertEqual(len(self.cards()), 1)
        self.tick(at(9, 2))
        db.reset_init_cache()              # simulated redeploy: fresh process state …
        flow.reset_cache()
        db.invalidate()
        self.tick(at(9, 4))                # … the stored switch keeps it live, the row keeps it once
        self.assertEqual(len(self.cards()), 1)
        self.assertEqual(len(self.cards("502")), 1)
        self.assertEqual(self.kinds().count("converted"), 1)

    def test_checkout_start_twice_converts_once(self):
        r1 = self.start(at(9))
        r2 = self.start(at(9, 1))
        self.assertEqual(sorted(r1["posted"]), sorted([WK, WK2]))
        self.assertEqual(r2["posted"], [])
        self.assertEqual(len(self.cards()), 1)

    def test_start_pings_checkouts_already_past_and_lists_rooms_missing(self):
        self.tovers.append({"lid": 303, "day": DAY, "res_id": "5003", "unit": "Ouja | بلا قناة",
                            "guest": "X", "phone": "", "conversation_id": "",
                            "channel_name": "", "checkout_at": at(12).isoformat(),
                            "checkin_at": None, "clean_minutes": 40})
        rep = self.start(at(11, 30))       # 202 checked out at 11:00, 101 at 12:00
        self.assertEqual(rep["pinged"], [WK2])
        self.assertEqual(rep["no_channel"], ["Ouja | بلا قناة"])
        pings = [t for t in self.d.texts_in("502") if "وقت خروج" in t]
        self.assertEqual(len(pings), 1)
        self.assertTrue(pings[0].startswith("<@111> 🚪 وقت خروج **Omar**"))
        self.assertEqual(self.d.texts_in("501"), [""])          # the card only — not yet

    def test_two_rooms_with_one_key_never_make_the_card_hop(self):
        self.chans.append({"channel_id": "599", "key": WK, "review": False})   # a duplicate room
        self.start(at(9))
        for m in (2, 4, 6, 8):
            self.tick(at(9, m))
        self.assertEqual(len(self.cards("501")) + len(self.cards("599")), 1)

    def test_card_follows_a_reopened_room(self):
        self.start(at(9))
        self.chans = [{"channel_id": "601", "key": WK, "review": False}]
        self.tick(at(9, 2))
        self.assertEqual(len(self.cards("601")), 1)
        self.assertEqual(db.item(WK)["channel_id"], "601")

    def test_cleaned_rooms_are_skipped(self):
        self.status[LID] = "submitted"
        rep = self.start(at(9))
        self.assertEqual(rep["cleaned"], [WK])
        self.assertIsNone(db.item(WK))

    def test_no_card_before_eight_on_the_automatic_tick(self):
        db.set_setting("live", "1")
        self.tick(at(7, 58))
        self.assertEqual(self.cards(), [])
        self.tick(at(8, 0))
        self.assertEqual(len(self.cards()), 1)

    def test_ping_exactly_at_checkout_then_reminders_every_30(self):
        self.start(at(9))
        self.tick(at(11, 58))
        self.assertNotIn("ping", self.kinds())
        self.tick(at(12, 0))
        self.assertEqual(self.kinds().count("ping"), 1)
        self.tick(at(12, 2))
        self.assertEqual(self.kinds().count("ping"), 1)
        self.tick(at(12, 30))
        self.assertEqual(self.kinds().count("remind"), 1)

    def test_stop_silences_the_tick_but_buttons_still_record(self):
        self.start(at(9))
        flow.stop("admin")
        self.tick(at(12, 0))
        self.assertNotIn("ping", self.kinds())
        res = run(flow.answer_yes(WK, "نورة", "222", at(12, 5)))
        self.assertTrue(res["ok"])
        self.assertEqual(db.item(WK)["state"], engine.OUT)

    def test_stored_switch_beats_env(self):
        os.environ["CHECKOUT_WATCH_LIVE"] = "1"
        db.invalidate()
        self.assertTrue(flow.live())
        db.set_setting("live", "0", "admin")
        self.assertFalse(flow.live())

    def test_hostaway_is_read_once_per_five_minutes(self):
        self.start(at(9))
        calls = self.turnover_calls
        self.tick(at(9, 2))
        self.tick(at(9, 4))
        self.assertEqual(self.turnover_calls, calls)
        self.tick(at(9, 6))
        self.assertEqual(self.turnover_calls, calls + 1)


# ============================================================== the answers

class TestAnswers(FlowCase):

    def setUp(self):
        super().setUp()
        self.start(at(9))
        self.tick(at(12, 0))

    def test_yes_records_the_presser_and_tells_the_team(self):
        res = run(flow.answer_yes(WK, "نورة", "222", at(12, 40)))
        self.assertTrue(res["ok"])
        row = db.item(WK)
        self.assertEqual((row["state"], row["state_by"], row["state_by_did"]),
                         (engine.OUT, "نورة", "222"))
        self.assertIn(texts.YES_POST, self.d.texts_in("501"))
        card_edit = [e for e in self.d.edits if e["id"] == row["card_message_id"]][-1]
        self.assertIn("أكده نورة 12:40", card_edit["embed"]["description"])

    def test_second_press_is_told_who_answered_first(self):
        run(flow.answer_yes(WK, "نورة", "222", at(12, 40)))
        res = run(flow.answer_noanswer(WK, "ناصر", "111", at(12, 41)))
        self.assertFalse(res["ok"])
        self.assertIn("انحفظت قبلك من نورة", res["message"])
        self.assertEqual(self.kinds().count("noanswer"), 0)

    def test_no_needs_a_valid_time_and_never_guesses(self):
        res = run(flow.answer_no(WK, "ناصر", "111", "packing", "", "custom", "11:00", at(12, 5)))
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "past")
        self.assertEqual(db.item(WK)["state"], engine.ASKING)
        res = run(flow.answer_no(WK, "ناصر", "111", "other", "", "1h", None, at(12, 5)))
        self.assertEqual(res["error"], "reason_text")

    def test_no_then_reask_at_the_promised_time(self):
        run(flow.answer_no(WK, "ناصر", "111", "late_ask", "", "custom", "15:30", at(12, 5)))
        row = db.item(WK)
        self.assertEqual(row["state"], engine.INSIDE)
        desc = [e for e in self.d.edits if e["id"] == row["card_message_id"]][-1]["embed"]["description"]
        self.assertIn("🔴 لو طلع 15:30 ما نلحق ننظف قبل 16:00 — أقصى وقت نقدر نعطيه 15:20", desc)
        self.assertIn("أقصى تأخير نقدر نعطيه 15:20", desc)
        self.tick(at(15, 28))
        self.assertNotIn("reask", self.kinds())
        self.tick(at(15, 30))
        self.assertEqual(self.kinds().count("reask"), 1)
        self.assertEqual(db.item(WK)["state"], engine.ASKING)

    def test_surprise_is_attributed_to_the_yes_presser(self):
        run(flow.answer_yes(WK, "نورة", "222", at(12, 40)))
        res = run(flow.surprise(WK, "خالد", "333", at(13, 10)))
        self.assertTrue(res["ok"])
        ev = db.events(WK, ["surprise"])[0]
        self.assertEqual((ev["actor"], ev["detail"]), ("خالد", "نورة"))
        self.assertEqual(db.item(WK)["state"], engine.INSIDE)
        chan = self.d.texts_in("501")
        self.assertTrue(any(t.startswith("🚨 الفريق وصل والضيف داخل — <@111>") for t in chan))
        self.assertIn("reask", self.kinds())

    def test_reminder_disables_the_previous_prompt(self):
        run(flow.answer_noanswer(WK, "ناصر", "111", at(12, 5)))
        self.tick(at(12, 35))
        ping_id = db.events(WK, ["ping"])[0]["detail"]
        self.assertTrue(any(e["id"] == ping_id and e["disabled"] for e in self.d.edits))
        remind_posts = [p for p in self.d.posts if (p["text"] or "").startswith("⏰")]
        self.assertEqual(remind_posts[-1]["buttons"], ["yes", "noanswer", "no", "wa"])
        self.assertIn("الضيف ما رد من 30 دقيقة", remind_posts[-1]["text"])

    def test_before_out_warning_when_submitted_unconfirmed(self):
        self.assertTrue(flow.submitted_before_out(WK, "cleaner"))
        self.assertEqual(db.events(WK, ["submitted"])[0]["detail"], "before_out")
        run(flow.answer_yes(WK2, "نورة", "222", at(12, 1)))
        self.assertFalse(flow.submitted_before_out(WK2, "cleaner"))

    def test_cleaning_link_up(self):
        self.status[LID] = "submitted"
        self.tick(at(13))
        self.assertEqual(db.item(WK)["state"], engine.CLEANED)
        self.status[LID] = "approved"
        self.tick(at(13, 2))
        self.tick(at(13, 4))
        self.assertEqual(db.item(WK)["state"], engine.APPROVED)
        self.assertEqual(self.kinds().count("submitted"), 1)
        self.assertEqual(self.kinds().count("approved"), 1)

    def test_deleted_room_after_submit_counts_as_approved(self):
        self.status[LID] = "submitted"
        self.tick(at(13))
        self.status[LID] = "none"
        self.chans = [c for c in self.chans if c["key"] != WK]
        self.tick(at(13, 2))
        self.assertEqual(db.item(WK)["state"], engine.APPROVED)


# ============================================================== Airbnb (§6)

class TestAirbnb(FlowCase):

    def setUp(self):
        super().setUp()
        self.start(at(9))
        self.tick(at(12, 0))

    def test_first_noanswer_then_third_reminder_never_a_third(self):
        run(flow.answer_noanswer(WK, "ناصر", "111", at(12, 5)))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0][0], "c1")
        for t in (at(12, 35), at(13, 5)):
            self.tick(t)
        self.assertEqual(len(self.sent), 1)                     # reminders 1 and 2: nothing
        self.tick(at(13, 35))                                   # reminder 3 (+90)
        self.assertEqual(len(self.sent), 2)
        self.assertNotEqual(self.sent[0][1], self.sent[1][1])   # a duplicate would be suppressed
        for t in (at(14, 5), at(14, 35), at(15, 5)):
            self.tick(t)
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(self.kinds().count("airbnb_sent"), 2)
        self.assertEqual(db.item(WK)["remind_count"], 6)

    def test_a_firewall_block_is_logged_once_and_never_retried(self):
        self.send_result = "firewall_blocked"
        run(flow.answer_noanswer(WK, "ناصر", "111", at(12, 5)))
        for t in (at(12, 35), at(13, 5), at(13, 35), at(14, 5)):
            self.tick(t)
        self.assertEqual(len(self.sent), 1)
        fails = db.events(WK, ["airbnb_failed"])
        self.assertEqual([e["detail"] for e in fails], ["firewall_blocked"])
        desc = [e for e in self.d.edits if e["embed"]][-1]["embed"]["description"]
        self.assertIn("ما انرسلت رسالة Airbnb (firewall_blocked)", desc)

    def test_an_exception_is_logged_not_raised(self):
        def boom(cid, body):
            raise RuntimeError("hostaway down")
        HOST.send_guest = boom
        res = run(flow.answer_noanswer(WK, "ناصر", "111", at(12, 5)))
        self.assertTrue(res["ok"])
        self.assertIn("hostaway down", db.events(WK, ["airbnb_failed"])[0]["detail"])

    def test_switch_off_sends_nothing(self):
        os.environ["CHECKOUT_WATCH_AIRBNB"] = "0"
        run(flow.answer_noanswer(WK, "ناصر", "111", at(12, 5)))
        self.assertEqual(self.sent, [])


# ============================================================== oujact wiring (§7)

class TestOujactWiring(FlowCase):

    def setUp(self):
        super().setUp()
        self.start(at(9))
        self.tick(at(12, 0))

    def last(self):
        return self.oujact[-1][2]

    def test_yes(self):
        run(flow.answer_yes(WK, "نورة", "222", at(12, 5)))
        self.assertEqual(self.oujact[-1], (LID, DAY, "guest_confirmed", "نورة"))
        self.assertEqual(self.oulog[-1], (LID, "guest_out", "نورة"))

    def test_no_late(self):
        for code in ("late_ok", "late_ask"):
            db.update_item(WK, {"state": engine.ASKING})
            run(flow.answer_no(WK, "ناصر", "111", code, "", "1h", None, at(12, 5)))
            self.assertEqual(self.last(), "late_checkout")

    def test_no_other_reasons(self):
        for code in ("packing", "unaware", "refuse", "other"):
            db.update_item(WK, {"state": engine.ASKING})
            run(flow.answer_no(WK, "ناصر", "111", code, "x", "1h", None, at(12, 5)))
            self.assertEqual(self.last(), "inside", code)

    def test_noanswer(self):
        run(flow.answer_noanswer(WK, "ناصر", "111", at(12, 5)))
        self.assertEqual(self.last(), "no_answer")

    def test_surprise(self):
        run(flow.answer_yes(WK, "نورة", "222", at(12, 5)))
        run(flow.surprise(WK, "خالد", "333", at(12, 50)))
        self.assertEqual(self.last(), "inside")


# ============================================================== WhatsApp (§5.5)

class TestWhatsApp(FlowCase):

    def setUp(self):
        super().setUp()
        self.start(at(9))

    def test_link_carries_the_presser_name_and_normalised_phone(self):
        res = run(flow.whatsapp(WK, "نورة", "222", at(12)))
        self.assertTrue(res["url"].startswith("https://wa.me/966501234567?text="))
        body = urllib.parse.unquote(res["url"].split("text=", 1)[1])
        self.assertIn("معك نورة من عوجا", body)
        self.assertIn("this is نورة from Ouja", body)
        self.assertIn("مرحبا Sara", body)
        self.assertEqual(db.events(WK, ["wa_link"])[0]["actor"], "نورة")

    def test_no_phone_falls_back_to_the_airbnb_link(self):
        res = run(flow.whatsapp(WK2, "نورة", "222", at(12)))
        self.assertEqual(res["url"], "")
        self.assertEqual(res["message"], texts.WA_NO_PHONE)
        self.assertEqual(res["links"], [("https://www.airbnb.com/hosting/stay/ABC123",
                                         "💬 حجز الضيف في Airbnb")])


# ============================================================== board + 17:00 (§10)

class TestBoard(FlowCase):

    def board_posts(self):
        return [p for p in self.d.posts if p["channel"] == "900"]

    def board_edits(self):
        return [e for e in self.d.edits if e["channel"] == "900"]

    def test_no_edit_when_unchanged(self):
        self.start(at(9))
        self.assertEqual(len(self.board_posts()), 1)
        self.tick(at(9, 2))
        self.tick(at(9, 4))
        self.assertEqual(len(self.board_posts()), 1)
        self.assertEqual(self.board_edits(), [])
        run(flow.answer_yes(WK, "نورة", "222", at(9, 5)))
        self.assertEqual(len(self.board_edits()), 1)
        txt = self.board_edits()[-1]["text"]
        self.assertIn("✅ طلع — ننظف", txt)
        self.assertIn("أكده نورة 09:05", txt)
        self.assertIn("<#501>", txt)
        self.assertIn("🔴 دخول 16:00", txt)

    def test_board_reposts_if_its_message_was_deleted(self):
        self.start(at(9))
        mid = self.board_posts()[0]["id"]
        self.d.missing.add(mid)
        run(flow.answer_yes(WK, "نورة", "222", at(9, 5)))
        self.assertEqual(len(self.board_posts()), 2)
        self.assertEqual(db.board_message_ids(), [self.board_posts()[1]["id"]])

    def test_summary_once_per_day_across_ticks_and_a_restart(self):
        self.start(at(9))
        run(flow.answer_yes(WK, "نورة", "222", at(12, 5)))
        self.status[LID] = "approved"
        self.tick(at(15))
        self.tick(at(16, 58))
        self.assertEqual([p for p in self.board_posts() if "ملخص" in (p["text"] or "")], [])
        self.tick(at(17, 0))
        self.tick(at(17, 2))
        db.reset_init_cache()               # restart
        flow.reset_cache()
        self.tick(at(17, 4))
        sums = [p["text"] for p in self.board_posts() if "ملخص" in (p["text"] or "")]
        self.assertEqual(len(sums), 1)
        self.assertIn("اليوم 2 خروج · معتمدة قبل ٥: 1 · متأخرة: Ouja | النرجس 2", sums[0])
        self.assertNotIn("ناصر", sums[0])
        self.assertNotIn("نورة", sums[0])
        self.assertEqual(self.kinds(WK2).count("deadline_miss"), 1)
        self.assertEqual(self.kinds(WK).count("deadline_miss"), 0)

    def test_no_summary_while_stopped(self):
        self.start(at(9))
        flow.stop("admin")
        self.tick(at(17, 5))
        self.assertFalse(db.daily_claimed(DAY))


# ============================================================== risk + report

class TestRiskAndReport(FlowCase):

    def test_risk_is_computed_while_stopped_and_orders_red_first(self):
        self.now = at(12, 30)
        rows = run(flow.risk_rows(at(12, 30)))
        self.assertEqual(len(rows), 2)
        chunks = flow.risk_chunks(rows, at(12, 30))
        text = "".join(chunks)
        self.assertIn("اليوم 2 خروج · 1 منها فيها دخول اليوم", text)
        self.assertIn("🟠 **Ouja | الملقا 1**", text)           # unconfirmed with a check-in
        self.assertLess(text.index("🟠"), text.index("🟢"))

    def test_report_per_person(self):
        self.start(at(9))
        self.tick(at(12, 0))
        run(flow.answer_yes(WK, "نورة", "222", at(12, 20)))
        run(flow.answer_yes(WK2, "نورة", "222", at(12, 0)))
        text = "".join(flow.report_text(at(18), 1))
        self.assertIn("**ناصر** — خروج: 2", text)
        self.assertIn("للإدارة فقط", text)


# ============================================================== demo (§9)

class TestDemo(FlowCase):

    CH = {"yes": "701", "noanswer": "702", "no": "703", "surprise": "704", "risk": "705"}

    def setUp(self):
        super().setUp()
        run(flow.demo_setup(self.CH, "فيصل", "999", at(12)))

    def demo_row(self, n):
        return db.item("demo:%d" % n)

    def test_setup_posts_steps_sample_and_real_card(self):
        self.assertEqual(len(db.demo_items()), 4)
        for scen, ch in self.CH.items():
            posts = [p for p in self.d.posts if p["channel"] == ch]
            self.assertEqual(posts[0]["embed"]["title"], "📖 خطوات الفيديو")
            self.assertIn(posts[0]["id"], self.d.pins)
            if scen != "risk":
                self.assertIn("🎬 تجربة", posts[1]["embed"]["title"])
                self.assertIn("🎬 تجربة", posts[2]["embed"]["title"])
                self.assertIn("demo_ff", posts[2]["buttons"])
        self.assertIn("خطر اليوم", self.d.texts_in("705")[-1])
        self.assertEqual(db.setting("demo_risk_channel"), "705")

    def test_ff_advances_and_nothing_real_is_touched(self):
        r = run(flow.demo_ff("demo:2", at(12, 1)))
        self.assertEqual(r["action"], "ping")
        run(flow.answer_noanswer("demo:2", "فيصل", "999", at(12, 2)))
        for _ in range(3):
            run(flow.demo_ff("demo:2", at(12, 3)))
        self.assertEqual(self.demo_row(2)["remind_count"], 3)
        previews = [t for t in self.d.texts_in("702") if t.startswith("🎬 تجربة — كان بينرسل")]
        self.assertEqual(len(previews), 2)
        run(flow.demo_ff("demo:4", at(12, 1)))
        run(flow.answer_yes("demo:4", "فيصل", "999", at(12, 2)))
        run(flow.surprise("demo:4", "فيصل", "999", at(12, 3)))
        run(flow.demo_ff("demo:1", at(12, 1)))
        run(flow.answer_yes("demo:1", "فيصل", "999", at(12, 2)))
        self.assertEqual(self.sent, [])                          # no guest message
        self.assertEqual(self.oujact, [])                        # no oujact_checkout.json write
        self.assertEqual(self.oulog, [])
        self.assertEqual([p for p in self.d.posts if p["channel"] == "900"], [])   # no board
        self.assertEqual(db.items_for_day(DAY), [])              # invisible to board/summary
        self.assertEqual(flow.report_text(at(18), 7), ["📈 **تقرير الخروج — آخر 7 أيام** — للإدارة فقط"
                                                      + texts.NL + "ما فيه بيانات للفترة." + texts.NL])

    def test_demo_whatsapp_opens_the_contact_picker(self):
        res = run(flow.whatsapp("demo:1", "فيصل", "999", at(12)))
        self.assertTrue(res["url"].startswith("https://wa.me/?text="))

    def test_demo_no_scenario_shows_the_red_cap(self):
        run(flow.demo_ff("demo:3", at(12, 1)))
        res = run(flow.answer_no("demo:3", "فيصل", "999", "late_ask", "", "3h", None, at(12, 2)))
        self.assertTrue(res["ok"])
        desc = [e for e in self.d.edits if e["channel"] == "703" and e["embed"]][-1]["embed"]["description"]
        self.assertIn("🔴 لو طلع", desc)
        self.assertEqual(run(flow.demo_ff("demo:3", at(12, 3)))["action"], "reask")

    def test_demo_rows_survive_real_ticks_untouched(self):
        self.start(at(12, 5))
        self.assertEqual(self.demo_row(1)["state"], engine.WAITING)
        self.assertNotIn("demo", "".join(p["text"] or "" for p in self.d.posts
                                         if p["channel"] == "900"))

    def test_demo_end_deletes_only_demo_rows(self):
        self.start(at(9))
        real_before = len(db.items_for_day(DAY))
        n = flow.demo_end()
        self.assertEqual(n, 4)
        self.assertEqual(db.demo_items(), [])
        self.assertEqual(len(db.items_for_day(DAY)), real_before)
        self.assertEqual(real_before, 2)
        self.assertTrue(all(not e["work_key"].startswith("demo:") for e in db.events()))

    def test_running_demo_again_resets(self):
        run(flow.demo_ff("demo:1", at(12, 1)))
        run(flow.demo_setup(self.CH, "فيصل", "999", at(12, 5)))
        self.assertEqual(self.demo_row(1)["state"], engine.WAITING)
        self.assertEqual(len(db.demo_items()), 4)


def tearDownModule():
    # bot.py prints at import; flush before unittest writes its summary so the LAST line of
    # the run is the verdict (GATES.md G3 reads only that line).
    sys.stdout.flush()


if __name__ == "__main__":
    unittest.main()
