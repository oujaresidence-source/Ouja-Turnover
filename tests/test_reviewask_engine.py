# -*- coding: utf-8 -*-
"""
«رفع التقييم» — the PURE engine. Every number the owner approved is locked here (spec §3, §6,
§8, §10 + the 2026-10-03 «ابدأ» ruling: a 0 / empty / None score is not a review at all).

Run: python3 -m unittest tests.test_reviewask_engine
"""

import datetime
import os
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reviewask import engine as E  # noqa: E402

TZ = E.tz()


def at(y, m, d, hh=0, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=TZ)


def rev(lid, raw, res=None, typ="guest-to-host", channel="Airbnb", source=None, rid=None):
    r = {"id": rid or "r%s-%s-%s" % (lid, res, raw), "listing_id": lid, "rating_raw": raw,
         "rating": 0, "channel": channel, "reservation_id": res}
    if source:
        r["source"] = source
    if typ is not None:
        r["raw"] = {"type": typ, "channelName": channel, "rating": raw}
    return r


def cfg(**kw):
    c = E.default_cfg()
    c.update(kw)
    return c


# ------------------------------------------------------------------ §3 the 4.75 line

class TestReviewsNeeded(unittest.TestCase):
    def test_spec_examples(self):
        self.assertEqual(E.reviews_needed(10, 90), 11)
        self.assertEqual(E.reviews_needed(47, 415), 64)
        self.assertEqual(E.reviews_needed(4, 38), 1)

    def test_above_line_needs_nothing(self):
        self.assertEqual(E.reviews_needed(4, 39), 0)
        self.assertEqual(E.reviews_needed(10, 100), 0)

    def test_needed_really_lifts_above(self):
        for n, r in ((10, 90), (47, 415), (4, 38), (3, 18), (120, 1100)):
            k = E.reviews_needed(n, r)
            self.assertGreater(Fraction(r + 10 * k, n + k), Fraction(19, 2))
            if k:
                self.assertLessEqual(Fraction(r + 10 * (k - 1), n + k - 1), Fraction(19, 2))

    def test_integer_math_no_float(self):
        self.assertIsInstance(E.reviews_needed(10, 90), int)


class TestInProgram(unittest.TestCase):
    def test_exactly_475_is_in(self):
        self.assertTrue(E.in_program(4, 38))          # 4.75 exactly
        self.assertTrue(E.in_program(20, 190))

    def test_anything_above_is_out(self):
        self.assertFalse(E.in_program(4, 39))         # 4.875
        self.assertFalse(E.in_program(100, 951))      # 4.755

    def test_fewer_than_three_is_in(self):
        self.assertTrue(E.in_program(0, 0))
        self.assertTrue(E.in_program(2, 20))          # two perfect reviews: still no Airbnb rating
        self.assertFalse(E.in_program(3, 30))


class TestScoreFilter(unittest.TestCase):
    """Owner ruling at «ابدأ»: 0 / empty / None is NOT a review — not in R, not in n."""

    def test_zero_and_empty_scores_are_not_reviews(self):
        for bad in (0, "0", None, "", "0.0", 0.0, "abc"):
            self.assertIsNone(E.review_score({"rating_raw": bad}), bad)
        self.assertEqual(E.review_score({"rating_raw": 10}), 10)
        self.assertEqual(E.review_score({"rating_raw": "8"}), 8)
        self.assertEqual(E.review_score({"rating_raw": 9.5}), Fraction(19, 2))

    def test_apartment_with_tens_and_zeros_averages_the_tens_only(self):
        reviews = [rev(1, 10, "a"), rev(1, 10, "b"), rev(1, 10, "c"),
                   rev(1, 0, "d"), rev(1, None, "e"), rev(1, "", "f"),
                   rev(1, 0, "g", typ=None, source="csv")]
        st = E.apartment_status(reviews)[1]
        self.assertEqual(st["n"], 3)
        self.assertEqual(st["R"], 30)
        self.assertEqual(st["avg"], 5.0)
        self.assertFalse(st["in_program"])           # 3 × 5★ = out; the zeros did not drag it in

    def test_zero_from_hostaway_and_from_seed_both_excluded(self):
        reviews = [rev(2, 10, "a"), rev(2, 10, "b"), rev(2, 10, "c"), rev(2, 10, "d"),
                   rev(2, 0, "e"), rev(2, 0, "f", typ=None, source="csv")]
        st = E.apartment_status(reviews)[2]
        self.assertEqual((st["n"], st["R"]), (4, 40))


