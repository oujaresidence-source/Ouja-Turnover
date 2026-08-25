# -*- coding: utf-8 -*-
"""
Who can reach which wifi endpoint, and what the read models actually return.

TWO REGRESSIONS THIS FILE EXISTS TO CATCH
-----------------------------------------
1. Somebody "tidies" the permission rules into one broad ("/api/wifi/", "wifi") READ
   prefix. That prefix also matches GET /api/wifi/fill — the read behind the public
   /wifi-fill team page — so the whole field team is locked out of a page that is
   supposed to open with nothing. Exactly why /api/schedule/day+week are absent from
   the read rules too.
2. The tab label goes missing in one language and renders the literal word
   "undefined" in the sidebar (CLAUDE.md trap #2, which has bitten twice).

Run: python3 -m unittest tests.test_wifi_routes_gating
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot                            # noqa: E402
from brain import db as bdb           # noqa: E402
from wifi import db, engine, routes   # noqa: E402
from wifi.host import HOST            # noqa: E402


def _read_tab(path):
    """What bot.py's middleware would demand for a GET of this path (None = ungated)."""
    for prefix, tab in bot._ROLE_READ_RULES:
        if path.startswith(prefix):
            return tab
    return None


def _write_tab(path):
    if path in bot._ROLE_EXEMPT_WRITES:
        return "EXEMPT"
    for prefix, tab in bot._ROLE_WRITE_RULES:
        if path.startswith(prefix):
            return tab
    return None


class TestTheTeamPageStaysOpen(unittest.TestCase):

    def test_the_public_backfill_read_is_not_behind_a_login(self):
        self.assertIsNone(_read_tab("/api/wifi/fill"),
                          "GET /api/wifi/fill is gated — the team cannot open /wifi-fill")

    def test_the_public_backfill_write_is_exempt(self):
        self.assertEqual(_write_tab("/api/wifi/fill-save"), "EXEMPT")

    def test_everything_else_is_gated(self):
        self.assertEqual(_read_tab("/api/wifi/list"), "wifi")
        self.assertEqual(_read_tab("/api/wifi/unit/123"), "wifi")
        for p in ("/api/wifi/log", "/api/wifi/renew", "/api/wifi/check", "/api/wifi/dead",
                  "/api/wifi/edit", "/api/wifi/unit-settings"):
            self.assertEqual(_write_tab(p), "wifi", "%s is not permission-gated" % p)

    def test_every_registered_route_is_accounted_for(self):
        """A new endpoint added without a rule fails here rather than in production."""
        seen = []

        class _App:
            class router:
                @staticmethod
                def add_get(path, h):
                    seen.append(("GET", path))

                @staticmethod
                def add_post(path, h):
                    seen.append(("POST", path))

                @staticmethod
                def add_delete(path, h):
                    seen.append(("DELETE", path))

        routes.register(_App)
        public = {"/api/wifi/fill", "/api/wifi/fill-save", "/wifi-fill"}
        for method, path in seen:
            if path in public or not path.startswith("/api/"):
                continue
            tab = _read_tab(path) if method == "GET" else _write_tab(path)
            self.assertEqual(tab, "wifi", "%s %s has no permission rule" % (method, path))


class TestTheTabCannotRenderUndefined(unittest.TestCase):

    def test_the_label_exists_in_both_languages(self):
        for lang in ("ar", "en"):
            self.assertIn("wifi", bot.NAV_DEF["labels"][lang])
            self.assertTrue(str(bot.NAV_DEF["labels"][lang]["wifi"]).strip())

    def test_the_tab_is_a_permission_key(self):
        """Without this it can never be restricted and leaks into every sidebar."""
        self.assertIn("wifi", bot._USER_TABS)

    def test_it_is_in_the_nav_and_in_a_category(self):
        ids = [i["id"] for i in bot.NAV_DEF["items"]]
        self.assertIn("wifi", ids)
        cat_ids = [i for c in bot.NAV_DEF["cats"] for i in c["ids"]]
        self.assertIn("wifi", cat_ids)

    def test_a_new_non_admin_user_does_not_get_it_for_free(self):
        """Whitelist model: the owner ticks it in الصلاحيات first."""
        self.assertFalse(bot._default_perms("viewer").get("wifi", {}).get("write"))


