# -*- coding: utf-8 -*-
"""G9 — caching must never paper over a failed Hostaway pull.

This is the specific hazard the span layer introduces. fetch_reservations_window
marks _res_window_degraded on a page-1 failure, and compute_owner_statement uses
that mark to stamp the statement `degraded` and REFUSE to publish it (M3). A span
cache that quietly served rows — or that cached a failed pull — would erase that
signal and let a wrong statement be frozen and sent to an owner.

So: a failed span is never cached, never clears the mark, and the degraded
contract survives intact.

Run: python3 -m unittest tests.test_owner_span_degraded -v
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-degraded"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE
os.environ["RES_SPAN_ENABLED"] = "1"

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

LID = 601
OWNER = "مالك التدهور"
MK = "2026-06"


class _Req(object):
    headers = {}
    query = {}


class SpanDegradedTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("D1")] = {
            "apartment": "D1", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_links.clear()
        bot._expenses.clear()
        self._orig = (bot.api_get, bot.get_listings_map, bot.get_reservations_cached)
        bot.get_listings_map = lambda: {LID: "Ouja | D1"}
        bot.get_reservations_cached = lambda: []
        self._actor = fapi.actor
        fapi.actor = lambda r: "tester"
        self._clear()

    def tearDown(self):
        bot.api_get, bot.get_listings_map, bot.get_reservations_cached = self._orig
        fapi.actor = self._actor
        self._clear()

    def _clear(self):
        bot._owner_portal_cache.clear()
        bot._owner_partial_cache.clear()
        bot._res_window_cache.clear()
        bot._res_span_cache.clear()
        bot._res_window_degraded.clear()
        OW._stmt_payload_cache.clear()
        OW._stmt_compare_cache.clear()

    def _break_hostaway(self):
        def boom(path, params=None, _retry=0):
            raise RuntimeError("hostaway down")
        bot.api_get = boom

    def test_a_failed_span_is_never_cached(self):
        """A cached empty span would look like 'this owner had no bookings' — and
        would keep looking that way for the whole TTL."""
        self._break_hostaway()
        from datetime import date
        rows = bot.fetch_reservations_span(date(2026, 1, 1), date(2026, 6, 30))
        self.assertEqual(rows, [])
        self.assertEqual(len(bot._res_span_cache), 0,
                         "a failed span pull was cached — it would be served as truth")

    def test_a_failed_span_does_not_clear_the_degraded_mark(self):
        self._break_hostaway()
        from datetime import date
        s, e = date(2026, 6, 1), date(2026, 6, 30)
        bot.fetch_reservations_window(s, e)
        self.assertIn((s.isoformat(), e.isoformat()), bot._res_window_degraded,
                      "the degradation mark was lost")

    def test_the_statement_is_still_stamped_degraded(self):
        self._break_hostaway()
        stmt = OW.compute_owner_statement(OWNER, MK)
        self.assertIsNotNone(stmt)
        self.assertTrue(stmt.get("degraded"),
                        "a statement built from a failed pull was not marked degraded")

    def test_publishing_a_degraded_statement_is_still_refused(self):
        """The whole point of the mark: a number we are not sure of must never be
        frozen into an owner's published statement."""
        self._break_hostaway()
        out = OW.statement_publish(_Req(), {"owner": OWNER, "m": MK, "basis": "normal"})
        body, status = out if isinstance(out, tuple) else (out, 200)
        self.assertEqual(status, 503)
        self.assertEqual(body.get("error"), "degraded_data")
        self.assertTrue(body.get("message_ar"))

    def test_a_healthy_span_clears_the_mark_again(self):
        """Positive control: the mark must not be sticky, or one blip would make
        the section permanently unpublishable."""
        from datetime import date
        s, e = date(2026, 6, 1), date(2026, 6, 30)
        self._break_hostaway()
        bot.fetch_reservations_window(s, e)
        self.assertIn((s.isoformat(), e.isoformat()), bot._res_window_degraded)

        bot.api_get = lambda path, params=None, _retry=0: {"result": []}
        bot._res_window_cache.clear()
        bot.fetch_reservations_window(s, e)
        self.assertNotIn((s.isoformat(), e.isoformat()), bot._res_window_degraded,
                         "a healthy pull must clear the degradation mark")


if __name__ == "__main__":
    unittest.main(verbosity=2)
