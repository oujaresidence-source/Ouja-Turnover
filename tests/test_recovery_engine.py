# -*- coding: utf-8 -*-
"""
TDD lock for recovery.engine — the pure rules of «استرداد التجربة».

These tests are the contract. The equity claim in §15.4 (month-end gap within ±2 under a
conflict-heavy month) is not something anyone can verify by watching the live server for
thirty days, so it is proved here instead. Run this before ANY edit to the assignment or
compaction code.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recovery import engine  # noqa: E402


def g(text, ts=""):
    return {"who": "guest", "text": text, "ts": ts}


def s(text, ts=""):
    return {"who": "staff", "text": text, "ts": ts}


class TestSignals(unittest.TestCase):

    def test_pleasantry_matches_whole_turn_only(self):
        self.assertTrue(engine.is_pleasantry("شكرا"))
        self.assertTrue(engine.is_pleasantry("  تمام  "))
        self.assertTrue(engine.is_pleasantry("ok"))
        self.assertTrue(engine.is_pleasantry("👍"))
        self.assertTrue(engine.is_pleasantry("thanks a lot"))

    def test_a_complaint_that_opens_politely_is_not_a_pleasantry(self):
        # The whole cost saving is worthless if it eats the complaint.
        self.assertFalse(engine.is_pleasantry("شكرا بس المكيف ما يشتغل"))
        self.assertFalse(engine.is_pleasantry("thanks, but the AC is not working"))

    def test_automated_detection_is_for_staff_turns_only(self):
        wifi = "كلمة المرور للواي فاي: OUJA2026"
        self.assertTrue(engine.looks_automated(wifi))
        # ...and the guest saying the wifi failed must survive, which is why _blocks()
        # applies looks_automated to staff turns only.
        blocks = engine._blocks([g("الواي فاي ما يشتغل"), s(wifi)])
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["who"], "guest")

    def test_complaint_hints_match_across_arabic_spelling(self):
        self.assertTrue(engine.has_complaint("المكيف ما يشتغل"))
        self.assertTrue(engine.has_complaint("THE AC IS NOT WORKING"))
        self.assertFalse(engine.has_complaint("كل شي ممتاز"))

    def test_the_real_complaints_bot_py_s_list_missed(self):
        """Regression lock. These are verbatim guest messages from the project's own eval
        set (golden_set.seed.jsonl) whose cases are labelled «شكوى» / «نزاع مالي» /
        «إلغاء حجز». bot.py's hint list matches none of them, which would drop the
        complaint line out of a long conversation before the model ever saw it."""
        for text in (
            "المكيف ما يبرد والجو حر، الوضع تعبنا والله",
            "ليش خصمتوا تأمين؟ أنا ما كسرت شي وهذا ظلم",
            "أبغى ألغي الحجز وأرجع فلوسي كاملة",
        ):
            self.assertTrue(engine.has_complaint(text), text)

    def test_ordinary_questions_are_not_treated_as_complaints(self):
        """The other half of the lock: widening the list must not turn every routine
        question into a complaint. Also verbatim from the eval set."""
        for text in (
            "كم باسوورد الواي فاي؟",
            "متى وقت تسجيل الخروج؟",
            "فيه موقف سيارة خاص للشقة؟",
            "تنصحني بمطاعم زينة قريبة؟",
            "شكراً، كانت إقامة ممتازة 🙏",
            "السلام عليكم",
            "ممكن مناشف إضافية لو سمحت؟",
        ):
            self.assertFalse(engine.has_complaint(text), text)

    def test_substring_matching_does_not_fire_inside_innocent_words(self):
        # «حر» inside «الحرم»/«بحر» and «صوت» inside «صوتك» are why those bare forms
        # are deliberately absent from COMPLAINT_HINTS.
        for text in ("كم تبعد الشقة عن الحرم؟", "الشقة قريبة من البحر؟", "صوتك واضح"):
            self.assertFalse(engine.has_complaint(text), text)


class TestCompaction(unittest.TestCase):

    def test_collapses_consecutive_same_sender(self):
        out = engine.compact([g("المكيف"), g("ما يشتغل"), s("نجيك الحين")])
        self.assertEqual(out.count("الضيف:"), 1)

    def test_keeps_first_guest_complaint_and_the_reply_that_followed(self):
        msgs = [g("مرحبا وصلنا"), s("حياكم الله")]
        for i in range(12):                       # alternating, so they stay separate blocks
            msgs += [g("رسالة %d" % i), s("رد %d" % i)]
        msgs += [g("المكيف ما يشتغل"), s("نرسل الفني")]
        for i in range(3):
            msgs += [g("تابع %d" % i), s("تمام %d" % i)]
        out = engine.compact(msgs)
        self.assertIn("مرحبا وصلنا", out)        # first guest block
        self.assertIn("المكيف ما يشتغل", out)     # the complaint
        self.assertIn("نرسل الفني", out)          # the staff reply right after it
        self.assertIn(engine.ELLIPSIS, out)       # and it visibly dropped the middle

    def test_drops_template_traffic(self):
        out = engine.compact([
            g("المكيف ما يشتغل"),
            s("رمز الدخول: 4417"),
            s("كلمة المرور للواي فاي: OUJA2026"),
            s("نرسل لك الفني الحين"),
        ])
        self.assertNotIn("4417", out)
        self.assertNotIn("OUJA2026", out)
        self.assertIn("نرسل لك الفني", out)

    def test_hard_cap_drops_from_the_middle_never_the_ends(self):
        first, last = "بداية القصة هنا", "آخر شي قاله الضيف"
        msgs = [g(first)]
        msgs += [g("حشو طويل جدا " * 40) for _ in range(60)]
        msgs += [s("رد"), g(last)]
        out = engine.compact(msgs, max_chars=6000)
        self.assertLessEqual(len(out), 6000)
        self.assertIn(first, out)
        self.assertIn(last, out)

    def test_empty_conversation_is_empty_not_an_error(self):
        self.assertEqual(engine.compact([]), "")
        self.assertEqual(engine.compact([s("كلمة المرور للواي فاي: X"), g("شكرا")]), "")


class TestCacheKey(unittest.TestCase):
    """§3.1 — the cost guarantee, stated as a hash property."""

    BASE = [g("المكيف ما يشتغل"), s("نرسل الفني")]

    def test_same_conversation_same_hash(self):
        a = engine.content_hash(engine.compact(self.BASE))
        b = engine.content_hash(engine.compact(list(self.BASE)))
        self.assertEqual(a, b)

    def test_a_template_message_does_not_buy_a_second_api_call(self):
        before = engine.content_hash(engine.compact(self.BASE))
        after = engine.content_hash(engine.compact(
            self.BASE + [s("كلمة المرور للواي فاي: OUJA2026"), g("تمام")]))
        self.assertEqual(before, after)

    def test_a_real_new_guest_message_does_invalidate_it(self):
        before = engine.content_hash(engine.compact(self.BASE))
        after = engine.content_hash(engine.compact(self.BASE + [g("لين الحين ما جا أحد")]))
        self.assertNotEqual(before, after)


class TestEligibility(unittest.TestCase):

    def cand(self, **kw):
        base = {"reservation_id": "R1", "score": 6.2, "in_house": True,
                "evidence_state": "known", "has_open_ticket": False}
        base.update(kw)
        return base

    def test_a_low_scoring_in_house_guest_is_eligible(self):
        self.assertEqual(engine.eligibility(self.cand()), (True, "eligible"))

    def test_every_rejection_names_its_reason(self):
        cases = [
            (self.cand(score=7.0), "score_ok"),
            (self.cand(score=9), "score_ok"),
            (self.cand(score=None), "no_score"),
            (self.cand(evidence_state="unknown"), "no_score"),
            (self.cand(has_open_ticket=True), "already_open"),
            (self.cand(in_house=False), "not_in_house"),
            (self.cand(reservation_id=""), "no_reservation"),
        ]
        for cand, reason in cases:
            ok, got = engine.eligibility(cand)
            self.assertFalse(ok, reason)
            self.assertEqual(got, reason)

    def test_threshold_is_strictly_below_seven(self):
        self.assertTrue(engine.eligibility(self.cand(score=6.99))[0])
        self.assertFalse(engine.eligibility(self.cand(score=7.0))[0])


class TestPriority(unittest.TestCase):

    def test_orders_by_in_house_then_score_then_repeat_then_value(self):
        rows = [
            {"reservation_id": "d", "in_house": False, "score": 2, "total_price": 9000},
            {"reservation_id": "c", "in_house": True, "score": 6, "total_price": 500},
            {"reservation_id": "b", "in_house": True, "score": 4, "total_price": 500},
            {"reservation_id": "a", "in_house": True, "score": 4, "total_price": 500,
             "repeat_guest": True},
        ]
        order = [r["reservation_id"] for r in sorted(rows, key=engine.priority_key)]
        self.assertEqual(order, ["a", "b", "c", "d"])

    def test_value_breaks_a_tie_highest_first(self):
        rows = [{"reservation_id": "lo", "in_house": True, "score": 5, "total_price": 100},
                {"reservation_id": "hi", "in_house": True, "score": 5, "total_price": 8000}]
        self.assertEqual([r["reservation_id"] for r in sorted(rows, key=engine.priority_key)],
                         ["hi", "lo"])


class TestSelectBatch(unittest.TestCase):

    def test_the_cap_defers_it_does_not_drop(self):
        cands = [{"reservation_id": "R%d" % i, "score": 3, "in_house": True,
                  "evidence_state": "known"} for i in range(20)]
        out = engine.select_batch(cands, cap=15)
        self.assertEqual(len(out["taken"]), 15)
        self.assertEqual(len(out["deferred"]), 5)      # returned, never silently truncated
        self.assertEqual(len(out["taken"]) + len(out["deferred"]), 20)

    def test_skipped_candidates_carry_their_reason(self):
        out = engine.select_batch([{"reservation_id": "R1", "score": 9, "in_house": True,
                                    "evidence_state": "known"}], cap=15)
        self.assertEqual(out["taken"], [])
        self.assertEqual(out["skipped"][0]["skip_reason"], "score_ok")


AGENTS = [{"id": "111", "name": "محمد اليامي"}, {"id": "222", "name": "عهود"}]


class TestAssignment(unittest.TestCase):

    def test_the_unit_owner_is_never_the_caller(self):
        r = engine.choose_agent(AGENTS, {}, unit_owner_name="محمد اليامي")
        self.assertEqual(r["agent_id"], "222")
        self.assertEqual(r["excluded_id"], "111")
        self.assertEqual(r["reason"], "conflict_reassigned")

    def test_owner_name_matching_survives_spelling_drift(self):
        # The calendar and the agent config are two different stores.
        r = engine.choose_agent(AGENTS, {}, unit_owner_name="  محمد اليامى ")
        self.assertEqual(r["excluded_id"], "111")

    def test_a_unit_owned_by_nobody_conflicts_with_nobody(self):
        r = engine.choose_agent(AGENTS, {}, unit_owner_name=None)
        self.assertIsNone(r["excluded_id"])
        self.assertEqual(r["reason"], "equity")

    def test_equity_picks_the_agent_with_fewer_tickets(self):
        stats = {"111": {"assigned_count": 5}, "222": {"assigned_count": 2}}
        self.assertEqual(engine.choose_agent(AGENTS, stats)["agent_id"], "222")

    def test_conflict_debt_breaks_a_tie_but_never_overrides_the_count(self):
        level = {"111": {"assigned_count": 4, "conflict_debt": 3},
                 "222": {"assigned_count": 4, "conflict_debt": 0}}
        self.assertEqual(engine.choose_agent(AGENTS, level)["agent_id"], "111")
        # ...and an agent already AHEAD does not jump the queue on debt alone, which is
        # the literal-spec behaviour that would widen the very gap debt exists to close.
        ahead = {"111": {"assigned_count": 9, "conflict_debt": 3},
                 "222": {"assigned_count": 4, "conflict_debt": 0}}
        self.assertEqual(engine.choose_agent(AGENTS, ahead)["agent_id"], "222")

    def test_an_absent_agent_is_not_assigned(self):
        r = engine.choose_agent(AGENTS, {}, absent_ids=["111"])
        self.assertEqual(r["agent_id"], "222")

    def test_all_conflicted_falls_through_to_the_supervisor(self):
        solo = [{"id": "111", "name": "محمد اليامي"}]
        r = engine.choose_agent(solo, {}, unit_owner_name="محمد اليامي")
        self.assertIsNone(r["agent_id"])
        self.assertEqual(r["fallback"], "supervisor")
        self.assertEqual(r["reason"], "all_conflicted")
        self.assertEqual(r["excluded_id"], "111")

    def test_everyone_absent_is_reported_as_absence_not_conflict(self):
        r = engine.choose_agent(AGENTS, {}, absent_ids=["111", "222"])
        self.assertEqual(r["fallback"], "supervisor")
        self.assertEqual(r["reason"], "all_absent")

    def test_receiving_a_ticket_clears_one_unit_of_debt(self):
        stats = engine.apply_exclusion({}, "111")
        self.assertEqual(stats["111"]["conflict_debt"], 1)
        stats = engine.apply_assignment(stats, "111", "2026-08-06T16:00:00+03:00")
        self.assertEqual(stats["111"]["conflict_debt"], 0)
        self.assertEqual(stats["111"]["assigned_count"], 1)

    def test_apply_assignment_does_not_mutate_the_caller_s_dict(self):
        # The caller writes the result to SQLite; a failed write must not leave the
        # in-memory counters ahead of the database.
        before = {"111": {"assigned_count": 1, "conflict_debt": 0, "last_assigned_at": None}}
        engine.apply_assignment(before, "111", "x")
        self.assertEqual(before["111"]["assigned_count"], 1)


class TestEquityRepairOverAMonth(unittest.TestCase):
    """§4.3's month-end target, and the honest limit of it.

    §4.3 asks for a month-end gap within ±2. That target is reachable only while conflicts
    are a MINORITY of the month's tickets. If one agent owns the apartments behind most of
    the complaints, the tickets on those units can only go to the other agent, and no
    selection rule can undo it — the arithmetic floor on the gap is
    (conflicted tickets) − (free tickets). These tests pin both facts: the engine hits the
    realistic target, AND it hits the floor exactly rather than pretending in the
    unreachable case. The gap alert in §4.3 is what covers the second case.
    """

    def _run_month(self, owners, agents=None):
        agents = agents or AGENTS
        stats = {}
        for owner in owners:
            pick = engine.choose_agent(agents, stats, unit_owner_name=owner)
            if pick["excluded_id"]:
                stats = engine.apply_exclusion(stats, pick["excluded_id"])
            if pick["agent_id"]:
                stats = engine.apply_assignment(stats, pick["agent_id"], "2026-08-01")
        return stats

    def test_a_realistic_conflict_rate_lands_within_two(self):
        # 30 tickets; AGENT_A owns roughly a fifth of the book, so ~6 conflict.
        owners = (["محمد اليامي"] * 6) + ([None] * 24)
        stats = self._run_month(owners)
        self.assertLessEqual(engine.equity_gap(stats, ["111", "222"]), 2)

    def test_conflicts_are_repaired_the_moment_free_tickets_arrive(self):
        # Worst ordering: every conflicted ticket first, then the free ones.
        stats = self._run_month((["محمد اليامي"] * 8) + ([None] * 22))
        self.assertLessEqual(engine.equity_gap(stats, ["111", "222"]), 2)

    def test_an_unrepairable_month_hits_the_arithmetic_floor_exactly(self):
        # 20 tickets on AGENT_A's units + 10 free. AGENT_B must take all 20, so the best
        # possible split is 20/10 — a gap of 10. The engine must reach that and no worse.
        stats = self._run_month((["محمد اليامي"] * 20) + ([None] * 10))
        self.assertEqual(stats["222"]["assigned_count"], 20)
        self.assertEqual(stats["111"]["assigned_count"], 10)
        self.assertEqual(engine.equity_gap(stats, ["111", "222"]), 10)

    def test_after_three_exclusions_the_excluded_agent_catches_back_up(self):
        stats = self._run_month(["محمد اليامي"] * 3 + [None] * 3)
        self.assertLessEqual(engine.equity_gap(stats, ["111", "222"]), 2)
        self.assertEqual(stats["111"]["conflict_debt"], 0)   # the debt cleared

    def test_an_unconflicted_month_is_split_evenly(self):
        stats = self._run_month([None] * 20)
        self.assertEqual(stats["111"]["assigned_count"], 10)
        self.assertEqual(stats["222"]["assigned_count"], 10)


class TestExtractionValidation(unittest.TestCase):

    GOOD = {
        "headline_ar": "المكيف ما اشتغل من أول يوم",
        "timeline": [{"when": "اليوم الأول", "what_ar": "الضيف بلّغ عن المكيف"}],
        "quotes": ["المكيف ما يشتغل"],
        "root_cause": "maintenance",
        "physical_issue": True,
        "already_promised_ar": "وعدوه بفني",
        "unresolved_ar": "الفني ما جا",
        "severity": 4,
        "call_opener_ar": "أعتذر منك عن موضوع المكيف",
    }

    def test_a_good_payload_passes(self):
        clean, err = engine.validate_extraction(self.GOOD)
        self.assertIsNone(err)
        self.assertEqual(clean["severity"], 4)
        self.assertTrue(clean["physical_issue"])

    def test_an_unknown_root_cause_becomes_other_rather_than_failing(self):
        clean, err = engine.validate_extraction(dict(self.GOOD, root_cause="حريقة"))
        self.assertIsNone(err)
        self.assertEqual(clean["root_cause"], "other")

    def test_a_bad_severity_is_a_failure_not_a_guess(self):
        for bad in (0, 6, "high", None):
            clean, err = engine.validate_extraction(dict(self.GOOD, severity=bad))
            self.assertIsNone(clean)
            self.assertTrue(err)

    def test_missing_headline_or_timeline_fails(self):
        self.assertIsNone(engine.validate_extraction(dict(self.GOOD, headline_ar=""))[0])
        self.assertIsNone(engine.validate_extraction(dict(self.GOOD, timeline=[]))[0])

    def test_quotes_are_capped_at_two(self):
        clean, _ = engine.validate_extraction(dict(self.GOOD, quotes=["a", "b", "c", "d"]))
        self.assertEqual(len(clean["quotes"]), 2)

    def test_the_string_null_is_treated_as_no_promise(self):
        clean, _ = engine.validate_extraction(dict(self.GOOD, already_promised_ar="null"))
        self.assertIsNone(clean["already_promised_ar"])

    def test_severity_colour_never_raises(self):
        self.assertEqual(engine.severity_color(5), 0xC0392B)
        self.assertEqual(engine.severity_color(None), 0x95A5A6)
        self.assertEqual(engine.severity_color("x"), 0x95A5A6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
