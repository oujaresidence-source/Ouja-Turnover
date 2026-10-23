# -*- coding: utf-8 -*-
"""
«طلبات سام» → ops warnings → commission, on a REAL ops.db inside a temporary brain.db.

Locked: rrdesk/flow.py::_warn is the package's only ops.db.issue_warning call; 1st miss in an
ISO week = a private notice, 2nd = ONE warning (kind 'rr', period 'RR-YYYY-Www'), 3rd = KPI
only, a new week starts again; one warning → multiplier 0.9; dry-run writes ops_dryrun_log and
nothing else; the period key can never collide with 'wr' (bare week) or 'OC-' (night); a voided
warning restores 1.0; an excused miss does not count; leave / admin / unowned never count.

Run: python3 -m unittest tests.test_rrdesk_warn
"""

import datetime
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "fixtures", "rrdesk"))

import fakes as F                                   # noqa: E402
from ops import db as odb                           # noqa: E402
from rrdesk import db, engine, flow                 # noqa: E402


_ASKS = ["photos", "invoice", "video", "receipt", "quote", "guest_chat"]


def make_request(tc, mid, at, mentions=(F.NASSER,)):
    """Each request asks for something different — the same ask again would (rightly) be a
    re-ask of the open one, not a new request."""
    tc.clock.t = at
    db.set_setting("detect_mode", "auto")
    n = len(db.recent_requests())
    ask = _ASKS[n % len(_ASKS)]
    F.fake_model(tc, classify=dict(F.REQ_CLASSIFY, asks=[ask]))
    rid = flow.on_message(F.msg(mid, "send the %s please" % ask, mentions=mentions, at_=at))["request"]
    F.deliver_all()
    return rid


def miss_it(tc, rid, at):
    """Nobody's first notice is a miss: at `at` the overdue owner gets the reminder, and the
    miss is recorded 40 minutes later (MISS_GRACE_MIN = 30 working minutes)."""
    for t in (at, at + datetime.timedelta(minutes=40)):
        tc.clock.t = t
        flow.tick()
        F.deliver_all()
    return db.miss(rid)


def judge(tc, at):
    """The judge waits out the 48-hour excuse window, then rules."""
    tc.clock.t = at
    flow.tick()
    F.deliver_all()


AFTER_W43 = F.at(2026, 10, 24, 12, 0)                 # Saturday, still ISO week 43, > 48 h later


