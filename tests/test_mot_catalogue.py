# -*- coding: utf-8 -*-
"""
The catalogue, frozen.

60 live components / 41 criteria without a pool, 66 / 47 with (61/67 under the original
2026-09 version, which retired nothing — a retired key is still counted for old rounds). Every key unique and STABLE
against the snapshot below — a future edit may add a key, never rename or drop one, because
closed rounds are stored by key and must still render years later.

Run: python3 -m unittest tests.test_mot_catalogue
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mot import catalogue as C  # noqa: E402

FROZEN_KEYS = [
    "c01.suitability", "c02.lighting", "c03.elevator", "c04.price_board",
    "c05.condition", "c06.rules_board", "c07.smart_lock", "c08.broom", "c08.detergents",
    "c08.gloves", "c09.bin",
    "c10.iron", "c11.qr_saudi", "c12.prayer_rug", "c12.qibla", "c13.wifi", "c14.door_cam",
    "c15.bedroom_seat", "c16.tv", "c17.kettle", "c17.cups", "c17.water", "c18.dishes",
    "c18.cutlery", "c19.living_vent",
    "c20.room_size", "c21.mattress", "c21.pillows", "c21.linen", "c21.protector",
    "c22.nightstand", "c23.wardrobe", "c23.shelves", "c23.mirror", "c23.hangers",
    "c24.blackout", "c25.master_vent",
    "c26.bathroom", "c27.toilet", "c28.shower", "c28.glass_door", "c28.antislip",
    "c29.sink_mirror", "c30.hand_soap", "c30.body_soap", "c30.shampoo", "c31.towel_rack",
    "c32.bath_mat", "c33.bath_vent",
    "c34.microwave", "c35.cookware", "c35.prep_tools", "c35.dinner_set", "c36.hood",
    "c37.extinguisher", "c37.fire_blanket", "c37.smoke_detector", "c37.first_aid",
    "c38.electrical", "c39.evac_plan", "c40.eco_stickers", "c41.hospitality",
    "c42.pool_ladder", "c43.pool_rails", "c44.pool_floor", "c45.pool_fence",
    "c46.pool_rescue", "c47.pool_electric",
]


class TestCounts(unittest.TestCase):
    def test_60_without_pool_66_with(self):
        self.assertEqual(len(C.components(False)), 60)
        self.assertEqual(len(C.components(True)), 66)

    def test_old_rounds_keep_their_61_67(self):
        # 2026-09 rounds: the 61 they had + c12.qibla (added later, never retired) = 62.
        # Additions reach old rounds as «unchecked»; retirements never take rows away from them.
        self.assertEqual(len(C.components(False, version="2026-09")), 62)
        self.assertEqual(len(C.components(True, version="2026-09")), 68)
        self.assertNotIn("c18.dishes", [c["key"] for c in C.components(False)])
        self.assertIn("c18.dishes", [c["key"] for c in C.components(False, version="2026-09")])
        self.assertIn("c35.dinner_set", [c["key"] for c in C.components(False)])

    def test_retired_keys_stay_in_the_catalogue_list(self):
        keys = [r[0] for r in C.CATALOGUE]
        for k in C.RETIRED:
            self.assertIn(k, keys)
            self.assertGreater(C.RETIRED[k], "2026-09")

    def test_41_criteria_without_pool_47_with(self):
        self.assertEqual(C.criteria_count(False), 41)
        self.assertEqual(C.criteria_count(True), 47)

    def test_pool_section_is_exactly_six(self):
        pool = [c for c in C.components(True) if c["pool_only"]]
        self.assertEqual(len(pool), 6)
        self.assertTrue(all(42 <= c["criterion_no"] <= 47 for c in pool))


class TestStability(unittest.TestCase):
    def test_keys_unique(self):
        keys = [r[0] for r in C.CATALOGUE]
        self.assertEqual(len(keys), len(set(keys)))

    def test_keys_match_frozen_snapshot_in_order(self):
        self.assertEqual([r[0] for r in C.CATALOGUE], FROZEN_KEYS)

    def test_every_row_well_formed(self):
        for r in C.CATALOGUE:
            self.assertEqual(len(r), len(C.FIELDS), r[0])
            key, section, no, crit, label, kind, billed, hint = r
            self.assertIn(section, C.SECTION_LABEL, key)
            self.assertIn(kind, C.KINDS, key)
            self.assertIn(billed, C.BILLED, key)
            self.assertIn(hint, C.HINTS, key)
            self.assertTrue(1 <= no <= 47, key)
            self.assertTrue(crit and label, key)
            # the key prefix carries the criterion number, so a row can never drift sections
            self.assertEqual(int(key[1:3]), no, key)

    def test_version_present(self):
        self.assertTrue(C.CATALOGUE_VERSION)

    def test_document_components_map_to_license_tasks(self):
        docs = {c["key"] for c in C.components(True) if c["kind"] == "document"}
        self.assertEqual(docs, set(C.DOCUMENT_TASK_KEY))
        for k in C.DOCUMENT_TASK_KEY.values():
            self.assertTrue(k.startswith("s5."))

    def test_wifi_key_is_a_product(self):
        self.assertEqual(C.by_key(C.WIFI_KEY)["kind"], "product")

    def test_official_wording_present_for_all_47(self):
        self.assertEqual(sorted(C.DESCRIPTION_AR), list(range(1, 48)))
        for c in C.components(True):
            self.assertTrue(c["description_ar"])

    def test_merged_criterion_still_counted(self):
        self.assertEqual(C.criteria_count(False), 41)
        self.assertEqual(C.criteria_count(True), 47)
        self.assertNotIn(18, {c["criterion_no"] for c in C.components(False)})


if __name__ == "__main__":
    unittest.main()
