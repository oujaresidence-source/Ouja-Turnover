# -*- coding: utf-8 -*-
"""«الحملات» board — the owner's campaign page. Offline: fake reservations, throwaway brain.db.

Locked here:
  * status by time: scheduled → measuring (inside the window) → done; a cancelled send stays out
    of every total
  * a booking counts only when a person who GOT the campaign (phone key) books INSIDE its window;
    before the send, after the window, someone else, or an unconfirmed booking never counts
  * baseline = people × the group's no-message rate × the share of the window measured so far;
    lift = bookings − baseline; owners count replies + signed units, never bookings
  * the comparison group (holdout) is measured from the first «الليلة الثانية بنص» send
  * a tap is credited by phone key first, else to the latest send of its template
  * totals: cost only for sent campaigns, return per riyal, the next send
  * the audience upload stores keys, never a number; admin edits validate
  * the shipped seed: 13 campaigns, 1,959 people, every group known, no phone numbers in it

Run: python3 -m unittest tests.test_campaign_board
"""
import datetime
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                     # noqa: E402
from campaigns import board, db, engine, host   # noqa: E402

DT = datetime.datetime

SEED = {
    "msg_cost_sar": 0.25,
    "groups": {
        "B1": {"name": "الليلة الثانية بنص", "kind": "guest", "unit": "حجز", "value": 1000,
               "expect": [0.02, 0.04, 0.08], "baseline": 0.01, "window_days": 14},
        "A1": {"name": "الملاك", "kind": "owner", "unit": "شقة", "value": 1900,
               "expect": [0.01, 0.02, 0.04], "baseline": 0, "window_days": 30},
        "A2": {"name": "شهري", "kind": "guest", "unit": "حجز شهري", "value": 15000,
               "expect": [0.004, 0.01, 0.02], "baseline": None, "window_days": 30},
    },
    "campaigns": [
        # Riyadh 12:00 = 09:00 UTC
        {"id": "B1-same", "group": "B1", "title": "t", "who": "w", "send_at": "2026-11-25T12:00",
         "people": 100, "template": "ouja_midweek_half_img"},
        {"id": "B1-plan", "group": "B1", "title": "t", "who": "w", "send_at": "2026-11-27T18:00",
         "people": 50, "template": "ouja_midweek_half_img"},
        {"id": "A1-2026", "group": "A1", "title": "t", "who": "w", "send_at": "2026-11-25T11:00",
         "people": 127, "template": "ouja_owner_recontact_img"},
        {"id": "A2-monthly", "group": "A2", "title": "t", "who": "w", "send_at": "2026-12-13T11:00",
         "people": 500, "template": ""},
    ],
}


def by_id(res, cid):
    return [r for r in res["campaigns"] if r["id"] == cid][0]