class TestReviewFilter(unittest.TestCase):
    def test_host_to_guest_excluded(self):
        reviews = [rev(3, 10, "a"), rev(3, 10, "b"), rev(3, 10, "c"),
                   rev(3, 2, "d", typ="host-to-guest")]
        self.assertEqual(E.apartment_status(reviews)[3]["n"], 3)

    def test_non_airbnb_excluded(self):
        reviews = [rev(4, 10, "a"), rev(4, 2, "b", channel="Booking.com"),
                   rev(4, 2, "c", channel="bookingcom")]
        self.assertEqual(E.apartment_status(reviews)[4]["n"], 1)

    def test_seed_rows_without_type_count_as_guest_reviews(self):
        reviews = [rev(5, 8, "a", typ=None, source="csv")]
        self.assertTrue(E.is_guest_review(reviews[0]))
        self.assertTrue(E.is_guest_review({"raw": {"type": ""}}))
        self.assertFalse(E.is_guest_review({"raw": {"type": "host-to-guest"}}))
        self.assertEqual(E.apartment_status(reviews)[5]["n"], 1)

    def test_same_reservation_counts_once_live_wins(self):
        reviews = [rev(6, 6, "x", typ=None, source="csv", rid="csv:x"), rev(6, 10, "x", rid="77")]
        st = E.apartment_status(reviews)[6]
        self.assertEqual((st["n"], st["R"]), (1, 10))

    def test_channel_id_2018_is_airbnb(self):
        r = {"listing_id": 7, "rating_raw": 10, "channel": "", "raw": {"type": "guest-to-host",
                                                                       "channelId": 2018}}
        self.assertTrue(E.is_airbnb_review(r))


class TestApartmentStatus(unittest.TestCase):
    def test_pins_override_and_both_numbers_shown(self):
        reviews = [rev(8, 10, str(i)) for i in range(5)]           # 5.0, computed OUT
        st = E.apartment_status(reviews, overrides={8: {"mode": "in", "reason": "Airbnb يقول 4.7"}})[8]
        self.assertFalse(st["computed_in"])
        self.assertEqual(st["pinned"], "in")
        self.assertTrue(st["in_program"])
        st2 = E.apartment_status([rev(9, 2, "a")], overrides={9: {"mode": "out", "reason": "x"}})[9]
        self.assertTrue(st2["computed_in"])
        self.assertFalse(st2["in_program"])

    def test_needed_for_new_units_reaches_three(self):
        st = E.apartment_status([rev(10, 10, "a")])[10]
        self.assertEqual(st["needed"], 2)                 # 1 more would still show no rating

    def test_open_tickets_column_does_not_change_program(self):
        reviews = [rev(11, 10, str(i)) for i in range(5)]
        st = E.apartment_status(reviews, open_tickets={11: 3})[11]
        self.assertEqual(st["open_tickets"], 3)
        self.assertFalse(st["in_program"])

    def test_listing_with_only_tickets_appears(self):
        st = E.apartment_status([], open_tickets={12: 1})
        self.assertIn(12, st)
        self.assertTrue(st[12]["in_program"])             # no reviews at all = new unit


# ------------------------------------------------------------------ §8 call time

class TestCallTime(unittest.TestCase):
    def test_october_is_2000(self):
        self.assertEqual(E.call_time(datetime.date(2026, 10, 14), cfg()), "20:00")

    def test_june_is_2045(self):
        self.assertEqual(E.call_time(datetime.date(2027, 6, 10), cfg()), "20:45")
        self.assertEqual(E.call_time(datetime.date(2027, 5, 1), cfg()), "20:45")
        self.assertEqual(E.call_time(datetime.date(2027, 8, 31), cfg()), "20:45")
        self.assertEqual(E.call_time(datetime.date(2027, 9, 1), cfg()), "20:00")

    def test_ramadan_range_is_2130(self):
        c = cfg(ramadan=[(datetime.date(2027, 2, 8), datetime.date(2027, 3, 9))], hijri_month=None)
        self.assertEqual(E.call_time(datetime.date(2027, 2, 20), c), "21:30")
        self.assertEqual(E.call_time(datetime.date(2027, 3, 10), c), "20:00")

    def test_hijri_detector_wins_when_present(self):
        c = cfg(ramadan=[], hijri_month=lambda d: 9)
        self.assertEqual(E.call_time(datetime.date(2026, 10, 14), c), "21:30")

    def test_env_override_wins(self):
        c = cfg(call_at="19:15", ramadan=[(datetime.date(2027, 2, 8), datetime.date(2027, 3, 9))])
        self.assertEqual(E.call_time(datetime.date(2027, 2, 20), c), "19:15")
        self.assertEqual(E.call_time(datetime.date(2027, 6, 20), c), "19:15")

    def test_bad_env_falls_back_to_auto(self):
        self.assertEqual(E.call_time(datetime.date(2026, 10, 14), cfg(call_at="late")), "20:00")

    def test_ramadan_env_parser(self):
        self.assertEqual(E.parse_ramadan("2027-02-08:2027-03-09, junk"),
                         [(datetime.date(2027, 2, 8), datetime.date(2027, 3, 9))])
        self.assertEqual(E.parse_ramadan(""), [])


