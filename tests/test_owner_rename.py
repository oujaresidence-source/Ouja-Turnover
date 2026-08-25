# -*- coding: utf-8 -*-
"""One-time owner rename «نجلاء القاسم» → «نجلاء الغشام» (2026-08-10, owner-approved).

The owner's name is the PRIMARY KEY of six separate stores. Renaming only the
registry would leave a brand-new empty owner beside an old one holding every
statement, her share link and her phone. This suite pins the whole move:

  R1  every store follows the name — registry, unit_owners, links, statements,
      terms profile — and the portal cache is dropped for both names.
  R2  her existing share TOKEN survives, so the link already in her WhatsApp
      keeps working.
  R3  published snapshots get the NAME fixed and NOT ONE NUMBER touched.
  R4  it runs exactly once (marked), and a second boot is a no-op.
  R5  a name it cannot resolve unambiguously changes NOTHING and stays
      unmarked — a wrong guess is worse than doing nothing.
  R6  no other owner is touched.

Run: python3 tests/test_owner_rename.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = tempfile.mkdtemp(prefix="ouja-test-rename-")
os.environ.setdefault("STATE_DIR", _STATE)

import bot  # noqa: E402

OLD, NEW = "نجلاء القاسم", "نجلاء الغشام"
OTHER = "بتول يوسف"


def _write(name, obj):
    with open(os.path.join(bot.STATE_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _read(name):
    with open(os.path.join(bot.STATE_DIR, name), encoding="utf-8") as f:
        return json.load(f)


# A published July statement: the numbers below must come back byte-identical.
SNAPSHOT = {"currency": "SAR", "owner": OLD, "month": "2026-07",
            "total_income": 18400.55, "ouja_fee": 3680.11, "expenses": 1200.0,
            "cleaning": {"type": "owner", "total": 1050.0}, "owner_net": 12470.44,
            "apartments": [{"lid": 526697, "apartment": "103 NRJS", "owner_net": 12470.44}]}


class OwnerRenameTest(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ouja-rename-case-")
        bot.STATE_DIR = self.dir
        # The live shape: registry keyed by apartment, links/statements/terms by NAME.
        self.registry = {
            "103 nrjs": {"apartment": "103 NRJS", "owner": OLD, "mgmt_pct": 20.0,
                         "lid": 526697, "cleaning": {"type": "owner", "amount": 1050.0}},
            "d7": {"apartment": "D7", "owner": OTHER, "mgmt_pct": 20.0,
                   "lid": 111, "cleaning": {"type": "owner", "amount": 1050.0}},
        }
        _write("owner_registry.json", self.registry)
        bot._owner_registry.clear()
        bot._owner_registry.update(self.registry)

        bot._unit_owners.clear()
        bot._unit_owners.update({"103 NRJS": OLD, "D7": OTHER})
        _write("unit_owners.json", dict(bot._unit_owners))

        bot._owner_links.clear()
        bot._owner_links.update({
            OLD: {"token": "tok-najla-live", "active": True, "opens": 4,
                  "created_at": "2026-06-01T10:00:00", "regen_log": []},
            OTHER: {"token": "tok-batool", "active": True, "opens": 1, "regen_log": []},
        })
        _write("owner_links.json", dict(bot._owner_links))

        _write("owner_statements.json", {
            OLD + "|2026-06": {"owner": OLD, "month": "2026-06", "status": "sent",
                               "edits": {"resv": {}, "exp_manual": []}, "published": None},
            OLD + "|2026-07": {"owner": OLD, "month": "2026-07", "status": "opened",
                               "edits": {"resv": {}, "exp_manual": []},
                               "published": {"version": 2, "at": "2026-08-02T09:00:00",
                                             "by": "faisal", "basis": "normal",
                                             "snapshot": json.loads(json.dumps(SNAPSHOT))}},
            OTHER + "|2026-07": {"owner": OTHER, "month": "2026-07", "status": "draft",
                                 "edits": {}, "published": None},
        })
        _write("owner_terms.json", {
            "owners": {OLD: {"phone": "966500000000", "notes": "تحويل بنكي", "active": True},
                       OTHER: {"phone": "966511111111", "notes": "", "active": True}},
            "units": {"103 nrjs": {"contract_from": "2026-01-01"}},
            "versions": [],
        })
        bot._owner_portal_cache[(OLD, "2026-07")] = ({"owner": OLD}, 0.0)
        bot._owner_portal_cache[(OTHER, "2026-07")] = ({"owner": OTHER}, 0.0)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        bot._owner_portal_cache.clear()

    # ---------- R1: every store follows the name ----------
    def test_registry_and_unit_owners_follow(self):
        bot._owner_rename_once()
        self.assertEqual(bot._owner_registry["103 nrjs"]["owner"], NEW)
        self.assertEqual(_read("owner_registry.json")["103 nrjs"]["owner"], NEW)
        self.assertEqual(bot._unit_owners["103 NRJS"], NEW)
        self.assertEqual(_read("unit_owners.json")["103 NRJS"], NEW)
        # the rest of the row is untouched
        self.assertEqual(bot._owner_registry["103 nrjs"]["mgmt_pct"], 20.0)
        self.assertEqual(bot._owner_registry["103 nrjs"]["lid"], 526697)

    def test_statements_and_terms_follow(self):
        bot._owner_rename_once()
        st = _read("owner_statements.json")
        self.assertIn(NEW + "|2026-06", st)
        self.assertIn(NEW + "|2026-07", st)
        self.assertNotIn(OLD + "|2026-06", st)
        self.assertNotIn(OLD + "|2026-07", st)
        self.assertEqual(st[NEW + "|2026-07"]["owner"], NEW)
        self.assertEqual(st[NEW + "|2026-07"]["status"], "opened")   # status preserved
        tm = _read("owner_terms.json")
        self.assertEqual(tm["owners"][NEW]["phone"], "966500000000")
        self.assertNotIn(OLD, tm["owners"])
        self.assertEqual(tm["units"]["103 nrjs"]["contract_from"], "2026-01-01")

    def test_portal_cache_dropped_for_both_names(self):
        bot._owner_rename_once()
        left = [k for k in bot._owner_portal_cache if k[0] in (OLD, NEW)]
        self.assertEqual(left, [], "a stale cached report would serve the old name")

    # ---------- R2: her live link keeps working ----------
    def test_share_token_survives(self):
        bot._owner_rename_once()
        self.assertNotIn(OLD, bot._owner_links)
        self.assertEqual(bot._owner_links[NEW]["token"], "tok-najla-live")
        self.assertEqual(bot._owner_links[NEW]["opens"], 4)
        self.assertEqual(_read("owner_links.json")[NEW]["token"], "tok-najla-live")

    # ---------- R3: published money is frozen ----------
    def test_published_snapshot_name_only(self):
        bot._owner_rename_once()
        pub = _read("owner_statements.json")[NEW + "|2026-07"]["published"]
        snap = pub["snapshot"]
        self.assertEqual(snap["owner"], NEW)
        self.assertEqual(pub["version"], 2)
        self.assertEqual(pub["at"], "2026-08-02T09:00:00")
        self.assertEqual(pub["basis"], "normal")
        expect = json.loads(json.dumps(SNAPSHOT))
        expect["owner"] = NEW
        self.assertEqual(snap, expect, "a number moved — publish snapshots are frozen")

    # ---------- R4: exactly once ----------
    def test_runs_once_and_is_marked(self):
        self.assertTrue(bot._owner_rename_once())
        self.assertIn("rename-najla-2026-08",
                      _read("owner_registry_migrations.json"))
        # a later deliberate rename BACK by Faisal must survive the next boot
        bot._owner_registry["103 nrjs"]["owner"] = "اسم غيّره فيصل بيده"
        self.assertFalse(bot._owner_rename_once())
        self.assertEqual(bot._owner_registry["103 nrjs"]["owner"], "اسم غيّره فيصل بيده")

    # ---------- R5: unresolvable → change nothing, stay unmarked ----------
    def test_missing_owner_changes_nothing(self):
        for k in ("103 nrjs",):
            bot._owner_registry[k]["owner"] = OTHER
        _write("owner_registry.json", bot._owner_registry)
        before = _read("owner_statements.json")
        self.assertFalse(bot._owner_rename_once())
        self.assertEqual(_read("owner_statements.json"), before)
        self.assertNotIn("rename-najla-2026-08",
                         bot._load_json("owner_registry_migrations.json", []) or [])

    def test_ambiguous_owner_changes_nothing(self):
        # two owners both carrying every token of the old name → refuse to guess
        bot._owner_registry["x1"] = {"apartment": "X1", "owner": "نجلاء عبدالله القاسم",
                                     "mgmt_pct": 20.0, "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_registry["x2"] = {"apartment": "X2", "owner": "نجلاء سعد القاسم",
                                     "mgmt_pct": 20.0, "cleaning": {"type": "ours", "amount": 0}}
        del bot._owner_registry["103 nrjs"]
        _write("owner_registry.json", bot._owner_registry)
        self.assertFalse(bot._owner_rename_once())
        self.assertEqual(bot._owner_registry["x1"]["owner"], "نجلاء عبدالله القاسم")
        self.assertEqual(bot._owner_registry["x2"]["owner"], "نجلاء سعد القاسم")

    def test_resolves_a_longer_single_match(self):
        # «نجلاء عبدالله القاسم» — one owner, every token present → safe to rename
        bot._owner_registry["103 nrjs"]["owner"] = "نجلاء عبدالله القاسم"
        _write("owner_registry.json", bot._owner_registry)
        bot._owner_links["نجلاء عبدالله القاسم"] = bot._owner_links.pop(OLD)
        self.assertTrue(bot._owner_rename_once())
        self.assertEqual(bot._owner_registry["103 nrjs"]["owner"], NEW)
        self.assertEqual(bot._owner_links[NEW]["token"], "tok-najla-live")

    def test_finance_caches_are_dropped(self):
        """finance.owners memoizes both files in module globals. If those aren't
        dropped, the ERP keeps serving the OLD name until the next restart."""
        from finance import api as fapi, owners as fo
        fapi.B = bot                          # what finance.wire() does at boot
        fo._stmt_cache["v"] = None
        fo._terms_cache["v"] = None
        fo._stmt_store()                      # prime both caches with the old name
        fo._terms_store()
        self.assertIn(OLD + "|2026-07", fo._stmt_cache["v"])
        bot._owner_rename_once()
        self.assertIsNone(fo._stmt_cache["v"], "stale statement cache = old name in the ERP")
        self.assertIsNone(fo._terms_cache["v"], "stale terms cache = her phone lost")
        self.assertIn(NEW + "|2026-07", fo._stmt_store())   # re-reads the moved file
        self.assertIsNotNone(fo.stmt_rec(NEW, "2026-07"))
        fo._stmt_cache["v"] = None
        fo._terms_cache["v"] = None

    # ---------- R6: nobody else moves ----------
    def test_other_owner_untouched(self):
        bot._owner_rename_once()
        self.assertEqual(bot._owner_registry["d7"]["owner"], OTHER)
        self.assertEqual(bot._unit_owners["D7"], OTHER)
        self.assertEqual(bot._owner_links[OTHER]["token"], "tok-batool")
        self.assertIn(OTHER + "|2026-07", _read("owner_statements.json"))
        self.assertIn(OTHER, _read("owner_terms.json")["owners"])
        self.assertIn((OTHER, "2026-07"), bot._owner_portal_cache)


if __name__ == "__main__":
    unittest.main(verbosity=2)
