# -*- coding: utf-8 -*-
"""
The synthetic run: one fake unit through open -> results -> close, with FAKE host caps,
asserting by hand the score, the quote total and the ticket fan-out. No web server.

Unit: 2 bedrooms, 2 bathrooms, 3 beds, owner «أبو خالد» 0500000000, pool known = no.
Failures:
    c21.mattress  product/owner   qty default 3 x 900 = 2700
    c27.toilet    works/owner     1 x 350 = 350            -> owner quote 3050 (works separated)
    c08.detergents product/ouja   1 x 60                   -> ONE purchase ticket, 60 SAR
    c33.bath_vent works/ouja (billed_to overridden)        -> ONE maintenance ticket
    c39.evac_plan document                                 -> onboarding s5.9
    c03.elevator  structural                               -> blocker, never a line
    c13.wifi      answered by the wifi bridge = missing     -> 1 x 250 owner line
Score: 61 components, 7 missing -> 54 available, compliance 88.5, inspected 100.

Run: python3 -m unittest tests.test_mot_flow
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                      # noqa: E402
from mot import catalogue as C, db, host, routes  # noqa: E402

LID = 777


class FakeHost:
    def __init__(self):
        self.quotes, self.tickets, self.onb, self.features, self.logs = [], [], [], {}, []

    def caps(self, features=None):
        self.features = features
        return {
            "listings": lambda: {LID: "Ouja | اختبار 777", 778: "Ouja | 778"},
            "unit_meta": lambda lid: {"bedrooms": 2, "bathrooms": 2, "beds": 3,
                                      "owner": "أبو خالد", "owner_phone": "0500000000"},
            "unit_features": lambda lid: self.features,
            "set_unit_features": lambda lid, feats, by: self.features.__class__ and setattr(self, "features", list(feats)),
            "wifi_status": lambda lid: False,
            "save_quote": self._save_quote,
            "ticket_create": self._ticket,
            "onb_license_tasks": self._onb,
            "log_event": lambda cat, text: self.logs.append(text),
            "public_base": lambda: "https://x.test",
            "state_dir": tempfile.mkdtemp(prefix="motstate_"),
        }

    def _save_quote(self, payload):
        self.quotes.append(payload)
        total = sum(i["qty"] * i["price"] for i in payload["items"])
        return {"id": "q_1", "number": "OJ-202609-001", "totals": {"grand_total": total}}

    def _ticket(self, title, **kw):
        self.tickets.append(dict(kw, title=title))
        return {"id": "T%d" % len(self.tickets)}

    def _onb(self, lid, keys):
        self.onb.append((lid, keys))
        return {"project_id": 42}


class FlowCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="motflow_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self.fh = FakeHost()
        host.wire(self.fh.caps(features=[]))
        for k, v in {"c21.mattress": 900, "c27.toilet": 350, "c08.detergents": 60,
                     "c13.wifi": 250, "c33.bath_vent": 500}.items():
            db.set_price(k, v, by="t")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def open(self, **p):
        return routes.core_open(dict(listing_id=LID, **p), actor="فيصل")

    def fill(self, rid, fails, billed=None):
        for c in C.components(False):
            if c["key"] == C.WIFI_KEY:
                continue
            routes.core_result({"id": rid, "comp_key": c["key"],
                                "state": "missing" if c["key"] in fails else "available",
                                "billed_to": (billed or {}).get(c["key"])}, actor="فيصل")


class TestOpen(FlowCase):
    def test_unknown_pool_asks_once_then_teaches_the_sheet(self):
        host.wire(self.fh.caps(features=None))
        st, body = self.open()
        self.assertEqual(st, 409)
        self.assertTrue(body["need_pool_answer"])
        st, body = self.open(has_pool=True)
        self.assertEqual(st, 200)
        self.assertEqual(self.fh.features, ["pool"])
        self.assertEqual(body["round"]["denominator"], 67)
        self.assertEqual(body["round"]["pool_source"], "inspector")

    def test_known_no_pool_is_61_from_decor(self):
        st, body = self.open()
        self.assertEqual((st, body["round"]["denominator"], body["round"]["pool_source"]), (200, 61, "decor"))

    def test_override_needs_a_reason(self):
        self.assertEqual(self.open(has_pool=True)[0], 400)
        st, body = self.open(has_pool=True, pool_reason="المسبح مشترك بالمجمع")
        self.assertEqual((st, body["round"]["pool_source"], body["round"]["denominator"]), (200, "override", 67))

    def test_wifi_is_prefilled_from_the_bridge(self):
        st, body = self.open()
        r = db.results(body["id"])[C.WIFI_KEY]
        self.assertEqual((r["state"], r["source"]), ("missing", "wifi"))

    def test_second_open_is_refused_in_arabic(self):
        self.open()
        st, body = self.open()
        self.assertEqual(st, 409)
        self.assertEqual(body["error"], routes.ALREADY_OPEN)

    def test_unknown_unit_refused(self):
        self.assertEqual(routes.core_open({"listing_id": 1}, actor="x")[0], 404)


class TestResultRules(FlowCase):
    def test_wifi_override_needs_a_reason(self):
        rid = self.open()[1]["id"]
        st, _ = routes.core_result({"id": rid, "comp_key": C.WIFI_KEY, "state": "available"}, actor="x")
        self.assertEqual(st, 400)
        st, body = routes.core_result({"id": rid, "comp_key": C.WIFI_KEY, "state": "available",
                                       "note": "راوتر المالك شغال"}, actor="x")
        self.assertEqual((st, body["result"]["source"]), (200, "override"))

    def test_pool_component_refused_on_a_no_pool_round(self):
        rid = self.open()[1]["id"]
        st, _ = routes.core_result({"id": rid, "comp_key": "c46.pool_rescue", "state": "missing"}, actor="x")
        self.assertEqual(st, 400)

    def test_phone_door_writes_only_state_qty_note(self):
        rid = self.open()[1]["id"]
        tok = routes.core_token({"id": rid}, actor="x")[1]["token"]
        st, body = routes.core_check_result({"token": tok, "comp_key": "c21.mattress", "state": "missing",
                                             "qty": 2, "billed_to": "ouja", "note": "مهترئة"})
        self.assertEqual(st, 200)
        r = db.results(rid)["c21.mattress"]
        self.assertEqual((r["qty"], r["billed_to"], r["note"]), (2, "", "مهترئة"))
        self.assertEqual(routes.core_check_get(tok)[0], 200)
        self.assertNotIn("prices", routes.core_check_get(tok)[1])


class TestClose(FlowCase):
    FAILS = {"c21.mattress", "c27.toilet", "c08.detergents", "c33.bath_vent", "c39.evac_plan", "c03.elevator"}

    def test_partial_round_cannot_close(self):
        rid = self.open()[1]["id"]
        st, body = routes.core_close({"id": rid}, actor="فيصل")
        self.assertEqual(st, 409)
        self.assertEqual(body["not_inspected"], 60)

    def test_the_whole_fanout_by_hand(self):
        rid = self.open()[1]["id"]
        self.fill(rid, self.FAILS, billed={"c33.bath_vent": "ouja"})
        st, body = routes.core_close({"id": rid}, actor="فيصل")
        self.assertEqual(st, 200, body)
        sc = body["score"]
        self.assertEqual((sc["available"], sc["missing"], sc["not_inspected"]), (54, 7, 0))
        self.assertEqual((sc["compliance_pct"], sc["inspected_pct"]), (88.5, 100.0))
        # owner quote: mattress 3x900 + wifi 250 + toilet 350 (works, separated)
        self.assertEqual(len(self.fh.quotes), 1)
        qp = self.fh.quotes[0]
        self.assertEqual((qp["client_name"], qp["client_phone"]), ("أبو خالد", "0500000000"))
        descs = [i["description"] for i in qp["items"]]
        self.assertEqual(sum(i["qty"] * i["price"] for i in qp["items"]), 2700 + 250 + 350)
        self.assertTrue(any("أعمال وتركيبات" in d for d in descs))
        self.assertLess(descs.index(next(d for d in descs if "مراتب" in d)),
                        descs.index(next(d for d in descs if "أعمال" in d)))
        self.assertFalse(any("المصعد" in d or "الإخلاء" in d or "منظفات" in d for d in descs))
        # tickets: ONE purchase (proc-shaped) + ONE maintenance
        cats = [t["category"] for t in self.fh.tickets]
        self.assertEqual(sorted(cats), ["صيانة", "مشتريات"])
        proc = next(t for t in self.fh.tickets if t["category"] == "مشتريات")
        for needle in ("الوحدات:", "السبب:", "البنود:", "المبلغ: 60", "مواد ومنظفات"):
            self.assertIn(needle, proc["description"])
        self.assertEqual(proc["source_ref"], "mot:%d" % rid)
        self.assertEqual(proc["cost"], 60.0)
        # documents -> onboarding
        self.assertEqual(self.fh.onb, [(LID, ["s5.9"])])
        # blocker recorded, never a line
        self.assertEqual(body["fanout"]["blocked"], ["c03.elevator"])
        # frozen on the round
        r = db.round_(rid)
        self.assertEqual((r["compliance_pct"], r["quote_id"]), (88.5, "q_1"))
        self.assertTrue(r["recheck_due"] > r["closed_at"][:10])
        self.assertTrue(any("88.5" in l for l in self.fh.logs))

    def test_unpriced_line_blocks_close_until_confirmed(self):
        rid = self.open()[1]["id"]
        self.fill(rid, {"c16.tv"})
        st, body = routes.core_close({"id": rid}, actor="x")
        self.assertEqual((st, body["unpriced"]), (409, ["c16.tv"]))
        st, body = routes.core_close({"id": rid, "allow_unpriced": True}, actor="x")
        self.assertEqual(st, 200)

    def test_clean_round_produces_nothing(self):
        rid = self.open()[1]["id"]
        routes.core_result({"id": rid, "comp_key": C.WIFI_KEY, "state": "available", "note": "ok"}, actor="x")
        self.fill(rid, set())
        st, body = routes.core_close({"id": rid}, actor="x")
        self.assertEqual(st, 200)
        self.assertEqual((self.fh.quotes, self.fh.tickets, self.fh.onb), ([], [], []))
        self.assertEqual(body["score"]["compliance_pct"], 100.0)

    def test_portfolio_reads_the_closed_round(self):
        rid = self.open()[1]["id"]
        self.fill(rid, self.FAILS, billed={"c33.bath_vent": "ouja"})
        routes.core_close({"id": rid}, actor="x")
        st, body = routes.core_portfolio()
        row = next(r for r in body["rows"] if r["listing_id"] == LID)
        self.assertEqual(row["latest"]["compliance_pct"], 88.5)
        self.assertEqual(row["blockers"], 1)
        self.assertEqual(row["outstanding_sar"], 2700 + 250 + 350 + 60)
        self.assertEqual(body["summary"]["blocked"], 1)
        self.assertEqual(body["summary"]["never"], 1)

    def test_report_gate(self):
        rid = self.open()[1]["id"]
        self.assertEqual(routes.core_report(rid)[0], 409)
        self.fill(rid, set())
        routes.core_result({"id": rid, "comp_key": C.WIFI_KEY, "state": "available", "note": "ok"}, actor="x")
        routes.core_close({"id": rid}, actor="x")
        st, body = routes.core_report(rid)
        self.assertEqual(st, 200)
        self.assertIn("سجل مطابقة", body["html"])
        self.assertIn("100.0", body["html"])


if __name__ == "__main__":
    unittest.main()
