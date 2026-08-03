# -*- coding: utf-8 -*-
"""
Per-employee links, the personal page, and the follow-up counts.

RULES THIS FILE PROTECTS
------------------------
1. The follow-up table is sorted by WHO IS FURTHEST BEHIND, first. Same principle as the
   main list: the row that needs you is row one, never alphabetical.
2. «خلص» counts apartments that actually have a subscription recorded — a remembered
   blank-date row still counts as answered, because the employee DID answer. Silence and
   «ما أعرف» are different things and must not be merged.
3. A short ?e=<id> link resolves to exactly the same list as the old ?who=<name> link.
   The old form keeps working — links already sent must not die.
4. An employee with nothing left to do reports zero remaining and is not hidden.

Run: python3 -m unittest tests.test_wifi_progress
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb          # noqa: E402
from wifi import db, routes          # noqa: E402
from wifi.host import HOST           # noqa: E402

EMPLOYEES = [
    {"id": 1, "name": "ناصر", "emoji": "🟢", "color": "#4A6246", "sort_order": 0},
    {"id": 2, "name": "مآثر", "emoji": "🟠", "color": "#8B593C", "sort_order": 1},
    {"id": 5, "name": "عهود", "emoji": "🟡", "color": "#36655E", "sort_order": 4},
]
# ناصر owns 3, مآثر owns 2, عهود owns 1, and 200 belongs to nobody.
APARTMENTS = [
    {"listing_id": 101, "owner_name": "ناصر"}, {"listing_id": 102, "owner_name": "ناصر"},
    {"listing_id": 103, "owner_name": "ناصر"}, {"listing_id": 110, "owner_name": "مآثر"},
    {"listing_id": 111, "owner_name": "مآثر"}, {"listing_id": 120, "owner_name": "عهود"},
]
LISTINGS = {101: "Ouja | A", 102: "Ouja | B", 103: "Ouja | C",
            110: "Ouja | D", 111: "Ouja | E", 120: "Ouja | F", 200: "Ouja | Orphan"}


class WifiProgressCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wifiprog_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self._saved = (HOST.listings, HOST.permanent_map)
        HOST.listings = lambda: dict(LISTINGS)
        HOST.permanent_map = lambda: {"employees": list(EMPLOYEES),
                                      "apartments": list(APARTMENTS)}

    def tearDown(self):
        HOST.listings, HOST.permanent_map = self._saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fill(self, lid, who, date="2026-07-20"):
        return routes.core_fill_save(
            {"listing_id": lid, "provider": "stc", "source_kind": "first_party",
             "label_days": 30, "purchase_date": date}, who=who, today="2026-08-03")


class TestTheShortLink(WifiProgressCase):

    def test_an_id_resolves_to_the_same_list_as_the_name(self):
        _st, by_id = routes.core_fill(eid=1, today="2026-08-03")
        _st, by_name = routes.core_fill(who="ناصر", today="2026-08-03")
        self.assertEqual(by_id["who"], "ناصر")
        self.assertEqual([u["listing_id"] for u in by_id["units"]],
                         [u["listing_id"] for u in by_name["units"]])

    def test_the_old_name_link_still_works(self):
        """Links already sent on WhatsApp must not die."""
        _st, body = routes.core_fill(who="مآثر", today="2026-08-03")
        self.assertEqual(body["who"], "مآثر")
        self.assertEqual(len(body["units"]), 2)

    def test_the_page_gets_the_employee_colour_and_emoji(self):
        """The personal look comes from the Employee Calendar — no second copy here."""
        _st, body = routes.core_fill(eid=1, today="2026-08-03")
        self.assertEqual(body["me"], {"id": 1, "name": "ناصر", "emoji": "🟢", "color": "#4A6246"})

    def test_an_unknown_id_shows_the_picker_instead_of_a_wrong_list(self):
        """Better to ask who you are than to show somebody else's apartments."""
        _st, body = routes.core_fill(eid=999, today="2026-08-03")
        self.assertEqual(body["who"], "")
        self.assertIsNone(body["me"])
        self.assertEqual(sorted(body["people"]), sorted(["ناصر", "مآثر", "عهود"]))

    def test_every_employee_gets_a_link(self):
        _st, body = routes.core_progress(today="2026-08-03")
        self.assertEqual(sorted(r["id"] for r in body["rows"] if r["id"]), [1, 2, 5])

    def test_at_equal_progress_the_bigger_pile_comes_first(self):
        """Nobody has filled anything, so everyone is at 0%. The tie-break is how much
        work is outstanding: 3 unanswered apartments needs a louder nudge than 1."""
        _st, body = routes.core_progress(today="2026-08-03")
        named = [(r["name"], r["remaining"]) for r in body["rows"] if r["name"]]
        self.assertEqual(named, [("ناصر", 3), ("مآثر", 2), ("عهود", 1)])