class TestTheReadModels(unittest.TestCase):
    """Wired against fake Hostaway listings + a fake Employee Calendar, so the shapes
    bot.py hands over are the shapes routes actually reads."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wifiroutes_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self._saved = (HOST.listings, HOST.permanent_map)
        HOST.listings = lambda: {101: "Ouja | Nofa 1", 102: "Ouja | Nofa 2", 103: "Ouja | Village"}
        HOST.permanent_map = lambda: {"apartments": [
            {"listing_id": 101, "owner_name": "ناصر"},
            {"listing_id": 102, "owner_name": "ناصر"},
            {"listing_id": 103, "owner_name": "فهد"},
        ]}

    def tearDown(self):
        HOST.listings, HOST.permanent_map = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_list_is_sorted_by_days_left_with_unknowns_last(self):
        routes.core_log({"listing_id": 101, "provider": "stc", "source_kind": "first_party",
                         "label_days": 90, "purchase_date": "2026-06-01"},
                        actor="ناصر", today="2026-08-03")     # ends 2026-08-30 -> 27 left
        routes.core_log({"listing_id": 103, "provider": "zain", "source_kind": "first_party",
                         "label_days": 30, "purchase_date": "2026-07-20"},
                        actor="فهد", today="2026-08-03")      # ends 2026-08-19 -> 16 left
        st, body = routes.core_list(today="2026-08-03")
        self.assertEqual(st, 200)
        self.assertEqual([u["listing_id"] for u in body["units"]], [103, 101, 102])
        self.assertEqual(body["counters"]["ok"], 2)
        self.assertEqual(body["counters"]["unknown"], 1)   # 102 has nothing recorded

    def test_a_unit_with_no_subscription_is_unknown_not_healthy(self):
        _st, body = routes.core_list(today="2026-08-03")
        for u in body["units"]:
            self.assertEqual(u["band"], "unknown")
            self.assertIsNone(u["days_left"])

    def test_the_label_trusted_flag_reaches_the_row(self):
        routes.core_log({"listing_id": 101, "provider": "mobily", "source_kind": "vendor",
                         "source_name": "محل النور", "label_days": 90,
                         "purchase_date": "2026-08-01"}, actor="ناصر", today="2026-08-03")
        _st, body = routes.core_list(today="2026-08-03")
        row = [u for u in body["units"] if u["listing_id"] == 101][0]
        self.assertEqual(row["confidence"], "label")
        self.assertEqual(row["sub"]["expected_days"], 90)

    def test_no_money_total_leaks_into_phase_one(self):
        """The accountant's view is Phase 3 — this page answers 'what is about to die'."""
        _st, body = routes.core_list(today="2026-08-03")
        self.assertNotIn("spend_sar", body)

    def test_the_fill_page_filters_to_one_person_and_counts_progress(self):
        routes.core_fill_save({"listing_id": 101, "provider": "stc",
                               "source_kind": "first_party", "label_days": 30,
                               "purchase_date": "2026-07-20"}, who="ناصر", today="2026-08-03")
        _st, body = routes.core_fill(who="ناصر", today="2026-08-03")
        self.assertEqual([u["listing_id"] for u in body["units"]], [102, 101])  # unknown first
        self.assertEqual((body["done"], body["total"]), (1, 2))
        self.assertEqual(body["people"], ["فهد", "ناصر"])

    def test_the_assignee_comes_from_the_employee_calendar_not_a_second_copy(self):
        _st, body = routes.core_list(today="2026-08-03")
        got = {u["listing_id"]: u["assignee"] for u in body["units"]}
        self.assertEqual(got, {101: "ناصر", 102: "ناصر", 103: "فهد"})

    def test_a_unit_kept_out_of_hostaway_still_shows_because_money_is_attached(self):
        db.create_sub({"listing_id": 999, "apartment_name": "Ouja | Retired",
                       "provider": "stc", "label_days": 30, "purchase_date": "2026-07-20",
                       "activation_date": "2026-07-20", "amount_sar": 250})
        _st, body = routes.core_list(today="2026-08-03")
        self.assertIn(999, [u["listing_id"] for u in body["units"]])

    def test_the_unit_view_shows_the_whole_history_newest_first(self):
        routes.core_log({"listing_id": 101, "provider": "stc", "source_kind": "first_party",
                         "label_days": 30, "purchase_date": "2026-05-01"},
                        actor="ناصر", today="2026-06-05")
        routes.core_log({"listing_id": 101, "provider": "zain", "source_kind": "first_party",
                         "label_days": 30, "purchase_date": "2026-06-01"},
                        actor="ناصر", today="2026-06-05")     # renewal: old one had 4 days left
        _st, body = routes.core_unit(101, today="2026-06-05")
        self.assertEqual(len(body["history"]), 2)
        self.assertEqual(body["history"][0]["provider"], "zain")
        self.assertEqual(body["history"][0]["status"], "active")
        self.assertEqual(body["history"][1]["status"], "replaced")


class TestConfigIsReadOnceWithSafeDefaults(unittest.TestCase):

    def test_the_two_knobs_have_the_documented_defaults(self):
        self.assertEqual(engine.MIN_OBSERVATIONS, 3)
        self.assertEqual(engine.LOCK_GRACE_DAYS, 5)


if __name__ == "__main__":
    unittest.main()
