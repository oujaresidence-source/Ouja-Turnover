# -*- coding: utf-8 -*-
"""Hatif (WhatsApp) availability replies — offline tests against a fake Hatif.

Locked here:
  * parse: Najdi/English date phrases → check-in/check-out, nights, guests, size, neighborhood;
    a bare number is never a date; past and over-long stays are refused with a reason
  * engine: HMAC check fails closed; reply text lists ONLY units the search returned as
    available with a price; "unknown" is never worded as "nothing available"
  * client: token cached, refreshed once on 401, secret never echoed
  * service: outbound messages and button taps are ignored (no self-reply loop); a delivery is
    handled once; dry-run sends nothing; the allowlist holds live sends to test numbers; only a
    conversation assigned to the bot seat is answered, and it is handed back afterwards
  * privacy: no phone number in the event log or in any Discord line

Run: python3 -m unittest tests.test_hatif
"""
import datetime
import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                   # noqa: E402
from hatif import client, config, db, engine, host, parse, service  # noqa: E402

TODAY = datetime.date(2026, 11, 13)        # a Friday
NOW = datetime.datetime(2026, 11, 13, 14, 0)
CH = "3a239350-68cf-26fa-6f12-1d5dbce4b5e6"
CONV = "conv-1"
BOT = "bot-user-1"
PHONE = "966551234567"
HOODS = [("al_malqa", "الملقا", "Al Malqa"), ("hittin", "حطين", "Hittin"),
         ("al_nuzha", "النزهة", "Al Nuzha")]


def P(text, today=TODAY):
    return parse.parse_request(text, today, HOODS)


