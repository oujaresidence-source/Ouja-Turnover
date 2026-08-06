# -*- coding: utf-8 -*-
"""«بدون خصم ٣٪» — the alternate-basis view of an owner statement.

Ouja deducts a flat 3% from DIRECT (non-Airbnb) bookings before reporting them.
The owner wanted to see the same report with that deduction not applied, and was
explicit about the constraint: "so we cannot mess up anything and there is always
a way to go back."

So this file guards two different things:

  1. THE MATH — a direct booking reads full value, Airbnb is untouched, and
     رسوم عوجا (a % of income) rises with the income the way it must.
  2. THE BLAST RADIUS — the override is read-only. It cannot reach a published
     statement, and asking for it must never change what the normal path returns.

(2) is the one that matters. compute_owner_statement is the code behind every
real statement in the business; the whole design rests on the override defaulting
to off and statement_publish recomputing without it.
"""
import inspect
import pathlib
import re
import unittest

import bot
from finance import owners as OW

JS = pathlib.Path("finance/static/erp.js").read_text("utf-8")
INIT = pathlib.Path("finance/__init__.py").read_text("utf-8")

NOFEE = {"direct_fee_pct": 0.0}


def _resv(rid, channel, amount, day="05", **kw):
    """One normalized reservation row, shaped the way compute_owner_report wants."""
    row = {"id": rid, "channel": channel, "lid": 1, "apartment": "Ouja | A15",
           "guest": "ضيف", "checkin": "2026-07-%s" % day, "checkout": "2026-07-09",
           "nights": 4, "status": "new", "refund": 0.0, "extras": 0.0,
           "total_price": amount}
    if channel == "airbnb":
        row["airbnb_payout"] = amount
    else:
        row["direct_revenue"] = amount
    row.update(kw)
    return row


def _report(rows, pct=20.0, settings=None):
    import datetime
    return bot.compute_owner_report(rows, [], datetime.date(2026, 7, 1),
                                    datetime.date(2026, 7, 31), pct, settings)


class TheMath(unittest.TestCase):
    def test_direct_booking_loses_3pct_normally(self):
        rep = _report([_resv("d1", "direct", 10000.0)])
        self.assertEqual(rep["income_direct"], 9700.0)

    def test_direct_booking_keeps_every_riyal_with_the_override(self):
        rep = _report([_resv("d1", "direct", 10000.0)], settings=NOFEE)
        self.assertEqual(rep["income_direct"], 10000.0)

    def test_airbnb_is_identical_on_both_bases(self):
        rows = [_resv("a1", "airbnb", 10000.0)]
        self.assertEqual(_report(rows)["income_airbnb"],
                         _report(rows, settings=NOFEE)["income_airbnb"])

    def test_ouja_fee_follows_the_higher_income(self):
        # the owner chose "let everything recalculate": 20% of 10,000 not of 9,700
        rows = [_resv("d1", "direct", 10000.0)]
        self.assertEqual(_report(rows)["ouja_fee"], 1940.0)
        self.assertEqual(_report(rows, settings=NOFEE)["ouja_fee"], 2000.0)

    def test_owner_net_still_ties_out_to_income_minus_fees(self):
        rep = _report([_resv("d1", "direct", 10000.0)], settings=NOFEE)
        self.assertAlmostEqual(rep["owner_net"],
                               rep["total_income"] - rep["ouja_fee"]
                               - rep["expenses"] - rep["cleaning"]["total"], places=2)

    def test_the_gap_between_the_two_bases_is_exactly_the_fee(self):
        rows = [_resv("d1", "direct", 10000.0), _resv("d2", "direct", 3333.33, day="12"),
                _resv("a1", "airbnb", 8000.0, day="20")]
        normal, nofee = _report(rows), _report(rows, settings=NOFEE)
        fee = sum(l["direct_fee_amount"] for l in normal["resv_lines"]
                  if l.get("direct_fee_amount"))
        self.assertAlmostEqual(nofee["total_income"] - normal["total_income"], fee, places=2)
        self.assertGreater(fee, 0)      # a vacuous pass would satisfy the line above

    def test_refund_still_comes_off_the_base(self):
        # 0% must mean "no fee", NOT "ignore the rest of the money math"
        rep = _report([_resv("d1", "direct", 10000.0, refund=1000.0)], settings=NOFEE)
        self.assertEqual(rep["income_direct"], 9000.0)

    def test_a_line_on_the_alternate_basis_carries_no_fee(self):
        line = _report([_resv("d1", "direct", 10000.0)], settings=NOFEE)["resv_lines"][0]
        self.assertEqual(line["direct_fee_amount"], 0.0)
        self.assertEqual(line["direct_fee_pct"], 0.0)


