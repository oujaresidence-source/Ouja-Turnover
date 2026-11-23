# -*- coding: utf-8 -*-
"""
«المقاولات» rulebook, locked. Owner decisions 2026-11-23:
  - a project's lines come from the signed quote; each line gets ONE date
  - lines are in work order: a date earlier than the line above is refused
  - «ابدأ» works only with owner + unit + site supervisor + signed + paid + dates in order
  - reminders: 2 days before (heads-up), the due day 4 PM «خلص؟», 7 PM → Asil, next morning → Faisal
  - never a reminder on Friday
  - a reminder planned before the project started, or long past, is never sent late

Run: python3 -m unittest tests.test_contracting_engine
"""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracting import engine  # noqa: E402


def item(i, due, status="open", **kw):
    d = {"id": "it%d" % i, "pos": i, "name": "بند %d" % i, "due": due, "status": status,
         "is_handover": 0}
    d.update(kw)
    return d


class TestParsing(unittest.TestCase):
    def test_pasted_quote_lines(self):
        txt = "رفع مساحي للتراس\t350\nمنقل غاز مع تمديد الغاز   1,900\nكنب خارجي - 4000.50\n\n   \nسطر بدون مبلغ"
        rows = engine.parse_lines(txt)
        self.assertEqual([r["name"] for r in rows],
                         ["رفع مساحي للتراس", "منقل غاز مع تمديد الغاز", "كنب خارجي", "سطر بدون مبلغ"])
        self.assertEqual([r["amount"] for r in rows], [350.0, 1900.0, 4000.5, None])

    def test_arabic_digits_amount(self):
        self.assertEqual(engine.parse_lines("سرير ٧٠٠")[0]["amount"], 700.0)

    def test_dates(self):
        today = dt.date(2026, 11, 23)
        self.assertEqual(engine.parse_date("2026-12-01", today), "2026-12-01")
        self.assertEqual(engine.parse_date("1/12/2026", today), "2026-12-01")
        self.assertEqual(engine.parse_date("٥/١٢", today), "2026-12-05")
        self.assertEqual(engine.parse_date("3/1", today), "2027-01-03")   # already past → next year
        self.assertIsNone(engine.parse_date("بكرة", today))
        self.assertIsNone(engine.parse_date("31/2/2026", today))


class TestOrderAndStartGate(unittest.TestCase):
    def proj(self, **kw):
        p = {"owner": "أ. عبدالعزيز الزاحم", "unit": "D2", "supervisor": "أبو أمين",
             "signed": 1, "paid": 1}
        p.update(kw)
        return p

    def test_out_of_order_line_is_named(self):
        its = [item(1, "2026-11-24"), item(2, "2026-11-30"), item(3, "2026-11-26")]
        probs = engine.order_problems(its)
        self.assertEqual(list(probs), ["it3"])
        self.assertIn("فوقه", probs["it3"])

    def test_same_day_is_fine_missing_date_is_not(self):
        its = [item(1, "2026-11-24"), item(2, "2026-11-24"), item(3, "")]
        self.assertEqual(list(engine.order_problems(its)), ["it3"])

    def test_ready_project_starts(self):
        its = [item(1, "2026-11-24"), item(2, "2026-11-30")]
        self.assertTrue(engine.start_check(self.proj(), its)["ok"])

    def test_every_missing_piece_is_listed(self):
        its = [item(1, "2026-11-30"), item(2, "2026-11-24")]
        res = engine.start_check(self.proj(owner="", unit=" ", supervisor="", signed=0, paid=0), its)
        self.assertFalse(res["ok"])
        for word in ("المالك", "الوحدة", "مشرف", "توقيع", "الدفعة", "التواريخ"):
            self.assertTrue(any(word in w for w in res["why"]), word)

    def test_no_lines_no_start(self):
        self.assertFalse(engine.start_check(self.proj(), [])["ok"])


class TestSchedule(unittest.TestCase):
    def test_plain_weekday(self):
        # due Tuesday 2026-12-01 → heads-up Sunday 29th 09:00, ask Tue 16:00,
        # Asil Tue 19:00, Faisal Wed 2nd 09:00
        s = {k: at for k, at, _w in engine.schedule_for("2026-12-01")}
        self.assertEqual(s["heads_up"], dt.datetime(2026, 11, 29, 9, 0))
        self.assertEqual(s["ask"], dt.datetime(2026, 12, 1, 16, 0))
        self.assertEqual(s["esc_lead"], dt.datetime(2026, 12, 1, 19, 0))
        self.assertEqual(s["esc_boss"], dt.datetime(2026, 12, 2, 9, 0))

    def test_never_on_friday(self):
        # due Friday 2026-11-27: heads-up would be Wed 25 (fine); ask moves to Saturday 28
        s = {k: at for k, at, _w in engine.schedule_for("2026-11-27")}
        self.assertEqual(s["ask"].date(), dt.date(2026, 11, 28))
        # due Sunday 2026-11-29: heads-up would be Friday 27 → Thursday 26
        s2 = {k: at for k, at, _w in engine.schedule_for("2026-11-29")}
        self.assertEqual(s2["heads_up"].date(), dt.date(2026, 11, 26))
        # due Thursday 2026-11-26: Faisal next morning would be Friday → Saturday
        s3 = {k: at for k, at, _w in engine.schedule_for("2026-11-26")}
        self.assertEqual(s3["esc_boss"].date(), dt.date(2026, 11, 28))
        for sch in (s, s2, s3):
            for at in sch.values():
                self.assertNotEqual(at.weekday(), 4)


