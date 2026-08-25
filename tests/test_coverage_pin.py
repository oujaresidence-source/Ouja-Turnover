# -*- coding: utf-8 -*-
"""The pin endpoint is the only WRITE the coverage tab has — lock its refusals.

A pin is trusted downstream by the dispatch and ETA code, so a bad one sends a cleaner
to the wrong building. Every case that must be refused is asserted here.
"""

import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import coverage_study as C
from coverage_study import routes


class _Req:
    def __init__(self, body, role="admin"):
        self._b = body
        self.role = role

    async def json(self):
        return self._b


def _json(obj, status=200):
    d = dict(obj)
    d["_status"] = status
    return d


class TestPin(unittest.TestCase):
    def setUp(self):
        self.saved = {}
        self.store = {9: {"id": 9, "internal_name": "برج رافال 3902", "active": True}}
        self.role = "admin"

        def set_pin(lid, link, lat, lng):
            self.saved[lid] = {"link": link, "lat": lat, "lng": lng}
            return True

        C.wire({
            "json_response": _json, "dash_auth": lambda r: True,
            "req_role": lambda r: self.role,
            "listings": lambda: list(self.store.values()),
            "teams": lambda: [], "guide_units": lambda: [], "status_log": lambda: [],
            "reports": lambda: [], "photos": lambda: [],
            "load_json": lambda n, d: d, "save_json": lambda n, o: None,
            "maps_key": lambda: "", "set_pin": set_pin,
        })

    def _pin(self, link, lid=9):
        return asyncio.run(routes.api_pin(_Req({"lid": lid, "link": link})))

    def test_coordinate_link_is_saved(self):
        r = self._pin("https://maps.google.com/?q=24.7924934,46.6326583")
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(self.saved[9]["lat"], 24.7924934, places=5)

    def test_plus_code_text_is_decoded_offline_and_saved(self):
        r = self._pin("QJVM+4MM, King Fahd Rd, As Sahafah, Riyadh")
        self.assertTrue(r["ok"])
        self.assertTrue(24.0 < self.saved[9]["lat"] < 25.5)

    def test_nonsense_is_refused_and_nothing_is_written(self):
        r = self._pin("hello there")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "unresolvable")
        self.assertEqual(self.saved, {})

    def test_a_location_outside_riyadh_is_refused(self):
        # A link pasted from the wrong browser tab must not land on the map.
        r = self._pin("https://maps.google.com/?q=51.5074,-0.1278")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "out_of_range")
        self.assertEqual(self.saved, {})

    def test_empty_link_is_refused(self):
        r = self._pin("   ")
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "empty_link")

    def test_bad_listing_id_is_refused(self):
        r = asyncio.run(routes.api_pin(_Req({"lid": "abc", "link": "x"})))
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "bad_lid")

    def test_viewer_cannot_write(self):
        self.role = "viewer"
        r = self._pin("https://maps.google.com/?q=24.79,46.63")
        self.assertFalse(r["ok"])
        self.assertEqual(self.saved, {})

    def test_ops_can_write(self):
        self.role = "ops"
        r = self._pin("https://maps.google.com/?q=24.79,46.63")
        self.assertTrue(r["ok"])


if __name__ == "__main__":
    unittest.main()
