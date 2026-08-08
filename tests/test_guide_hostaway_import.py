# -*- coding: utf-8 -*-
"""
Bringing apartments added to Hostaway AFTER the one-shot Supabase export into
the guide («➕ شقق جديدة من Hostaway»).

The rules this locks down:
  * an apartment already in the guide is NEVER offered again — not by Hostaway
    id, and not by name (a second row would split its photos across two guest
    pages and the guest would land on the empty one);
  * a suggested slug never collides — not with an existing slug, not with
    another suggestion in the same batch (the slug IS the public link);
  * the add endpoint re-derives the truth from Hostaway: a client cannot post a
    made-up listing id or name into the guide;
  * new rows are created HIDDEN (active=0) — an apartment with no arrival
    photos must not be reachable by a guest;
  * running it twice creates nothing the second time.

Run: python3 -m unittest tests.test_guide_hostaway_import
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                 # noqa: E402
from guide import db as gdb                 # noqa: E402
from guide import importer, routes          # noqa: E402


def _L(lid, internal, public="", address="", active=True):
    return {"id": lid, "internal_name": internal, "public_name": public or internal,
            "address": address, "active": active}


class _Req:
    """Just enough aiohttp request for these handlers."""
    def __init__(self, body=None, role="admin"):
        self._body = body or {}
        self.role = role

    async def json(self):
        return self._body


def _json(data, status=200):
    return {"status": status, "data": data}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ----------------------------------------------------------------- pure logic
class SlugTest(unittest.TestCase):
    def test_slugify_drops_brand_and_punctuation(self):
        self.assertEqual(importer.slugify_name("Ouja | Huge 2BR Penthouse with Pool"),
                         "huge-2br-penthouse-with-pool")
        self.assertEqual(importer.slugify_name("Spacious Mid-Century Apt • Self Entry"),
                         "spacious-mid-century-apt-self-entry")

    def test_slugify_truncates_on_a_word_boundary(self):
        s = importer.slugify_name("Ouja | Modern Luxury 2BR near Airport | Al-Narjis", 24)
        self.assertLessEqual(len(s), 24)
        self.assertFalse(s.endswith("-"))
        self.assertTrue(s.startswith("modern-luxury-2br"))

    def test_arabic_or_empty_name_falls_back_to_the_listing_id(self):
        self.assertEqual(importer.suggest_slug("شقة فخمة", 5512, set()), "ha-5512")
        self.assertEqual(importer.suggest_slug("", 77, set()), "ha-77")

    def test_suggestion_never_collides(self):
        taken = {"huge-2br-penthouse-with-pool", "huge-2br-penthouse-with-pool-9"}
        s = importer.suggest_slug("Huge 2BR Penthouse with Pool", 9, taken)
        self.assertNotIn(s, taken)


class NewFromHostawayTest(unittest.TestCase):
    def setUp(self):
        self.units = [
            {"slug": "101b", "listing_id": 477747, "listing_name": "Ouja Luxury Retreat"},
            # in the guide but never matched to Hostaway — the «غير مرتبطة» rows
            {"slug": "3bmj", "listing_id": None,
             "listing_name": "Ouja | Big Modern 1BR  75  4K TV  Self-Entry"},
        ]

    def test_only_the_genuinely_missing_ones_are_offered(self):
        ha = [_L(477747, "Ouja Luxury Retreat"),                       # linked by id
              _L(600, "Ouja | Big Modern 1BR 75 4K TV Self-Entry"),    # same apt, unlinked
              _L(700, "Ouja | Rooftop Studio", address="حي النرجس")]   # genuinely new
        res = importer.new_from_hostaway(ha, self.units)
        self.assertEqual([r["lid"] for r in res["new"]], [700])
        self.assertEqual(res["new"][0]["address"], "حي النرجس")
        self.assertEqual([r["lid"] for r in res["unlinked"]], [600])
        self.assertEqual(res["in_guide"], 1)

    def test_inactive_hostaway_listings_are_left_out(self):
        ha = [_L(800, "Ouja | Old Unit", active=False)]
        res = importer.new_from_hostaway(ha, self.units)
        self.assertEqual(res["new"], [])
        self.assertEqual(res["skipped_inactive"], 1)

    def test_two_new_listings_with_the_same_name_get_different_slugs(self):
        ha = [_L(901, "Ouja | Twin Suite"), _L(902, "Ouja | Twin Suite")]
        res = importer.new_from_hostaway(ha, self.units)
        slugs = [r["slug"] for r in res["new"]]
        self.assertEqual(len(set(slugs)), 2)

    def test_a_suggestion_never_steals_an_existing_slug(self):
        units = self.units + [{"slug": "rooftop-studio", "listing_id": 1,
                               "listing_name": "something else entirely"}]
        res = importer.new_from_hostaway([_L(700, "Ouja | Rooftop Studio")], units)
        self.assertNotEqual(res["new"][0]["slug"], "rooftop-studio")


# ------------------------------------------------------------- the HTTP guard
class AddRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="guide_hai_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        gdb.reset_init_cache()
        asyncio.set_event_loop(asyncio.new_event_loop())
        cls.ha = [_L(477747, "Ouja Luxury Retreat"),
                  _L(700, "Ouja | Rooftop Studio", address="حي النرجس"),
                  _L(701, "Ouja | Garden Duplex")]
        routes.wire({"json_response": _json,
                     "dash_auth": lambda r: True,
                     "req_role": lambda r: getattr(r, "role", "viewer"),
                     "listings_full": lambda: cls.ha,
                     "listings": lambda: {l["id"]: l["internal_name"] for l in cls.ha}})

    def setUp(self):
        gdb.execute("DELETE FROM guide_units", ())
        gdb.upsert_unit("101b", listing_id=477747, listing_name="Ouja Luxury Retreat")

    def _preview(self, role="admin"):
        return run(routes.api_ha_new(_Req(role=role)))["data"]

    def _add(self, items, role="admin"):
        return run(routes.api_ha_add(_Req({"items": items}, role=role)))["data"]

    def test_preview_lists_the_two_missing_ones(self):
        d = self._preview()
        self.assertTrue(d["ok"])
        self.assertEqual(sorted(r["lid"] for r in d["new"]), [700, 701])

    def test_viewer_cannot_preview_or_add(self):
        self.assertFalse(self._preview(role="viewer")["ok"])
        self.assertFalse(self._add([{"lid": 700, "slug": "rooftop"}], role="viewer")["ok"])
        self.assertIsNone(gdb.get_unit("rooftop"))

    def test_add_creates_a_hidden_unit_with_the_hostaway_name(self):
        d = self._add([{"lid": 700, "slug": "Rooftop"}])   # slug is lower-cased
        self.assertTrue(d["ok"])
        self.assertEqual(d["created"], 1)
        u = gdb.get_unit("rooftop")
        self.assertIsNotNone(u)
        self.assertEqual(u["listing_id"], 700)
        self.assertEqual(u["listing_name"], "Ouja | Rooftop Studio")
        self.assertEqual(u["active"], 0)                   # hidden until photos are in
        self.assertFalse(u["map_link"])                    # the owner pastes the pin

    def test_a_client_supplied_name_is_ignored(self):
        self._add([{"lid": 700, "slug": "rooftop", "listing_name": "HACKED"}])
        self.assertEqual(gdb.get_unit("rooftop")["listing_name"], "Ouja | Rooftop Studio")

    def test_taken_slug_is_refused_and_the_existing_unit_is_untouched(self):
        d = self._add([{"lid": 700, "slug": "101b"}])
        self.assertEqual(d["created"], 0)
        self.assertTrue(d["results"][0]["error"])
        u = gdb.get_unit("101b")
        self.assertEqual(u["listing_id"], 477747)          # NOT repointed at 700
        self.assertEqual(u["active"], 1)                   # NOT hidden

    def test_bad_slug_is_refused(self):
        for bad in ("", "a b", "شقة", "x" * 90, "-lead"):
            d = self._add([{"lid": 700, "slug": bad}])
            self.assertEqual(d["created"], 0, bad)

    def test_a_listing_already_in_the_guide_cannot_be_added_again(self):
        d = self._add([{"lid": 477747, "slug": "second-page"}])
        self.assertEqual(d["created"], 0)
        self.assertIsNone(gdb.get_unit("second-page"))

    def test_unknown_listing_id_is_refused(self):
        d = self._add([{"lid": 999999, "slug": "ghost"}])
        self.assertEqual(d["created"], 0)
        self.assertIsNone(gdb.get_unit("ghost"))

    def test_two_slugs_pointing_at_the_same_listing_in_one_batch(self):
        d = self._add([{"lid": 700, "slug": "one"}, {"lid": 700, "slug": "two"}])
        self.assertEqual(d["created"], 1)
        self.assertIsNone(gdb.get_unit("two"))

    def test_running_it_twice_creates_nothing_the_second_time(self):
        first = self._preview()["new"]
        self._add([{"lid": r["lid"], "slug": r["slug"]} for r in first])
        before = len(gdb.units(False))
        self.assertEqual(self._preview()["new"], [])
        self._add([{"lid": r["lid"], "slug": r["slug"]} for r in first])
        self.assertEqual(len(gdb.units(False)), before)


if __name__ == "__main__":
    unittest.main()
