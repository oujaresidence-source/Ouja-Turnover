# -*- coding: utf-8 -*-
"""M12 regression — brain recompute/seed handlers must not run Hostaway pulls
on the event loop (api_seed's full recompute is a 120-day paginated pull).

Run: python3 -m unittest tests.test_brain_routes_nonblocking_m12
"""
import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BLOCKING = {"api_recompute": "todays_view", "api_seed": "recompute"}


class BrainRoutesNonblockingM12Test(unittest.TestCase):
    def test_heavy_calls_go_through_to_thread(self):
        tree = ast.parse((ROOT / "brain" / "routes.py").read_text(encoding="utf-8"))
        fns = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
        for fn_name, heavy in BLOCKING.items():
            node = fns[fn_name]
            src_calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
            direct = [c for c in src_calls
                      if isinstance(c.func, ast.Attribute) and c.func.attr == heavy
                      and not (isinstance(c.func.value, ast.Name) and c.func.value.id == "asyncio")]
            # the heavy fn may appear ONLY as an argument to asyncio.to_thread
            for c in direct:
                self.fail(f"{fn_name} calls {heavy}() directly on the event loop")


if __name__ == "__main__":
    unittest.main()
