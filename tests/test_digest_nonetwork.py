# -*- coding: utf-8 -*-
"""The renderer and the notifier never touch the network, and only ONE file in the
package is allowed to (digest/net_live.py). Part 1 is a static grep of the package;
part 2 imports the pure modules with sockets blocked and exercises them."""
import glob
import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "digest")
FORBIDDEN = ("import requests", "from requests", "import urllib", "from urllib.request",
             "import http.client", "from http.client", "import socket", "from socket",
             "import aiohttp", "from aiohttp")
ALLOWED_FILE = os.path.join(PKG, "net_live.py")


class OnlyNetLiveTouchesTheNetwork(unittest.TestCase):
    def test_no_other_module_imports_a_network_client(self):
        files = glob.glob(os.path.join(PKG, "*.py")) + glob.glob(os.path.join(PKG, "*", "*.py"))
        self.assertTrue(files)
        bad = []
        for f in files:
            if os.path.abspath(f) == ALLOWED_FILE:
                continue
            with open(f, encoding="utf-8") as fh:
                src = fh.read()
            for needle in FORBIDDEN:
                if needle in src:
                    bad.append("%s: %s" % (os.path.relpath(f, ROOT), needle))
        self.assertEqual(bad, [])


class _NoSockets(object):
    """Context manager: any attempt to open a socket raises."""
    def __enter__(self):
        self._orig = socket.socket
        def boom(*a, **k):
            raise AssertionError("network call attempted inside a pure module")
        socket.socket = boom
        return self

    def __exit__(self, *a):
        socket.socket = self._orig


class PureModulesRunWithSocketsBlocked(unittest.TestCase):
    def test_core_modules_import_and_run_offline(self):
        with _NoSockets():
            from digest import dates, schedule, schema, voice, guard, links   # noqa: F401
            from datetime import datetime
            from zoneinfo import ZoneInfo
            now = datetime(2026, 9, 2, 13, tzinfo=ZoneInfo("Asia/Riyadh"))
            w = dates.week_for(now)
            self.assertEqual(w.iso, "2026-09-03")
            self.assertTrue(schedule.should_fire(now))
            self.assertEqual(voice.slop_hits("نور الرياض يرجع"), [])

    def test_render_and_notify_run_offline(self):
        # Filled in at P3/P5: once digest.render.html and digest.notify exist they are
        # imported and exercised here. Until then the modules are absent and this
        # assertion documents the contract.
        with _NoSockets():
            try:
                from digest.render import html as rhtml      # noqa: F401
            except ImportError:
                rhtml = None
            try:
                from digest import notify                    # noqa: F401
            except ImportError:
                notify = None
            import json
            if rhtml is not None:
                p = json.load(open(os.path.join(ROOT, "tests", "fixtures", "digest", "payload_good.json"), encoding="utf-8"))
                self.assertIn("<html", rhtml.build_pages(p, {}))
            if notify is not None:
                p2 = json.load(open(os.path.join(ROOT, "tests", "fixtures", "digest", "payload_good.json"), encoding="utf-8"))
                self.assertIn("العدد", notify.build_message(p2, 12, p2.get("dropped"), "https://x"))


if __name__ == "__main__":
    unittest.main()
