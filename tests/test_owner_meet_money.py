# -*- coding: utf-8 -*-
"""M1 / M2 / M4 — the meeting's money IS the statement's money, to the halala.

Synthetic Hostaway rows go through the REAL statement path (`_owner_month_report` →
finance.owners → build_owner_report), with only `api_get` stubbed — the same harness as
tests/test_owner_perf_budget.py. Nothing in the money chain is mocked. Each period is checked
three ways: the snapshot's figure, the sum of the statement's own `owner_net`, and a figure worked
out by hand from the fixture's payouts, fee % and cleaning (the positive control — if the
statement path and the hand figure ever disagree, this test says which).

Run: python3 -m unittest tests.test_owner_meet_money
"""
import contextlib
import datetime
import io
import os
import shutil
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-ownermeet-money"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE
os.environ["RES_SPAN_ENABLED"] = "1"

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402
import owner_meet  # noqa: E402
from owner_meet import money, periods, snapshot  # noqa: E402

from brain import db as bdb  # noqa: E402

fapi.attach(bot)
bdb.set_db_path_for_tests(os.path.join(_STATE, "brain.db"))

OWNER = "مالك الاجتماع"
L1, L2 = 77, 78
TODAY = datetime.date(2026, 10, 6)
Q = Decimal("0.01")

# Per month: L1 earns 1000 + 1500, L2 earns 800. 20% management on both. L2's owner pays a
# 300 SAR monthly cleaning subscription; L1's cleaning is Ouja's.
PER_MONTH = {L1: Decimal("2500") - Decimal("500"),
             L2: Decimal("800") - Decimal("160") - Decimal("300")}


def _resv(rid, lid, payout, arrival):
    dep = (datetime.date.fromisoformat(arrival) + datetime.timedelta(days=2)).isoformat()
    return {"id": rid, "listingMapId": lid, "status": "new", "channelName": "Airbnb",
            "arrivalDate": arrival, "departureDate": dep, "nights": 2,
            "guestName": "G" + str(rid), "airbnbExpectedPayoutAmount": payout,
            "totalPrice": payout + 200, "refundAmount": None}


def _rows():
    rows, y, m = [], 2025, 1
    for i in range(22):
        mk = "%04d-%02d" % (y, m)
        rows.append(_resv("a%d" % i, L1, 1000.0, mk + "-05"))
        rows.append(_resv("b%d" % i, L1, 1500.0, mk + "-15"))
        rows.append(_resv("c%d" % i, L2, 800.0, mk + "-10"))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return rows


PEERS = list(range(901, 909))          # 8 other owners' 2-bedroom units — never shown to OUR owner


def _peer_rows():
    rows, y, m = [], 2025, 1
    for i in range(22):
        mk = "%04d-%02d" % (y, m)
        for k, lid in enumerate(PEERS):
            rows.append(_resv("p%d-%d" % (lid, i), lid, 400.0 + 150 * k, mk + "-%02d" % (3 + k)))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return rows


ALL_ROWS = _rows() + _peer_rows()


def _api(path, params=None, _retry=0):
    params = params or {}
    if path == "/reservations":
        lo = params.get("arrivalStartDate") or "0000-00-00"
        hi = params.get("arrivalEndDate") or "9999-99-99"
        sel = [r for r in ALL_ROWS if lo <= r["arrivalDate"][:10] <= hi]
        off, lim = int(params.get("offset") or 0), int(params.get("limit") or 200)
        return {"result": sel[off:off + lim]}
    return {"result": []}