class ParseTests(unittest.TestCase):
    def test_iso_range(self):
        r = P("2026-11-20 to 2026-11-22")
        self.assertTrue(r["ok"])
        self.assertEqual((r["check_in"], r["check_out"], r["nights"]), ("2026-11-20", "2026-11-22", 2))
        self.assertFalse(r["assumed_nights"])

    def test_day_month_slash_range(self):
        r = P("من 20/11 الى 23/11")
        self.assertEqual((r["check_in"], r["check_out"], r["nights"]), ("2026-11-20", "2026-11-23", 3))

    def test_arabic_digits_and_compact_range(self):
        r = P("٢٠-٢٢/١١")
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-11-20", "2026-11-22"))

    def test_month_name_with_nights(self):
        r = P("20 نوفمبر ليلتين")
        self.assertEqual((r["check_in"], r["check_out"], r["nights"]), ("2026-11-20", "2026-11-22", 2))
        r = P("5 dec 3 nights")
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-12-05", "2026-12-08"))

    def test_day_range_with_month_name(self):
        r = P("من 20 الى 23 نوفمبر")
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-11-20", "2026-11-23"))

    def test_single_date_assumes_one_night(self):
        r = P("20/11")
        self.assertTrue(r["ok"])
        self.assertEqual((r["check_in"], r["check_out"], r["nights"]), ("2026-11-20", "2026-11-21", 1))
        self.assertTrue(r["assumed_nights"])

    def test_relative_words(self):
        self.assertEqual(P("اليوم ليلة")["check_in"], "2026-11-13")
        self.assertEqual(P("بكرة ليلتين")["check_in"], "2026-11-14")
        self.assertEqual(P("بعد بكره")["check_in"], "2026-11-15")
        self.assertEqual(P("tomorrow 2 nights")["check_out"], "2026-11-16")

    def test_weekday_is_the_next_one(self):
        r = P("الخميس ليلتين")                    # today is Friday → next Thursday 19 Nov
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-11-19", "2026-11-21"))
        self.assertEqual(P("الجمعة")["check_in"], "2026-11-13")      # today counts
        self.assertEqual(P("thursday 3 nights")["check_out"], "2026-11-22")

    def test_two_weekdays(self):
        r = P("من الخميس الى السبت")
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-11-19", "2026-11-21"))
        r = P("الجمعة والسبت")                    # both nights → out Sunday
        self.assertEqual((r["check_in"], r["check_out"], r["nights"]), ("2026-11-13", "2026-11-15", 2))

    def test_dash_forms(self):
        self.assertEqual(P("20-11")["check_in"], "2026-11-20")
        self.assertEqual(P("20-11-2026 ليلتين")["check_out"], "2026-11-22")
        r = P("20-22")
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-11-20", "2026-11-22"))
        r = P("Nov 20-23")
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-11-20", "2026-11-23"))

    def test_day_without_month_is_the_coming_one(self):
        r = P("من 28 الى 30")
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-11-28", "2026-11-30"))
        r = P("يوم 25 ولمدة 3 ايام")
        self.assertEqual((r["check_in"], r["check_out"]), ("2026-11-25", "2026-11-28"))
        self.assertEqual(P("يوم 10 ليلتين")["check_in"], "2026-12-10")     # the 10th already passed

    def test_counts_and_clock_times_are_not_days(self):
        for t in ("من 2 الى 4 اشخاص", "ابي غرفتين 3-4 اشخاص", "من 9 الى 12 الليل",
                  "كم سعر الشقة 2-3 غرف", "رقمي 0551234567", "الساعة 3-4 العصر"):
            self.assertFalse(P(t)["ok"], t)

    def test_punctuation_does_not_hide_a_word(self):
        self.assertEqual(P("عندكم شي متاح الليلة؟")["check_in"], "2026-11-13")
        r = P("نهاية الاسبوع الجاي")                # «الاسبوع» here is not 7 nights
        self.assertEqual((r["check_in"], r["nights"]), ("2026-11-19", 2))

    def test_weekend(self):
        r = P("الويكند")
        self.assertEqual((r["check_in"], r["check_out"], r["nights"]), ("2026-11-19", "2026-11-21", 2))

    def test_nights_words(self):
        self.assertEqual(P("20/11 ثلاث ليالي")["nights"], 3)
        self.assertEqual(P("20/11 ٤ ليالي")["nights"], 4)
        self.assertEqual(P("20/11 اسبوع")["nights"], 7)
        self.assertEqual(P("20/11 يومين")["nights"], 2)

    def test_guests_size_neighborhood(self):
        r = P("الخميس ليلتين غرفتين 4 اشخاص في الملقا")
        self.assertEqual((r["guests"], r["type"], r["bedrooms"], r["neighborhood"]), (4, "2br", 2, "al_malqa"))
        self.assertEqual(P("20/11 استديو")["type"], "studio")
        self.assertEqual(P("20/11 غرفة وصالة")["type"], "1br")
        self.assertEqual(P("20/11 ثلاث غرف")["type"], "3br")
        r = P("20/11 اربع غرف")
        self.assertEqual((r["type"], r["bedrooms"]), (None, 4))
        self.assertEqual(P("20/11 شخصين")["guests"], 2)
        self.assertEqual(P("20/11 hittin")["neighborhood"], "hittin")

    def test_a_bare_number_is_not_a_date(self):
        for t in ("3 غرف", "ابي شقة 4 اشخاص", "كم السعر", "السلام عليكم", "500", ""):
            r = P(t)
            self.assertFalse(r["ok"], t)
            self.assertEqual(r["reason"], "no_dates", t)

    def test_year_rolls_forward(self):
        r = P("5/1 ليلتين")                       # 5 Jan already passed in 2026 → 2027
        self.assertEqual(r["check_in"], "2027-01-05")

    def test_explicit_past_is_refused(self):
        r = P("2026-11-01 to 2026-11-03")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "past")

    def test_checkout_before_checkin_is_refused(self):
        r = P("2026-11-25 to 2026-11-22")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "bad_range")

    def test_long_stay_goes_to_monthly(self):
        r = P("20/11 شهر")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "monthly")
        r = P("2026-11-20 to 2027-01-20")
        self.assertEqual(r["reason"], "monthly")

    def test_impossible_date(self):
        self.assertFalse(P("31/2")["ok"])


def unit(i, name, total, nights=2, area="الملقا", avail=True, bedrooms=2):
    return {"id": i, "name_ar": name, "area": area, "bedrooms": bedrooms, "available": avail,
            "nights": nights, "est_total": total, "est_avg": (round(total / nights) if total else None)}


REQ = {"ok": True, "check_in": "2026-11-19", "check_out": "2026-11-21", "nights": 2,
       "guests": None, "type": None, "bedrooms": None, "neighborhood": None, "assumed_nights": False}


