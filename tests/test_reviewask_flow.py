# -*- coding: utf-8 -*-
"""
«رفع التقييم» — flow + db with a fake HOST, a temp brain.db, no network, no Discord.

Locks (G4): one room per reservation across overlapping ticks, first-final-wins, a matched
review closes from ANY open state, a cancellation closes, /rv/<token> logs wa_opened and 302s to
wa.me with the owner's rendered template — plus the clock end-to-end, care mode, skips with
reasons, dry-run, the board, the monitor report, the 22:00 summary and the template history.

Run: python3 -m unittest tests.test_reviewask_flow
"""

import asyncio
import datetime
import os
import sys
import tempfile
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb  # noqa: E402
from reviewask import db, engine, flow, routes, texts  # noqa: E402
from reviewask.host import HOST  # noqa: E402

TZ = engine.tz()
D = "2026-10-14"


def at(y, m, d, hh=0, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=TZ)


def run(coro):
    return asyncio.run(coro)


class Fake:
    """Every HOST hook, recording what the package asked Discord to do."""

    def __init__(self):
        self.clock = at(2026, 10, 14, 0, 10)
        self.deps = []
        self.reviews = []
        self.rooms = {}            # channel id -> {"name", "topic"}
        self.posts = []            # (channel, text, embed, buttons, mentions)
        self.edits = []
        self.deleted = []
        self.claims = set()
        self.next_id = 9000
        self.mid = 100
        self.tickets_by_lid = {}
        self.recovery = set()
        self.dep_fail = False
        self.res_by_id = {}

    # data
    def departures(self, start, end):
        if self.dep_fail:
            raise RuntimeError("hostaway down")
        return [r for r in self.deps if start <= r["departure"][:10] <= end]

    def reservation(self, rid):
        return self.res_by_id.get(str(rid))

    def get_reviews(self):
        return list(self.reviews)

    def cover(self, lid, day):
        return {"name": "أصيل" if day == D else "نورة", "did": "111" if day == D else "222"}

    def maint_tickets(self, lid):
        return self.tickets_by_lid.get(lid, [])

    # discord
    async def open_room(self, name, topic):
        self.next_id += 1
        self.rooms[str(self.next_id)] = {"name": name, "topic": topic}
        return str(self.next_id)

    def known_rooms(self):
        out = {}
        for cid, r in self.rooms.items():
            rid = engine.topic_reservation(r["topic"])
            if rid:
                out[rid] = cid
        return out

    async def post(self, channel_id, text=None, embed=None, buttons=None, mentions=True):
        self.mid += 1
        self.posts.append((str(channel_id), text, embed, buttons, mentions))
        return str(self.mid)

    async def edit(self, channel_id, message_id, text=None, embed=None, buttons=None,
                   disabled=False):
        self.edits.append((str(channel_id), str(message_id), text, embed, buttons, disabled))
        return True

    async def board(self):
        return "BOARD"

    async def monitor(self):
        return "MONITOR"

    def room_posts(self):
        return [p for p in self.posts if p[0] not in ("BOARD", "MONITOR")]

    def claim(self, key):
        if key in self.claims:
            return False
        self.claims.add(key)
        return True

    def wire(self):
        HOST.now = lambda: self.clock
        HOST.departures = self.departures
        HOST.reservation = self.reservation
        HOST.reviews = self.get_reviews
        HOST.open_ticket_counts = lambda: {}
        HOST.maint_tickets = self.maint_tickets
        HOST.has_recovery = lambda rid: str(rid) in self.recovery
        HOST.cover = self.cover
        HOST.wa_number = lambda p: ("wa.me/" + "".join(c for c in str(p) if c.isdigit())) if p else ""
        HOST.guest_links = lambda rid: [("https://wa.me/1", "wa"),
                                        ("https://www.airbnb.com/hosting/stay/ABC123", "airbnb")]
        HOST.listings = lambda: {1: "Ouja | Narjis 101", 2: "Ouja | Malqa 7", 3: "Ouja | Yasmin 3"}
        HOST.open_room = self.open_room
        HOST.known_rooms = self.known_rooms
        HOST.post = self.post
        HOST.edit = self.edit
        HOST.board_channel = self.board
        HOST.monitor_channel = self.monitor
        HOST.link_base = lambda: "https://ouja.test"
        HOST.once_claim = self.claim
        HOST.once_release = lambda k: self.claims.discard(k)
        HOST.is_live = None


