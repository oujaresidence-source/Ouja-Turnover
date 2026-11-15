# -*- coding: utf-8 -*-
"""
The owner's minimum price per apartment must SURVIVE A RESTART, and there is ONE of it.

Found 2026-11-15: the minimum typed on the pricing page lived only in memory
(`_pe_floor_overrides = {}`), so every deploy wiped it — while the engine, the same-day
discount ladder and the targets board all read it. The Listings page had its own «floor»
field that fed nothing.

The main file cannot be imported (it boots a Discord bot), so the small functions are lifted
out of its text and run here against a fake disk.

Run: python3 -m unittest tests.test_price_floor_persist
"""

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAMES = ("_pe_floor_load", "_pe_floor_save", "_pe_floor_set", "_pe_floor_of")
FILE = "pricing_floor_overrides.json"


def src():
    with open(os.path.join(ROOT, "bot" + ".py"), encoding="utf-8") as f:
        return f.read()


def lifted(disk):
    """The floor helpers, wired to a dict instead of the state folder."""
    tree = ast.parse(src())
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
    assert len(body) == len(NAMES), [n.name for n in body]
    ns = {"PE_FLOOR_FILE": FILE,
          "_load_json": lambda name, default: disk.get(name, default),
          "_save_json": lambda name, obj: disk.__setitem__(name, obj) or True}
    exec(compile(ast.Module(body=body, type_ignores=[]), "floor_helpers", "exec"), ns)
    ns["_pe_floor_overrides"] = ns["_pe_floor_load"]()
    return ns


class Survives(unittest.TestCase):
    def test_a_typed_minimum_is_there_after_a_restart(self):
        disk = {}
        a = lifted(disk)
        self.assertTrue(a["_pe_floor_set"](457230, 480))
        self.assertEqual(a["_pe_floor_of"](457230), 480)
        b = lifted(disk)                                    # the process restarts
        self.assertEqual(b["_pe_floor_of"](457230), 480)
        self.assertEqual(b["_pe_floor_of"]("457230"), 480)  # ids arrive as text too
        self.assertEqual(b["_pe_floor_overrides"], {457230: 480})   # int keys, as every reader expects

    def test_clearing_it_is_remembered_too(self):
        disk = {}
        a = lifted(disk)
        a["_pe_floor_set"](1, 300)
        a["_pe_floor_set"](1, 0)
        self.assertEqual(lifted(disk)["_pe_floor_of"](1), 0)

    def test_bad_values_change_nothing(self):
        disk = {}
        a = lifted(disk)
        a["_pe_floor_set"](1, 300)
        for lid, v in (("x", 100), (1, "abc"), (None, 5)):
            self.assertFalse(a["_pe_floor_set"](lid, v))
        self.assertEqual(a["_pe_floor_of"](1), 300)
        self.assertEqual(a["_pe_floor_of"]("nope"), 0)

    def test_a_broken_file_starts_empty_instead_of_crashing(self):
        for bad in ("oops", ["a"], {"x": "y", "7": "300", "8": -5}):
            ns = lifted({FILE: bad})
            self.assertEqual(ns["_pe_floor_overrides"], {7: 300} if isinstance(bad, dict) else {})


class OneSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = src()

    def test_loaded_from_disk_at_start(self):
        self.assertIn("_pe_floor_overrides = _pe_floor_load()", self.s)
        self.assertNotIn("_pe_floor_overrides = {}", self.s)

    def test_nobody_writes_the_dict_behind_the_savers_back(self):
        self.assertEqual(self.s.count("_pe_floor_overrides[lid] = "), 1)   # inside _pe_floor_set only
        self.assertEqual(self.s.count("_pe_floor_overrides.pop("), 1)

    def test_both_pages_write_the_same_minimum(self):
        i = self.s.index("async def _api_plab_settings(request):")
        self.assertIn("_pe_floor_set(", self.s[i:i + 2600])
        i = self.s.index("async def _api_listings_update(request):")
        self.assertIn("_pe_floor_set(", self.s[i:i + 3600])

    def test_listings_page_shows_the_one_minimum(self):
        self.assertIn('"floor": rec.get("floor") or (_pe_floor_of(rec.get("id")) or None),', self.s)


if __name__ == "__main__":
    unittest.main()