class EngineTests(unittest.TestCase):
    def test_signature(self):
        raw = b'{"a":1}'
        sig = hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
        self.assertTrue(engine.verify_signature("s3cret", raw, sig))
        self.assertTrue(engine.verify_signature("s3cret", raw, sig.upper()))
        self.assertFalse(engine.verify_signature("s3cret", raw + b" ", sig))
        self.assertFalse(engine.verify_signature("s3cret", raw, ""))
        self.assertFalse(engine.verify_signature("s3cret", raw, None))
        self.assertFalse(engine.verify_signature("", raw, sig))          # no secret ⇒ closed

    def test_reply_lists_available_units_with_price_and_link(self):
        out = {"browse": False, "invalid_dates": False, "avail_error": False,
               "results": [unit(437215, "Ouja | Malqa 2BR", 1200), unit(441858, "Ouja | Cinema", 1540)]}
        t = engine.build_reply(REQ, out, "oujares.com")
        self.assertIn("Ouja | Malqa 2BR", t)
        self.assertIn("1,200", t)
        self.assertIn("oujares.com/apartments/437215", t)
        self.assertIn("oujares.com/apartments/441858", t)
        self.assertIn("19/11", t)
        self.assertIn("21/11", t)
        self.assertIn("Airbnb", t)
        self.assertLessEqual(len(t), 4096)

    def test_units_without_a_confirmed_price_are_not_listed(self):
        out = {"avail_error": True, "results": [unit(1, "Known", 900), unit(2, "NoPrice", None),
                                                 dict(unit(3, "Unknown", None), available=None)]}
        t = engine.build_reply(REQ, out, "oujares.com")
        self.assertIn("Known", t)
        self.assertNotIn("NoPrice", t)
        self.assertNotIn("Unknown", t)
        self.assertIn("search?check_in=2026-11-19&check_out=2026-11-21", t)

    def test_unknown_is_never_worded_as_full(self):
        t = engine.build_reply(REQ, {"avail_error": True, "results": []}, "oujares.com")
        self.assertNotIn("ما لقيت", t)
        self.assertIn("ما قدرت", t)
        t = engine.build_reply(REQ, {"avail_error": False, "results": []}, "oujares.com")
        self.assertIn("ما لقيت", t)

    def test_cap_and_more_line(self):
        res = [unit(i, "U%d" % i, 1000 + i) for i in range(1, 10)]
        t = engine.build_reply(REQ, {"avail_error": False, "results": res}, "oujares.com", limit=6)
        self.assertIn("U6", t)
        self.assertNotIn("U7", t)
        tail = t.split("U6")[1].split("\n", 2)[2]         # everything after the 6th unit's link
        self.assertIn("search?check_in=", tail)
        self.assertNotRegex(tail, r"\d+\s*شق")            # owner rule: never state how many

    def test_bedroom_filter_for_sizes_the_site_has_no_tag_for(self):
        req = dict(REQ, bedrooms=4)
        res = [unit(1, "Two", 900, bedrooms=2), unit(2, "Four", 2000, bedrooms=4)]
        t = engine.build_reply(req, {"avail_error": False, "results": res}, "oujares.com")
        self.assertIn("Four", t)
        self.assertNotIn("Two", t)

    def test_assumed_one_night_is_said(self):
        req = dict(REQ, check_out="2026-11-20", nights=1, assumed_nights=True)
        t = engine.build_reply(req, {"avail_error": False, "results": [unit(1, "A", 500, nights=1)]}, "oujares.com")
        self.assertIn("ليلة وحدة", t)

    def test_help_texts(self):
        for reason in ("no_dates", "past", "bad_range", "monthly"):
            t = engine.help_text(reason)
            self.assertTrue(t and len(t) < 600, reason)
        self.assertIn("شهري", engine.help_text("monthly"))

    def test_phone(self):
        self.assertEqual(engine.normalize_phone("+966 55 123 4567"), "966551234567")
        self.assertEqual(engine.normalize_phone("0551234567"), "966551234567")
        self.assertIsNone(engine.normalize_phone(""))


class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._b, self.text = status, body, json.dumps(body or {})

    def json(self):
        if self._b is None:
            raise ValueError("no json")
        return self._b