# ------------------------------------------------------------------ §10 language + templates

class TestLanguageAndTemplate(unittest.TestCase):
    def test_saudi_number_is_arabic(self):
        self.assertEqual(E.language("wa.me/966501234567"), "ar")
        self.assertEqual(E.language("966501234567"), "ar")

    def test_foreign_number_is_english(self):
        self.assertEqual(E.language("wa.me/447700900123"), "en")
        self.assertEqual(E.language(""), "ar")

    def test_unknown_placeholder_survives(self):
        out, unknown = E.render_template("هلا {الاسم} {مجهول}", {"الاسم": "سارة"})
        self.assertEqual(out, "هلا سارة {مجهول}")
        self.assertEqual(unknown, ["مجهول"])

    def test_all_placeholders(self):
        out, unknown = E.render_template("{الاسم}|{الموظف}|{الشقة}|{رابط_التقييم}",
                                         {"الاسم": "A", "الموظف": "B", "الشقة": "C",
                                          "رابط_التقييم": "D"})
        self.assertEqual((out, unknown), ("A|B|C|D", []))

    def test_pick_template_falls_back_to_arabic(self):
        t = {"ar": "عربي", "en": "", "call_script": "x"}
        self.assertEqual(E.pick_template(t, "en"), "عربي")
        self.assertEqual(E.pick_template({"ar": "ع", "en": "E"}, "en"), "E")

    def test_unit_short_and_guest_first(self):
        self.assertEqual(E.unit_short("Ouja | Narjis 101 self-entry"), "Narjis 101 self-entry")
        self.assertEqual(E.unit_short("Ouja|B13"), "B13")
        self.assertEqual(E.guest_first("Sara Al-Otaibi 12345"), "Sara")
        self.assertEqual(E.guest_first("1234"), "")

    def test_room_name_and_topic(self):
        name = E.room_name("Ouja | Narjis 101", "Sara Ali")
        self.assertTrue(name.startswith("تقييم-"))
        self.assertLessEqual(len(name), 90)
        self.assertIn("sara", name)
        self.assertEqual(E.topic("555", 12, 7), "ouja-rv:555 lid:12 seq:7")
        self.assertEqual(E.topic_reservation("ouja-rv:555 lid:12 seq:7"), "555")
        self.assertIsNone(E.topic_reservation("ouja-dp:555 seq:1"))


# ------------------------------------------------------------------ §4 eligibility

