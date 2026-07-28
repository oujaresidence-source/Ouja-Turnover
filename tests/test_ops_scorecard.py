# -*- coding: utf-8 -*-
"""
Phase 3 «كرت التقييم» — the monthly 1-5 scorecard.

The rules being locked here are the ones that decide whether this is fair:

    * attribution: a message on unit X routes to the COVERER when the owner is off
    * rates are per apartment — two people with equal per-apartment performance and
      different loads score the SAME
    * coverage can raise a score and can never lower it
    * a line below the minimum sample is excluded and its weight redistributed to 100%
    * a missing-data line renders «بيانات ناقصة» and scores no zero
    * review sub-scores exclude location and value
    * the multiplier can never produce a value below 1.0
    * an override without a written reason is refused
    * dry-run releases nothing to employees

Run: python3 -m unittest tests.test_ops_scorecard
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                  # noqa: E402
from schedule import db as sdb, seed as sseed               # noqa: E402
from ops import db, scorecard                                # noqa: E402


def code_only(module):
    """Module source with every comment and string literal stripped.

    The structural guards below assert that certain things do not exist IN THE CODE. Scanning
    raw source would fail on the docstrings that explain why they must not exist, which would
    push the next person to delete the explanation instead of keeping the guarantee."""
    import inspect
    import io
    import tokenize
    src = inspect.getsource(module)
    out = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


def facts(**kw):
    base = {"apartment_days": 300, "working_days": 26, "coverage_days": 0,
            "response": {"answered": 0, "total": 0},
            "escalation": {"taken": 0, "total": 0},
            "turnover": {"closed_before_checkin": 0, "total": 0},
            "compliance": {"filed": 0, "expected": 0, "active_warnings": 0},
            "reviews": []}
    base.update(kw)
    return base


class TestFairnessRuleA_NormalizeByLoad(unittest.TestCase):
    """Absolute totals would make the hardest-working person score worst."""

    def test_two_loads_same_per_apartment_performance_score_the_same(self):
        heavy = scorecard.build("كثير", facts(
            apartment_days=372,                     # 12 apartments x 31 days
            turnover={"closed_before_checkin": 120, "total": 124}))
        light = scorecard.build("قليل", facts(
            apartment_days=248,                     # 8 apartments x 31 days
            turnover={"closed_before_checkin": 60, "total": 62}))
        self.assertEqual(heavy["score"], light["score"])
        self.assertEqual(_line(heavy, "turnover")["score"], _line(light, "turnover")["score"])

    def test_the_rate_helper_is_per_apartment_day(self):
        self.assertEqual(scorecard.per_apartment_rate(30, 300), 0.1)
        self.assertEqual(scorecard.per_apartment_rate(20, 200), 0.1)

    def test_no_load_is_no_opinion_not_a_zero(self):
        self.assertIsNone(scorecard.per_apartment_rate(5, 0))


class TestFairnessRuleB_CoverageOnlyAdds(unittest.TestCase):
    """If covering hurts, people stop covering and the roster collapses."""

    def test_coverage_raises_the_multiplier_and_never_lowers_it(self):
        f = facts(turnover={"closed_before_checkin": 100, "total": 100})
        none = scorecard.build("أ", dict(f, coverage_days=0, working_days=26))
        lots = scorecard.build("ب", dict(f, coverage_days=13, working_days=26))
        self.assertEqual(none["score"], lots["score"])           # the score itself is untouched
        self.assertGreater(lots["multiplier"], none["multiplier"])
        self.assertGreaterEqual(lots["coverage_bonus"], none["coverage_bonus"])

    def test_the_bonus_is_never_negative_however_strange_the_input(self):
        self.assertEqual(scorecard.coverage_bonus(-5, 26), 0.0)
        self.assertEqual(scorecard.coverage_bonus(0, 0), 0.0)
        self.assertGreaterEqual(scorecard.coverage_bonus(99, 26), 0.0)

    def test_the_bonus_is_capped_at_five_points(self):
        self.assertLessEqual(scorecard.coverage_bonus(999, 26), 5)


class TestFairnessRuleC_MissingDataIsNotALowScore(unittest.TestCase):

    def test_a_line_with_no_data_is_excluded_not_zeroed(self):
        card = scorecard.build("أ", facts(turnover={"closed_before_checkin": 50, "total": 50}))
        resp = _line(card, "response")
        self.assertIsNone(resp["score"])
        self.assertEqual(resp["label_ar"], "بيانات ناقصة")
        self.assertEqual(resp["effective_weight"], 0)
        self.assertIn("response", card["missing"])

    def test_the_surviving_weights_still_total_one_hundred(self):
        card = scorecard.build("أ", facts(turnover={"closed_before_checkin": 50, "total": 50}))
        self.assertAlmostEqual(card["total_weight"], 100.0, places=3)

    def test_a_line_below_the_minimum_sample_is_excluded(self):
        few = scorecard.build("أ", facts(turnover={"closed_before_checkin": 3, "total": 3}),
                              minimum=5)
        self.assertIsNone(_line(few, "turnover")["score"])
        enough = scorecard.build("أ", facts(turnover={"closed_before_checkin": 6, "total": 6}),
                                 minimum=5)
        self.assertIsNotNone(_line(enough, "turnover")["score"])

    def test_a_gap_in_our_instrumentation_cannot_drag_a_score_down(self):
        """Only the turnover line has data, and it is perfect. The score must be 5, not
        5 * 20/100."""
        card = scorecard.build("أ", facts(turnover={"closed_before_checkin": 50, "total": 50}))
        self.assertEqual(card["score"], 5.0)

    def test_a_person_we_know_nothing_about_gets_no_number(self):
        card = scorecard.build("أ", facts())
        self.assertIsNone(card["score"])
        self.assertEqual(card["multiplier"], 1.0)
        self.assertEqual(len(card["missing"]), 5)


class TestFixedStandardsNotRanking(unittest.TestCase):

    def test_everyone_can_score_five_in_the_same_month(self):
        perfect = facts(turnover={"closed_before_checkin": 100, "total": 100},
                        compliance={"filed": 4, "expected": 4, "active_warnings": 0})
        cards = [scorecard.build(n, perfect) for n in ("أ", "ب", "ج", "د", "هـ", "و")]
        self.assertTrue(all(c["score"] == 5.0 for c in cards))

    def test_thresholds_are_absolute(self):
        self.assertEqual(scorecard.score_from_thresholds(0.99, (0.95, 0.90, 0.80, 0.65)), 5)
        self.assertEqual(scorecard.score_from_thresholds(0.95, (0.95, 0.90, 0.80, 0.65)), 5)
        self.assertEqual(scorecard.score_from_thresholds(0.94, (0.95, 0.90, 0.80, 0.65)), 4)
        self.assertEqual(scorecard.score_from_thresholds(0.10, (0.95, 0.90, 0.80, 0.65)), 1)
        self.assertIsNone(scorecard.score_from_thresholds(None, (0.9,)))

    def test_there_is_no_forced_distribution_anywhere(self):
        """In a team of six, ranking guarantees somebody is last every month regardless of
        how well they did — which destroys the mutual coverage the roster depends on."""
        src = code_only(scorecard).lower().replace("private_ranking", "")
        for banned in ("percentile", "rank_score", "curve", "forced", "relative_to_peers"):
            self.assertNotIn(banned, src)


class TestReviewSubScores(unittest.TestCase):

    def test_location_and_value_are_excluded(self):
        revs = [{"cleanliness": 10, "communication": 10, "location": 2, "value": 2}]
        self.assertEqual(scorecard.review_average(revs), 10.0)

    def test_respect_house_rules_is_excluded_too(self):
        """That one is us rating the GUEST, not the guest rating our work."""
        self.assertEqual(scorecard.review_average([{"cleanliness": 8, "respect_house_rules": 2}]),
                         8.0)

    def test_check_in_and_accuracy_are_included(self):
        revs = [{"checkin": 8, "accuracy": 10}]
        self.assertEqual(scorecard.review_average(revs), 9.0)

    def test_no_usable_categories_means_missing_not_zero(self):
        self.assertIsNone(scorecard.review_average([{"location": 10, "value": 10}]))
        self.assertIsNone(scorecard.review_average([]))


class TestMoney(unittest.TestCase):
    """The scorecard can only ADD. Phase 1 is the only place money is ever taken away."""

    def test_the_multiplier_is_never_below_one(self):
        for s in (None, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
            self.assertGreaterEqual(scorecard.bonus_multiplier(s), 1.0, s)

    def test_a_terrible_month_still_costs_nothing(self):
        card = scorecard.build("أ", facts(turnover={"closed_before_checkin": 0, "total": 50}))
        self.assertEqual(card["score"], 1.0)
        self.assertEqual(card["multiplier"], 1.0)

    def test_a_great_month_adds(self):
        card = scorecard.build("أ", facts(turnover={"closed_before_checkin": 50, "total": 50}))
        self.assertGreater(card["multiplier"], 1.0)

    def test_the_bonus_adds_on_top_of_the_score(self):
        self.assertGreater(scorecard.bonus_multiplier(5.0, 5.0),
                           scorecard.bonus_multiplier(5.0, 0.0))


class TestWorkingHours(unittest.TestCase):

    def test_the_window_is_eleven_to_one_thirty_next_day(self):
        def t(h, m=0):
            return datetime.datetime(2026, 8, 3, h, m)
        self.assertTrue(scorecard.in_working_hours(t(11, 0)))
        self.assertTrue(scorecard.in_working_hours(t(23, 59)))
        self.assertTrue(scorecard.in_working_hours(t(0, 30)))
        self.assertTrue(scorecard.in_working_hours(t(1, 30)))
        self.assertFalse(scorecard.in_working_hours(t(1, 31)))
        self.assertFalse(scorecard.in_working_hours(t(9, 0)))


class ScorecardDbCase(unittest.TestCase):
    ENV = {"SCORECARD_ENABLED": "1", "SCORECARD_DRYRUN": "1", "SCORECARD_MIN_SAMPLE": "5"}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="opscard_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        sdb.reset_init_cache()
        db.reset_init_cache()
        sseed.seed_if_empty()
        self._saved = {k: os.environ.get(k) for k in self.ENV}
        os.environ.update(self.ENV)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def seed_card(self, month="2026-07", employee="ناصر"):
        card = scorecard.build(employee, facts(
            turnover={"closed_before_checkin": 40, "total": 50},
            compliance={"filed": 4, "expected": 4, "active_warnings": 0}))
        scorecard.save(month, [card], by="tester")
        return card


class TestAttribution(ScorecardDbCase):
    """§3.1 — by OWNERSHIP, because Hostaway has no sender field at all."""

    def test_a_units_work_routes_to_the_coverer_when_the_owner_is_off(self):
        emps = {e["name"]: e for e in sdb.employees()}
        nasser = emps["ناصر"]                       # off_day 2 = الثلاثاء
        apt = [a for a in sdb.apartments() if a["owner_id"] == nasser["id"]][0]
        sdb.execute("UPDATE schedule_apartments SET listing_id=? WHERE id=?", (99001, apt["id"]))

        # 2026-07-28 is a Tuesday (ناصر's day off) -> somebody else must own his unit
        off_day = scorecard.attribution(datetime.date(2026, 7, 28))
        self.assertIn(99001, off_day)
        self.assertNotEqual(off_day[99001]["name"], "ناصر")
        self.assertEqual(off_day[99001]["kind"], "coverage")

        # 2026-07-29 is a Wednesday -> it is his own again
        on_day = scorecard.attribution(datetime.date(2026, 7, 29))
        self.assertEqual(on_day[99001]["name"], "ناصر")
        self.assertEqual(on_day[99001]["kind"], "own")

    def test_the_module_never_tries_to_identify_a_sender(self):
        """A live API dump proved every outgoing Hostaway message has sentUsingHostaway=0 and
        userId=null, because the team replies inside Airbnb. There is no field to read, so any
        future attempt to read one is a bug — this fails if somebody tries."""
        src = code_only(scorecard)
        for f in ("userId", "sentUsingHostaway", "sentBy", "sent_by", "agentName", "userName"):
            self.assertNotIn(f, src)


class TestOwnerApproval(ScorecardDbCase):

    def test_an_override_without_a_written_reason_is_refused(self):
        self.seed_card()
        for bad in ("", "   ", None):
            r = scorecard.override("2026-07", "ناصر", "turnover", 5, bad, "فيصل")
            self.assertFalse(r["ok"])
            self.assertIn("سبب", r["error"])

    def test_an_override_with_a_reason_is_recorded_with_who_and_why(self):
        self.seed_card()
        r = scorecard.override("2026-07", "ناصر", "turnover", 5,
                               "الصور ضاعت بسبب عطل عندنا مو عنده", "فيصل")
        self.assertTrue(r["ok"], r)
        line = _line(r["card"], "turnover")
        self.assertEqual(line["score"], 5)
        self.assertEqual(line["overridden"]["by"], "فيصل")
        self.assertIn("عطل", line["overridden"]["reason"])

    def test_an_override_rescores_the_headline(self):
        card = self.seed_card()
        before = card["score"]
        r = scorecard.override("2026-07", "ناصر", "turnover", 5, "سبب مكتوب", "فيصل")
        self.assertGreater(r["card"]["score"], before)

    def test_a_score_outside_one_to_five_is_refused(self):
        self.seed_card()
        for bad in (0, 6, -1, "x"):
            self.assertFalse(scorecard.override("2026-07", "ناصر", "turnover", bad,
                                                "سبب", "فيصل")["ok"])

    def test_nothing_can_be_edited_after_the_employee_has_seen_it(self):
        self.seed_card()
        db.release_scorecard("2026-07", "ناصر", "فيصل")
        r = scorecard.override("2026-07", "ناصر", "turnover", 5, "سبب", "فيصل")
        self.assertFalse(r["ok"])
        self.assertIn("انرسل", r["error"])

    def test_recomputing_never_overwrites_a_released_card(self):
        self.seed_card()
        db.release_scorecard("2026-07", "ناصر", "فيصل")
        released = db.scorecard("2026-07", "ناصر")["card_json"]
        scorecard.save("2026-07", [scorecard.build("ناصر", facts(
            turnover={"closed_before_checkin": 0, "total": 50}))], by="tester")
        self.assertEqual(db.scorecard("2026-07", "ناصر")["card_json"], released)


class TestDryRun(ScorecardDbCase):

    def test_dry_run_releases_nothing_to_employees(self):
        self.seed_card()
        r = scorecard.release("2026-07", "فيصل")
        self.assertFalse(r["ok"])
        self.assertTrue(r["dryrun"])
        self.assertEqual(r["released"], [])
        self.assertIsNone(db.scorecard("2026-07", "ناصر")["released_at"])

    def test_with_dry_run_off_the_owner_can_release(self):
        self.seed_card()
        os.environ["SCORECARD_DRYRUN"] = "0"
        r = scorecard.release("2026-07", "فيصل")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["released"], ["ناصر"])
        self.assertIsNotNone(db.scorecard("2026-07", "ناصر")["released_at"])

    def test_computing_a_month_stores_a_card_per_employee(self):
        rep = scorecard.gather("2026-07")
        self.assertEqual(len(rep["cards"]), 5)
        scorecard.save("2026-07", rep["cards"], by="tester")
        self.assertEqual(len(db.scorecards("2026-07")), 5)

    def test_the_ranking_exists_but_is_marked_private(self):
        rep = scorecard.gather("2026-07")
        self.assertIn("private_ranking", rep)
        self.assertEqual(len(rep["private_ranking"]), 5)


def _line(card, key):
    return next(l for l in card["lines"] if l["key"] == key)


if __name__ == "__main__":
    unittest.main()
