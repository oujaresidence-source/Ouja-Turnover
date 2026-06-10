# -*- coding: utf-8 -*-
"""Slice 0b regression suite — the Abu-Fahad June-2026 wrong-number bug.

Root causes pinned here forever:
  R1  build_owner_report read the TRUNCATED full-history pull (~6,000 rows,
      newest months silently missing) → whole reservations invisible.
  R2  the registry seed listed SEVEN units for أبو فهد (102B missing) → a whole
      unit invisible.
  R3  airbnb rows without a payout field were excluded with NO visible value.

The synthetic scenario mirrors the real shape exactly: 18% mgmt, cleaning
'ours', and engineered amounts where the broken pipeline shows 18,842.00 and
the fixed pipeline shows 48,114.05 (the owner's books figure).

Run: python3 tests/test_owner_statement_0b.py
"""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-0b")
os.makedirs("/tmp/ouja-test-state-0b", exist_ok=True)

import bot  # noqa: E402

JUNE_S, JUNE_E = date(2026, 6, 1), date(2026, 6, 30)


def _resv(rid, lid, payout, checkin="2026-06-05", checkout="2026-06-08",
          status="new", channel="Airbnb", total=None):
    return {"id": rid, "listingMapId": lid, "status": status,
            "channelName": channel, "arrivalDate": checkin, "departureDate": checkout,
            "nights": 3, "guestName": "Guest " + str(rid),
            "airbnbExpectedPayoutAmount": payout, "totalPrice": total,
            "refundAmount": None}


# The engineered books: 8 units (101 = lid 1..7 registered, 102B = lid 8 missing
# from the registry pre-fix). Income splits so the broken pull nets 18,842.00.
FULL_SET = [
    _resv("a1", 1, 10000.00),                      # visible in the truncated cache
    _resv("a2", 2, 12978.05),                      # visible in the truncated cache
    _resv("a3", 3, 23697.62, checkin="2026-06-15", checkout="2026-06-18"),  # NEWER → truncated away
    _resv("a4", 4, 10000.00, checkin="2026-06-20", checkout="2026-06-23"),  # NEWER → truncated away
    _resv("a5", 8, 2000.00),                       # unit 102B — not in the registry pre-fix
]
TRUNCATED_CACHE = [r for r in FULL_SET if r["id"] in ("a1", "a2", "a5")]


class ComputeVisibilityTest(unittest.TestCase):
    """R3: a missing payout NEVER vanishes — excluded with reason + reference."""

    def test_missing_payout_is_visible_with_reference(self):
        rows = [
            {"id": "x1", "channel": "airbnb", "status": "new", "apartment": "101A",
             "checkin": "2026-06-03", "checkout": "2026-06-06", "nights": 3,
             "airbnb_payout": None, "total_price": 4321.0, "refund": 0, "extras": 0},
            {"id": "x2", "channel": "airbnb", "status": "new", "apartment": "101A",
             "checkin": "2026-06-10", "checkout": "2026-06-12", "nights": 2,
             "airbnb_payout": 1500.0, "total_price": 1700.0, "refund": 0, "extras": 0},
        ]
        rep = bot.compute_owner_report(rows, [], JUNE_S, JUNE_E, 18.0)
        self.assertEqual(rep["total_income"], 1500.0)        # never guessed from totalPrice
        nr = [l for l in rep["resv_lines"] if l.get("needs_review")]
        self.assertEqual(len(nr), 1)
        self.assertEqual(nr[0]["exclude_reason"], "missing_payout")
        self.assertEqual(nr[0]["reference_total"], 4321.0)
        es = rep["excluded_summary"]
        self.assertEqual(es["needs_review"], 1)
        self.assertEqual(es["needs_review_reference"], 4321.0)
        self.assertEqual(es["reasons"], {"missing_payout": 1})
        self.assertFalse(rep["reconciliation"]["balanced"])  # refuses to pretend


