# -*- coding: utf-8 -*-
"""The room-flood guard.

Without the start-date cutoff the first tick would open a Discord room for every historical
direct booking — hundreds of channels. Locked here:
  * 200 historical direct reservations + a start date of today ⇒ ZERO tickets, zero rooms
  * DIRECTPAY_MAX_OPEN_PER_TICK is honoured and the remainder is REPORTED, not dropped
  * the start date is persisted on first run and never recomputed
  * dry-run writes the ledger row but fires nothing
  * the synthetic 30-reservation run the owner report prints

Run: python3 -m unittest tests.test_directpay_startdate
"""
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                  # noqa: E402
from directpay import db, engine, host, service              # noqa: E402

CONFIRMED = {"new", "modified"}
NOW = datetime.datetime(2026, 9, 10, 12, 0)


def finance_channel(r):
    ch = (r.get("channelName") or r.get("channel") or "").strip().lower()
    if "airbnb" in ch:
        return "airbnb"
    if (not ch) or any(w in ch for w in ("direct", "manual", "website", "owner", "walk")):
        return "direct"
    return "other"


def res(rid, channel="direct", status="new", booked="2026-09-10 09:00:00", **kw):
    r = {"id": rid, "channelName": channel, "status": status, "reservationDate": booked,
         "listingMapId": 900, "guestName": "ضيف %s" % rid, "arrivalDate": "2026-10-01",
         "departureDate": "2026-10-04", "nights": 3, "totalPrice": 1000.0 + rid}
    r.update(kw)
    return r


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dpstart_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self.fired = []
        host.wire({
            "now": lambda: NOW, "state_dir": self.tmp,
            "finance_channel": finance_channel, "confirmed_statuses": lambda: CONFIRMED,
            "payment_signal": lambda r: (None, None, None, []),
            "listings": lambda: {900: "Ouja | B14"},
            "notify": lambda p: self.fired.append(p), "log_event": None,
        })
        for k in ("DIRECTPAY_DRYRUN", "DIRECTPAY_START_DATE", "DIRECTPAY_MAX_OPEN_PER_TICK"):
            os.environ.pop(k, None)
        os.environ["DIRECTPAY_DRYRUN"] = "0"

    def tearDown(self):
        for k in ("DIRECTPAY_DRYRUN", "DIRECTPAY_START_DATE", "DIRECTPAY_MAX_OPEN_PER_TICK"):
            os.environ.pop(k, None)


class TestStartDate(Case):
    def test_200_historical_direct_bookings_open_nothing(self):
        hist = [res(i, booked="2026-0%d-%02d 10:00:00" % (1 + i % 8, 1 + i % 27)) for i in range(1, 201)]
        out = service.process_reservations(hist, now=NOW)
        self.assertEqual(out["opened"], [])
        self.assertEqual(out["waiting"], 0)
        self.assertEqual(out["skipped"].get("before_start"), 200)
        self.assertEqual(db.q("SELECT COUNT(*) c FROM directpay_tickets")[0]["c"], 0)
        self.assertEqual(self.fired, [])

    def test_start_date_defaults_to_first_boot_and_is_persisted(self):
        self.assertIsNone(db.setting_get("start_date"))
        self.assertEqual(service.start_date(), NOW.date())
        self.assertEqual(db.setting_get("start_date"), "2026-09-10")
        # a later boot (different "today") must NOT move it
        host.wire({"now": lambda: NOW + datetime.timedelta(days=9)})
        self.assertEqual(service.start_date(), datetime.date(2026, 9, 10))

    def test_env_start_date_seeds_but_the_persisted_value_wins_after(self):
        os.environ["DIRECTPAY_START_DATE"] = "2026-09-01"
        self.assertEqual(service.start_date(), datetime.date(2026, 9, 1))
        os.environ["DIRECTPAY_START_DATE"] = "2026-08-01"
        self.assertEqual(service.start_date(), datetime.date(2026, 9, 1))

    def test_a_garbled_env_start_date_falls_back_to_today(self):
        os.environ["DIRECTPAY_START_DATE"] = "yesterday"
        self.assertEqual(service.start_date(), NOW.date())


