# -*- coding: utf-8 -*-
"""
«طلبات سام» pure engine — every rule that decides whether somebody is reminded, accused or
left alone. No Discord, no database, no clock.

Run: python3 -m unittest tests.test_rrdesk_engine
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import engine as oeng          # noqa: E402
from rrdesk import engine as e          # noqa: E402

RIY = oeng.tz()


def at(y, mo, d, h, mi=0):
    return datetime.datetime(y, mo, d, h, mi, tzinfo=RIY)


class Language(unittest.TestCase):
    def test_direction(self):
        self.assertEqual(e.direction("وش صار على المطالبة؟"), "ar2en")
        self.assertEqual(e.direction("Please send the invoice"), "en2ar")
        self.assertIsNone(e.direction("12345 !!"))
        # a mostly-English line with one Arabic word still goes to Arabic
        self.assertEqual(e.direction("Please upload the photos of 11B كنب today thanks"), "en2ar")
        # more than 30% Arabic → for Sam
        self.assertEqual(e.direction("ok تم رفع الصور والفاتورة"), "ar2en")

    def test_skip_rules(self):
        self.assertEqual(e.skip_reason("👍"), "trivial")
        self.assertEqual(e.skip_reason("<@123456789012345678>"), "trivial")
        self.assertEqual(e.skip_reason("HMPDWX82SK"), "trivial")
        self.assertEqual(e.skip_reason("https://airbnb.com/resolution/123"), "trivial")
        self.assertEqual(e.skip_reason("3,722"), "trivial")
        self.assertEqual(e.skip_reason("```" + chr(10) + "copy this" + chr(10) + "```"), "code_block")
        self.assertEqual(e.skip_reason("RR TICKET — the claim", is_bot=True), "bot_english")
        self.assertIsNone(e.skip_reason("صار له ٢٤ ساعة ينتظر الاعتماد", is_bot=True))
        self.assertEqual(e.skip_reason("anything", is_ours=True), "own")
        self.assertEqual(e.skip_reason("translated" + e.INVISIBLE_MARK), "own")
        self.assertIsNone(e.skip_reason("Can you send the photos?"))
        self.assertEqual(e.skip_reason("", has_embeds=True), "embeds_only")

    def test_phrase_table_is_free_and_normalised(self):
        self.assertEqual(e.phrase_lookup("تم ✅", "ar2en"), "Done.")
        self.assertEqual(e.phrase_lookup("أبشر طال عمرك", "ar2en"), "On it, sir.")
        self.assertEqual(e.phrase_lookup("Thanks!", "en2ar"), "شكراً")
        self.assertIsNone(e.phrase_lookup("please send the invoice", "en2ar"))
        self.assertEqual(e.phrase_lookup("roger", "en2ar", {"en2ar": {"roger": "تمام"}}), "تمام")

    def test_tatweel_does_not_crash_and_folds(self):
        self.assertEqual(e.normalize("تمـــام"), e.normalize("تمام"))
        self.assertEqual(e.phrase_lookup("تمـام", "ar2en"), "OK.")

    def test_cache_key_depends_on_direction_and_glossary(self):
        a = e.cache_key("Send it", "en2ar", 1)
        self.assertEqual(a, e.cache_key("send it!", "en2ar", 1))
        self.assertNotEqual(a, e.cache_key("Send it", "en2ar", 2))
        self.assertNotEqual(a, e.cache_key("Send it", "ar2en", 1))


class WorkingTime(unittest.TestCase):
    def test_add_is_the_inverse_of_worked_minutes(self):
        for start in (at(2026, 10, 20, 9, 0), at(2026, 10, 20, 12, 10), at(2026, 10, 20, 23, 50),
                      at(2026, 10, 21, 1, 0), at(2026, 10, 21, 1, 29), at(2026, 10, 21, 3, 0)):
            for m in (15, 30, 60, 180, 480, 960, 1500):
                due = e.add_work_minutes(start, m)
                self.assertAlmostEqual(e.worked_minutes(start, due), m, places=1)

    def test_night_ask_is_due_next_morning(self):
        # asked 01:00 with a 60-minute SLA: 30 minutes tonight, 30 after 11:00
        self.assertEqual(e.add_work_minutes(at(2026, 10, 21, 1, 0), 60), at(2026, 10, 21, 11, 30))
        # asked in the dead zone: the clock starts at 11:00
        self.assertEqual(e.add_work_minutes(at(2026, 10, 21, 4, 0), 60), at(2026, 10, 21, 12, 0))
        # across midnight inside working hours: plain addition
        self.assertEqual(e.add_work_minutes(at(2026, 10, 20, 23, 30), 60), at(2026, 10, 21, 0, 30))

    def test_in_work_hours(self):
        self.assertTrue(e.in_work_hours(at(2026, 10, 21, 0, 45)))
        self.assertFalse(e.in_work_hours(at(2026, 10, 21, 1, 30)))
        self.assertFalse(e.in_work_hours(at(2026, 10, 21, 10, 59)))
        self.assertTrue(e.in_work_hours(at(2026, 10, 21, 11, 0)))

    def test_urgent_via_aircover(self):
        self.assertTrue(e.is_urgent(True, {}))
        self.assertTrue(e.is_urgent(False, {"days_left": 3}))
        self.assertTrue(e.is_urgent(False, {"days_left": -2, "deadline_passed": True}))
        self.assertFalse(e.is_urgent(False, {"days_left": 4}))
        self.assertFalse(e.is_urgent(False, {}))
        self.assertEqual(e.sla_minutes(True), (30, 180))
        self.assertEqual(e.sla_minutes(False), (60, 480))
        self.assertEqual(e.sla_minutes(False, {"resp_min": 90}), (90, 480))


class StateMachine(unittest.TestCase):
    def test_happy_path(self):
        s = e.OPEN
        s = e.transition(s, "team_message")
        self.assertEqual(s, e.ACK)
        self.assertIsNone(e.transition(s, "team_message"))
        s = e.transition(s, "deliver")
        self.assertEqual(s, e.DELIVERED)
        self.assertEqual(e.transition(s, "got_it"), e.CONFIRMED)
        self.assertEqual(e.transition(s, "auto_confirm"), e.CONFIRMED_AUTO)

    def test_rework_returns_to_acknowledged(self):
        self.assertEqual(e.transition(e.DELIVERED, "not_what"), e.ACK)
        self.assertIsNone(e.transition(e.ACK, "not_what"))

    def test_terminal_states_accept_nothing(self):
        for t in e.TERMINAL:
            for ev in ("ack", "deliver", "got_it", "cancel", "ticket_closed", "not_what"):
                self.assertIsNone(e.transition(t, ev))

    def test_cancel_and_ticket_close_from_any_live_state(self):
        for s in (e.OPEN, e.ACK, e.DELIVERED):
            self.assertEqual(e.transition(s, "cancel"), e.CANCELLED)
            self.assertEqual(e.transition(s, "ticket_closed"), e.CLOSED_WITH_TICKET)

    def test_deliver_straight_from_open(self):
        self.assertEqual(e.transition(e.OPEN, "deliver"), e.DELIVERED)
        self.assertEqual(e.transition(e.ACK, "unavailable"), e.DELIVERED)
        self.assertIsNone(e.transition(e.DELIVERED, "unavailable"))


class Ladder(unittest.TestCase):
    clock = at(2026, 10, 20, 12, 0)

    def test_open_timetable(self):
        st = {s["step"]: s["at"] for s in e.ladder(e.OPEN, self.clock, False)}
        self.assertEqual(st["R1"], at(2026, 10, 20, 12, 30))
        self.assertEqual(st["R2"], at(2026, 10, 20, 13, 0))
        # no acknowledgement: the miss comes at 200% of the RESPONSE SLA, and the delivery
        # reminders that would come after it are not on the ladder at all
        self.assertEqual(st["MISS"], at(2026, 10, 20, 14, 0))
        self.assertNotIn("D1", st)
        # once acknowledged, the delivery reminders are back
        st = {s["step"]: s["at"] for s in e.ladder(e.ACK, self.clock, False)}
        self.assertEqual(st["D1"], at(2026, 10, 20, 18, 0))
        self.assertEqual(st["D2"], at(2026, 10, 20, 20, 0))

    def test_acknowledged_has_no_response_steps_and_misses_on_delivery(self):
        st = {s["step"]: s["at"] for s in e.ladder(e.ACK, self.clock, False)}
        self.assertNotIn("R1", st)
        self.assertNotIn("R2", st)
        # 960 working minutes from 12:00: 13.5 h tonight to 01:30, 2.5 h from 11:00
        self.assertEqual(st["MISS"], at(2026, 10, 21, 13, 30))

    def test_delivered_and_terminal_have_no_ladder(self):
        self.assertEqual(e.ladder(e.DELIVERED, self.clock, False), [])
        self.assertEqual(e.ladder(e.CONFIRMED, self.clock, False), [])

    def test_due_step_sends_only_the_latest(self):
        now = at(2026, 10, 20, 13, 5)          # R1 and R2 both due
        self.assertEqual(e.due_step(e.OPEN, self.clock, False, now)["step"], "R2")
        self.assertIsNone(e.due_step(e.OPEN, self.clock, False, now, sent={"R2"}))
        self.assertIsNone(e.due_step(e.OPEN, self.clock, False, at(2026, 10, 20, 12, 10)))
        # asleep through everything: wakes up to the MISS only
        self.assertEqual(e.due_step(e.OPEN, self.clock, False, at(2026, 10, 22, 12, 0))["step"],
                         "MISS")

    def test_urgent_ladder(self):
        st = {s["step"]: s["at"] for s in e.ladder(e.ACK, self.clock, True)}
        self.assertEqual(st["D2"], at(2026, 10, 20, 15, 0))
        self.assertEqual(st["MISS"], at(2026, 10, 20, 18, 0))

    def test_step_key_by_generation(self):
        self.assertEqual(e.step_key("R1"), "R1")
        self.assertEqual(e.step_key("R1", 2), "R1#2")

    def test_auto_confirm(self):
        d = at(2026, 10, 20, 12, 0)
        self.assertFalse(e.auto_confirm_due(d, d + datetime.timedelta(hours=47)))
        self.assertTrue(e.auto_confirm_due(d, d + datetime.timedelta(hours=48)))


class JudgeAndMercy(unittest.TestCase):
    def test_judge(self):
        self.assertIsNone(e.judge(0))
        self.assertEqual(e.judge(1), e.NOTICE)
        self.assertEqual(e.judge(2), e.WARN)
        self.assertEqual(e.judge(3), e.KPI_ONLY)
        self.assertEqual(e.judge(7), e.KPI_ONLY)

    def test_new_week_resets(self):
        self.assertEqual(e.period_key(datetime.date(2026, 10, 25)), "RR-2026-W43")
        self.assertEqual(e.period_key(datetime.date(2026, 10, 26)), "RR-2026-W44")

    def test_eligibility(self):
        self.assertTrue(e.miss_eligible("command", e.OPEN, "11"))
        self.assertTrue(e.miss_eligible("detected", e.ACK, "11"))
        self.assertFalse(e.miss_eligible("possible", e.OPEN, "11"))
        self.assertFalse(e.miss_eligible("pin", e.DELIVERED, "11"))
        self.assertFalse(e.miss_eligible("pin", e.CANCELLED, "11"))
        self.assertFalse(e.miss_eligible("pin", e.CLOSED_WITH_TICKET, "11"))
        self.assertFalse(e.miss_eligible("pin", e.OPEN, ""))
        self.assertFalse(e.miss_eligible("pin", e.OPEN, "11", unowned=True))
        self.assertFalse(e.miss_eligible("pin", e.OPEN, "11", owner_is_admin=True))
        self.assertFalse(e.miss_eligible("pin", e.OPEN, "11", owner_on_leave=True))


class Reask(unittest.TestCase):
    def test_same_file_ask_is_a_reask(self):
        live = [(1, ["photos", "invoice"], e.ACK), (2, ["info"], e.OPEN)]
        self.assertEqual(e.reask_of(["photos"], live), 1)
        self.assertIsNone(e.reask_of(["info"], live))          # two questions = two requests
        self.assertIsNone(e.reask_of(["video"], live))
        self.assertIsNone(e.reask_of(["photos"], [(1, ["photos"], e.DELIVERED)]))


class Burst(unittest.TestCase):
    def test_second_line_within_15_minutes_joins(self):
        t = at(2026, 10, 20, 22, 40)
        live = [(1, t, e.OPEN)]
        self.assertEqual(e.burst_of(t + datetime.timedelta(minutes=1), live), 1)
        self.assertIsNone(e.burst_of(t + datetime.timedelta(minutes=16), live))
        self.assertIsNone(e.burst_of(t + datetime.timedelta(minutes=1), [(1, t, e.ACK)]))


class Owner(unittest.TestCase):
    def test_order(self):
        kw = dict(opener=("30", "op"), responsible=("40", "resp"), lead=("50", "lead"),
                  excluded={"1", "2"}, calendar_dids={"30", "40"})
        self.assertEqual(e.choose_owner(mentioned=["1", "20"], **kw)["rule"], 1)
        self.assertEqual(e.choose_owner(mentioned=["1", "20"], **kw)["did"], "20")
        self.assertEqual(e.choose_owner(replied="21", **kw)["did"], "21")
        self.assertEqual(e.choose_owner(mentioned=["1"], role_mentioned=True, **kw)["rule"], 2)
        self.assertEqual(e.choose_owner(**kw)["rule"], 3)
        kw2 = dict(kw, calendar_dids={"40"})
        self.assertEqual(e.choose_owner(**kw2)["rule"], 4)
        r = e.choose_owner(lead=("50", "lead"))
        self.assertEqual((r["rule"], r["unowned"], r["did"]), (5, True, "50"))


class Kpis(unittest.TestCase):
    def test_insufficient_under_three(self):
        now = at(2026, 10, 25, 12)
        k = e.kpis([{"state": "confirmed", "asked_at": at(2026, 10, 20, 12).isoformat()}], now)
        self.assertTrue(k["insufficient"])
        self.assertIsNone(k["resp_on_time"])
        self.assertEqual(e.meets(k), {})

    def test_numbers(self):
        c = at(2026, 10, 20, 12)
        rd, dd = e.dues(c, False)
        rows = []
        for i, (ack_m, dlv_m, rw) in enumerate(((10, 120, 0), (90, 300, 1), (20, 600, 0),
                                                (None, None, 0))):
            rows.append({"state": "confirmed" if dlv_m else "open", "asked_at": c.isoformat(),
                         "clock_at": c.isoformat(), "resp_due": rd.isoformat(),
                         "deliv_due": dd.isoformat(), "rework": rw,
                         "acked_at": (c + datetime.timedelta(minutes=ack_m)).isoformat() if ack_m else None,
                         "delivered_at": (c + datetime.timedelta(minutes=dlv_m)).isoformat() if dlv_m else None})
        k = e.kpis(rows, at(2026, 10, 25, 12), voice_count=1, misses=1)
        self.assertEqual(k["owned"], 4)
        self.assertEqual(k["resp_on_time"], 0.5)       # 10 and 20 in, 90 late, never = late
        self.assertEqual(k["deliv_on_time"], 0.5)      # 120 + 300 in, 600 late, never = late
        self.assertEqual(k["median_resp_min"], 20.0)
        self.assertAlmostEqual(k["rework_rate"], 0.333, places=3)
        m = e.meets(k)
        self.assertFalse(m["resp_on_time"])
        self.assertFalse(m["misses"])
        self.assertFalse(m["voice"])


class Calibration(unittest.TestCase):
    def test_defaults_without_data(self):
        c = e.calibrate([], [])
        self.assertEqual((c["resp_min"], c["deliv_min"]), (60, 480))
        self.assertEqual(c["resp_source"], "default")

    def test_rounding_and_clamps(self):
        c = e.calibrate([10, 12, 15, 20, 25, 30], [100, 200, 300, 400, 500, 600])
        self.assertEqual(c["resp_min"], 30)            # p60 ≈ 20 → 15 → clamp 30
        self.assertEqual(c["deliv_min"], 420)          # p60 = 400 → 6.7 h → 7 h
        c = e.calibrate([500] * 6, [5000] * 6)
        self.assertEqual((c["resp_min"], c["deliv_min"]), (120, 960))
        self.assertEqual(c["resp_breach_share"], 1.0)

    def test_threshold(self):
        good = [(0.9, True, True)] * 20 + [(0.5, True, False)] * 5 + [(0.2, False, False)] * 10
        r = e.choose_threshold(good)
        self.assertEqual(r["mode"], "auto")
        self.assertAlmostEqual(r["threshold"], 0.55, places=2)
        bad = [(0.9, True, True)] * 5 + [(0.9, True, False)] * 5
        self.assertEqual(e.choose_threshold(bad)["mode"], "explicit")

    def test_majority(self):
        self.assertEqual(e.majority(["7", "7", "8", ""]), "7")
        self.assertIsNone(e.majority([]))


class Text(unittest.TestCase):
    def test_time_format(self):
        self.assertEqual(e.fmt_time(at(2026, 10, 20, 12, 30)), "12:30 PM")
        self.assertEqual(e.fmt_time(at(2026, 10, 20, 0, 5)), "12:05 AM")
        self.assertEqual(e.fmt_due_ar(at(2026, 10, 21, 13, 0), at(2026, 10, 20, 9)), "بكرة 1:00 م")


if __name__ == "__main__":
    unittest.main()