class FakeHatif:
    def __init__(self):
        self.calls, self.tokens = [], 0
        self.assignee = BOT
        self.phone = PHONE
        self.fail_401_once = False
        self.send_status = 200

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if url.endswith("/connect/token"):
            self.tokens += 1
            return Resp(200, {"access_token": "tok%d" % self.tokens, "token_type": "Bearer", "expires_in": 3600})
        if self.fail_401_once:
            self.fail_401_once = False
            return Resp(401, {})
        if "/conversations/service-account/" in url and url.endswith("/assign"):
            b = kw.get("json") or {}
            self.assignee = b.get("assignedUserId")
            return Resp(200, {})
        if "/conversations/service-account/" in url:
            return Resp(200, {"id": CONV, "status": 1, "phoneNumber": self.phone,
                              "channelId": CH, "assigneeId": self.assignee})
        if url.endswith("/whatsapp/service-account/sendText"):
            return Resp(self.send_status, {"status": "Sent", "conversationEventId": "out-1"})
        return Resp(404, {})

    def sent(self):
        return [c[2]["json"] for c in self.calls if c[1].endswith("/sendText")]

    def assigns(self):
        return [c[2].get("json") for c in self.calls if c[1].endswith("/assign")]


def inbound(text, eid="ev-1", **over):
    p = {"workspaceId": "w", "channelId": CH, "conversationId": CONV, "conversationEventId": eid,
         "contactId": "c1", "messageId": "wamid.1", "direction": "Inbound", "messageType": "Text",
         "body": text, "status": "Delivered"}
    p.update(over)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hatif_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        for k in list(os.environ):
            if k.startswith("HATIF_"):
                os.environ.pop(k)
        os.environ.update({"HATIF_CLIENT_ID": "cid", "HATIF_CLIENT_SECRET": "s3cret",
                           "HATIF_WEBHOOK_SECRET": "whsec", "HATIF_CHANNEL_ID": CH,
                           "HATIF_BOT_USER_ID": BOT, "HATIF_DRYRUN": "0", "HATIF_ACK": "0"})
        self.h = FakeHatif()
        client.set_session_for_tests(self.h)
        service.reset_for_tests()
        self.msgs, self.searches = [], []
        self.out = {"avail_error": False, "results": [unit(437215, "Ouja | Malqa 2BR", 1200)]}

        def search(ci, co, guests, typ, hood):
            self.searches.append((ci, co, guests, typ, hood))
            return self.out
        host.wire({"now": lambda: NOW, "notify": lambda t: self.msgs.append(t),
                   "log_event": lambda c, t: None, "search": search,
                   "neighborhoods": lambda: HOODS, "site_host": lambda: "oujares.com"})

    def run_one(self, payload):
        return service.handle(payload)


class ClientTests(Base):
    def test_token_cached_and_refreshed_on_401(self):
        client.get_conversation(CONV)
        client.get_conversation(CONV)
        self.assertEqual(self.h.tokens, 1)
        self.h.fail_401_once = True
        c = client.get_conversation(CONV)
        self.assertEqual(c["assigneeId"], BOT)
        self.assertEqual(self.h.tokens, 2)

    def test_token_request_shape(self):
        client.get_conversation(CONV)
        m, url, kw = self.h.calls[0]
        self.assertEqual((m, url), ("POST", "https://api.voxa.sa/connect/token"))
        self.assertEqual(kw["data"]["grant_type"], "client_credentials")
        self.assertEqual(kw["data"]["scope"], "VoxaAPI")

    def test_secret_never_in_errors(self):
        self.h.send_status = 500
        with self.assertRaises(client.HatifError) as cm:
            client.send_text(CH, PHONE, "hi")
        self.assertNotIn("s3cret", str(cm.exception))