def dep(res_id, lid, day=D, status="new", channel="airbnb", phone="+966 50 111 2222",
        guest="Sara Ali", arrival="2026-10-10"):
    return {"res_id": str(res_id), "lid": lid, "unit": "Ouja | Unit %s" % lid, "guest": guest,
            "phone": phone, "conversation_id": "c%s" % res_id, "status": status,
            "channel": channel, "arrival": arrival, "departure": day}


def weak_reviews(lid, n=4, raw=8):
    return [{"id": "w%s-%d" % (lid, i), "listing_id": lid, "rating_raw": raw,
             "channel": "Airbnb", "reservation_id": "old%s-%d" % (lid, i),
             "raw": {"type": "guest-to-host"}} for i in range(n)]


def strong_reviews(lid, n=5):
    return weak_reviews(lid, n, 10)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rv_flow_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        flow.reset_caches()
        flow._locks.clear()
        for k in [k for k in os.environ if k.startswith("REVIEWASK_")]:
            os.environ.pop(k)
        self.f = Fake()
        self.f.wire()
        self.f.reviews = weak_reviews(1) + strong_reviews(2) + weak_reviews(3)
        self.f.deps = [dep(501, 1), dep(502, 2), dep(503, 3, channel="direct")]
        db.set_setting("live", "1")

    def open_today(self):
        return run(flow.open_rooms(D, "test", dry=False, now_=self.f.clock))

    def t(self, res="501"):
        return db.by_reservation(res)


