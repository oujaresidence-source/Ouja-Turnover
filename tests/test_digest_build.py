# -*- coding: utf-8 -*-
"""digest.build — the orchestrator end to end, offline: saved fixtures through FakeHttp,
a temp brain.db, no model. Proves the latch, the dead-link drop at render time, the
rebuild cap, the alternate swap + ruling, and that a bad payload fails without files.
The render step needs Chromium; those tests skip without it."""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "digest"))

from brain import db as bdb
from digest import build, db as ddb, schema
from digest.render import build as rbuild
from _fake_http import FakeHttp, fixture, HERE as FIX

TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime(2026, 9, 2, 13, 0, tzinfo=TZ)
_CHROMIUM = rbuild.chromium_available()


def fixture_http(permissive=True, **extra_pages):
    with open(os.path.join(FIX, "saff-roshn-20260902.html"), "rb") as fh:
        saff_html = fh.read().decode("cp1256", "replace")
    pages = {
        build.platinumlist.CALENDAR_URL: (200, "text/html", fixture("platinumlist-this-weekend-20260902.html")),
        "https://riyadh.platinumlist.net/ar/event-tickets/107433/spacetoon-memories-with-assem-sukkar-in-riyadh":
            (200, "text/html", fixture("platinumlist-event-107433-20260902.html")),
        build.elcinema.NOW_URL: (200, "text/html", fixture("elcinema-now-sa-20260902.html")),
        build.saff.SCHEDULE_URL: (200, "text/html", saff_html),
        build.kooora.PAGE_URL: (200, "text/html", fixture("kooora-roshn-20260902.html")),
    }
    pages.update(extra_pages)
    return FakeHttp(pages=pages, permissive_head=permissive)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="digestbuild_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        ddb.reset_init_cache()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        for t in ("digest_rulings", "digest_candidates", "digest_items", "digest_issues"):
            ddb.execute("DELETE FROM " + t)


class Latch(Base):
    def test_existing_week_of_and_already_built(self):
        self.assertIsNone(build.existing_week_of(NOW))
        self.assertFalse(build.already_built(NOW))
        ddb.open_issue("2026-09-03", 1)
        self.assertEqual(build.existing_week_of(NOW), "2026-09-03")
        self.assertTrue(build.already_built(NOW))

    def test_second_build_for_the_same_week_is_refused(self):
        ddb.open_issue("2026-09-03", 1)
        with self.assertRaises(build.BuildError):
            build.build_issue(NOW, fixture_http(), out_root=self.tmp)


class Collect(Base):
    def test_collect_from_fixtures_fills_every_section(self):
        rep = {"dropped": [], "errors": []}
        by = build._collect(build.dates.week_for(NOW), NOW, fixture_http(), None, None, rep)
        self.assertGreaterEqual(len(by["events"]), 5)
        self.assertGreaterEqual(len(by["cinema"]), 10)
        self.assertGreaterEqual(len(by["fixtures"]), 4)
        self.assertGreaterEqual(len(by["worth"]), 4)
        self.assertEqual(rep["errors"], [])
        self.assertTrue(all("confidence" in c for cands in by.values() for c in cands))
        thu = [f for f in by["fixtures"] if f["home"] == "الدرعية"][0]
        self.assertEqual(thu["confidence"], 1.0)                 # cross-checked with kooora
        sh = [f for f in by["fixtures"] if f["home"] == "الشباب"][0]
        self.assertEqual(sh["confidence"], 0.85)                 # no counterpart → lower, still eligible

    def test_a_source_that_dies_is_reported_not_fatal(self):
        http = fixture_http()
        del http.pages[build.saff.SCHEDULE_URL]
        rep = {"dropped": [], "errors": []}
        by = build._collect(build.dates.week_for(NOW), NOW, http, None, None, rep)
        self.assertEqual(by["fixtures"], [])
        self.assertTrue(any("saff" in d["ttl"] or "الاتحاد" in d["ttl"] for d in rep["dropped"]))
        self.assertGreaterEqual(len(by["events"]), 5)

    def test_dead_link_is_dropped_with_reason(self):
        http = fixture_http(permissive=True)
        http.head_status["https://riyadh.platinumlist.net/ar/event-tickets/107438/big-sam-live-in-riyadh"] = 404
        rep = {"dropped": [], "errors": []}
        by = build._collect(build.dates.week_for(NOW), NOW, http, None, None, rep)
        n = len(by["events"])
        build._verify_and_prune(by, http, rep)
        self.assertEqual(len(by["events"]), n - 1)
        self.assertTrue(any(d["reason"] == "الرابط ما يفتح" for d in rep["dropped"]))

    def test_assemble_obeys_the_schema(self):
        http = fixture_http()
        rep = {"dropped": [], "errors": []}
        w = build.dates.week_for(NOW)
        by = build._collect(w, NOW, http, None, None, rep)
        verified = build._verify_and_prune(by, http, rep)
        picked = build.rank.choose(by, {})
        items = {}
        for section, cands in picked["primary"].items():
            items[section] = [build._item_from(c, {"kind": "generated", "sha256": "x", "src": ""}) for c in cands]
        p = build.assemble(w, 1, NOW, items, verified, "", rep["dropped"], picked["alternates"])
        self.assertEqual(schema.validate(p), [])
        self.assertEqual(len(schema.section(p, "cinema")["items"]), 3)
        self.assertTrue(p["alternates"])


