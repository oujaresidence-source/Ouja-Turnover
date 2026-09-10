# -*- coding: utf-8 -*-
"""Source-level rules for directpay/ that must not be "simplified" away later, plus the
bot.py boundary (the 2026-09-03 digest outage: the wiring referenced a submodule the
package never imported → AttributeError → caught → every route silently gone).

  * directpay/ imports no discord, no bot, no requests/socket/urllib — HOST is the only door
  * the channel-creation path in bot.py uses _make_channel_spill, never create_text_channel
  * directpay/*.py contain ZERO backslashes (the DASHBOARD_HTML/page.py trap, kept out by rule)
  * every `_directpay.<name>` bot.py references resolves on the package
  * every dp_* custom_id lives in a View that bot.add_view registers
  * env defaults: ENABLED on, DRYRUN ON, loops exist and are not running
  * role rules + nav + both T.ar / T.en carry the `dpay` tab
  * the webhook line, the loop guard, the staggered start
  * no web close endpoint exists

Run: python3 -m unittest tests.test_directpay_structure
"""
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="dpstruct_state_"))
for _k in ("DIRECTPAY_DRYRUN", "DIRECTPAY_ENABLED"):
    os.environ.pop(_k, None)          # the clean-env default is what we assert

PKG = os.path.join(ROOT, "directpay")
with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as _fh:
    BOT_SRC = _fh.read()


def _pkg_sources():
    out = {}
    for fn in sorted(os.listdir(PKG)):
        if fn.endswith(".py"):
            with open(os.path.join(PKG, fn), encoding="utf-8") as fh:
                out[fn] = fh.read()
    return out


def _func_body(src, name):
    m = re.search(r"^(async def|def) %s\(" % re.escape(name), src, re.M)
    assert m, "function %s not found in bot.py" % name
    rest = src[m.start():]
    nxt = re.search(r"\n(?:async def |def |@|class )", rest[1:])
    return rest[:nxt.start() + 1] if nxt else rest


class PackageIsolation(unittest.TestCase):
    def test_no_discord_bot_or_sockets(self):
        for fn, src in _pkg_sources().items():
            self.assertNotRegex(src, r"^\s*(import|from)\s+discord\b", fn)
            self.assertNotRegex(src, r"^\s*(import|from)\s+bot\b", fn)
            for mod in ("requests", "socket", "urllib", "http.client", "aiohttp"):
                self.assertNotRegex(src, r"^\s*(import|from)\s+%s\b" % re.escape(mod), "%s imports %s" % (fn, mod))

    def test_zero_backslashes(self):
        for fn, src in _pkg_sources().items():
            self.assertNotIn(chr(92), src, "%s contains a backslash" % fn)

    def test_expected_modules_exist(self):
        names = set(_pkg_sources())
        for need in ("__init__.py", "host.py", "db.py", "engine.py", "notify.py", "routes.py",
                     "service.py", "proof.py", "config.py"):
            self.assertIn(need, names)

    def test_engine_is_pure(self):
        src = _pkg_sources()["engine.py"]
        self.assertNotRegex(src, r"\bHOST\b\s*[.(]")        # never touches the bridge
        self.assertNotRegex(src, r"(?m)^\s*from \. import")
        self.assertNotRegex(src, r"(?m)^\s*from \.host")
        self.assertNotRegex(src, r"(?m)^\s*import sqlite")

    def test_no_stayhub_network(self):
        for fn, src in _pkg_sources().items():
            self.assertNotRegex(src, r"stayhub\.[a-z]+/", fn)      # no URL to StayHub, ever


class BotBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import bot
        cls.bot = bot

    def test_import_guard_and_flags(self):
        self.assertTrue(self.bot._HAS_DIRECTPAY)
        self.assertTrue(self.bot.DIRECTPAY_ENABLED)
        self.assertTrue(self.bot._directpay.notify.dryrun())      # DRYRUN ON by default
        self.assertEqual(self.bot.DIRECTPAY_CATEGORY, "تحصيل الحجوزات المباشرة")
        self.assertEqual(self.bot.DIRECTPAY_SUMMARY_CHANNEL, "تحصيل-الملخص")
        self.assertEqual(self.bot.DIRECTPAY_POLL_MIN, 10)

    def test_loops_exist_and_are_not_running(self):
        b = self.bot
        self.assertFalse(b.directpay_poll_loop.is_running())
        self.assertEqual(b.directpay_poll_loop.minutes, 10)
        self.assertFalse(b.directpay_nudge_loop.is_running())
        self.assertEqual(b.directpay_nudge_loop.hours, 1)
        self.assertNotIn("time=", _func_body(BOT_SRC, "directpay_nudge_loop"))

    def test_loops_are_guarded_and_staggered(self):
        # registered through the on_ready tuple loop that calls _loop_guard(_lp, _nm)
        self.assertRegex(BOT_SRC, r"\(directpay_poll_loop,\s*\"directpay_poll_loop\"\)")
        self.assertRegex(BOT_SRC, r"\(directpay_nudge_loop,\s*\"directpay_nudge_loop\"\)")
        guard_block = BOT_SRC[BOT_SRC.index("(directpay_poll_loop, \"directpay_poll_loop\")") - 600:
                              BOT_SRC.index("(directpay_nudge_loop, \"directpay_nudge_loop\")") + 400]
        self.assertIn("_loop_guard(_lp, _nm)", guard_block)
        self.assertRegex(BOT_SRC, r"_pending\.append\(directpay_poll_loop\)")
        self.assertRegex(BOT_SRC, r"_pending\.append\(directpay_nudge_loop\)")
        self.assertNotRegex(BOT_SRC, r"directpay_(poll|nudge)_loop\.start\(\)")

    def test_every_package_attribute_bot_uses_resolves(self):
        import directpay
        names = sorted(set(re.findall(r"_directpay[.]([a-z_]+)", BOT_SRC)))
        self.assertTrue(names)
        missing = [n for n in names if not hasattr(directpay, n)]
        self.assertEqual(missing, [])
        for dotted in sorted(set(re.findall(r"_directpay[.]([a-z_]+[.][a-z_]+)", BOT_SRC))):
            obj = directpay
            for part in dotted.split("."):
                self.assertTrue(hasattr(obj, part), dotted)
                obj = getattr(obj, part)

    def test_channel_creation_spills_never_create_text_channel(self):
        body = _func_body(BOT_SRC, "_directpay_make_room")
        self.assertIn("_make_channel_spill(", body)
        self.assertNotIn("create_text_channel", body)
        # and nothing in the directpay Discord block calls it either
        start = BOT_SRC.index("def _directpay_notify(")
        end = BOT_SRC.index("directpay_nudge_loop.before_loop")
        self.assertNotIn("create_text_channel", BOT_SRC[start:end])

    def test_every_dp_custom_id_is_in_a_registered_view(self):
        ids = sorted(set(re.findall(r"custom_id=\"(dp_[a-z_]+)\"", BOT_SRC)))
        self.assertTrue(ids)
        for cid in ("dp_close", "dp_notdirect", "dp_writeoff", "dp_refresh"):
            self.assertIn(cid, ids)
        for cid in ids:
            # the class whose body carries this custom_id
            pos = BOT_SRC.index("custom_id=\"%s\"" % cid)
            cls_m = None
            for m in re.finditer(r"^class (\w+)\(discord\.ui\.View\):", BOT_SRC, re.M):
                if m.start() < pos:
                    cls_m = m
            self.assertIsNotNone(cls_m, cid)
            cls = cls_m.group(1)
            self.assertRegex(BOT_SRC, r"bot\.add_view\(%s\(\)\)" % cls, "%s (%s) not registered" % (cid, cls))
            v = getattr(self.bot, cls)()
            self.assertIsNone(v.timeout, cls)

    def test_gate_is_written_fresh(self):
        body = _func_body(BOT_SRC, "_dp_can_close")
        self.assertNotIn("_tk_is_admin", body)
        self.assertNotIn("manage_guild", body)

    def test_webhook_line_present_and_bg_task(self):
        body = _func_body(BOT_SRC, "_handle_hook")
        self.assertIn("_bg_task(_directpay_on_hook(", body)
        self.assertIn("hook:directpay", body)

    def test_role_rules_nav_and_i18n(self):
        b = self.bot
        self.assertIn(("/api/directpay/", "dpay"), b._ROLE_WRITE_RULES)
        self.assertIn(("/api/directpay/", "dpay"), b._ROLE_READ_RULES)
        self.assertIn("dpay", b._USER_TABS)
        ids = [i["id"] for i in b.NAV_DEF["items"]]
        self.assertIn("dpay", ids)
        ops = next(c for c in b.NAV_DEF["cats"] if c["tk"] == "cat_ops")
        self.assertIn("dpay", ops["ids"])
        self.assertEqual(b.NAV_DEF["labels"]["ar"]["dpay"], "التحصيل")
        self.assertEqual(b.NAV_DEF["labels"]["en"]["dpay"], "Collection")
        html = b.DASHBOARD_HTML
        self.assertIn('id="view_dpay"', html)
        self.assertIn("function loadDpay(", html)
        self.assertRegex(html, r"case 'dpay':\s*return loadDpay\(\);")
        self.assertIn("if(id==='dpay') loadDpay();", html)
        # both T tables carry the tab label (a missing one renders the word "undefined")
        ar = html[html.index("const T = {"):]
        ar_block = ar[:ar.index("  en:{dir:'ltr'")]
        en_block = ar[ar.index("  en:{dir:'ltr'"):ar.index("  en:{dir:'ltr'") + 40000]
        self.assertRegex(ar_block, r"\bdpay:'التحصيل'")
        self.assertRegex(en_block, r"\bdpay:'Collection'")

    def test_no_web_close_endpoint(self):
        import directpay
        src = _pkg_sources()["routes.py"]
        self.assertNotRegex(src, r"/api/directpay/(close|verify|writeoff|void)")
        calls = []

        class R(object):
            def add_get(self, p, h): calls.append(("GET", p))
            def add_post(self, p, h): calls.append(("POST", p))

        class App(object):
            router = R()
        directpay.register_routes(App())
        self.assertIn(("GET", "/api/directpay/board"), calls)
        self.assertIn(("GET", "/api/directpay/ticket/{id}"), calls)
        self.assertIn(("POST", "/api/directpay/note"), calls)
        for _, p in calls:
            self.assertNotRegex(p, r"close|verify|writeoff|void", p)

    def test_wiring_block_runs_without_error(self):
        b = self.bot
        import directpay
        calls = []

        class R(object):
            def add_get(self, p, h): calls.append(p)
            def add_post(self, p, h): calls.append(p)

        class App(object):
            router = R()
        directpay.wire(b._directpay_caps())
        directpay.register_routes(App())
        self.assertIn("/api/directpay/board", calls)
        for cap in ("dash_auth", "req_role", "actor", "req_actor", "json_response", "web", "state_dir",
                    "state_path", "tz", "now", "listings", "notify", "log_event", "finance_channel",
                    "payment_signal", "ha_reservations_window", "ha_reservation", "confirmed_statuses"):
            self.assertIsNotNone(getattr(directpay.HOST, cap, None), cap)
        self.assertEqual(directpay.HOST.confirmed_statuses(), b.CONFIRMED_STATUSES)
        self.assertTrue(callable(directpay.HOST.confirmed_statuses))

    def test_wire_print_states_the_posture(self):
        self.assertRegex(BOT_SRC, r"\[directpay\] wired.*dryrun=")


if __name__ == "__main__":
    unittest.main()