class TestEligibility(unittest.TestCase):
    def res(self, **kw):
        r = {"res_id": "1", "lid": 1, "status": "new", "channel": "airbnb",
             "arrival": "2026-10-10", "departure": "2026-10-14"}
        r.update(kw)
        return r

    def test_review_mode(self):
        self.assertEqual(E.eligibility(self.res(), in_program=True, care=False), ("review", ""))

    def test_care_mode_beats_rating(self):
        self.assertEqual(E.eligibility(self.res(), in_program=False, care=True), ("care", ""))

    def test_skips_have_reasons(self):
        self.assertEqual(E.eligibility(self.res(), in_program=False, care=False)[1], "out_of_program")
        self.assertEqual(E.eligibility(self.res(status="cancelled"), True, False)[1], "cancelled")
        self.assertEqual(E.eligibility(self.res(channel="direct"), True, False)[1], "not_airbnb")
        self.assertEqual(E.eligibility(self.res(channel="other"), True, True)[1], "not_airbnb")
        self.assertEqual(E.eligibility(self.res(), True, False, exists=True)[1], "duplicate")
        for code in ("out_of_program", "cancelled", "not_airbnb", "duplicate"):
            self.assertIn(code, E.SKIP_AR)

    def test_care_overlap(self):
        t = [{"created_at": "2026-10-11T10:00:00+03:00", "closed_at": None}]
        self.assertTrue(E.care_from_tickets(t, "2026-10-10", "2026-10-14"))
        old = [{"created_at": "2026-09-01T10:00:00+03:00", "closed_at": "2026-09-02T10:00:00+03:00"}]
        self.assertFalse(E.care_from_tickets(old, "2026-10-10", "2026-10-14"))
        still = [{"created_at": "2026-09-01T10:00:00+03:00", "closed_at": None}]
        self.assertTrue(E.care_from_tickets(still, "2026-10-10", "2026-10-14"))
        later = [{"created_at": "2026-10-20T10:00:00+03:00", "closed_at": None}]
        self.assertFalse(E.care_from_tickets(later, "2026-10-10", "2026-10-14"))


# ------------------------------------------------------------------ §6 the clock

def row(**kw):
    r = {"state": E.WAITING, "mode": "review", "day": "2026-10-14", "stage_due_at": None,
         "pinged_at": None, "remind_count": 0, "missed_at": None, "next_due_at": None,
         "calls_used": 0, "later_used": 0, "care_ok": 0}
    r.update(kw)
    return r


