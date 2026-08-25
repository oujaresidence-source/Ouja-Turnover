# -*- coding: utf-8 -*-
"""
The HTTP boundary. The owner rule has to hold where it is actually attacked: an
unauthenticated POST from the guest guide.

    POST /api/decor/inquire  → one lead. Zero orders. Zero cakes. Zero assignments.
    Only POST /api/decor/lead/open (login + admin/ops) can ever produce an order.

Run: python3 -m unittest tests.test_decor_routes
"""

import asyncio
import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                       # noqa: E402
from decor import db, host, packs, routes         # noqa: E402


class _Content:
    def __init__(self, raw):
        self._raw = raw

    async def read(self, n=-1):
        return self._raw if n < 0 else self._raw[:n]


class _Req:
    """Just enough aiohttp request for these handlers."""
    def __init__(self, body=None, role="admin"):
        self.content = _Content(json.dumps(body or {}, ensure_ascii=False).encode("utf-8"))
        self.role = role
        self.method = "POST"


def _json(data, status=200):
    return {"status": status, "data": data}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class DecorRoutesCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="decorroutes_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        db.reset_init_cache()
        asyncio.set_event_loop(asyncio.new_event_loop())
        host.wire({
            "json_response": _json,
            "dash_auth": lambda r: True,
            "req_role": lambda r: getattr(r, "role", "viewer"),
            "actor": lambda r: "ناصر",
            "now": lambda: datetime.datetime(2026, 8, 1, 10, 0),
            "guide_units": lambda: [{"slug": "b14", "listing_id": 900,
                                     "listing_name": "Ouja | Boulevard 2BR"}],
            "inhouse": lambda day: [{"id": 5551, "listingMapId": 900, "guestName": "أبو خالد",
                                     "arrivalDate": "2026-08-01", "departureDate": "2026-08-04"}],
            "notify": None,
        })

    def setUp(self):
        routes._rate.clear()
        routes._ctx_cache.update({"at": 0, "units": {}, "inhouse": []})


class TestPublicInquire(DecorRoutesCase):

    def test_a_guest_tap_creates_a_lead_and_nothing_else(self):
        before = db.counts()
        r = run(routes.inquire(_Req({"slug": "b14", "pack_id": "diamond", "lang": "ar"})))
        self.assertEqual(r["status"], 200)
        self.assertTrue(r["data"]["ok"])
        after = db.counts()
        self.assertEqual(after["leads_total"], before["leads_total"] + 1)
        self.assertEqual(after["orders"], before["orders"])
        self.assertEqual(after["cakes"], before["cakes"])

    def test_the_second_tap_within_the_window_is_the_same_interest(self):
        run(routes.inquire(_Req({"slug": "c2-nfl", "pack_id": "silver"})))
        before = db.counts()["leads_total"]
        r = run(routes.inquire(_Req({"slug": "c2-nfl", "pack_id": "silver"})))
        self.assertTrue(r["data"].get("dedupe"))
        self.assertEqual(db.counts()["leads_total"], before)

    def test_a_flood_is_capped_and_still_creates_no_work(self):
        before = db.counts()
        for i in range(40):
            run(routes.inquire(_Req({"slug": "flood-unit", "pack_id": "bronze"})))
        after = db.counts()
        self.assertLessEqual(after["leads_total"] - before["leads_total"], 2)   # dedupe + rate cap
        self.assertEqual(after["orders"], before["orders"])

    def test_rubbish_input_is_swallowed_quietly(self):
        before = db.counts()["leads_total"]
        for body in ({}, {"slug": "../etc/passwd", "pack_id": "diamond"},
                     {"slug": "b14", "pack_id": "no_such_pack"},
                     {"slug": "b14"}, {"pack_id": "diamond"}):
            r = run(routes.inquire(_Req(body)))
            self.assertEqual(r["status"], 200)          # a guest never sees an error
        self.assertEqual(db.counts()["leads_total"], before)