class RegistryMigrationTest(unittest.TestCase):
    """R2: 102B joins أبو فهد once; the marker keeps later deletions deliberate."""

    def setUp(self):
        bot._owner_registry.clear()
        bot._owner_seed_if_empty()
        # wipe the migration marker so each test starts pre-fix
        bot._save_json("owner_registry_migrations.json", [])

    def test_seed_has_only_seven_units_for_abu_fahad(self):
        owner = "ابو فهد عبدالحمن الخطيب"
        units = [r["apartment"] for r in bot._owner_registry.values() if r["owner"] == owner]
        self.assertEqual(len(units), 7)
        self.assertNotIn("102B", units)

    def test_migration_adds_102b_with_same_terms(self):
        self.assertTrue(bot._owner_registry_migrate())
        rec = bot._owner_registry.get(bot._owner_key("102B"))
        self.assertIsNotNone(rec)
        self.assertEqual(rec["owner"], "ابو فهد عبدالحمن الخطيب")
        self.assertEqual(rec["mgmt_pct"], 18.0)
        self.assertEqual(rec["cleaning"]["type"], "ours")

    def test_migration_is_idempotent_and_respects_deletion(self):
        bot._owner_registry_migrate()
        bot._owner_registry.pop(bot._owner_key("102B"))      # Faisal deletes it on purpose
        self.assertFalse(bot._owner_registry_migrate())      # marker blocks re-adding
        self.assertNotIn(bot._owner_key("102B"), bot._owner_registry)


class WindowSourceTest(unittest.TestCase):
    """R1: statements read the TARGETED window pull, never the truncated cache."""

    def setUp(self):
        self._window, self._cached = bot.fetch_reservations_window, bot.get_reservations_cached
        self._listings = bot.get_listings_map
        self._expenses = dict(bot._expenses)
        bot._expenses.clear()
        bot.fetch_reservations_window = lambda s, e, pad_days=45: FULL_SET
        bot.get_reservations_cached = lambda ttl=1800: TRUNCATED_CACHE
        bot.get_listings_map = lambda: {1: "Ouja | 101A", 2: "Ouja | 101B", 3: "Ouja | 201A",
                                        4: "Ouja | 201B", 5: "Ouja | 102A", 6: "Ouja | 202A",
                                        7: "Ouja | 202B", 8: "Ouja | 102B"}

    def tearDown(self):
        bot.fetch_reservations_window = self._window
        bot.get_reservations_cached = self._cached
        bot.get_listings_map = self._listings
        bot._expenses.clear()
        bot._expenses.update(self._expenses)

    def test_statement_includes_rows_missing_from_the_old_cache(self):
        rep = bot.build_owner_report(3, JUNE_S, JUNE_E, 18.0, {})
        self.assertEqual(rep["total_income"], 23697.62)      # the truncated row IS counted

    def test_full_owner_reconciliation_18842_to_48114(self):
        """The reconciliation table in numbers: broken pipeline = 18,842.00 —
        fixed pipeline = 48,114.05. Every excluded riyal accounted for."""
        mgmt = 18.0
        # fixed world: all five reservations across all EIGHT units
        fixed_income = sum(r["airbnbExpectedPayoutAmount"] for r in FULL_SET)
        fixed_net = round(fixed_income * (1 - mgmt / 100.0), 2)
        self.assertEqual(round(fixed_income, 2), 58675.67)
        self.assertEqual(fixed_net, 48114.05)                # the owner's books figure
        # broken world: truncated cache + 102B (lid 8) not in the registry
        broken_income = sum(r["airbnbExpectedPayoutAmount"] for r in TRUNCATED_CACHE
                            if r["listingMapId"] != 8)
        broken_net = round(broken_income * (1 - mgmt / 100.0), 2)
        self.assertEqual(broken_net, 18842.00)               # the wrong number on his statement
        # and the gap decomposes EXACTLY into the two causes
        lost_truncation = sum(r["airbnbExpectedPayoutAmount"] for r in FULL_SET
                              if r["id"] in ("a3", "a4"))
        lost_unit = sum(r["airbnbExpectedPayoutAmount"] for r in FULL_SET if r["listingMapId"] == 8)
        self.assertEqual(round((lost_truncation + lost_unit) * (1 - mgmt / 100.0), 2),
                         round(fixed_net - broken_net, 2))
        # the per-unit statement math agrees with the arithmetic above
        per_unit = [bot.build_owner_report(lid, JUNE_S, JUNE_E, mgmt, {}) for lid in (1, 2, 3, 4, 8)]
        self.assertEqual(round(sum(r["owner_net"] for r in per_unit), 2), fixed_net)


if __name__ == "__main__":
    unittest.main(verbosity=2)
