# -*- coding: utf-8 -*-
"""
A FRESH apartment (not in Hostaway yet) is an onboarding project, inspected under -project_id.

    it shows in the portfolio flagged «قيد الضم», opens and closes like any unit
    documents fan out to ITS project, tickets carry no bogus Hostaway id
    the day the project gets a listing_id, its rounds move to that id — history survives
    «شقة جديدة» validates like «ضم الوحدات» and never opens a half-filled project

Run: python3 -m unittest tests.test_mot_fresh_unit
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                      # noqa: E402
from mot import catalogue as C, db, host, routes  # noqa: E402


class FreshCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="motfresh_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self.projects = [{"project_id": 9, "unit_name": "Ouja | برج الياسمين 12", "bedrooms": 1,
                          "client_name": "أم سارة", "client_whatsapp": "0501112222", "district": "الملقا",
                          "amenities": None, "listing_id": None}]
        self.created, self.onb, self.tickets = [], [], []

        def create(fields, by):
            self.created.append(fields)
            pr = dict(fields, project_id=50, id=50, listing_id=None)
            self.projects.append(pr)
            return pr

        host.wire({
            "listings": lambda: {300: "Ouja | 300"},
            "unit_meta": lambda lid: {"bedrooms": 2, "bathrooms": 2, "beds": 2, "owner": "x", "owner_phone": ""},
            "unit_features": lambda lid: [], "set_unit_features": lambda *a: None,
            "wifi_status": lambda lid: True,
            "save_quote": lambda p: {"id": "q", "number": "N", "totals": {"grand_total": 0}},
            "ticket_create": lambda t, **k: (self.tickets.append(k) or {"id": "T"}),
            "onb_license_tasks": lambda lid, keys: (self.onb.append((lid, keys)) or {"project_id": abs(lid)}),
            "onb_fresh_units": lambda: list(self.projects),
            "onb_create_unit": create,
            "log_event": lambda c, t: None, "public_base": lambda: "", "state_dir": self.tmp,
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fill(self, rid, fails=(), pool=False):
        for c in C.components(pool):
            routes.core_result({"id": rid, "comp_key": c["key"],
                                "state": "missing" if c["key"] in fails else "available"}, actor="x")


class TestPortfolioAndOpen(FreshCase):
    def test_fresh_unit_listed_with_negative_id(self):
        st, body = routes.core_portfolio()
        row = next(r for r in body["rows"] if r["listing_id"] == -9)
        self.assertTrue(row["fresh"])
        self.assertEqual(row["project_id"], 9)
        self.assertEqual(body["summary"]["units"], 2)

    def test_open_asks_for_pool_when_amenities_silent(self):
        st, body = routes.core_open({"listing_id": -9}, actor="x")
        self.assertEqual(st, 409)
        self.assertTrue(body["need_pool_answer"])
        st, body = routes.core_open({"listing_id": -9, "has_pool": False}, actor="x")
        self.assertEqual((st, body["round"]["denominator"], body["round"]["pool_source"]), (200, 61, "inspector"))
        # wifi is NOT prefilled for a unit that has no Hostaway id
        self.assertNotIn(C.WIFI_KEY, db.results(body["id"]))

    def test_pool_read_from_amenities(self):
        self.projects[0]["amenities"] = '["pool","gym"]'
        st, body = routes.core_open({"listing_id": -9}, actor="x")
        self.assertEqual((st, body["round"]["denominator"], body["round"]["pool_source"]), (200, 67, "decor"))

    def test_unit_meta_comes_from_the_project(self):
        st, body = routes.core_unit(-9)
        self.assertEqual(body["meta"]["owner"], "أم سارة")
        self.assertEqual(body["meta"]["owner_phone"], "0501112222")
        self.assertEqual(body["meta"]["bedrooms"], 1)
        self.assertTrue(body["meta"]["fresh"])


class TestCloseOnFresh(FreshCase):
    def test_documents_go_to_its_project_and_tickets_carry_no_lid(self):
        rid = routes.core_open({"listing_id": -9, "has_pool": False}, actor="x")[1]["id"]
        self.fill(rid, fails={"c39.evac_plan", "c08.detergents"})
        st, body = routes.core_close({"id": rid, "allow_unpriced": True}, actor="x")
        self.assertEqual(st, 200, body)
        self.assertEqual(self.onb, [(-9, ["s5.9"])])
        self.assertEqual(len(self.tickets), 1)
        self.assertIsNone(self.tickets[0]["lid"])


class TestReconcile(FreshCase):
    def test_rounds_follow_the_apartment_into_hostaway(self):
        rid = routes.core_open({"listing_id": -9, "has_pool": False}, actor="x")[1]["id"]
        self.fill(rid)
        routes.core_close({"id": rid}, actor="x")
        # the project is published and gets its Hostaway id
        self.projects[0]["listing_id"] = 300
        st, body = routes.core_portfolio()
        ids = [r["listing_id"] for r in body["rows"]]
        self.assertNotIn(-9, ids)
        row = next(r for r in body["rows"] if r["listing_id"] == 300)
        self.assertEqual(row["latest"]["compliance_pct"], 100.0)
        self.assertEqual(db.round_(rid)["listing_id"], 300)
        self.assertEqual(db.rounds_for(-9), [])


class TestNewUnit(FreshCase):
    GOOD = {"unit_name": "برج الياسمين 14", "district": "الملقا", "client_name": "أبو علي",
            "client_whatsapp": "0503334444", "bedrooms": 2}

    def test_creates_an_onboarding_project_with_defaults(self):
        st, body = routes.core_new_unit(self.GOOD, actor="فيصل")
        self.assertEqual(st, 200, body)
        self.assertEqual(body["listing_id"], -50)
        f = self.created[0]
        self.assertEqual(f["unit_name"], "Ouja | برج الياسمين 14")
        self.assertEqual((f["client_type"], f["unit_kind"], f["furnish_state"]), ("owner", "compound", "furnished"))
        self.assertNotIn("amenities", f)
        # and it is immediately a unit
        self.assertIn(-50, routes._all_units())

    def test_pool_flag_becomes_an_amenity(self):
        routes.core_new_unit(dict(self.GOOD, has_pool=True), actor="x")
        self.assertEqual(self.created[0]["amenities"], "pool")

    def test_refuses_a_half_filled_project(self):
        for missing in ("district", "client_name", "client_whatsapp", "bedrooms", "unit_name"):
            p = dict(self.GOOD); p.pop(missing)
            st, _ = routes.core_new_unit(p, actor="x")
            self.assertEqual(st, 400, missing)
        self.assertEqual(self.created, [])

    def test_long_name_refused(self):
        st, _ = routes.core_new_unit(dict(self.GOOD, unit_name="ا" * 60), actor="x")
        self.assertEqual(st, 400)


if __name__ == "__main__":
    unittest.main()