class TestOpening(Base):
    def test_one_room_per_reservation_across_three_overlapping_ticks(self):
        async def three():
            return await asyncio.gather(flow.tick(self.f.clock), flow.tick(self.f.clock),
                                        flow.open_rooms(D, "x", dry=False, now_=self.f.clock))
        run(three())
        self.f.claims.clear()                                     # even a lost claim file
        db.set_setting("open_check:%s" % D, "")
        run(flow.tick(self.f.clock + datetime.timedelta(hours=1)))
        topics = [r["topic"] for r in self.f.rooms.values()]
        self.assertEqual(len(topics), 1, topics)
        self.assertTrue(topics[0].startswith("ouja-rv:501 "))
        self.assertEqual(db.counts()["rv_tickets"], 1)

    def test_a_room_already_in_discord_is_never_reopened(self):
        self.f.rooms["77"] = {"name": "x", "topic": "ouja-rv:501 lid:1 seq:1"}
        rep = self.open_today()
        self.assertEqual(rep["opened"], [])
        self.assertIn("duplicate", [s["reason"] for s in rep["skipped"]])

    def test_skips_are_listed_with_reasons(self):
        self.f.deps.append(dep(504, 1, status="cancelled"))
        rep = self.open_today()
        reasons = {s["res_id"]: s["reason"] for s in rep["skipped"]}
        self.assertEqual(reasons["502"], "out_of_program")
        self.assertEqual(reasons["503"], "not_airbnb")
        self.assertEqual(reasons["504"], "cancelled")
        self.assertEqual([o["res_id"] for o in rep["opened"]], ["501"])
        text = texts.open_summary(rep, D, False)
        self.assertIn("الشقة فوق ٤.٧٥", text)

    def test_dry_run_opens_nothing_and_lists_would_open(self):
        db.set_setting("live", "0")
        rep = run(flow.open_rooms(D, "x", now_=self.f.clock))
        self.assertEqual([w["res_id"] for w in rep["would_open"]], ["501"])
        self.assertEqual(self.f.rooms, {})
        self.assertEqual(db.counts()["rv_tickets"], 0)
        self.assertIn("تجربة", texts.open_summary(rep, D, True))

    def test_tick_does_nothing_while_off(self):
        db.set_setting("live", "0")
        self.assertEqual(run(flow.tick(at(2026, 10, 14, 17, 0))), {"skipped": "off"})
        self.assertEqual(self.f.posts, [])

    def test_card_is_silent_and_strong_care_stay_gets_a_room(self):
        self.f.tickets_by_lid[2] = [{"created_at": "2026-10-11T10:00:00+03:00", "closed_at": None}]
        rep = self.open_today()
        self.assertEqual(sorted(o["res_id"] for o in rep["opened"]), ["501", "502"])
        self.assertEqual(self.t("502")["mode"], "care")
        for ch, _text, embed, buttons, mentions in self.f.posts:
            self.assertFalse(mentions)
            self.assertIsNone(buttons)
        care_card = [p[2] for p in self.f.posts if p[2] and "Unit 2" in p[2]["title"]][0]
        self.assertIn(texts.CARE_WARNING, str(care_card))

    def test_already_reviewed_is_a_skip(self):
        self.f.reviews.append({"id": "x", "listing_id": 1, "rating_raw": 10, "channel": "Airbnb",
                               "reservation_id": "501", "raw": {"type": "guest-to-host"}})
        rep = self.open_today()
        self.assertEqual(rep["opened"], [])
        self.assertIn("already_reviewed", [s["reason"] for s in rep["skipped"]])

    def test_no_reviews_never_means_every_apartment_is_weak(self):
        self.f.reviews = []
        rep = self.open_today()
        self.assertTrue(rep["error"])
        self.assertEqual(rep["opened"], [])
        self.assertEqual(self.f.rooms, {})

        def broken():
            raise RuntimeError("dictionary changed size during iteration")
        HOST.reviews = broken
        rep = self.open_today()
        self.assertTrue(rep["error"])
        self.assertEqual(self.f.rooms, {})

    def test_hostaway_down_is_an_error_not_an_empty_day(self):
        self.f.dep_fail = True
        rep = self.open_today()
        self.assertTrue(rep["error"])
        self.assertEqual(rep["opened"], [])