class BlastRadius(unittest.TestCase):
    """The override must be unable to reach anything durable."""

    def test_every_threaded_function_defaults_the_override_off(self):
        for fn in (OW.unit_statement, OW.compute_owner_statement,
                   OW.statement_payload, OW.compute_owner_range):
            sig = inspect.signature(fn)
            self.assertIn("settings", sig.parameters, fn.__name__)
            self.assertIsNone(sig.parameters["settings"].default, fn.__name__)

    def test_publish_recomputes_without_settings(self):
        # THE guard: statement_publish must build its snapshot from a bare
        # compute_owner_statement(owner, mkey). If a `settings=` ever appears in
        # that call, an alternate-basis view could be frozen and sent to an owner.
        src = inspect.getsource(OW.statement_publish)
        call = re.search(r"compute_owner_statement\((.*?)\)", src, re.S)
        self.assertIsNotNone(call, "publish no longer calls compute_owner_statement")
        self.assertNotIn("settings", call.group(1))

    def test_default_report_is_unchanged_by_the_new_parameter(self):
        rows = [_resv("d1", "direct", 10000.0), _resv("a1", "airbnb", 5000.0, day="20")]
        self.assertEqual(_report(rows), _report(rows, settings=None))

    def test_the_alternate_basis_is_stamped_so_no_surface_can_mislabel_it(self):
        # _finance_aggregate drops direct_fee_pct; an unstamped 0% report would
        # print «دخل مباشر (−٣٪)» above full-value numbers.
        src = inspect.getsource(OW.compute_owner_statement)
        self.assertIn("no_direct_fee", src)
        src2 = inspect.getsource(OW.compute_owner_range)
        self.assertIn("no_direct_fee", src2)

    def test_pdf_renderer_reads_the_stamp(self):
        src = inspect.getsource(bot._pdf_statement_bytes)
        self.assertIn("no_direct_fee", src)


class Wiring(unittest.TestCase):
    def test_download_route_is_registered_and_separate(self):
        self.assertIn("/erp/api/owners/no-direct-fee.zip", INIT)
        self.assertIn("/erp/api/owners/no-direct-fee.zip", JS)

    def test_download_is_read_only(self):
        # registered without write=True — it must never sit on a mutating guard
        line = next(l for l in INIT.splitlines() if "no-direct-fee.zip" in l and "add_" in l)
        self.assertIn("add_get", line)
        self.assertNotIn("write=True", line)

    def test_toggle_labels_exist_in_both_languages(self):
        for key in ("o_nofee", "o_nofee_on", "o_nofee_dl",
                    "o_nofee_dl_all", "o_nofee_dl_all_confirm"):
            self.assertEqual(len(re.findall(r"\b%s:" % key, JS)), 2,
                             "%s must be defined in BOTH T.ar and T.en" % key)

    def test_the_default_download_is_scoped_to_the_owner_on_screen(self):
        # the owner pressed the button on one owner's statement and got the whole
        # book — the per-owner download must stay the DEFAULT, all-owners opt-in
        h = JS[JS.index("act === 'se-nofee-dl'"):]
        h = h[:h.index("else if (act === 'se-tieout')")]
        self.assertIn("allOwners = (act === 'se-nofee-dl-all')", h)
        self.assertIn("who = allOwners ? '' : (dZ.owner || '')", h)
        self.assertIn("'&owner=' + encodeURIComponent(who)", h)
        self.assertIn("confirm(", h)        # the whole book is a confirmed choice


if __name__ == "__main__":
    unittest.main()
