# -*- coding: utf-8 -*-
"""«حملات عوجا» campaign engine stage 1 — offline tests (fake host, throwaway brain.db).

Locked here:
  * code words: Arabic spelling variants match; «نص ساعة» and friends never do
  * the B1 Special Offer: night 1 at the calendar price, night 2 at 50 %, never under the
    floor; Sun–Wed and next-night-free checks; reasons instead of guesses
  * the opt-out list: persistent, one row per person, phone kept only as a salted key
  * the watcher alerts once per Hostaway message; button taps route to the right channel,
    a menu-flow tap is left to Hatif, dry-run never sends, nothing posts a phone number
  * hatif.service hands campaign taps over and keeps everything else exactly as before
  * the Sunday report fires once and matches bookings within 7 days

Run: python3 -m unittest tests.test_campaigns
"""
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                     # noqa: E402
from campaigns import config, db, engine, host, service          # noqa: E402

UTC = datetime.timezone.utc
RIYADH = datetime.timezone(datetime.timedelta(hours=3))
SUN = datetime.date(2026, 11, 29)          # a Sunday — the first send day
PHONE = "966551234567"


def cal(*rows):
    return [{"date": d.isoformat(), "isAvailable": a, "price": p, "reservationId": r}
            for d, a, p, r in rows]


# =============================================================== code words
class CodewordTests(unittest.TestCase):
    def hit(self, text):
        h = engine.match_codeword(text)
        return h["code"] if h else None

    def test_exact_and_variants(self):
        for t in ("عرض نص", "عرض النص", "عرض نصف", "عرض النصف", "عرض النصّ", "عَرض نص",
                  "هلا، أبي عرض نص لو سمحت", "وعرض نص", "عرض  نص", "عرضنص", "عرض نص!",
                  "ابي عرض النص الليلة الثانية", "عرض بالنص"):
            self.assertEqual(self.hit(t), "B1", t)

    def test_no_false_positives(self):
        for t in ("نص ساعة وأوصل", "بعد نص ساعة", "عرض نص ساعة", "وصلت قبل نص ساعه",
                  "فيه عرض؟", "النص مو واضح", "عرض نصيحة", "عرضكم حلو بس نص الشقة وسخ",
                  "عرض نص الليل", "half price please", "", None, "12345"):
            self.assertIsNone(self.hit(t), t)

    def test_list_is_one_config_dict(self):
        words = dict(config.CODEWORDS)
        words["C1"] = {"title": "جاي الرياض", "phrases": ["جاي الرياض"], "kind": "alert_only"}
        h = engine.match_codeword("انا جاي الرياض الاسبوع الجاي", words)
        self.assertEqual(h["code"], "C1")
        self.assertIsNone(engine.match_codeword("انا جاي الرياض", config.CODEWORDS))

    def test_normalize(self):
        self.assertEqual(engine.normalize("إيقاف  العروضُ"), "ايقاف العروض")
        self.assertEqual(engine.normalize("مـدينة"), "مدينه")


