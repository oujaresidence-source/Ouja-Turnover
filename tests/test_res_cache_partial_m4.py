# -*- coding: utf-8 -*-
"""M4 regression — a mid-pagination failure must not overwrite a fuller
reservation cache with a partial list for the whole TTL.

Run: python3 tests/test_res_cache_partial_m4.py
"""
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-m4")
os.makedirs("/tmp/ouja-test-state-m4", exist_ok=True)

import bot  # noqa: E402

FULL = [{"id": i} for i in range(300)]


class ResCachePartialM4Test(unittest.TestCase):
    def setUp(self):
        self._api_get = bot.api_get
        self._cache = dict(bot._res_cache)
        bot._res_cache.update({"data": None, "ts": 0, "fetch_failed": False, "truncated": False})

    def tearDown(self):
        bot.api_get = self._api_get
        bot._res_cache.clear(); bot._res_cache.update(self._cache)

    def _api(self, fail_after_page=None):
        calls = {"n": 0}

        def api_get(path, params=None):
            p = params or {}
            off, lim = int(p.get("offset", 0)), int(p.get("limit", 100))
            if lim == 1:                       # the H3 count peek
                return {"status": "success", "result": FULL[:1], "count": len(FULL)}
            page = off // 100
            if fail_after_page is not None and page >= fail_after_page:
                raise RuntimeError("hostaway 500")
            return {"status": "success", "result": FULL[off:off + lim], "count": len(FULL)}
        return api_get

    def test_partial_pull_keeps_previous_cache(self):
        bot.api_get = self._api()                     # healthy warm-up: 300 rows
        first = bot.get_reservations_cached(ttl=1800)
        self.assertEqual(len(first), 300)
        bot._res_cache["ts"] = 0                      # force refresh
        bot.api_get = self._api(fail_after_page=1)    # now dies after page 0 → 100 rows
        second = bot.get_reservations_cached(ttl=1800)
        self.assertEqual(len(second), 300, "partial pull must NOT replace the fuller cache")
        self.assertEqual(len(bot._res_cache["data"]), 300)

    def test_retry_happens_soon_not_after_full_ttl(self):
        bot.api_get = self._api()
        bot.get_reservations_cached(ttl=1800)
        bot._res_cache["ts"] = 0
        bot.api_get = self._api(fail_after_page=1)
        bot.get_reservations_cached(ttl=1800)
        age = time.time() - bot._res_cache["ts"]
        self.assertGreater(age, 1000, "ts must be backdated so a retry happens in ~5 min")

    def test_healthy_smaller_pull_still_replaces(self):
        bot.api_get = self._api()
        bot.get_reservations_cached(ttl=1800)
        bot._res_cache["ts"] = 0
        smaller = FULL[:150]

        def api_ok_smaller(path, params=None):
            p = params or {}
            off, lim = int(p.get("offset", 0)), int(p.get("limit", 100))
            if lim == 1:
                return {"status": "success", "result": smaller[:1], "count": len(smaller)}
            return {"status": "success", "result": smaller[off:off + lim], "count": len(smaller)}
        bot.api_get = api_ok_smaller
        out = bot.get_reservations_cached(ttl=1800)
        self.assertEqual(len(out), 150, "a SUCCESSFUL smaller pull is real (cancellations) and must land")


if __name__ == "__main__":
    unittest.main()