class TestTheFollowUpCounts(WifiProgressCase):

    def test_furthest_behind_is_row_one(self):
        self.fill(101, "ناصر"); self.fill(102, "ناصر"); self.fill(103, "ناصر")   # 3/3 done
        self.fill(120, "عهود")                                                    # 1/1 done
        _st, body = routes.core_progress(today="2026-08-03")
        named = [r for r in body["rows"] if r["name"]]
        self.assertEqual(named[0]["name"], "مآثر")            # 0 of 2 — needs the nudge
        self.assertEqual(named[0]["remaining"], 2)
        self.assertTrue(all(r["done"] == r["total"] for r in named[1:]))

    def test_the_counts_are_per_employee_not_global(self):
        self.fill(101, "ناصر")
        _st, body = routes.core_progress(today="2026-08-03")
        by = {r["name"]: r for r in body["rows"]}
        self.assertEqual((by["ناصر"]["done"], by["ناصر"]["total"]), (1, 3))
        self.assertEqual((by["مآثر"]["done"], by["مآثر"]["total"]), (0, 2))
        self.assertEqual(by["ناصر"]["pct"], 33)

    def test_a_remembered_blank_date_still_counts_as_answered(self):
        """«ما أعرف» IS an answer. Counting it as unanswered would push people to guess —
        the exact thing the button exists to prevent."""
        self.fill(101, "ناصر", date=None)
        _st, body = routes.core_progress(today="2026-08-03")
        by = {r["name"]: r for r in body["rows"]}
        self.assertEqual(by["ناصر"]["done"], 1)

    def test_an_apartment_nobody_owns_is_shown_not_swallowed(self):
        """An unassigned unit is the one that gets forgotten — it gets its own row."""
        _st, body = routes.core_progress(today="2026-08-03")
        orphan = [r for r in body["rows"] if not r["name"]]
        self.assertEqual(len(orphan), 1)
        self.assertEqual(orphan[0]["total"], 1)
        self.assertIsNone(orphan[0]["id"])          # no id -> the UI offers no link

    def test_a_finished_employee_reports_zero_left_and_stays_visible(self):
        self.fill(120, "عهود")
        _st, body = routes.core_progress(today="2026-08-03")
        by = {r["name"]: r for r in body["rows"]}
        self.assertEqual(by["عهود"]["remaining"], 0)
        self.assertEqual(by["عهود"]["pct"], 100)
        self.assertTrue(by["عهود"]["finished"])

    def test_the_totals_line_adds_up(self):
        self.fill(101, "ناصر"); self.fill(110, "مآثر")
        _st, body = routes.core_progress(today="2026-08-03")
        self.assertEqual(body["done"], 2)
        self.assertEqual(body["total"], 7)          # 6 assigned + 1 orphan
        self.assertEqual(sum(r["total"] for r in body["rows"]), 7)

    def test_last_fill_is_utc_stamped_so_the_phone_reads_it_right(self):
        """A bare timestamp is read as LOCAL time by the browser and lands 3 hours off
        in Riyadh. The Z is what makes «قبل ساعتين» honest."""
        self.fill(101, "ناصر")
        _st, body = routes.core_progress(today="2026-08-03")
        by = {r["name"]: r for r in body["rows"]}
        self.assertTrue(by["ناصر"]["last_fill"].endswith("Z"))
        self.assertIsNone(by["مآثر"]["last_fill"])


class TestTheReadyMessage(WifiProgressCase):

    def test_each_row_carries_its_own_link_path(self):
        _st, body = routes.core_progress(today="2026-08-03")
        by = {r["name"]: r for r in body["rows"] if r["name"]}
        self.assertEqual(by["ناصر"]["link"], "/wifi-fill?e=1")
        self.assertEqual(by["عهود"]["link"], "/wifi-fill?e=5")

    def test_the_orphan_row_has_no_link_to_send(self):
        _st, body = routes.core_progress(today="2026-08-03")
        orphan = [r for r in body["rows"] if not r["name"]][0]
        self.assertIsNone(orphan["link"])


class TestTheProgressEndpointIsGated(unittest.TestCase):

    def test_it_needs_the_wifi_permission(self):
        import bot
        tab = None
        for prefix, t in bot._ROLE_READ_RULES:
            if "/api/wifi/progress".startswith(prefix):
                tab = t
                break
        self.assertEqual(tab, "wifi", "/api/wifi/progress is readable without permission")


if __name__ == "__main__":
    unittest.main()
