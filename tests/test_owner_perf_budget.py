# -*- coding: utf-8 -*-
"""Owner-section performance budget — the gates from the Owners speed work.

The complaint this locks down: the owner profile page fanned out to ~15 distinct
month reports, each its own paginated Hostaway pull (~60 calls), against a global
ceiling of 11 calls / 10s. That is minutes of pure throttle wait for one screen.

G4 — cold profile costs <= 10 Hostaway calls (was ~60).
G5 — warm profile costs 0.
Both assert the NETS ARE UNCHANGED against the same synthetic data, because a fast
wrong number is worse than a slow right one.

Run: python3 -m unittest tests.test_owner_perf_budget -v
"""
import os
import shutil
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-perfbudget"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE
os.environ["RES_SPAN_ENABLED"] = "1"      # force the span layer on: no creds in tests

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

LID = 77
OWNER = "مالك الأداء"


def _resv(rid, payout, arrival):
    """One synthetic Airbnb reservation, shaped like a real Hostaway row."""
    return {"id": rid, "listingMapId": LID, "status": "new", "channelName": "Airbnb",
            "arrivalDate": arrival, "departureDate": arrival[:8] + "28", "nights": 2,
            "guestName": "G" + str(rid), "airbnbExpectedPayoutAmount": payout,
            "totalPrice": payout + 200, "refundAmount": None}


def _synthetic_rows():
    """Two bookings a month across a 20-month span — wide enough that the 12-month
    grid and its 3-month look-back are all inside one span pull."""
    rows = []
    y, m = 2025, 1
    for i in range(30):
        mk = "%04d-%02d" % (y, m)
        rows.append(_resv("r%d-a" % i, 1000.0, mk + "-05"))
        rows.append(_resv("r%d-b" % i, 1500.0, mk + "-15"))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return rows


ALL_ROWS = _synthetic_rows()


class _Counter(object):
    """Counting stub for bot.api_get. Serves /reservations from ALL_ROWS, honouring
    the same arrivalStartDate/arrivalEndDate/limit/offset contract the real API has,
    so paging behaves the way production paging does."""

    def __init__(self):
        self.calls = 0
        self.paths = []

    def __call__(self, path, params=None, _retry=0):
        self.calls += 1
        self.paths.append(path)
        params = params or {}
        if path == "/reservations":
            lo = params.get("arrivalStartDate") or "0000-00-00"
            hi = params.get("arrivalEndDate") or "9999-99-99"
            sel = [r for r in ALL_ROWS if lo <= r["arrivalDate"][:10] <= hi]
            off = int(params.get("offset") or 0)
            lim = int(params.get("limit") or 200)
            return {"result": sel[off:off + lim]}
        return {"result": []}


class _OwnerFixture(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("P1")] = {
            "apartment": "P1", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_links.clear()
        bot._expenses.clear()
        self._orig_api = bot.api_get
        self._orig_listings = bot.get_listings_map
        bot.get_listings_map = lambda: {LID: "Ouja | P1"}
        self.counter = _Counter()
        bot.api_get = self.counter
        self._clear_caches()

    def tearDown(self):
        bot.api_get = self._orig_api
        bot.get_listings_map = self._orig_listings
        self._clear_caches()
        bot._owner_links.clear()

    def _clear_caches(self):
        bot._owner_portal_cache.clear()
        bot._res_window_cache.clear()
        bot._res_span_cache.clear()
        bot._res_window_degraded.clear()
        bot._owner_partial_cache.clear()
        bot._listings["map"] = {}
        bot._listings["ts"] = 0


class OwnerPerfBudgetTest(_OwnerFixture):
    # ---- G4 ----------------------------------------------------------------
    def test_g4_cold_profile_stays_within_ten_hostaway_calls(self):
        d = OW.owner_profile(OWNER)
        self.assertTrue(d.get("ok"), d)
        self.assertEqual(len(d["months"]), 12, "the grid must still be 12 months")
        self.assertLessEqual(
            self.counter.calls, 10,
            "cold owner profile made %d Hostaway calls (budget 10); paths=%r"
            % (self.counter.calls, self.counter.paths))

    # ---- G5 ----------------------------------------------------------------
    def test_g5_warm_profile_makes_no_hostaway_calls(self):
        OW.owner_profile(OWNER)
        before = self.counter.calls
        d2 = OW.owner_profile(OWNER)
        self.assertTrue(d2.get("ok"), d2)
        self.assertEqual(self.counter.calls - before, 0,
                         "warm owner profile must not touch Hostaway")

