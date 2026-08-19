# -*- coding: utf-8 -*-
"""
S14 + S15 — the switch that changes what a guest sees, and the licence store.

THE POINT OF THESE TESTS: a warning beside a working button is a button that gets
pressed. The refusal has to be in code.

Run: python3 -m unittest tests.test_monthly_switch
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                              # noqa: E402
from monthly import db, host, live, settings             # noqa: E402


class _Connected(object):
    """The guest-site connection is OFF by default since the outage. Tests that
    exercise the wiring turn it on for their own duration, so the disconnect
    stays the thing you have to opt out of rather than the thing you forget."""

    def __enter__(self):
        self._prev = live.CONNECTED_TO_GUEST_SITE
        live.CONNECTED_TO_GUEST_SITE = True

    def __exit__(self, *_a):
        live.CONNECTED_TO_GUEST_SITE = self._prev
        return False


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="monthly_switch_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_for_tests()
        self.store = {}
        host.HOST.load_json = lambda name, default=None: self.store.get(name, default)
        host.HOST.save_json = lambda name, obj: self.store.__setitem__(name, obj)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        host.HOST.load_json = None
        host.HOST.save_json = None


class ShipsOnButOnlyWhereMeasuredTest(_Base):
    """Owner decision, 2026-08-19: ship engine_verified ON. Renamed from
    ShipsOffTest with the behaviour it now describes, rather than left asserting
    a default that is no longer the intent. Safe to ship on because the mode
    cannot publish a pooled average — the guarantee is in live.engine_after, not
    in the choice of default."""

    def test_the_switch_ships_as_discount_after_the_outage(self):
        """Reverted 2026-08-19: engine_verified was shipped on and the guest site
        became unreachable. The mode is still correct and still selectable; it
        just no longer reaches a customer-facing page."""
        self.assertEqual(settings.price_source(), "discount")

    def test_the_guest_site_hook_is_off(self):
        self.assertFalse(live.CONNECTED_TO_GUEST_SITE)

    def test_nothing_reaches_the_guest_path_while_it_is_disconnected(self):
        settings.set_price_source("engine_verified", coverage=0.9)
        import monthly.collect as collect
        collect._CACHE["2026-10"] = {"at": collect._now_ts(), "unit_meta": {1: {}}}
        real = collect.price_one
        collect.price_one = lambda lid, month, **k: {"price": 15000,
                                                     "basis": "own_history"}
        try:
            self.assertIsNone(live.engine_after(
                1, "2026-10", 20000, 1,
                {"before": 20000, "after": 16000, "saved": 4000, "pct": 0.2,
                 "ceiling": 0.3, "per_month_before": 20000,
                 "per_month_after": 16000, "promo": False, "promo_label": ""}))
        finally:
            collect.price_one = real
            collect._CACHE.clear()

    def test_the_shipped_mode_can_never_publish_a_pooled_number(self):
        """The property that makes shipping it on defensible."""
        import monthly.collect as collect
        real = collect.price_one
        collect.price_one = lambda lid, month, **k: {"price": 15000,
                                                     "basis": "district_pool"}
        try:
            self.assertIsNone(live.engine_after(
                1, "2026-10", 20000, 1,
                {"before": 20000, "after": 16000, "saved": 4000, "pct": 0.2,
                 "ceiling": 0.3, "per_month_before": 20000,
                 "per_month_after": 16000, "promo": False, "promo_label": ""}))
        finally:
            collect.price_one = real

    def test_an_unreadable_settings_file_falls_back_to_the_shipped_default(self):
        host.HOST.load_json = lambda *_a, **_k: (_ for _ in ()).throw(IOError("gone"))
        self.assertEqual(settings.price_source(), "discount")

    def test_a_corrupt_value_falls_back_to_discount(self):
        self.store[settings.FILE] = {"price_source": "whatever"}
        self.assertEqual(settings.price_source(), "discount")


class RefusalIsInCodeTest(_Base):
    def test_flipping_to_engine_below_the_threshold_is_refused(self):
        settings.set_price_source("discount", coverage=0.31)
        with self.assertRaises(settings.FlipRefused) as cm:
            settings.set_price_source("engine", coverage=0.31, actor="faisal")
        self.assertIn("31%", str(cm.exception))
        self.assertIn("60%", str(cm.exception))
        self.assertEqual(settings.price_source(), "discount")

    def test_todays_real_coverage_is_refused(self):
        for cov in (0.26, 0.31, 0.53):
            with self.assertRaises(settings.FlipRefused):
                settings.set_price_source("engine", coverage=cov)

    def test_unknown_coverage_is_refused_rather_than_assumed_fine(self):
        with self.assertRaises(settings.FlipRefused):
            settings.set_price_source("engine", coverage=None)

    def test_above_the_threshold_it_flips(self):
        settings.set_price_source("engine", coverage=0.72, actor="faisal")
        self.assertEqual(settings.price_source(), "engine")

    def test_the_override_needs_a_typed_reason(self):
        settings.set_price_source("discount", coverage=0.31)
        with self.assertRaises(settings.FlipRefused) as cm:
            settings.set_price_source("engine", coverage=0.31, override=True, reason="")
        self.assertIn("سبب", str(cm.exception))
        self.assertEqual(settings.price_source(), "discount")

    def test_an_override_with_a_reason_is_allowed_and_recorded(self):
        settings.set_price_source("engine", coverage=0.31, override=True,
                                  reason="اختبار مع مالك واحد", actor="faisal")
        cur = settings.load()
        self.assertEqual(cur["price_source"], "engine")
        self.assertTrue(cur["price_source_overridden"])
        self.assertEqual(cur["price_source_actor"], "faisal")
        self.assertEqual(cur["price_source_coverage_at_flip"], 0.31)

    def test_going_back_to_discount_is_never_refused(self):
        settings.set_price_source("engine", coverage=0.9)
        settings.set_price_source("discount", coverage=0.1)
        self.assertEqual(settings.price_source(), "discount")


class FlipStateTest(_Base):
    def test_it_carries_the_number_that_says_not_to_flip(self):
        st = settings.flip_state(0.31)
        self.assertEqual(st["coverage_pct"], 31)
        self.assertEqual(st["min_pct"], 60)
        self.assertFalse(st["may_flip"])
        self.assertTrue(st["needs_override"])
        self.assertIn("60%", st["criterion_ar"])


class LiveContractTest(_Base):
    """monthly_pricing returns exactly nine keys and the whole guest site reads
    them. The engine path must return the same shape or the switch touches
    everything instead of one function."""

    NINE = ("before", "after", "saved", "pct", "ceiling", "per_month_before",
            "per_month_after", "promo", "promo_label")

    def _discount(self):
        return {"before": 20000, "after": 16000, "saved": 4000, "pct": 0.2,
                "ceiling": 0.3, "per_month_before": 20000,
                "per_month_after": 16000, "promo": False, "promo_label": ""}

    def test_while_the_switch_is_off_the_engine_path_never_runs(self):
        self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))

    def test_the_engine_path_returns_the_same_nine_keys(self):
        settings.set_price_source("engine", coverage=0.9)
        import monthly.collect as collect
        real = collect.price_one
        collect._CACHE["2026-10"] = {"at": collect._now_ts(), "unit_meta": {1: {}}}
        collect.price_one = lambda lid, month, **k: {"price": 15000}
        try:
            with _Connected():
                out = live.engine_after(1, "2026-10", 20000, 1, self._discount())
        finally:
            collect.price_one = real
            collect._CACHE.clear()
        self.assertIsNotNone(out)
        self.assertEqual(set(out), set(self.NINE))
        for k in ("before", "after", "saved", "per_month_before", "per_month_after"):
            self.assertIsInstance(out[k], int)
        self.assertEqual(out["after"], 15000)
        self.assertEqual(out["saved"], 5000)

    def test_it_refuses_to_make_the_monthly_offer_more_expensive(self):
        """A monthly offer that costs more than booking the nights outright is
        not an offer, and the live site is where being wrong is public."""
        settings.set_price_source("engine", coverage=0.9)
        import monthly.collect as collect
        real = collect.price_one
        collect._CACHE["2026-10"] = {"at": collect._now_ts(), "unit_meta": {1: {}}}
        collect.price_one = lambda lid, month, **k: {"price": 25000}
        try:
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            collect.price_one = real
            collect._CACHE.clear()

    def test_any_exception_falls_back_to_the_discount_path(self):
        settings.set_price_source("engine", coverage=0.9)
        import monthly.collect as collect
        real = collect.price_one

        def boom(*_a, **_k):
            raise RuntimeError("hostaway down")

        collect.price_one = boom
        try:
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            collect.price_one = real

    def test_no_engine_price_falls_back(self):
        settings.set_price_source("engine", coverage=0.9)
        import monthly.collect as collect
        real = collect.price_one
        collect.price_one = lambda lid, month, **k: {"price": None}
        try:
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            collect.price_one = real


class LicenceTest(_Base):
    def test_the_filter_ships_off(self):
        self.assertFalse(settings.load()["licence_filter_on"])
        self.assertEqual(settings.load()["licence_filter_due"], "2026-09-30")

    def test_a_unit_with_no_licence_is_not_ok(self):
        self.assertFalse(db.licence_ok(123))

    def test_a_number_without_a_date_is_not_ok(self):
        db.licence_set(123, "AD-1", "", entered_by="faisal")
        self.assertFalse(db.licence_ok(123))

    def test_an_expired_licence_is_not_ok(self):
        db.licence_set(123, "AD-1", "2026-01-01")
        self.assertFalse(db.licence_ok(123, today="2026-08-19"))

    def test_a_current_licence_is_ok(self):
        db.licence_set(123, "AD-1", "2027-01-01")
        self.assertTrue(db.licence_ok(123, today="2026-08-19"))

    def test_expiring_within_14_days_is_flagged_separately_from_expired(self):
        db.licence_set(1, "A", "2026-08-25")     # 6 days out
        db.licence_set(2, "B", "2026-07-01")     # gone
        db.licence_set(3, "C", "2027-06-01")     # fine
        db.licence_set(4, None, None)            # never entered
        rep = db.licences_expiring(14, today="2026-08-19")
        self.assertEqual([r["unit_id"] for r in rep["expiring"]], [1])
        self.assertEqual([r["unit_id"] for r in rep["expired"]], [2])
        self.assertEqual([r["unit_id"] for r in rep["missing"]], [4])

    def test_entry_is_idempotent_and_keeps_the_actor(self):
        db.licence_set(9, "AD-9", "2027-01-01", entered_by="faisal")
        db.licence_set(9, "AD-9b", "2027-02-01", entered_by="faisal")
        self.assertEqual(len(db.licence_all()), 1)
        self.assertEqual(db.licence_get(9)["licence_no"], "AD-9b")
        self.assertEqual(db.licence_get(9)["entered_by"], "faisal")


if __name__ == "__main__":
    unittest.main()


class VerifiedOnlyModeTest(_Base):
    """The middle setting. All-or-nothing was the defect: it forced a choice
    between publishing pooled averages for the whole portfolio and publishing
    nothing, when a third of the units already have real per-unit numbers."""

    def _discount(self):
        return {"before": 20000, "after": 16000, "saved": 4000, "pct": 0.2,
                "ceiling": 0.3, "per_month_before": 20000,
                "per_month_after": 16000, "promo": False, "promo_label": ""}

    def _with_basis(self, basis, price=15000):
        """Warms the cache as well as stubbing the price: the guest path is now
        cache-only, so a stub without a warm month is correctly ignored."""
        import monthly.collect as collect
        real = collect.price_one
        collect._CACHE["2026-10"] = {"at": collect._now_ts(), "unit_meta": {1: {}}}
        collect.price_one = lambda lid, month, **k: {"price": price, "basis": basis}
        return real, collect

    def test_verified_needs_no_coverage_gate(self):
        """Its guarantee is in the code, not in a threshold — so at 26% coverage
        it is still allowed, because it cannot publish a pooled number."""
        settings.set_price_source("engine_verified", coverage=0.26, actor="faisal")
        self.assertEqual(settings.price_source(), "engine_verified")

    def test_full_engine_is_still_gated_at_the_same_threshold(self):
        with self.assertRaises(settings.FlipRefused):
            settings.set_price_source("engine", coverage=0.26)

    def test_the_refusal_now_points_at_the_middle_option(self):
        with self.assertRaises(settings.FlipRefused) as cm:
            settings.set_price_source("engine", coverage=0.26)
        # «للمقيسة» — the alef of «ال» elides after the ل, exactly as it does
        # in «للمالك». Same trap, second time this session.
        self.assertIn("للمقيسة فقط", str(cm.exception))

    def test_a_unit_with_its_own_history_gets_the_engine_price(self):
        settings.set_price_source("engine_verified", coverage=0.26)
        real, collect = self._with_basis("own_history")
        try:
            with _Connected():
                out = live.engine_after(1, "2026-10", 20000, 1, self._discount())
        finally:
            collect.price_one = real
            collect._CACHE.clear()
        self.assertIsNotNone(out)
        self.assertEqual(out["after"], 15000)

    def test_a_pool_priced_unit_keeps_the_discount_path(self):
        settings.set_price_source("engine_verified", coverage=0.26)
        for basis in ("district_pool", "bedroom_pool", "insufficient"):
            real, collect = self._with_basis(basis)
            try:
                self.assertIsNone(
                    live.engine_after(1, "2026-10", 20000, 1, self._discount()),
                    "%s must never reach the guest site under engine_verified" % basis)
            finally:
                collect.price_one = real

    def test_full_engine_mode_does_publish_pooled_units(self):
        """The difference between the two modes, stated as a test."""
        settings.set_price_source("engine", coverage=0.9)
        real, collect = self._with_basis("district_pool")
        try:
            with _Connected():
                self.assertIsNotNone(
                    live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            collect.price_one = real

    def test_discount_mode_ignores_the_engine_entirely(self):
        settings.set_price_source("discount", coverage=0.9)
        real, collect = self._with_basis("own_history")
        try:
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            collect.price_one = real


class GuestPathNeverBlocksTest(_Base):
    """A guest page must never wait on Hostaway. price_one pulls years of
    reservation history and paginates the listings API; putting that in front of
    a customer looking at apartments is how a pricing feature takes down a
    storefront."""

    def _discount(self):
        return {"before": 20000, "after": 16000, "saved": 4000, "pct": 0.2,
                "ceiling": 0.3, "per_month_before": 20000,
                "per_month_after": 16000, "promo": False, "promo_label": ""}

    def test_a_cold_cache_falls_back_instead_of_computing(self):
        import monthly.collect as collect
        collect._CACHE.clear()
        called = []
        real = collect.month_state
        collect.month_state = lambda *a, **k: called.append(1) or (_ for _ in ()).throw(
            AssertionError("the guest path computed a month state"))
        try:
            settings.set_price_source("engine_verified", coverage=0.9)
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            collect.month_state = real
        self.assertEqual(called, [])

    def test_a_warm_cache_serves_the_price(self):
        import monthly.collect as collect
        settings.set_price_source("engine_verified", coverage=0.9)
        collect._CACHE["2026-10"] = {"at": collect._now_ts(), "unit_meta": {1: {}}}
        real = collect.price_one
        collect.price_one = lambda lid, month, **k: {"price": 15000,
                                                     "basis": "own_history"}
        try:
            with _Connected():
                out = live.engine_after(1, "2026-10", 20000, 1, self._discount())
        finally:
            collect.price_one = real
            collect._CACHE.clear()
        self.assertIsNotNone(out)
        self.assertEqual(out["after"], 15000)

    def test_an_expired_cache_is_treated_as_cold(self):
        import monthly.collect as collect
        settings.set_price_source("engine_verified", coverage=0.9)
        collect._CACHE["2026-10"] = {"at": collect._now_ts() - collect._CACHE_TTL - 5,
                                     "unit_meta": {1: {}}}
        try:
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            collect._CACHE.clear()

    def test_a_unit_absent_from_the_cached_month_falls_back(self):
        import monthly.collect as collect
        settings.set_price_source("engine_verified", coverage=0.9)
        collect._CACHE["2026-10"] = {"at": collect._now_ts(), "unit_meta": {999: {}}}
        try:
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            collect._CACHE.clear()