class TestClockFlow(Base):
    def test_wa_stage_then_call_next_evening(self):
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        row = self.t()
        self.assertEqual(row["state"], engine.WA_DUE)
        self.assertEqual(row["responsible"], "أصيل")              # the cover of the action day
        ping = self.f.room_posts()[-1]
        self.assertTrue(ping[4])                                   # mention
        self.assertIn("<@111>", ping[1])
        link = [b for b in ping[3] if isinstance(b, tuple)][0]
        self.assertEqual(link[1], "فتح واتساب")
        self.assertTrue(link[2].startswith("https://ouja.test/rv/"))
        self.assertLessEqual(len(link[2]), 512)
        res = run(flow.answer(row["id"], "sent", "نورة", "222", now_=at(2026, 10, 14, 17, 30)))
        self.assertTrue(res["ok"])
        self.assertEqual(self.t()["state_by"], "نورة")            # the PRESSER is recorded
        run(flow.tick(at(2026, 10, 15, 20, 0)))
        row = self.t()
        self.assertEqual(row["state"], engine.CALL_DUE)
        self.assertEqual(row["responsible"], "نورة")              # day+1 cover
        self.assertIn("نص المكالمة", self.f.room_posts()[-1][1])

    def test_first_final_wins(self):
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        tid = self.t()["id"]

        async def both():
            return await asyncio.gather(
                flow.answer(tid, "replied_will", "أ", "1", now_=at(2026, 10, 14, 17, 5)),
                flow.answer(tid, "replied_no", "ب", "2", now_=at(2026, 10, 14, 17, 5)))
        a, b = run(both())
        self.assertEqual(sorted([a["ok"], b["ok"]]), [False, True])
        loser = a if not a["ok"] else b
        self.assertIn("انحفظت قبلك من", loser["message"])

    def test_matched_review_closes_from_any_open_state(self):
        for st in engine.OPEN:
            with self.subTest(state=st):
                self.setUp()
                self.open_today()
                db.update_ticket(self.t()["id"], {"state": st})
                self.f.reviews.append({"id": "R1", "listing_id": 1, "rating_raw": 8,
                                       "channel": "Airbnb", "reservation_id": "501",
                                       "raw": {"type": "guest-to-host"}})
                run(flow.tick(at(2026, 10, 15, 14, 0)))
                row = self.t()
                self.assertEqual(row["state"], engine.REVIEWED)
                self.assertEqual(row["review_stars"], 4.0)
                self.assertTrue(row["closed_at"])
                self.assertIn("تقييم أقل من ٥", self.f.room_posts()[-1][1])

    def test_zero_score_review_does_not_close(self):
        self.open_today()
        self.f.reviews.append({"id": "R0", "listing_id": 1, "rating_raw": 0, "channel": "Airbnb",
                               "reservation_id": "501", "raw": {"type": "guest-to-host"}})
        run(flow.tick(at(2026, 10, 14, 14, 0)))
        self.assertEqual(self.t()["state"], engine.WAITING)

    def test_cancellation_closes(self):
        self.open_today()
        self.f.deps[0]["status"] = "cancelled"
        flow.reset_caches()
        run(flow.tick(at(2026, 10, 14, 15, 0)))
        row = self.t()
        self.assertEqual(row["state"], engine.CANCELLED)
        self.assertIn("انلغى", row["close_note"])

    def test_moved_departure_closes_with_a_note(self):
        self.open_today()
        self.f.deps[0]["departure"] = "2026-10-15"
        flow.reset_caches()
        run(flow.tick(at(2026, 10, 14, 15, 0)))
        self.assertIn("2026-10-15", self.t()["close_note"])

    def test_failed_read_never_cancels(self):
        self.open_today()
        self.f.dep_fail = True
        flow.reset_caches()
        run(flow.tick(at(2026, 10, 14, 15, 0)))
        self.assertEqual(self.t()["state"], engine.WAITING)

    def test_missing_from_window_is_reread_by_id(self):
        self.open_today()
        self.f.deps = []
        self.f.res_by_id["501"] = dep(501, 1, status="cancelled")
        flow.reset_caches()
        run(flow.tick(at(2026, 10, 14, 15, 0)))
        self.assertEqual(self.t()["state"], engine.CANCELLED)

    def test_staff_miss_is_logged_against_the_responsible_and_attempt_kept(self):
        self.open_today()
        tid = self.t()["id"]
        db.update_ticket(tid, {"state": engine.WA_SENT,
                               "next_due_at": engine.iso(at(2026, 10, 15, 20, 0))})
        run(flow.tick(at(2026, 10, 15, 20, 0)))
        run(flow.tick(at(2026, 10, 15, 22, 0)))
        row = self.t()
        self.assertEqual(row["calls_used"], 0)
        self.assertEqual(row["stage_due_at"], engine.iso(at(2026, 10, 16, 20, 0)))
        miss = db.events(tid, ["staff_miss"])
        self.assertEqual(len(miss), 1)
        self.assertEqual(miss[0]["actor"], "نورة")

    def test_nothing_guest_facing_in_quiet_hours(self):
        self.open_today()
        n = len(self.f.posts)
        for h in (22, 23, 2, 8, 12):
            day = 14 if h >= 22 else 15
            run(flow.tick(at(2026, 10, day, h, 30)))
        self.assertEqual([p for p in self.f.posts[n:] if p[4]], [])

    def test_expiry_closes_on_day_14(self):
        self.open_today()
        db.update_ticket(self.t()["id"], {"state": engine.PROMISED})
        run(flow.tick(at(2026, 10, 27, 23, 59)))
        self.assertEqual(self.t()["state"], engine.PROMISED_EXPIRED)

    def test_satisfied_opens_whatsapp_at_once(self):
        self.f.tickets_by_lid[1] = [{"created_at": "2026-10-11T10:00:00+03:00", "closed_at": None}]
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        self.assertEqual(self.t()["state"], engine.CARE_DUE)
        run(flow.answer(self.t()["id"], "satisfied", "أصيل", "111", now_=at(2026, 10, 14, 18, 0)))
        self.assertEqual(self.t()["state"], engine.WA_DUE)
        self.assertIn("sent", self.f.room_posts()[-1][3])

    def test_no_phone_offers_airbnb_and_call_still_opens(self):
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        res = run(flow.answer(self.t()["id"], "no_phone", "أصيل", "111",
                              now_=at(2026, 10, 14, 17, 10)))
        self.assertEqual(res["links"][0][1], "رسالة Airbnb")
        self.assertNotIn("wa.me", res["links"][0][0])
        run(flow.tick(at(2026, 10, 15, 20, 0)))
        self.assertEqual(self.t()["state"], engine.CALL_DUE)

    def test_complaint_links_the_maintenance_room(self):
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        res = run(flow.complaint_opened(self.t()["id"], "4242", "أصيل", "111",
                                        now_=at(2026, 10, 14, 17, 20)))
        self.assertTrue(res["ok"])
        self.assertEqual(self.t()["state"], engine.COMPLAINT)
        self.assertIn("<#4242>", self.f.room_posts()[-1][1])