    # ---- the numbers must not move -----------------------------------------
    def test_nets_are_identical_with_and_without_the_span_layer(self):
        """The whole point: the span pull must return exactly what per-month pulls
        returned. Same synthetic data, span ON vs span OFF -> identical nets."""
        d_span = OW.owner_profile(OWNER)
        nets_span = [(m["m"], m["net"]) for m in d_span["months"]]

        os.environ["RES_SPAN_ENABLED"] = "0"
        try:
            self._clear_caches()
            d_plain = OW.owner_profile(OWNER)
            nets_plain = [(m["m"], m["net"]) for m in d_plain["months"]]
        finally:
            os.environ["RES_SPAN_ENABLED"] = "1"

        self.assertEqual(nets_span, nets_plain,
                         "span slicing changed the numbers — that is a correctness bug")
        self.assertTrue(any(n for _, n in nets_span), "fixture produced no income at all")


class AnomalyEquivalenceTest(_OwnerFixture):
    """§4.2 — deriving the 3-month average from the grid must produce EXACTLY the
    anomalies the old per-month _owner_month_report lookups produced."""

    def test_derived_prior_nets_match_the_per_month_lookup(self):
        OW.owner_profile(OWNER)          # warm every month report
        mk = "2026-06"
        rep = bot._owner_month_report(OWNER, mk)
        self.assertIsNotNone(rep)

        old_path = OW.owner_anomalies(OWNER, mk, rep)                 # prior_nets=None
        priors = []
        for pm in OW._prev_months(mk, 3):
            pr = bot._owner_month_report(OWNER, pm)
            if pr is not None and pr.get("owner_net") is not None:
                priors.append(float(pr["owner_net"]))
        new_path = OW.owner_anomalies(OWNER, mk, rep, prior_nets=priors)
        self.assertEqual(old_path, new_path,
                         "derived 3-month average changed the anomaly output")

    def test_deviation_still_fires_when_it_should(self):
        """Positive control: a net far from its 3-month average must still flag,
        or this whole check has been silently disabled."""
        rep = {"owner_net": 100.0, "apartments": [], "excluded_summary": {}}
        flagged = OW.owner_anomalies(OWNER, "2026-06", rep,
                                     prior_nets=[3000.0, 3000.0, 3000.0])
        self.assertIn("net_deviation", {a["key"] for a in flagged})

    def test_no_priors_means_no_deviation_check(self):
        rep = {"owner_net": 100.0, "apartments": [], "excluded_summary": {}}
        quiet = OW.owner_anomalies(OWNER, "2026-06", rep, prior_nets=[])
        self.assertNotIn("net_deviation", {a["key"] for a in quiet})


class SingleFlightTest(_OwnerFixture):
    """G6 — five simultaneous openers must cost ONE compute, not five.

    This is what makes «حاول مرة ثانية» safe: before it, pressing retry while the
    first computation was still running started a second identical one beside it."""

    def test_five_concurrent_profile_loads_compute_once(self):
        real = OW._owner_profile_compute
        computes = []
        lock = threading.Lock()

        def slow(owner):
            with lock:
                computes.append(owner)
            time.sleep(0.2)
            return real(owner)
        OW._owner_profile_compute = slow
        try:
            results = [None] * 5
            errors = []

            def run(i):
                try:
                    results[i] = OW.owner_profile(OWNER)
                except Exception as e:      # pragma: no cover
                    errors.append(e)

            threads = [threading.Thread(target=run, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
        finally:
            OW._owner_profile_compute = real

        self.assertEqual(errors, [], "a waiter blew up")
        self.assertEqual(len(computes), 1,
                         "expected exactly ONE underlying compute, got %d" % len(computes))
        nets = [[(m["m"], m["net"]) for m in r["months"]] for r in results]
        for n in nets[1:]:
            self.assertEqual(n, nets[0], "waiters got different numbers from the leader")

    def test_a_failing_leader_propagates_to_every_waiter(self):
        """An exception must reach all five, not just the leader — otherwise four
        callers silently receive None and render an empty page."""
        boom = RuntimeError("hostaway down")

        def explode(owner):
            time.sleep(0.15)
            raise boom
        real = OW._owner_profile_compute
        OW._owner_profile_compute = explode
        try:
            seen = []

            def run():
                try:
                    OW.owner_profile(OWNER)
                    seen.append("no-error")
                except RuntimeError as e:
                    seen.append(str(e))
            threads = [threading.Thread(target=run) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
        finally:
            OW._owner_profile_compute = real
        self.assertEqual(seen, ["hostaway down"] * 5,
                         "the leader's failure did not reach every waiter: %r" % seen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
