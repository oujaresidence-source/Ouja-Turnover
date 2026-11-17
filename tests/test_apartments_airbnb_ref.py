# -*- coding: utf-8 -*-
"""/apartments × Airbnb reference (2026-11-17).

Owner rules locked here:
  * Airbnb is the approved reference and is NEVER written. Bedroom fixes live in our own
    dashboard override (guest_overrides.json → "bedrooms"); Hostaway is not touched either,
    because its listing data syncs out to Airbnb.
  * A bedrooms override of 0 makes the unit a studio everywhere on the guest site: the
    card, the filter chip, the search filter.
  * «وش قالوا ضيوفنا» shows only 5/5 public reviews, never a private note, never a
    review that complains about something, and only the guest's first name.
  * The Airbnb-reference corrections are written ONCE per version; a later dashboard edit wins.

Run: python3 -m unittest tests.test_apartments_airbnb_ref
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-abref")
os.makedirs("/tmp/ouja-test-state-abref", exist_ok=True)

import bot  # noqa: E402


def _snap(lid, beds=1, tags=("1br",), amen=()):
    return {"id": lid, "name": "Unit %d" % lid, "active": True, "beds": beds, "bedrooms": beds,
            "tag_keys": list(tags), "capacity": 4, "amenities": list(amen), "images": []}


class BedroomOverride(unittest.TestCase):
    def setUp(self):
        self.p = [mock.patch.object(bot, "_gw_cache", {"listings": [
                      _snap(1, 1, ("1br", "malqa")), _snap(2, 2, ("2br",)), _snap(3, 2, ("2br",))]}),
                  mock.patch.object(bot, "_gw_overrides", {"1": {"bedrooms": 0}, "2": {"bedrooms": 3}}),
                  mock.patch.object(bot, "_gw_taxonomy", dict(bot._gw_taxonomy))]
        for x in self.p:
            x.start()
            self.addCleanup(x.stop)

    def test_studio_override_replaces_the_layout_tag_only(self):
        s, ov = bot._gw_find_by_slug_or_id("1")
        self.assertEqual(s["beds"], 0)
        self.assertIn("studio", s["tag_keys"])
        self.assertNotIn("1br", s["tag_keys"])
        self.assertIn("malqa", s["tag_keys"], "non-layout tags survive")

    def test_cached_snapshot_is_not_mutated(self):
        bot._gw_visible_snaps()
        self.assertEqual(bot._gw_cache["listings"][0]["tag_keys"], ["1br", "malqa"])
        self.assertEqual(bot._gw_cache["listings"][0]["beds"], 1)

    def test_search_filters_by_the_corrected_layout(self):
        ids = lambda tags: sorted(l["id"] for l in bot._gw_search(tags=tags)["results"])
        self.assertEqual(ids("studio"), [1])
        self.assertEqual(ids("3br"), [2])
        self.assertEqual(ids("2br"), [3])

    def test_studio_becomes_a_filter_option(self):
        keys = [o["key"] for o in bot._gw_noo_options()]
        self.assertIn("studio", keys)

    def test_no_override_means_hostaway_value(self):
        s, _ = bot._gw_find_by_slug_or_id("3")
        self.assertIs(s, bot._gw_cache["listings"][2])


class ReviewPicks(unittest.TestCase):
    def setUp(self):
        revs = {
            "a": {"listing_id": 7, "rating": 5, "public_review": "شقة مرة نظيفة وموقعها ممتاز والدخول سهل، أنصح فيها بقوة",
                  "guest_name": "Sara Al Ahmad", "date": "2026-03-01", "is_public": True,
                  "private_review": "PRIVATE NOTE"},
            "b": {"listing_id": 7, "rating": 5, "public_review": "Lovely place and great host, but the AC was noisy at night",
                  "guest_name": "John", "date": "2026-04-01", "is_public": True},
            "c": {"listing_id": 7, "rating": 4, "public_review": "Nice and clean apartment, good location for the boulevard",
                  "guest_name": "Ali", "date": "2026-04-02", "is_public": True},
            "d": {"listing_id": 7, "rating": 5, "public_review": "Perfect stay, spotless home and very comfortable beds for all of us",
                  "guest_name": "Maha", "date": "2026-05-02", "is_public": False},
        }
        self.p = [mock.patch.object(bot, "_reviews", revs),
                  mock.patch.object(bot, "_gw_reviews_pick_cache", {"t": 0.0, "map": None})]
        for x in self.p:
            x.start()
            self.addCleanup(x.stop)

    def test_only_clean_public_five_star(self):
        picks = bot._gw_review_picks(7)
        self.assertEqual(len(picks), 1)
        self.assertIn("أنصح", picks[0]["text"])

    def test_first_name_only_and_no_private_note(self):
        p = bot._gw_review_picks(7)[0]
        self.assertEqual(p["name"], "Sara")
        self.assertNotIn("PRIVATE", str(p))


class AirbnbAmenities(unittest.TestCase):
    def test_reference_list_wins_and_is_arabic(self):
        ref = {"units": {"9": {"amenities": ["Wifi", "Air conditioning", "Window AC unit", "Movie theater",
                                              "Wine glasses", "Free parking on premises"]}}}
        with mock.patch.object(bot, "_gw_ab_ref_cache", {"data": ref}):
            groups, tiles = bot._gw_amenities_view(_snap(9))
        flat = [i for g in groups for i in g["items"]]
        self.assertIn("سينما خاصة", flat)
        self.assertEqual(flat.count("تكييف"), 1, "two AC titles collapse into one")
        self.assertFalse(any("Wine" in i or "نبيذ" in i for i in flat), "left out on purpose")
        self.assertEqual(tiles[0]["ar"], "سينما خاصة", "cinema leads the tiles")

    def test_falls_back_to_hostaway(self):
        with mock.patch.object(bot, "_gw_ab_ref_cache", {"data": {"units": {}}}):
            groups, tiles = bot._gw_amenities_view(_snap(10, amen=["Wireless Internet", "Air conditioning"]))
        self.assertTrue(groups)
        self.assertTrue(any(t["icon"] == "wifi" for t in tiles))


class CorrectionsApplyOnce(unittest.TestCase):
    def test_written_once_then_dashboard_wins(self):
        ref = {"version": 1, "corrections": {"5": {"neighborhood": "al_rabi", "bedrooms": 3}}}
        ovs = {"5": {"neighborhood": "al_taawun"}}
        with mock.patch.object(bot, "_gw_ab_ref_cache", {"data": ref}), \
             mock.patch.object(bot, "_gw_overrides", ovs), \
             mock.patch.object(bot, "_gw_save_ov", lambda: None):
            self.assertEqual(bot._gw_apply_ref_corrections(), 1)
            self.assertEqual(ovs["5"]["neighborhood"], "al_rabi")
            self.assertEqual(ovs["5"]["bedrooms"], 3)
            ovs["5"]["neighborhood"] = "al_malqa"          # owner edits it later in the dashboard
            self.assertEqual(bot._gw_apply_ref_corrections(), 0)
            self.assertEqual(ovs["5"]["neighborhood"], "al_malqa")

    def test_a_new_batch_only_applies_its_own_fixes(self):
        ref = {"version": 2, "corrections": {
            "5": {"neighborhood": "al_rabi", "v": 1},
            "6": {"visible": False, "v": 2},
            "7": {"bedrooms": 3, "v": 2}}}
        ovs = {"5": {"neighborhood": "al_malqa", "ref_v": 1},      # v1 applied, then edited by the owner
               "7": {"neighborhood": "al_qirawan"}}
        with mock.patch.object(bot, "_gw_ab_ref_cache", {"data": ref}), \
             mock.patch.object(bot, "_gw_overrides", ovs), \
             mock.patch.object(bot, "_gw_save_ov", lambda: None):
            self.assertEqual(bot._gw_apply_ref_corrections(), 2)
        self.assertEqual(ovs["5"]["neighborhood"], "al_malqa", "v1 fix not re-applied over the owner's edit")
        self.assertIs(ovs["6"]["visible"], False)
        self.assertEqual(ovs["7"]["bedrooms"], 3)
        self.assertEqual(ovs["7"]["neighborhood"], "al_qirawan")

    def test_owner_decisions_are_in_the_shipped_reference(self):
        bot._gw_ab_ref_cache["data"] = None
        c = bot._gw_ab_ref()["corrections"]
        self.assertEqual(c["462594"]["bedrooms"], 3)          # Dyar 20
        self.assertIs(c["417977"]["visible"], False)          # dead Airbnb link
        self.assertIs(c["535907"]["visible"], False)          # dead Airbnb link

    def test_shipped_reference_names_only_known_neighbourhoods(self):
        keys = {k for k, _ar, _en in bot.RIYADH_NEIGHBORHOODS}
        bot._gw_ab_ref_cache["data"] = None
        for lid, c in (bot._gw_ab_ref().get("corrections") or {}).items():
            if c.get("neighborhood"):
                self.assertIn(c["neighborhood"], keys, lid)


if __name__ == "__main__":
    unittest.main()