class TestDue(unittest.TestCase):
    started = "2026-11-23T10:00:00"

    def due(self, items, now, sent=()):
        return [(r["item_id"], r["kind"]) for r in
                engine.due_reminders(items, now, set(sent), self.started)]

    def key(self, iid, due, kind):
        return engine.reminder_key(iid, due, kind)

    def test_heads_up_then_ask(self):
        its = [item(1, "2026-12-01")]
        self.assertEqual(self.due(its, dt.datetime(2026, 11, 29, 9, 5)), [("it1", "heads_up")])
        self.assertEqual(self.due(its, dt.datetime(2026, 12, 1, 16, 1),
                                  [self.key("it1", "2026-12-01", "heads_up")]), [("it1", "ask")])

    def test_sent_once(self):
        its = [item(1, "2026-12-01")]
        k = self.key("it1", "2026-12-01", "heads_up")
        self.assertEqual(self.due(its, dt.datetime(2026, 11, 29, 9, 30), [k]), [])

    def test_escalation_chain_needs_the_previous_step(self):
        its = [item(1, "2026-12-01")]
        at7 = dt.datetime(2026, 12, 1, 19, 5)
        # the ask was never sent (bot down all afternoon) → no escalation accuses anyone
        self.assertEqual(self.due(its, at7), [])
        ask = self.key("it1", "2026-12-01", "ask")
        self.assertEqual(self.due(its, at7, [ask]), [("it1", "esc_lead")])
        lead = self.key("it1", "2026-12-01", "esc_lead")
        self.assertEqual(self.due(its, dt.datetime(2026, 12, 2, 9, 1), [ask, lead]),
                         [("it1", "esc_boss")])

    def test_done_or_blocked_items_stay_quiet(self):
        ask = self.key("it1", "2026-12-01", "ask")
        at7 = dt.datetime(2026, 12, 1, 19, 5)
        self.assertEqual(self.due([item(1, "2026-12-01", "done")], at7, [ask]), [])
        self.assertEqual(self.due([item(1, "2026-12-01", "blocked")], at7, [ask]), [])

    def test_photos_pending_still_escalates(self):
        ask = self.key("it1", "2026-12-01", "ask")
        self.assertEqual(self.due([item(1, "2026-12-01", "awaiting_photos")],
                                  dt.datetime(2026, 12, 1, 19, 5), [ask]), [("it1", "esc_lead")])

    def test_nothing_from_before_the_start(self):
        # due 24th, project started 23rd 10:00 → heads-up (22nd) predates the start: skipped
        its = [item(1, "2026-11-24")]
        self.assertEqual(self.due(its, dt.datetime(2026, 11, 23, 10, 5)), [])

    def test_long_past_is_dropped_not_sent_late(self):
        its = [item(1, "2026-12-01")]
        # the ask window closes before 19:00 — a 22:00 restart does not post «خلص؟»
        self.assertEqual(self.due(its, dt.datetime(2026, 12, 1, 22, 0),
                                  [self.key("it1", "2026-12-01", "heads_up")]), [])

    def test_a_delay_makes_a_fresh_schedule(self):
        old = [self.key("it1", "2026-12-01", k) for k in ("heads_up", "ask", "esc_lead")]
        its = [item(1, "2026-12-03")]        # moved by «تأخر»
        self.assertEqual(self.due(its, dt.datetime(2026, 12, 3, 16, 2), old), [("it1", "ask")])

    def test_blocked_reaches_faisal_after_a_day(self):
        its = [item(1, "2026-12-01", "blocked", blocked_at="2026-12-01T11:00:00")]
        self.assertEqual(self.due(its, dt.datetime(2026, 12, 2, 10, 0)), [])
        self.assertEqual(self.due(its, dt.datetime(2026, 12, 2, 11, 5)), [("it1", "blocked_boss")])

    def test_handover_line_is_asked_like_any_other(self):
        its = [item(9, "2026-12-15", is_handover=1)]
        self.assertEqual(self.due(its, dt.datetime(2026, 12, 15, 16, 1),
                                  [self.key("it9", "2026-12-15", "heads_up")]), [("it9", "ask")])


class TestSummary(unittest.TestCase):
    def test_summary_once_a_day_not_friday(self):
        self.assertTrue(engine.summary_due(dt.datetime(2026, 11, 24, 8, 3), set(), True))
        self.assertFalse(engine.summary_due(dt.datetime(2026, 11, 24, 8, 3),
                                            {engine.summary_key(dt.date(2026, 11, 24))}, True))
        self.assertFalse(engine.summary_due(dt.datetime(2026, 11, 27, 8, 3), set(), True))
        self.assertFalse(engine.summary_due(dt.datetime(2026, 11, 24, 7, 59), set(), True))
        self.assertFalse(engine.summary_due(dt.datetime(2026, 11, 24, 8, 3), set(), False))

    def test_project_health(self):
        its = [item(1, "2026-11-24", "done"), item(2, "2026-11-25"), item(3, "2026-12-01")]
        h = engine.health(its, dt.date(2026, 11, 26))
        self.assertEqual((h["done"], h["total"]), (1, 3))
        self.assertEqual([i["id"] for i in h["late"]], ["it2"])
        self.assertEqual(h["next"]["id"], "it2")
        self.assertEqual(h["state"], "late")


class TestHandoverDefault(unittest.TestCase):
    def test_two_days_after_last_skipping_friday(self):
        self.assertEqual(engine.handover_due(["2026-12-13", "2026-12-10"]), "2026-12-15")
        self.assertEqual(engine.handover_due(["2026-11-25"]), "2026-11-28")   # 27th is Friday
        self.assertEqual(engine.handover_due([]), "")


if __name__ == "__main__":
    unittest.main()