class Grep(unittest.TestCase):
    def test_only_one_issue_warning_call_in_the_package(self):
        hits = []
        for fn in sorted(os.listdir(os.path.join(ROOT, "rrdesk"))):
            if fn.endswith(".py"):
                with open(os.path.join(ROOT, "rrdesk", fn), encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if re.search(r"issue_warning[(]", line):
                            hits.append((fn, i))
        self.assertEqual(len(hits), 1, hits)
        self.assertEqual(hits[0][0], "flow.py")
        with open(os.path.join(ROOT, "rrdesk", "flow.py"), encoding="utf-8") as f:
            src = f.read()
        i = src.index("def _warn(")
        j = src.index("odb.issue_warning(", i)
        self.assertLess(j - i, 2500)                       # it lives INSIDE _warn
        # defined once, called once (the judge); «_warn()» in prose does not count
        self.assertEqual(len(re.findall(r"_warn[(][^)]", src)), 2)


class Judge(unittest.TestCase):
    def setUp(self):
        F.setup(self, now=F.at(2026, 10, 19, 12, 0))      # Monday, ISO week 43

    def two_misses(self, live):
        if live:
            flow.set_switch("warn_live", True, "test")
        r1 = make_request(self, "a1", F.at(2026, 10, 19, 12, 0))
        miss_it(self, r1, F.at(2026, 10, 19, 16, 0))
        r2 = make_request(self, "a2", F.at(2026, 10, 20, 12, 0))
        miss_it(self, r2, F.at(2026, 10, 20, 16, 0))
        return r1, r2

    def test_a_reminder_comes_before_any_miss(self):
        r1 = make_request(self, "a1", F.at(2026, 10, 19, 12, 0))
        self.clock.t = F.at(2026, 10, 19, 16, 0)            # overdue at the first look
        flow.tick()
        self.assertIsNone(db.miss(r1))
        self.assertIn("R2", db.ladder_sent(r1))
        self.assertIsNotNone(miss_it(self, r1, F.at(2026, 10, 19, 16, 1)))

    def test_judging_waits_for_the_excuse_window(self):
        self.two_misses(live=True)
        self.assertEqual(odb.all_warnings(), [])           # nothing before 48 h
        judge(self, AFTER_W43)
        self.assertEqual(len(odb.all_warnings()), 1)

    def test_first_miss_is_a_notice_only(self):
        r1 = make_request(self, "a1", F.at(2026, 10, 19, 12, 0))
        miss_it(self, r1, F.at(2026, 10, 19, 16, 0))
        judge(self, AFTER_W43)
        self.assertEqual(db.miss(r1)["verdict"], "notice")
        self.assertTrue(F.queued("dm", "notice:"))
        self.assertEqual(odb.all_warnings(), [])

    def test_second_miss_is_one_live_warning_and_commission_drops(self):
        self.two_misses(live=True)
        judge(self, AFTER_W43)
        ws = odb.all_warnings()
        self.assertEqual(len(ws), 1)
        self.assertEqual(ws[0]["id"], "wn_ناصر_RR-2026-W43")
        ob = odb.obligation(ws[0]["obligation_id"])
        self.assertEqual((ob["kind"], ob["period_key"], ob["status"]), ("rr", "RR-2026-W43", "missed"))
        self.assertEqual(odb.commission("ناصر", "2026-10")["multiplier"], 0.9)
        self.assertTrue(F.queued("dm", "warn:"))
        self.assertTrue(F.queued("room", "warnhr:"))
        self.assertIn("RR #47", ws[0]["reason_ar"])
        self.assertNotIn("ر.س", ws[0]["reason_ar"])          # no money figures

    def test_third_miss_is_kpi_only(self):
        self.two_misses(live=True)
        r3 = make_request(self, "a3", F.at(2026, 10, 21, 12, 0))
        miss_it(self, r3, F.at(2026, 10, 21, 16, 0))
        judge(self, AFTER_W43)
        self.assertEqual(db.miss(r3)["verdict"], "kpi")
        self.assertEqual(len(odb.all_warnings()), 1)

    def test_new_week_resets(self):
        self.two_misses(live=True)
        judge(self, AFTER_W43)
        r = make_request(self, "b1", F.at(2026, 10, 26, 12, 0))     # Monday, week 44
        miss_it(self, r, F.at(2026, 10, 26, 16, 0))
        judge(self, F.at(2026, 10, 28, 18, 0))
        self.assertEqual(db.miss(r)["verdict"], "notice")

    def test_dry_run_writes_only_the_dry_log(self):
        self.two_misses(live=False)
        judge(self, AFTER_W43)
        self.assertEqual(odb.all_warnings(), [])
        self.assertIsNone(odb.commission("ناصر", "2026-10"))
        dry = odb.dry_rows(kind="rr_warning")
        self.assertEqual(len(dry), 1)
        self.assertEqual(dry[0]["period_key"], "RR-2026-W43")
        self.assertIn("٩٠٪", dry[0]["detail"])
        self.assertIn('"multiplier": 0.9', dry[0]["payload"])
        self.assertEqual(F.queued("dm", "warn:"), [])

    def test_voided_warning_restores_commission(self):
        self.two_misses(live=True)
        judge(self, AFTER_W43)
        w = odb.all_warnings()[0]
        odb.void_warning(w["id"], "ريم", "appeal accepted")
        self.assertEqual(odb.recompute_commission("ناصر", "2026-10")["multiplier"], 1.0)

    def test_excuse_inside_the_window_prevents_the_warning(self):
        flow.set_switch("warn_live", True, "test")
        r1, r2 = self.two_misses(live=True)
        line = db.miss(r1)["line_message_id"]
        self.assertTrue(line)
        ok, _ = flow.press("excuse", line, {"did": F.NASSER, "name": "Nasser"}, {"reason": "كنت عند الضيف"})
        self.assertFalse(ok)                                   # not the lead
        ok, _ = flow.press("excuse", line, {"did": F.ASEEL, "name": "Aseel"}, {"reason": "قصير"})
        self.assertFalse(ok)                                   # reason < 10 characters
        ok, _ = flow.press("excuse", line, {"did": F.ASEEL, "name": "Aseel"},
                           {"reason": "كان عنده دخول ضيف مستعجل"})
        self.assertTrue(ok)
        judge(self, AFTER_W43)
        self.assertEqual(db.miss(r2)["verdict"], "notice")      # the excused one no longer counts
        self.assertEqual(odb.all_warnings(), [])

    def test_excuse_window_is_48_hours(self):
        r1 = make_request(self, "a1", F.at(2026, 10, 19, 12, 0))
        miss_it(self, r1, F.at(2026, 10, 19, 16, 0))
        self.clock.t = F.at(2026, 10, 21, 17, 0)
        ok, text = flow.press("excuse", db.miss(r1)["line_message_id"], {"did": F.ASEEL, "name": "A"},
                              {"reason": "reason long enough here"})
        self.assertFalse(ok)

    def test_leave_admin_outsiders_unowned_never_count(self):
        flow.set_switch("warn_live", True, "test")
        # on leave and nobody to cover: the lead holds it as UNOWNED with a fresh clock — no one pays
        self.state["resp"] = ("ناصر", F.NASSER, "owner")
        r1 = make_request(self, "a1", F.at(2026, 10, 19, 12, 0))
        self.state["leave"].add("ناصر")
        miss_it(self, r1, F.at(2026, 10, 19, 16, 0))
        r = db.request(r1)
        self.assertEqual((r["owner_did"], r["unowned"], r["gen"]), (F.ASEEL, 1, 2))
        self.assertFalse([m for m in db.misses_for(r1) if m["eligible"]])
        self.state["leave"].clear()
        # an admin (known up front through HOST.admin_ids) is reminded, never eligible
        from rrdesk.host import HOST
        HOST.admin_ids = lambda: [F.NASSER]
        self.addCleanup(lambda: setattr(HOST, "admin_ids", None))
        r2 = make_request(self, "a2", F.at(2026, 10, 20, 12, 0))
        self.assertEqual(miss_it(self, r2, F.at(2026, 10, 20, 16, 0))["eligible"], 0)
        judge(self, AFTER_W43)
        self.assertEqual(odb.all_warnings(), [])

    def test_asking_someone_outside_the_calendar_makes_it_unowned(self):
        """Sam asked Faisal: nobody on the team was asked, so nobody on the team can be late —
        not even the ticket opener (reviewer re-check, new finding 1)."""
        r = make_request(self, "o1", F.at(2026, 10, 19, 12, 0), mentions=(F.FAISAL,))
        req = db.request(r)
        self.assertEqual((req["owner_did"], req["owner_rule"], req["unowned"]), (F.ASEEL, 5, 1))
        miss_it(self, r, F.at(2026, 10, 19, 16, 0))
        self.assertFalse([m for m in db.misses_for(r) if m["eligible"]])
        ev = [e for e in db.events(request_id=r) if e["kind"] == "owner_chosen"][0]
        self.assertEqual(ev["detail"]["skipped_mentions"], [F.FAISAL])

    def test_reassigned_miss_stops_counting(self):
        r1 = make_request(self, "a1", F.at(2026, 10, 19, 12, 0))
        miss_it(self, r1, F.at(2026, 10, 19, 16, 0))
        card = db.request(r1)["card_message_id"]
        self.clock.t = F.at(2026, 10, 19, 17, 0)
        ok, _ = flow.press("reassign", card, {"did": F.ASEEL, "name": "Aseel"},
                           {"to_did": F.NOURA, "reason": "Nasser was at a check-in"})
        self.assertTrue(ok)
        self.assertTrue(db.miss(r1, 1)["excused_at"])


class PeriodKeys(unittest.TestCase):
    def test_no_collision_with_other_kinds(self):
        F.setup(self)
        k = engine.period_key(F.at(2026, 10, 20, 12).date())
        self.assertEqual(k, "RR-2026-W43")
        self.assertNotEqual(k, "2026-W43")                       # weekly report ('wr')
        self.assertFalse(k.startswith("OC-"))                    # on-call nights
        a = odb.ensure_obligation("wr", "ناصر", F.NASSER, "2026-W43", "2026-10-26T23:59:00+03:00")
        b = odb.ensure_obligation("rr", "ناصر", F.NASSER, k, "2026-10-26T23:59:00+03:00")
        wa = odb.issue_warning(a, "wr")
        wb = odb.issue_warning(b, "rr")
        self.assertNotEqual(wa["id"], wb["id"])
        self.assertEqual(odb.recompute_commission("ناصر", "2026-10")["multiplier"], 0.75)


if __name__ == "__main__":
    unittest.main()