class ServiceTests(Base):
    def test_happy_path_sends_one_reply_and_hands_back(self):
        r = self.run_one(inbound("الخميس ليلتين غرفتين"))
        self.assertEqual(r["outcome"], "sent")
        self.assertEqual(self.searches, [("2026-11-19", "2026-11-21", None, "2br", None)])
        sent = self.h.sent()
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["toNumber"], PHONE)
        self.assertEqual(sent[0]["channelId"], CH)
        self.assertIn("oujares.com/apartments/437215", sent[0]["text"])
        self.assertEqual(self.h.assigns(), [{}])                # handed back to the menu

    def test_ack_goes_first_when_enabled(self):
        os.environ["HATIF_ACK"] = "1"
        self.run_one(inbound("الخميس ليلتين"))
        sent = self.h.sent()
        self.assertEqual(len(sent), 2)
        self.assertNotIn("oujares.com/apartments/437215", sent[0]["text"])

    def test_outbound_and_taps_and_other_channels_are_ignored(self):
        for p in (inbound("الخميس ليلتين", direction="Outbound"),
                  inbound("الخميس ليلتين", eid="e2", interactiveReply={"id": "x", "text": "الخميس"}),
                  inbound("الخميس ليلتين", eid="e3", channelId="other"),
                  inbound("", eid="e4"),
                  inbound("x", eid="e5", messageType="Image")):
            self.assertEqual(self.run_one(p)["outcome"], "ignored")
        self.assertEqual(self.h.calls, [])
        self.assertEqual(self.searches, [])

    def test_a_delivery_is_handled_once(self):
        self.run_one(inbound("الخميس ليلتين"))
        r = self.run_one(inbound("الخميس ليلتين"))
        self.assertEqual(r["outcome"], "duplicate")
        self.assertEqual(len(self.h.sent()), 1)

    def test_not_assigned_to_the_bot_means_silence(self):
        self.h.assignee = "some-human"
        r = self.run_one(inbound("الخميس ليلتين"))
        self.assertEqual(r["outcome"], "not_ours")
        self.assertEqual(self.h.sent(), [])
        self.assertEqual(self.searches, [])
        self.h.assignee = None
        self.assertEqual(self.run_one(inbound("الخميس ليلتين", eid="e2"))["outcome"], "not_ours")

    def test_dryrun_sends_nothing_but_reports(self):
        os.environ["HATIF_DRYRUN"] = "1"
        r = self.run_one(inbound("الخميس ليلتين"))
        self.assertEqual(r["outcome"], "dryrun")
        self.assertEqual(self.h.sent(), [])
        self.assertEqual(self.h.assigns(), [])
        self.assertTrue(any("oujares.com/apartments/437215" in m for m in self.msgs))

    def test_dryrun_is_the_default(self):
        os.environ.pop("HATIF_DRYRUN")
        self.assertEqual(self.run_one(inbound("الخميس ليلتين"))["outcome"], "dryrun")
        self.assertEqual(self.h.sent(), [])

    def test_allowlist_holds_live_sends_to_test_numbers(self):
        os.environ["HATIF_TEST_NUMBERS"] = "+966 50 000 0000"
        r = self.run_one(inbound("الخميس ليلتين"))
        self.assertEqual(r["outcome"], "dryrun")
        self.assertEqual(self.h.sent(), [])
        os.environ["HATIF_TEST_NUMBERS"] = "0500000000, 0551234567"
        r = self.run_one(inbound("الخميس ليلتين", eid="e2"))
        self.assertEqual(r["outcome"], "sent")

    def test_no_credentials_is_listen_only(self):
        os.environ.pop("HATIF_CLIENT_ID")
        r = self.run_one(inbound("الخميس ليلتين"))
        self.assertEqual(r["outcome"], "observed")
        self.assertEqual(self.h.calls, [])
        self.assertTrue(self.msgs)
        r = self.run_one(inbound("السلام عليكم", eid="e2"))      # not dates → nothing to show
        self.assertEqual(r["outcome"], "ignored")

    def test_unreadable_dates_get_help_then_a_human(self):
        os.environ["HATIF_HUMAN_USER_ID"] = "nasser"
        r = self.run_one(inbound("ابي شقة حلوة"))
        self.assertEqual(r["outcome"], "help")
        self.assertEqual(len(self.h.sent()), 1)
        self.assertEqual(self.h.assigns(), [])                  # still ours: the guest tries again
        r = self.run_one(inbound("مدري", eid="e2"))
        self.assertEqual(r["outcome"], "handoff")
        self.assertEqual(self.h.assigns(), [{"assignedUserId": "nasser"}])

    def test_send_failure_is_recorded_not_raised(self):
        self.h.send_status = 500
        r = self.run_one(inbound("الخميس ليلتين"))
        self.assertEqual(r["outcome"], "error")
        self.assertTrue(any("تعذر" in m or "خطأ" in m for m in self.msgs))

    def test_rate_cap(self):
        os.environ["HATIF_MAX_PER_MIN"] = "2"
        outs = []
        for i in range(4):
            self.h.assignee = BOT                  # the menu hands each new request to the bot
            outs.append(self.run_one(inbound("الخميس ليلتين", eid="e%d" % i))["outcome"])
        self.assertEqual(outs.count("sent"), 2)
        self.assertEqual(outs.count("throttled"), 2)

    def test_privacy_no_phone_anywhere_we_keep(self):
        self.run_one(inbound("الخميس ليلتين"))
        blob = json.dumps(db.recent(50), ensure_ascii=False) + " ".join(self.msgs)
        self.assertNotIn(PHONE, blob)
        self.assertNotIn("551234567", blob)

    def test_status_shape(self):
        self.run_one(inbound("الخميس ليلتين"))
        st = service.status()
        self.assertEqual(st["dryrun"], False)
        self.assertTrue(st["configured"])
        self.assertEqual(st["events"][0]["outcome"], "sent")
        self.assertNotIn("s3cret", json.dumps(st))
        self.assertNotIn("whsec", json.dumps(st))