# =============================================================== the price
class OfferTests(unittest.TestCase):
    def offer(self, arrival, rows, floor=0, departure=None, **kw):
        a = arrival
        dep = departure or (a + datetime.timedelta(days=1))
        return engine.second_night_offer(a, dep, rows, floor, **kw)

    def test_sunday_half_second_night(self):
        o = self.offer(SUN, cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 1, 400, None)))
        self.assertTrue(o["eligible"], o["reasons"])
        self.assertEqual((o["night1_price"], o["night2_price"], o["total"]), (400, 200, 600))
        self.assertEqual((o["offer_checkin"], o["offer_checkout"]), ("2026-11-29", "2026-12-01"))
        self.assertFalse(o["floored"])

    def test_night2_uses_its_own_calendar_price(self):
        o = self.offer(SUN, cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 1, 450, None)))
        self.assertEqual((o["night2_full"], o["night2_price"], o["total"]), (450, 225, 625))

    def test_never_below_floor(self):
        o = self.offer(SUN, cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 1, 400, None)), floor=260)
        self.assertEqual((o["night2_price"], o["total"]), (260, 660))
        self.assertTrue(o["floored"])
        self.assertTrue(o["eligible"])

    def test_floor_under_half_changes_nothing(self):
        o = self.offer(SUN, cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 1, 400, None)), floor=150)
        self.assertEqual(o["night2_price"], 200)
        self.assertFalse(o["floored"])

    def test_rounds_half_up(self):
        o = self.offer(SUN, cal((SUN, 1, 401, None), (SUN + datetime.timedelta(1), 1, 401, None)))
        self.assertEqual(o["night2_price"], 201)        # 200.5 → 201

    def test_thursday_is_not_the_offer(self):
        thu = SUN + datetime.timedelta(days=4)
        o = self.offer(thu, cal((thu, 1, 700, None), (thu + datetime.timedelta(1), 1, 800, None)))
        self.assertFalse(o["eligible"])
        self.assertTrue(any("الخميس" in r for r in o["reasons"]))
        self.assertEqual(o["total"], 1100)              # still computed for a supervisor

    def test_wednesday_flags_weekend_second_night(self):
        wed = SUN + datetime.timedelta(days=3)
        o = self.offer(wed, cal((wed, 1, 400, None), (wed + datetime.timedelta(1), 1, 700, None)))
        self.assertTrue(o["eligible"])
        self.assertTrue(o["night2_weekend"])
        self.assertEqual(o["night2_weekday"], "الخميس")

    def test_next_night_booked(self):
        o = self.offer(SUN, cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 0, 400, 991)))
        self.assertFalse(o["eligible"])
        self.assertFalse(o["night2_free"])

    def test_next_night_unknown_is_not_guessed(self):
        o = self.offer(SUN, cal((SUN, 1, 400, None)))
        self.assertFalse(o["eligible"])
        self.assertIsNone(o["night2_free"])
        self.assertEqual(o["night2_price"], 200)        # half of night 1 when night 2 has no price

    def test_no_price_no_total(self):
        o = self.offer(SUN, [])
        self.assertIsNone(o["total"])
        self.assertFalse(o["eligible"])

    def test_no_date(self):
        o = engine.second_night_offer(None, None, [], 0)
        self.assertFalse(o["eligible"])
        self.assertEqual(o["reasons"], ["ما عرفنا تاريخ الدخول"])

    def test_three_night_request(self):
        o = self.offer(SUN, cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 1, 400, None)),
                       departure=SUN + datetime.timedelta(days=3))
        self.assertFalse(o["eligible"])
        self.assertEqual(o["nights_requested"], 3)


# =============================================================== shared fixture
class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="campaigns_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        for k in list(os.environ):
            if k.startswith("CAMPAIGN") or k.startswith("HATIF_"):
                os.environ.pop(k)
        self.posts, self.searches, self.sent = [], [], []
        self.now = datetime.datetime(2026, 11, 29, 14, 20, tzinfo=RIYADH)
        self.cal_rows = cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 1, 400, None))
        self.res_rows = []

        def search(ci, co, guests, typ, hood):
            self.searches.append((ci, co))
            return {"avail_error": False, "results": [
                {"id": 437215, "name_ar": "Ouja | الملقا غرفتين", "area": "الملقا",
                 "available": True, "est_total": 450}]}

        host.wire({"now": lambda: self.now,
                   "post": lambda where, text, role="": self.posts.append((where, text, role)),
                   "log_event": lambda c, t: None,
                   "calendar": lambda lid, a, b: self.cal_rows,
                   "floor": lambda lid: 0,
                   "responsible": lambda lid, name: "نورة",
                   "links": lambda rid, ct: [("https://www.airbnb.com/hosting/messages/1", "💬 محادثة Airbnb")],
                   "dates_from_text": lambda h: (None, None, "low"),
                   "reservations": lambda a, b: self.res_rows,
                   "search": search, "site_host": lambda: "oujares.com"})
        self._orig_api = service._hatif_api
        service._hatif_api = lambda: (None, None)

    def tearDown(self):
        service._hatif_api = self._orig_api

    def item(self, text="ابي عرض نص", mid="m1", **over):
        it = {"conversation_id": 5551, "message_id": mid, "guest": "Abdullah Alharbi",
              "unit": "Ouja | Malqa 2BR", "listing_id": 437215, "reservation_id": 777,
              "res_status": "inquiry", "comm_type": "airbnb", "guest_text": text,
              "history": "Guest: " + text, "checkin": SUN.isoformat(),
              "checkout": (SUN + datetime.timedelta(1)).isoformat()}
        it.update(over)
        return it

    def tap(self, label, eid="e1", **over):
        p = {"direction": "Inbound", "messageType": "Text", "body": label,
             "interactiveReply": {"id": "btn-1", "text": label}, "conversationEventId": eid,
             "messageId": "w-" + eid, "conversationId": "conv-9", "contactId": "ct-42",
             "channelId": "ch-1"}
        p.update(over)
        return p

    def all_text(self):
        return "\n".join(t for _, t, _ in self.posts)


