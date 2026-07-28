# -*- coding: utf-8 -*-
"""
«نظام الالتزام» end-to-end lifecycle, on a real (temporary) brain.db with the real Employee
Calendar seed. No Discord, no network — HOST.notify is a list.

The rules being locked here are the ones that cost somebody money if they break:

    * one obligation can never produce two warnings, even if the loop runs twice
    * approved leave waives SILENTLY — zero messages
    * a leader excuse before the deadline blocks the warning
    * the quarterly free pass is spent once, on a FIRST miss, and never by leave
    * an unreachable person is never warned (عهود has no Discord id in assignments.json)
    * 4 clean weeks retire exactly the OLDEST active warning
    * an appeal auto-escalates at 24h; accepting it voids and recomputes commission at once
    * a rejection with no written reason is refused
    * DRY-RUN issues nothing, sends nothing, writes no warning rows
    * the monthly public summary contains no employee name

Run: python3 -m unittest tests.test_ops_flow
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                     # noqa: E402
from schedule import db as sdb, seed as sseed   # noqa: E402
from ops import db, engine, notify, routes      # noqa: E402
from ops.host import HOST                       # noqa: E402

RIYADH = engine.tz()
W = "2026-W31"                     # Monday 2026-07-27, due 23:59
DUE = datetime.datetime(2026, 7, 27, 23, 59, tzinfo=RIYADH)
NASSER, MAATHER, NOURA, YAMI, OHOUD = "ناصر", "مآثر", "نورة", "محمد اليامي", "عهود"

# assignments.json as it really is today: four ids, one of them spelled differently from the
# calendar (ماذر / مآثر), and عهود missing entirely.
REAL_IDS = {"ناصر": "1134973768159203418", "ماذر": "1461084999213252754",
            "نورة": "1449067268637200587", "محمد اليامي": "894222545274945548"}


def at(y, m, d, hh=0, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=RIYADH)


class OpsCase(unittest.TestCase):
    """Fresh brain.db per test class, seeded with the real 5-employee calendar."""

    ENV = {"OPS_ACCOUNTABILITY_ENABLED": "1", "OPS_WARN_DRYRUN": "0",
           "OPS_FREE_PASS_PER_QUARTER": "0", "OPS_APPEAL_SLA_HOURS": "24",
           "OPS_DISCORD_IDS": "", "OPS_NAME_ALIASES": ""}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="opstest_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        sdb.reset_init_cache()
        db.reset_init_cache()
        sseed.seed_if_empty()

        self.sent = []
        self.reports = []
        HOST.notify = self.sent.append
        HOST.weekly_reports = lambda: list(self.reports)
        HOST.discord_ids = lambda: dict(REAL_IDS)
        HOST.public_base = lambda: "https://ouja.test"
        HOST.actor = lambda req: "tester"

        self._saved = {k: os.environ.get(k) for k in self.ENV}
        os.environ.update(self.ENV)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # -- helpers -------------------------------------------------------------
    def open_week(self, when=None):
        """What actually happens in production: the Sunday-evening nudge is what OPENS the
        week's obligations. Nothing is ever created retroactively — see
        TestTheDeadline.test_a_week_the_system_never_opened_can_never_be_a_warning."""
        return notify.tick(now=when or at(2026, 7, 26, 18, 5))

    def file_report(self, employee, date="2026-07-26"):
        self.reports.append({"employee": employee, "date": date})

    def texts(self):
        return [p.get("text", "") for p in self.sent]

    def sent_to(self, employee):
        return [p for p in self.sent if p.get("employee") == employee]


class TestRosterAndReachability(OpsCase):

    def test_employees_come_from_the_calendar_not_a_second_list(self):
        names = [e["name"] for e in notify.employees()]
        self.assertEqual(names, [NASSER, MAATHER, NOURA, YAMI, OHOUD])

    def test_the_maather_spelling_typo_is_resolved(self):
        """assignments.json says «ماذر», the calendar says «مآثر». Different letters, so it
        is fixed by a stated alias, not a silent fuzzy match."""
        emp = {e["name"]: e for e in notify.employees()}
        self.assertTrue(emp[MAATHER]["reachable"])
        self.assertEqual(emp[MAATHER]["did"], REAL_IDS["ماذر"])

    def test_ohoud_has_no_discord_id_and_is_flagged_not_hidden(self):
        emp = {e["name"]: e for e in notify.employees()}
        self.assertFalse(emp[OHOUD]["reachable"])
        self.assertEqual(emp[OHOUD]["did"], "")
        self.assertIn(OHOUD, notify.tick(now=at(2026, 7, 26, 18, 5))["unreachable"])

    def test_the_env_override_can_fill_a_missing_id_without_a_deploy(self):
        os.environ["OPS_DISCORD_IDS"] = '{"عهود": "999000111"}'
        emp = {e["name"]: e for e in notify.employees()}
        self.assertTrue(emp[OHOUD]["reachable"])
        self.assertEqual(emp[OHOUD]["did"], "999000111")


class TestTheLadder(OpsCase):

    def test_one_nudge_per_level_and_never_twice(self):
        notify.tick(now=at(2026, 7, 26, 18, 5))                 # L1
        self.assertEqual([n["level"] for n in
                          notify.tick(now=at(2026, 7, 26, 18, 10))["nudged"]], [])
        r = notify.tick(now=at(2026, 7, 27, 10, 5))             # L2
        self.assertEqual(sorted({n["level"] for n in r["nudged"]}), ["L2"])

    def test_a_sleeping_bot_sends_only_the_latest_level(self):
        """Down all Sunday and Monday morning: wake at 16:05 and send L3 ONLY. Three DMs at
        once is how people learn to mute the bot."""
        r = notify.tick(now=at(2026, 7, 27, 16, 5))
        self.assertEqual(sorted({n["level"] for n in r["nudged"]}), ["L3"])
        for p in self.sent:
            self.assertNotIn("مساك الله", p.get("text", ""))     # no L1 backlog

    def test_l4_carries_the_leader_excuse_prompt(self):
        os.environ["OPS_LEAD_ID"] = "555"
        try:
            notify.tick(now=at(2026, 7, 27, 20, 5))
            l4 = [p for p in self.sent if p.get("level") == "L4"]
            self.assertTrue(l4)
            self.assertTrue(all(p["lead_id"] == "555" for p in l4))
            self.assertIn("عذر مسبق", l4[0]["lead_text"])
        finally:
            os.environ.pop("OPS_LEAD_ID", None)

    def test_filing_the_report_stops_the_ladder(self):
        self.file_report(NASSER)
        r = notify.tick(now=at(2026, 7, 27, 10, 5))
        self.assertIn(NASSER, r["done"])
        self.assertEqual([n for n in r["nudged"] if n["employee"] == NASSER], [])
        self.assertEqual(db.obligation(db.obligation_id("wr", NASSER, W))["status"], "done")

    def test_a_report_dated_inside_the_window_counts(self):
        for d in ("2026-07-21", "2026-07-26", "2026-07-27"):
            self.reports = [{"employee": NOURA, "date": d}]
            self.assertTrue(notify.report_done(NOURA, W), d)
        self.reports = [{"employee": NOURA, "date": "2026-07-05"}]
        self.assertFalse(notify.report_done(NOURA, W))


class TestUnreachableIsAHoleNotANudge(OpsCase):

    def test_a_person_with_no_discord_id_gets_one_alert_not_four_dead_nudges(self):
        for now in (at(2026, 7, 26, 18, 5), at(2026, 7, 27, 10, 5),
                    at(2026, 7, 27, 16, 5), at(2026, 7, 27, 20, 5)):
            notify.tick(now=now)
        to_ohoud = [n for n in notify.tick(now=at(2026, 7, 27, 20, 10))["nudged"]
                    if n["employee"] == OHOUD]
        self.assertEqual(to_ohoud, [])
        alerts = [p for p in self.sent
                  if p.get("kind") == "alert" and p.get("employee") == OHOUD]
        self.assertEqual(len(alerts), 1)
        self.assertIn("Discord ID", alerts[0]["lead_text"])

    def test_the_dead_route_is_what_blocks_the_warning(self):
        self.open_week()
        oid = db.obligation_id("wr", OHOUD, W)
        self.assertFalse(db.is_reachable(oid, "", dry=False))
        r = notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertEqual([x["verdict"] for x in r["verdicts"] if x["employee"] == OHOUD],
                         ["unreachable"])


class TestTheComplianceScreen(OpsCase):
    """routes.state() is what /compliance renders — the owner's only window on all this."""

    def test_it_shows_every_employee_with_status_warnings_and_commission(self):
        self.open_week()
        self.file_report(NASSER)
        notify.tick(now=at(2026, 7, 27, 10, 5))
        notify.tick(now=at(2026, 7, 28, 0, 5))
        st = routes.state(W)
        self.assertTrue(st["ok"])
        rows = {r["employee"]: r for r in st["rows"]}
        self.assertEqual(sorted(rows), sorted([NASSER, MAATHER, NOURA, YAMI, OHOUD]))
        self.assertEqual(rows[NASSER]["status"], "done")
        self.assertEqual(rows[NASSER]["multiplier"], 1.0)
        self.assertEqual(rows[MAATHER]["status"], "missed")
        self.assertEqual(rows[MAATHER]["multiplier"], 0.9)
        self.assertFalse(rows[OHOUD]["reachable"])

    def test_the_unreachable_hole_is_surfaced_not_buried(self):
        self.open_week()
        st = routes.state(W)
        self.assertIn(OHOUD, st["unreachable"]["no_discord_id"])

    def test_an_open_appeal_appears_with_its_stage_in_arabic(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        w = db.warnings_for(NASSER, "active")[0]
        routes.do_open_appeal(w["appeal_token"], "عندي عذر")
        st = routes.state(W)
        self.assertEqual(len(st["appeals"]), 1)
        self.assertEqual(st["appeals"][0]["stage_name"], "أصيل")
        self.assertEqual(st["appeals"][0]["employee"], NASSER)

    def test_the_screen_reports_the_mode_honestly(self):
        self.assertFalse(routes.state(W)["dryrun"])
        os.environ["OPS_WARN_DRYRUN"] = "1"
        self.assertTrue(routes.state(W)["dryrun"])


class TestTheDeadline(OpsCase):

    def test_a_week_the_system_never_opened_can_never_be_a_warning(self):
        """A fresh deploy on Tuesday must NOT invent last week's obligation and warn five
        people for a week nobody was ever nudged about."""
        r = notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertEqual(r["verdicts"], [])
        self.assertEqual(db.counts()["ops_warnings"], 0)
        self.assertIsNone(db.obligation(db.obligation_id("wr", NASSER, W)))

    def test_a_miss_issues_exactly_one_warning_and_cuts_commission(self):
        self.open_week()
        r = notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertIn("missed", [v["verdict"] for v in r["verdicts"]])
        ws = db.warnings_for(NASSER, "active")
        self.assertEqual(len(ws), 1)
        led = db.commission(NASSER, ws[0]["month_key"])
        self.assertEqual(led["multiplier"], 0.9)
        self.assertIn("٩٠٪", "".join(self.texts()))

    def test_running_the_loop_twice_cannot_produce_a_second_warning(self):
        self.open_week()
        for _ in range(5):
            notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertEqual(len(db.warnings_for(NASSER)), 1)
        self.assertEqual(db.counts()["ops_warnings"], 4)      # 4 reachable people, 1 each

    def test_the_warning_is_private_and_carries_the_appeal_link(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        w = db.warnings_for(NASSER, "active")[0]
        dm = [p for p in self.sent_to(NASSER) if p.get("kind") == "warning"][0]
        self.assertIn(w["appeal_token"], dm["text"])
        self.assertIn("https://ouja.test/appeal/", dm["text"])
        self.assertEqual(dm["hr_channel"], notify.hr_channel())
        self.assertNotIn("public_channel", dm)

    def test_an_unreachable_person_is_never_warned(self):
        self.open_week()
        r = notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertEqual(db.warnings_for(OHOUD), [])
        self.assertEqual([x["verdict"] for x in r["verdicts"] if x["employee"] == OHOUD],
                         ["unreachable"])
        self.assertEqual(db.obligation(db.obligation_id("wr", OHOUD, W))["status"], "waived")

    def test_a_deadline_missed_by_the_loop_is_still_settled_later(self):
        """Container restarts across Monday midnight and the loop only runs Wednesday. The
        obligation must still reach a verdict rather than sit pending forever."""
        self.open_week()
        r = notify.tick(now=at(2026, 7, 29, 9, 0))
        self.assertEqual(db.obligation(db.obligation_id("wr", NASSER, W))["status"], "missed")
        self.assertEqual(r["period"], "2026-W32")            # and the new week has opened
        self.assertTrue(db.obligation(db.obligation_id("wr", NASSER, "2026-W32")))

    def test_unreadable_reports_never_produce_a_warning(self):
        self.open_week()

        def boom():
            raise RuntimeError("hostaway down")
        HOST.weekly_reports = boom
        notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertEqual(db.counts()["ops_warnings"], 0)
        self.assertEqual(db.obligation(db.obligation_id("wr", NASSER, W))["status"], "pending")


class TestMercy(OpsCase):

    def test_approved_leave_waives_silently_with_zero_messages(self):
        self.open_week()
        emp = next(e for e in sdb.employees() if e["name"] == NOURA)
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,"
                    "status,created_at) VALUES(?,?,?,?,'approved',?)",
                    (emp["id"], "2026-07-25", "2026-07-28", "vacation", sdb.now_iso()))
        notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertEqual(db.warnings_for(NOURA), [])
        self.assertEqual(db.obligation(db.obligation_id("wr", NOURA, W))["status"], "waived")
        self.assertEqual([p for p in self.sent_to(NOURA)
                          if p.get("kind") in ("warning", "mercy")], [])

    def test_leave_does_not_burn_the_quarterly_free_pass(self):
        os.environ["OPS_FREE_PASS_PER_QUARTER"] = "1"
        self.open_week()
        emp = next(e for e in sdb.employees() if e["name"] == NOURA)
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,"
                    "status,created_at) VALUES(?,?,?,?,'approved',?)",
                    (emp["id"], "2026-07-25", "2026-07-28", "vacation", sdb.now_iso()))
        notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertFalse(db.free_pass_used(NOURA, "2026-Q3"))

    def test_the_free_pass_applies_once_per_quarter_on_a_first_miss(self):
        os.environ["OPS_FREE_PASS_PER_QUARTER"] = "1"
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))                       # week 31 -> forgiven
        self.assertEqual(db.warnings_for(NASSER), [])
        self.assertTrue(db.free_pass_used(NASSER, "2026-Q3"))
        self.assertIn("السماح الفصلي", "".join(self.texts()))

        notify.tick(now=at(2026, 8, 4, 0, 5))                        # week 32 -> a warning
        self.assertEqual(len(db.warnings_for(NASSER, "active")), 1)

    def test_a_leader_excuse_before_the_deadline_blocks_the_warning(self):
        notify.tick(now=at(2026, 7, 27, 20, 5))                      # obligation exists
        r = routes.do_excuse(NASSER, W, "كان بمستشفى — كلمني", "أصيل")
        self.assertTrue(r["ok"], r)
        notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertEqual(db.warnings_for(NASSER), [])
        self.assertEqual(db.obligation(db.obligation_id("wr", NASSER, W))["status"], "excused")

    def test_an_excuse_needs_a_written_reason(self):
        notify.tick(now=at(2026, 7, 27, 20, 5))
        self.assertFalse(routes.do_excuse(NASSER, W, "   ", "أصيل")["ok"])

    def test_an_excuse_after_a_warning_is_refused_and_points_at_the_honest_route(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        r = routes.do_excuse(NASSER, W, "عنده عذر", "أصيل")
        self.assertFalse(r["ok"])
        self.assertIn("إنذار", r["error"])

    def test_four_clean_weeks_retire_exactly_the_oldest_active_warning(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))                       # W31 warning
        notify.tick(now=at(2026, 8, 4, 0, 5))                        # W32 warning
        self.assertEqual(len(db.warnings_for(NASSER, "active")), 2)
        oldest = sorted(db.warnings_for(NASSER, "active"),
                        key=lambda w: w["issued_at"])[0]

        for wk, day in (("2026-W33", "2026-08-10"), ("2026-W34", "2026-08-17"),
                        ("2026-W35", "2026-08-24"), ("2026-W36", "2026-08-31")):
            self.file_report(NASSER, day)
            notify.tick(now=datetime.datetime.fromisoformat(day + "T12:00").replace(tzinfo=RIYADH))

        active = db.warnings_for(NASSER, "active")
        self.assertEqual(len(active), 1)
        self.assertEqual(db.warning(oldest["id"])["status"], "retired")
        self.assertEqual(db.commission(NASSER, active[0]["month_key"])["multiplier"], 0.9)

    def test_a_waive_voids_the_warning_and_restores_the_money_at_once(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        w = db.warnings_for(NASSER, "active")[0]
        r = routes.do_waive(w["id"], "الشبكة كانت طايحة عنده", "فيصل")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["commission"]["multiplier"], 1.0)
        self.assertEqual(db.warning(w["id"])["status"], "voided")

    def test_a_waive_needs_a_written_reason(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        w = db.warnings_for(NASSER, "active")[0]
        self.assertFalse(routes.do_waive(w["id"], "", "فيصل")["ok"])
        self.assertEqual(db.warning(w["id"])["status"], "active")


class TestAppeals(OpsCase):

    def warn(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        return db.warnings_for(NASSER, "active")[0]

    def test_the_token_opens_an_appeal_with_no_login(self):
        w = self.warn()
        r = routes.do_open_appeal(w["appeal_token"], "سلمته يوم الأحد بس النت فصل")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["appeal"]["stage"], "s1")
        self.assertEqual(notify.APPROVER_NAMES["s1"], "أصيل")

    def test_a_bad_token_reveals_nothing(self):
        self.warn()
        r = routes.do_open_appeal("not-a-real-token", "أي كلام")
        self.assertFalse(r["ok"])
        for name in (NASSER, MAATHER, NOURA, YAMI, OHOUD):
            self.assertNotIn(name, repr(r))

    def test_accept_voids_and_recomputes_commission_immediately(self):
        w = self.warn()
        a = routes.do_open_appeal(w["appeal_token"], "عندي إثبات")["appeal"]
        r = routes.do_decide_appeal(a["id"], "accept", "شفت الإثبات — الإنذار غلط", "أصيل")
        self.assertEqual(r["outcome"], "accepted")
        self.assertEqual(r["commission"]["multiplier"], 1.0)
        self.assertEqual(db.warning(w["id"])["status"], "voided")
        self.assertEqual(db.appeal(a["id"])["stage"], "closed")

    def test_reject_without_a_written_reason_is_refused(self):
        w = self.warn()
        a = routes.do_open_appeal(w["appeal_token"], "أعترض")["appeal"]
        for bad in ("", "   ", None):
            r = routes.do_decide_appeal(a["id"], "reject", bad, "أصيل")
            self.assertFalse(r["ok"])
            self.assertIn("سبب", r["error"])
        self.assertEqual(db.appeal(a["id"])["stage"], "s1")      # still open, not closed

    def test_the_employee_hears_the_reason_at_every_transition(self):
        w = self.warn()
        a = routes.do_open_appeal(w["appeal_token"], "أعترض")["appeal"]
        routes.do_decide_appeal(a["id"], "escalate", "أبي رأي ريم", "أصيل")
        routes.do_decide_appeal(a["id"], "reject", "التقرير فعلاً ما وصل", "ريم")
        to_emp = [p for p in self.sent_to(NASSER) if p.get("kind") == "appeal"]
        self.assertTrue(any("ريم" in p["text"] for p in to_emp))
        self.assertTrue(any("التقرير فعلاً ما وصل" in p["text"] for p in to_emp))

    def test_it_auto_escalates_at_24h_and_never_dies_in_silence(self):
        w = self.warn()
        a = routes.do_open_appeal(w["appeal_token"], "أعترض")["appeal"]
        opened = datetime.datetime.fromisoformat(db.appeal(a["id"])["opened_at"])

        self.assertEqual(notify.appeal_tick(now=opened +
                                            datetime.timedelta(hours=23))["moved"], [])
        self.assertEqual(db.appeal(a["id"])["stage"], "s1")

        notify.appeal_tick(now=opened + datetime.timedelta(hours=24, minutes=1))
        self.assertEqual(db.appeal(a["id"])["stage"], "s2")
        notify.appeal_tick(now=opened + datetime.timedelta(hours=49))
        self.assertEqual(db.appeal(a["id"])["stage"], "s3")
        hist = db.appeal_decisions(db.appeal(a["id"]))
        self.assertEqual(sum(1 for h in hist if h["action"] == "auto_escalated"), 2)

    def test_an_appeal_on_a_voided_warning_is_refused(self):
        w = self.warn()
        routes.do_waive(w["id"], "عذر مقبول", "فيصل")
        self.assertFalse(routes.do_open_appeal(w["appeal_token"], "أعترض")["ok"])


class TestDryRun(OpsCase):
    """The mode that runs for two full weeks before anything is switched on."""

    ENV = dict(OpsCase.ENV, OPS_WARN_DRYRUN="1")

    def test_it_issues_nothing_sends_nothing_and_writes_no_warning_rows(self):
        for now in (at(2026, 7, 26, 18, 5), at(2026, 7, 27, 10, 5), at(2026, 7, 27, 20, 5),
                    at(2026, 7, 28, 0, 5), at(2026, 7, 28, 9, 0)):
            notify.tick(now=now)
        c = db.counts()
        self.assertEqual(c["ops_warnings"], 0)
        self.assertEqual(c["ops_free_passes"], 0)
        self.assertEqual(c["ops_appeals"], 0)
        self.assertEqual(self.sent, [])                    # not one message left the process
        self.assertGreater(c["ops_dryrun_log"], 0)         # but the log is full

    def test_the_log_says_what_would_have_happened_and_to_whom(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        rows = db.dry_rows(200)
        would = [r for r in rows if r["kind"] == "warning"]
        self.assertTrue(would)
        self.assertIn(NASSER, [r["employee"] for r in would])
        self.assertIn("٩٠٪", " ".join(r["detail"] for r in would))

    def test_dry_run_still_records_the_ladder_so_the_owner_sees_the_timing(self):
        notify.tick(now=at(2026, 7, 26, 18, 5))
        oid = db.obligation_id("wr", NASSER, W)
        self.assertEqual(db.sent_levels(oid), ["L1"])
        self.assertEqual([r["path"] for r in db.ladder_rows(oid)], ["dryrun"])

    def test_commission_is_never_written_in_dry_run(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        self.assertEqual(db.counts()["ops_commission_ledger"], 0)


class TestPublicOutput(OpsCase):

    def test_the_monthly_summary_contains_no_employee_name(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        s = notify.monthly_summary("2026-07")
        for name in (NASSER, MAATHER, NOURA, YAMI, OHOUD):
            self.assertNotIn(name, s["text"])
            self.assertNotIn(name, repr(s["counts"]))
        self.assertIn("التقارير الأسبوعية", s["text"])
        self.assertIn("إنذارات", s["text"])

    def test_it_reads_in_arabic_numerals_like_the_spec(self):
        s = notify.monthly_summary("2026-07")["text"]
        for d in "0123456789":
            self.assertNotIn(d, s.split("·")[0].replace("2026-07", ""))

    def test_nothing_is_posted_publicly_unless_asked(self):
        self.open_week()
        notify.tick(now=at(2026, 7, 28, 0, 5))
        before = len(self.sent)
        notify.monthly_summary("2026-07")
        self.assertEqual(len(self.sent), before)


class TestNoHumanCanAccuse(unittest.TestCase):
    """A structural guard, not a behavioural one: if a future edit wires warning-issuing
    into a route, this fails."""

    def test_no_route_handler_can_reach_issue_warning(self):
        import inspect
        src = inspect.getsource(routes)
        self.assertEqual(src.count("db.issue_warning("), 0)
        self.assertEqual(src.count("issue_warning"), 1)      # the docstring line only

    def test_issue_warning_is_called_from_exactly_one_place(self):
        import inspect
        src = inspect.getsource(notify)
        self.assertEqual(src.count("db.issue_warning("), 1)


if __name__ == "__main__":
    unittest.main()
