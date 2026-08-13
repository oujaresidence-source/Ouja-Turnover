# -*- coding: utf-8 -*-
"""«شقتك جاهزة» guest ready notice — synthetic, no network.

The gate is the whole feature: a message that reaches a real guest may only be
offered when a guest really arrives that day, we are still before his check-in
time, we have a conversation to write into, and the apartment has a guide link
in its Hostaway custom fields. Everything else must refuse with a plain reason
rather than half-send. The send itself is claimed once per reservation.
"""
import unittest
from datetime import datetime, timedelta

import bot


TODAY = datetime.now(bot.TZ).date()
TOMORROW = (TODAY + timedelta(days=1)).isoformat()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()
LID = 90210


def res(date_iso, **kw):
    r = {"id": 555001, "listingMapId": LID, "status": "new", "arrivalDate": date_iso,
         "checkInTime": "15:00", "conversationId": 77001, "guestName": "عبدالله المطيري"}
    r.update(kw)
    return r


class ReadyGate(unittest.TestCase):
    def setUp(self):
        self._api, self._guide, self._name = bot.api_get, bot.get_guide_url, bot._cleanproof_listing_name
        self._sent = dict(bot._ready_sent)
        bot.get_guide_url = lambda lid: "https://oujares.com/guide/d7"
        bot._cleanproof_listing_name = lambda lid: "Ouja | القيروان D7"
        bot._ready_sent.clear()

    def tearDown(self):
        bot.api_get, bot.get_guide_url = self._api, self._guide
        bot._cleanproof_listing_name = self._name
        bot._ready_sent.clear()
        bot._ready_sent.update(self._sent)

    def rows(self, *items):
        bot.api_get = lambda path, params=None: {"result": list(items)}

    # ---- the happy path ----
    def test_arrival_before_checkin_offers_the_notice(self):
        self.rows(res(TOMORROW))
        payload, why = bot._ready_context(LID, TOMORROW)
        self.assertEqual(why, "")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["cid"], "77001")
        self.assertEqual(payload["first"], "عبدالله")
        self.assertIn("https://oujares.com/guide/d7", payload["body"])
        self.assertIn("هلا عبدالله", payload["body"])

    # ---- every refusal ----
    def test_no_arrival_that_day(self):
        self.rows()
        self.assertEqual(bot._ready_context(LID, TOMORROW)[1], "no_arrival_today")

    def test_other_apartment_does_not_count(self):
        self.rows(res(TOMORROW, listingMapId=LID + 1))
        self.assertEqual(bot._ready_context(LID, TOMORROW)[1], "no_arrival_today")

    def test_cancelled_booking_does_not_count(self):
        self.rows(res(TOMORROW, status="cancelled"))
        self.assertEqual(bot._ready_context(LID, TOMORROW)[1], "no_arrival_today")

    def test_after_checkin_time_never_offers(self):
        self.rows(res(YESTERDAY))
        self.assertEqual(bot._ready_context(LID, YESTERDAY)[1], "after_checkin")

    def test_no_conversation_never_offers(self):
        self.rows(res(TOMORROW, conversationId=None))
        self.assertEqual(bot._ready_context(LID, TOMORROW)[1], "no_conversation")

    def test_no_guide_link_never_offers(self):
        bot.get_guide_url = lambda lid: None
        self.rows(res(TOMORROW))
        self.assertEqual(bot._ready_context(LID, TOMORROW)[1], "no_guide_link")

    def test_already_notified_guest_is_not_offered_again(self):
        self.rows(res(TOMORROW))
        bot._ready_sent["555001"] = "x"
        self.assertEqual(bot._ready_context(LID, TOMORROW)[1], "already_sent")

    def test_hostaway_down_refuses_quietly(self):
        def boom(path, params=None):
            raise RuntimeError("timeout")
        bot.api_get = boom
        self.assertEqual(bot._ready_context(LID, TOMORROW)[1], "hostaway_error")

    def test_earliest_checkin_wins_when_two_bookings(self):
        self.rows(res(TOMORROW, id=1, checkInTime="18:00"),
                  res(TOMORROW, id=2, checkInTime="13:00", conversationId=99))
        payload, _ = bot._ready_context(LID, TOMORROW)
        self.assertEqual(payload["res_id"], "2")


class SendClaim(unittest.TestCase):
    """One reservation gets told once — a double click cannot double-send."""

    def setUp(self):
        self._sent = dict(bot._ready_sent)
        bot._ready_sent.clear()

    def tearDown(self):
        bot._ready_sent.clear()
        bot._ready_sent.update(self._sent)

    def test_second_claim_is_refused(self):
        self.assertTrue(bot._ready_claim_send("999"))
        self.assertFalse(bot._ready_claim_send("999"))

    def test_release_after_a_failed_send_allows_a_retry(self):
        self.assertTrue(bot._ready_claim_send("999"))
        bot._ready_release_send("999")
        self.assertTrue(bot._ready_claim_send("999"))

    def test_empty_reservation_id_is_never_claimable(self):
        self.assertFalse(bot._ready_claim_send(""))


class LateClick(unittest.TestCase):
    """The question card can sit unanswered. Confirming it late must not send."""

    def test_future_checkin_is_not_passed(self):
        soon = (datetime.now(bot.TZ) + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
        self.assertFalse(bot._ready_checkin_passed(soon))

    def test_past_checkin_is_passed(self):
        gone = (datetime.now(bot.TZ) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
        self.assertTrue(bot._ready_checkin_passed(gone))

    def test_unreadable_time_refuses_rather_than_sends(self):
        for bad in ("", None, "غداً", "2026-13-99 99:99"):
            self.assertTrue(bot._ready_checkin_passed(bad), bad)


class MessageText(unittest.TestCase):
    def test_unusable_names_fall_back_to_a_neutral_greeting(self):
        for bad in ("", "Guest", "guests", "A", "ضيف", "123", None):
            self.assertEqual(bot._ready_guest_first_name(bad), "", bad)

    def test_real_names_keep_only_the_first_name(self):
        self.assertEqual(bot._ready_guest_first_name("عبدالله المطيري"), "عبدالله")
        self.assertEqual(bot._ready_guest_first_name("Sarah Al Otaibi"), "Sarah")

    def test_body_carries_the_link_and_no_second_signature(self):
        body = bot._ready_message_text("", "https://oujares.com/guide/x1")
        self.assertIn("هلا وغلا", body)
        self.assertIn("شقتك جاهزة لاستقبالك", body)
        self.assertIn("https://oujares.com/guide/x1", body)
        # send_guest_message appends the team signature — the body must not repeat it
        self.assertNotIn("فريق عوجا", body)


if __name__ == "__main__":
    unittest.main()
