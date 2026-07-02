# -*- coding: utf-8 -*-
"""M5 regression — async handlers must never call get_listings_map() directly.

A COLD get_listings_map() paginates Hostaway synchronously (up to ~95s with
retries) and freezes every web request + the Discord heartbeat when called on
the event loop. Async code must go through get_listings_map_async().

This test AST-scans bot.py: any direct get_listings_map() call lexically
inside an `async def` (excluding nested sync helpers, which run in threads)
fails the build.

Run: python3 tests/test_no_blocking_listings_m5.py
"""
import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-m5")
os.makedirs("/tmp/ouja-test-state-m5", exist_ok=True)

ALLOWED = {"get_listings_map_async"}   # the wrapper itself


def _direct_calls(fn_node, name):
    """Call sites of `name` directly in fn_node's body, not in nested defs/lambdas."""
    hits = []

    def visit(node, in_nested):
        for child in ast.iter_child_nodes(node):
            nested = in_nested or isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            if (not in_nested and isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name) and child.func.id == name):
                hits.append(child.lineno)
            visit(child, nested)
    visit(fn_node, False)
    return hits


class NoBlockingListingsM5Test(unittest.TestCase):
    def test_async_functions_use_the_async_wrapper(self):
        tree = ast.parse((ROOT / "bot.py").read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name not in ALLOWED:
                for ln in _direct_calls(node, "get_listings_map"):
                    offenders.append(f"{node.name}:{ln}")
        self.assertEqual(offenders, [],
                         "async fns must await get_listings_map_async(): " + ", ".join(offenders))

    def test_async_wrapper_warm_hit_uses_cache(self):
        import bot
        old_map, old_ts = bot._listings["map"], bot._listings["ts"]
        called = []
        orig = bot.get_listings_map
        bot.get_listings_map = lambda: called.append(1) or {}
        try:
            import asyncio
            import time
            bot._listings["map"], bot._listings["ts"] = {1: "Ouja | X"}, time.time()
            out = asyncio.run(bot.get_listings_map_async())
            self.assertEqual(out, {1: "Ouja | X"})
            self.assertFalse(called, "warm cache must not re-fetch")
        finally:
            bot.get_listings_map = orig
            bot._listings["map"], bot._listings["ts"] = old_map, old_ts


if __name__ == "__main__":
    unittest.main()