class _Fixture(unittest.TestCase):
    def setUp(self):
        bdb.set_db_path_for_tests(os.path.join(_STATE, "brain.db"))   # other test modules move it
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("M1")] = {
            "apartment": "M1", "owner": OWNER, "mgmt_pct": 20.0, "lid": L1,
            "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_registry[bot._owner_key("M2")] = {
            "apartment": "M2", "owner": OWNER, "mgmt_pct": 20.0, "lid": L2,
            "cleaning": {"type": "owner", "amount": 300}}
        bot._owner_links.clear()
        bot._expenses.clear()
        self._orig = (bot.api_get, bot.get_listings_map)
        self._orig_ls = bot._ls_store
        ls = {str(L1): {"internal_name": "Ouja | M1", "bedrooms": 2, "active": True},
              str(L2): {"internal_name": "Ouja | M2", "bedrooms": 1, "active": True}}
        for lid in PEERS:
            ls[str(lid)] = {"internal_name": "Peer Unit %d" % lid, "bedrooms": 2, "active": True}
        bot._ls_store = {"listings": ls, "last_sync": None, "last_summary": {}}
        bot.get_listings_map = lambda: {L1: "Ouja | M1", L2: "Ouja | M2"}
        bot.api_get = _api
        self._clear()
        owner_meet.wire(bot._owner_meet_caps())

    def tearDown(self):
        bot.api_get, bot.get_listings_map = self._orig
        bot._ls_store = self._orig_ls
        self._clear()

    def _clear(self):
        bot._owner_portal_cache.clear()
        bot._res_window_cache.clear()
        bot._res_span_cache.clear()
        bot._res_window_degraded.clear()
        bot._owner_partial_cache.clear()
        bot._listings["map"] = {}
        bot._listings["ts"] = 0

    def _build(self, first, last, lids=()):
        p = periods.resolve("custom", TODAY, first_mkey=first, last_mkey=last)
        return p, snapshot.build({"owner": OWNER, "lids": list(lids), "period": p,
                                  "meeting_date": TODAY.isoformat()})

    @staticmethod
    def _d(x):
        return Decimal(str(x)).quantize(Q)


class M1OwnerNetToTheHalala(_Fixture):
    CASES = (("2026-08", "2026-08", 1), ("2026-06", "2026-08", 3), ("2025-09", "2026-08", 12))

    def test_whole_owner_equals_the_statement_and_the_hand_figure(self):
        for first, last, n in self.CASES:
            with self.subTest(months=n):
                p, snap = self._build(first, last)
                got = self._d(snap["owner"]["scope"]["money"]["total"]["owner_net"])
                stmt = sum((self._d(bot._owner_month_report(OWNER, m)["owner_net"]) for m in p["months"]),
                           Decimal(0))
                hand = (PER_MONTH[L1] + PER_MONTH[L2]) * n
                self.assertEqual(len(p["months"]), n)
                self.assertEqual(got, stmt, "meeting net must equal Σ statement owner_net")
                self.assertEqual(stmt, hand, "statement path disagrees with the hand-worked figure")
                self.assertTrue(snap["meta"]["whole_owner"])

    def test_one_unit_equals_its_unit_slice_and_the_hand_figure(self):
        for first, last, n in self.CASES:
            for lid in (L1, L2):
                with self.subTest(months=n, lid=lid):
                    p, snap = self._build(first, last, lids=[lid])
                    got = self._d(snap["owner"]["scope"]["money"]["total"]["owner_net"])
                    stmt = sum((self._d(OW.unit_slice(bot._owner_month_report(OWNER, m), lid)["owner_net"])
                                for m in p["months"]), Decimal(0))
                    self.assertEqual(got, stmt)
                    self.assertEqual(stmt, PER_MONTH[lid] * n)
                    self.assertFalse(snap["meta"]["whole_owner"])
                    self.assertEqual([u["lid"] for u in snap["owner"]["units"]], [lid],
                                     "a one-unit meeting carries no other unit")

    def test_per_unit_blocks_add_up_to_the_owner_here(self):
        _p, snap = self._build("2026-06", "2026-08")
        units = sum((self._d(u["money"]["total"]["owner_net"]) for u in snap["owner"]["units"]), Decimal(0))
        self.assertEqual(units, self._d(snap["owner"]["scope"]["money"]["total"]["owner_net"]))

    def test_waterfall_reconciles_and_shows_cleaning_only_where_the_owner_pays(self):
        _p, snap = self._build("2026-06", "2026-08")
        by = {u["lid"]: u for u in snap["owner"]["units"]}
        self.assertTrue(by[L1]["money"]["waterfall"]["reconciled"])
        self.assertTrue(by[L2]["money"]["waterfall"]["reconciled"])
        self.assertNotIn("cleaning", [r["key"] for r in by[L1]["money"]["waterfall"]["rows"]])
        self.assertIn("cleaning", [r["key"] for r in by[L2]["money"]["waterfall"]["rows"]])
        self.assertEqual(sum(by[L2]["money"]["per100"].values()), 100)

    def test_the_snapshot_survives_a_json_round_trip_exactly(self):
        from owner_meet import db
        _p, snap = self._build("2026-06", "2026-08")
        text = db.canonical(snap)
        import json
        again = json.loads(text)
        self.assertEqual(self._d(again["owner"]["scope"]["money"]["total"]["owner_net"]),
                         self._d(snap["owner"]["scope"]["money"]["total"]["owner_net"]))