class RouteTests(Base):
    """The public door: signed or refused, answered at once, work done in the background."""

    def setUp(self):
        Base.setUp(self)
        from aiohttp import web
        from hatif import routes
        self.jobs, self.authed = [], False
        host.wire({"web": web, "background": lambda fn: self.jobs.append(fn), "run": None,
                   "dash_auth": lambda request: self.authed,
                   "json_response": lambda data, status=200: web.json_response(data, status=status)})
        self._web, self._routes = web, routes

    def app(self):
        a = self._web.Application()                # a fresh app per call: one event loop each
        self._routes.register_routes(a)
        return a

    def call(self, method, path, raw=b"", headers=None):
        import asyncio
        from aiohttp.test_utils import TestClient, TestServer

        async def go():
            async with TestClient(TestServer(self.app())) as c:
                r = await c.request(method, path, data=raw, headers=headers or {})
                return r.status, await r.json()
        return asyncio.run(go())

    def signed(self, payload, secret="whsec"):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return raw, {"X-Voxa-Signature": hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()}

    def test_good_signature_is_acked_and_queued(self):
        raw, h = self.signed(inbound("الخميس ليلتين"))
        st, _ = self.call("POST", "/hatif/webhook", raw, h)
        self.assertEqual(st, 200)
        self.assertEqual(len(self.jobs), 1)
        self.assertEqual(self.h.calls, [])                 # nothing ran inside the request
        self.assertEqual(self.jobs[0]()["outcome"], "sent")

    def test_bad_or_missing_signature_is_refused(self):
        raw, h = self.signed(inbound("الخميس ليلتين"), secret="wrong")
        self.assertEqual(self.call("POST", "/hatif/webhook", raw, h)[0], 401)
        self.assertEqual(self.call("POST", "/hatif/webhook", raw)[0], 401)
        self.assertEqual(self.jobs, [])

    def test_no_secret_configured_refuses_everything(self):
        os.environ.pop("HATIF_WEBHOOK_SECRET")
        raw, h = self.signed(inbound("الخميس ليلتين"), secret="")
        self.assertEqual(self.call("POST", "/hatif/webhook", raw, h)[0], 401)
        self.assertEqual(self.jobs, [])

    def test_our_own_outgoing_messages_are_not_even_queued(self):
        raw, h = self.signed(inbound("المتاح من 19/11", direction="Outbound"))
        self.assertEqual(self.call("POST", "/hatif/webhook", raw, h)[0], 200)
        self.assertEqual(self.jobs, [])

    def test_status_needs_a_login_and_hides_secrets(self):
        self.assertEqual(self.call("GET", "/api/hatif/status")[0], 401)
        self.authed = True
        st, body = self.call("GET", "/api/hatif/status")
        self.assertEqual(st, 200)
        self.assertNotIn("whsec", json.dumps(body))
        self.assertNotIn("s3cret", json.dumps(body))

    def test_browser_probe(self):
        st, body = self.call("GET", "/hatif/webhook")
        self.assertEqual((st, body["hatif"]), (200, "listening"))


class ConfigTests(Base):
    def test_defaults_are_safe(self):
        for k in list(os.environ):
            if k.startswith("HATIF_"):
                os.environ.pop(k)
        self.assertTrue(config.dryrun())
        self.assertFalse(config.configured())
        self.assertEqual(config.webhook_secret(), "")
        self.assertEqual(config.gate(), "assigned")


if __name__ == "__main__":
    unittest.main()
