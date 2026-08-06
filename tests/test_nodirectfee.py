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
from finance import api as FAPI
from finance import owners as OW

# finance/ reaches bot.py through api.B, which mount() normally sets at boot.
FAPI.B = FAPI.B or bot

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


def _publish(body):
    """Run statement_publish against stubs and report what it did: which settings
    reached the compute, and what landed on the stored record."""
    rec = {}
    seen = {}

    def fake_compute(owner, mkey, apply_edits=True, settings=None):
        seen["settings"] = settings
        out = {"owner": owner, "owner_net": 100.0, "total_income": 100.0}
        if settings is not None and settings.get("direct_fee_pct") is not None:
            out["direct_fee_pct"] = float(settings["direct_fee_pct"])
            out["no_direct_fee"] = (float(settings["direct_fee_pct"]) == 0.0)
        return out

    saved = (OW.compute_owner_statement, OW.stmt_rec, OW._stmt_save,
             OW._invalidate_owner_cache, FAPI.actor)
    OW.compute_owner_statement = fake_compute
    OW.stmt_rec = lambda o, m, create=False: rec
    OW._stmt_save = lambda: None
    OW._invalidate_owner_cache = lambda *a, **k: None
    FAPI.actor = lambda r: "tester"
    try:
        data, status = OW.statement_publish(None, body)
    finally:
        (OW.compute_owner_statement, OW.stmt_rec, OW._stmt_save,
         OW._invalidate_owner_cache, FAPI.actor) = saved
    return {"data": data, "status": status, "record": rec.get("published") or {},
            "audit": rec.get("audit") or [], "seen_settings": seen.get("settings")}


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

    def test_publish_defaults_to_the_normal_3pct_basis(self):
        # The owner asked (2026-08-06) to be able to publish the no-fee statement,
        # so publish is no longer basis-blind. What replaces that guarantee: the
        # basis must arrive EXPLICITLY, and its absence always means the real one.
        r = _publish({"owner": "X", "m": "2026-07"})
        self.assertEqual(r["seen_settings"], None)
        self.assertEqual(r["record"]["basis"], "normal")

    def test_publish_refuses_a_basis_it_does_not_know(self):
        data, status = OW.statement_publish(None, {"owner": "X", "m": "2026-07",
                                                   "basis": "half_price"})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "bad_basis")

    def test_publishing_the_no_fee_basis_records_it(self):
        r = _publish({"owner": "X", "m": "2026-07", "basis": "no_direct_fee"})
        self.assertEqual(r["seen_settings"], {"direct_fee_pct": 0.0})
        self.assertEqual(r["record"]["basis"], "no_direct_fee")
        # …and the audit trail carries it, or six months from now nobody can tell
        # which statement an owner was actually sent
        self.assertEqual(r["audit"][-1]["after"]["basis"], "no_direct_fee")

    def test_the_owners_copy_carries_no_internal_stamp(self):
        # his call: «ولا شي — كشف عادي تماماً». The snapshot must not trip the
        # red band or the «تقرير بدون خصم ٣٪» title.
        snap = _publish({"owner": "X", "m": "2026-07", "basis": "no_direct_fee"})["record"]["snapshot"]
        self.assertNotIn("no_direct_fee", snap)
        # but direct_fee_pct=0 STAYS — it is what stops the PDF printing «−٣٪»
        self.assertEqual(snap["direct_fee_pct"], 0.0)

    def test_the_view_cannot_publish_itself(self):
        # the basis comes from the button pressed, never from the screen's state
        h = JS[JS.index("act === 'se-publish'"):]
        h = h[:h.index("else if (act === 'se-nofee')")]
        self.assertIn("(act === 'se-publish-nofee') ? 'no_direct_fee' : 'normal'", h)
        self.assertIn("basis: pubBase", h)
        self.assertNotIn("seUI.nofee ?", h)      # never derived from the toggle


class ThePublishedLabel(unittest.TestCase):
    """A published no-fee statement says nothing about the fee — but silence must
    not become a false «−٣٪» on a document an owner receives."""

    _label = staticmethod(bot._pdf_direct_income_label)

    def test_normal_statement_still_shows_the_percentage(self):
        self.assertEqual(self._label({"direct_fee_pct": 3.0}), "دخل مباشر (−3.0٪)")

    def test_internal_preview_says_it_plainly(self):
        self.assertIn("بدون خصم", self._label({"direct_fee_pct": 0.0, "no_direct_fee": True}))

    def test_published_no_fee_is_silent_and_never_claims_a_deduction(self):
        lbl = self._label({"direct_fee_pct": 0.0})
        self.assertEqual(lbl, "دخل مباشر")
        self.assertNotIn("٪", lbl)
        self.assertNotIn("−", lbl)

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