class TestWhatsAppLink(Base):
    def test_rv_token_logs_and_redirects_with_the_rendered_template(self):
        import aiohttp.web as web
        db.save_templates("هلا {الاسم}، معك {الموظف} — {الشقة} {رابط_التقييم} {مجهول}",
                          "Hi {الاسم}", "script", "owner")
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        tok = db.link_for(self.t()["id"])["token"]
        self.assertGreaterEqual(len(tok), 16)

        async def web_thread(fn, *a, **kw):
            return fn(*a, **kw)
        HOST.web, HOST.web_thread = web, web_thread

        class Req:
            headers = {}
            remote = "1.2.3.4"
            match_info = {"token": tok}

        with self.assertRaises(web.HTTPFound) as cm:
            run(routes.handle_rv(Req()))
        url = cm.exception.location
        self.assertTrue(url.startswith("https://wa.me/966501112222?text="))
        text = urllib.parse.unquote(url.split("?text=", 1)[1])
        self.assertEqual(text, "هلا Sara، معك أصيل — Unit 1 https://www.airbnb.com/users/reviews "
                               "{مجهول}")
        self.assertEqual(len(db.events(self.t()["id"], ["wa_opened"])), 1)

        Req.match_info = {"token": "nope-nope-nope-nope"}
        with self.assertRaises(web.HTTPNotFound):
            run(routes.handle_rv(Req()))

    def test_foreign_number_gets_english(self):
        db.save_templates("عربي {الاسم}", "Hi {الاسم}", "", "owner")
        self.f.deps[0]["phone"] = "+44 7700 900123"
        self.open_today()
        tok = db.link_for(self.t()["id"])["token"]
        url = flow.wa_redirect(tok)
        self.assertIn(urllib.parse.quote("Hi Sara", safe=""), url)

    def test_rate_limit(self):
        for i in range(routes.RATE_MAX):
            self.assertTrue(routes._rate_ok("9.9.9.9", 1000.0 + i * 0.01))
        self.assertFalse(routes._rate_ok("9.9.9.9", 1001.0))
        self.assertTrue(routes._rate_ok("9.9.9.9", 1100.0))


