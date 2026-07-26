# -*- coding: utf-8 -*-
"""
Apartment names come from the HOSTAWAY API, not from a stored copy (owner, 2026-07-26).

The slug still has to come from the guide — it is the only identifier the guest's button can
send — but the name a supervisor reads, and the name in the fill-in sheet, is the live
Hostaway one. Hostaway units with no guide page are reported, never silently dropped.

Run: python3 -m unittest tests.test_decor_hostaway_units
"""

import asyncio
import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                        # noqa: E402
from decor import db, host, routes                 # noqa: E402


class _Content:
    def __init__(self, raw):
        self._raw = raw

    async def read(self, n=-1):
        return self._raw if n < 0 else self._raw[:n]


class _Req:
    def __init__(self, body=None, role="admin"):
        self.content = _Content(json.dumps(body or {}, ensure_ascii=False).encode("utf-8"))
        self.role = role
        self.method = "GET"


class _Resp:
    def __init__(self, body=None, content_type="", headers=None, **kw):
        self.body = body
        self.content_type = content_type
        self.headers = headers or {}


class _Web:
    Response = _Resp


def _json(data, status=200):
    return {"status": status, "data": data}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


LIVE = {900: "Ouja | Boulevard 2BR + Pool", 901: "Ouja | Nuzha 101A",
        902: "Ouja | Not In The Guide Yet"}


class TestHostawayNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="decorhw_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        db.reset_init_cache()
        asyncio.set_event_loop(asyncio.new_event_loop())
        host.wire({
            "json_response": _json, "web": _Web,
            "dash_auth": lambda r: True,
            "req_role": lambda r: getattr(r, "role", "viewer"),
            "actor": lambda r: "ناصر",
            "now": lambda: datetime.datetime(2026, 8, 1, 10, 0),
            "listings": lambda: LIVE,
            "guide_units": lambda: [
                {"slug": "b14", "listing_id": 900, "listing_name": "OLD STALE NAME"},
                {"slug": "101a", "listing_id": 901, "listing_name": "OLD STALE NAME 2"},
                {"slug": "orphan", "listing_id": None, "listing_name": "No Hostaway link"},
            ],
            "inhouse": lambda day: [],
        })

    def setUp(self):
        routes._ctx_cache.update({"at": 0, "units": {}, "inhouse": []})

    def test_the_live_hostaway_name_wins_over_the_stored_one(self):
        rows = {r["slug"]: r for r in routes._feature_rows()}
        self.assertEqual(rows["b14"]["apartment"], "Ouja | Boulevard 2BR + Pool")
        self.assertNotIn("STALE", rows["b14"]["apartment"])
        self.assertTrue(rows["b14"]["from_hostaway"])

    def test_a_unit_with_no_hostaway_link_still_appears(self):
        """It has a guide page, so a guest CAN tap a package on it — dropping it would hide
        a real order behind a missing link."""
        rows = {r["slug"]: r for r in routes._feature_rows()}
        self.assertIn("orphan", rows)
        self.assertFalse(rows["orphan"]["from_hostaway"])

    def test_hostaway_units_with_no_guide_page_are_reported_not_dropped(self):
        unl = routes._unlinked_listings()
        self.assertEqual([u["listing_id"] for u in unl], [902])

    def test_hostaway_being_down_never_breaks_the_screen(self):
        def boom():
            raise RuntimeError("hostaway down")
        host.wire({"listings": boom})
        try:
            routes._ctx_cache.update({"at": 0, "units": {}, "inhouse": []})
            rows = {r["slug"]: r for r in routes._feature_rows()}
            self.assertEqual(rows["b14"]["apartment"], "OLD STALE NAME")   # falls back
            self.assertFalse(rows["b14"]["from_hostaway"])                 # and says so
            self.assertEqual(routes._unlinked_listings(), [])
        finally:
            host.wire({"listings": lambda: LIVE})
            routes._ctx_cache.update({"at": 0, "units": {}, "inhouse": []})

    def test_the_downloadable_sheet_is_built_from_live_names(self):
        db.set_unit_features("101a", ["jacuzzi"], by="ناصر")
        routes._ctx_cache.update({"at": 0, "units": {}, "inhouse": []})
        resp = run(routes.features_export(_Req()))
        text = resp.body.decode("utf-8-sig")
        self.assertIn("Ouja | Boulevard 2BR + Pool", text)
        self.assertNotIn("STALE", text)
        self.assertIn("csv", resp.content_type)
        self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))
        lines = [l for l in text.splitlines() if l.strip()]
        self.assertEqual(len(lines), 4)                      # header + 3 guide units
        row_101a = [l for l in lines if l.startswith("101a,")][0]
        self.assertIn("نعم", row_101a)                       # the jacuzzi we already know
        row_b14 = [l for l in lines if l.startswith("b14,")][0]
        self.assertIn("الاسم يذكر مسبح", row_b14)            # flagged for the owner to confirm

    def test_a_viewer_cannot_download_the_sheet(self):
        r = run(routes.features_export(_Req(role="viewer")))
        self.assertEqual(r["status"], 403)


if __name__ == "__main__":
    unittest.main()