class TestClock(unittest.TestCase):
    C = cfg()

    def test_waiting_is_silent_until_wa_time(self):
        self.assertIsNone(E.next_action(row(), at(2026, 10, 14, 16, 59), self.C))
        a = E.next_action(row(), at(2026, 10, 14, 17, 0), self.C)
        self.assertEqual((a["act"], a["state"]), ("stage", E.WA_DUE))

    def test_care_mode_stages_care_due(self):
        a = E.next_action(row(mode="care"), at(2026, 10, 14, 17, 0), self.C)
        self.assertEqual(a["state"], E.CARE_DUE)

    def test_nothing_guest_facing_in_quiet_hours(self):
        # a room opened late: 22:00–13:00 silence holds the first ping until 13:00
        r = row(day="2026-10-14")
        for t in (at(2026, 10, 14, 22, 0), at(2026, 10, 15, 2, 0), at(2026, 10, 15, 12, 59)):
            self.assertIsNone(E.next_action(r, t, self.C), t)
        self.assertEqual(E.next_action(r, at(2026, 10, 15, 13, 0), self.C)["act"], "stage")

    def test_quiet_window_bounds(self):
        self.assertTrue(E.in_quiet(at(2026, 10, 14, 22, 0), "22:00", "13:00"))
        self.assertTrue(E.in_quiet(at(2026, 10, 15, 12, 59), "22:00", "13:00"))
        self.assertFalse(E.in_quiet(at(2026, 10, 15, 13, 0), "22:00", "13:00"))
        self.assertFalse(E.in_quiet(at(2026, 10, 14, 21, 59), "22:00", "13:00"))

    def staged(self, state=E.WA_DUE, sd=None, **kw):
        sd = sd or at(2026, 10, 14, 17, 0)
        base = dict(state=state, stage_due_at=E.iso(sd), pinged_at=E.iso(sd))
        if state == E.WA_DUE:
            base["next_due_at"] = E.iso(at(2026, 10, 15, 20, 0))
        base.update(kw)
        return row(**base)

    def test_wa_reminders_1800_and_1930(self):
        r = self.staged()
        self.assertIsNone(E.next_action(r, at(2026, 10, 14, 17, 59), self.C))
        self.assertEqual(E.next_action(r, at(2026, 10, 14, 18, 0), self.C)["act"], "remind")
        r2 = self.staged(remind_count=1)
        self.assertIsNone(E.next_action(r2, at(2026, 10, 14, 19, 29), self.C))
        self.assertEqual(E.next_action(r2, at(2026, 10, 14, 19, 30), self.C)["act"], "remind")
        r3 = self.staged(remind_count=2)
        self.assertIsNone(E.next_action(r3, at(2026, 10, 14, 21, 0), self.C))

    def test_wa_staff_miss_then_call_next_evening(self):
        r = self.staged(remind_count=2)
        a = E.next_action(r, at(2026, 10, 14, 22, 0), self.C)
        self.assertEqual(a["act"], "miss")
        self.assertNotIn("stage_due_at", a["fields"])     # a WhatsApp miss moves on to the call
        r.update(a["fields"])
        self.assertIsNone(E.next_action(r, at(2026, 10, 15, 19, 59), self.C))
        a = E.next_action(r, at(2026, 10, 15, 20, 0), self.C)
        self.assertEqual((a["act"], a["state"]), ("stage", E.CALL_DUE))

    def test_wa_sent_calls_at_call_time(self):
        r = row(state=E.WA_SENT, next_due_at=E.iso(at(2026, 10, 15, 20, 0)))
        self.assertIsNone(E.next_action(r, at(2026, 10, 15, 19, 59), self.C))
        self.assertEqual(E.next_action(r, at(2026, 10, 15, 20, 0), self.C)["state"], E.CALL_DUE)

    def test_call_reminders_45_and_2130(self):
        r = self.staged(E.CALL_DUE, sd=at(2026, 10, 15, 20, 0))
        self.assertEqual(E.next_action(r, at(2026, 10, 15, 20, 45), self.C)["act"], "remind")
        r["remind_count"] = 1
        self.assertIsNone(E.next_action(r, at(2026, 10, 15, 21, 29), self.C))
        self.assertEqual(E.next_action(r, at(2026, 10, 15, 21, 30), self.C)["act"], "remind")

    def test_staff_miss_rolls_the_same_attempt(self):
        r = self.staged(E.CALL_DUE, sd=at(2026, 10, 15, 20, 0), remind_count=2)
        a = E.next_action(r, at(2026, 10, 15, 22, 0), self.C)
        self.assertEqual(a["act"], "miss")
        self.assertEqual(a["fields"]["stage_due_at"], E.iso(at(2026, 10, 16, 20, 0)))
        self.assertEqual(a["fields"]["remind_count"], 0)
        self.assertNotIn("calls_used", a["fields"])          # the guest attempt is NOT consumed
        r.update(a["fields"])
        self.assertIsNone(E.next_action(r, at(2026, 10, 16, 19, 59), self.C))
        self.assertEqual(E.next_action(r, at(2026, 10, 16, 20, 0), self.C)["act"], "ping")

    def test_care_due_miss_rolls_to_next_call_time(self):
        r = self.staged(E.CARE_DUE, sd=at(2026, 10, 14, 17, 0), remind_count=2, mode="care")
        a = E.next_action(r, at(2026, 10, 14, 22, 0), self.C)
        self.assertEqual(a["fields"]["stage_due_at"], E.iso(at(2026, 10, 15, 20, 0)))

    def test_day_14_expires(self):
        r = row(state=E.WA_SENT, next_due_at=E.iso(at(2026, 10, 15, 20, 0)), day="2026-10-14")
        self.assertNotEqual((E.next_action(r, at(2026, 10, 27, 23, 58), self.C) or {}).get("act"),
                            "expire")
        a = E.next_action(r, at(2026, 10, 27, 23, 59), self.C)
        self.assertEqual((a["act"], a["state"]), ("expire", E.EXPIRED))
        p = row(state=E.PROMISED, day="2026-10-14")
        self.assertIsNone(E.next_action(p, at(2026, 10, 20, 20, 0), self.C))
        self.assertEqual(E.next_action(p, at(2026, 10, 27, 23, 59), self.C)["state"],
                         E.PROMISED_EXPIRED)

    def test_terminal_does_nothing(self):
        for st in E.TERMINAL:
            self.assertIsNone(E.next_action(row(state=st), at(2026, 10, 27, 23, 59), self.C))


# ------------------------------------------------------------------ §7 presses

