# -*- coding: utf-8 -*-
"""owner_meet structure — the platform traps (brief P1–P11) enforced on the SOURCE, not on trust.

Each check here has bitten this codebase before: a stray backslash killed a dashboard login twice,
asyncio.to_thread starved the guest site, get_reservations_cached() under-counted an owner
statement (18,842 instead of 48,114), and a module nobody wired "guarded" nothing.

Run: python3 -m unittest tests.test_owner_meet_structure
"""
import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "owner_meet"
sys.path.insert(0, str(ROOT))


def _py_files():
    return sorted(PKG.glob("*.py"))


def _read(p):
    return Path(p).read_text(encoding="utf-8")


def _func_src(src, name):
    m = re.search(r"^(async )?def " + re.escape(name) + r"\(", src, re.M)
    if not m:
        return None
    body_at = src.index(chr(10), m.end()) + 1                  # search from the line AFTER the def
    nxt = re.search(r"^(async )?def |^[A-Za-z_]", src[body_at:], re.M)
    return src[m.start(): body_at + (nxt.start() if nxt else len(src))]


# Words / fields that would mean a back-calculated or Hostaway-fee waterfall (M3 + Faisal 2026-10-06).
FORBIDDEN_FIELDS = ("airbnbListingHostFee", "hostChannelFee", "channelCommissionAmount",
                    "taxAmount", "vatAmount", "airbnbTotalPaidAmount", "totalTax")
# Arithmetic with the prototype's back-calculation constants (÷1.15 VAT, ×0.822 host fee). A CSS size
# like `calc(var(--u)*1.15)` is not money: the multiplier there is a CSS unit, so only a bare number
# or identifier on the other side of the operator counts.
_BACKCALC = re.compile(r"(?:[A-Za-z0-9_)][ ]*[/*][ ]*(?:1[.]15|0?[.]822)(?![0-9]))"
                       r"|(?:(?<![0-9.])(?:1[.]15|0?[.]822)[ ]*[*][ ]*[A-Za-z_(])")


def waterfall_hits(text):
    hits = [w for w in FORBIDDEN_FIELDS if w in text]
    hits += [m.group(0).strip() for m in _BACKCALC.finditer(text) if "var(--" not in text[max(0, m.start() - 12):m.start() + 2]]
    return hits


class PackageSource(unittest.TestCase):
    def test_package_exists_with_its_modules(self):
        names = {p.name for p in _py_files()}
        for need in ("__init__.py", "host.py", "config.py", "db.py", "periods.py", "money.py",
                     "engine.py", "snapshot.py", "jobs.py", "airbnb_import.py", "texts.py", "charts.py",
                     "render.py", "routes.py", "ops.py", "redact.py", "privacy.py", "abnb.py"):
            self.assertIn(need, names)

    def test_never_imports_bot(self):
        for p in _py_files():
            self.assertIsNone(re.search(r"^\s*(import bot\b|from bot\b)", _read(p), re.M), p.name)

    def test_never_uses_to_thread_or_run_in_executor(self):
        for p in _py_files():
            src = _read(p)
            self.assertNotIn("to_thread(", src, p.name)
            self.assertNotIn("run_in_executor", src, p.name)

    def test_zero_backslashes_in_every_module(self):
        files = list(_py_files()) + sorted(PKG.rglob("*.js"))
        for p in files:
            bad = [i + 1 for i, line in enumerate(_read(p).splitlines()) if chr(92) in line]
            self.assertEqual(bad, [], "%s has a backslash on line(s) %s" % (p.name, bad))

    def test_py39_parseable(self):
        for p in _py_files():
            ast.parse(_read(p), filename=str(p), feature_version=(3, 9))

    def test_no_sample_content(self):
        for p in list(PKG.rglob("*.py")) + list(PKG.rglob("*.js")) + list(PKG.rglob("*.json")):
            self.assertNotIn("مثال توضيحي", _read(p), p.name)

    def test_no_scheduler_no_automatic_send(self):
        """Nothing is ever sent to an owner on its own: no loops, no timers, no Discord posts."""
        for p in _py_files():
            src = _read(p)
            for bad in ("create_task(", "tasks.loop", "call_later(", "ensure_future(", ".send(", "send_message("):
                self.assertNotIn(bad, src, "%s uses %s" % (p.name, bad))

    def test_never_touches_the_truncating_reservation_cache(self):
        for p in _py_files():
            self.assertNotIn("get_reservations_cached", _read(p), p.name)


class WaterfallScope(unittest.TestCase):
    """Faisal 2026-10-06: «وين راح كل ريال» starts at «صافي الحجوزات» in this version."""

    def test_no_back_calculation_and_no_fee_fields_in_the_package(self):
        for p in list(_py_files()) + list(PKG.rglob("*.js")):
            self.assertEqual(waterfall_hits(_read(p)), [], p.name)

    def test_the_scanner_sees_a_planted_back_calculation(self):
        """Positive control: the absence check above is only worth something if it can fail."""
        self.assertTrue(waterfall_hits("net = gross / 1.15 * 0.822"))
        self.assertTrue(waterfall_hits("payout = paid * .822"))
        self.assertTrue(waterfall_hits("pre_vat = total/1.15"))
        self.assertEqual(waterfall_hits("r.get('airbnbListingHostFee')"), ["airbnbListingHostFee"])
        self.assertEqual(waterfall_hits("font-size:calc(var(--u)*1.15);line-height:1.15"), [],
                         "a CSS size is not a back-calculation")

    def test_waterfall_rows_start_at_booking_income(self):
        from decimal import Decimal
        from owner_meet import money
        tot = {f: Decimal(0) for f in money.FIELDS}
        tot.update(total_income=Decimal(100), owner_net=Decimal(100))
        keys = [r["key"] for r in money.waterfall(tot)["rows"]]
        self.assertEqual(keys[0], "income")
        self.assertTrue(set(keys) <= {"income", "fee", "cleaning", "expenses", "adjustments", "net"}, keys)


class BotWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = _read(ROOT / "bot.py")

    def test_import_guard_and_wiring_block(self):
        self.assertIn("import owner_meet as _owner_meet", self.src)
        self.assertIn("_owner_meet.wire(_owner_meet_caps())", self.src)
        self.assertIn("_owner_meet.bootstrap()", self.src)

    def test_caps_wrap_the_statement_path_and_the_targeted_window(self):
        body = _func_src(self.src, "_owner_meet_caps")
        self.assertIsNotNone(body)
        self.assertIn('"month_report": _owner_month_report', body)
        self.assertIn("fetch_reservations_window_checked(", body)
        self.assertNotIn("get_reservations_cached", body)
        unit = _func_src(self.src, "_om_unit_month")
        self.assertIn("unit_slice(_owner_month_report(", unit)

    def test_caps_never_create_a_portal_token(self):
        body = _func_src(self.src, "_om_portal_token")
        self.assertNotIn("get_or_create", body)
        self.assertNotIn("regenerate", body)


if __name__ == "__main__":
    unittest.main()
