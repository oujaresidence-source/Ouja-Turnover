# -*- coding: utf-8 -*-
"""The web lane — guest pages must never queue behind bot work.

2026-08-23: /guide/data.json, /api/stay/* and /api/monthly/* stopped answering
for hours while the pages themselves still served in 0.7s. Every one of them
handed its work to asyncio.to_thread — the single default pool that background
jobs also use — and that pool was full. Guests sat on «جارٍ التحميل» forever.

These tests lock the four structural fixes and the diagnostic.

Run: python3 -m unittest tests.test_web_lane
"""
import asyncio
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-weblane")
os.makedirs("/tmp/ouja-test-state-weblane", exist_ok=True)

from brain import db as bdb          # noqa: E402
from guide import db as gdb          # noqa: E402
from guide import routes as groutes  # noqa: E402

BOT_SRC = (ROOT / "bot.py").read_text(encoding="utf-8")


def _func_body(src, name):
    """The source of one top-level function, up to the next top-level def."""
    m = re.search(r"^(async def|def) %s\(" % re.escape(name), src, re.M)
    assert m, "function %s not found in bot.py" % name
    rest = src[m.start():]
    nxt = re.search(r"\n(?:async def |def |@|class )", rest[1:])
    return rest[:nxt.start() + 1] if nxt else rest


class GuideRecordsUnchangedTest(unittest.TestCase):
    """One query replaced one-query-per-unit. The OUTPUT must be identical —
    entries_for() is still here, so we compare against it directly."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="weblane_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        gdb.reset_init_cache()
        gdb.reset_public_cache()
        for slug in ("a1-one", "b2-two"):
            gdb.upsert_unit(slug, listing_name="Ouja | " + slug, wifi_name="w", wifi_pass="p")
        gdb.upsert_unit("z9-off", listing_name="Ouja | hidden", active=0)
        # own rows, a for-everyone row, another unit's row, a draft, out-of-order sorts
        gdb.add_entry("a1-one", "faq", "سؤال أ", "", "جواب أ", "", None, 2)
        gdb.add_entry("a1-one", "faq", "سؤال ب", "", "جواب ب", "", None, 1)
        gdb.add_entry("", "faq", "سؤال للجميع", "", "جواب للجميع", "", None, 0)
        gdb.add_entry("b2-two", "faq", "سؤال ثاني", "", "جواب ثاني", "", None, 0)
        gdb.add_entry("a1-one", "faq", "مسودة", "", "غير منشورة", "", None, 0, "draft")
        gdb.add_entry("a1-one", "note", "ليست سؤال", "", "قسم آخر", "", None, 0)

    def _expected_faq(self, slug):
        return [{"title_ar": e.get("title_ar") or "", "title_en": e.get("title_en") or "",
                 "body_ar": e.get("body_ar") or "", "body_en": e.get("body_en") or ""}
                for e in gdb.entries_for(slug) if e.get("section") == "faq"]

    def test_faq_identical_to_the_per_unit_query(self):
        recs = {r["id"]: r for r in gdb.public_records()}
        self.assertEqual(sorted(recs), ["a1-one", "b2-two"])     # inactive stays out
        for slug in recs:
            self.assertEqual(recs[slug]["faq"], self._expected_faq(slug),
                             "faq for %s drifted from the original query" % slug)

    def test_no_cross_unit_leak_and_drafts_excluded(self):
        recs = {r["id"]: r for r in gdb.public_records()}
        a = [f["title_ar"] for f in recs["a1-one"]["faq"]]
        self.assertIn("سؤال للجميع", a)          # the for-everyone row reaches every unit
        self.assertNotIn("سؤال ثاني", a)          # another unit's row must NOT
        self.assertNotIn("مسودة", a)              # drafts must NOT
        self.assertNotIn("ليست سؤال", a)          # other sections must NOT

    def test_sort_order_preserved(self):
        rec = {r["id"]: r for r in gdb.public_records()}["a1-one"]
        self.assertEqual([f["title_ar"] for f in rec["faq"]],
                         [f["title_ar"] for f in self._expected_faq("a1-one")])


class GuideCacheTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="weblanec_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        gdb.reset_init_cache()
        gdb.reset_public_cache()
        gdb.upsert_unit("c3-cache", listing_name="Ouja | cache")

    def test_cold_then_warm(self):
        recs, stale = gdb.public_records_cached()
        self.assertIsNone(recs)                       # nothing served from an empty cache
        self.assertTrue(stale)
        gdb.public_records_fresh()
        recs, stale = gdb.public_records_cached()
        self.assertEqual(len(recs), 1)
        self.assertFalse(stale)

    def test_any_write_invalidates(self):
        gdb.public_records_fresh()
        self.assertFalse(gdb.public_records_cached()[1])
        gdb.add_entry("c3-cache", "faq", "جديد", "", "نص", "")
        self.assertTrue(gdb.public_records_cached()[1],
                        "an owner edit must mark data.json stale at once")
        gdb.public_records_fresh()
        recs, stale = gdb.public_records_cached()
        self.assertFalse(stale)
        self.assertEqual(recs[0]["faq"][0]["title_ar"], "جديد")

    def test_ttl_expires(self):
        gdb.public_records_fresh()
        gdb._pub_cache["ts"] -= (gdb.PUBLIC_TTL + 1)
        self.assertTrue(gdb.public_records_cached()[1])


class DataJsonNeverUsesTheSharedPoolTest(unittest.TestCase):
    """The regression itself: this handler must not touch asyncio.to_thread,
    and a warm cache must not touch the database."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="weblaner_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        gdb.reset_init_cache()
        gdb.reset_public_cache()
        gdb.upsert_unit("d4-route", listing_name="Ouja | route")
        groutes.wire({"json_response": lambda payload: payload})

    def _call(self):
        return asyncio.run(groutes.data_json(object()))

    def test_cold_and_warm_calls_avoid_to_thread(self):
        def _boom(*a, **k):
            raise AssertionError("data.json must never use the shared to_thread pool")
        orig = groutes.asyncio.to_thread
        groutes.asyncio.to_thread = _boom
        try:
            self.assertEqual(len(self._call()), 1)     # cold: builds on the guide's own pool
            self.assertEqual(len(self._call()), 1)     # warm: straight from memory
        finally:
            groutes.asyncio.to_thread = orig

    def test_warm_cache_does_not_read_the_database(self):
        self._call()                                    # warm it
        def _boom(*a, **k):
            raise AssertionError("a warm data.json must not hit the DB")
        orig = gdb.public_records
        gdb.public_records = _boom
        try:
            self.assertEqual(len(self._call()), 1)
        finally:
            gdb.public_records = orig

    def test_source_has_no_to_thread(self):
        src = (ROOT / "guide" / "routes.py").read_text(encoding="utf-8")
        handler = src[src.index("async def data_json"):]
        handler = handler[:handler.index("async def media")]
        self.assertNotIn("to_thread", handler)