class TestTheGate(DecorRoutesCase):

    def _fresh_lead(self, slug, pack="diamond"):
        """Straight to the table: the public endpoint's dedupe window is verified in
        TestPublicInquire, and re-using it here would make every test share one lead."""
        return db.create_lead(slug, pack)

    def test_a_viewer_cannot_open_a_request(self):
        lead = self._fresh_lead("viewer-unit")
        before = db.counts()["orders"]
        r = run(routes.lead_open(_Req({"lead_id": lead["id"]}, role="viewer")))
        self.assertEqual(r["status"], 403)
        self.assertEqual(db.counts()["orders"], before)

    def test_opening_is_refused_while_the_apartment_lacks_the_feature(self):
        db.set_unit_features("gate-nopool", ["jacuzzi"], by="ناصر")
        lead = self._fresh_lead("gate-nopool")
        before = db.counts()["orders"]
        r = run(routes.lead_open(_Req({"lead_id": lead["id"]})))
        self.assertFalse(r["data"]["ok"])
        self.assertEqual(r["data"]["error"], "capability")
        self.assertIn("مسبح", r["data"]["message"])
        self.assertEqual(len(r["data"]["affected_items"]), 2)
        self.assertEqual(db.counts()["orders"], before)          # nothing was created
        self.assertEqual(db.lead(lead["id"])["status"], "new")     # still open for a decision

    def test_an_override_needs_a_reason(self):
        db.set_unit_features("gate-reason", ["jacuzzi"], by="ناصر")
        lead = self._fresh_lead("gate-reason")
        before = db.counts()["orders"]
        r = run(routes.lead_open(_Req({"lead_id": lead["id"], "override_kind": "accept_gap"})))
        self.assertFalse(r["data"]["ok"])
        self.assertEqual(r["data"]["error"], "override_needs_who_and_why")
        self.assertEqual(db.counts()["orders"], before)          # nothing was created

    def test_accept_gap_opens_a_stamped_order_with_guest_context_filled_in(self):
        db.set_unit_features("b14", ["jacuzzi"], by="ناصر")
        lead = self._fresh_lead("b14")
        r = run(routes.lead_open(_Req({"lead_id": lead["id"], "override_kind": "accept_gap",
                                       "reason": "الضيف موافق بدون مسبح"})))
        self.assertTrue(r["data"]["ok"])
        o = r["data"]["order"]
        self.assertIn("مسبح", o["capability_stamp"])
        self.assertEqual(o["overridden_by"], "ناصر")
        self.assertEqual(o["guest_name"], "أبو خالد")              # from the in-house query
        self.assertEqual(o["deadline_at"], "2026-08-01T15:00")     # check-in, 3 PM default
        self.assertEqual(o["cake"]["due_at"], "2026-07-31T15:00")  # 24h earlier, own job
        self.assertEqual(db.lead(lead["id"])["status"], "opened")

    def test_correction_opens_a_clean_order_and_the_unit_stops_asking(self):
        db.set_unit_features("gate-fix", ["jacuzzi"], by="ناصر")
        lead = self._fresh_lead("gate-fix")
        r = run(routes.lead_open(_Req({"lead_id": lead["id"], "override_kind": "correction",
                                       "reason": "القائمة غلط"})))
        self.assertTrue(r["data"]["ok"])
        self.assertEqual(r["data"]["order"]["capability_stamp"], "")
        self.assertIn("pool", db.unit_features("gate-fix"))
        lead2 = self._fresh_lead("gate-fix")
        r2 = run(routes.lead_open(_Req({"lead_id": lead2["id"]})))       # no override needed now
        self.assertTrue(r2["data"]["ok"])


class TestDispatchGate(DecorRoutesCase):

    _n = [0]

    def _open_bronze(self):
        self._n[0] += 1
        lead = db.create_lead("bronze-unit-%d" % self._n[0], "bronze")
        r = run(routes.lead_open(_Req({"lead_id": lead["id"], "event_at": "2026-08-05T21:00"})))
        return r["data"]["order"]

    def test_dispatch_is_refused_and_says_exactly_what_is_missing(self):
        o = self._open_bronze()
        r = run(routes.order_dispatch(_Req({"order_id": o["id"]})))
        self.assertFalse(r["data"]["ok"])
        self.assertEqual(r["data"]["error"], "incomplete")
        keys = [m["key"] for m in r["data"]["missing_inputs"]]
        self.assertEqual(sorted(keys), ["bed_letters", "occasion", "phrases"])
        self.assertIn("الأحرف على السرير", r["data"]["ask_text"])
        self.assertEqual(db.order(o["id"])["state"], "awaiting_guest")

    def test_the_order_becomes_ready_only_when_everything_is_in(self):
        o = self._open_bronze()
        run(routes.order_inputs(_Req({"order_id": o["id"],
                                      "inputs": {"phrases": "٥", "bed_letters": "ن"}})))
        self.assertEqual(db.order(o["id"])["state"], "awaiting_guest")
        run(routes.order_inputs(_Req({"order_id": o["id"], "inputs": {"occasion": "زواج"}})))
        self.assertEqual(db.order(o["id"])["state"], "awaiting_guest")   # price still missing
        run(routes.order_update(_Req({"order_id": o["id"], "final_price_sar": 700})))
        self.assertEqual(db.order(o["id"])["state"], "ready")
        r = run(routes.order_dispatch(_Req({"order_id": o["id"]})))
        self.assertTrue(r["data"]["ok"])
        self.assertEqual(db.order(o["id"])["state"], "dispatched")

    def test_the_event_time_wins_over_check_in(self):
        o = self._open_bronze()
        self.assertEqual(o["deadline_at"], "2026-08-05T21:00")
        self.assertEqual(o["work_start_at"], "2026-08-05T20:00")     # bronze = 60 minutes


class TestFeaturesSheet(DecorRoutesCase):

    def test_the_owners_csv_imports_as_sent(self):
        csv = ("رمز الشقة,اسم الشقة,مسبح؟,جاكوزي؟,بانيو؟,ملاحظة\n"
               "h8-vlg,Ouja | Bohemian Escape,نعم,,نعم,\n"
               "c2-nfl,Biggest 2BR,,نعم,نعم,\n"
               "not a slug!,x,نعم,,,\n")
        r = run(routes.features_import(_Req({"csv": csv})))
        self.assertTrue(r["data"]["ok"])
        self.assertEqual(r["data"]["saved"], 2)
        self.assertEqual(r["data"]["skipped"], 2)          # header row + the bad slug
        self.assertEqual(sorted(db.unit_features("h8-vlg")), ["bathtub", "pool"])
        self.assertEqual(sorted(db.unit_features("c2-nfl")), ["bathtub", "jacuzzi"])

    def test_a_viewer_cannot_edit_the_sheet(self):
        r = run(routes.features_set(_Req({"slug": "b14", "features": ["pool"]}, role="viewer")))
        self.assertEqual(r["status"], 403)


if __name__ == "__main__":
    unittest.main()
