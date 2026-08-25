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


class _Engine(object):
    """Stub the PRECOMPUTED price the host hands over.

    Reconnected 2026-08-24 on a different mechanism, so these tests changed with
    it. The old ones stubbed collect.price_one and warmed collect._CACHE, because
    the guest path used to compute inside the request — which is what took the
    site down. There is nothing to warm now: bot.py precomputes on a background
    loop and wires the answer in as HOST.engine_price. Tests that still poked at
    collect would be testing a path the guest can no longer reach."""

    def __init__(self, price=15000, basis="own_history"):
        self.payload = None if price is None else {"price": price, "basis": basis}

    def __enter__(self):
        self._prev = host.HOST.engine_price
        host.HOST.engine_price = lambda lid, month: self.payload
        return self

    def __exit__(self, *_a):
        host.HOST.engine_price = self._prev
        return False


class _NoEngine(object):
    """No precomputed price at all — the loop has not run yet, or this unit has
    no price. The guest must get the discount path and never a blank."""

    def __enter__(self):
        self._prev = host.HOST.engine_price
        host.HOST.engine_price = lambda lid, month: None

    def __exit__(self, *_a):
        host.HOST.engine_price = self._prev
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
        host.HOST.engine_price = None


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

    def test_the_guest_site_hook_is_on(self):
        """Reconnected 2026-08-24. What makes this safe is not the flag but the
        next two tests: the path cannot compute and cannot open a database."""
        self.assertTrue(live.CONNECTED_TO_GUEST_SITE)

    def test_the_guest_path_no_longer_imports_collect_at_all(self):
        """The regression that caused the outage, stated as a property of the file.
        collect is the module that opens brain.db; live must not reach it. Comments
        may name it — that is how the reason survives — so this reads the code."""
        import ast
        import inspect
        tree = ast.parse(inspect.getsource(live))
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                used.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                used.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                used.add(node.value.id)
        self.assertNotIn("collect", used,
                         "live.py must not reach collect — that is the outage path")
        self.assertNotIn("db", used, "nor the database directly")

    def test_without_a_wired_lookup_nothing_is_published(self):
        """Not wired means not connected, silently — never a crash on a guest page."""
        settings.set_price_source("engine_verified", coverage=0.9)
        host.HOST.engine_price = None
        self.assertIsNone(live.engine_after(
            1, "2026-10", 20000, 1,
            {"before": 20000, "after": 16000, "saved": 4000, "pct": 0.2,
             "ceiling": 0.3, "per_month_before": 20000,
             "per_month_after": 16000, "promo": False, "promo_label": ""}))

    def test_the_shipped_mode_can_never_publish_a_pooled_number(self):
        """The property that makes shipping it on defensible."""
        settings.set_price_source("engine_verified", coverage=0.9)
        with _Engine(price=15000, basis="district_pool"):
            self.assertIsNone(live.engine_after(
                1, "2026-10", 20000, 1,
                {"before": 20000, "after": 16000, "saved": 4000, "pct": 0.2,
                 "ceiling": 0.3, "per_month_before": 20000,
                 "per_month_after": 16000, "promo": False, "promo_label": ""}))

    def test_an_unreadable_settings_file_falls_back_to_the_shipped_default(self):
        host.HOST.load_json = lambda *_a, **_k: (_ for _ in ()).throw(IOError("gone"))
        self.assertEqual(settings.price_source(), "discount")

    def test_a_corrupt_value_falls_back_to_discount(self):
        self.store[settings.FILE] = {"price_source": "whatever"}
        self.assertEqual(settings.price_source(), "discount")


