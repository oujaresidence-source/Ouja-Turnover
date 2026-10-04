# -*- coding: utf-8 -*-
"""The ERP rides the web lane — المركز المالي must never queue behind bot work.

2026-09-03 and again 2026-10-03: every owner/month showed «تعذّر تحميل البيانات».
Every ERP handler handed its work to asyncio.to_thread — the single default pool
that ~50 bot loops also fill — so a request sat in the queue, never started, and
the browser gave up at 30s. Live probe 2026-10-04: a loop-only route answered in
0.47s while a pool-backed route took 8.5s at the same instant (29.7s earlier).

Run: python3 -m unittest tests.test_erp_web_lane
"""
import asyncio
import concurrent.futures
import contextvars
import re
import sys
import threading
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import finance                      # noqa: E402
from finance import api as fapi     # noqa: E402

BOT_SRC = (ROOT / "bot.py").read_text(encoding="utf-8")
FIN_SRC = (ROOT / "finance" / "__init__.py").read_text(encoding="utf-8")


def _func_src(src, name):
    m = re.search(r"^(async def|def) %s\(" % re.escape(name), src, re.M)
    assert m, "function %s not found" % name
    rest = src[m.start():]
    nxt = re.search(r"\n(?:async def |def |@|class )", rest[1:])
    return rest[:nxt.start() + 1] if nxt else rest


def _fake_bot(pool):
    """A stand-in for bot.py carrying bot.py's REAL web_thread source, bound to
    our own small pool — so the test exercises the shipped code, not a copy."""
    ns = {"asyncio": asyncio, "contextvars": contextvars, "_web_pool": pool}
    exec(_func_src(BOT_SRC, "web_thread"), ns)
    return types.SimpleNamespace(web_thread=ns["web_thread"])


class ContractTest(unittest.TestCase):
    def test_no_erp_handler_uses_the_default_pool(self):
        body = FIN_SRC.replace(_func_src(FIN_SRC, "_wt"), "")
        self.assertNotIn("asyncio.to_thread(", body,
                         "an ERP handler is back on the shared pool — use _wt()")
        self.assertGreaterEqual(body.count("await _wt("), 28)

    def test_web_thread_copies_contextvars(self):
        self.assertIn("copy_context()", _func_src(BOT_SRC, "web_thread"),
                      "without it every ERP request loses the 'user' Hostaway priority")


class JammedPoolTest(unittest.TestCase):
    def setUp(self):
        self._old_b = fapi.B

    def tearDown(self):
        fapi.B = self._old_b

    def _run_with_jammed_default_pool(self, coro_factory):
        """Fill the loop's default pool with one blocked worker, then run."""
        release = threading.Event()

        async def main():
            loop = asyncio.get_running_loop()
            loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=1))
            loop.run_in_executor(None, release.wait)          # the jam
            await asyncio.sleep(0.05)
            try:
                return await asyncio.wait_for(coro_factory(), timeout=1.0)
            finally:
                release.set()
        return asyncio.run(main())

    def test_positive_control_to_thread_is_stuck(self):
        with self.assertRaises(asyncio.TimeoutError):
            self._run_with_jammed_default_pool(lambda: asyncio.to_thread(lambda: "ok"))

    def test_erp_work_still_runs_when_the_default_pool_is_full(self):
        lane = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        try:
            fapi.B = _fake_bot(lane)
            out = self._run_with_jammed_default_pool(lambda: finance._wt(lambda a, b=0: a + b, 2, b=3))
            self.assertEqual(out, 5)
        finally:
            lane.shutdown(wait=False)

    def test_user_priority_survives_the_hop(self):
        prio = contextvars.ContextVar("prio", default="background")
        lane = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            fapi.B = _fake_bot(lane)

            async def main():
                prio.set("user")
                return await finance._wt(prio.get)
            self.assertEqual(asyncio.run(main()), "user")
        finally:
            lane.shutdown(wait=False)

    def test_falls_back_when_no_lane(self):
        fapi.B = None
        self.assertEqual(asyncio.run(finance._wt(lambda: "ok")), "ok")


if __name__ == "__main__":
    unittest.main()