class GuestHandlersOnTheWebPoolTest(unittest.TestCase):
    """/stay and /monthly data endpoints run on the web pool, not the shared one."""

    GUEST_HANDLERS = ("_api_stay_match", "_api_stay_search", "_api_stay_featured",
                      "_api_stay_listing", "_monthly_search_async",
                      "_api_monthly_featured", "_api_monthly_listing",
                      "_api_monthly_quote")

    def test_no_guest_handler_uses_to_thread(self):
        for name in self.GUEST_HANDLERS:
            body = _func_body(BOT_SRC, name)
            self.assertNotIn("asyncio.to_thread", body,
                             "%s must use web_thread — to_thread queues behind bot jobs" % name)

    def test_every_guest_handler_uses_web_thread(self):
        for name in self.GUEST_HANDLERS:
            self.assertIn("web_thread(", _func_body(BOT_SRC, name), name)

    def test_web_pool_exists_and_outsizes_the_monthly_fan_out(self):
        import bot
        self.assertTrue(callable(bot.web_thread))
        self.assertGreaterEqual(bot._web_pool._max_workers, 12,
                                "the monthly search alone can hold 8 workers")
        self.assertNotEqual(bot._web_pool, getattr(asyncio, "_default_executor", None))

    def test_web_thread_runs_off_the_default_pool(self):
        import bot
        import threading

        async def _go():
            return await bot.web_thread(lambda: threading.current_thread().name)
        self.assertTrue(asyncio.run(_go()).startswith("ouja-web"))


class NoUnboundedWaitsTest(unittest.TestCase):
    """A wait with no deadline is how one stuck job takes the whole app down."""

    def test_pdf_render_has_a_timeout(self):
        src = (ROOT / "owner_report" / "renderer" / "ouja_render.py").read_text(encoding="utf-8")
        self.assertIn("PDF_TIMEOUT_S", src)
        self.assertIn(".result(timeout=PDF_TIMEOUT_S)", src)
        self.assertNotIn("_pw_pool.submit(_pw_print, html_tmp, pdf_path).result()", src)
        self.assertIn("import atexit, base64, os, pathlib, threading", src)   # os is used now

    def test_guide_page_gives_up_and_offers_a_retry(self):
        tpl = (ROOT / "guide" / "templates" / "guide.html").read_text(encoding="utf-8")
        self.assertIn("fetchWithTimeout", tpl)
        self.assertIn("AbortController", tpl)
        self.assertIn("guideRetry", tpl)
        self.assertIn("إعادة المحاولة", tpl)


class ThreadHealthTest(unittest.TestCase):
    """Next freeze: look, don't guess."""

    def test_snapshot_shape(self):
        import bot
        h = bot.thread_health()
        for k in ("threads_total", "threads_by_name", "default_pool", "web_pool",
                  "guide_pool", "hostaway"):
            self.assertIn(k, h)
        self.assertIn("queued", h["web_pool"])
        self.assertIn("in_10s_window", h["hostaway"])

    def test_endpoint_is_registered_and_gated(self):
        self.assertIn('app.router.add_get("/api/health/threads"', BOT_SRC)
        body = _func_body(BOT_SRC, "_api_health_threads")
        self.assertIn("_dash_auth(request)", body)
        self.assertIn('"unauthorized"', body)


if __name__ == "__main__":
    unittest.main()
