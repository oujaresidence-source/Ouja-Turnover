# -*- coding: utf-8 -*-
"""New Hostaway units must SURFACE in الملاك before anyone assigns them (2026-09-06).

The accounting team reported «V6 و 101 النرجس غير موجودة في الملاك ولا أقدر أسحب تقرير»:
the owners section is registry-driven, so a listing that exists in Hostaway but has no
owner row was invisible everywhere — and the only add path lived inside an EXISTING
owner's profile, so a unit with a brand-new owner could never be registered at all.

Pins:
  • owners_payload() exposes `unassigned` = active Hostaway listings no registry row resolves to
  • a listing already matched (explicit lid OR name auto-match) is NOT listed as unassigned
  • inactive (deactivated) listings never appear
  • unit_add with a NEVER-SEEN owner name creates that owner and clears the unit
Run: python3 tests/test_owner_new_units.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-newunits"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)


class _Req:
    """The minimum finance.api.actor() needs."""
    headers = {}
    cookies = {}
    query = {}

    def __init__(self):
        self.remote = "test"


class NewUnitsSurface(unittest.TestCase):
    def setUp(self):
        self._reg = dict(bot._owner_registry)
        self._store = bot._ls_store
        bot._owner_registry.clear()
        bot._owner_registry.update({
            bot._owner_key("C2"): {"apartment": "C2", "owner": "نواف الوهيبي", "mgmt_pct": 20.0,
                                   "cleaning": {"type": "owner", "amount": 1250.0}},
            bot._owner_key("L-07"): {"apartment": "L-07", "owner": "احمد الصغير", "mgmt_pct": 15.0,
                                     "lid": 300, "cleaning": {"type": "owner", "amount": 1115.0}},
        })
        bot._ls_store = {"listings": {
            "100": {"id": 100, "internal_name": "C2 NFL", "active": True},              # name auto-match
            "300": {"id": 300, "internal_name": "شقة 7 - الماجديه", "active": True},   # explicit lid
            "569266": {"id": 569266, "internal_name": "V6-VLG", "active": True},       # NEW, unowned
            "576627": {"id": 576627, "internal_name": "101 -Narjs", "active": True},   # NEW, unowned
            "497185": {"id": 497185, "internal_name": "old unit", "active": False},    # deactivated
        }, "last_sync": "2026-09-06T03:00:00+03:00", "last_summary": {}}

    def tearDown(self):
        bot._owner_registry.clear(); bot._owner_registry.update(self._reg)
        bot._ls_store = self._store

    def test_unassigned_lists_only_active_unowned_listings(self):
        p = fapi.owners_payload()
        got = {(u["lid"], u["name"]) for u in p["unassigned"]}
        self.assertEqual(got, {(569266, "V6-VLG"), (576627, "101 -Narjs")})
        self.assertEqual(p["unassigned_count"], 2)

    def test_adding_to_a_brand_new_owner_creates_the_owner_and_clears_the_unit(self):
        before = {r["owner"] for r in fapi.owners_payload()["rows"]}
        self.assertNotIn("مالك جديد", before)
        data, status = OW.unit_add(_Req(), {"owner": "مالك جديد", "apartment": "V6", "lid": 569266,
                                            "mgmt_pct": 20, "cleaning": {"type": "ours", "amount": 0}})
        self.assertEqual(status, 200, data)
        p = fapi.owners_payload()
        owners = {r["owner"]: r for r in p["rows"]}
        self.assertIn("مالك جديد", owners)
        self.assertEqual(owners["مالك جديد"]["apartments_all"], ["V6"])
        self.assertEqual([u["lid"] for u in p["unassigned"]], [576627])


if __name__ == "__main__":
    unittest.main()