class M2ManagementPctFromTerms(_Fixture):
    def test_the_label_follows_terms_on(self):
        _p, snap = self._build("2026-08", "2026-08", lids=[L2])
        self.assertEqual(snap["owner"]["units"][0]["mgmt_pct"], 20.0)
        bot._owner_registry[bot._owner_key("M2")]["mgmt_pct"] = 25.0
        OW._terms_cache["v"] = None
        self._clear()
        _p, snap = self._build("2026-08", "2026-08", lids=[L2])
        self.assertEqual(snap["owner"]["units"][0]["mgmt_pct"], 25.0)
        self.assertEqual(self._d(snap["owner"]["scope"]["money"]["total"]["owner_net"]),
                         Decimal("800") - Decimal("200") - Decimal("300"))

    def test_a_missing_pct_is_a_red_readiness_line(self):
        bot._owner_registry[bot._owner_key("M1")]["mgmt_pct"] = None
        OW._terms_cache["v"] = None
        _p, snap = self._build("2026-08", "2026-08", lids=[L1])
        reds = [c for c in snap["presenter"]["readiness"] if c["level"] == "red"]
        self.assertTrue(any(c["key"] == "mgmt_pct" for c in reds), snap["presenter"]["readiness"])
        self.assertFalse(money.can_send(snap)[0])


class M4DegradedBlocksSend(_Fixture):
    def test_a_degraded_reservation_pull_blocks_send(self):
        orig = owner_meet.HOST.reservations_window
        owner_meet.HOST.reservations_window = lambda s, e: (orig(s, e)[0], True)
        try:
            _p, snap = self._build("2026-08", "2026-08")
        finally:
            owner_meet.HOST.reservations_window = orig
        self.assertTrue(snap["meta"]["degraded"])
        ok, why = money.can_send(snap)
        self.assertFalse(ok)
        self.assertTrue(why)

    def test_a_degraded_month_statement_blocks_send(self):
        orig = owner_meet.HOST.month_report

        def degraded(owner, mk):
            rep = dict(orig(owner, mk))
            if mk == "2026-07":
                rep["degraded"] = True
            return rep
        owner_meet.HOST.month_report = degraded
        try:
            _p, snap = self._build("2026-06", "2026-08")
        finally:
            owner_meet.HOST.month_report = orig
        self.assertIn("2026-07", [c.get("month") for c in snap["presenter"]["readiness"] if c["key"] == "degraded"])
        self.assertFalse(money.can_send(snap)[0])

    def test_a_clean_build_can_send(self):
        _p, snap = self._build("2026-08", "2026-08")
        self.assertFalse(snap["meta"]["degraded"])
        reds = [c for c in snap["presenter"]["readiness"] if c["level"] == "red"]
        self.assertEqual(reds, [])
        self.assertTrue(money.can_send(snap)[0])


class PeersInsideARealBuild(_Fixture):
    """R1/R2 end to end: the owner half carries bands, never another unit's id, name or a count."""

    def test_bands_exist_and_nothing_about_other_units_leaks(self):
        import json
        _p, snap = self._build("2026-06", "2026-08", lids=[L1])
        u = snap["owner"]["units"][0]
        self.assertEqual(u["bedrooms"], 2)
        self.assertEqual(u["peers"]["income"]["scope"], "peers")
        self.assertEqual(set(u["peers"]["income"]), {"value", "p25", "p50", "p75", "pct10", "tone", "label", "scope"})
        self.assertIsNotNone(u["fair_share"])
        owner_text = json.dumps(snap["owner"], ensure_ascii=False)
        import re
        for lid in PEERS:
            self.assertIsNone(re.search("(?<![0-9.])%d(?![0-9])" % lid, owner_text), lid)
            self.assertNotIn("Peer Unit %d" % lid, owner_text)
        self.assertNotIn("Ouja | M2", owner_text, "a one-unit meeting never names the owner's other unit")
        self.assertNotIn("computed_at", owner_text)
        occ = u["peers"]["occupancy"]["value"]
        self.assertEqual(occ, round(occ, 4), "owner-facing ratios are rounded")
        self.assertEqual(snap["presenter"]["peer_internal"][L1]["income"]["n"], len(PEERS),
                         "the peer count lives in the presenter half only")

    def test_a_one_bedroom_unit_with_no_one_bedroom_peers_compares_with_the_portfolio(self):
        _p, snap = self._build("2026-06", "2026-08", lids=[L2])
        band = snap["owner"]["units"][0]["peers"]["income"]
        self.assertEqual(band["scope"], "portfolio")
        self.assertIn("شققنا", band["label"])