class TestTemplates(Base):
    def test_seed_on_first_read_and_history_on_save(self):
        t = db.templates()
        self.assertIn("{الاسم}", t["ar"])
        self.assertEqual(t["updated_by"], "seed")
        db.save_templates("A {الاسم}", "", "S", "فيصل")
        db.save_templates("B {الاسم}", "", "S", "فيصل")
        self.assertEqual(db.templates()["ar"], "B {الاسم}")
        hist = db.template_history()
        self.assertEqual([h["ar"] for h in hist][:2], ["A {الاسم}", t["ar"]])

    def test_preview_flags_unknown_and_measures_url(self):
        p = flow.preview({"ar": "هلا {الاسم} {غلط}", "en": "", "call_script": "{الموظف}"})
        self.assertEqual(p["ar"]["unknown"], ["غلط"])
        self.assertIn("سارة", p["ar"]["text"])
        self.assertGreater(p["ar"]["url_len"], 20)
        self.assertEqual(p["en"]["text"], p["ar"]["text"])        # empty English → Arabic
        self.assertEqual(p["call_script"]["text"], "أصيل")

    def test_route_validation(self):
        st, body = routes.core_save_templates({"ar": "", "en": "x"}, "f")
        self.assertEqual(st, 400)
        st, body = routes.core_save_templates({"ar": "x" * 4001}, "f")
        self.assertEqual(st, 400)
        st, body = routes.core_pin({"lid": 1, "mode": "in", "reason": ""}, "f")
        self.assertEqual(st, 400)
        st, body = routes.core_pin({"lid": 2, "mode": "in", "reason": "Airbnb يقول 4.6"}, "f")
        self.assertEqual(st, 200)
        self.assertTrue(flow.program()[2]["in_program"])
        routes.core_pin({"lid": 2, "mode": "clear"}, "f")
        self.assertFalse(flow.program()[2]["in_program"])


class TestBoardAndReports(Base):
    def test_board_sections_and_no_money(self):
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        chunks = flow.board_chunks(at(2026, 10, 14, 17, 1), flow.program(), flow._names())
        body = "".join(chunks)
        self.assertIn("واتساب لازم ينرسل", body)
        self.assertIn("الشقق تحت ٤.٧٥", body)
        for bad in ("SAR", "ر.س", "ريال"):
            self.assertNotIn(bad, body)

    def test_monitor_report_names_people_and_is_latched(self):
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        n = len(self.f.posts)
        self.assertTrue(run(flow.maybe_monitor_report(at(2026, 10, 14, 17, 30))))
        post = self.f.posts[n]
        self.assertEqual(post[0], "MONITOR")
        self.assertIn("أصيل", post[1])
        self.assertIn("متأخر 30 دقيقة", post[1])
        self.assertFalse(run(flow.maybe_monitor_report(at(2026, 10, 14, 17, 45))))   # same slot
        self.assertFalse(run(flow.maybe_monitor_report(at(2026, 10, 14, 16, 30))))   # before 17:00

    def test_monitor_silent_when_nothing_due(self):
        self.open_today()
        self.assertFalse(run(flow.maybe_monitor_report(at(2026, 10, 14, 18, 0))))

    def test_summary_once_a_day(self):
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        run(flow.answer(self.t()["id"], "sent", "أصيل", "111", now_=at(2026, 10, 14, 17, 5)))
        self.assertTrue(run(flow.maybe_summary(at(2026, 10, 14, 22, 0))))
        self.assertIn("رسائل الواتساب: 1 من 1", self.f.posts[-1][1])
        self.assertFalse(run(flow.maybe_summary(at(2026, 10, 14, 22, 30))))

    def test_report_per_person(self):
        self.open_today()
        run(flow.tick(at(2026, 10, 14, 17, 0)))
        run(flow.answer(self.t()["id"], "sent", "أصيل", "111", now_=at(2026, 10, 14, 17, 5)))
        people, apts = flow.report_data(at(2026, 10, 14, 23, 0), 7)
        p = {x["name"]: x for x in people}["أصيل"]
        self.assertEqual((p["wa_due"], p["wa_done"]), (1, 1))
        self.assertEqual(apts[0]["needed"], flow.program()[1]["needed"])
        self.assertIn("أصيل", "".join(flow.report_text(at(2026, 10, 14, 23, 0), 7)))


if __name__ == "__main__":
    unittest.main()
