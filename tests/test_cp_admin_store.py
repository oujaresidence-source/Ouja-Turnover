# -*- coding: utf-8 -*-
"""
cp.admin_store — the cp_admin.json overlay (v2 plan Task 2).

The contract: repo cp/data/*.json stay the DEFAULTS; everything the dashboard
edits lives in one overlay in STATE_DIR; the renderer merges defaults ← overlay
key-by-key; publish copies the working overlay into history (last 10) and marks
it live; rollback restores any of the 10 exactly. Validators refuse garbage at
the store level so no handler can save it by accident.

Run: python3 -m unittest tests.test_cp_admin_store
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cp import admin_store  # noqa: E402


class _Disk:
    def __init__(self):
        self.data = {}

    def load(self, name, default=None):
        return copy.deepcopy(self.data.get(name, default))

    def save(self, name, obj):
        self.data[name] = copy.deepcopy(obj)
        return True


def store(disk=None):
    return admin_store.Store(load_json=(disk or _Disk()).load,
                             save_json=(disk or _Disk()).save) if disk is None \
        else admin_store.Store(load_json=disk.load, save_json=disk.save)


class SchemaAndDefaults(unittest.TestCase):
    def test_first_load_creates_schema_v1(self):
        s = store(_Disk())
        ov = s.overlay()
        self.assertEqual(ov["schema_version"], 1)
        self.assertEqual(ov["published_version"], "v1")
        self.assertEqual(ov["contacts"]["whatsapp"], "966533779297")
        self.assertEqual(ov["showcase"]["max"], 6)
        self.assertEqual(ov["history"], [])

    def test_unknown_top_level_keys_are_dropped_on_save(self):
        d = _Disk()
        s = store(d)
        s.update_section("contacts", {"whatsapp": "966512345678"}, by="u1")
        d.data["cp_admin.json"]["evil"] = {"x": 1}
        s2 = store(d)
        self.assertNotIn("evil", s2.overlay())


class Validators(unittest.TestCase):
    def setUp(self):
        self.s = store(_Disk())

    def test_whatsapp_digits_only(self):
        with self.assertRaises(admin_store.ValidationError):
            self.s.update_section("contacts", {"whatsapp": "not-a-number"}, by="u")
        self.s.update_section("contacts", {"whatsapp": "+966 5 1234 5678"}, by="u")
        self.assertEqual(self.s.overlay()["contacts"]["whatsapp"], "966512345678")

    def test_email_shape(self):
        with self.assertRaises(admin_store.ValidationError):
            self.s.update_section("contacts", {"email": "nope"}, by="u")

    def test_booking_link_must_be_http_or_empty(self):
        with self.assertRaises(admin_store.ValidationError):
            self.s.update_section("contacts", {"booking_link": "javascript:alert(1)"}, by="u")
        self.s.update_section("contacts", {"booking_link": ""}, by="u")
        self.s.update_section("contacts", {"booking_link": "https://calendly.com/ouja"}, by="u")

    def test_at_least_one_booking_mode_stays_on(self):
        with self.assertRaises(admin_store.ValidationError):
            self.s.update_section("contacts", {"booking_modes": {"online": False, "office": False}}, by="u")

    def test_slots_subset(self):
        with self.assertRaises(admin_store.ValidationError):
            self.s.update_section("contacts", {"slots": ["am", "midnight"]}, by="u")

    def test_showcase_hard_max(self):
        with self.assertRaises(admin_store.ValidationError):
            self.s.update_section("showcase", {"max": 13}, by="u")
        self.s.update_section("showcase", {"max": 12}, by="u")

    def test_shots_capped_at_three(self):
        shots = [{"id": str(i), "caption_ar": "", "path": "x"} for i in range(4)]
        with self.assertRaises(admin_store.ValidationError):
            self.s.update_section("shots", shots, by="u")

    def test_reviews_ids_are_ints_capped_at_six(self):
        with self.assertRaises(admin_store.ValidationError):
            self.s.update_section("reviews", {"ids": [1, 2, 3, 4, 5, 6, 7]}, by="u")
        self.s.update_section("reviews", {"ids": [86, 117, 97]}, by="u")

    def test_update_stamps_by_and_at(self):
        self.s.update_section("contacts", {"email": "a@b.co"}, by="faisal")
        ov = self.s.overlay()
        self.assertEqual(ov["updated_by"], "faisal")
        self.assertTrue(ov["updated_at"])


class MergePrecedence(unittest.TestCase):
    def test_default_when_overlay_silent(self):
        s = store(_Disk())
        merged = s.merged_manual({"median_response_minutes":
                                  {"value": 2.3, "as_of": "2026-08-26", "source": "x"}})
        self.assertEqual(merged["median_response_minutes"]["value"], 2.3)

    def test_overlay_wins_when_set(self):
        s = store(_Disk())
        s.update_section("figures_manual", {"median_response_minutes":
                                            {"value": 2.1, "as_of": "2026-09-01",
                                             "source": "sample"}}, by="u")
        merged = s.merged_manual({"median_response_minutes":
                                  {"value": 2.3, "as_of": "2026-08-26", "source": "x"}})
        self.assertEqual(merged["median_response_minutes"]["value"], 2.1)

    def test_incomplete_manual_entry_is_refused(self):
        s = store(_Disk())
        with self.assertRaises(admin_store.ValidationError):
            s.update_section("figures_manual",
                             {"messages_total": {"value": 160000, "as_of": "",
                                                 "source": "x"}}, by="u")


class PublishAndRollback(unittest.TestCase):
    def setUp(self):
        self.disk = _Disk()
        self.s = store(self.disk)

    def test_publish_appends_history_and_marks_live(self):
        self.s.update_section("contacts", {"email": "a@b.co"}, by="u")
        self.s.publish("v2", by="admin1")
        ov = self.s.overlay()
        self.assertEqual(ov["published_version"], "v2")
        self.assertEqual(len(ov["history"]), 1)
        self.assertEqual(ov["history"][0]["by"], "admin1")
        self.assertEqual(ov["history"][0]["version"], "v2")

    def test_history_caps_at_ten(self):
        for i in range(12):
            self.s.update_section("contacts", {"office_label_ar": "مكتب %d" % i}, by="u")
            self.s.publish("v2", by="u")
        self.assertEqual(len(self.s.overlay()["history"]), 10)

    def test_published_snapshot_is_frozen_not_live(self):
        """The public page renders the PUBLISHED overlay; edits after publish
        must not leak until the next publish."""
        self.s.update_section("contacts", {"office_label_ar": "الأصل"}, by="u")
        self.s.publish("v2", by="u")
        self.s.update_section("contacts", {"office_label_ar": "مسودة"}, by="u")
        self.assertEqual(self.s.published_overlay()["contacts"]["office_label_ar"], "الأصل")
        self.assertEqual(self.s.overlay()["contacts"]["office_label_ar"], "مسودة")

    def test_rollback_restores_exactly(self):
        self.s.update_section("contacts", {"office_label_ar": "أول"}, by="u")
        self.s.publish("v2", by="u")
        self.s.update_section("contacts", {"office_label_ar": "ثاني"}, by="u")
        self.s.publish("v2", by="u")
        entries = self.s.overlay()["history"]
        self.s.rollback(entries[0]["at"], by="admin1")
        self.assertEqual(self.s.published_overlay()["contacts"]["office_label_ar"], "أول")

    def test_unknown_rollback_target_raises(self):
        with self.assertRaises(admin_store.ValidationError):
            self.s.rollback("2020-01-01T00:00:00", by="u")


if __name__ == "__main__":
    unittest.main()
