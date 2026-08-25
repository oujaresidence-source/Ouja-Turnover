# -*- coding: utf-8 -*-
"""studio.external — live-web signal collection, run offline.

Locks the promises that make external signals trustworthy:
  * a well-formed fact WITH url + date is stored as exactly one signal;
  * a fact WITHOUT a url is dropped (the anti-fabrication gate);
  * a fact that restates a signal we already have is dropped (novelty);
  * one stream raising never stops the other streams;
  * a search that returns None yields [] and does not raise.
No network (HOST.claude_search is faked) and no real brain.db (temp path).
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb              # noqa: E402
from studio import db as sdb, engine, external  # noqa: E402
from studio.host import HOST             # noqa: E402


def _fact(source, title, fact, url="https://www.stats.gov.sa/news/1", as_of="2026-07-20",
          strength=80, detail="يهم صاحب الشقة"):
    d = {"source": source, "title": title, "fact": fact, "detail": detail,
         "as_of": as_of, "strength": strength}
    if url is not None:
        d["url"] = url
    return d


class _Search(object):
    """Fake bot.claude_search_json. `by_stream` maps a stream key -> payload dict,
    an Exception instance to raise, or None (model returned nothing)."""

    def __init__(self, by_stream, default=None):
        self.by_stream = by_stream
        self.default = default
        self.calls = []

    def __call__(self, system, user, max_tokens=4000, model=None, max_uses=None,
                 allowed_domains=None):
        key = None
        for k in external.STREAM_KEYS:
            if '"source": "%s"' % k in system:
                key = k
                break
        self.calls.append(key)
        payload = self.by_stream.get(key, self.default)
        if isinstance(payload, Exception):
            raise payload
        if payload is None:
            return None, []
        return payload, ["https://example.com/seen"]


class ExternalTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="studioext_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        HOST.now = lambda: datetime(2026, 7, 23, 9, 0, 0)
        HOST.model_premium = "test-model"
        HOST.save_json = None

    def setUp(self):
        sdb.execute("DELETE FROM studio_signals")
        external.PROGRESS.clear()
        external.PROGRESS["running"] = False


class TestCollect(ExternalTestBase):
    def test_grounded_fact_is_stored_once(self):
        HOST.claude_search = _Search({"regulation": {"signals": [
            _fact("regulation", "نظام الـ٢٩ يوم",
                  "نظام جديد يمنع استضافة نفس الضيف أكثر من ٢٩ يوم متواصل",
                  url="https://mt.gov.sa/news/29", as_of="2026-06-15")]}})
        out = external.collect(streams=["regulation"])
        self.assertEqual(len(out), 1)
        rows = sdb.signals(family="external")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "regulation")
        self.assertEqual(rows[0]["url"], "https://mt.gov.sa/news/29")
        self.assertEqual(rows[0]["as_of"], "2026-06-15")
        self.assertTrue(rows[0]["nkey"])

    def test_fact_without_url_is_dropped(self):
        HOST.claude_search = _Search({"market": {"signals": [
            _fact("market", "٣٧ مليون سائح",
                  "وصل عدد السياح ٣٧٫٢ مليون في الربع الأول ٢٠٢٦", url=None)]}})
        out = external.collect(streams=["market"])
        self.assertEqual(out, [])
        self.assertEqual(sdb.signals(family="external"), [])

    def test_fact_without_date_is_dropped(self):
        HOST.claude_search = _Search({"market": {"signals": [
            _fact("market", "رقم بدون تاريخ", "السوق نما ١٠٪ هالسنة", as_of="")]}})
        self.assertEqual(external.collect(streams=["market"]), [])
        self.assertEqual(sdb.signals(family="external"), [])

    def test_duplicate_angle_is_dropped(self):
        payload = {"signals": [_fact(
            "market", "سياح الربع الأول",
            "عدد السياح في السعودية وصل ٣٧٫٢ مليون في الربع الأول ٢٠٢٦",
            url="https://stats.gov.sa/q1", as_of="2026-07-01")]}
        HOST.claude_search = _Search({"market": payload})
        self.assertEqual(len(external.collect(streams=["market"])), 1)

        # same angle, different wording + different url -> new sid, but the novelty
        # gate must still refuse it.
        HOST.claude_search = _Search({"market": {"signals": [_fact(
            "market", "سياح الربع الأول ٢٠٢٦",
            "عدد السياح في السعودية وصل إلى ٣٧٫٢ مليون خلال الربع الأول من ٢٠٢٦",
            url="https://stats.gov.sa/q1-again", as_of="2026-07-02")]}})
        self.assertEqual(external.collect(streams=["market"]), [])
        self.assertEqual(len(sdb.signals(family="external")), 1)

    def test_failing_stream_does_not_stop_the_others(self):
        HOST.claude_search = _Search({
            "regulation": RuntimeError("web search 500"),
            "market": {"signals": [_fact(
                "market", "إشغال الرياض",
                "إشغال فنادق الرياض ٧٨٪ في يونيو ٢٠٢٦",
                url="https://stats.gov.sa/occ", as_of="2026-07-05")]},
            "global_trend": {"signals": [_fact(
                "global_trend", "سوق ١٥٤ مليار",
                "سوق الإيجار قصير المدى عالمياً ١٥٤ مليار دولار في ٢٠٢٦",
                url="https://example.com/str", as_of="2026-07-10")]},
            "trend": None,
        })
        out = external.collect()
        sources = sorted(s["source"] for s in out)
        self.assertEqual(sources, ["global_trend", "market"])
        self.assertEqual(len(sdb.signals(family="external")), 2)
        snap = external.snapshot()
        self.assertEqual(snap.get("errors"), 1)
        self.assertTrue(snap.get("done"))
        self.assertFalse(snap.get("running"))

    def test_search_returning_none_is_safe(self):
        HOST.claude_search = _Search({}, default=None)
        self.assertEqual(external.collect(), [])
        self.assertEqual(sdb.signals(family="external"), [])

    def test_search_returning_bare_none_is_safe(self):
        class _Bare(object):
            def __call__(self, *a, **kw):
                return None
        HOST.claude_search = _Bare()
        self.assertEqual(external.collect(streams=["trend"]), [])

    def test_per_stream_cap(self):
        angles = ["افتتاح مطار جديد في الرياض بطاقة ١٢٠ مليون مسافر",
                  "موسم الرياض يبدأ أكتوبر بفعاليات ترفيهية ضخمة",
                  "أسعار الإيجارات السكنية ارتفعت ٩٪ حسب تقرير رسمي",
                  "قطار الرياض نقل ١٥ مليون راكب منذ التشغيل",
                  "كأس آسيا يستضيفه الملعب الجديد شمال المدينة",
                  "منصة إيجار سجلت مليون عقد إلكتروني هالسنة"]
        many = {"signals": [_fact("trend", "خبر %d" % i, angles[i],
                                  url="https://news.example.com/%d" % i,
                                  as_of="2026-07-2%d" % (i % 10))
                            for i in range(len(angles))]}
        HOST.claude_search = _Search({"trend": many})
        out = external.collect(streams=["trend"], per_stream=2)
        self.assertEqual(len(out), 2)

    def test_unknown_stream_key_is_ignored(self):
        HOST.claude_search = _Search({}, default={"signals": []})
        self.assertEqual(external.collect(streams=["nope"]), [])
        self.assertEqual(HOST.claude_search.calls, [])


class TestStreamDefinitions(ExternalTestBase):
    def test_four_spec_streams(self):
        self.assertEqual(set(external.STREAM_KEYS), set(engine.EXTERNAL_SOURCES))
        self.assertEqual(len(external.STREAMS), 4)

    def test_prompts_ban_fabrication_and_demand_source(self):
        for st in external.STREAMS:
            sysmsg = st["system"]
            self.assertIn("url", sysmsg)
            self.assertIn("as_of", sysmsg)
            self.assertIn("YYYY-MM-DD", sysmsg)
            self.assertIn("تخترع", sysmsg)          # explicit no-fabrication rule
            self.assertIn("فاضية", sysmsg)          # empty list is an accepted answer
            self.assertIn('"source": "%s"' % st["key"], sysmsg)

    def test_seed_context_is_framed_as_unverified(self):
        user = external.build_user(_by("regulation"), per_stream=3, today="2026-07-23")
        self.assertIn("2026-07-23", user)
        self.assertIn("غير مؤكدة", user)
        self.assertIn("٢٩", user)
        market = external.build_user(_by("market"), today="2026-07-23")
        self.assertIn("غير مؤكدة", market)


def _by(key):
    return [s for s in external.STREAMS if s["key"] == key][0]


if __name__ == "__main__":
    unittest.main()
