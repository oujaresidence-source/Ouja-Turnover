# -*- coding: utf-8 -*-
"""
The catalogue and the seeder.

The seeder's promise is the one worth guarding: it is ADDITIVE FOREVER. Re-running it can
never duplicate a row, never reopen a resolution, and never overwrite a reason a human typed.
A resolution is a decision, and a decision is not data to be recomputed — the same rule that
governs a typed manual expense in the ERP.

Run: python3 -m unittest tests.test_onb_catalogue
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                      # noqa: E402
from onboarding import catalogue, db             # noqa: E402


BASE = {"client_name": "عبدالله", "client_type": "owner", "client_whatsapp": "0555",
        "unit_name": "Ouja | الملقا 1", "district": "الملقا", "unit_kind": "tower",
        "bedrooms": 2, "furnish_state": "unfurnished"}


class TestCatalogueShape(unittest.TestCase):
    """Pure — no database."""

    def test_10a_keys_are_unique(self):
        keys = [r[0] for r in catalogue.CATALOGUE]
        self.assertEqual(len(keys), len(set(keys)))

    def test_10b_every_stage_is_declared(self):
        declared = set(catalogue.STAGE_ORDER)
        for r in catalogue.CATALOGUE:
            self.assertIn(r[1], declared, "task %s sits in an undeclared stage %s" % (r[0], r[1]))

    def test_10c_owner_role_is_a_label_and_there_is_no_delegable_field(self):
        """Build spec R7. The catalogue rows are 6-tuples on purpose: there is nowhere to put
        a per-task delegation restriction, so one cannot be added by accident. Every task is
        delegable to either of the project's two people."""
        for r in catalogue.CATALOGUE:
            self.assertEqual(len(r), 6, "catalogue row %s grew a field — R7 is at risk" % r[0])
            self.assertIn(r[4], catalogue.OWNER_ROLES)
        self.assertNotIn("delegable", catalogue.__dict__)

    def test_10d_no_ongoing_task_can_gate_a_unit(self):
        """`ongoing` is company work, never seeded onto a project — a gate flag there would
        block every publish forever."""
        for r in catalogue.ongoing_rows():
            self.assertEqual(r[5], 0, "ongoing task %s is marked as a gate" % r[0])

    def test_10e_the_counts_the_owner_signed_off(self):
        self.assertEqual(len(catalogue.rows_for_seed()), 63)
        self.assertEqual(len(catalogue.ongoing_rows()), 5)


class SeedCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="onbcat_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        db.reset_init_cache()

    def _mk(self, **over):
        f = dict(BASE)
        f.update(over)
        return db.create_project(f, "tester")

    def _res(self, pid):
        return {t["catalogue_key"]: t for t in db.tasks(pid)}


class TestSeeding(SeedCase):

    def test_11_a_furnished_unit_skips_the_fit_out_but_not_the_licence(self):
        p = self._mk(furnish_state="furnished")
        rows = self._res(p["id"])
        for i in range(1, 13):
            k = "s4.%d" % i
            self.assertEqual(rows[k]["resolution"], "na", "%s should be n/a on a furnished unit" % k)
            self.assertTrue(rows[k]["reason"], "%s was marked n/a with no reason" % k)
        for i in range(1, 8):
            self.assertEqual(rows["s5.%d" % i]["resolution"], "open")

    def test_12_an_owner_is_not_a_tenant_and_not_a_prospect(self):
        rows = self._res(self._mk(client_type="owner")["id"])
        self.assertEqual(rows["s1.6"]["resolution"], "na")
        self.assertEqual(rows["s1.7"]["resolution"], "na")
        self.assertIn("مالك", rows["s1.6"]["reason"])
        self.assertEqual(rows["s1.5"]["resolution"], "na")
        # a tenant keeps the sublet checks OPEN — they are the whole point for that client type
        trows = self._res(self._mk(client_type="tenant")["id"])
        self.assertEqual(trows["s1.6"]["resolution"], "open")
        self.assertEqual(trows["s1.7"]["resolution"], "open")

    def test_13_reseeding_adds_nothing_and_overwrites_no_resolution(self):
        p = self._mk()
        before = db.tasks(p["id"])
        t = [x for x in before if x["catalogue_key"] == "s2.6"][0]
        db.resolve_task(t["id"], "blocked", "العميل مسافر", "ناصر")
        db.seed_tasks(p["id"])
        after = db.tasks(p["id"])
        self.assertEqual(len(after), len(before), "re-seeding duplicated rows")
        again = [x for x in after if x["catalogue_key"] == "s2.6"][0]
        self.assertEqual(again["resolution"], "blocked")
        self.assertEqual(again["reason"], "العميل مسافر")
        self.assertEqual(again["resolved_by"], "ناصر")

    def test_14_flipping_furnish_state_touches_only_open_tasks(self):
        p = self._mk(furnish_state="unfurnished")
        rows = self._res(p["id"])
        self.assertEqual(rows["s4.1"]["resolution"], "open")
        # a human decides s4.2 is DONE before the unit is reclassified as furnished
        db.resolve_task(rows["s4.2"]["id"], "done", "", "نورة")
        db.update_project(p["id"], furnish_state="furnished")
        db.apply_auto_na(p["id"])
        after = self._res(p["id"])
        self.assertEqual(after["s4.1"]["resolution"], "na")      # was open -> auto n/a
        self.assertEqual(after["s4.2"]["resolution"], "done")    # human's call survives
        self.assertEqual(after["s4.2"]["resolved_by"], "نورة")

    def test_14b_linking_a_fit_out_project_reopens_nothing_but_seeds_correctly(self):
        p = self._mk(pmo_project_id="PMO-7")
        self.assertEqual(self._res(p["id"])["s4.13"]["resolution"], "open")
        q = self._mk()
        self.assertEqual(self._res(q["id"])["s4.13"]["resolution"], "na")


if __name__ == "__main__":
    unittest.main()