class OwnerFlipTest(_Base):
    """The 2026-08-25 flip to engine_verified, asked for in the owner's own words.

    A script writing a value into a settings file has no author and no reason, which
    is exactly what set_price_source refuses from a human. So this records both — and
    runs ONCE, because a flip that reasserts itself every boot is not a default, it is
    an argument with the owner that the owner cannot win."""

    def test_it_flips_the_switch_and_records_who_and_why(self):
        self.assertEqual(settings.price_source(), "discount")
        self.assertEqual(settings.apply_owner_flip(), "flipped")
        self.assertEqual(settings.price_source(), "engine_verified")
        cur = settings.load()
        self.assertTrue(cur["price_source_reason"], "a flip with no reason is a mystery")
        self.assertIn("owner", cur["price_source_actor"])
        self.assertTrue(cur["price_source_at"])

    def test_it_runs_once(self):
        settings.apply_owner_flip()
        self.assertEqual(settings.apply_owner_flip(), "already-applied")

    def test_the_owner_changing_it_back_is_permanent(self):
        """The whole point of the marker. If the owner looks at engine prices and
        wants the discount back, one click must hold — through every later boot."""
        settings.apply_owner_flip()
        settings.set_price_source("discount", coverage=0.9, actor="faisal",
                                  reason="رجعوها")
        self.assertEqual(settings.apply_owner_flip(), "already-applied")
        self.assertEqual(settings.price_source(), "discount",
                         "boot must never overrule a human's choice")

    def test_it_never_raises_even_if_state_is_unreadable(self):
        host.HOST.load_json = lambda *_a, **_k: (_ for _ in ()).throw(IOError("gone"))
        host.HOST.save_json = lambda *_a, **_k: (_ for _ in ()).throw(IOError("gone"))
        self.assertEqual(settings.apply_owner_flip(), "error")


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
        with _Engine():
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))

    def test_the_engine_path_returns_the_same_nine_keys(self):
        settings.set_price_source("engine", coverage=0.9)
        with _Engine(price=15000, basis=None):
            out = live.engine_after(1, "2026-10", 20000, 1, self._discount())
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
        with _Engine(price=25000):
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))

    def test_any_exception_falls_back_to_the_discount_path(self):
        settings.set_price_source("engine", coverage=0.9)

        def boom(*_a, **_k):
            raise RuntimeError("anything at all")

        prev = host.HOST.engine_price
        host.HOST.engine_price = boom
        try:
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))
        finally:
            host.HOST.engine_price = prev

    def test_no_engine_price_falls_back(self):
        settings.set_price_source("engine", coverage=0.9)
        with _Engine(price=None):
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))


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
        with _Engine(basis="own_history"):
            out = live.engine_after(1, "2026-10", 20000, 1, self._discount())
        self.assertIsNotNone(out)
        self.assertEqual(out["after"], 15000)

    def test_a_pool_priced_unit_keeps_the_discount_path(self):
        settings.set_price_source("engine_verified", coverage=0.26)
        for basis in ("district_pool", "bedroom_pool", "portfolio_pool",
                      "insufficient"):
            with _Engine(basis=basis):
                self.assertIsNone(
                    live.engine_after(1, "2026-10", 20000, 1, self._discount()),
                    "%s must never reach the guest site under engine_verified" % basis)

    def test_the_units_own_history_publishes_whichever_months_it_came_from(self):
        """own_recent and own_seasonal are the APARTMENT'S OWN record from its other
        months. They were refused as if they were pool averages, which left 39 of 60
        apartments on the old price after the owner turned the engine on — 3 of 20
        rows moved and the rest looked untouched."""
        settings.set_price_source("engine_verified", coverage=0.26)
        for basis in ("own_history", "own_recent", "own_seasonal"):
            with _Engine(basis=basis):
                out = live.engine_after(1, "2026-10", 20000, 1, self._discount())
            self.assertIsNotNone(out, "%s is the unit's own record, not an average"
                                 % basis)
            self.assertEqual(out["after"], 15000)

    def test_the_publisher_and_the_coverage_report_cannot_drift_apart(self):
        """Both now read engine.OWN_BASES. The bug was two hand-kept copies of one
        list, in two files, quietly disagreeing about what "its own history" means."""
        from monthly import engine
        self.assertEqual(engine.OWN_BASES,
                         ("own_history", "own_recent", "own_seasonal"))
        import inspect
        self.assertIn("engine.OWN_BASES", inspect.getsource(live.engine_after))

    def test_full_engine_mode_does_publish_pooled_units(self):
        """The difference between the two modes, stated as a test."""
        settings.set_price_source("engine", coverage=0.9)
        with _Engine(basis="district_pool"):
            self.assertIsNotNone(
                live.engine_after(1, "2026-10", 20000, 1, self._discount()))

    def test_discount_mode_ignores_the_engine_entirely(self):
        settings.set_price_source("discount", coverage=0.9)
        with _Engine(basis="own_history"):
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))


class GuestPathNeverBlocksTest(_Base):
    """A guest page must never wait on Hostaway OR on brain.db.

    The old version of this class warmed collect._CACHE and asserted the guest
    path did not COMPUTE. That was the right worry and the wrong guarantee: a warm
    cache still meant four SQLite connections per unit inside the page load, and
    on 2026-08-19 that is what stopped the site responding. The guarantee is now
    structural — the guest path reads a value someone else already computed — so
    these tests assert that a missing or stale value degrades quietly instead."""

    def _discount(self):
        return {"before": 20000, "after": 16000, "saved": 4000, "pct": 0.2,
                "ceiling": 0.3, "per_month_before": 20000,
                "per_month_after": 16000, "promo": False, "promo_label": ""}

    def test_nothing_precomputed_yet_falls_back_to_the_discount(self):
        """Right after a deploy the background loop has not run. The guest sees
        the price the site has always shown, not a blank and not a wait."""
        settings.set_price_source("engine_verified", coverage=0.9)
        with _NoEngine():
            self.assertIsNone(live.engine_after(1, "2026-10", 20000, 1, self._discount()))

    def test_a_precomputed_price_is_served(self):
        settings.set_price_source("engine_verified", coverage=0.9)
        with _Engine(price=15000, basis="own_history"):
            out = live.engine_after(1, "2026-10", 20000, 1, self._discount())
        self.assertIsNotNone(out)
        self.assertEqual(out["after"], 15000)

    def test_the_guest_path_never_opens_the_database(self):
        """brain.db is replaced by a landmine for the duration. If any part of the
        guest price path reaches SQLite, this fails instead of the storefront."""
        import sqlite3
        settings.set_price_source("engine_verified", coverage=0.9)
        real_connect = sqlite3.connect

        def boom(*_a, **_k):
            raise AssertionError("the guest price path opened brain.db")

        sqlite3.connect = boom
        try:
            with _Engine(price=15000, basis="own_history"):
                out = live.engine_after(1, "2026-10", 20000, 1, self._discount())
        finally:
            sqlite3.connect = real_connect
        self.assertEqual(out["after"], 15000)
