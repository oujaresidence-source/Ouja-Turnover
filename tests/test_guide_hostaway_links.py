# -*- coding: utf-8 -*-
"""Guide↔Hostaway link cutover — the one-button rewrite of the old Netlify
guide URLs inside Hostaway Custom Fields.

Run: python3 -m unittest tests.test_guide_hostaway_links
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-gha")
os.makedirs("/tmp/ouja-test-state-gha", exist_ok=True)

from brain import db as bdb        # noqa: E402
from guide import db as gdb        # noqa: E402
import bot  # noqa: E402


def _listing(lid, name, cf_value, cf_id=77, alias_dup=False):
    cf = {"id": 9000 + lid, "customFieldId": cf_id, "value": cf_value,
          "customField": {"id": cf_id, "name": "Listing Internal Name"}}
    L = {"id": lid, "internalListingName": name, "name": name,
         "listingCustomFieldValues": [cf]}
    if alias_dup:                       # Hostaway exposes the same value under alias keys
        L["customFieldValues"] = [dict(cf)]
    return L


class GhaScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="gha_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        gdb.reset_init_cache()
        gdb.upsert_unit("f2", listing_name="F2", listing_id=441826)
        gdb.upsert_unit("h8-vlg", listing_name="Bohemian Escape")   # unlinked

    def setUp(self):
        self._fetch = bot._ha_fetch_all_listings
        self._flag = bot.GUIDE_ENABLED
        bot.GUIDE_ENABLED = True

    def tearDown(self):
        bot._ha_fetch_all_listings = self._fetch
        bot.GUIDE_ENABLED = self._flag

    def test_scan_links_slug_via_listing_then_url_and_dedupes(self):
        bot._ha_fetch_all_listings = lambda: [
            _listing(441826, "F2", "https://oujaguide.netlify.app/f2", alias_dup=True),
            _listing(555, "Bohemian", "https://oujaguide.netlify.app/h8-vlg"),
            _listing(666, "Mystery", "https://oujaguide.netlify.app/unknown-slug"),
            _listing(777, "NoGuide", "https://example.com/other"),
        ]
        rows = bot._gha_scan()
        by = {r["lid"]: r for r in rows}
        self.assertEqual(len(rows), 3, "non-netlify values ignored; alias dup counted once")
        self.assertEqual(by[441826]["new"], bot.GUIDE_PUBLIC_BASE + "/guide/f2")
        self.assertIsNone(by[441826]["skip"])
        # unlinked listing falls back to the slug inside the old URL
        self.assertEqual(by[555]["new"], bot.GUIDE_PUBLIC_BASE + "/guide/h8-vlg")
        # unknown slug + unlinked → skipped with a reason, never guessed
        self.assertIsNone(by[666]["new"])
        self.assertTrue(by[666]["skip"])

    def test_apply_puts_customFieldValues_and_verifies(self):
        bot._ha_fetch_all_listings = lambda: [
            _listing(441826, "F2", "https://oujaguide.netlify.app/f2")]
        puts, current = [], {"v": "https://oujaguide.netlify.app/f2"}

        def fake_put(path, body, _retry=0):
            puts.append((path, body))
            current["v"] = body["customFieldValues"][0]["value"]
            return {"status": "success"}

        def fake_get(path, params=None):
            if path == "/listings" or path.startswith("/listings?"):
                return {"status": "success", "result": []}
            return {"status": "success", "result":
                    {"id": 441826, "listingCustomFieldValues":
                     [{"customFieldId": 77, "value": current["v"]}]}}
        _put, _get, _sync = bot.api_put, bot.api_get, bot.sync_listings_store
        bot.api_put, bot.sync_listings_store = fake_put, lambda raw=None: None
        bot.api_get = fake_get
        try:
            bot._gha_state.update({"running": True, "done": 0, "total": 0, "ok": 0,
                                   "failed": [], "skipped": 0, "error": ""})
            bot._gha_apply_job()
            st = bot._gha_state
            self.assertFalse(st["running"])
            self.assertEqual(st["ok"], 1)
            self.assertEqual(st["failed"], [])
            self.assertEqual(puts[0][0], "/listings/441826")
            self.assertEqual(puts[0][1]["customFieldValues"],
                             [{"customFieldId": 77,
                               "value": bot.GUIDE_PUBLIC_BASE + "/guide/f2"}])
        finally:
            bot.api_put, bot.api_get, bot.sync_listings_store = _put, _get, _sync

    def test_apply_reports_unverified_write(self):
        bot._ha_fetch_all_listings = lambda: [
            _listing(441826, "F2", "https://oujaguide.netlify.app/f2")]

        def fake_get(path, params=None):
            if "441826" in path:
                return {"status": "success", "result":
                        {"listingCustomFieldValues":
                         [{"customFieldId": 77, "value": "https://oujaguide.netlify.app/f2"}]}}
            return {"status": "success", "result": []}
        _put, _get, _sync = bot.api_put, bot.api_get, bot.sync_listings_store
        bot.api_put = lambda p, b, _retry=0: {"status": "success"}   # write "succeeds"…
        bot.api_get = fake_get                                       # …but read-back shows OLD value
        bot.sync_listings_store = lambda raw=None: None
        try:
            bot._gha_state.update({"running": True, "done": 0, "total": 0, "ok": 0,
                                   "failed": [], "skipped": 0, "error": ""})
            bot._gha_apply_job()
            self.assertEqual(bot._gha_state["ok"], 0)
            self.assertEqual(len(bot._gha_state["failed"]), 1,
                             "a write that doesn't stick must be reported, not counted ok")
        finally:
            bot.api_put, bot.api_get, bot.sync_listings_store = _put, _get, _sync


if __name__ == "__main__":
    unittest.main()
