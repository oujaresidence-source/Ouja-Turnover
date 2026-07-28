# -*- coding: utf-8 -*-
"""
ops.capture — persisting the scorecard's missing input, on a real (temporary) brain.db.

The rules being locked:
    * attribution routes to the COVERER when the owner is off that date, and to the OWNER
      when they are working — resolved for THAT date, never today's roster
    * first response only: a second outgoing in the same exchange creates no new event
    * the backfill is idempotent — running it twice writes zero duplicates
    * an escalation taken by somebody other than the responsible person sets
      taken_by_responsible = 0
    * the capture layer can never take down the guest-messaging path

Run: python3 -m unittest tests.test_ops_capture
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                # noqa: E402
from schedule import db as sdb, seed as sseed             # noqa: E402
from ops import capture, db, engine, notify               # noqa: E402
from ops.host import HOST                                 # noqa: E402

RIYADH = engine.tz()

# 2026-07-28 is a Tuesday. In the seeded calendar ناصر is off on الثلاثاء (off_day 2),
# so his apartments must be attributed to whoever covers them that day.
TUE = datetime.date(2026, 7, 28)
WED = datetime.date(2026, 7, 29)
LID = 990011


def msg(mid, inbound, when, body="hello"):
    return {"id": mid, "isIncoming": 1 if inbound else 0, "date": when, "body": body}


class CaptureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="opscap_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        sdb.reset_init_cache()
        db.reset_init_cache()
        sseed.seed_if_empty()
        capture.clear_attribution_cache()

        # link one of ناصر's apartments to a Hostaway listing id
        nasser = next(e for e in sdb.employees() if e["name"] == "ناصر")
        apt = [a for a in sdb.apartments() if a["owner_id"] == nasser["id"]][0]
        sdb.execute("UPDATE schedule_apartments SET listing_id=? WHERE id=?", (LID, apt["id"]))

        HOST.msg_is_inbound = lambda m: int(m.get("isIncoming") or 0) == 1
        HOST.msg_time = lambda m: m.get("date") or ""
        HOST.msg_is_automated = lambda m: "booking confirmed" in (m.get("body") or "").lower()
        HOST.work_start_hour, HOST.work_end_hour, HOST.work_end_min = 11, 25, 30
        HOST.discord_ids = lambda: {"ناصر": "111", "نورة": "333"}

        self._cap = os.environ.get("OPS_CAPTURE_ENABLED")
        os.environ["OPS_CAPTURE_ENABLED"] = "1"

    def tearDown(self):
        if self._cap is None:
            os.environ.pop("OPS_CAPTURE_ENABLED", None)
        else:
            os.environ["OPS_CAPTURE_ENABLED"] = self._cap
        capture.clear_attribution_cache()


class TestAttribution(CaptureCase):
    """Hostaway cannot tell us who replied. We attribute by ownership, per date."""

    def test_it_routes_to_the_owner_when_the_owner_is_working(self):
        name, _did, how = capture.responsible_for(LID, WED)      # Wednesday: ناصر works
        self.assertEqual(name, "ناصر")
        self.assertEqual(how, "owner")

    def test_it_routes_to_the_coverer_when_the_owner_is_off(self):
        name, _did, how = capture.responsible_for(LID, TUE)      # Tuesday: ناصر is off
        self.assertNotEqual(name, "ناصر")
        self.assertTrue(name)
        self.assertEqual(how, "coverer")

    def test_an_unknown_apartment_is_unknown_never_a_guess(self):
        name, did, how = capture.responsible_for(4242424, WED)
        self.assertEqual((name, did, how), ("", "", "unknown"))

    def test_garbage_listing_ids_do_not_raise(self):
        for bad in (None, "", "abc", {}):
            self.assertEqual(capture.responsible_for(bad, WED)[2], "unknown")

    def test_attribution_is_frozen_into_the_row_at_capture_time(self):
        capture.on_conversation("c1", LID, "Ouja | تجربة",
                                [msg("g1", True, "2026-07-28 12:00:00"),
                                 msg("h1", False, "2026-07-28 12:20:00")])
        row = db.response_event("c1", "g1")
        coverer = row["responsible"]
        self.assertEqual(row["attribution"], "coverer")
        # the roster changes afterwards — a scored month must not be rewritten
        sdb.execute("UPDATE schedule_employees SET off_day=5 WHERE name='ناصر'")
        capture.clear_attribution_cache()
        self.assertEqual(db.response_event("c1", "g1")["responsible"], coverer)

    def test_the_claim_picker_spelling_is_reconciled(self):
        """CLAIM_NAMES is a THIRD spelling: «ماثر» vs «مآثر» vs «ماذر»."""
        self.assertEqual(capture.match_person("ماثر"), "مآثر")
        self.assertEqual(capture.match_person("نوره"), "نورة")
        self.assertEqual(capture.match_person("محمد"), "محمد اليامي")

    def test_an_unknown_claim_name_is_never_attributed_to_somebody_else(self):
        self.assertEqual(capture.match_person("زائر"), "زائر")


class TestResponseCapture(CaptureCase):

    def test_one_wait_one_row_with_worked_minutes(self):
        r = capture.on_conversation("c1", LID, "unit",
                                    [msg("g1", True, "2026-07-29 12:00:00"),
                                     msg("h1", False, "2026-07-29 12:25:00")])
        self.assertEqual(r["written"], 1)
        row = db.response_event("c1", "g1")
        self.assertEqual(row["minutes_raw"], 25.0)
        self.assertEqual(row["minutes_worked"], 25.0)
        self.assertEqual(row["responsible"], "ناصر")
        self.assertEqual(row["month_key"], "2026-07")

    def test_a_second_outgoing_in_the_same_exchange_creates_no_new_event(self):
        capture.on_conversation("c1", LID, "unit",
                                [msg("g1", True, "2026-07-29 12:00:00"),
                                 msg("h1", False, "2026-07-29 12:10:00"),
                                 msg("h2", False, "2026-07-29 12:40:00")])
        self.assertEqual(db.counts()["ops_response_events"], 1)
        self.assertEqual(db.response_event("c1", "g1")["outgoing_msg_id"], "h1")

    def test_the_overnight_clock_only_counts_working_time(self):
        capture.on_conversation("c1", LID, "unit",
                                [msg("g1", True, "2026-07-29 02:00:00"),
                                 msg("h1", False, "2026-07-29 11:30:00")])
        row = db.response_event("c1", "g1")
        self.assertEqual(row["minutes_raw"], 570.0)      # 9.5h by the clock
        self.assertEqual(row["minutes_worked"], 30.0)    # 30 min by any fair measure

    def test_an_unanswered_wait_is_recorded_then_completed_later(self):
        capture.on_conversation("c1", LID, "unit", [msg("g1", True, "2026-07-29 12:00:00")])
        row = db.response_event("c1", "g1")
        self.assertIsNone(row["responded_at"])

        r = capture.on_conversation("c1", LID, "unit",
                                    [msg("g1", True, "2026-07-29 12:00:00"),
                                     msg("h1", False, "2026-07-29 12:45:00")])
        self.assertEqual(r["completed"], 1)
        self.assertEqual(r["written"], 0)
        row = db.response_event("c1", "g1")
        self.assertEqual(row["responded_at"], "2026-07-29 12:45:00")
        self.assertEqual(row["minutes_worked"], 45.0)

    def test_a_later_reply_never_overwrites_the_first(self):
        capture.on_conversation("c1", LID, "unit",
                                [msg("g1", True, "2026-07-29 12:00:00"),
                                 msg("h1", False, "2026-07-29 12:10:00")])
        capture.on_conversation("c1", LID, "unit",
                                [msg("g1", True, "2026-07-29 12:00:00"),
                                 msg("h1", False, "2026-07-29 12:10:00"),
                                 msg("h9", False, "2026-07-29 18:00:00")])
        self.assertEqual(db.response_event("c1", "g1")["minutes_worked"], 10.0)

    def test_running_the_same_conversation_ten_times_writes_one_row(self):
        for _ in range(10):
            capture.on_conversation("c1", LID, "unit",
                                    [msg("g1", True, "2026-07-29 12:00:00"),
                                     msg("h1", False, "2026-07-29 12:20:00")])
        self.assertEqual(db.counts()["ops_response_events"], 1)

    def test_the_kill_switch_stops_recording_and_nothing_else(self):
        os.environ["OPS_CAPTURE_ENABLED"] = "0"
        r = capture.on_conversation("c1", LID, "unit",
                                    [msg("g1", True, "2026-07-29 12:00:00")])
        self.assertEqual(r, {"written": 0, "completed": 0, "skipped": 0})
        self.assertEqual(db.counts()["ops_response_events"], 0)


class TestItCannotTakeDownGuestMessaging(CaptureCase):
    """This runs inside the live guest path. It must fail silently, always."""

    def test_malformed_messages_never_raise(self):
        for junk in ([{"nonsense": 1}], [None], [{"id": None, "date": None}],
                     [{"id": "x", "isIncoming": 1, "date": "not-a-date"}]):
            r = capture.on_conversation("cX", LID, "unit", junk)
            self.assertIsInstance(r, dict)

    def test_a_broken_database_never_raises(self):
        original = db.record_response_event

        def boom(_row):
            raise RuntimeError("disk full")
        db.record_response_event = boom
        try:
            r = capture.on_conversation("cY", LID, "unit",
                                        [msg("g1", True, "2026-07-29 12:00:00")])
            self.assertEqual(r["skipped"], 1)
        finally:
            db.record_response_event = original

    def test_a_broken_calendar_never_raises(self):
        original = capture.attribution_for

        def boom(_day):
            raise RuntimeError("calendar down")
        capture.attribution_for = boom
        try:
            r = capture.on_conversation("cZ", LID, "unit",
                                        [msg("g1", True, "2026-07-29 12:00:00")])
            self.assertIsInstance(r, dict)
        finally:
            capture.attribution_for = original


class TestEscalationCapture(CaptureCase):

    def test_taken_by_the_responsible_person_sets_the_flag(self):
        capture.on_escalation_opened("e1", "unit", LID, opened_at="2026-07-29 13:00:00")
        row = db.escalation_event("e1")
        self.assertEqual(row["responsible"], "ناصر")

        capture.on_escalation_taken("e1", "ناصر")
        self.assertEqual(db.escalation_event("e1")["taken_by_responsible"], 1)

    def test_taken_by_somebody_else_sets_zero(self):
        capture.on_escalation_opened("e2", "unit", LID, opened_at="2026-07-29 13:00:00")
        capture.on_escalation_taken("e2", "نوره")            # the claim-picker spelling
        row = db.escalation_event("e2")
        self.assertEqual(row["taken_by"], "نورة")            # reconciled
        self.assertEqual(row["taken_by_responsible"], 0)

    def test_the_first_take_wins(self):
        capture.on_escalation_opened("e3", "unit", LID, opened_at="2026-07-29 13:00:00")
        capture.on_escalation_taken("e3", "ناصر")
        capture.on_escalation_taken("e3", "نورة")
        self.assertEqual(db.escalation_event("e3")["taken_by"], "ناصر")

    def test_an_escalation_on_an_off_day_belongs_to_the_coverer(self):
        capture.on_escalation_opened("e4", "unit", LID, opened_at="2026-07-28 13:00:00")
        self.assertNotEqual(db.escalation_event("e4")["responsible"], "ناصر")


class TestBackfill(CaptureCase):

    CONVOS = [{"id": "b1", "listingMapId": LID, "listingName": "unit"}]
    MSGS = {"b1": [msg("g1", True, "2026-07-29 12:00:00"),
                   msg("h1", False, "2026-07-29 12:15:00"),
                   msg("g2", True, "2026-07-29 16:00:00"),
                   msg("h2", False, "2026-07-29 16:40:00")]}

    def run_backfill(self, days=30):
        return capture.backfill(days=days,
                                fetch_conversations=lambda d: self.CONVOS,
                                fetch_messages=lambda cid: self.MSGS.get(cid, []),
                                listings={LID: "Ouja | تجربة"})

    def test_it_writes_one_event_per_exchange(self):
        rep = self.run_backfill()
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["written"], 2)
        self.assertEqual(db.counts()["ops_response_events"], 2)

    def test_running_it_twice_writes_zero_duplicates(self):
        self.run_backfill()
        again = self.run_backfill()
        self.assertEqual(again["written"], 0)
        self.assertEqual(again["skipped"], 2)
        self.assertEqual(db.counts()["ops_response_events"], 2)

    def test_it_reports_how_much_it_could_attribute(self):
        rep = self.run_backfill()
        self.assertEqual(rep["events_in_window"], 2)
        self.assertEqual(rep["unattributed"], 0)

    def test_an_unlinked_apartment_is_counted_as_unattributed(self):
        self.CONVOS = [{"id": "b9", "listingMapId": 777777, "listingName": "غير مربوطة"}]
        self.MSGS = {"b9": [msg("g1", True, "2026-07-29 12:00:00")]}
        rep = self.run_backfill()
        self.assertEqual(rep["unattributed"], 1)

    def test_the_day_range_is_clamped(self):
        self.assertEqual(self.run_backfill(days=500)["days"], 90)
        self.assertEqual(self.run_backfill(days=0)["days"], 1)

    def test_with_no_reader_wired_it_refuses_instead_of_guessing(self):
        HOST.fetch_conversations = None
        HOST.fetch_messages = None
        self.assertFalse(capture.backfill(days=30)["ok"])


if __name__ == "__main__":
    unittest.main()
