# -*- coding: utf-8 -*-
"""
What reaches a quote, and what never does.

    structural  -> never a line, anywhere (it is a blocker)
    document    -> never a line (it is an onboarding task)
    product     -> owner quote or Ouja purchase list, by billed_to
    works       -> owner quote (its OWN group) or Ouja maintenance list, by billed_to
    a zero price is FLAGGED, never silently dropped

Run: python3 -m unittest tests.test_mot_quote
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mot import catalogue as C, engine  # noqa: E402

PRICES = {"c10.iron": 150.0, "c21.mattress": 900.0, "c02.lighting": 400.0,
          "c08.detergents": 60.0, "c27.toilet": 350.0, "c46.pool_rescue": 0.0}
META = {"bedrooms": 2, "bathrooms": 2, "beds": 3}


def fails(*keys, **over):
    r = {c["key"]: {"state": "available"} for c in C.components(True)}
    for k in keys:
        r[k] = {"state": "missing"}
    for k, v in over.items():
        r[k].update(v)
    return r


class TestSplit(unittest.TestCase):
    def test_structural_and_document_never_become_lines(self):
        q = engine.quote_lines(fails("c03.elevator", "c39.evac_plan"), PRICES, META, True)
        self.assertEqual(q["owner"], [])
        self.assertEqual(q["ouja_products"], [])
        self.assertEqual(q["ouja_works"], [])
        self.assertEqual([b["key"] for b in q["blocked"]], ["c03.elevator"])
        self.assertEqual([d["key"] for d in q["documents"]], ["c39.evac_plan"])

    def test_billed_to_splits_owner_and_ouja(self):
        q = engine.quote_lines(fails("c10.iron", "c08.detergents", "c27.toilet"), PRICES, META, True)
        self.assertEqual([l["key"] for l in q["owner"]], ["c10.iron", "c27.toilet"])
        self.assertEqual([l["key"] for l in q["ouja_products"]], ["c08.detergents"])

    def test_per_unit_override_of_billed_to(self):
        q = engine.quote_lines(fails("c10.iron", **{"c10.iron": {"billed_to": "ouja"}}),
                               PRICES, META, True)
        self.assertEqual(q["owner"], [])
        self.assertEqual([l["key"] for l in q["ouja_products"]], ["c10.iron"])

    def test_works_land_in_their_own_group(self):
        q = engine.quote_lines(fails("c02.lighting", "c27.toilet", "c10.iron"), PRICES, META, True)
        groups = [l["group"] for l in q["owner"]]
        self.assertEqual(groups, ["product", "works", "works"])   # products first, works after
        self.assertTrue(all(l["group"] == "works" for l in q["owner"] if l["kind"] == "works"))

    def test_ouja_works_are_maintenance_not_purchase(self):
        q = engine.quote_lines(fails("c27.toilet", **{"c27.toilet": {"billed_to": "ouja"}}),
                               PRICES, META, True)
        self.assertEqual([l["key"] for l in q["ouja_works"]], ["c27.toilet"])
        self.assertEqual(q["ouja_products"], [])


class TestArithmetic(unittest.TestCase):
    def test_qty_times_price_with_default_qty(self):
        q = engine.quote_lines(fails("c21.mattress"), PRICES, META, True)
        line = q["owner"][0]
        self.assertEqual(line["qty"], 3)              # per_bed -> beds
        self.assertEqual(line["price"], 900.0)
        self.assertEqual(line["total"], 2700.0)
        self.assertEqual(q["owner_total"], 2700.0)

    def test_inspector_qty_wins(self):
        q = engine.quote_lines(fails("c21.mattress", **{"c21.mattress": {"qty": 1}}), PRICES, META, True)
        self.assertEqual(q["owner"][0]["total"], 900.0)

    def test_zero_price_is_flagged_not_dropped(self):
        q = engine.quote_lines(fails("c46.pool_rescue", "c16.tv"), PRICES, META, True)
        keys = [l["key"] for l in q["owner"]]
        self.assertIn("c46.pool_rescue", keys)
        self.assertIn("c16.tv", keys)
        self.assertEqual(sorted(q["unpriced"]), ["c16.tv", "c46.pool_rescue"])

    def test_stale_price_flag(self):
        prices = {"c10.iron": {"price_sar": 150.0, "set_at": "2026-01-01T00:00:00"}}
        q = engine.quote_lines(fails("c10.iron"), prices, META, True, today="2026-09-06")
        self.assertEqual(q["stale"], ["c10.iron"])
        fresh = {"c10.iron": {"price_sar": 150.0, "set_at": "2026-08-01T00:00:00"}}
        self.assertEqual(engine.quote_lines(fails("c10.iron"), fresh, META, True,
                                            today="2026-09-06")["stale"], [])

    def test_quote_items_payload_shape(self):
        q = engine.quote_lines(fails("c10.iron", "c27.toilet"), PRICES, META, True)
        items = engine.quote_items(q["owner"])
        self.assertEqual(set(items[0]), {"description", "note", "qty", "price"})
        # the works separator is a visible zero line, so the owner sees the plumber
        descs = [i["description"] for i in items]
        self.assertTrue(any("أعمال وتركيبات" in d for d in descs))
        self.assertEqual(descs.index(next(d for d in descs if "أعمال" in d)), 1)


if __name__ == "__main__":
    unittest.main()