class RecordAndJobs(_Fixture):
    def test_a_build_saves_a_version_and_a_frozen_one_cannot_change(self):
        import sqlite3
        from owner_meet import db, jobs
        p = periods.resolve("custom", TODAY, first_mkey="2026-08", last_mkey="2026-08")
        mid = db.create_meeting(OWNER, [], p, TODAY.isoformat(), "test")
        ver = jobs.run(mid, {"owner": OWNER, "lids": [], "period": p, "meeting_date": TODAY.isoformat()})
        self.assertEqual(ver, 1)
        row = db.snapshot(mid)
        self.assertEqual(row["sha256"], db.sha256_of(row["json"]))
        self.assertEqual(db.meeting(mid)["state"], "ready")
        db.freeze(mid, 1)
        from brain import db as bdb
        from contextlib import closing
        with closing(bdb.connect()) as cx:
            with self.assertRaises(sqlite3.DatabaseError):
                cx.execute("UPDATE meet_snapshots SET json='{}' WHERE meeting_id=? AND version=1", (mid,))
            with self.assertRaises(sqlite3.DatabaseError):
                cx.execute("DELETE FROM meet_snapshots WHERE meeting_id=? AND version=1", (mid,))
        self.assertEqual(db.snapshot(mid, 1)["sha256"], row["sha256"])

    def test_one_failing_month_is_a_red_line_not_a_dead_build(self):
        orig = owner_meet.HOST.month_report

        def flaky(owner, mk):
            if mk == "2026-07":
                raise RuntimeError("hostaway down")
            return orig(owner, mk)
        owner_meet.HOST.month_report = flaky
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:     # the builder logs the failed month
                _p, snap = self._build("2026-06", "2026-08")
            self.assertIn("2026-07", out.getvalue())
        finally:
            owner_meet.HOST.month_report = orig
        miss = [c for c in snap["presenter"]["readiness"] if c["key"] == "missing_month"]
        self.assertEqual([c["month"] for c in miss], ["2026-07"])
        self.assertFalse(money.can_send(snap)[0])

    def test_a_stale_month_is_a_yellow_line(self):
        orig = owner_meet.HOST.month_report
        owner_meet.HOST.month_report = lambda o, mk: dict(orig(o, mk), stale=True)
        try:
            _p, snap = self._build("2026-08", "2026-08")
        finally:
            owner_meet.HOST.month_report = orig
        self.assertIn("stale", [c["key"] for c in snap["presenter"]["readiness"] if c["level"] == "yellow"])

    def test_a_build_interrupted_by_a_restart_is_failed_at_boot(self):
        from owner_meet import db
        p = periods.resolve("custom", TODAY, first_mkey="2026-08", last_mkey="2026-08")
        mid = db.create_meeting(OWNER, [], p, TODAY.isoformat(), "test")
        db.set_build(mid, state="building", progress=40)
        owner_meet.bootstrap()
        m = db.meeting(mid)
        self.assertEqual(m["state"], "error")
        self.assertIn("إعادة تشغيل", m["build_error"])

    def test_a_bad_owner_records_an_arabic_error_not_a_crash(self):
        from owner_meet import db, jobs
        p = periods.resolve("custom", TODAY, first_mkey="2026-08", last_mkey="2026-08")
        mid = db.create_meeting("مالك غير موجود", [], p, TODAY.isoformat(), "test")
        self.assertIsNone(jobs.run(mid, {"owner": "مالك غير موجود", "lids": [], "period": p,
                                         "meeting_date": TODAY.isoformat()}))
        m = db.meeting(mid)
        self.assertEqual(m["state"], "error")
        self.assertIn("ما لقينا", m["build_error"])


if __name__ == "__main__":
    unittest.main()