# =============================================================== opt-out list
class OptOutTests(Base):
    def test_add_and_check_by_phone_key(self):
        k = engine.phone_key(PHONE, db.salt())
        self.assertNotIn("551234567", k)
        self.assertTrue(db.add_optout(k, "ct-1", "conv-1", "4567"))
        self.assertTrue(db.is_opted_out([engine.phone_key("0551234567", db.salt())]))
        self.assertFalse(db.is_opted_out([engine.phone_key("966559999999", db.salt())]))

    def test_one_row_per_person_and_duplicate(self):
        k = engine.phone_key(PHONE, db.salt())
        self.assertTrue(db.add_optout(k, "ct-1"))
        self.assertFalse(db.add_optout(k, "ct-1"))
        self.assertEqual(len(db.optouts()), 1)

    def test_contact_id_alone_is_enough(self):
        db.add_optout("contact:ct-7", "ct-7")
        self.assertTrue(db.is_opted_out([], "ct-7"))
        self.assertTrue(service.is_suppressed(contact_id="ct-7"))

    def test_persists_across_restart(self):
        db.add_optout("contact:ct-8", "ct-8")
        salt1 = db.salt()
        db.reset_init_cache()                          # a fresh process on the same volume
        self.assertTrue(db.is_opted_out(["contact:ct-8"]))
        self.assertEqual(db.salt(), salt1)

    def test_phone_key_is_salted_and_stable(self):
        self.assertEqual(engine.phone_key("+966 55 123 4567", "s"), engine.phone_key("0551234567", "s"))
        self.assertNotEqual(engine.phone_key(PHONE, "s"), engine.phone_key(PHONE, "t"))
        self.assertEqual(engine.phone_key("", "s"), "")

    def test_stop_words_whole_message_only(self):
        for t in ("ايقاف", "إيقاف العروض", "STOP", "Stop."):
            self.assertTrue(engine.is_stop_message(t), t)
        for t in ("وقف السيارة عند الباب", "ايقاف الحجز؟ لا ابي اكمل", "stop by tomorrow"):
            self.assertFalse(engine.is_stop_message(t), t)


# =============================================================== the watcher
class WatcherTests(Base):
    def test_alert_once_with_price_and_owner(self):
        r = service.on_guest_message(self.item())
        self.assertEqual(r["outcome"], "alerted")
        self.assertEqual(len(self.posts), 1)
        where, text, _ = self.posts[0]
        self.assertEqual(where, "offers")
        for want in ("Abdullah Alharbi", "Ouja | Malqa 2BR", "الأحد 29/11", "✅", "600 ر.س",
                     "200 ر.س", "نورة", "15 دقيقة", "5551", "Special Offer"):
            self.assertIn(want, text, want)
        self.assertEqual(service.on_guest_message(self.item())["outcome"], "duplicate")
        self.assertEqual(len(self.posts), 1)

    def test_no_code_word_no_post(self):
        self.assertEqual(service.on_guest_message(self.item("بوصل بعد نص ساعة"))["outcome"], "none")
        self.assertEqual(self.posts, [])

    def test_switch_off(self):
        os.environ["CAMPAIGN_WATCH"] = "0"
        self.assertEqual(service.on_guest_message(self.item())["outcome"], "off")
        self.assertEqual(self.posts, [])

    def test_floor_shown(self):
        host.HOST.floor = lambda lid: 300
        service.on_guest_message(self.item())
        self.assertIn("للحد الأدنى 300 ر.س", self.posts[0][1])
        self.assertIn("700 ر.س", self.posts[0][1])

    def test_booked_next_night_says_so(self):
        self.cal_rows = cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 0, 400, 12))
        service.on_guest_message(self.item())
        self.assertIn("❌ العرض ما ينطبق", self.posts[0][1])

    def test_role_ping_passed(self):
        os.environ["CAMPAIGN_OFFER_ROLE_ID"] = "123456789"
        service.on_guest_message(self.item())
        self.assertEqual(self.posts[0][2], "123456789")

    def test_hits_are_logged_for_the_week(self):
        service.on_guest_message(self.item(mid="a"))
        service.on_guest_message(self.item(mid="b"))
        rows = db.hits_between("2000-01-01", "9999-01-01")
        self.assertEqual([r["code"] for r in rows], ["B1", "B1"])

    def test_calendar_trouble_is_not_a_crash(self):
        host.HOST.post = None
        host.HOST.calendar = lambda *a: (_ for _ in ()).throw(RuntimeError("x"))
        host.HOST.floor = lambda lid: (_ for _ in ()).throw(RuntimeError("y"))
        r = service.on_guest_message(self.item())
        self.assertEqual(r["outcome"], "alerted")        # calendar trouble → reasons, not a crash