class ComputeTests(unittest.TestCase):
    def setUp(self):
        self.aud = {"B1-same": {"sent": [("k1", ""), ("k2", ""), ("k3", "")]},
                    "B1-holdout": {"holdout": [("h1", ""), ("h2", "")]}}

    def run_(self, now, bookings=(), taps=(), numbers=None, aud=None):
        return board.compute(SEED, numbers or {}, self.aud if aud is None else aud, list(taps),
                             list(bookings), now)

    def test_status_by_time(self):
        r = self.run_(DT(2026, 11, 25, 8, 30))                       # 11:30 Riyadh
        self.assertEqual(by_id(r, "A1-2026")["status"], "measuring")
        self.assertEqual(by_id(r, "B1-same")["status"], "scheduled")
        self.assertEqual(r["next"], ["B1-same"])
        r = self.run_(DT(2026, 12, 10))
        self.assertEqual(by_id(r, "B1-same")["status"], "done")      # 14 days passed
        self.assertEqual(by_id(r, "A1-2026")["status"], "measuring")  # owners: 30 days
        self.assertEqual(by_id(r, "A2-monthly")["status"], "scheduled")

    def test_only_audience_inside_window_confirmed(self):
        now = DT(2026, 11, 30)
        bk = [{"id": 1, "made": DT(2026, 11, 25, 10), "pkey": "k1", "total": 900, "nights": 2},
              {"id": 2, "made": DT(2026, 11, 26), "pkey": "k1", "total": 300, "nights": 1},   # same person
              {"id": 3, "made": DT(2026, 11, 25, 8), "pkey": "k2", "total": 999},            # before send
              {"id": 4, "made": DT(2026, 11, 27), "pkey": "zz", "total": 999},               # not in list
              {"id": 5, "made": DT(2026, 12, 20), "pkey": "k3", "total": 999}]               # after window
        r = self.run_(now, bk)
        a = by_id(r, "B1-same")["actual"]
        self.assertEqual(a["bookings"], 1)          # one PERSON booked
        self.assertEqual(a["sar"], 1200)            # both of their bookings count as money
        self.assertEqual(a["nights"], 3)
        self.assertEqual(r["totals"]["bookings"], 1)
        self.assertEqual(r["totals"]["revenue"], 1200)

    def test_baseline_scales_with_time_measured(self):
        # B1-same: 3 people loaded → people=3; 7 of 14 days measured → 3 × 1% × 0.5
        now = DT(2026, 11, 25, 9) + datetime.timedelta(days=7)
        row = by_id(self.run_(now), "B1-same")
        self.assertEqual(row["people"], 3)
        self.assertAlmostEqual(row["baseline"], 0.015, places=3)
        self.assertAlmostEqual(row["lift"], -0.015, places=3)
        # Hatif's own «sent» count wins over the list size
        row = by_id(self.run_(now, numbers={"B1-same": {"sent": 200}}), "B1-same")
        self.assertEqual(row["people"], 200)
        self.assertAlmostEqual(row["baseline"], 1.0, places=2)

    def test_owner_counts_replies_and_signed(self):
        taps = [{"created_at": "2026-11-25T09:00:00", "template": "ouja_owner_recontact_img",
                 "kind": "owner_call", "phone_key": "o1"},
                {"created_at": "2026-11-25T10:00:00", "template": "ouja_owner_recontact_img",
                 "kind": "owner_later", "phone_key": "o2"},
                {"created_at": "2026-11-25T10:05:00", "template": "ouja_owner_recontact_img",
                 "kind": "opt_out", "phone_key": "o3"}]
        r = self.run_(DT(2026, 11, 26), taps=taps, numbers={"A1-2026": {"signed": 2}})
        a = by_id(r, "A1-2026")["actual"]
        self.assertEqual(a, {"replies": 2, "signed": 2, "sar": 3800})
        self.assertNotIn("bookings", a)
        self.assertEqual(r["totals"]["owner_signed"], 2)
        self.assertEqual(r["totals"]["opt_out"], 1)

    def test_tap_credit_by_key_then_latest_send(self):
        taps = [{"created_at": "2026-11-28T10:00:00", "template": "ouja_midweek_half_img",
                 "kind": "show_units", "phone_key": "k2"},       # key → B1-same even after B1-plan went
                {"created_at": "2026-11-28T10:00:00", "template": "ouja_midweek_half",
                 "kind": "show_units", "phone_key": "unknown"},  # no key → the latest send = B1-plan
                {"created_at": "2026-11-25T10:00:00", "template": "ouja_midweek_half_img",
                 "kind": "show_units", "phone_key": ""}]          # before B1-plan → B1-same
        r = self.run_(DT(2026, 11, 29), taps=taps)
        self.assertEqual(by_id(r, "B1-same")["taps"], {"show_units": 2})
        self.assertEqual(by_id(r, "B1-plan")["taps"], {"show_units": 1})

    def test_cancelled_stays_out(self):
        r = self.run_(DT(2026, 11, 29), numbers={"B1-plan": {"status": "cancelled"}})
        self.assertEqual(by_id(r, "B1-plan")["status"], "cancelled")
        self.assertEqual(by_id(r, "B1-plan")["cost"], 0)
        self.assertEqual(r["totals"]["campaigns_total"], 3)

    def test_moved_send(self):
        r = self.run_(DT(2026, 11, 25, 10), numbers={"B1-plan": {"send_at": "2026-11-25T12:00"}})
        self.assertEqual(by_id(r, "B1-plan")["status"], "measuring")

    def test_totals_cost_roi_expected(self):
        bk = [{"id": 1, "made": DT(2026, 11, 26), "pkey": "k1", "total": 1000}]
        r = self.run_(DT(2026, 11, 26, 12), bk)
        t = r["totals"]
        # sent so far: A1 (127) + B1-same (3 loaded) → 130 × 0.25
        self.assertEqual(t["people_sent"], 130)
        self.assertEqual(t["cost"], 32.5)
        self.assertEqual(t["roi"], round(1000 / 32.5, 1))
        self.assertEqual(by_id(r, "B1-plan")["cost"], 0)              # not sent yet: costs nothing
        self.assertEqual(by_id(r, "B1-plan")["expected"]["count"], [1.0, 2.0, 4.0])
        self.assertEqual(by_id(r, "B1-plan")["expected"]["sar"], [1000, 2000, 4000])
        self.assertIsNone(by_id(r, "A2-monthly").get("baseline"))     # no history → no baseline

    def test_no_baseline_group_measured(self):
        r = self.run_(DT(2026, 12, 14), aud={"A2-monthly": {"sent": [("m1", "")]}},
                      bookings=[{"id": 9, "made": DT(2026, 12, 13, 12), "pkey": "m1", "total": 15000}])
        row = by_id(r, "A2-monthly")
        self.assertIsNone(row["baseline"])
        self.assertIsNone(row["lift"])
        self.assertEqual(row["actual"]["bookings"], 1)

    def test_holdout_from_first_b1_send(self):
        bk = [{"id": 1, "made": DT(2026, 11, 26), "pkey": "h1", "total": 500},
              {"id": 2, "made": DT(2026, 11, 20), "pkey": "h2", "total": 500}]   # before: no
        r = self.run_(DT(2026, 11, 28), bk)
        self.assertEqual(r["holdout"]["people"], 2)
        self.assertEqual(r["holdout"]["booked"], 1)
        self.assertEqual(r["holdout"]["rate"], 50.0)
        self.assertIsNone(self.run_(DT(2026, 11, 24))["holdout"])         # nothing sent yet


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="campboard_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        os.environ.pop("STATE_DIR", None)
        self.calls = []
        host.wire({"reservations": lambda a, b: self.calls.append((a, b)) or self.rows})
        self.rows = []
        board._bk_cache.update(key=None, at=0.0, rows=[])

    def test_audience_keys_only(self):
        res = board.load_audience("B1-same", ["0551234567", "+966551234568", "nope", "0551234567"])
        self.assertEqual(res, {"added": 2, "bad": 1})
        with open(bdb.db_path(), "rb") as f:
            raw = f.read()
        self.assertNotIn(b"551234567", raw)            # the number never reaches the file
        aud = db.audiences()
        self.assertEqual(len(aud["B1-same"]["sent"]), 2)
        self.assertEqual(aud["B1-same"]["sent"][0][0],
                         engine.phone_key("966551234567", db.salt()))
        self.assertEqual(board.load_audience("B1-same", ["0551234569"], replace=True)["added"], 1)
        self.assertEqual(len(db.audiences()["B1-same"]["sent"]), 1)
        self.assertEqual(board.load_audience("B1-holdout", ["0551234570"], role="holdout")["added"], 1)
        with self.assertRaises(ValueError):
            board.load_audience("nope", ["0551234567"])
        with self.assertRaises(ValueError):
            board.load_audience("B1-same", ["0551234567"], role="boss")

    def test_numbers_validate(self):
        board.set_numbers("B1-same", {"sent": "140", "delivered": 138, "note": "x"})
        board.set_numbers("B1-same", {"read_n": 90})
        n = db.board_numbers()["B1-same"]
        self.assertEqual((n["sent"], n["delivered"], n["read_n"], n["note"]), (140, 138, 90, "x"))
        board.set_numbers("B1-same", {"delivered": ""})
        self.assertIsNone(db.board_numbers()["B1-same"]["delivered"])
        for bad in ({"status": "paused"}, {"send_at": "tomorrow"}, {"sent": "many"}):
            with self.assertRaises((ValueError, TypeError)):
                board.set_numbers("B1-same", bad)
        with self.assertRaises(ValueError):
            board.set_numbers("nope", {"sent": 1})

    def test_board_end_to_end(self):
        board.load_audience("B1-same", ["0551234567"])
        self.rows = [{"id": 7, "status": "new", "reservationDate": "2026-11-26 10:00:00",
                      "phone": "+966 55 123 4567", "totalPrice": 850, "nights": 2},
                     {"id": 8, "status": "inquiry", "reservationDate": "2026-11-26 10:00:00",
                      "phone": "0551234567", "totalPrice": 999}]
        r = board.board(DT(2026, 11, 27))
        row = by_id(r, "B1-same")
        self.assertEqual(row["actual"]["bookings"], 1)
        self.assertEqual(row["actual"]["sar"], 850)
        self.assertEqual(r["audiences"]["B1-same"], {"sent": 1})
        self.assertEqual(len(self.calls), 1)
        board.board(DT(2026, 11, 27))
        self.assertEqual(len(self.calls), 1)            # cached: Hostaway asked once

    def test_no_hostaway_call_before_any_send(self):
        board.load_audience("B1-same", ["0551234567"])
        board.board(DT(2026, 11, 24))
        self.assertEqual(self.calls, [])