class TestPresses(unittest.TestCase):
    C = cfg()
    NOW = at(2026, 10, 15, 20, 10)

    def test_second_noanswer_closes(self):
        r = row(state=E.CALL_DUE)
        p1 = E.press(r, "noanswer", self.NOW, self.C)
        self.assertEqual(p1["fields"]["state"], E.CALL_RETRY)
        self.assertEqual(p1["fields"]["calls_used"], 1)
        self.assertEqual(p1["fields"]["next_due_at"], E.iso(at(2026, 10, 16, 20, 0)))
        r.update(p1["fields"])
        r["state"] = E.CALL_DUE
        p2 = E.press(r, "noanswer", self.NOW, self.C)
        self.assertEqual(p2["fields"]["state"], E.NO_ANSWER_FINAL)

    def test_call_later_does_not_consume_once(self):
        r = row(state=E.CALL_DUE)
        p = E.press(r, "later", self.NOW, self.C)
        self.assertEqual(p["fields"]["state"], E.CALL_RETRY)
        self.assertEqual(p["fields"].get("calls_used", 0), 0)
        self.assertEqual(p["fields"]["later_used"], 1)
        r.update(p["fields"])
        r["state"] = E.CALL_DUE
        p2 = E.press(r, "later", self.NOW, self.C)            # second «بعدين» = «ما رد»
        self.assertEqual(p2["fields"]["calls_used"], 1)
        self.assertEqual(p2["fields"]["state"], E.CALL_RETRY)
        self.assertEqual(p2["kind"], "noanswer")

    def test_allowed_from_guards(self):
        self.assertIn(E.WA_DUE, E.ALLOWED_FROM["sent"])
        self.assertNotIn(E.CALL_DUE, E.ALLOWED_FROM["sent"])
        for k in E.ALLOWED_FROM:
            for st in E.TERMINAL:
                self.assertNotIn(st, E.ALLOWED_FROM[k], (k, st))

    def test_satisfied_unlocks_whatsapp(self):
        r = row(state=E.CARE_DUE, mode="care")
        p = E.press(r, "satisfied", self.NOW, self.C)
        self.assertEqual(p["fields"]["state"], E.WA_DUE)
        self.assertEqual(p["fields"]["care_ok"], 1)
        self.assertEqual(p["fields"]["next_due_at"], E.iso(at(2026, 10, 16, 20, 0)))

    def test_outcomes(self):
        self.assertEqual(E.press(row(state=E.CALL_DUE), "rated", self.NOW, self.C)["fields"]["state"],
                         E.PROMISED)
        self.assertEqual(E.press(row(state=E.CALL_DUE), "decline", self.NOW, self.C)["fields"]["state"],
                         E.DECLINED)
        self.assertEqual(E.press(row(state=E.CALL_DUE), "wrong", self.NOW, self.C)["fields"]["state"],
                         E.WRONG_NUMBER)
        self.assertEqual(E.press(row(state=E.WA_DUE), "sent", self.NOW, self.C)["fields"]["state"],
                         E.WA_SENT)
        np_ = E.press(row(state=E.WA_DUE), "no_phone", self.NOW, self.C)["fields"]
        self.assertEqual((np_["state"], np_["wa_note"]), (E.WA_SENT, "no_phone"))
        self.assertEqual(E.press(row(state=E.WA_SENT), "replied_quiet", self.NOW, self.C)
                         ["fields"]["state"], E.WA_SENT)
        self.assertEqual(E.press(row(state=E.WA_SENT), "replied_will", self.NOW, self.C)
                         ["fields"]["state"], E.PROMISED)

    def test_care_retry_returns_to_care(self):
        r = row(state=E.CALL_RETRY, mode="care", care_ok=0,
                next_due_at=E.iso(at(2026, 10, 15, 20, 0)))
        self.assertEqual(E.next_action(r, at(2026, 10, 15, 20, 0), self.C)["state"], E.CARE_DUE)
        r["care_ok"] = 1
        self.assertEqual(E.next_action(r, at(2026, 10, 15, 20, 0), self.C)["state"], E.CALL_DUE)

    def test_stage_buttons(self):
        self.assertEqual(E.stage_buttons(row(state=E.WAITING)), [])
        self.assertEqual(E.stage_buttons(row(state=E.PROMISED)), [])
        self.assertIn("sent", E.stage_buttons(row(state=E.WA_DUE)))
        self.assertIn("noanswer", E.stage_buttons(row(state=E.CALL_DUE)))
        self.assertIn("satisfied", E.stage_buttons(row(state=E.CARE_DUE, mode="care")))
        self.assertIn("satisfied", E.stage_buttons(row(state=E.CALL_RETRY, mode="care")))
        self.assertNotIn("satisfied", E.stage_buttons(row(state=E.CALL_RETRY, mode="review")))
        for st in E.TERMINAL:
            self.assertEqual(E.stage_buttons(row(state=st)), [])


if __name__ == "__main__":
    unittest.main()