# =============================================================== Hatif buttons
class FakeHC:
    def __init__(self):
        self.sent = []

    def get_conversation(self, cid):
        return {"phoneNumber": "+" + PHONE, "assigneeId": None, "contactName": "سارة"}

    def send_text(self, ch, phone, text):
        self.sent.append((ch, phone, text))


class FakeCfg:
    def __init__(self, dry=False, allow=()):
        self.dry, self.allow = dry, set(allow)

    def dryrun(self):
        return self.dry

    def test_numbers(self):
        return self.allow

    def bot_user_id(self):
        return "bot-seat"

    def channel_id(self):
        return "ch-1"

    def max_units(self):
        return 6


class ButtonTests(Base):
    def test_owner_call_goes_to_owners_channel(self):
        self.assertTrue(service.on_hatif(self.tap("إيه، كلموني")))
        where, text, _ = self.posts[0]
        self.assertEqual(where, "owners")
        self.assertIn("ساعات", text)
        self.assertIn("ouja_owner_recontact", text)

    def test_label_variants(self):
        self.assertTrue(service.on_hatif(self.tap("ايه كلموني", eid="e2")))
        self.assertEqual(self.posts[-1][0], "owners")

    def test_menu_flow_tap_is_left_to_hatif(self):
        self.assertFalse(service.on_hatif(self.tap("الحجوزات", eid="e3")))
        self.assertEqual(self.posts, [])

    def test_retry_handled_once(self):
        self.assertTrue(service.on_hatif(self.tap("وش إيليت؟", eid="e4")))
        self.assertTrue(service.on_hatif(self.tap("وش إيليت؟", eid="e4")))
        self.assertEqual(len(self.posts), 1)

    def test_show_units_dryrun_prepares_never_sends(self):
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg())
        self.assertTrue(service.on_hatif(self.tap("وريني الشقق", eid="e5")))
        text = self.posts[0][1]
        self.assertIn("الرد الجاهز", text)
        self.assertIn("Ouja | الملقا غرفتين", text)
        self.assertEqual(fake.sent, [])
        self.assertEqual(self.searches, [("2026-11-29", "2026-11-30")])   # tonight is a Sunday

    def test_show_units_live_when_both_dryruns_off(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=False))
        service.on_hatif(self.tap("وريني الشقق", eid="e6"))
        self.assertEqual(len(fake.sent), 1)
        self.assertEqual(fake.sent[0][1], PHONE)
        self.assertIn("انرسلت", self.posts[0][1])

    def test_opted_out_person_is_never_sent_to(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=False))
        service.on_hatif(self.tap("إيقاف العروض", eid="e7"))
        service.on_hatif(self.tap("وش إيليت؟", eid="e8"))
        self.assertEqual(fake.sent, [])
        self.assertIn("إيقاف العروض", self.posts[-1][1])

    def test_test_numbers_allowlist_holds(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=False, allow={"966500000000"}))
        service.on_hatif(self.tap("وش إيليت؟", eid="e9"))
        self.assertEqual(fake.sent, [])

    def test_opt_out_button_and_typed_stop(self):
        self.assertTrue(service.on_hatif(self.tap("إيقاف العروض", eid="o1")))
        self.assertTrue(service.is_suppressed(contact_id="ct-42"))
        self.assertTrue(service.on_hatif(self.tap("إيقاف العروض", eid="o2")))   # already on the list
        self.assertEqual(len(db.optouts()), 1)
        typed = self.tap("STOP", eid="o3", contactId="ct-77")
        typed.pop("interactiveReply")
        self.assertTrue(service.on_hatif(typed))
        self.assertTrue(service.is_suppressed(contact_id="ct-77"))

    def test_plain_text_equal_to_a_label_counts(self):
        p = self.tap("وريني الباقات", eid="t1")
        p.pop("interactiveReply")
        self.assertTrue(service.on_hatif(p))
        self.assertIn("باقات", self.posts[0][1])
        self.assertIn("ouja_moments_midweek", self.posts[0][1])

    def test_shared_label_template_unknown_unless_hinted(self):
        service.on_hatif(self.tap("وريني الشقق", eid="h1"))
        self.assertIn("قالب غير محدد", self.posts[-1][1])
        p = self.tap("وريني الشقق", eid="h2", interactiveReply={"id": "ouja_midweek_half_btn0",
                                                              "text": "وريني الشقق"})
        service.on_hatif(p)
        self.assertIn("ouja_midweek_half", self.posts[-1][1])
        self.assertIn("عرض نص", self.posts[-1][1])

    def test_outbound_and_switch_off(self):
        self.assertFalse(service.on_hatif(self.tap("إيه، كلموني", eid="x1", direction="Outbound")))
        os.environ["CAMPAIGN_BUTTONS"] = "0"
        self.assertFalse(service.on_hatif(self.tap("إيه، كلموني", eid="x2")))
        self.assertEqual(self.posts, [])

    def test_no_phone_number_anywhere(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=True))
        for i, label in enumerate(("إيه، كلموني", "وريني الشقق", "وش إيليت؟", "إيقاف العروض")):
            service.on_hatif(self.tap(label, eid="p%d" % i))
        blob = self.all_text() + repr(db.taps_between("2000", "9999")) + repr(db.optouts())
        self.assertNotIn("551234567", blob)
        self.assertIn("••4567", self.all_text())