class TestPerTickCap(Case):
    def test_cap_is_honoured_and_the_rest_waits(self):
        os.environ["DIRECTPAY_MAX_OPEN_PER_TICK"] = "5"
        batch = [res(i) for i in range(1, 13)]
        out = service.process_reservations(batch, now=NOW)
        self.assertEqual(len(out["opened"]), 5)
        self.assertEqual(out["waiting"], 7)
        self.assertEqual(len(self.fired), 5)
        self.assertEqual({p["kind"] for p in self.fired}, {"open"})
        out2 = service.process_reservations(batch, now=NOW)
        self.assertEqual(len(out2["opened"]), 5)
        self.assertEqual(out2["waiting"], 2)
        out3 = service.process_reservations(batch, now=NOW)
        self.assertEqual(len(out3["opened"]), 2)
        self.assertEqual(out3["waiting"], 0)
        self.assertEqual(db.q("SELECT COUNT(*) c FROM directpay_tickets")[0]["c"], 12)
        out4 = service.process_reservations(batch, now=NOW)
        self.assertEqual(out4["opened"], [])
        self.assertEqual(out4["skipped"].get("duplicate"), 12)

    def test_cap_zero_holds_everything(self):
        os.environ["DIRECTPAY_MAX_OPEN_PER_TICK"] = "0"
        out = service.process_reservations([res(1), res(2)], now=NOW)
        self.assertEqual(out["opened"], [])
        self.assertEqual(out["waiting"], 2)


class TestDryRun(Case):
    def test_dryrun_writes_the_ledger_but_fires_nothing(self):
        os.environ["DIRECTPAY_DRYRUN"] = "1"
        out = service.process_reservations([res(1), res(2)], now=NOW)
        self.assertEqual(len(out["opened"]), 2)
        self.assertEqual(self.fired, [])
        rows = db.q("SELECT dryrun, channel_id FROM directpay_tickets")
        self.assertEqual([r["dryrun"] for r in rows], [1, 1])
        self.assertEqual([r["channel_id"] for r in rows], [None, None])

    def test_rooms_are_backfilled_when_dryrun_is_switched_off(self):
        os.environ["DIRECTPAY_DRYRUN"] = "1"
        service.process_reservations([res(1), res(2)], now=NOW)
        os.environ["DIRECTPAY_DRYRUN"] = "0"
        os.environ["DIRECTPAY_MAX_OPEN_PER_TICK"] = "1"
        out = service.process_reservations([], now=NOW)
        self.assertEqual(len(self.fired), 1)
        self.assertEqual(out["backfilled"], 1)
        self.assertEqual(out["waiting"], 1)


class TestSyntheticRun(Case):
    """~30 fake reservations through the whole eligibility + ledger path; the exact set of
    ids that would open a room. This is the run printed in the owner report."""
    def test_exact_open_set(self):
        os.environ["DIRECTPAY_DRYRUN"] = "1"
        os.environ["DIRECTPAY_MAX_OPEN_PER_TICK"] = "50"
        batch = []
        chans = ["direct", "Airbnb", "", "Booking.com", "Manual", "Vrbo", "Website", "airbnb official",
                 "Owner Stay", "walk-in", "Direct", "Expedia"]
        for i in range(1, 25):
            batch.append(res(i, channel=chans[i % len(chans)]))
        batch.append(res(25, status="cancelled"))                        # cancelled → no
        batch.append(res(26, status="inquiry"))                          # inquiry → no
        batch.append(res(27, booked="2026-09-09 23:00:00"))              # before start → no
        batch.append(res(28, channel=""))                                # blank → yes (deliberate)
        batch.append(res(29, channel="Booking.com"))                     # other → no
        batch.append(res(2))                                             # duplicate id → one row
        out = service.process_reservations(batch, now=NOW)
        opened = sorted(int(t["reservation_id"]) for t in out["opened"])
        expect = sorted([i for i in range(1, 25) if finance_channel({"channelName": chans[i % len(chans)]}) == "direct"] + [28])
        self.assertEqual(opened, expect)
        self.assertEqual(expect, [2, 4, 6, 8, 9, 10, 12, 14, 16, 18, 20, 21, 22, 24, 28])
        self.assertEqual(db.q("SELECT COUNT(*) c FROM directpay_tickets")[0]["c"], len(expect))
        self.assertEqual(out["skipped"], {"not_direct": 11, "status": 2, "before_start": 1, "duplicate": 1})
        row = db.by_reservation("28")
        self.assertEqual(row["channel_raw"], "")                     # verbatim, printed on the card
        self.assertEqual(engine.raw_channel(batch[7]), "Owner Stay")


if __name__ == "__main__":
    unittest.main()