class SeedTests(unittest.TestCase):
    def test_shipped_seed(self):
        with open(board.SEED, encoding="utf-8") as f:
            raw = f.read()
        d = json.loads(raw)
        self.assertEqual(len(d["campaigns"]), 13)
        self.assertEqual(sum(c["people"] for c in d["campaigns"]), 1959)
        self.assertFalse(re.search(r"(?:\+?966|0)5\d{8}", raw))          # no phone number, ever
        ids = [c["id"] for c in d["campaigns"]]
        self.assertEqual(len(ids), len(set(ids)))
        for c in d["campaigns"]:
            self.assertIn(c["group"], d["groups"])
            board.to_utc(c["send_at"])
        r = board.compute(d, {}, {}, [], [], DT(2026, 11, 24, 12))
        self.assertEqual(r["next"], ["A1-2026"])
        self.assertEqual(r["totals"]["cost_planned"], round(1959 * 0.25, 2))

    def test_state_file_wins_and_bad_edit_keeps_last_good(self):
        tmp = tempfile.mkdtemp(prefix="campseed_")
        os.environ["STATE_DIR"] = tmp
        try:
            board._seed_cache.update(path=None, mtime=None, data=None)
            p = os.path.join(tmp, "campaign_board.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"groups": {}, "campaigns": [{"id": "X"}]}, f)
            self.assertEqual(board.load_seed()["campaigns"][0]["id"], "X")
            with open(p, "w", encoding="utf-8") as f:
                f.write("{broken")
            os.utime(p, (1, 1))
            self.assertEqual(board.load_seed()["campaigns"][0]["id"], "X")
        finally:
            os.environ.pop("STATE_DIR", None)
            board._seed_cache.update(path=None, mtime=None, data=None)


if __name__ == "__main__":
    unittest.main()