# =============================================================== hatif hand-over
class HatifHandoverTests(Base):
    def setUp(self):
        Base.setUp(self)
        from hatif import host as hhost, service as hsvc, db as hdb
        self.hhost, self.hsvc = hhost, hsvc
        hdb.reset_init_cache()
        hsvc.reset_for_tests()
        hhost.wire({"now": lambda: datetime.datetime(2026, 11, 29, 14, 0),
                    "notify": lambda t: None, "search": lambda *a: {"results": []},
                    "neighborhoods": lambda: [], "site_host": lambda: "oujares.com",
                    "campaign_tap": service.on_hatif})

    def tearDown(self):
        self.hhost.HOST.campaign_tap = None
        Base.tearDown(self)

    def test_campaign_tap_is_handed_over(self):
        self.assertEqual(self.hsvc.handle(self.tap("إيه، كلموني"))["outcome"], "campaign")
        self.assertEqual(self.posts[0][0], "owners")

    def test_menu_tap_still_ignored(self):
        self.assertEqual(self.hsvc.handle(self.tap("الحجوزات", eid="m9"))["outcome"], "ignored")

    def test_without_campaigns_wired_taps_stay_ignored(self):
        self.hhost.HOST.campaign_tap = None
        self.assertEqual(self.hsvc.handle(self.tap("إيه، كلموني", eid="m8"))["outcome"], "ignored")
        self.assertEqual(self.posts, [])