@unittest.skipUnless(_CHROMIUM, "Chromium not available")
class FullBuild(Base):
    def test_cold_start_builds_a_preview_with_files_and_rows(self):
        rep = build.build_issue(NOW, fixture_http(), out_root=self.tmp)
        self.assertEqual(rep["status"], "preview", rep["errors"])
        for k in ("pdf", "png", "json"):
            self.assertTrue(os.path.isfile(rep["files"][k]), k)
        row = ddb.issue_for_week("2026-09-03")
        self.assertEqual(row["status"], "preview")
        self.assertTrue(row["html_sha"])
        self.assertTrue(ddb.candidates(rep["issue_id"], "events", 0))
        self.assertTrue([r for r in ddb.items(rep["issue_id"]) if r["state"] == "primary"])
        self.assertTrue(build.already_built(NOW))

    def test_alternate_swap_writes_a_ruling_and_rerenders(self):
        rep = build.build_issue(NOW, fixture_http(), out_root=self.tmp)
        iid = rep["issue_id"]
        before = schema.section(ddb.issue(iid)["payload"], "events")["items"][0]["ttl"]
        alts = ddb.candidates(iid, "events", 0)
        self.assertTrue(alts)
        build.apply_alternate(iid, "events", 0, 1, fixture_http(), NOW, who="faisal", out_root=self.tmp)
        after = schema.section(ddb.issue(iid)["payload"], "events")["items"][0]["ttl"]
        self.assertNotEqual(before, after)
        r = ddb.rulings_for(iid)[-1]
        self.assertEqual((r["who"], r["action"], r["section"], r["slot"]), ("faisal", "alt", "events", 0))
        self.assertEqual(r["detail"]["from"], before)

    def test_drop_reflows_and_records_why(self):
        rep = build.build_issue(NOW, fixture_http(), out_root=self.tmp)
        iid = rep["issue_id"]
        n = len(schema.section(ddb.issue(iid)["payload"], "events")["items"])
        build.drop_slot(iid, "events", 0, NOW, who="faisal", out_root=self.tmp)
        p = ddb.issue(iid)["payload"]
        self.assertEqual(len(schema.section(p, "events")["items"]), n - 1)
        self.assertEqual(schema.section(p, "events")["layout"], schema.layout_for("events", n - 1))
        self.assertTrue(any(d["reason"] == "حذفه فيصل" for d in p["dropped"]))
        self.assertEqual(ddb.rulings_for(iid)[-1]["action"], "drop")

    def test_rebuild_is_capped_at_three(self):
        rep = build.build_issue(NOW, fixture_http(), out_root=self.tmp)
        iid = rep["issue_id"]
        for _ in range(3):
            build.rebuild(iid, NOW, fixture_http(), out_root=self.tmp)
        with self.assertRaises(build.BuildError):
            build.rebuild(iid, NOW, fixture_http(), out_root=self.tmp)

    def test_approve_records_what_he_liked(self):
        rep = build.build_issue(NOW, fixture_http(), out_root=self.tmp)
        build.approve(rep["issue_id"], NOW, who="faisal")
        r = ddb.rulings_for(rep["issue_id"])[-1]
        self.assertEqual(r["action"], "approve")
        self.assertTrue(r["detail"]["categories"])
        self.assertEqual(ddb.issue(rep["issue_id"])["status"], "approved")

    def test_too_few_events_fails_without_files(self):
        http = fixture_http()
        del http.pages[build.platinumlist.CALENDAR_URL]
        rep = build.build_issue(NOW, http, out_root=self.tmp)
        self.assertEqual(rep["status"], "failed")
        self.assertEqual(rep["files"], {})
        self.assertEqual(ddb.issue_for_week("2026-09-03")["status"], "failed")


if __name__ == "__main__":
    unittest.main()
