# -*- coding: utf-8 -*-
"""H2 regression — one exception must never permanently kill state persistence.

The bug: persist_loop's body had no try/except, and persist_state iterated
~45 LIVE containers from a worker thread while the event loop mutated them.
One intermittent "dictionary changed size during iteration" stopped the
discord.py task loop → tickets/expenses/escalations silently stopped saving.

Run: python3 tests/test_persist_loop_h2.py
"""
import asyncio
import os
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-h2")
os.makedirs("/tmp/ouja-test-state-h2", exist_ok=True)

import bot  # noqa: E402


class PersistLoopH2Test(unittest.TestCase):
    def test_loop_body_swallows_persist_errors(self):
        """A raising persist_state must not propagate out of the loop body."""
        orig = bot.persist_state
        bot.persist_state = lambda: (_ for _ in ()).throw(
            RuntimeError("dictionary changed size during iteration"))
        try:
            asyncio.run(bot.persist_loop.coro())   # must NOT raise
        finally:
            bot.persist_state = orig

    def test_loop_has_error_handler(self):
        """Even if something escapes the body, an error handler restarts the loop."""
        self.assertIsNotNone(getattr(bot.persist_loop, "_error", None),
                             "persist_loop needs an @persist_loop.error handler")

    def test_persist_survives_concurrent_mutation(self):
        """Hammer the live containers from another thread while persisting."""
        stop = threading.Event()

        def mutate():
            i = 0
            while not stop.is_set():
                i += 1
                k = i % 5000                       # bounded working set (no OOM)
                bot._pending_replies[k] = {"draft": "x"}
                bot._escalations[k] = {"unit": "u"}
                bot._tickets.insert(0, {"id": k})
                bot._pending_replies.pop((k * 7) % 5000, None)
                bot._escalations.pop((k * 11) % 5000, None)
                if len(bot._tickets) > 500:
                    del bot._tickets[400:]
                if i % 200 == 0:
                    time.sleep(0.001)              # let persist_state make progress

        t = threading.Thread(target=mutate, daemon=True)
        t.start()
        try:
            deadline = time.time() + 5
            runs = 0
            while time.time() < deadline and runs < 8:
                bot.persist_state()   # must never raise under concurrent mutation
                runs += 1
        finally:
            stop.set()
            t.join(timeout=2)
            bot._pending_replies.clear()
            bot._escalations.clear()
            del bot._tickets[:]
        self.assertGreater(runs, 0)


if __name__ == "__main__":
    unittest.main()