# =============================================================== weekly report
class ReportTests(Base):
    def test_should_fire_once_on_sunday_9(self):
        sun9 = datetime.datetime(2026, 12, 6, 9, 0, tzinfo=RIYADH)
        self.assertTrue(engine.should_fire(sun9, "", 6, 9))
        self.assertFalse(engine.should_fire(sun9, "2026-12-06", 6, 9))
        self.assertFalse(engine.should_fire(sun9.replace(hour=8), "", 6, 9))
        self.assertFalse(engine.should_fire(sun9 + datetime.timedelta(days=1), "", 6, 9))

    def test_tick_posts_once_and_counts(self):
        # last week's activity (all inside 29/11 09:00 → 06/12 09:00 Riyadh)
        self.now = datetime.datetime(2026, 11, 30, 12, 0, tzinfo=RIYADH)
        service.on_guest_message(self.item(mid="h1"))
        service.on_guest_message(self.item(mid="h2", guest="Mona Saad", reservation_id=888))
        service.on_hatif(self.tap("وريني الشقق", eid="r1"))
        service.on_hatif(self.tap("إيه، كلموني", eid="r2"))
        service.on_hatif(self.tap("إيقاف العروض", eid="r3"))
        # Abdullah booked a day later; Mona never did
        self.res_rows = [{"id": 999, "status": "new", "guestName": "abdullah  ALHARBI",
                          "reservationDate": "2026-12-01 08:00:00", "listingMapId": 437215},
                         {"id": 1000, "status": "cancelled", "guestName": "Mona Saad",
                          "reservationDate": "2026-12-01 08:00:00"}]
        self.posts.clear()
        sun9 = datetime.datetime(2026, 12, 6, 9, 0, tzinfo=RIYADH)
        r = service.weekly_tick(sun9)
        self.assertEqual(r["outcome"], "posted")
        st = r["stats"]
        self.assertEqual(st["hits"]["B1"]["n"], 2)
        self.assertEqual(st["hits"]["B1"]["booked"], 1)
        self.assertEqual(st["optouts"], 1)
        self.assertEqual(st["taps"]["ouja_owner_recontact"]["owner_call"], 1)
        self.assertEqual(st["taps"]["?"]["show_units"], 1)
        self.assertEqual(len(self.posts), 1)
        self.assertIn("تقرير حملات عوجا", self.posts[0][1])
        self.assertIn("انحجز منها 1", self.posts[0][1])
        self.assertEqual(service.weekly_tick(sun9 + datetime.timedelta(minutes=30))["outcome"], "not_due")
        self.assertEqual(len(self.posts), 1)

    def test_same_inquiry_id_confirmed_counts(self):
        self.now = datetime.datetime(2026, 11, 30, 12, 0, tzinfo=RIYADH)
        service.on_guest_message(self.item(mid="h9", guest="Guest"))
        self.res_rows = [{"id": 777, "status": "new", "guestName": "", "reservationDate": "2026-11-20"}]
        r = service.weekly_tick(datetime.datetime(2026, 12, 6, 9, 5, tzinfo=RIYADH))
        self.assertEqual(r["stats"]["hits"]["B1"]["booked"], 1)

    def test_booking_after_7_days_does_not_count(self):
        self.now = datetime.datetime(2026, 11, 29, 12, 0, tzinfo=RIYADH)
        service.on_guest_message(self.item(mid="h3"))
        self.res_rows = [{"id": 5, "status": "new", "guestName": "Abdullah Alharbi",
                          "reservationDate": "2026-12-08 10:00:00"}]
        r = service.weekly_tick(datetime.datetime(2026, 12, 6, 9, 0, tzinfo=RIYADH))
        self.assertEqual(r["stats"]["hits"]["B1"]["booked"], 0)

    def test_report_off(self):
        os.environ["CAMPAIGN_REPORT"] = "0"
        r = service.weekly_tick(datetime.datetime(2026, 12, 6, 9, 0, tzinfo=RIYADH))
        self.assertEqual(r["outcome"], "off")

    def test_empty_week_still_reports(self):
        r = service.weekly_tick(datetime.datetime(2026, 12, 6, 9, 0, tzinfo=RIYADH))
        self.assertEqual(r["outcome"], "posted")
        self.assertIn("ما وصلنا أي كلمة سر", self.posts[0][1])


