# -*- coding: utf-8 -*-
"""Guide Engine wiring — template 1:1 integrity, data.json contract,
elite-geo cutover, gap→guide loop pieces, nav/i18n parity.

Run: python3 -m unittest tests.test_guide_wiring
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-guidew")
os.makedirs("/tmp/ouja-test-state-guidew", exist_ok=True)

from brain import db as bdb        # noqa: E402
from guide import db as gdb        # noqa: E402

TPL = (ROOT / "guide" / "templates" / "guide.html").read_text(encoding="utf-8")


class GuideTemplateTest(unittest.TestCase):
    """The reproduced page must keep the live site 1:1 and lose Supabase."""

    def test_js_parses(self):
        import esprima
        for js in re.findall(r"<script>(.*?)</script>", TPL, re.S):
            esprima.parseScript(js)

    def test_live_site_content_kept(self):
        self.assertIn('theme-color" content="#1A130D"', TPL)     # dark warm-brown theme
        self.assertIn("حياكم الله", TPL)                          # landing welcome
        self.assertIn("لحظات عوجا", TPL)                          # Ouja Moments
        self.assertIn("tel:+966551324214", TPL)                   # 24/7 hotline
        for n in ("911", "999", "998", "997", "993", "996"):     # Saudi emergency numbers
            self.assertIn('tel:' + n, TPL)
        for price in ("1,450", "998", "799", "670", "598"):      # event packages, verbatim
            self.assertIn(price, TPL)
        self.assertIn("Sawari", TPL)                              # chauffeur partner
        self.assertIn("OUJA", TPL)                                # Jaayek promo code

    def test_supabase_retired_and_paths_inhouse(self):
        self.assertNotIn("supabase.co", TPL)
        self.assertNotIn("cdn.jsdelivr.net/npm/@supabase", TPL)
        self.assertIn('const DATA_URL = "/guide/data.json";', TPL)
        self.assertIn("/guide/fonts/", TPL)
        self.assertIn('src="/guide/logo.png"', TPL)
        self.assertIn("listing.faq", TPL)                         # gap-loop FAQ section
        # mirrored-media URLs must survive photoSrc
        self.assertIn("t.startsWith('/')", TPL)

    def test_fonts_shipped(self):
        for w in ("Light", "Regular", "Medium", "Bold"):
            p = ROOT / "guide" / "static" / "fonts" / ("thmanyahsans-%s.woff2" % w)
            self.assertTrue(p.is_file(), p.name + " must ship with the app")


class GuideDataContractTest(unittest.TestCase):
    """public_records must expose exactly what the page's render() reads."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="guidew_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        gdb.reset_init_cache()
        gdb.upsert_unit("t1-abc", listing_name="Ouja | T1", listing_id=42,
                        map_link="https://maps.google.com/?q=24.7695369,46.58399966",
                        wifi_name="Ouja_T1", wifi_pass="pass1234",
                        notes="العنوان: حي الملقا")

    def test_record_keys_match_page_reads(self):
        rec = gdb.public_records()[0]
        page_reads = set(re.findall(r"listing\.([a-z_]+)", TPL))
        page_reads.discard("id")
        for k in page_reads:
            self.assertIn(k, rec, "page reads listing.%s — data.json must carry it" % k)

    def test_bot_wiring_and_elite_cutover(self):
        import bot
        self.assertTrue(bot._HAS_GUIDE)
        self.assertTrue(hasattr(bot, "GUIDE_ENABLED"))
        # elite geo must read the guide DB (no HTTP) when records exist
        orig_flag = bot.GUIDE_ENABLED
        bot.GUIDE_ENABLED = True

        def _no_http(*a, **k):
            raise AssertionError("elite geo must not hit the network when the guide DB has rows")
        orig_get = bot.requests.get
        bot.requests.get = _no_http
        try:
            m = bot._elite_geo_fetch()
            self.assertTrue(m, "coords must come from the guide DB map_link")
            self.assertIn((24.7695369, 46.58399966), list(m.values()))
        finally:
            bot.requests.get = orig_get
            bot.GUIDE_ENABLED = orig_flag

    def test_gap_add_writes_entry_that_renders(self):
        import bot
        # the modal writes via _guide.db.add_entry with the unit slug matched by listing id
        unit = gdb.unit_by_listing(42)
        self.assertIsNotNone(unit)
        gdb.add_entry(unit["slug"], "faq", "وين الموقف؟", "", "الموقف رقم ١٢ بالقبو", "",
                      None, 0, "published", "gap", "tester")
        rec = {r["id"]: r for r in gdb.public_records()}[unit["slug"]]
        self.assertTrue(any(f["title_ar"] == "وين الموقف؟" for f in rec["faq"]))
        # nav/i18n parity (trap #2)
        self.assertIn("guide", bot.NAV_DEF["labels"]["ar"])
        self.assertIn("guide", bot.NAV_DEF["labels"]["en"])
        self.assertIn('id="view_guide"', bot.DASHBOARD_HTML)
        self.assertIn("function loadGuide", bot.DASHBOARD_HTML)
        # the gap card carries the four actions (add / add-all / already-there / no-need)
        src = (ROOT / "bot.py").read_text(encoding="utf-8")
        for cid in ("wm_gap_add", "wm_gap_add_all", "wm_gap_exists", "wm_gap_no_need"):
            self.assertIn(cid, src)


if __name__ == "__main__":
    unittest.main()