# =============================================================== Discord cards + buttons
class CardTests(Base):
    """The card shows what the text showed, its buttons do the job in one press, and a press
    can never send twice, send in dry-run, or post a phone number."""

    def setUp(self):
        Base.setUp(self)
        self.cards, self.guest_sent = [], []

        def post(where, text, role="", card=None):
            self.posts.append((where, text, role))
            if card is not None:
                self.cards.append((where, card))
                db.set_alert_message(card["alert_id"], "msg-%d" % len(self.cards), "ch-1")

        host.HOST.post = post
        host.HOST.send_guest = lambda cid, body, comm: self.guest_sent.append((cid, body, comm)) or {"id": 1}

    def tearDown(self):
        host.HOST.send_guest = None
        Base.tearDown(self)

    def last(self):
        return self.cards[-1][1], "msg-%d" % len(self.cards)

    def blob(self, card):
        e = card["embed"]
        return "\n".join([e["title"], e.get("description", ""), (e.get("footer") or {}).get("text", "")]
                         + ["%s %s" % (f["name"], f["value"]) for f in e["fields"]]
                         + [b[1] for b in card["buttons"]] + [l[0] for l in card["links"]])

    def actions(self, card):
        return [b[0] for b in card["buttons"]]

    # ------------------------------------------------ code word
    def test_codeword_card_has_the_offer_and_one_press_buttons(self):
        service.on_guest_message(self.item())
        card, _ = self.last()
        b = self.blob(card)
        for want in ("Abdullah Alharbi", "Ouja | Malqa 2BR", "الأحد 29 نوفمبر", "600 ريال", "200 ريال",
                     "نورة", "15 دقيقة", "هلا Abdullah", "Special Offer", "② أرسلت العرض"):
            self.assertIn(want, b, want)
        self.assertEqual(self.actions(card), ["send", "claim", "done"])
        self.assertTrue(card["links"][0][0].startswith("①"))
        self.assertEqual(len(self.posts), 1)                 # one message: the card (text = fallback)

    def test_dryrun_press_sends_nothing_and_says_why(self):
        service.on_guest_message(self.item())
        _, mid = self.last()
        r = service.press(mid, "send", "نورة")
        self.assertFalse(r["ok"])
        self.assertIn("تجربة", r["msg"])
        self.assertEqual(self.guest_sent, [])
        self.assertIn("send", self.actions(r["card"]))       # still open: the button stays
        self.assertIn("⚠️", self.blob(r["card"]))

    def test_live_press_sends_once_and_closes_the_card(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        service.on_guest_message(self.item())
        _, mid = self.last()
        r = service.press(mid, "send", "نورة")
        self.assertTrue(r["ok"])
        self.assertEqual(len(self.guest_sent), 1)
        cid, body, comm = self.guest_sent[0]
        self.assertEqual((cid, comm), (5551, "airbnb"))
        self.assertIn("600 ريال", body)
        self.assertEqual(r["card"]["buttons"], [])
        self.assertIn("نورة", self.blob(r["card"]))
        again = service.press(mid, "send", "سارة")
        self.assertFalse(again["ok"])
        self.assertEqual(len(self.guest_sent), 1)            # never twice

    def test_firewall_refusal_keeps_it_open(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        host.HOST.send_guest = lambda cid, body, comm: "firewall_blocked"
        service.on_guest_message(self.item())
        _, mid = self.last()
        r = service.press(mid, "send", "نورة")
        self.assertFalse(r["ok"])
        self.assertIn("الجدار الناري", r["msg"])
        self.assertEqual(db.alert_by_message(mid)["state"], "open")

    def test_not_eligible_offers_the_polite_decline(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        self.cal_rows = cal((SUN, 1, 400, None), (SUN + datetime.timedelta(1), 0, 400, 12))
        service.on_guest_message(self.item())
        card, mid = self.last()
        self.assertEqual(self.actions(card), ["decline", "claim", "done"])
        self.assertIn("ما ينطبق — أرسل اعتذار", self.blob(card))
        r = service.press(mid, "decline", "نورة")
        self.assertTrue(r["ok"])
        self.assertIn("تاريخ ثاني", self.guest_sent[0][1])

    def test_unknown_date_asks_for_it(self):
        service.on_guest_message(self.item(checkin=None, checkout=None))
        card, _ = self.last()
        self.assertIn("اسأله عن التاريخ", self.blob(card))

    def test_booked_guest_gets_the_alteration_wording(self):
        service.on_guest_message(self.item(res_status="new"))
        card, _ = self.last()
        self.assertIn("أرسلت التعديل", self.blob(card))

    def test_claim_writes_the_name_once(self):
        service.on_guest_message(self.item())
        _, mid = self.last()
        self.assertTrue(service.press(mid, "claim", "نورة")["ok"])
        self.assertIn("نورة ماسكه", self.blob(service.paint(db.alert_by_message(mid)["id"])))
        self.assertFalse(service.press(mid, "claim", "سارة")["ok"])

    def test_unknown_message(self):
        self.assertFalse(service.press("nope", "send", "x")["ok"])

    def test_two_presses_at_once_only_one_acts(self):
        service.on_guest_message(self.item())
        aid = db.alert_by_message(self.last()[1])["id"]
        self.assertEqual(db.begin_alert_action(aid), "open")
        self.assertIsNone(db.begin_alert_action(aid))

    # ------------------------------------------------ owners
    def test_owner_card_buttons_and_no_answer_message(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=False))
        service.on_hatif(self.tap("إيه، كلموني", eid="oc1"))
        card, mid = self.last()
        self.assertEqual(self.cards[-1][0], "owners")
        self.assertEqual(self.actions(card), ["called", "noanswer", "notint", "claim"])
        r = service.press(mid, "noanswer", "فيصل")
        self.assertTrue(r["ok"])
        self.assertEqual(fake.sent[-1][2], config.OWNER_NOANSWER_TEXT)
        self.assertEqual(self.actions(r["card"]), ["called", "notint"])      # waiting for the call
        r = service.press(mid, "called", "فيصل")
        self.assertTrue(r["ok"])
        self.assertEqual(r["card"]["buttons"], [])

    # ------------------------------------------------ prepared WhatsApp replies
    def test_units_held_then_sent_by_one_press(self):
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=False))
        service.on_hatif(self.tap("وريني الشقق", eid="u1"))       # CAMPAIGN_BUTTONS_DRYRUN=1 → held
        card, mid = self.last()
        self.assertEqual(fake.sent, [])
        self.assertEqual(self.actions(card)[0], "send")
        self.assertIn("Ouja | الملقا غرفتين", self.blob(card))
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        r = service.press(mid, "send", "نورة")
        self.assertTrue(r["ok"])
        self.assertEqual(len(fake.sent), 1)
        self.assertIn("انرسل", self.blob(r["card"]))

    def test_auto_sent_card_says_so(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=False))
        service.on_hatif(self.tap("وش إيليت؟", eid="u2"))
        card, _ = self.last()
        self.assertIn("انرسل تلقائياً", self.blob(card))
        self.assertNotIn("send", self.actions(card))

    def test_opted_out_person_is_not_sent_from_a_card_either(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=False))
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "1"
        service.on_hatif(self.tap("وش إيليت؟", eid="u3"))
        _, mid = self.last()
        service.on_hatif(self.tap("إيقاف العروض", eid="u4"))
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        r = service.press(mid, "send", "نورة")
        self.assertFalse(r["ok"])
        self.assertEqual(fake.sent, [])

    # ------------------------------------------------ photo templates + privacy
    def test_photo_template_is_the_same_campaign(self):
        p = self.tap("وريني الشقق", eid="i1", interactiveReply={"id": "ouja_midweek_half_img_btn0",
                                                              "text": "وريني الشقق"})
        service.on_hatif(p)
        self.assertIn("ouja_midweek_half_img", self.posts[-1][1])
        self.assertIn("عرض نص", self.posts[-1][1])
        self.assertIn("الليلة الثانية بنص", self.blob(self.cards[-1][1]))
        self.assertEqual(engine.resolve_template("إيه، كلموني"), "ouja_owner_recontact")

    def test_no_phone_number_on_any_card_or_row(self):
        os.environ["CAMPAIGN_BUTTONS_DRYRUN"] = "0"
        fake = FakeHC()
        service._hatif_api = lambda: (fake, FakeCfg(dry=True))
        for i, label in enumerate(("إيه، كلموني", "وريني الشقق", "وش إيليت؟", "إيقاف العروض")):
            service.on_hatif(self.tap(label, eid="z%d" % i))
        everything = "\n".join(self.blob(c) for _, c in self.cards)
        rows = repr([db.alert(c["alert_id"]) for _, c in self.cards])
        self.assertNotIn("551234567", everything + rows)
        self.assertIn("••4567", everything)


if __name__ == "__main__":
    unittest.main()
